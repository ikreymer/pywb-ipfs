from io import BytesIO

try:
    import httplib
except ImportError:
    import http.client as httplib


orig_connection = httplib.HTTPConnection

from contextlib import contextmanager

import ssl
from array import array


# ============================================================================
class RecordingStream(object):
    def __init__(self, fp, recorder):
        self.fp = fp
        self.recorder = recorder
        #self.recorder.start_response()

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
        self.recorder.write_response_line(line)
        return line

    def close(self):
        try:
            self.recorder.finish_response()
        except Exception as e:
            import traceback
            traceback.print_exc(e)

        res = self.fp.close()
        return res


# ============================================================================
class RecordingHTTPResponse(httplib.HTTPResponse):
    def __init__(self, recorder, *args, **kwargs):
        httplib.HTTPResponse.__init__(self, *args, **kwargs)
        self.fp = RecordingStream(self.fp, recorder)


# ============================================================================
class RecordingHTTPConnection(httplib.HTTPConnection):
    global_recorder_maker = None

    def __init__(self, *args, **kwargs):
        orig_connection.__init__(self, *args, **kwargs)
        if not self.global_recorder_maker:
            self.recorder = None
        else:
            self.recorder = self.global_recorder_maker()

            def make_recording_response(*args, **kwargs):
                return RecordingHTTPResponse(self.recorder, *args, **kwargs)

            self.response_class = make_recording_response

    def send(self, data):
        if not self.recorder:
            orig_connection.send(self, data)
            return

        if hasattr(data,'read') and not isinstance(data, array):
            url = None
            while True:
                buff = data.read(16384)
                if not buff:
                    break

                orig_connection.send(self, buff)
                self.recorder.write_request(url, buff)
        else:
            if not self.recorder.has_url():
                url = self._get_url(data)
            orig_connection.send(self, data)
            self.recorder.write_request(url, data)


    def _get_url(self, data):
        try:
            buff = BytesIO(data)
            line = buff.readline()

            path = line.split(' ', 2)[1]
            host = self.host
            port = self.port
            scheme = 'https' if isinstance(self.sock, ssl.SSLSocket) else 'http'

            url = scheme + '://' + host
            if (scheme == 'https' and port != '443') and (scheme == 'http' and port != '80'):
                url += ':' + port

            url += path
        except Exception as e:
            raise

        return url


    def request(self, *args, **kwargs):
        #if self.recorder:
        #    self.recorder.start_request(self)

        res = orig_connection.request(self, *args, **kwargs)

        if self.recorder:
            self.recorder.finish_request(self.sock)

        return res

    #def getresponse(self, *args, **kwargs):
    #    res = orig_connection.getresponse(self, *args, **kwargs)
    #    return res


# ============================================================================
class Recorder(object):
    def __init__(self, url):
        self.counters = dict(write_req=0, write_resp=0)
        self.request = self._create_buffer()
        self.response = self._create_buffer()
        self.url = None

    def has_url(self):
        return self.url is not None

    def _create_buffer(self):
        return BytesIO()

    def write_request(self, url, buff):
        #self.url = urls.pop(self)
        print(self.url)
        print(url)
        print(urls)

        #assert(url == self.url)
        #print(buff)
        self.request.write(buff)

    def write_response_line(self, line):
        self.response.write(line)

    def write_response_buff(self, buff):
        pass

    def finish_request(self, socket):
        #print(self.request.getvalue())
        #print(self.request.getvalue())
        self.counters['write_req'] += 1
        print(self.counters)

        #self.response.write('<BODY {0}>'.format(len(buff)))
        #self.response.write(buff)
        pass

    def finish_response(self):
        #print('RESPONSE')
        #print(self.response.getvalue())
        self.counters['write_resp'] += 1

        #print(self.response.getvalue())
        print(self.counters)


# ============================================================================
httplib.HTTPConnection = RecordingHTTPConnection
# ============================================================================


class DefaultRecorderMaker(object):
    def __call__(self):
        return Recorder()


@contextmanager
def record_requests(url, recorder_maker):
    if not recorder_maker:
        recorder_maker = DefaultRecorderMaker()

    RecordingHTTPConnection.global_recorder_maker = recorder_maker
    yield
    RecordingHTTPConnection.global_recorder_maker = None


import requests as patched_requests

def request(url, method='GET', recorder=None, session=patched_requests, **kwargs):
    with record_requests(url, recorder):
        kwargs['proxies'] = None
        kwargs['allow_redirects'] = False
        r = session.request(method=method,
                            url=url,
                            **kwargs)

    return r


def clearnow():
    RecordingHTTPConnection.global_recorder_maker = None

