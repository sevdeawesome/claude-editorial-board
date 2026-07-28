# Writing Review Kit — flagged-HTML review, plug and play

Drop a Google Docs HTML export (or a .zip containing one) into `drop/` and ask
for a review. This file is the complete playbook: clean the export, fan out
review subagents over the writing guides, apply their findings as inline
color flags, verify, deliver. Battle-tested across multiple review rounds —
the gotchas below are all real.

## Layout

```
review_kit/
├── CLAUDE.md            ← this playbook
├── writing_guides/      ← EVERY .md here is a rubric source; point all agents at all of them
├── tools/               ← deterministic pipeline (no hardcoded paths; run with python3)
│   ├── clean.py         export.html → clean.html   (auto-detects format classes, checks parity)
│   ├── slice.py         clean.html → work/slice_NN.html + word-count manifest
│   ├── extract.py       agent .output transcript → validated out_*.json (repairs bad JSON)
│   ├── apply.py         clean.html + work/out_*.json → flagged.html
│   └── verify.py        clean.html vs flagged.html  (parity, tag balance, counts)
├── input/                ← user drops export .html or .zip here
├── work/                ← slices + agent JSONs for the current run (archive per round)
└── out/                 ← deliverables: <name>_clean.html, <name>_flagged.html, lab pages
```

## The deliverable

`out/<name>_flagged.html` — the document, visually identical, with three layers:

1. **Inline flags**: red = clear violation, yellow = weak/questionable,
   green = strongest passages (hunt greens honestly — they teach as much as reds).
   Hover shows what's wrong + 2–3 rewrites; click pins.
2. **One purple HIGH LEVEL COMMENT box per section**: letter grade, 2–3 sentence
   assessment, concrete checkable instructions to rise one letter.
3. **One red DOCUMENT-LEVEL FLAGS box** after the title: whole-document problems
   + overall grade.

Also produce `out/<name>_clean.html` — the de-soup'd export. It is the review
base AND a gift to the user: 40KB of Google class soup becomes ~120 readable
lines. **Never modify the original export.**

## Pipeline (follow in order)

```bash
K=review_kit   # run from the project root, adjust as needed
# 0. unzip if needed; find the export
unzip -o "$K/drop/whatever.zip" -d "$K/drop/"

# 1. clean (refuses to write on parity failure)
python3 $K/tools/clean.py "$K/drop/export.html" "$K/out/<name>_clean.html" --title "Doc Title"

# 2. inspect + slice
python3 $K/tools/slice.py "$K/out/<name>_clean.html" "$K/work/"
```

3. **Fan out review subagents in ONE message** (parallel, general-purpose,
   background). One agent per ~350–700 words (group small slices), plus ONE
   document-compliance agent that reads the whole clean file. Prompt contract
   below — follow it closely; the apply engine depends on it.

4. **Extract each agent's JSON as its completion notification arrives**:
   `python3 $K/tools/extract.py <task>.output $K/work/out_<X>.json`
   Never read/tail the .output transcript into context — extract.py exists so
   you only ever see a one-line summary.

5. **Apply + verify** (rerunnable — apply always rebuilds from clean):
   ```bash
   python3 $K/tools/apply.py  $K/out/<name>_clean.html $K/out/<name>_flagged.html $K/work/
   python3 $K/tools/verify.py $K/out/<name>_clean.html $K/out/<name>_flagged.html
   ```
   All three verify checks must pass before delivering. If apply reports a
   skipped grade box, add an entry to `work/anchors.json`
   (`{"section-name-substring": {"before": "raw text the box precedes"}}`) and rerun.

6. **Deliver a chat report**: grades table (section → grade → the one thing
   holding it back), flag counts, fastest wins. On a re-review, lead with
   what improved: fixed vs. survived, grade movement per section.

## Subagent prompt contract

Every section agent gets, verbatim where possible:

- Its slice path(s) in `work/`, plus one line saying what the slice contains.
- Instruction to read EVERY file in `writing_guides/` — prose guides (Pinker /
  Sword / Munger distillations) AND any house style guide. **House style
  violations in the draft are first-class findings, and the agent's own
  rewrites must comply with house style** (this bites constantly: spaced vs
  unspaced dashes, "U.S.", banned glossary terms, number style, heading case).
- The rubric: metadiscourse, hedging tics, zombie nouns, jargon without a
  handhold, vague abstraction, curse of knowledge, flab, grammar/mechanics,
  redundancy, structure. Seed it with 5–10 specific things YOU noticed in that
  slice ("verify yourself, flag only if real") — seeded agents come back sharper.
- Rate EVERY heading in the slice (title, h1/h2, bold run-in labels) red/yellow/green.
- Section grades: honest letters, `to_next_grade` items concrete and checkable
  ("cut X to Y words"), never vibes.
- On re-reviews: list what round N−1 flagged so the agent can green genuine
  fixes and catch survivors. Give last round's grade for comparison.
- **Final message = RAW JSON ONLY** (no fences), in this exact shape:

```json
{"findings": [{"snippet": "...", "severity": "red|yellow|green",
   "category": "grammar|hedging|metadiscourse|zombie-noun|jargon|vague|logic|redundancy|citation|rule-break|strong-prose",
   "whats_wrong": "problem + which rule (green: why it works)",
   "alternatives": ["rewrite 1", "rewrite 2"]}],
 "heading_ratings": [{"heading_text": "...", "severity": "...", "whats_wrong": "...", "alternatives": []}],
 "section_grades": [{"section": "...", "grade": "B+", "assessment": "2-3 sentences",
   "to_next_grade": ["...", "...", "..."]}]}
```

The doc-compliance agent returns `{"doc_flags": [{"issue", "detail"}], "overall":
{"grade", "assessment", "to_next_grade"}}` and checks: venue fit/length,
pre-publication debris (feedback notes, alternative-title lists, figure
placeholders, unresolved Doc comments — clean.py keeps comments visible as
`.gdoc-comment` divs), citation defects (bare "(source)" links, ad-tracking
querystrings, fragmented multi-anchor citations, duplicate cites), and
consistency sweeps (names, number style, quote marks, dash conventions, term
definitions, heading case).

### Snippet rules (tell every agent — these anchor automated edits)

- `snippet` must be a **verbatim substring of the raw slice bytes**, entities
  as-is (`&rsquo;` `&mdash;` `&nbsp;` stay escaped).
- **No `<` or `>`** — never span a tag boundary. Flag the longest clean run
  inside one element; note wider scope in `whats_wrong`.
- Prefer 6+ words, unique in the whole document.

## Gotchas (each cost a debugging cycle once)

- **Agent JSON is unreliable at the edges.** extract.py repairs: markdown
  fences, commentary around the JSON, trailing commas, truncated output
  missing `}`/`]}`, extra keys after a prematurely closed root,
  `to_next_grade` left outside `overall`. If it still fails it prints the
  bad region — fix surgically, never retype whole payloads.
- **Transport double-escapes entities** (`&amp;rsquo;` for `&rsquo;`,
  `R&amp;D` for `R&D`). apply.py retries snippets with `&amp;`→`&` and
  double-unescapes all display text. Any custom page builder must do the same
  or ampersands render literally.
- **Agents quote HTML in prose** ("the file contains `<p>Alternative
  titles:</p>`"). Any text destined for visible HTML must be escaped AFTER
  double-unescaping (apply.py `vis_text`) or the quoted tags become real tags
  and break tag balance.
- **Self-collision**: once flags are applied, tooltips contain quoted document
  phrases. apply.py refuses matches inside `data-note` attributes; anything
  extra you insert must anchor on surrounding raw HTML, not bare phrases.
- **Longest-snippet-first is mandatory** — short snippets break longer matches.
- **Grade-box anchoring**: apply.py fuzzy-matches section names to h1/h2 text
  (≥0.5 token overlap), sends "title/front matter" grades after the first
  heading, everything else needs `work/anchors.json`. Watch the SKIP report.
- **Google Docs word-splitting**: exports split words across spans
  (`resear</span><span>chers`). Any parity diff must strip inline tags to ''
  (not ' ') before comparing — clean.py and verify.py already do.
- **Between review rounds**: `mkdir work/roundN && mv work/out_*.json work/slice_* work/roundN/`
  before slicing the new export, or apply.py will load stale findings.
- **Agents sometimes save scratch files** in shared directories. apply.py
  globs `out_*.json` — keep the work dir clean.

## Optional labs (on request)

The same pattern — persona deliberation in one or more subagents, RAW JSON
back, a self-contained HTML gallery page in `out/` — extends to:

- **Title lab**: 3–4 agents each owning a corner of title-space (bold/hooky,
  measured/explainer, concept-hooks/metaphors, venue-engineered), every title
  scored 0–100 on axes (bold, hook, insider, fear, personal), page gets
  per-axis sort buttons. Steal candidate titles from the essay's own lines.
- **Intro / conclusion labs**: one agent, four personas (ruthless editor,
  methods purist, phone-reading policy staffer, the author), paragraph-by-
  paragraph keep/rewrite/cut verdicts + 4–5 rewrites at different lengths,
  each with cuts/keeps/risks and honest word counts. Conclusions: isolate the
  kicker sentence for display.
- **Email lab**: two parallel agents (line-by-line critic + candidate drafter);
  candidates at multiple lengths with ONE explicit ask each and a mandatory
  `[WHY-YOU LINE]` personalization slot.

Lab pages: self-contained HTML, no external requests, light+dark via
`prefers-color-scheme`, CSS custom properties, single accent hue for meters
(labels carry identity, color carries magnitude only). Persona transcripts go
in `<details>`. Deliberation quality comes from personas with CONFLICTING
incentives arguing over the actual text — always give them the essay, the
guides, and prior review findings to fight about.

## House rules

- Visible text of flagged file must be byte-identical to the clean file —
  verify.py is the gate, never skip it.
- Subagents never edit files; they return JSON, the main loop applies.
- Grades are honest letters. A+ exists and so does F.
- If the venue is known, its style guide governs both the findings AND every
  rewrite the review suggests. If unknown, ask the user for venue rules once.
