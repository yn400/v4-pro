"""Delete draft release."""
import json
import subprocess
import urllib.error
import urllib.request

p = subprocess.run(['git','credential','fill'],
    input='protocol=https\nhost=github.com\n\n',
    capture_output=True, text=True, timeout=5)
token = ''
for line in p.stdout.strip().split('\n'):
    k_v = line.split('=', 1)
    if k_v[0] == 'password':
        token = k_v[1]

url = 'https://api.github.com/repos/yn400/v4-pro/releases'
req = urllib.request.Request(url)
req.add_header('Authorization', 'token ' + token)
req.add_header('User-Agent', 'v4-pro')

for r in json.loads(urllib.request.urlopen(req).read()):
    if r.get('draft'):
        rid = r['id']
        req2 = urllib.request.Request(
            'https://api.github.com/repos/yn400/v4-pro/releases/' + str(rid),
            method='DELETE')
        req2.add_header('Authorization', 'token ' + token)
        req2.add_header('User-Agent', 'v4-pro')
        urllib.request.urlopen(req2)
        print('Deleted draft id=' + str(rid))
    else:
        print('Published: ' + r.get('html_url', '?'))
