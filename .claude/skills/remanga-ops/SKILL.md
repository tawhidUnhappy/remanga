---
name: remanga-ops
description: How the remanga codebase works and what has bitten before - load it before changing remanga. The pipeline (download -> panel marks -> panel PDF -> narration -> TTS -> video) and its three LLM hand-offs (crop, narration, upload set), the code map, the JSON contracts, design decisions with their reasons, footguns by area, and how to test without touching anyone's projects.
---

# remanga: working on the code

remanga turns manga chapters into narrated recap videos. The judgment calls - how a page is cut into
shots, what the narrator says, how the videos are packaged - are made by an LLM the user talks to
(Gemini, ChatGPT, Claude, ...): remanga builds a PDF and a prompt, the user uploads both, pastes the
LLM's one JSON reply into a file, and remanga checks it and does everything else on the machine.
Claude, working in this repo, is the coder - and can also play the LLM's part with the tools in
`.claude/skills/remanga-long-recap/`, writing the very same JSON.

Entry points: `./bootstrap.sh` (idempotent setup) · `./pipeline.sh` (the Textual menus) ·
`./run.sh <command>` (the CLI, `remanga/cli.py`). Lint: `.venv/bin/python -m ruff check remanga`.

## Ground rules

- **Fix the code, never one chapter's data.** A chapter that comes out wrong means a fix to the code
  or the prompt for every chapter - not hand-editing that chapter's files.
- **Never touch real projects in a test.** Work from a scratch directory (see Testing); `projects/`,
  `global/` and `config.json` are the user's. A test must never save `config.json`.
- **Verify by running**, not by reading: a real download, a PDF (`pdfimages`), a TTS take, a render,
  the menus in Textual's Pilot. Look at images you produce.
- **Small modules.** One job per file (the biggest are ~270 lines); split a file that holds two jobs
  and re-export from the package `__init__` so callers never change. After moving code, check for a
  decorator left on the wrong side of the cut and a helper that became two copies - both pass ruff
  and imports, only running a real chapter catches them. `ruff --fix` (F401) deletes a re-export the
  module itself does not use: point callers at the new module, or list it in `__all__`.
- **The repo is public.** No personal paths, profile names, keys or user notes in code, prompts or
  skills; per-user values live in `config.json` and `global/` (both gitignored).
- **Prompts and checks move together.** `prompts/*.md` is what the LLM gets; each has a checker in
  code. Change one, change the other: `crop.md` <-> `remanga/crop_plan/`, `narration.md` <->
  `remanga/narration/check.py`, `upload.md` <-> `remanga/upload_plan/reply.py`.
- **Keep it light.** Settings are one flat list of rows (never a wizard), global (no per-project
  overrides). Features removed on purpose stay out; bring one back only when asked.

## The pipeline

```
download   -> projects/P/chapters/chapter_N/pages/            (MangaDex checksums; comix.to via the Firefox helper)
mark       -> crops.json: the Panel Marker web UI (MAGI v3 detects, a person fixes)
  or crop-pdf -> pdf/chapter_N/crop_1.pdf (MAGI's boxes numbered, hints dashed) + prompts/crop.md to an LLM,
     its JSON pasted into chapters/chapter_N/crop_reply.txt -> marks-from-reply -> crops.json + panels/
pdf        -> cuts panels/ from crops.json, then pdf/chapter_N/panels_1.pdf ... (+ an empty narration.json)
     prompts/narration.md + the PDF to an LLM, its JSON pasted into chapters/chapter_N/narration.json
video      -> check the reply -> TTS takes (batched, whisper-aligned) -> mix with music -> render
             -> video/chapter_N/P_chN_recap.mp4; long -> video/long/ch1-5/
upload-pdf -> pdf/upload/upload_1.pdf (each chapter's biggest panels + colour pages + the story) + prompts/upload.md,
     its JSON pasted into upload/upload_reply.txt -> upload-from-reply -> upload/ templates, stamped beside every video
```

Every hand-off has the same shape: a PDF whose first page carries the facts and a reply skeleton, a
record of what the PDF showed (so the reply is read against it, and an old or misplaced reply is
caught by its id), one JSON reply, and on any error nothing changes and a fix request
(`*_fix_request.md`) is written to paste back into the same chat.

## Code map (`remanga/`)

- `workflow/` - the steps both front-ends call (`projects chapters download panels crop_pdf
  crop_reply pdf video long_video upload upload_pdf upload_reply voices cleanup ...`), re-exported
  from its `__init__`, so the CLI and the menus can never do a step differently.
- `cli.py` + `cli_commands.py`; `ui/` - Textual menus (`screens/chapters.py` the table,
  `chapter_menu.py` the menu, `chapter_work.py`/`video_work.py` the work, `settings*.py`, dialogs).
- `crop_plan/` - the crop plan both an LLM and Claude crop in: `grammar` (JSON, and the older plain
  lines), `pages`/`strip` (applying it), `found` (what MAGI saw besides panels), `breakouts` (hints
  and notes), `sheets` (drawing), `handoff` (text page + record), `reply`, `report`.
- `narration/` - the narration reply: `check` (errors, warnings, fix request), `document` (read,
  load, write; the story so far), `speakable` (what no voice can say is cleaned before TTS).
- `upload_plan/` - the upload set: `facts` (titles and credits from the source, the story),
  `candidates` (images offered), `handoff`, `reply`, `framing` (thumbnail layout), `description`.
- `cropper/` (crops.json -> panels/: snapping, seams, trim, dedupe), `pdf/` (lossless pages under a
  size cap, split into parts), `audio/` (takes, retakes, mix, master), `subtitles/` (faster-whisper
  alignment), `video/` (compositor, frame timeline, render, encoding, thumbnail), `store/`
  (content-addressed versions, chapter locks), `webui/` (Panel Marker, Writer, Reviewer),
  `plugins/` (every kind with more than one member), `config/`, `paths/` (every path; never build
  one inline elsewhere).
- Plug-ins (`remanga/plugins/`, drop-ins in top-level `plugins/`, or entry points): `tts`
  (`kokoro`, `drama3`, `edge_tts`), `tool` (isolated venvs `.tools/venv-<name>` with a `setup.py`
  each), `layout` (`pages`, `long_strip`), `source` (`mangadex`, `browser` = comix.to), `job`. A
  plug-in's `__init__.py` imports only `remanga.plugins` and `remanga.tool_envs.spec` and names its
  code as `"module:attr"` strings - the registry loads while `remanga.config` is still importing,
  and `tool_envs` must stay stdlib-only for bootstrap. Core never names a particular plug-in; it asks
  through `layouts.py`, `sources.py`, `workflow/queue.jobs()`, `tool_envs.catalog`.

## The LLM contracts

**Crop plan** (`prompts/crop.md`, `crop_plan/grammar.py`). `{"chapter", "marks", "pages": [{"page",
"panels": [...], "exact"?, "why"?}], "problems"}`; a panel is a box number, a measured
`[ymin, xmin, ymax, xmax]` in thousandths of the page, or a string joining parts with `+` (box
numbers, hint labels `F1`/`B1`, `ymin,xmin,ymax,xmax`). A webtoon: `{"edits": [{"join": ROW},
{"split": ROW}, {"move": [ROW, NEW]}, {"drop": ROW}, {"add": [TOP, BOTTOM]}]}`. The older plain lines
(`page 4: 1 / 2+3`) are still read. Read against `pdf/chapter_N/crop_marks.json` - the boxes AS
DRAWN, never crops.json: after a reply is used crops.json is renumbered, and re-reading the reply
against it would swap panels back.

**Hints** (`crop_plan/breakouts.py`). MAGI v3 returns figures, texts, tails and text-tail pairs
besides panels; the worker sends them and `found.json` keeps them per page (pixels + page size).
Each text box is widened to its balloon (`found.balloon_box`: from each side, the first dark line
after a white gap - letters touching the text box are not an outline). A figure or balloon crossing
a box becomes a labelled dashed hint with a suggestion: a balloon goes with the panel its tail points
into (else the one clearly holding most of it, else the one whose middle it is nearer), widened over
it, page exact; a figure 70%+ in one frame widens it; across frames of one tier/column whose
rectangle takes in no other frame, they join; else the figure is a shot of its own, page exact.
Notes flag thin strips (empty = sliver; words = a caption cut off), duplicate boxes and a box inside
another. Plain overlap is NOT noted: slanted borders overlap as much as one panel cut in two (20 of
36 pages of one chapter were noise). Measured on a raw-MAGI chapter whose corrected marks had 10
pages made exact: hints and notes pointed at 8.

**Narration** (`prompts/narration.md`, `narration/check.py`, `narration/document.py`, `narration/story.py`).
One JSON block, two sections: `{"narration": {"chapter", "problems", "panels": {ID: "text" | "skip REASON"}},
"memory": {"summary", "events", "characters", "places", "terms", "threads"}}`, every cut panel in reading
order. The older shape - `"panels": [{"panel", "text"} | {"panel", "skip", "text": ""}]` - still reads:
`read_reply` turns either into the list of entries every reader uses (a panel id the object held twice
comes back twice, `json_io.ReplyObject`, so the check still sees it). Skips: `credits ad blank duplicate
title` (not story) and `merged` / `merged_prev` (story folded into the next / previous narrated panel -
the LLM is also the editor deciding screen time). Errors stop the video: a missing or duplicate panel, an
unknown skip, `merged` with nothing narrated after it, `merged_prev` with nothing before, a memory whose
sections have the wrong shape. Warnings: under 3 or over 110 words, more than half the story panels folded,
quotation marks, contractions. `memory` is what the chapter CHANGED (characters/places/terms: name ->
present state, null removes; threads: the whole open list, pre-filled in the skeleton); `story_so_far`
folds every earlier chapter's memory in order (`story.add_chapter`), so the story so far is rebuilt from
the narration.json files alone and never sees a later chapter. An older whole-story memory (`key_events`,
`open_threads` ...) starts the fold afresh. The story so far and the reply skeleton are on part 1's text
page only. A fix request asks for a patch, `{"patch": {"chapter", "panels": {...}, "memory"?}}`, saved
over narration.json like a reply; `read_reply` merges it into `narration_base.json` (kept by
`keep_base` when the fix request is written or the Reviewer opens) and writes the whole result back;
the review prompt asks for the same patch.

**Upload set** (`prompts/upload.md`, `upload_plan/reply.py`). `{"upload", "sets": [{"letter",
"angle", "title", "thumbnail": {"tiles": [{"image", "subject", "framing", "tint"?, "avoid"?,
"share"?}], "labels": [{"text", "tile", "color"?, "arrow"?}], "badge"}}], "description": {"hook",
"hashtags"}, "problems"}`. Titles 20-92 characters (` (01-48)` is added; YouTube cuts at 100). The
LLM only says WHAT (image, face box, words); `framing.py` lays it out: crop around the subject at the
framing's fill, never upscaled past 2.6x, shifted/tightened to keep `avoid` boxes out; labels sized
to fit, under/beside the face (never on it), inside their tile, clear of YouTube's bottom-right
length stamp; arrows stop short of the face. The description is assembled in code
(`description.py`): the hook, `{chapter}`, `{timestamps}`, the link, titles and credits (from the
source's `get_manga_credits`, cached in project.json - never from the LLM), hashtags, a fair-use and
an AI-voice line. What a reply replaces goes to `upload/old_<time>/`.

## Design decisions - and why (don't undo them)

- **Panels, not pages.** The video plays one panel per shot; crops.json and narration.json are the
  only files nothing can rebuild (Reset keeps them).
- **LLMs read pages well and measure them badly**: frames taken from the page margin, panels back as
  thin strips. So every hand-off lets the LLM reuse what the machine drew (box numbers, hint labels,
  offered image ids) and measure only where nothing fits.
- **Reading order is MAGI's unless the story proves it wrong.** In one chapter every page a checker
  "fixed" had been right (a tall right panel comes before the stacked ones beside it) and one fix gave
  a thought to the wrong character. `webui/mark_ops.py` (recursive XY-cut) orders marks, the
  direction from project.json; a mark spanning >= 80% of the width and <= 35% of the height is its
  own tier.
- **The narration PDF carries panels only.** Adding the full pages with boxes alongside the panels,
  and asking for ten or fifteen self-review passes, both made narration worse - they were tried and
  dropped together. Pages INSTEAD of panels (ids drawn on
  them) is a quarter of the PDF pages, so a quarter of what the images cost; it is not in the pipeline
  until a scored A/B shows it narrates as well (`.claude/skills/remanga-narration-eval`, `variants.py`).
  The prompt ends with a whole chapter of another manga narrated in the target voice - rules say
  what, the example shows the sound.
- **Narration style:** reported speech, no quotation marks, no contractions, present tense, one calm
  narrator, no emoting; `?`, `!` and `...` where a sentence really is one. Rigid rules make a large
  model invent things to obey them, so the prompt opens with "the rules serve the story".
- **Voices are used raw.** No speed, pitch or effect settings; only joins (a take's edge silence
  trimmed, `TAKE_GAP_MS` 420 between takes - never 0: a line starting the instant the last ends
  sounds wrong), one gain to the Volume target with a peak guard, resampling, and the music bed.
- **Every image page of a PDF is exactly its image** (`own_size`). An LLM prices a PDF page the same
  whatever it shows (Gemini 3: 560 tokens a page at its default; older Gemini 258) and scales it to fit:
  the narration PDF used to centre each panel on a page the size of the chapter's biggest, where the
  median panel filled 17% of the page - most of what every page cost went on black, and small lettering
  shrank with it. For the crop and upload PDFs a margin would also shift the boxes an LLM reads off them.
- **Text pages are dense and few** (`textpage.TEXT_PAGE_SIZE`, 1224x1584 at 11pt, 180-character lines):
  a text page is priced like any other page, and its words reach the LLM from the text layer. The font
  is WinAnsiEncoding (cp1252): with no encoding a reader used StandardEncoding, which turned every
  apostrophe into a curly quote and every accented letter into another glyph.
- **Measure tokens before and after** (`.claude/skills/remanga-narration-eval/tokens.py`). Before these
  changes a late chapter of a long manga cost ~127k tokens in and ~18k out on Gemini, two thirds of the
  reply being the whole story written out again; the story so far is now folded from change records.
- **Nothing is overwritten or made twice** (`store/`): takes, word timings and videos are filed by
  the exact recipe that made them, SHA-256 checked before reuse, read-only once written; chapters
  link to them. Every video is a version; "Make video fresh" proves reuse by remaking.
- **4K by default is a user's choice, not a requirement** - `video.width/height` decide; the quality
  warning names the smallest size that shows every panel whole. `video.max_upscale` (3x) keeps small
  panels sharp instead of blown up.
- **Music is measured by its loud parts** (EBU "LRA high"), so every track peaks at the same level
  under the voice; `audio.bgm_below_voice_lu` 23.5 sits where recap channels do. A long video gets
  ONE music bed across its chapters (a bed per chapter restarted the song at every chapter).

## Footguns, by area

**PDFs.** Every PDF stays under `pdf.max_mb`, parts split in order; JPEG pages go in as their own
bytes (DCTDecode); other pages the smaller of PNG-IDAT and TIFF-predictor streams; only a page over
the cap alone goes near-lossless. Verify with `pdfimages`, not `pdftoppm` (72 dpi rendering isn't
1:1). The text page is Latin-1 Helvetica: a backtick prints as a curly quote (no backticks on text
pages), anything else outside Latin-1 becomes `?`; `textwrap` splits `7: 1234-5678` across lines, so
entries carry no inner space (`7:1234-5678`).

**Audio and alignment.**
- A panel synthesized alone resets the voice's tone, so panels are read in batched takes and
  faster-whisper finds each panel inside its take. Whisper is trusted for WHEN, never WHAT; it
  refuses below 90% match (`align.MIN_MATCH_RATIO`) because a misalignment is silent. A name whisper
  spells its own way counts as heard when 80%+ of its letters agree.
- Silence cannot find panel boundaries (a model pauses inside panels as long as between them).
- A long take can collapse (a model reads a few panels then emits silence to the token budget):
  caught before transcription by length vs the ENGINE's own pace (`chars_per_second` - each engine
  must measure its own, or every take looks like a runaway), then split at a page and retried.
- Seeded engines get retakes: a take that hums between words (`audio/hums.py`) or drops a sentence
  is read again under other seeds and the better reading kept - never cut (whisper misses names).
- Trim with a sustained speech level relative to the clip's own loudness, not a fixed -50 dBFS; when
  a join sounds wrong, measure at an audible -40 dBFS, not at the trim's own threshold. Never trim
  the clip on disk - offsets live in the manifest. Resample through ffmpeg, never pydub.
- Normalize by measuring and applying one gain (`ebur128` I + true peak), never single-pass dynamic
  loudnorm (it pumps the music between sentences).
- Never hand a cloning model text you have not proved is in its reference audio (whisper invents a
  tail for a clip cut mid-sentence, and the model then speaks it). A cloned voice drifts inside a
  long take - re-anchor with shorter takes.

**Engines.** Kokoro: the voice is a name, its `lang_code` follows the voice; fixed voices, seconds a
chapter. Edge: online, not a licensed API (said in the README). Drama 3 (speech.cpp, Vulkan, Q4 GGUF):
reads from a voice file one sentence per request (whole-chapter requests clicked at chunk joins on
the codec's 2048-sample grid and dropped sentences); each sentence's tail silence is cut to 350 ms;
on a 12 GB card the worker holds `gpu_headroom_gb` while speech.cpp loads (it has no knob and runs
out of memory otherwise), and retries a load that fails for memory - including "cannot reserve the
memory of the codec's decoding". A voice file is keyed by name and seed, not by its cue text.

**The store.** Every writer writes tmp + rename (writing INTO a placed file hits a read-only store
file). `link_or_copy` returns early when the destination already is the source (rename between two
links of one file is a POSIX no-op and leaked hidden `.tmp` links). A version's label comes from the
narration's own voice record, not the settings now. GPU TTS is not byte-deterministic:
`compare_fresh` judges "same reading" by length, words and word timings.

**Cropper and marks.** `box_1000` is `[ymin, xmin, ymax, xmax]`. Panels are cut in list order.
A page `"exact": true` turns off snapping, trimming and padding (overlapping marks would be pulled
apart) - the Panel Marker round-trips it (`MarkerState.exact`). `page_index` names the panels,
`page_filename` finds the file (a scan's out-of-order page is fixed by listing pages in story
order). Gutter snapping must stay inside the panel it snaps: a page-scaled search radius once moved
both edges of a thin caption banner into the gutter above it - **a blank or sliver crop under a
correct-looking mark is the snapper, not the marker**. When reading boxes off a gridded image, read
the grid labels, never the image's pixel rows.

**Long strips (webtoons).** No MAGI (it is trained on printed pages). The detector votes: verified
gutters (a colour counts only once it separates the strip, and a repeat only with art between - a
fade "verified" itself as six gutters), border signals that never cut on their own, glue for small
pieces, blank pieces dropped, a too-tall picture split only at a calm stretch. A gutter is trimmed to
its clean rows (a balloon hanging across it was cut in half). Strip marks are full width, overlap
allowed; `pages.py` never splits overlapping marks across pages. Score detector changes with
`strip_score.py` (this folder) against chapters people marked by hand; a fair score counts a cut
anywhere in the same gutter or flat run as the same cut.

**Sources.** MangaDex: honour `X-RateLimit-Retry-After`/`Retry-After` on 429 (guessed waits gave up
mid-verify); licensed chapters list with 0 pages; decimal chapters are chapters of their own (`1-5`
takes 4.5, not 5.1). A project may have several sources (`sources.py`): clients never write the
top-level identity; each chapter downloads from the source that downloaded it, else the first with
pages; a configured-language row from any source beats a fallback-language row. comix.to: Cloudflare
plus a signed API, so the user's own Firefox does the work through the remanga helper extension -
never Playwright/Selenium/BiDi (`navigator.webdriver` sits on "Just a moment..." forever), never
copying the user's cookies. The helper is HMAC-paired per copy, answers only localhost, opens list
pages by address (a scripted pager click trips the site's firewall), and saves a chapter only when
every count of its pages agrees. Mock tests use their own port (47699) - the real helper polls 47615
- and must stub `session.explain_loading`, or a test opens about:debugging in the user's Firefox.
UI tests must never open a comix.to project's chapter list for the same reason.

**Upload set.** A set with no CH badge: `place_badge` needs a corner no face box or label touches, and
the crop scores ties went by float noise (0.2 + 0.1 > 0.1 + 0.2), so a tightened crop won and lifted
the face into the corner. Scores are rounded (ties go to the least-tightened crop) and
`upload-from-reply` warns when a set gets no badge. Read reply boxes off `thumb.py boxes` (the
thumbnails skill), never off the PDF's own rendering.

**UI (Textual).** Nothing is highlighted until an arrow key or a click; a single click highlights,
a double click (or Enter) chooses - a test that presses Enter first "hangs", by design. A subclass
`_on_click` must `event.prevent_default()`; `OptionList.__init__` highlights option 0 itself; `log`
is a Widget property; a box with `height: auto` clips and cannot scroll (dialogs cap their scrolling
part to the window). Work runs in a TaskScreen thread; Ctrl+C raises KeyboardInterrupt into it, then
SIGTERM, then SIGKILL after 3 s (ffmpeg ignores SIGTERM mid-encode), and any blocking wait waits in
short steps (a thread parked in one `Event.wait()` cannot be interrupted). Check small windows:
`virtual_size.height > region.height and not allow_vertical_scroll` means unreachable content.
Menu wording says what is KEPT and what is REDONE, and names the slow part.

**Web UIs.** The Panel Marker, Strip Marker, Writer and Reviewer share `webui/static_shared/`
(theme, screens.js). Verify gestures in headless Chromium. Shift+S cannot be a second binding
(shortcuts.js lowercases keys).

## Testing

```bash
S=$(mktemp -d); cd "$S"
ln -s /path/to/remanga/checkpoints checkpoints; ln -s /path/to/remanga/global global
cp /path/to/remanga/config.json /path/to/remanga/config.example.json .
mkdir -p projects/zzTest/chapters/chapter_1 && cp -r <a project>/chapters/chapter_1/pages projects/zzTest/chapters/chapter_1/
cp <a project>/project.json projects/zzTest/
PYTHONPATH=/path/to/remanga /path/to/remanga/.venv/bin/python -m remanga.cli crop-pdf -p zzTest -c 1
```

- `projects/`, `config.json` and `global/` resolve against the working directory; model paths too -
  symlink `checkpoints/` or the weights download again into the scratch directory.
- Never `bin/uv run --project <repo>` for tests (it rewrites uv.lock and re-syncs `.venv`).
- Stub `RemangaConfig.save` in UI tests and compare `config.json`'s md5 before and after.
- Pilot: `RemangaApp(RemangaConfig.load()).run_test(size=...)`, push `ChaptersScreen(config,
  project)` with `fetch` stubbed for no network, call `screen.actions([{"chapter": "1"}])`, press
  down index+1 times and Enter on a Choice.
- A stop test must stop the REAL render (a tiny libx264 encode stops fine; NVENC on a real chapter
  did not).

## Maintenance rule

When a session hits a non-obvious bug, a wrong assumption or a footgun and fixes it, add a terse
entry here in the right section - symptom -> cause -> rule - or tighten one, and delete what a code
change made stale. General lessons only: no dates, no user names, no project names, no personal
preferences (those belong in the user's own notes, not in this public repo).
