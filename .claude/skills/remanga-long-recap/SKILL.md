---
name: remanga-long-recap
description: The whole remanga job from one message - the user gives a manga link (MangaDex or comix.to) and says "start to end long" (or "long recap", "full recap", "make the long video"). Means, with no further instructions - every chapter downloaded (another language where English is missing), panels marked and checked, the narration written by Claude, every chapter narrated and rendered, the long video joined, and the upload set made - three title/thumbnail pairs (A/B/C) and ONE description beside the long video.
---

# "Start to end long": the whole job from one link

The user's words (2026-10-27): "next time I don't need to say the complete things like making
thumbnail, title and description - just provide the manga link and say start to end long and you
should understand". So: do every step below without asking, check it, report once at the end.
Read remanga-ops (how remanga works) and remanga-thumbnails (the upload style) alongside this.

## Decided already - don't ask

- **Chapters:** every chapter the site lists, first to last. A decimal chapter (2.1, 2.2) is a chapter
  of its own. One not out in English comes in another language (`downloader.fallback_languages`):
  narrate it in English and tell the user which language its pages were in.
- **Settings:** the user's config.json as it is - engine and voice (Drama 3 `smooth_young_male` since
  2026-10-27), music, video size, intro. Never change them unasked.
- **Narration:** Claude writes it, following `prompts/narration.md` to the letter. The user's own
  route (upload the PDF to Gemini) is for when they do it themselves.
- **Upload set:** `projects/<P>/upload/` - `title.txt` `title_b.txt` `title_c.txt`, `thumbnail.json`
  `thumbnail_b.json` `thumbnail_c.json`, and ONE `description.txt`. Stamping writes A/ B/ C/ (title +
  thumbnail) beside every video and the one description once, as `<P>_ch<label>_description.txt`.
- **Times** for the user in their PC's 12-hour format (10:40 PM).

## The steps (from the remanga repo root; tools in this folder)

1. **Project:** `./run.sh new "<link>"` - prints the project name (P).
2. **Download:** `./run.sh download -p P` lists the chapters (a fallback chapter shows its language),
   then `-c all`. comix.to goes through the user's own Firefox helper - they must be at the PC to pass
   Cloudflare checks; say so before starting.
3. **Panel marks** - with `crop.py` (this folder), the same way for page manga and webtoons:
   first the machine's proposal, then Claude reads sheets with coordinates on them and writes a few
   lines of plain text. Page manga: `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/detect.py P 1,2.1,...`
   (MAGI v3, headless); a webtoon proposes itself (the long-strip detector). Then, per chapter:
   - `crop.py show P N OUT [first-last]` - page manga: 4 pages a sheet, the marks numbered in reading
     order on a 0-1000 grid (zoom one page with `overlay.py chapter_dir OUT 1 900 N-N`); webtoon: the
     strip in columns of 2,400 rows with a ruler in chapter rows and every proposed cut labelled.
   - write `plan.txt` and `crop.py apply P N plan.txt` - page manga: `page 6: y1,x1,y2,x2 / ...`
     (thousandths, reading order; `page 5 exact: ...` keeps overlaps; `page 13: none`); webtoon:
     `split ROW`, `join ROW`, `move ROW NEWROW`, `drop ROW`, `add TOP BOTTOM` on the proposal.
   - `crop.py check P N OUT` cuts the panels with remanga's cutter, writes contact sheets and lists
     any panel cut much smaller or larger than its mark (the snapper ate a gutter, or grew a panel
     into the blurb under it) - look at every fixed page and every listed panel; a page that keeps
     growing back gets `exact`. (Or run `./run.sh pdf -p P -c all`, which also cuts.)
   On a long manga, review the marks while reading for the narration (step 4's 2-a-sheet overlay shows
   the same boxes larger) instead of a separate 4-a-sheet pass: one look a page, fixes as you go.
   MAGI misses seen on page manga: a thin sliver between panels marked as a panel; a caption box
   straddling two panels split between them; a top box swallowing the panel under an overhanging
   figure; a tall figure over several frames given one whole-page box (Lilina-san: 6 of 80 pages).
   The webtoon detector's leftovers (2026-10-27, 90% of the user's cuts found): captions split off
   their picture, app/news screens cut along their own bands, tall pictures cut in a calm stretch -
   `join` them; a picture split by the artist with no gutter can be missed - `split` it.
4. **Narration** - the long part, done well. Read `prompts/narration.md` whole first. Read the pages
   2 a sheet with the final ids drawn: `overlay.py chapter_dir OUT 2 620`. Write a line per panel, in
   order, as you go - `001_004_02 | text`, or `001_004_01 | skip credits` (ad, blank, duplicate, title,
   merged) - and a memory JSON carried forward from the previous chapter's narration.json (series_title,
   last_chapter, characters, places, key_events, open_threads; extra keys like `terms` are fine). Then
   `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py P N rows.txt memory.json`
   - refuses unless the ids are exactly the cut panels in order, writes narration.json whole (renamed
   into place, so the render queue never reads half of it), then runs Make video's check (state must be
   ok; its style warnings catch quotes and contractions). The voice: reported speech, no quotation
   marks, no contractions, present tense, one steady narrator; names only once the story gives them;
   every bubble's content kept. Pace seen: ~55-60 words a page (Lilina ch1: 179 panels, 3,282 words
   for 51 pages; Expelled ch1-7: 1,650-1,820 words for ~31-37 pages). A flashback is still told in the
   present tense. Keep the drafts (rows.txt, memory.json, plan.txt) in a folder on /mnt/datadisk, not
   the session scratchpad: /tmp is wiped when the PC powers off (it happened mid-job, 2026-10-28) -
   and delete that folder when the job is done.
5. **Upload set** - write it BEFORE the render ends so stamping is automatic, and only on the CPU:
   the GPU belongs to the render (Drama 3 needs all 12 GB; a GPU job beside it can kill a take).
   Follow remanga-thumbnails: credits and titles from the MangaDex API, never memory; a candidates
   contact sheet; the colour cover as a `page` tile with a `box` clear of the logo; three different
   angles; title <= 92 characters before ` (01-NN)`; the thumbnail never repeats its own title's
   words; real art, no gore, bottom-right corner clear; render all three and LOOK at them. The
   description: two-paragraph hook, `▶ {chapter}`, `{timestamps}`, the manga link, `Manga:` English +
   romaji, `Story: ... · Art: ...`, hashtags, the fair-use line, `Narration voice: AI text-to-speech.`,
   `Support the official release of ...`.
6. **Render, in the background, from the first finished chapter on** - `render_queue.py` (this
   folder) renders each chapter as soon as its narration is ok, so rendering overlaps the narrating:
   `mkdir -p projects/P/logs && setsid nohup env PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/render_queue.py P --long >> projects/P/logs/render_queue.log 2>&1 < /dev/null &`
   It renders in chapter order, re-renders a chapter whose narration.json changed after it was
   narrated, runs verify.py on each, waits while MAGI or another render holds the GPU, runs once per
   project (lock), and with `--long` joins the long video + stamps the upload set when every chapter
   is done; the log ends `EXIT n`. After a power-off, start it again - takes come back from the store.
   Watch the chapter log (`projects/P/logs/`, or the queue log) for "worker ready" before calling it
   running (a load can fail). Drama 3 takes ~39 s a take, about 1.3x the narration's length plus a few
   minutes a chapter: Lilina-san (28 min, 3 chapters) ~50 min; Expelled ch1 (18:16) ~25 min. Give the
   ETA in 12-hour time.
7. **Check before saying done:** `./run.sh download -p P -c all` once more - it re-hashes every page
   against MangaDex's checksums ("All N pages verified ... nothing to download"); then
   `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/verify.py P --decode` (when nothing
   renders) - per chapter: pages counted, decoded and marked; panels cut and decoding; Make video's
   check; audio manifest bytes + SHA-256, every take a whole WAV, every take's whisper words re-aligned
   (>= 90%); video and audio streams equal and as long as the narration, every packet and frame
   readable, about -14 LUFS, no hidden `.tmp`; then the long video the same way. It caught a truncated
   page, take and mp4 on a test copy. Then by eye: one frame from each chapter; the three stamped
   thumbnails; A/B/C titles <= 100 characters with their suffix; the description beside the long video
   has the chapter timestamps.
8. **Report:** the long video's path and length, the chapters (and any not in English), the A/B/C
   titles in a table, the description's path - short.

## First run (Lilina-san, 2026-10-27) - what it took

3 chapters (1 en, 2.1 en, 2.2 Indonesian only), 80 pages, 278 panels, ~5,000 words of narration,
28:10 of video. Problems hit, all fixed in code since: a Drama 3 load that ran short of GPU memory
was not retried (now it is), and every re-placed video left a hidden `.tmp` hard link (gone). The
user stopped mid-render once to pick a new voice - voice auditions are in remanga-ops ("New Drama 3
voices by audition"); present any listening comparison as a labelled video, not an mp3.

## Second run (Expelled from an S-Rank Guild, 2026-10-28) - a long one

48 chapters, 1,576 pages, 6,315 MAGI marks (~4 a page; detection ~65 s a chapter, 52 min for all -
run it in the background and start reading chapter 1 as soon as its marks exist). MAGI on this
art: right about 9 pages in 10; the misses were a talk panel and an inset in one box, duplicate
boxes over one panel, a publisher blurb boxed as a panel, bubbles hanging over a frame edge split
between two marks (widen the panel that owns the bubble, `exact`), and slivers of sky between
panels (`skip merged` rather than re-marking). The PC was powered off mid-job: everything in /tmp
went, the render loop with it - hence drafts on /mnt/datadisk and the restartable render queue. The
user asked mid-job (2026-10-28) for every page and every take to be proved whole - verify.py - and
said tools belong in this folder (or remanga itself), new skills in remanga's .claude/skills, never
in a private folder of Claude's.
