import tempfile
import uuid
import base64
import hashlib
import datetime
import zlib
import sys


# ============================================================================
class WARCRecorder(object):

    WARC_RECORDS = {'warcinfo': 'application/warc-fields',
         'response': 'application/http; msgtype=response',
         'revisit': 'application/http; msgtype=response',
         'request': 'application/http; msgtype=request',
         'metadata': 'application/warc-fields',
        }

    def __init__(self, url):
        self.url = url
        self.target_ip = None

        self.req_buff = self._create_buffer()
        self.req_block_digest = self._create_digester()

        self.resp_buff = self._create_buffer()
        self.resp_block_digest = self._create_digester()
        self.resp_payload_digest = self._create_digester()

    def _create_digester(self):
        return Digester('sha1')

    def _create_buffer(self):
        return tempfile.SpooledTemporaryFile(max_size=512*1024)

    def write_request(self, buff):
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
        orig_out = self._create_buffer()
        #orig_out = open('/tmp/test2.warc.gz', 'w')

        resp_id = self._make_warc_id()
        out = orig_out

        out = GzippingWriter(orig_out)
        self._write_warc_record(out, self.url, 'response', self.resp_buff,
                                warc_id=resp_id,
                                ip=self.target_ip,
                                payload_digest=self.resp_payload_digest,
                                block_digest=self.resp_block_digest)

        out = GzippingWriter(orig_out)
        self._write_warc_record(out, self.url, 'request', self.req_buff,
                                concur_to = resp_id,
                                block_digest=self.req_block_digest)

        orig_out.flush()
        #orig_out.close()
        orig_out.seek(0)
        sys.stdout.write(orig_out.read())

    def _header(self, out, name, value):
        self._line(out, name + ': ' + str(value))

    def _line(self, out, line):
        out.write(line + '\r\n')

    def _write_warc_record(self, out, uri, record_type, buff,
                           date=None, warc_id=None, ip=None, concur_to=None,
                           content_type=None,
                           payload_digest=None,
                           block_digest=None):

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

        if concur_to:
            self._header(out, 'WARC-Concurrent-To', concur_to)

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
    def _make_warc_id():
        return "<urn:uuid:%s>" % uuid.uuid1()

    @staticmethod
    def _make_date():
        return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


# ============================================================================
class GzippingWriter(object):
    def __init__(self, out):
        self.compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS + 16)
        self.out = out

    def write(self, buff):
        if isinstance(buff, str):
            buff = buff.encode('utf-8')
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
