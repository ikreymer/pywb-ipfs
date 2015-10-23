from pywb.utils.canonicalize import calc_search_range
from pywb.cdx.cdxobject import CDXObject
from pywb.warc.cdxindexer import write_cdx_index
from pywb.utils.timeutils import timestamp_to_datetime

from io import BytesIO

class RedisIndexer(object):
    def __init__(self, redis, key):
        self.redis = redis
        self.key = key

    def add_record(self, stream, name=None):
        stream.seek(0)
        if not name:
            name = stream.name

        cdxout = BytesIO()
        write_cdx_index(cdxout, stream, name,
                        cdxj=True, append_post=True)

        cdxes = cdxout.getvalue()
        for cdx in cdxes.split('\n'):
            if cdx:
                self.redis.zadd(self.key, 0, cdx)

        return cdx

    def lookup(self, digest, url, timestamp):
        start, end = calc_search_range(url, 'exact')
        results = self.redis.zrangebylex(self.key, '[' + start, '(' + end)
        for res in results:
            cdx = CDXObject(res)
            if digest == cdx.get('digest'):
                return ('revisit', cdx['url'], timestamp_to_datetime(cdx['timestamp']))

        return None

