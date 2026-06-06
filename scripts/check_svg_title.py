"""Check SVG title and first content line."""
import re
import sys

c = open(sys.argv[1], encoding='utf-8').read()

title_match = re.search(r'<text class="terminal.*?-title"[^>]*>([^<]+)</text>', c)
if title_match:
    title = title_match.group(1).replace('&#160;', ' ')
    print(f'Title bar: "{title}"')
else:
    print('Title: NOT FOUND')

# Find first line content
for m in re.finditer(r'class="terminal[^"]*-r\d+"[^>]*>([^<]+)<', c):
    text = m.group(1).replace('&#160;', ' ')
    if text.strip():
        print(f'First content: "{text.strip()}"')
        break
