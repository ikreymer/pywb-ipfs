from __future__ import absolute_import

from pywb.rewrite.rewrite_live import LiveRewriter

from pywb_liverec.liverec import request, ReadFullyStream, orig_requests
from pywb_liverec.warcrecorder import SingleFileWARCRecorder
from pywb_liverec.redisindexer import RedisIndexer

from redis import StrictRedis

from io import BytesIO

indexer = RedisIndexer(StrictRedis(), 'warc:cdxj')


#=================================================================
class WARCRecFactory(object):
    def __call__(self):
        return SingleFileWARCRecorder('./record.warc.gz', indexer)


#=================================================================
class LiveRecordRewriter(LiveRewriter):
    def __init__(self, *args, **kwargs):
        super(LiveRecordRewriter, self).__init__(*args, **kwargs)

        def live_rec(*args, **kwargs):
            return request(recorder_maker=self._get_recorder_factory(), *args, **kwargs)

        self.live_request = live_rec

    def is_recording(self):
        return True

    def _get_recorder_factory(self):
        return WARCRecFactory()

    def fetch_http(self, *args, **kwargs):
        status_headers, stream = super(LiveRecordRewriter, self).fetch_http(*args, **kwargs)
        stream = ReadFullyStream(stream)
        return status_headers, stream

    def add_metadata(self, url, headers, content):
        recorder = WARCRecFactory()()
        data = BytesIO()
        data.write(content)
        url = url.replace('http:/', 'metadata:/')
        recorder.add_user_record(url, headers['Content-Type'], data)

    def get_video_info(self, url):
        with orig_requests():
            return super(LiveRecordRewriter, self).get_video_info(url)
