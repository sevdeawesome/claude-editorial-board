#!/usr/bin/env python3
"""Slice a clean HTML file into per-section scratch files for review subagents.

Usage: python3 slice.py <clean.html> <work_dir>

Splits at every <h1>/<h2>, keeps front matter (before the second heading) as
slice 01, and prints a manifest with word counts so the orchestrator can group
small sections into one agent (~350-700 words per agent is the sweet spot).
Slices are verbatim byte ranges of the clean file — snippets taken from a
slice are guaranteed to be verbatim substrings of the clean file.
"""
import re, html, sys, os

CLEAN, WORK = sys.argv[1], sys.argv[2]
src = open(CLEAN).read()
os.makedirs(WORK, exist_ok=True)

body_start = src.find('<body')
heads = [(m.start(), html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip() or '(untitled)')
         for m in re.finditer(r'<(h[12])[^>]*>(.*?)</\1>', src, re.S)]

bounds = []
for i, (pos, text) in enumerate(heads):
    end = heads[i + 1][0] if i + 1 < len(heads) else src.find('</body>')
    bounds.append((pos, end, text))

def words(s):
    s = re.sub(r'</?(span|a|sup|b|i|u)\b[^>]*>', '', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    return len(html.unescape(s).split())

print(f'{"slice":8} {"words":>6}  heading')
for i, (a, b, text) in enumerate(bounds, 1):
    fn = os.path.join(WORK, f'slice_{i:02d}.html')
    open(fn, 'w').write(src[a:b])
    print(f'{i:02d}       {words(src[a:b]):>6}  {text[:70]}')
print(f'\n{len(bounds)} slices written to {WORK}/')
print('Group adjacent small slices per agent (~350-700 words each); '
      'agents may receive multiple slice files.')
