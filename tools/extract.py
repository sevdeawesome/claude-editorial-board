#!/usr/bin/env python3
"""Extract the final JSON payload from a subagent transcript (.output JSONL).

Usage: python3 extract.py <agent.output> <out.json>

Never dump the .output file into context — it is a full transcript. This
script harvests the LAST assistant text block and repairs every JSON defect
seen in production:
  - markdown fences around the JSON
  - leading/trailing commentary outside the outermost {...}
  - trailing commas before } or ]
  - extra keys trailing after a prematurely closed root object
  - truncated output missing closing brackets ('}', ']}', '"]}')
Prints a one-line summary (keys + counts) — that is all the orchestrator needs.
"""
import json, sys, re

inpath, outpath = sys.argv[1], sys.argv[2]
last_text = None
with open(inpath) as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get('message', obj)
        content = msg.get('content')
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'text' and c.get('text', '').strip():
                    last_text = c['text']
        elif isinstance(content, str) and content.strip():
            last_text = content
        if isinstance(obj.get('result'), str) and obj['result'].strip():
            last_text = obj['result']

if not last_text:
    print('ERROR: no assistant text found')
    sys.exit(1)

t = last_text.strip()
m = re.search(r'```(?:json)?\s*(\{.*)\s*```?', t, re.S)
if m:
    t = m.group(1)
i = t.find('{')
if i == -1:
    print('ERROR: no JSON object found')
    sys.exit(1)
t = t[i:].strip()

data = None
# strategy 1: as-is, and truncation-repair suffixes
for suffix in ('', '}', ']}', '"]}', '"}]}'):
    try:
        data = json.loads(t + suffix)
        if suffix:
            print(f'repaired: appended {suffix!r}')
        break
    except json.JSONDecodeError:
        pass
# strategy 2: trailing commas
if data is None:
    t2 = re.sub(r',(\s*[}\]])', r'\1', t)
    try:
        data = json.loads(t2)
        print('repaired: removed trailing commas')
    except json.JSONDecodeError:
        pass
# strategy 3: root closed early with keys trailing — parse then merge
if data is None:
    try:
        data, end = json.JSONDecoder().raw_decode(t)
        rest = t[end:].strip().lstrip(',').strip()
        if rest:
            if rest.endswith('}') and not rest.startswith('{'):
                rest = '{' + rest
            extra = json.loads(rest)
            if isinstance(extra, dict):
                data.update(extra)
                print('repaired: merged trailing keys', list(extra.keys()))
    except json.JSONDecodeError as e:
        print(f'ERROR: unrepairable JSON ({e}). Inspect manually around char {e.pos}:')
        print(repr(t[max(0, e.pos - 150):e.pos + 100]))
        sys.exit(1)

# common shape fix: to_next_grade left outside the overall object
if isinstance(data, dict) and 'to_next_grade' in data and \
        isinstance(data.get('overall'), dict) and 'to_next_grade' not in data['overall']:
    data['overall']['to_next_grade'] = data.pop('to_next_grade')
    print('repaired: moved to_next_grade into overall')

open(outpath, 'w').write(json.dumps(data, ensure_ascii=False, indent=1))
summary = {k: (len(v) if isinstance(v, list) else 'obj') for k, v in data.items()}
print('OK', outpath, summary)
