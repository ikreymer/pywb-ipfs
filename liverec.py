from io import BytesIO


try:
    import httplib
except ImportError:
    import http.client as httplib


from contextlib import contextmanager

orig_connection = httplib.HTTPConnection

# ============================================================================
class RecordingStream(object):
    def __init__(self, fp, recorder):
        self.fp = fp
        self.recorder = recorder
        if hasattr(self.fp, 'unread'):
            self.unread = self.fp.unread

        if hasattr(self.fp, 'tell'):
            self.tell = self.fp.tell

    def read(self, amt=None):
        buff = self.fp.read(amt)
        self.recorder.write_response_buff(buff)
        return buff

    def readline(self, maxlen=None):
        line = self.fp.readline(maxlen)
        #if not buff.startswith('HTTP'):
        #    buff = self.recorder.filter_header_line(buff)
        #self.out.write(buff)
        self.recorder.write_response_line(line)
        return line

    def close(self):
        res = self.fp.close()
        self.recorder.finish_response()
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
            self.recorder.write_request(data)

        res = orig_connection.send(self, data)
        return res


    def request(self, *args, **kwargs):
        res = orig_connection.request(self, *args, **kwargs)

        if self.recorder:
            self.recorder.finish_request(self.sock)

        return res

    def getresponse(self, *args, **kwargs):
        res = orig_connection.getresponse(self, *args, **kwargs)
        return res


# ============================================================================
class Recorder(object):
    def __init__(self, url):
        self.url = url

        self.request = self._create_buffer()
        self.response = self._create_buffer()
        self.resp_header_offset = 0

    def _create_buffer(self):
        return BytesIO()

    def write_request(self, buff):
        self.request.write(buff)

    def finish_request(self, socket):
        print(self.request.getvalue())

    def write_response_line(self, line):
        self.response.write(line)

    def write_response_buff(self, buff):
        self.response.write(buff)

    def finish_response(self):
        print(self.response.getvalue())


# ============================================================================
httplib.HTTPConnection = RecordingHTTPConnection
# ============================================================================


@contextmanager
def record_requests(url, recorder_cls=Recorder):
    RecordingHTTPConnection.global_recorder = recorder_cls(url)
    yield
    RecordingHTTPConnection.global_recorder = None


import requests as patched_requests


def request(url, method='GET', recorder_cls=Recorder, session=patched_requests, **kwargs):
    with record_requests(url, recorder_cls):
        r = session.request(method=method,
                                     url=url,
                                     allow_redirects=False, **kwargs)

    return r


