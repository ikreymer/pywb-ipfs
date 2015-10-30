import tempfile
import uuid
import base64
import hashlib
import datetime
import zlib
import sys
import os

from collections import OrderedDict

from pywb.utils.loaders import LimitReader
from pywb.utils.bufferedreaders import BufferedReader


# ============================================================================
class BaseWARCRecorder(object):

    WARC_RECORDS = {'warcinfo': 'application/warc-fields',
         'response': 'application/http; msgtype=response',
         'revisit': 'application/http; msgtype=response',
         'request': 'application/http; msgtype=request',
         'metadata': 'application/warc-fields',
        }

    REVISIT_PROFILE = 'http://netpreserve.org/warc/1.0/revisit/uri-agnostic-identical-payload-digest'

    def __init__(self, gzip=True, dedup=None):
        self.gzip = True

        self.dedup = dedup

        self.target_ip = None
        self.url = None
        self.finished = False

        self.req_buff = self._create_buffer()
        self.req_block_digest = self._create_digester()

        self.resp_buff = self._create_buffer()
        self.resp_block_digest = self._create_digester()
        self.resp_payload_digest = self._create_digester()

        self.payload_offset = 0

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
        self.req_block_digest.update(buff)
        self.req_buff.write(buff)

    def finish_request(self, socket):
        ip = socket.getpeername()
        if ip:
            self.target_ip = ip[0]

    def write_response_line(self, buff):
        self.resp_block_digest.update(buff)
        self.resp_buff.write(buff)

    def write_response_buff(self, buff):
        if not self.payload_offset:
            self.payload_offset = self.resp_buff.tell()

        self.resp_block_digest.update(buff)
        self.resp_payload_digest.update(buff)
        self.resp_buff.write(buff)

    def finish_response(self, incomplete=False):
        if self.finished:
            return

        try:
            # Don't write incomplete responses
            if incomplete:
                print('Skipping incomplete record for: ' + self.url)
                return

            self.dt_now = datetime.datetime.utcnow()
            self.write_records()

        finally:
            self.finished = True
            self.resp_buff.close()
            self.req_buff.close()

    def _write_warc_response(self, out, dt=None, concur_id=None, warc_id=None):
        dt = dt or self.dt_now
        if self.dedup:
            try:
                result = self.dedup.lookup(self.resp_payload_digest,
                                           self.url, dt)
            except Exception as e:
                import traceback
                traceback.print_exc(e)
                result = None

            if result == 'skip':
                return

            if isinstance(result, tuple) and result[0] == 'revisit':
                return self._write_warc_revisit(out, dt,
                                                result[1], result[2], warc_id)

        headers = (
            ('WARC-Type', 'response'),
            ('WARC-Record-ID', warc_id or self._make_warc_id()),
            ('WARC-Date', self._make_date(dt)),
            ('WARC-Target-URI', self.url),
            ('WARC-IP-Address', self.target_ip),
            ('WARC-Concurrent-To', concur_id),
            ('WARC-Block-Digest', self.resp_block_digest),
            ('WARC-Payload-Digest', self.resp_payload_digest)
        )

        self._write_warc_record(out, OrderedDict(headers), self.resp_buff)

    def _write_warc_revisit(self, out, dt, orig_url, orig_dt, warc_id=None):
        dt = dt or self.dt_now
        headers = (
            ('WARC-Type', 'revisit'),
            ('WARC-Record-ID', warc_id or self._make_warc_id()),
            ('WARC-Date', self._make_date(dt)),
            ('WARC-Target-URI', self.url),
            ('WARC-IP-Address', self.target_ip),
            ('WARC-Profile', self.REVISIT_PROFILE),
            ('WARC-Refers-To-Target-URI', orig_url),
            ('WARC-Refers-To-Date', self._make_date(orig_dt)),
            ('WARC-Payload-Digest', self.resp_payload_digest)
        )

        self.resp_buff.seek(0)

        header_buff = LimitReader(self.resp_buff, self.payload_offset)

        self._write_warc_record(out, OrderedDict(headers), header_buff,
                                length=self.payload_offset)

    def _write_warc_request(self, out, dt=None, concur_id=None, warc_id=None):
        dt = dt or self.dt_now
        headers = (
            ('WARC-Type', 'request'),
            ('WARC-Record-ID', warc_id or self._make_warc_id()),
            ('WARC-Date', self._make_date(dt)),
            ('WARC-Target-URI', self.url),
            ('WARC-Concurrent-To', concur_id),
            ('WARC-Block-Digest', self.resp_block_digest),
        )

        self._write_warc_record(out, OrderedDict(headers), self.req_buff)

    def _write_warc_metadata(self, out, url, content_type, data, dt=None, concur_id=None):
        dt = dt or datetime.datetime.utcnow()
        headers = (
            ('WARC-Type', 'metadata'),
            ('WARC-Record-ID', self._make_warc_id()),
            ('WARC-Date', self._make_date(dt)),
            ('WARC-Target-URI', url),
            ('WARC-Concurrent-To', concur_id),
        )

        self._write_warc_record(out, OrderedDict(headers), data,
                                content_type=content_type)

    def _write_warc_record(self, out, headers, buff, content_type=None, length=None):
        if self.gzip:
            out = GzippingWriter(out)

        self._line(out, 'WARC/1.0')

        for n, v in headers.iteritems():
            self._header(out, n, v)

        if not content_type:
            content_type = self.WARC_RECORDS[headers['WARC-Type']]

        self._header(out, 'Content-Type', content_type)

        if buff:
            if not length:
                length = buff.tell()
                buff.seek(0)

            self._header(out, 'Content-Length', length)
            # add empty line
            self._line(out, '')
            out.write(buff.read())
            # add two lines
            self._line(out, '\r\n')
        else:
            # add three lines (1 for end of header, 2 for end of record)
            self._line(out, 'Content-Length: 0\r\n\r\n')

        out.flush()

    def _header(self, out, name, value):
        if not value:
            return

        self._line(out, name + ': ' + str(value))

    def _line(self, out, line):
        out.write(line + '\r\n')

    @staticmethod
    def _make_warc_id(id_=None):
        if not id_:
            id_ = uuid.uuid1()
        return '<urn:uuid:{0}>'.format(id_)

    @staticmethod
    def _make_date(dt):
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


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

    def __eq__(self, string):
        digest = str(base64.b32encode(self.digester.digest()))
        if ':' in string:
            digest = self._type_ + ':' + digest
        return string == digest

    def __str__(self):
        return self.type_ + ':' + str(base64.b32encode(self.digester.digest()))


# ============================================================================
class SingleFileWARCRecorder(BaseWARCRecorder):
    def __init__(self, warcfilename, indexer=None):
        super(SingleFileWARCRecorder, self).__init__()
        self.warcfilename = warcfilename
        self.indexer = indexer

    def write_records(self):
        print('Writing {0} to {1} '.format(self.url, self.warcfilename))

        with open(self.warcfilename, 'a+b') as out:
            start = out.tell()
            resp_id = self._make_warc_id()

            self._write_warc_response(out, warc_id=resp_id)
            self._write_warc_request(out, concur_id=resp_id)
            out.flush()

            out.seek(start)
            if self.indexer:
                self.indexer.add_record(out, self.warcfilename)

    def add_user_record(self, url, content_type, data):
        with open(self.warcfilename, 'a+b') as out:
            start = out.tell()
            self._write_warc_metadata(out, url, content_type, data)
            out.flush()

            out.seek(start)
            if self.indexer:
                self.indexer.add_record(out, self.warcfilename)


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
