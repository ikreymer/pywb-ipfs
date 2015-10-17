#from patchy import record_requests, patched_requests


#url = 'http://www.iana.org/domains/example'
url = 'https://eff.org/'


from liverec import request, patched_requests

s = patched_requests.Session()

r = request('http://example.com/', session=s, stream=False)

#with record_requests(url):
#    r = patched_requests.get(url, stream=True, allow_redirects=False)

#r.raw.read(10)
#r.raw.read()
r.close()
