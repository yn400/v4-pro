"""Check release status in detail."""
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

# List all releases
url = 'https://api.github.com/repos/yn400/v4-pro/releases'
req = urllib.request.Request(url)
req.add_header('Authorization', 'token ' + token)
req.add_header('User-Agent', 'v4-pro')

try:
    result = json.loads(urllib.request.urlopen(req).read())
    print('Total releases:', len(result))
    for r in result:
        tag = r.get('tag_name', '?')
        state = r.get('state', '?')
        draft = r.get('draft', '?')
        url_r = r.get('html_url', '?')
        print('  ' + tag + ' state=' + state + ' draft=' + str(draft) + ' url=' + url_r)
except urllib.error.HTTPError as e:
    print('HTTP ' + str(e.code) + ': ' + e.read().decode()[:200])
