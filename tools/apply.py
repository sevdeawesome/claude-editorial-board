#!/usr/bin/env python3
"""Apply review-agent JSON findings to a clean HTML file -> flagged HTML.

Usage: python3 apply.py <clean.html> <flagged_out.html> <findings_dir>

<findings_dir> holds the agents' out_*.json files (schema: findings /
heading_ratings / section_grades, plus one file with doc_flags + overall).
Optional <findings_dir>/anchors.json maps section-name substrings to raw-HTML
anchor text for sections that have no heading of their own:
  {"outpaces": {"before": "I expect AI to improve"}}

Grade boxes auto-anchor by fuzzy-matching section names to h1/h2 text.
The doc-level box goes after the first h1 (or p.title). All hard-won rules
from production runs are baked in — see comments.
"""
import json, html, re, glob, sys, os

CLEAN, OUT, FDIR = sys.argv[1], sys.argv[2], sys.argv[3]
doc = open(CLEAN).read()

FLAG_CSS = '''<style>
.flag{position:relative;cursor:help;border-radius:2px;padding:0 1px}
.flag-red{background-color:#ffd9d9;box-shadow:inset 0 -2px 0 #c62828}
.flag-yellow{background-color:#fff3ae;box-shadow:inset 0 -2px 0 #c7a500}
.flag-green{background-color:#d7f3d7;box-shadow:inset 0 -2px 0 #2e7d32}
.flag:hover,.flag.pinned{z-index:50}
.flag:hover::after,.flag.pinned::after{content:attr(data-note);position:absolute;left:0;top:100%;
width:430px;max-width:70vw;background:#212121;color:#fafafa;font-size:12.5px;line-height:1.5;
font-family:Arial,sans-serif;font-weight:400;font-style:normal;text-align:left;padding:10px 12px;
border-radius:6px;white-space:pre-line;z-index:99;box-shadow:0 4px 14px rgba(0,0,0,.35)}
.legend{position:sticky;top:0;background:#fffef8;border-bottom:2px solid #bbb;padding:8px 14px;
font-family:Arial,sans-serif;font-size:12.5px;z-index:100}
.legend b{margin-right:14px}
.doc-flags{border:2px solid #c62828;background:#fff5f5;border-radius:6px;padding:12px 16px;
margin:14px 0;font-family:Arial,sans-serif;font-size:13px;line-height:1.55}
.doc-flags .hdr{font-weight:700;color:#c62828}
.doc-flags ul{margin:6px 0 0 18px;padding:0}
.hlc{border:2px solid #5e35b1;background:#f3eeff;border-radius:6px;padding:12px 16px;margin:14px 0;
font-family:Arial,sans-serif;font-size:13px;line-height:1.55}
.hlc .hdr{font-weight:700;color:#5e35b1}
.hlc .grade{display:inline-block;font-weight:700;font-size:15px;border:2px solid #5e35b1;
border-radius:4px;padding:1px 8px;margin-left:8px;background:#fff}
</style>
'''

LEGEND = '''<div class="legend"><b><span style="background:#ffd9d9;padding:1px 6px">red</span> = violation</b>
<b><span style="background:#fff3ae;padding:1px 6px">yellow</span> = weak / questionable</b>
<b><span style="background:#d7f3d7;padding:1px 6px">green</span> = strongest writing</b>
hover any highlight for what&#39;s wrong + rewrites &mdash; <b>click to pin it open</b>
(click again, click elsewhere, or Esc to close) &middot; purple boxes = section grade &amp; how to raise it</div>
'''

JS = '''<script>
document.addEventListener('click', function (e) {
  var f = e.target.closest('.flag');
  if (f) { f.classList.toggle('pinned'); e.stopPropagation(); }
  else document.querySelectorAll('.flag.pinned').forEach(function (x) { x.classList.remove('pinned'); });
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape')
    document.querySelectorAll('.flag.pinned').forEach(function (x) { x.classList.remove('pinned'); });
});
</script>
'''

SEV_HDR = {'red': '⚠ RED FLAG', 'yellow': '⚠ YELLOW FLAG', 'green': '✔ GREEN'}

def note_text(f):
    sev = f['severity']
    cat = f.get('category', 'strong-prose' if sev == 'green' else 'style').upper()
    ww = html.unescape(html.unescape(f['whats_wrong']))  # transport may double-escape
    note = f'{SEV_HDR[sev]} — {cat}\n{ww}'
    alts = [html.unescape(html.unescape(a)) for a in f.get('alternatives', []) if a]
    if sev != 'green' and alts:
        note += '\n\nAlternatives:\n' + '\n'.join(f'{i+1}) {a}' for i, a in enumerate(alts))
    return html.escape(note, quote=True)

def vis_text(s):
    """Agent text -> safe visible HTML: resolve double-escaping, then escape
    any literal tags the agent quoted so they display as text (not markup)."""
    return html.escape(html.unescape(html.unescape(s)), quote=False)

def wrap(snippet_html, sev, note):
    return f'<span class="flag flag-{sev}" data-note="{note}">{snippet_html}</span>'

# ---------- load agent JSON ----------
findings, headings, grades, doc_flags, overall = [], [], [], [], None
for fn in sorted(glob.glob(os.path.join(FDIR, 'out_*.json'))):
    d = json.load(open(fn))
    findings.extend(d.get('findings', []))
    headings.extend(d.get('heading_ratings', []))
    grades.extend(d.get('section_grades', []))
    doc_flags.extend(d.get('doc_flags', []))
    if d.get('overall'):
        overall = d['overall']

anchors_cfg = {}
acfg = os.path.join(FDIR, 'anchors.json')
if os.path.exists(acfg):
    anchors_cfg = json.load(open(acfg))

applied, skipped = [], []

# ---------- 1. inline findings, LONGEST snippet first (short snippets would
# otherwise break longer matches) ----------
findings.sort(key=lambda f: -len(f.get('snippet', '')))
for f in findings:
    snip = f.get('snippet', '')
    if not snip or '<' in snip or '>' in snip:
        skipped.append((snip[:60], 'contains tag chars or empty'))
        continue
    cand = snip
    if doc.count(cand) == 0:
        cand = snip.replace('&amp;', '&')   # transport double-escaping
    if doc.count(cand) == 0:
        cand = html.unescape(snip)
    n = doc.count(cand)
    if n != 1:
        skipped.append((snip[:60], f'count={n}'))
        continue
    # self-collision guard: never match inside an existing data-note attribute
    idx = doc.find(cand)
    pre = doc[max(0, idx - 800):idx]
    if pre.rfind('data-note="') > max(pre.rfind('">'), pre.rfind('</span>')):
        skipped.append((snip[:60], 'inside data-note'))
        continue
    doc = doc.replace(cand, wrap(cand, f['severity'], note_text(f)), 1)
    applied.append((f['severity'], snip[:60]))

# ---------- 2. heading ratings (anchored between > and <) ----------
for h in headings:
    ht = h.get('heading_text', '').strip()
    if not ht:
        continue
    sev = h['severity']
    note = note_text({'severity': sev, 'category': h.get('category', 'heading'),
                      'whats_wrong': h.get('whats_wrong', ''),
                      'alternatives': h.get('alternatives', [])})
    done = False
    body_off = doc.find('<body')  # <title> in head may duplicate the h1 text
    for variant in (ht, ht + ' ', ht.rstrip(), ht.replace('&', '&amp;')):
        for pre_anchor in ('>', '>&nbsp;'):
            probe = pre_anchor + variant + '<'
            if doc.count(probe, body_off) == 1:
                idx = doc.find(probe, body_off)
                repl = pre_anchor + wrap(variant, sev, note) + '<'
                doc = doc[:idx] + repl + doc[idx + len(probe):]
                applied.append((sev, 'HEADING: ' + ht[:50]))
                done = True
                break
        if done:
            break
    if not done:
        if doc.count(ht, body_off) == 1 and '<' not in ht:
            idx = doc.find(ht, body_off)
            doc = doc[:idx] + wrap(ht, sev, note) + doc[idx + len(ht):]
            applied.append((sev, 'HEADING(loose): ' + ht[:50]))
        else:
            skipped.append(('HEADING: ' + ht[:50], f'count={doc.count(ht, body_off)}'))

# ---------- 3. section grade boxes (auto-anchor by heading fuzzy match) ----------
def heading_positions():
    """(normalized text, index after close tag) for every h1/h2 — computed on
    the CURRENT doc so already-inserted flags/spans are accounted for."""
    out = []
    for m in re.finditer(r'<(h[12])[^>]*>(.*?)</\1>', doc, re.S):
        text = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
        out.append((text, m.end()))
    return out

def norm_tokens(s):
    return set(re.findall(r'[a-z0-9]+', s.lower()))

def grade_box(g):
    assess = vis_text(g['assessment'])
    items = ''.join(f'<li>{vis_text(i)}</li>' for i in g['to_next_grade'])
    return (f'\n<div class="hlc"><span class="hdr">HIGH LEVEL COMMENT — {vis_text(g["section"])}</span>'
            f'<span class="grade">{g["grade"]}</span><br>\n{assess}'
            f'\n<br><b>To raise it a letter:</b><ul style="margin:6px 0 0 18px">{items}</ul></div>\n')

for g in grades:
    sec = g['section']
    # explicit anchors.json entry wins
    hit = None
    for key, spec in anchors_cfg.items():
        if key.lower() in sec.lower():
            hit = spec
            break
    if hit:
        tpos = doc.find(hit.get('before', hit.get('after', '')))
        if tpos == -1:
            skipped.append(('GRADE BOX: ' + sec, 'anchors.json text not found'))
            continue
        if 'before' in hit:
            pos = doc.rfind('<p>', 0, tpos)
            pos = pos if pos != -1 else tpos
        else:
            pos = doc.find('>', tpos) + 1
        doc = doc[:pos] + grade_box(g) + doc[pos:]
        applied.append(('grade', sec))
        continue
    # fuzzy match section name against heading texts
    stoks = norm_tokens(sec)
    best, best_score = None, 0.0
    for text, endpos in heading_positions():
        htoks = norm_tokens(text)
        if not htoks or not stoks:
            continue
        score = len(stoks & htoks) / min(len(stoks), len(htoks))
        if score > best_score:
            best, best_score = endpos, score
    if best is not None and best_score >= 0.5:
        doc = doc[:best] + grade_box(g) + doc[best:]
        applied.append(('grade', sec))
    elif any(w in sec.lower() for w in ('title', 'front')):
        # front-matter grades attach after the first heading
        hp = heading_positions()
        if hp:
            doc = doc[:hp[0][1]] + grade_box(g) + doc[hp[0][1]:]
            applied.append(('grade', sec))
        else:
            skipped.append(('GRADE BOX: ' + sec, 'no headings in doc'))
    else:
        skipped.append(('GRADE BOX: ' + sec,
                        f'no heading match (best={best_score:.2f}); add to anchors.json'))

# ---------- 4. doc-level box (after the first h1 / p.title) ----------
if overall:
    items = ''.join(f'<li><b>{vis_text(d["issue"])}</b> — {vis_text(d["detail"])}</li>'
                    for d in doc_flags)
    raise_items = ''.join(f'<li>{vis_text(i)}</li>' for i in overall.get('to_next_grade', []))
    assess = vis_text(overall.get('assessment', ''))
    box = (f'\n<div class="doc-flags"><span class="hdr">DOCUMENT-LEVEL FLAGS</span>'
           f'<span class="grade" style="border-color:#c62828;color:#c62828;display:inline-block;font-weight:700;'
           f'font-size:15px;border:2px solid #c62828;border-radius:4px;padding:1px 8px;margin-left:8px;background:#fff">'
           f'OVERALL: {overall["grade"]}</span><br>\n{assess}\n<ul>{items}</ul>'
           f'\n<b>To raise the overall grade a letter:</b><ul>{raise_items}</ul></div>\n')
    m = re.search(r'<p class="title"[^>]*>.*?</p>', doc, re.S) or \
        re.search(r'<h1[^>]*>.*?</h1>', doc, re.S)
    pos = m.end() if m else doc.find('<body') + len('<body>')
    doc = doc[:pos] + box + doc[pos:]
    applied.append(('doc-box', overall['grade']))

# ---------- 5. inject CSS / legend / JS ----------
doc = doc.replace('</head>', FLAG_CSS + '</head>', 1)
doc = doc.replace('<body>', '<body>\n' + LEGEND, 1)
doc = doc.replace('</body>', JS + '</body>', 1)

open(OUT, 'w').write(doc)

from collections import Counter
sev_counts = Counter(s for s, _ in applied if s in ('red', 'yellow', 'green'))
print(f'APPLIED: {len(applied)}  (red={sev_counts["red"]} yellow={sev_counts["yellow"]} green={sev_counts["green"]})')
print(f'SKIPPED: {len(skipped)}')
for s, why in skipped:
    print('  SKIP:', repr(s), '->', why)
