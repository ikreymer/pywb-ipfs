# pywb-ipfs

Very experimental demo of recording WARC data to IPFS

Requires redis (for now) and IPFS (of course).

Uses new (experimental) live rec system for writing WARCs

## Installation

1. `pip install -r requirements.txt`

2. Start ipfs daemon (if not already running) `ipfs daemon`

3. `uwsgi uwsgi.ini`

4. `http://localhost:9080/record/example.com/` to record a url

5. `http://localhost:9080/replay/example.com/` to replay the recording. If all goes well, the replay will be
served from a WARC record stored in IPFS.


WARC records are recorded to a local dir, then uploaded to IPFS and removed.

Redis is used for CDXJ (indexing) for recording and replay, but a copy is also written to IPFS.
