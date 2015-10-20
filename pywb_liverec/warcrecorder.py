import tempfile
import uuid
import base64
import hashlib
import datetime
import zlib
import sys
import os


# ============================================================================
class BaseWARCRecorder(object):

    WARC_RECORDS = {'warcinfo': 'application/warc-fields',
         'response': 'application/http; msgtype=response',
         'revisit': 'application/http; msgtype=response',
         'request': 'application/http; msgtype=request',
         'metadata': 'application/warc-fields',
        }

    def __init__(self, gzip=True):
        self.gzip = True

        self.target_ip = None
        self.url = None
        self.finished = False

        self.req_buff = self._create_buffer()
        self.req_block_digest = self._create_digester()

        self.resp_buff = self._create_buffer()
        self.resp_block_digest = self._create_digester()
        self.resp_payload_digest = self._create_digester()

    def has_url(self):
        return self.url is not None

    def _create_digester(self):
        return Digester('sha1')

    def _create_buffer(self):
        return tempfile.SpooledTemporaryFile(max_size=512*1024)

    def start_request(self):
        pass

    def start_response(self):
        pass

    def write_request(self, url, buff):
        if not self.url:
            self.url = url
        print(self.url)
        self.req_block_digest.update(buff)
        self.req_buff.write(buff)

    def finish_request(self, socket):
        ip = socket.getpeername()
        if ip:
            self.target_ip = ip[0]

    def write_response_line(self, buff):
        #self.resp_header_offset += len(line)
        self.resp_block_digest.update(buff)
        self.resp_buff.write(buff)

    def write_response_buff(self, buff):
        self.resp_block_digest.update(buff)
        self.resp_payload_digest.update(buff)
        self.resp_buff.write(buff)

    def finish_response(self):
        if self.finished:
            return

        try:
            self.write_records()

        finally:
            self.finished = True
            self.resp_buff.close()
            self.req_buff.close()

    def _write_warc_response(self, out, concur_id=None, warc_id=None):
        self._write_warc_record(out, self.url, 'response', self.resp_buff,
                                concur_id=concur_id,
                                warc_id=warc_id,
                                ip=self.target_ip,
                                payload_digest=self.resp_payload_digest,
                                block_digest=self.resp_block_digest)

    def _write_warc_request(self, out, concur_id=None, warc_id=None):
        self._write_warc_record(out, self.url, 'request', self.req_buff,
                                concur_id=concur_id,
                                warc_id=warc_id,
                                block_digest=self.req_block_digest)

    def _header(self, out, name, value):
        self._line(out, name + ': ' + str(value))

    def _line(self, out, line):
        out.write(line + '\r\n')

    def _write_warc_record(self, out, uri, record_type, buff,
                           date=None, warc_id=None, ip=None, concur_id=None,
                           content_type=None,
                           payload_digest=None,
                           block_digest=None):

        if self.gzip:
            out = GzippingWriter(out)

        self._line(out, 'WARC/1.0')

        self._header(out, 'WARC-Type', record_type)

        if not warc_id:
            warc_id = self._make_warc_id()

        self._header(out, 'WARC-Record-ID', warc_id)

        if not date:
            date = self._make_date()
        self._header(out, 'WARC-Date', date)

        self._header(out, 'WARC-Target-URI', uri)

        if ip:
            self._header(out, 'WARC-IP-Address', ip)

        if concur_id:
            self._header(out, 'WARC-Concurrent-To', concur_id)

        if block_digest:
            self._header(out, 'WARC-Block-Digest', block_digest)

        if payload_digest:
            self._header(out, 'WARC-Payload-Digest', payload_digest)

        if not content_type:
            content_type = self.WARC_RECORDS[record_type]

        self._header(out, 'Content-Type', content_type)

        if buff:
            self._header(out, 'Content-Length', buff.tell())
            # add empty line
            self._line(out, '')
            buff.seek(0)
            out.write(buff.read())
            # add two lines
            self._line(out, '\r\n')
        else:
            # add three lines (1 for end of header, 2 for end of record)
            self._line(out, 'Content-Length: 0\r\n\r\n')

        out.flush()

    @staticmethod
    def _make_warc_id(id_=None):
        if not id_:
            id_ = uuid.uuid1()
        return '<urn:uuid:{0}>'.format(id_)

    @staticmethod
    def _make_date():
        return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


# ============================================================================
class GzippingWriter(object):
    def __init__(self, out):
        self.compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS + 16)
        self.out = out

    def write(self, buff):
        #if isinstance(buff, str):
        #    buff = buff.encode('utf-8')
        buff = self.compressor.compress(buff)
        self.out.write(buff)

    def flush(self):
        buff = self.compressor.flush()
        self.out.write(buff)
        self.out.flush()


# ============================================================================
class Digester(object):
    def __init__(self, type_='sha1'):
        self.type_ = type_
        self.digester = hashlib.new(type_)

    def update(self, buff):
        self.digester.update(buff)

    def __str__(self):
        return self.type_ + ':' + str(base64.b32encode(self.digester.digest()))


# ============================================================================
class SingleFileWARCRecorder(BaseWARCRecorder):
    def __init__(self, warcfilename):
        super(SingleFileWARCRecorder, self).__init__()
        self.warcfilename = warcfilename

    def write_records(self):
        print('Writing {0} to {1} '.format(self.url, self.warcfile))
        with open(self.warcfilename, 'ab') as out:
            resp_id = self._make_warc_id()
            self._write_warc_response(out, warc_id=resp_id)
            self._write_warc_request(out, concur_id=resp_id)

            orig_out.flush()


# ============================================================================
class PerRecordWARCRecorder(BaseWARCRecorder):
    def __init__(self, warcdir):
        super(PerRecordWARCRecorder, self).__init__()
        self.warcdir = warcdir
        try:
            os.makedirs(warcdir)
        except:
            pass

    def write_records(self):
        resp_uuid = str(uuid.uuid1())
        resp_id = self._make_warc_id(resp_uuid)

        req_uuid = str(uuid.uuid1())
        req_id = self._make_warc_id(req_uuid)

        with open(os.path.join(self.warcdir, resp_uuid + '.warc.gz'), 'w') as out:
            self._write_warc_response(out, warc_id=resp_id)

        with open(os.path.join(self.warcdir, req_uuid + '.warc.gz'), 'w') as out:
            self._write_warc_request(out, warc_id=req_id, concur_id=resp_id)
