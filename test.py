#from patchy import record_requests, patched_requests


#url = 'http://www.iana.org/domains/example'
url = 'http://example.com/'


from liverec import request, patched_requests


from warcrecord import WARCRecorder

s = patched_requests.Session()

r = request(url, session=s, recorder_cls=WARCRecorder, stream=True)

#with record_requests(url):
#    r = patched_requests.get(url, stream=True, allow_redirects=False)

#r.raw.read(10)
r.raw.read()
r.close()
