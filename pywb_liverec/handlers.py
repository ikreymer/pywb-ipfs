from __future__ import absolute_import

from pywb.rewrite.rewrite_live import LiveRewriter

from pywb_liverec.liverec import request, ReadFullyStream

from pywb_liverec.warcrecorder import SingleFileWARCRecorder


#=================================================================
class WARCRecFactory(object):
    def __call__(self):
        return SingleFileWARCRecorder('./record')


#=================================================================
class LiveRecordRewriter(LiveRewriter):
    def __init__(self, *args, **kwargs):
        super(LiveRecordRewriter, self).__init__(*args, **kwargs)

        def live_rec(*args, **kwargs):
            return request(recorder=self._get_recorder_factory(), *args, **kwargs)

        self.live_request = live_rec

    def _get_recorder_factory(self):
        return WARCRecFactory()

    def fetch_http(self, *args, **kwargs):
        status_headers, stream = super(LiveRecordRewriter, self).fetch_http(*args, **kwargs)
        stream = ReadFullyStream(stream)
        return status_headers, stream
