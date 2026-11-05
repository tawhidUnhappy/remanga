---
name: remanga-long-recap
description: The whole remanga job from one manga link, done end to end by Claude - every chapter downloaded (another language where English is missing), panels marked and checked, the narration written, every chapter narrated and rendered, the long video joined, and the upload set made (three title/thumbnail pairs A/B/C and one description). Use when asked for the complete recap of a manga - "start to end", "long recap", "full recap", "make the long video of this".
---

# The whole job from one link

When asked for the complete recap of a manga, do every step below without asking what to make,
check it, and report once at the end. Read remanga-ops (how remanga works) and remanga-thumbnails
(the upload style) alongside this.

In this job Claude plays the LLM's part in each of remanga's three hand-offs, writing exactly the
JSON an LLM like Gemini would (`prompts/crop.md`, `prompts/narration.md`, `prompts/upload.md`). The
same checks apply, and any step can go back to the user's own LLM: the PDFs and prompts are there.

## Decided already - don't ask

- **Chapters:** every chapter the site lists, first to last. A decimal chapter (2.1, 2.2) is a chapter
  of its own. One not out in the configured language comes in another (`downloader.fallback_languages`):
  narrate it in English and say which language its pages were in.
- **Settings:** the user's `config.json` as it is - engine, voice, music, video size, intro. Never
  change them unasked.
- **Panel marks:** MAGI's proposal, reviewed by Claude with `crop.py` (step 3).
- **Narration:** written by Claude following `prompts/narration.md` to the letter.
- **Upload set:** `projects/<P>/upload/` - three title/thumbnail pairs (A/B/C, YouTube Test &
  Compare's maximum) and ONE description, written through the upload round trip (step 5). Stamping
  writes `A/ B/ C/` (title + thumbnail) beside every video and the description once beside it.
- **Times** for the user in their own clock's format.

## The steps (from the remanga repo root; tools in this folder)

0. **Notes first, on a long manga** (more than a few chapters): a notes file outside the repo with
   what is done and a "Next" section a fresh session can follow; keep it current after every
   chapter. Keep drafts (plans, replies) on a real disk too - `/tmp` is wiped at a power-off.
1. **Project:** `./run.sh new "<link>"` - prints the project name (P).
2. **Download:** `./run.sh download -p P` lists the chapters (a fallback chapter shows its language),
   then `-c all`. A comix.to manga goes through the user's own Firefox helper - they must be at the
   PC to pass Cloudflare checks; say so before starting.
3. **Panel marks.** Page manga: `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/detect.py P 1,2.1,...`
   (MAGI v3, headless; it also saves what it sees for the hints). A webtoon proposes itself (the
   long-strip detector). Then, per chapter:
   - `crop.py show P N OUT [first-last]` - page manga: 4 pages a sheet, the marks numbered in reading
     order on a 0-1000 grid, the hints dashed (F1 a figure, B1 a balloon crossing a box), and the
     hints and notes printed with their suggestions; webtoon: the strip in columns with a ruler in
     chapter rows and every cut labelled. Zoom one page with `overlay.py chapter_dir OUT 1 900 N-N`.
   - write `plan.json` - the crop reply's JSON, only the pages to change - and
     `crop.py apply P N plan.json`.
   - `crop.py check P N OUT` cuts the panels and lists any cut much smaller or larger than its mark
     (the gutter snapper); a page that keeps growing back gets `"exact": true`.
   On a long manga, review the marks while reading for the narration (step 4's 2-a-sheet overlay)
   instead of a separate pass. MAGI's usual misses are listed in `prompts/crop.md`; reorder only when
   the dialogue proves the order wrong - MAGI's right-to-left order is usually right.
4. **Narration** - the long part, done well. Read `prompts/narration.md` whole once per session (not
   once per chapter). Before each chapter, print the story so far it continues - every earlier
   chapter's memory folded, exactly what its PDF would give an LLM - with
   `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py P N --story`,
   instead of opening an earlier narration.json. Read the pages 2 a sheet with the final ids drawn:
   `overlay.py chapter_dir OUT 2 620`. Write the reply JSON (or, as you go, `rows.txt` with
   `001_004_02 | text` / `001_004_01 | skip merged` lines plus a `memory.json` holding only what this
   chapter changed - `summary`, `events`, the `characters`/`places`/`terms` it brought in or changed,
   and the open `threads` - never the whole story again), then
   `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py P N reply.json`
   (or `... P N rows.txt memory.json`) - it refuses unless the ids are exactly the cut panels in
   order and the memory has the right shape, writes narration.json whole (renamed into place, so the
   render queue never reads half of it), and runs Make video's check (state must be ok). Be the editor the prompt asks for: fold a
   panel with nothing of its own to show into the neighbour that matches its words (`merged` /
   `merged_prev`), and give the strong panels the context. Pace seen: about 55-60 words a page;
   1,650-2,150 words for a 30-37 page chapter. A flashback is still told in the present tense.
5. **Upload set** - before the render ends, so stamping is automatic, and on the CPU only (the GPU
   belongs to the render; a GPU job beside a big TTS model can kill a take):
   `./run.sh upload-pdf -p P -c <the first few chapters>`, extract its images
   (`pdfimages -j pdf/upload/upload_1.pdf OUT/i`) and its text (`pdftotext`), look at the strongest
   candidates (`.claude/skills/remanga-thumbnails/thumb.py offered P`, then `thumb.py boxes P ID ...` to
   read the boxes on the reply's grid), write `projects/P/upload/upload_reply.txt` following
   `prompts/upload.md` - three different angles, the faces boxed, anything to keep out boxed as
   `avoid` - then
   `./run.sh upload-from-reply -p P` and LOOK at `upload/preview_a.jpg` ... `_c`. Fix a weak one in
   the reply (a tighter framing, another image, an avoid box) and use it again.
6. **Render, in the background, from the first finished chapter on** - `render_queue.py` renders each
   chapter as soon as its narration is ok, so rendering overlaps the narrating:
   `mkdir -p projects/P/logs && setsid nohup env PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/render_queue.py P --long >> projects/P/logs/render_queue.log 2>&1 < /dev/null &`
   It renders in chapter order, re-renders a chapter whose narration.json changed after it was
   narrated, runs verify.py on each, waits while MAGI or another render holds the GPU, runs once per
   project (lock), and with `--long` joins the long video and stamps the upload set when every
   chapter is done; the log ends `EXIT n`. After a power-off, start it again - takes come back from
   the store. With a range (`render_queue.py P 1-14 --long`) it joins exactly those - for "the long
   video up to the chapter narrated last". Watch for "worker ready" in the chapter log before calling
   it running (a load can fail).
7. **Check before saying done:** `./run.sh download -p P -c all` once more - it re-hashes every page
   against MangaDex's checksums; then `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/verify.py P --decode`
   (when nothing renders): pages counted, decoded and marked; panels cut; Make video's check; every
   take whole and re-aligned; video and audio streams equal and as long as the narration, every
   frame readable, about the Volume target, no hidden `.tmp`; then the long video the same way. Then
   by eye: one frame from each chapter, the three stamped thumbnails, A/B/C titles at 100 characters
   or under with their suffix, the description beside the long video with its chapter timestamps.
8. **Report:** the long video's path and length, the chapters (and any not in English), the A/B/C
   titles in a table, the description's path - short.

## What long runs have taught

- MAGI takes about a minute a chapter: run detection for every chapter in the background and start
  reading chapter 1 as soon as its marks exist.
- Claude narrates a chapter of 120-160 panels in a few minutes; a large TTS model renders it in
  15-20 (Drama 3 on a 12 GB card runs ~1.3x the narration's length). The render is the bottleneck -
  start the queue early. A 14-chapter join takes minutes; verify.py about a minute.
- A power-off takes `/tmp` and the background render with it: drafts live on disk, and the queue is
  restartable.
- A chapter missing from the long video: read the queue log first - it names the take that failed
  (a whisper spelling once sank a take; alignment now forgives names spelled alike).
- On MAGI's page manga: about nine pages in ten are right. The misses are the ones `prompts/crop.md`
  lists - slivers, a caption split between two boxes, a talk panel and an inset in one box, a tall
  figure over several frames, a publisher blurb boxed.
