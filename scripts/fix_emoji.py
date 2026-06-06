"""Replace ALL non-ASCII characters in CLI source with ASCII-safe alternatives.
This is the most portable fix — works on any terminal, any OS."""
path = 'v4_pro/cli.py'
content = open(path, encoding='utf-8').read()

replacements = {
    # Checkmarks
    '\u2713': '[OK] ',         # ✓
    '\u2717': '[X] ',          # ✗
    '\u2714': '[OK] ',         # ✔
    '\u2716': '[X] ',          # ✖
    '\u2611': '[OK] ',         # ☑
    '\u25CF': '* ',            # ●
    '\u25C6': '<> ',           # ◆
    '\u25B6': '> ',            # ▶
    '\u25C0': '< ',            # ◀
    '\u25A0': '# ',            # ■
    '\u25CB': 'o ',            # ○
    '\u2660': '** ',           # ♠
    '\u2665': '** ',           # ♥
    '\u2666': '** ',           # ♦
    '\u2663': '** ',           # ♣
    '\u266A': '~ ',            # ♪
    '\u266B': '~ ',            # ♫
    '\u2192': '-> ',           # →
    '\u2190': '<- ',           # ←
    '\u2191': '^^ ',           # ↑
    '\u2193': 'vv ',           # ↓
    '\u21d2': '=> ',           # ⇒
    '\u21d0': '<= ',           # ⇐
    # Fullwidth characters
    '\uff01': '!',             # ！
    '\uff08': '(',             # （
    '\uff09': ')',             # ）
    '\uff0c': ',',             # ，
    '\uff0e': '.',             # ．
    '\uff1a': ':',             # ：
    '\uff1b': ';',             # ；
    '\uff1f': '?',             # ？
    # CJK punctuation that might be in text output
    '\u3001': ', ',            # 、
    '\u3002': '. ',            # 。
    '\u300a': '<<',            # 《
    '\u300b': '>>',            # 》
    '\u2014': '--',            # —
    '\u2013': '-',             # –
    '\u2018': "'",             # '
    '\u2019': "'",             # '
    '\u201c': '"',             # "
    '\u201d': '"',             # "
    '\u2022': '- ',            # •
    '\u2026': '...',           # …
}

for old, new in replacements.items():
    content = content.replace(old, new)

# Also check for any remaining non-ASCII characters that aren't in CJK range
# Keep Chinese characters (CJK Unified Ideographs U+4E00-U+9FFF) for docstrings
# but flag them
remaining_ascii = []
for i, ch in enumerate(content):
    code = ord(ch)
    if code > 127 and not (0x3400 <= code <= 0x9FFF) and not (0xF900 <= code <= 0xFAFF):
        if code not in [0x3000]:  # Ideographic space
            remaining_ascii.append((i, ch, hex(code)))

open(path, 'w', encoding='utf-8').write(content)
print(f'Replacements done. Remaining non-ASCII, non-CJK chars: {len(remaining_ascii)}')
for pos, ch, code in remaining_ascii[:10]:
    ctx = content[max(0,pos-5):min(len(content),pos+5)].replace('\n','\\n')
    print(f'  {code}: {ch} at {pos}: ...{ctx}...')
