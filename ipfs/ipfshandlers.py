from pywb_liverec.warcrecorder import BaseWARCRecorder
from pywb_liverec.handlers import LiveRecordRewriter
from pywb_liverec.redisindexer import RedisIndexer

import os
import uuid

from io import BytesIO

from urllib import quote_plus

from ipfsApi import Client
from redis import StrictRedis

from pywb.utils.loaders import LOADERS, BlockLoader, load_yaml_config

from uwsgidecorators import timer


#=================================================================
def init():
    config = load_yaml_config('./config.yaml')

    ipfs_host = config.get('ipfs_host', 'localhost')
    ipfs_port = config.get('ipfs_port', 5001)
    redis_url = config.get('redis_url')

    global rec_dir
    rec_dir = config.get('tmp_rec_dir', '/tmp/rec')

    global ipfs_api
    ipfs_api = Client(ipfs_host, ipfs_port)

    global redis_cli
    redis_cli = StrictRedis.from_url(redis_url)

    LOADERS['ipfs'] = IPFSLoader


#=================================================================
class IPFSLoader(BlockLoader):
    def load(self, url, start=0, length=-1):
        url = url.split('ipfs://')[-1]
        stream = ipfs_api.cat(url, stream=True)
        return stream


#=================================================================
class IPFSRecMaker(object):
    def __init__(self, api, redis):
        self.api = api
        self.redis = redis

    def __call__(self):
        return IPFSWARCRecorder(rec_dir, self.api, self.redis)


#=================================================================
class IPFSRecorder(LiveRecordRewriter):
    def __init__(self, *args, **kwargs):
        super(IPFSRecorder, self).__init__(*args, **kwargs)

        self.redis = redis_cli
        self.api = ipfs_api

    def _get_recorder_factory(self):
        return IPFSRecMaker(self.api, self.redis)


# ============================================================================
class IPFSWARCRecorder(BaseWARCRecorder):
    def __init__(self, warcdir, ipfs, redis):
        super(IPFSWARCRecorder, self).__init__()
        self.warcdir = warcdir
        self.ipfs = ipfs
        self.redisindex = RedisIndexer(redis, 'ipfs:cdxj')

        # experimental dedup support
        #self.dedup = self.redisindex

        try:
            os.makedirs(warcdir)
        except:
            pass

    def write_records(self):
        resp_uuid = str(uuid.uuid1())
        resp_id = self._make_warc_id(resp_uuid)

        req_uuid = str(uuid.uuid1())
        req_id = self._make_warc_id(req_uuid)

        filename = os.path.join(self.warcdir, resp_uuid + '.warc.gz')

        with open(filename, 'w') as out:
            self._write_warc_response(out, warc_id=resp_id)
            out.flush()

        # for now, not writing 'request'
        #with open(os.path.join(self.warcdir, req_uuid + '.warc.gz'), 'w') as out:
        #    self._write_warc_request(out, warc_id=req_id, concur_id=resp_id)

        with open(filename, 'r') as stream:
            stream = CustomNameStream(stream, quote_plus(self.url))
            res = self.ipfs.add(stream)
            if not res:
                print('IPFS ADD FAILED')

            else:
                path = 'ipfs://' + res['Hash']
                self.redisindex.add_record(stream, path)

        os.remove(filename)


# ============================================================================
class CustomNameStream(object):
    """ Wrapper to specify custom name for file
    """
    def __init__(self, stream, name):
        self.stream = stream
        self._name = name

    @property
    def name(self):
        return self._name

    def read(self, maxlen=None):
        return self.stream.read(maxlen)

    def readinto(self, buff):
        return self.stream.readinto(buff)

    def close(self):
        return self.stream.close()

    def tell(self):
        return self.stream.tell()

    def seek(self, *args, **kwargs):
        return self.stream.seek(*args, **kwargs)


@timer(30, target='mule')
def update_index(signum):
    """ Periodically update the index from Redis and put into IPFS
    """
    cdx = redis_cli.zrange('ipfs:cdxj', 0, -1)
    cdx = ''.join(cdx)
    buff = BytesIO(cdx)

    # Add New Index
    res = ipfs_api.add(CustomNameStream(buff, 'index.cdxj'))
    print('Updating Index: ' + str(res))

    # Register with IPNS
    res = ipfs_api.name_publish(res['Hash'])
    print res



# ============================================================================
init()

