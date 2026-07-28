#!/usr/bin/env python3
"""Verify a flagged file against its clean base. All three checks must pass.

Usage: python3 verify.py <clean.html> <flagged.html>

1. Visible-text parity after stripping injected elements (exit 1 on failure).
2. Stack-based tag balance over the whole flagged file.
3. Flag counts by severity; every .flag span carries a data-note.
"""
import re, html, sys

CLEAN, FLAGGED = sys.argv[1], sys.argv[2]
clean = open(CLEAN).read()
flagged = open(FLAGGED).read()

f = flagged
f = re.sub(r'<div class="legend">.*?</div>\n?', '', f, flags=re.S)
f = re.sub(r'<div class="doc-flags">.*?</ul></div>\n?', '', f, flags=re.S)
f = re.sub(r'<div class="hlc">.*?</ul></div>\n?', '', f, flags=re.S)
f = re.sub(r'<script>.*?</script>\n?', '', f, flags=re.S)
f = re.sub(r'<style>\n\.flag\{.*?</style>\n', '', f, flags=re.S)

def vis(s):
    s = s[s.find('<body'):]
    s = re.sub(r'</?(span|a|sup|b|i|u)\b[^>]*>', '', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    return ' '.join(html.unescape(s).split())

a, b = vis(clean), vis(f)
if a == b:
    print('1. TEXT PARITY: PASS')
else:
    print('1. TEXT PARITY: FAIL')
    import difflib
    sm = difflib.SequenceMatcher(None, a.split(), b.split())
    for op in sm.get_opcodes():
        if op[0] != 'equal':
            print('  ', op[0], '| CLEAN:', ' '.join(a.split()[op[1]:op[2]])[:120],
                  '|| FLAGGED:', ' '.join(b.split()[op[3]:op[4]])[:120])
            break
    sys.exit(1)

stack, ok = [], True
VOID = {'meta', 'br', 'img', 'hr', 'link', 'input'}
for m in re.finditer(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*?(/?)>', flagged):
    closing, tag, selfclose = m.group(1), m.group(2).lower(), m.group(3)
    if tag in VOID or selfclose:
        continue
    if not closing:
        stack.append((tag, m.start()))
    else:
        if not stack or stack[-1][0] != tag:
            print(f'2. TAG BALANCE: FAIL at {m.start()}: </{tag}> vs stack top {stack[-1] if stack else None}')
            ok = False
            break
        stack.pop()
if ok and stack:
    print('2. TAG BALANCE: FAIL, unclosed:', stack[-5:])
    ok = False
elif ok:
    print('2. TAG BALANCE: PASS')

flags = re.findall(r'<span class="flag flag-(red|yellow|green)"([^>]*)>', flagged)
from collections import Counter
c = Counter(s for s, _ in flags)
missing = sum(1 for _, attrs in flags if 'data-note="' not in attrs)
print(f'3. FLAGS: red={c["red"]} yellow={c["yellow"]} green={c["green"]} total={sum(c.values())}; missing data-note: {missing}')
print(f'   grade boxes: {flagged.count("HIGH LEVEL COMMENT")}, doc box: {flagged.count("DOCUMENT-LEVEL FLAGS")}')
sys.exit(0 if ok and missing == 0 else 1)
