"""Create Release v0.1.0."""
import json
import subprocess
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
data = json.dumps({
    'tag_name': 'v0.1.0',
    'name': 'V4 Pro v0.1.0',
    'body': 'First release of V4 Pro - AI Code Quality Gate.\n\nSee CHANGELOG.md for details.',
    'draft': False,
    'prerelease': False,
}).encode()

req = urllib.request.Request(url, data=data, method='POST')
req.add_header('Authorization', 'token ' + token)
req.add_header('Content-Type', 'application/json')
req.add_header('User-Agent', 'v4-pro')

try:
    result = json.loads(urllib.request.urlopen(req).read())
    print('Release created: ' + result.get('html_url', '?'))
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print('Error: ' + str(e.code) + ' ' + body[:200])
