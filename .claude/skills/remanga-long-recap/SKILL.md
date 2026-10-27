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
3. **Panel marks:** `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/detect.py P 1,2.1,...`
   (MAGI v3, headless, reading order from project.json). Then review EVERY page:
   `.venv/bin/python -I .claude/skills/remanga-long-recap/overlay.py projects/P/chapters/chapter_N OUT 4 460`
   (4 pages a sheet, numbered boxes, a 0-1000 grid); zoom a doubtful page with `1 900 N-N`.
   Fix crops.json directly: `box_1000` is **[ymin, xmin, ymax, xmax]** in thousandths; edited pages
   get `src: "manual"`, `user_decided: true`, `custom_order: true`, panel_ids renumbered 1..n;
   `"exact": true` only for a page whose marks overlap on purpose (no snapping). MAGI misses seen:
   a thin sliver between panels marked as a panel (drop it, or join it to its panel); a caption box
   straddling two panels split between them (one mark); a top box swallowing the panel under an
   overhanging figure; a tall figure over several frames given one whole-page box. Lilina-san: 6 of
   80 pages. Then `./run.sh pdf -p P -c all` cuts the panels; check every fixed page's panels with
   `panelsheet.py OUT.jpg 330 330 6 <panel pngs>` and that marks == panel files per page.
4. **Narration** - the long part, done well. Read `prompts/narration.md` whole first. Read the pages
   2 a sheet with the final ids drawn: `overlay.py chapter_dir OUT 2 620`. Write one JSON object a
   line per panel, in order, as you go ({"panel", "text"}; credits/ads/titles `{"panel", "skip": ...,
   "text": ""}`), and a memory JSON carried forward from the previous chapter (series_title,
   last_chapter, characters, places, key_events, open_threads). Then
   `PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/narration_json.py P N rows.jsonl memory.json`
   - refuses unless the ids are exactly the cut panels in order, then runs Make video's check (state
   must be ok). After each chapter, `./run.sh pdf -p P -c NEXT` so the next PDF's text page carries
   the story so far. The voice: reported speech, no quotation marks, no contractions, present tense,
   one steady narrator; names only once the story gives them; every bubble's content kept. Pace seen:
   ~60 words a page (Lilina ch1: 179 panels, 3,282 words for 51 pages).
5. **Upload set** - write it BEFORE the render ends so stamping is automatic, and only on the CPU:
   the GPU belongs to the render (Drama 3 needs all 12 GB; a GPU job beside it can kill a take).
   Follow remanga-thumbnails: credits and titles from the MangaDex API, never memory; a candidates
   contact sheet; the colour cover as a `page` tile with a `box` clear of the logo; three different
   angles; title <= 92 characters before ` (01-NN)`; the thumbnail never repeats its own title's
   words; real art, no gore, bottom-right corner clear; render all three and LOOK at them. The
   description: two-paragraph hook, `▶ {chapter}`, `{timestamps}`, the manga link, `Manga:` English +
   romaji, `Story: ... · Art: ...`, hashtags, the fair-use line, `Narration voice: AI text-to-speech.`,
   `Support the official release of ...`.
6. **Render, in the background:**
   `{ ./run.sh video -p P -c all && ./run.sh long -p P -c all && ./run.sh upload -p P; echo "EXIT $?"; } > LOG 2>&1`
   Wait for "worker ready" in LOG before calling it running (a load can fail). Drama 3 takes ~39 s a
   take, about 1.3x the narration's length plus a few minutes a chapter: Lilina-san (28 min of
   recap, 3 chapters) took ~50 min. Give the ETA in 12-hour time.
7. **Check before saying done:** LOG ends `EXIT 0`; every "N% of the narration matched" line is >= 90;
   the long mp4's video and audio durations are equal; `ebur128` reads about -14 LUFS; one frame
   from each chapter looks right; the three stamped thumbnails viewed; A/B/C titles <= 100
   characters with their suffix; the description beside the long video has the chapter timestamps;
   no hidden `.tmp` beside any video.
8. **Report:** the long video's path and length, the chapters (and any not in English), the A/B/C
   titles in a table, the description's path - short.

## First run (Lilina-san, 2026-10-27) - what it took

3 chapters (1 en, 2.1 en, 2.2 Indonesian only), 80 pages, 278 panels, ~5,000 words of narration,
28:10 of video. Problems hit, all fixed in code since: a Drama 3 load that ran short of GPU memory
was not retried (now it is), and every re-placed video left a hidden `.tmp` hard link (gone). The
user stopped mid-render once to pick a new voice - voice auditions are in remanga-ops ("New Drama 3
voices by audition"); present any listening comparison as a labelled video, not an mp3.
