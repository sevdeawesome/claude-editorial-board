#!/usr/bin/env python3
"""Convert a Google Docs HTML export into minimal semantic HTML.

Usage: python3 clean.py <export.html> <clean_out.html> [--title "Page Title"]

- Auto-detects the export's bold/italic/underline class names from its CSS.
- Drops images, class soup, and Google redirect-wrapped / ad-tracking URLs.
- Preserves <p>/<h1>-<h3>/<ul>/<ol>/<li>, bold, italic, links, sup, and
  Google Docs comment refs (kept as .gdoc-comment divs — they are review flags).
- Verifies visible text is identical to the export before writing.
"""
import re, html, sys
from urllib.parse import unquote

args = [a for a in sys.argv[1:] if not a.startswith('--')]
SRC, OUT = args[0], args[1]
title = 'Cleaned document'
if '--title' in sys.argv:
    title = sys.argv[sys.argv.index('--title') + 1]

src = open(SRC).read()
body = src[src.find('<body'):src.find('</body>')]

# auto-detect formatting classes from the export's CSS
css = src[src.find('<style'):src.find('</style>')]
BOLD = ITAL = UNDER = None
for m in re.finditer(r'\.(c\d+)\{([^}]*)\}', css):
    props = m.group(2)
    if 'font-weight:700' in props and BOLD is None:
        BOLD = m.group(1)
    if 'font-style:italic' in props and ITAL is None:
        ITAL = m.group(1)
    if 'text-decoration:underline' in props and UNDER is None:
        UNDER = m.group(1)
print('detected classes  bold:', BOLD, ' italic:', ITAL, ' underline:', UNDER)

def classes_of(tag_open):
    m = re.search(r'class="([^"]*)"', tag_open)
    return m.group(1).split() if m else []

def clean_inline(inner):
    out = []
    pos = 0
    for m in re.finditer(r'<[^>]+>', inner):
        if inner[pos:m.start()]:
            out.append(('text', inner[pos:m.start()]))
        out.append(('tag', m.group(0)))
        pos = m.end()
    if inner[pos:]:
        out.append(('text', inner[pos:]))

    res, span_stack, a_href = [], [], None
    for kind, t in out:
        if kind == 'text':
            res.append(t)
            continue
        if t.startswith('<span'):
            cls = classes_of(t)
            wraps = []
            if BOLD in cls: wraps.append('b')
            if ITAL in cls: wraps.append('i')
            if UNDER in cls and a_href is None: wraps.append('u')
            for w in wraps: res.append(f'<{w}>')
            span_stack.append(wraps)
        elif t.startswith('</span'):
            if span_stack:
                for w in reversed(span_stack.pop()):
                    res.append(f'</{w}>')
        elif t.startswith('<a '):
            m = re.search(r'href="([^"]*)"', t)
            href = m.group(1) if m else ''
            gm = re.match(r'https://www\.google\.com/url\?q=([^&]*)', href)
            if gm:
                href = unquote(html.unescape(gm.group(1)))
            idm = re.search(r'id="([^"]*)"', t)
            idattr = f' id="{idm.group(1)}"' if idm else ''
            if href:
                res.append(f'<a{idattr} href="{html.escape(href, quote=True)}">')
                a_href = href
            else:
                res.append(f'<a{idattr}>')
                a_href = ''
        elif t.startswith('</a'):
            res.append('</a>')
            a_href = None
        elif t.startswith('<sup'):
            res.append('<sup>')
        elif t.startswith('</sup'):
            res.append('</sup>')
        elif t.startswith('<br'):
            res.append('<br>')
        # <img> and everything else: dropped
    s = ''.join(res)
    s = s.replace('<b></b>', '').replace('<i></i>', '').replace('<u></u>', '')
    for w in ('b', 'i', 'u'):
        s = s.replace(f'</{w}><{w}>', '')
    return s

blocks = []
for m in re.finditer(r'<(p|h1|h2|h3|ul|ol|div)([^>]*)>(.*?)</\1>', body, re.S):
    tag, attrs, inner = m.group(1), m.group(2), m.group(3)
    if tag in ('ul', 'ol'):
        items = re.findall(r'<li[^>]*>(.*?)</li>', inner, re.S)
        lis = '\n'.join(f'  <li>{clean_inline(i).strip()}</li>' for i in items)
        blocks.append(f'<{tag}>\n{lis}\n</{tag}>')
    elif tag == 'div':
        if 'cmnt' in inner:  # Google Docs comment — keep visible, it is a review flag
            ps = re.findall(r'<p[^>]*>(.*?)</p>', inner, re.S)
            content = ' '.join(clean_inline(p).strip() for p in ps)
            blocks.append(f'<div class="gdoc-comment">{content}</div>')
    else:
        cls = classes_of('<x ' + attrs + '>')
        cleaned = clean_inline(inner).strip()
        if not re.sub(r'<[^>]+>', '', cleaned).strip():
            continue
        if 'title' in cls:
            blocks.append(f'<p class="title">{cleaned}</p>')
        else:
            blocks.append(f'<{tag}>{cleaned}</{tag}>')

head = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:Georgia,serif;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.6;color:#1a1a1a;font-size:16px}}
h1{{font-size:26px;line-height:1.3;margin:1.4em 0 .5em}}
h2{{font-size:21px;margin:1.3em 0 .5em}}
h3{{font-size:18px;margin:1.2em 0 .4em}}
p.title{{font-size:30px;font-weight:700;line-height:1.25;margin:.8em 0 .4em}}
ul,ol{{margin:.4em 0 .9em;padding-left:26px}}
li{{margin:.35em 0}}
a{{color:#1155cc}}
.gdoc-comment{{border-left:3px solid #e8a33d;background:#fdf6e9;padding:8px 12px;margin:18px 0;font-size:13.5px;font-family:Arial,sans-serif;color:#5f4a1e}}
</style>
</head>
<body>
'''
result = head + '\n\n'.join(blocks) + '\n</body></html>\n'

# ---- parity check before writing ----
def vis(s):
    s = s[s.find('<body'):]
    s = re.sub(r'</?(span|a|sup|b|i|u)\b[^>]*>', '', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    return ' '.join(html.unescape(s).split())

a, b = vis(src), vis(result)
if a != b:
    import difflib
    sm = difflib.SequenceMatcher(None, a.split(), b.split())
    print('PARITY FAIL — first diffs:')
    n = 0
    for op in sm.get_opcodes():
        if op[0] != 'equal':
            print(' ', op[0], '| ORIG:', ' '.join(a.split()[op[1]:op[2]])[:100],
                  '|| CLEAN:', ' '.join(b.split()[op[3]:op[4]])[:100])
            n += 1
            if n > 8: break
    sys.exit(1)

open(OUT, 'w').write(result)
print(f'PARITY OK — wrote {OUT} ({len(result)} bytes, {len(b.split())} visible words)')
