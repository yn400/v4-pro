"""Check SVG for rendering issues."""
import sys

path = sys.argv[1]
content = open(path, encoding='utf-8').read()
print(f'Size: {len(content)} B')
print(f'Lines: {content.count(chr(10))}')
has_complex = ('╭' in content) or ('┌' in content)
has_textlen = 'textLength' in content
print(f'Complex tables: {has_complex}')
print(f'textLength (overlap prone): {has_textlen}')
print('Font: Fira Code + monospace')
if has_textlen:
    print('WARNING: SVG may have text overlapping')
else:
    print('OK: clean SVG without textLength artifacts')
