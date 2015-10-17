from io import BytesIO
import httplib
from contextlib import contextmanager
import tempfile

orig_connection = httplib.HTTPConnection


# ============================================================================
class RecordingStream(object):
    def __init__(self, fp, recorder):
        self.fp = fp
        self.recorder = recorder
        self.out = recorder.create_buffer()

        if hasattr(self.fp, 'unread'):
            self.unread = self.fp.unread

        if hasattr(self.fp, 'tell'):
            self.tell = self.fp.tell


    def read(self, amt=None):
        buff = self.fp.read(amt)
        self.out.write(buff)
        return buff

    def readline(self, maxlen=None):
        buff = self.fp.readline(maxlen)
        if not buff.startswith('HTTP'):
            buff = self.recorder.filter_header_line(buff)

        self.out.write(buff)
        return buff

    def close(self):
        res = self.fp.close()
        self.recorder.write_response(self.out)
        return res


# ============================================================================
class RecordingHTTPResponse(httplib.HTTPResponse):
    def __init__(self, recorder, *args, **kwargs):
        httplib.HTTPResponse.__init__(self, *args, **kwargs)
        self.fp = RecordingStream(self.fp, recorder)


# ============================================================================
class RecordingHTTPConnection(httplib.HTTPConnection):
    global_recorder = None

    def __init__(self, *args, **kwargs):
        orig_connection.__init__(self, *args, **kwargs)
        self.recorder = self.global_recorder

        if self.recorder:
            def make_recording_response(*args, **kwargs):
                return RecordingHTTPResponse(self.recorder, *args, **kwargs)

            self.response_class = make_recording_response

    def send(self, data):
        if self.recorder:
            self.req_buff.write(data)

        return orig_connection.send(self, data)

    def request(self, *args, **kwargs):
        if self.recorder:
            self.req_buff = self.recorder.create_buffer()

        res = orig_connection.request(self, *args, **kwargs)

        if self.recorder:
            self.recorder.write_request(self.req_buff)

        return res

    def getresponse(self, *args, **kwargs):
        res = orig_connection.getresponse(self, *args, **kwargs)
        return res


# ============================================================================
class Recorder(object):
    def __init__(self, url):
        self.url = url

    def create_buffer(self):
        return tempfile.SpooledTemporaryFile(max_size=512*1024)

    def write_request(self, buff):
        buff.seek(0)
        print(buff.read())

    def write_response(self, buff):
        buff.seek(0)
        print(buff.read())

    def filter_header_line(self, buff):
        return buff


# ============================================================================
httplib.HTTPConnection = RecordingHTTPConnection
# ============================================================================


@contextmanager
def record_requests(url, recorder_cls=Recorder):
    RecordingHTTPConnection.global_recorder = recorder_cls(url)
    yield
    RecordingHTTPConnection.global_recorder = None


import requests as patched_requests


def request(url, method='GET', session=patched_requests, **kwargs):
    with record_requests(url):
        r = session.request(method=method,
                                     url=url,
                                     allow_redirects=False, **kwargs)

    return r


