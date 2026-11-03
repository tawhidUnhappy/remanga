---
name: remanga-narration-eval
description: Measure and compare remanga's narration hand-off - what each part of a chapter's PDF, prompt and reply costs in LLM tokens, and how correct the narration that comes back is, scored blind against a gold transcript. Use before and after any change to prompts/narration.md, the narration PDF, the memory or the reply format, or when asked whether a change made narration cheaper or better.
---

# Measuring the narration hand-off

A change to the hand-off is kept only when it costs fewer tokens AND narrates at least as correctly.
Both are measured here, on a throwaway copy of a real project (`projects/zz*`, deleted afterwards with
shutil). Run everything from the remanga repo root.

## Tokens - `tokens.py`

`PYTHONPATH=. .venv/bin/python .claude/skills/remanga-narration-eval/tokens.py P N OUT --tokenizer tok.json`
builds the chapter's PDF with remanga's own code (into OUT, not the project) and prices every part:

- Gemini: the prompt; the PDF's text as the LLM extracts it; every PDF page at a fixed price (Gemini 3
  bills a PDF page 560 tokens at its default media resolution whatever it shows, text pages included;
  `--page-tokens 258` for Gemini 2.x); the reply's narration and memory sections.
- Claude (when Claude narrates the chapter itself): the reading sheets (28x28-pixel patches), the story
  so far it reads, the rows and memory it writes.

Text is counted with a `tokenizers` tokenizer.json - Gemma 3's uses Gemini's own vocabulary (any public
copy of `gemma-3-*` has it) - or estimated at four characters a token without one. Measure an early and
a late chapter of a long manga: what grows with the story only shows late.

## Variants - `variants.py`

`variants.py P N OUT [--old WORKTREE]` writes the hand-off a chapter would get in each shape -
`panels` (today's), `pages` (the chapter's pages with every panel outlined and its id drawn, and the
prompt told so) and `old` (an earlier commit's own PDF step, from a `git worktree` of it). Each variant
goes to the LLM in a fresh chat, the same model for all, and its first reply is kept unedited - a fix
round would hide what the variant got wrong.

## Correctness - `magi_ocr.py`, `gold.py`, `score.py`

1. **Gold transcript.** `magi_ocr.py` (in MAGI's environment, GPU) reads every text on the pages;
   `gold.py` drafts `panel | speaker | kind | text` lines from it, per panel in reading order. Then
   check every page by eye - 2 pages a sheet with the ids drawn - and correct it: the speaker of every
   line (the name the story uses, or a description), the kind (`speech`, `thought`, `caption`, `sign`
   count; `sfx`, `blurb`, `credits` do not), misread words, lines MAGI put in the wrong panel. Gold text
   is manga text: keep it out of the repo.
2. **Blind sheet.** `score.py sheet P N GOLD OUT name=reply.txt ...` gives each reply a random letter
   (`OUT/key.json` - leave it unread), and writes `OUT/sheet.md`: per panel, the gold lines and what each
   reply tells there (a folded panel shows the text that carries it), plus `OUT/auto.json` - does it check
   out first time, style warnings, panels told and folded, words, size.
3. **Judge.** Read sheet.md and write `OUT/judgments.json` with only what is wrong, per letter: lines
   missing or only partly told, lines in the wrong mouth, panels whose lines are told out of order, and
   anything invented (see score.py's docstring). A judge that is also one of the narrators is not
   blind - say so in the report.
4. **Tally.** `score.py tally OUT`: per reply, the share of gold lines told, told whole, in the right
   mouth, inventions, order errors, first-try validity, words and reply size.

Report both tables - tokens and correctness - side by side, and say which numbers were measured and
which were estimated (published per-page prices are an estimate of what a chat app spends).
