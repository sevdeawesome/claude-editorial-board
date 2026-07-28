# Claude Editorial Board

Drop a Google Docs export into `input/`, ask Claude Code for a review, and get back your document with inline color-coded feedback: red for violations, yellow for weak spots, green for the strongest passages — plus per-section grades and rewrites on hover.

## How to use it

**1. Download your Google Doc as a web page** (File → Download → Web Page, .html zipped):

https://github.com/sevdeawesome/claude-editorial-board/raw/master/github_resources/download_google_doc.mp4

**2. Drag the download into the `input/` folder:**

https://github.com/sevdeawesome/claude-editorial-board/raw/master/github_resources/drop_into_input.mp4

**3. Open Claude Code in this repo and ask for a review:**

```
claude
> please review the doc in input/
```

Claude cleans the export, fans out review agents over the writing guides, and produces two files in `out/`:

- `<name>_clean.html` — a readable version of the export
- `<name>_flagged.html` — the review. Hover any flag to see what's wrong and 2–3 suggested rewrites.

## What's in the box

- `writing_guides/` — the rubrics (Pinker, Sword, Munger distillations + house style). Add your own `.md` files here and they're automatically part of every review.
- `tools/` — the deterministic pipeline (clean, slice, extract, apply, verify).
- `CLAUDE.md` — the full playbook Claude follows.

Your original export is never modified, and the flagged file's visible text is verified byte-identical to the clean version.
