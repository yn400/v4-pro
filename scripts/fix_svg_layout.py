"""Remove textLength attributes from Rich SVGs to prevent text overlapping."""
import re
import sys

for path in sys.argv[1:]:
    content = open(path, encoding='utf-8').read()
    original_len = len(content)
    # textLength forces exact character widths that cause overlap with CJK
    cleaned = re.sub(r' textLength="[^"]+"', '', content)
    open(path, 'w', encoding='utf-8').write(cleaned)
    removed = content.count('textLength') - cleaned.count('textLength')
    print(f'{path}: {original_len}B -> {len(cleaned)}B, removed {removed} textLength')
