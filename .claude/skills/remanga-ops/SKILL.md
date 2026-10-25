---
name: remanga-ops
description: Fast-start reference + known-bugs log for the remanga repo (manga pages -> panels marked with MAGI in a web UI -> panel PDF for an LLM -> Kokoro narration -> recap video). Load before any remanga work. Keep it updated (see maintenance rule at bottom).
---

# remanga fast-start

Repo: github.com/tawhidUnhappy/remanga · push straight to `main`, no PR flow.
Entry points: `./bootstrap.sh` (idempotent setup) · `./pipeline.sh` (menus) · `./run.sh <cmd>`.

**User rules**
- After code/repo changes, commit and push to `origin/main` without being asked (hold off only on
  something clearly unfinished or broken).
- Your job is the CODE, not the user's manga. A chapter that comes out wrong means fixing the code or
  the prompt for every chapter - never hand-patching that chapter's data. Test on throwaway
  `projects/zz*` copies (or scratch dirs) and delete them after. **Never modify the user's
  `projects/`.**
- Verify by running, not by asserting (real download / PDF / Kokoro TTS / render, pdfimages for PDFs).
- The user wants this LIGHT, and says what comes back. The 2026-09-17 cut removed everything; on
  2026-09-18 they asked for the **panel concept, the Panel Marker web UI and MAGI** back, and for
  direct page-based video to go. Still out, and not to be reintroduced unasked: Gemini crop grid,
  sheets/zips/packaging, the reviewer and writer web UIs, DeepSeek-OCR, pipeline editor, full-recap,
  remix, status/verify/wipe, extensions, Chatterbox cloning. Branches: `backup/main-2026-09-17`
  (everything), `backup/pages-kokoro-2026-09-18` (the page-based light version),
  `backup/chatterbox-2026-09-18`.

## Keep it in small modules (user request, 2026-09-18)

Split a file when it holds two jobs, and re-export from the package `__init__` so callers never
change (`workflow.make_pdf`, `video.compose.FrameCompositor` both still resolve). Two things that
bit during the split and are worth checking after any slice-and-move: a decorator left behind on the
wrong side of the cut (`@dataclass` on `_Page`), and a helper that silently became two copies. Both
passed ruff and imports - only running a real chapter caught them.

**Refactor 2026-09-30 (user request: "no too big files, all module based and small so an LLM
can easily update them").** Every file that held two jobs was split, re-exported so callers never
changed: `audio/batched.py` -> `takes` (making/halving takes) + `retakes` (hums, whisper) +
`batched` (orchestration); `ui/dialogs/` package (fit, choice, ask, result); `narration/` package
(files, check, document); `pdf/writer.py` -> `streams` + `textpage` + `writer`;
`workflow/deletables.py`; `downloader/feed.py` (now `plugins/mangadex/feed.py`; chapter feed mixin) + `chapter_pages.py` (the steps
of download_chapter, which was one 165-line method); `video/picture_cache.py`; `ui/task_io.py`;
`tool_envs/status.py`; `cli_commands.py`; `config/tts_kokoro.py` + `tts_qwen.py`;
`cropper/cut.py`; `audio/synth/qwen_reference.py` (now `plugins/qwen_tts/reference.py`); the Panel Marker's `history.js`, `split.js`,
`shortcuts-menu.js`; the Writer/Reviewer CSS out of their index.html. **`hardware.py` stays one
file on purpose**: bootstrap.sh runs it as a bare script before any env exists, so it cannot
import siblings. Verified after: 198 modules import, ruff clean, and a real run of each path -
MangaDex download + re-verify, MAGI detect, PDF (pdfimages 79+35, text page), Kokoro 114 panels ->
4K render, Qwen clone in batched takes (whisper 100%), webtoon strip -> exact crops, Panel Marker
S/Ctrl+Z/Shortcuts in Chromium, Settings dialogs in Pilot. Also fixed on the way: a chapter
MangaDex only links to (0 pages) now says so instead of "All 0 pages verified".
**How it was done, for next time:** scratchpad `movedefs.py` (top-level blocks, verbatim, via ast)
and `movemethods.py` (class members -> a mixin), then `ruff check --fix --select F401,I001`.
**ruff F401 deletes a re-export line** the source module does not itself use (`from .x import Y`
kept only for callers) - point the callers at the new module instead, or list it in `__all__`.

**Efficiency pass 2026-10-01 (measured on real chapters, outputs compared):** panel cutting runs pages
in a thread pool (PNG compression is outside the GIL): 16 -> 2.2 s for 114 panels, every panel
byte-identical. Mix 24.4 -> 5.4 s (see normalizing). Webtoon: stitch decodes in parallel 2.3 -> 0.6 s,
signals sample ~256 columns and compare colours in 32 slices (detect 7.3 -> 4.1 s, same 54 panels,
F1 0.86 unchanged), strip/ pages saved in parallel at PNG level 1 (a private intermediate; pixels
identical) so Finish went 14.7 -> 2.7 s. **Shared web screens:** `static_shared/js/screens.js` +
`css/screens.css` - showLoading (spinner, what, seconds) and showDone (counts, Next, terminal carried
on, close countdown that then says the tab can be closed: window.close only works on script-opened
tabs) - used by all four UIs; the Strip Marker loads `/api/layout` first so the strip is laid out
before detection. **De-duplicated:** `webui/shared_routes.py` (favicon + /shared, was in 4 apps),
`workflow/cleanup.guard`/`delete_paths` (was 5 copies), `static_shared/css/panel-list.css` (31 rules
identical in Writer + Reviewer CSS). pylint duplicate-code at 4 lines finds nothing left.

**Plug-ins 2026-10-01 (user request: "make remanga most of the codes as plug-ins").** Core is
`remanga/plugins/` `_registry.py` (register/items/get/find/resolve/call, one registry per kind),
`_loader.py` (built-in folders = every non-"_" package in remanga/plugins; drop-ins = top-level
`plugins/*.py|pkg`; entry points group `remanga.plugins`; a later one with the same name replaces;
a failing drop-in is reported once on stderr and skipped), `_kinds.py` (`TTSEngine`, `Layout`,
`Source`, `Job`; `tool` = `ToolSpec`). Kinds and built-ins: tts `kokoro` `qwen_tts`; tool (each
engine's + `magi` + `faster_whisper`); layout `long_strip` (order 50) `pages` (1000, the fallback:
matches anything); source `mangadex`; job `jobs`. Core asks through `remanga/layouts.py`
(`layout_for`, `pages_dir` - replaces is_long_strip/marking_pages_dir in workflow, cropper, Panel
Marker; detection = `layout.detect`), `remanga/sources.py` (`source_for`, `project_client`;
project.json now records `"source"`, a missing one = default), `workflow/queue.jobs()`,
`tool_envs.catalog.tools()/tool_names()/tool_spec()` (were TOOLS/TOOL_NAMES constants).
**Tools set themselves up (user request 2026-10-01: "they should include scripts for those to setup
instead of remanga handling it"):** each tool plug-in has `setup.py` = `TOOL` (ToolSpec with its
install `steps`, `install="...setup:install"`, `weights="...setup:weights"`), `install(torch_backend,
force)` (built-ins call `tool_envs.build_env`, the uv helper), `weights(config)`, and a `__main__`
via `tool_envs.cli.run_setup` (`python -m remanga.plugins.<pkg>.setup [--force] [--no-weights]`).
`__init__` registers `setup.TOOL`. `tool_envs.install_tool` only dispatches to `spec.install`
(no hook = build_env); ensure_tool/provision decide WHEN. `./run.sh setup [--tool X]` = provision +
each tool's `weights`. Fingerprint is still the steps, so existing envs stayed "ready".
**The one rule:** a plug-in's `__init__.py` imports only `remanga.plugins` and
`remanga.tool_envs.spec` (or its own stdlib-only setup.py), naming its code as `"module:attr"` strings - config/tts.py loads the
registry while `remanga.config` is still importing, and tool_envs must stay stdlib-only for
bootstrap. `./run.sh plugins` lists all. Verified: config.json round-trips identically; both
layouts cut byte-identical panels; MAGI and strip detection through the hook; Strip Marker routes;
MangaDex new project + list + download (35 pages verified), the long-strip tag -> `layout`;
queued PDF job; Settings engine switch in Pilot; Kokoro + Qwen clone narration. **Scratch runs:**
model dirs are relative to cwd - symlink `checkpoints/` (and `global/`) into a scratch cwd, or
the weights download again (5.6 GB filled /tmp, a RAM disk here).

## The workflow (the whole product)

```
download  -> projects/P/chapters/chapter_N/pages/          (MangaDex, checksum-verified)
mark      -> Panel Marker web UI (Flask, browser): Detect = MAGI v3, hand fixes -> crops.json
[optional: write = Narration Writer (type it yourself), review = Narration Reviewer (flag what is wrong
 -> narration_review.json + prompts/narration_review.md)]
pdf       -> cuts panels/ from crops.json, then projects/P/pdf/chapter_N/panels_1.pdf, ...
             (+ empty narration.json to paste into)
[user uploads prompts/narration.md + the PDF to an LLM, pastes the one JSON reply into narration.json]
video     -> check reply -> Kokoro clip per panel -> mix with BGM -> render panels
             -> projects/P/video/chapter_N/P_chN_recap.mp4
```

Code map (`remanga/`), one module per job after the 2026-09-18 regroup - no file over ~270 lines:
`workflow/` (the steps both front-ends call: `projects` `chapters` `download` `panels` `pdf` `video`
`cleanup`, all re-exported from its `__init__`), `cli.py`, `ui/` (Textual menus: `app.py`
styles/quit, `screens/` = `projects` `chapters` (the table) `chapter_menu` (the menu) `chapter_work` +
`video_work` (what it does, mixins) `settings` (+ `settings_sound`/`settings_video` rows) `settings` `common`, `dialogs.py`, `tasks.py`, `widgets.py`, `voice_settings.py`),
`activity.py` (progress bars: CLI Rich bar or UI task view),
`narration.py` (reply check, fix request, memory), `chapters.py` (ranges, sort, page naming),
`webui/` (the Panel Marker: Flask routes, MarkerSession/MarkerState,
static/), `cropper/` (crops.json -> panels/: crop_page, panel_boxes, gutter/, seams, trim, dedupe),
`pdf/` (`encode` one panel -> a PDF page, `pack` panels -> parts under the cap, `builder` wires
them, `writer` the PDF itself, `manifest_info` the text page), `plugins/` (see Plug-ins above:
engines, MAGI, faster-whisper, layouts, MangaDex, jobs - each a folder), `layouts.py`, `sources.py`,
`audio/` (tts, mix, master, clips, manifest, voice_chain, synth/base = the worker lifecycle),
`video/` (`canvas` one panel on one frame, `quality` is this size enough, `frames` the frame cache,
`compose` re-exports those three, `frame_timeline`, `render`, `encoding`), `config/`, `paths/`, `tool_envs/` +
`workers/` + `models/` (isolated venvs + weights; each tool's spec is in its plug-in).

## Narration reply (prompts/narration.md is the contract)

One JSON block, two sections (user request - NOT two blocks):
`{"narration": {"chapter", "problems", "panels": [{"panel", "skip", "text"}]}, "memory": {...}}`
one entry per PANEL id (`2.2_004_02` = chapter_page_panel), in reading order.
(`narration.read_reply` also accepts `panels`+`memory` side by side, and two separate blocks.)
- One entry per page ID, in order. Story page: `panels` = one note per panel in reading order (forces
  per-panel coverage, never read aloud) + `text`. Non-story: `skip` in credits/ad/blank/duplicate.
- **Pages in the PDF and self-review passes both made the narration WORSE (2026-09-22, user
  verdict).** Two things were tried on the user's say-so and taken straight back out on it: the PDF
  carrying every page with its panel boxes drawn on it beside the cut panels, and the prompt asking
  for ten (then fifteen) passes over the draft before replying. Both are on
  `backup/pdf-pages-and-passes-2026-09-22` if they are ever wanted again. **Do not re-suggest either
  unasked**, and when the next idea for "more context" or "more checking" comes up, remember these
  two: the quality bar here is what the chapter sounds like, and it is the user's ear that decides,
  not how thorough the pipeline looks.
- **The prompt ends with a whole chapter of another manga narrated as the user wants it** (2026-09-22,
  their file /mnt/datadisk/whatIwant/whatIwant.txt, ~2900 words, copied in verbatim and wrapped). It is
  the voice target - the rules above it say what to do, it shows what they sound like - with a short
  take-this/not-that framing: take the voice, the reported speech, the level of explanation and the
  connectives; never its names, plot or its one-unbroken-account shape. It passes
  `narration._style_warnings` as it stands. **If the user changes that file, re-sync the section** -
  the prompt holds a copy, not a link, because the prompt is what gets uploaded.
- `narration.load_narration` errors -> nothing synthesized, `pdf/chapter_N/fix_request.md` written.
  Warnings only: <12 words per listed panel; quotes/contractions (the user's narration style:
  reported speech, complete content, no quote marks, no contractions, one steady narrator).
  `?`/`!`/`...` ALLOWED since 2026-10-24 (user): narrator sentences may end in them; still no quoted
  dialogue. `narration/speakable.py` cleans text for every engine in `BaseWorkerSynthesizer.synthesize`
  (and `align._script_tokens` aligns against the same cleaned text): NFKC, emoji/symbols/CJK dropped,
  runs of marks collapsed, accents folded, $5 -> 5 dollars, 3/4 -> 3 out of 4. Measured why: Ming read
  "Chloé ... café" as "Khlo ... CAF" and "$5 and 30 percent" as "$5.30"; Kokoro read 3/4 "three-four".
  Delivery (pyin over . ? ! on 3 sentences): Ming's end pitch rises ~+9.5 st on ?, ~+7 on !, flat on
  period; Kokoro ignores ? (no rise) and ! only lifts median F0 ~6%. 0 of 1,663 existing panels change.
- The story so far lives only in narration.json: `make_pdf` reads the memory section of the nearest EARLIER chapter's
  narration.json (`narration.story_so_far`) and prints it on the text page, warning when earlier
  chapters have no narration yet. The user uploads only the prompt + PDF.

## Things that bit before - don't reintroduce

- **PDF size:** every PDF measured and kept <= `pdf.max_mb`; parts split in order. JPEG pages are
  embedded as their own bytes (DCTDecode) - "lossless" re-encoding of JPEG pages was ~8x bigger.
  Other pages: smaller of PNG-IDAT (Predictor 15; Pillow's PNG IDAT *is* the PDF stream) and TIFF
  Predictor 2, gray as 1 channel. Only a page over the cap alone goes near-lossless (palette/JPEG at
  PSNR floors 45/42/39/36). The text page is Latin-1 Helvetica and wraps at 95 chars.
- **Verify PDFs with `pdfimages -png/-all`, not `pdftoppm`**: 72dpi rendering isn't 1:1 (reads ~21 dB
  on lossless pages).
- **Caching chain:** audio_timing.json is rewritten only when content changes; mix fingerprints its
  mtime + BGM file stat + settings; render compares master_audio mtime and a picture fingerprint. A
  gratuitous rewrite anywhere upstream re-mixes and re-renders everything.
- **LCD background grid (2026-10-18):** `video.background_grid_px` (cell size at 1080p of the short side,
  0 = off, default 10) + `background_grid_strength` 0.5: a multiply layer built once per compositor
  (`FrameCompositor._lcd_grid`), over the blur only, before the panel is pasted. +40 ms per 4K frame. Frames
  re-composite on change via frames_settings.json (model_dump). If viewers see shimmer at 720p, go chunky.
- **Presets and voice effects REMOVED from main (2026-10-25, user: "remove all the presets and effects
  and just keep the original vocal and volume and background music volume, minimalistic settings").**
  Everything is on branch `backup/presets-effects-2026-10-25` (presets/*.json, config/presets.py,
  audio/voice_chain.py + microphone/breath/phone/blend/creak.py, gaps.py's pause cutting, the per-panel
  narration path, Settings rows for take length, pauses, edge fade, compressor... limiter). Main now:
  `audio.volume_lufs` (alias of the old `loudness_target_lufs`; one measured gain over the mix,
  alimiter only when that gain would pass -1 dBTP - audio/master.py:write_master - and then the loudness
  it took re-measured and given back, up to GUARD_PASSES 3: Drama 3's peaky voice landed -15.0 for -14
  with one pass, -14.2 now), `bgm_*` unchanged;
  fixed in code: always batched takes (`plan_batches(panels, inf, ...)` = the engine's max_take_seconds),
  TAKE_GAP_MS 420 between takes (never 0: the user hates a line starting the instant the last ends, 2026-10-04), EDGE_FADE_MS 35 at take edges, no gap tightening
  (`audio/take_audio.py` = load + identity only). Old config.json keys are ignored by pydantic.
  Verified on a copy of HimeSama ch3.1: Kokoro 27 panels -> 1 take, whisper 99%; mix -14 -> -14.2 LUFS
  (peak guard on), -18 -> -18.0 (both before TAKE_GAP_MS; a one-take chapter has no join to change). Lessons kept from the effects era, if any come back: measure an EQ with
  tones before trusting it (an octave-width shelf CUT 200 Hz); never synthesize a pitched breath thump (it
  is a kick drum); compare zoomed spectrograms, not band averages; the vocal-fry "rhh" is pitched, a
  breath detector misses it.
- **Menus fit any window (2026-10-25, user: "make the terminal ui run on any size ... don't overflow or hide
  content").** Measured first by rendering every screen as text at 30x8 .. 200x50 with Pilot
  (`app.screen._compositor.render_strips()`, joined segment texts - no SVG converter on this box): fixed
  column widths ran Title/Manga/What-it-does off the right edge, Footer dropped keys past it, TopBar ran
  the path into the info ("...GolemMaster19 chapters"), RichLog CROPPED words mid-line (it wraps once at
  write-time width; a scrollbar appearing or a resize then cuts text). Now in `ui/widgets.py`:
  `SafeTable` keeps every row's cells and re-lays columns on resize (`add_column(..., drop=N)`: fixed
  widths shrink to their content, text columns share the rest, spare room grows cut columns, `drop`
  columns leave a narrow window highest first, cells cut with an ellipsis; `update_cell_at` takes FULL
  column indexes); `RowDetail` under each table shows the highlighted row's cut/left-out text (<= 1/4 of
  the window, scrolls); `KeyBar` replaces Footer everywhere (wraps whole items, click = `app.simulate_key`,
  tells a dialog's `_fit` when its line count changes); `TopBar` collapses middle path parts to "…" then
  puts the info on line 2 (`.android TopBar` must be `height: auto`); `WrapLog` replaces RichLog (re-wraps
  on resize, follows the end). Choice/Checklist options are a `Columns` renderable: hint beside the label,
  or under it when the width left is < 24. fit.py: an OptionList not laid out yet reports virtual height
  0 - count 2 rows an option instead, or the note eats the list in a tiny window.
- **Narration accuracy (2026-10-18):** user measured ~20% wrong lines per chapter (Gemini Flash, high
  thinking). Sampled GhostStoryClub ch1 + VillainParty ch4.2: the misses were lines given to the focused
  main character (001_039: classmates' complaints given to Lee Jun), captions split over panels told as
  two unrelated lines (001_112/115), and invented expressions or dramatic adjectives. prompts/narration.md
  now has look-either-side, bubble order by reading_direction, *Who is speaking* (tail, tail-less,
  focus is not speaker, bubble shape -> verb), split sentences, *Only what is there*. Kept short on
  purpose: the 15-pass version (c75638e) made it worse. The user's style rules still win over any outside
  guide: no quotes, no emoting, third person, no foreshadowing.
- **Reply skeleton + loose rules (2026-10-18):** part 1's text page ends with the reply JSON, every panel
  id pre-listed with empty text (`pdf/manifest_info.py:reply_skeleton_lines`). The prompt opens with "the
  rules serve the story": guidance for a capable model, the panel wins over a rule, unsure = tell less /
  *someone* / `problems`. Bubble order, tail and shape rules say *usually*; quiet panels may be a few words
  (MIN_WORDS_PER_PANEL 3). User's reason: rigid rules make a large model invent things to obey them.
- **`skip: merged`:** a bubble-only story panel can leave the video and its lines open the next
  narrated panel's text (user request). check.py errors when nothing narrated follows it and warns past
  30% merged. load_narration drops it like any skip.
- **The gap between panels is trimmed, not just padded.** Qwen bakes an uneven lead-in into every
  clip - measured over a finished 137-panel chapter: lead median 370 ms, range 0-460, stdev 164;
  tail median 60 ms. Added to a 350 ms pause that was a median 780 ms gap that wobbled by panel,
  which the user heard as "a person separately speaking each panel". `audio/clips.py:speech_bounds`
  now finds the speech and leaves `SILENCE_KEEP_MS` (25) either side; `audio/tts.py` records the
  slice as `clip_start_ms` + `duration_ms` in audio_timing.json and `audio/master.py` takes exactly
  that slice. Measured after: 780 -> 50 ms median at gap 0, join stdev 164 -> 100 ms, master length
  equal to the timeline within 6 ms over 14 minutes.
  - **A median is the wrong way to check this (2026-09-20).** Measured at the same -50 dBFS the trim
    used, the gap looked solved: median 50 ms, max 60. Measured at an *audible* floor (-40 dBFS) the
    same chapter had 40 of 136 joins over 120 ms and a worst join of 590 ms. `detect_leading_silence`
    stops at the FIRST block over the threshold, so one 10 ms tick of room tone at -48 dBFS kept a
    whole 400 ms lead-in - and it counted as `duration_ms`, so no pause setting could reach it.
    `speech_bounds` now takes the first/last stretch holding `SUSTAIN_BLOCKS` (3 x 10 ms) above the
    clip's OWN speech level less `SPEECH_FLOOR_DB` (22), which is engine-independent where -50 was
    tuned for Kokoro. Measured after, same chapter: p90 440 -> 70 ms, max 590 -> 150, joins over
    120 ms 40 -> 1, narration 798.9 -> 786.2 s, and no clip got longer. **When a join still sounds
    wrong, measure at -40 dBFS, not at the trim's own threshold** - the threshold hides its own
    failures.
  - **Never trim the clip on disk** - it is what the model returned. The offsets live in the
    manifest, so re-deciding the gap is a pass over existing clips (a re-layout + re-mix + re-render)
    and never a re-narration.
  - **`duration_ms` is now the trimmed length**, so anything reading audio_timing.json gets a
    timeline that matches the master. Rows written before this have no `clip_start_ms` and a full
    `duration_ms`, which slices to the whole file - old chapters play as they did.
  - The edge fade is what keeps a tight join clean: worst sample step at a join measured -46.2 dBFS
    with the 35 ms fade against -35.7 dBFS without it.
- **audio_manifest.json** (`audio/manifest.py`) is zero trust on the audio folder, not on remanga's
  own bookkeeping: written once, at the end of a finished narration run, listing exactly the clip
  files that run needed. Checked before anything downstream reads the folder again - resuming a
  narration run and mixing both call `verify_audio_manifest` first - and raises `AudioManifestError`
  (tells the user to use Remake video) if a listed clip is no longer on disk, rather than silently
  narrating around it or mixing a chapter with lines missing. No manifest on disk (an older chapter)
  is not an error - there is nothing yet to check against. A panel remanga itself stops narrating
  removes its clip and rewrites the manifest in the same run, so that never trips it.
  - **Each row is `{name, bytes, sha256}`, not just a name (user request, 2026-09-20).** A name only
    proves a file is still there: a clip truncated by a full disk, rewritten by another tool or
    restored from the wrong backup passes a name check and then plays as silence or noise inside a
    finished chapter. Size is the cheap pre-check, the hash catches the rest (verified against a
    clip rewritten to the same length, which nothing else can see). Measured at ~1.3 GB/s, so a
    137-panel chapter costs about 55 ms per verify. Rows from before this are bare name strings and
    are still checked for existence - an older chapter is checked as far as its manifest allows.
- **Batched narration** (`audio.batch_narration`, settings row "Narration takes") is the answer to
  the tone resetting at every panel: a panel synthesized alone is a take of its own, so Qwen picks
  its pitch and pace from that line and nothing else. Trimming the joins did not touch it - it was
  never a gap. `audio/batching.py` joins panels into takes of about `batch_target_minutes`,
  **breaking only between pages** (not for how it sounds: greedy packing means one inserted panel
  shifts every later boundary and re-synthesizes the chapter). `remanga/subtitles/` then reads each
  take back with faster-whisper and matches the known script against it, so every panel still gets
  its own audio_timing row - pointing into its batch with `clip_start_ms`/`duration_ms` - and the
  mix, frame timeline and render never learn anything changed.
  - **Whisper is trusted for WHEN, never WHAT.** A misheard word just fails to match; mangled
    proper nouns, not numbers, are the common error in manga narration. It REFUSES below 90% match
    or with too many panels unanchored, because a misalignment is silent: the audio sounds perfect
    and the pictures are cut to the wrong words.
  - **Silence cannot find the boundaries** - measured, don't retry it: a 24-panel take needing 23
    boundaries had 46 pauses over 150 ms, because Qwen pauses between sentences inside a panel too,
    at the same 430-790 ms. That is why whisper is here and not a silence detector.
  - **`chunk_max_chars` must be off for a batch** (`synth.use_whole_text()`). It exists because a
    fixed generation budget truncates silently, but splitting a batch back into 260-char calls puts
    back every seam batching removes. The timeout has to rise with it (`_timeout_for`, 0.125 s per
    character): Qwen clone mode measured **RTF 1.40** on the 3060, so a 9-minute take is ~12.6 min
    of wall clock and the flat 300 s would kill it four times over.
  - **Numbers:** `subtitles/normalize.py` spells digits on BOTH sides rather than picking one, so
    it is right whichever side wrote the digit - chapters narrated before the prompt asked for
    words still align.
  - Measured end to end, 12 real panels in 3 takes: 99/100/100% matched, slices contiguous inside
    every batch, fades only at take edges. A real 142 s take of 24 panels matched 98.8% with every
    panel anchored. Whisper runs at RTF 0.10, free next to synthesis.
  - **A long take COLLAPSES, and the ten-minute plan does not work (2026-09-20).** Asked for 11,673
    characters in one go, Qwen read about three panels and then produced nothing but silence until
    max_new_tokens ran out: the file came back **655.28s, the 8192-token budget exactly**, whisper
    found 98 words in it (9 words/min against a normal 236), and the transcript tails off into
    "Thank you. Thank you... Thanks for watching!" - which is what whisper emits for silence. Match
    2.2%, 96 of 99 panels unanchored. In the SAME run a 4,611-character take came back whole and
    matched 97.5%. So the limit is the model's, not the token budget's, and it is somewhere below
    11,673 characters. The cap (then `MAX_BATCH_SECONDS`) was then **240s** and the settings offer 2 and 4 minutes,
    not 9.
    - `audio/takes.py:collapsed` catches it **before transcription**, on two signals: a take at
      the token ceiling, or one more than `RUNAWAY_FACTOR` (1.4) longer than its own estimate. The
      estimate is good enough for that - a healthy take asked for ~205s and came back 203s.
    - **The estimate is the ENGINE's pace (fixed 2026-10-04).** It was Qwen's 22.5 chars/s for
      every engine; Kokoro af_heart at speed 1.0 reads ~16, so every Kokoro take ran ~1.45x its
      estimate - right on the line. Golem Master ch1 page 5 (999 chars, a normal 63s) was split
      three times down to one 164-char panel (11s vs "7s") and failed the chapter with "cannot be
      split any further - lower Narration take length", which could never have helped. Now each
      synthesizer has `chars_per_second` (base = Qwen's `CHARS_PER_SECOND`; Kokoro's follows its
      speed along the measured wpm curve, held flat past 1.36), carried on every `Batch` and used
      by `plan_batches` too - so Kokoro takes are now really ~60s (22 takes for ch1, was 16 at
      ~85s). A new engine must measure its own pace or it inherits this bug.
    - **Qwen PRESETS are slower still (2026-10-04):** Ryan with the default monotone `instruct`
      measured 12.9 / 14.5 / 16.2 chars/s (928 / 627 / 185 chars), real speech with sentence
      pauses - 1.75x the clone's 22.5, so every take would have failed. `QwenSynthesizer.
      chars_per_second` = 13.5 in `custom` mode, 22.5 for clone/designed. A different preset or
      a livelier `instruct` may read faster - that only makes the check more lenient.
    - It then **splits at a page boundary and retries**, up to `MAX_SPLIT_DEPTH` (3). A collapse is
      the model losing the thread on a long text, so the answer is a shorter text.
    - **In-context cloning helps a lot and does NOT fix it (tested 2026-09-21).** The clone used to
      run in `x_vector_only_mode` because `designed_text` was empty. Whisper now reads the reference
      recording once and caches it beside the file (`plugins/qwen_tts/reference_text.py`,
      `<sample>.transcript.txt`), so the clone gets `--ref_text` and uses the recording IN CONTEXT.
      Same collapsing take, both ways: embedding-only gave 98 words and 2.2% matched; in-context
      gave **863 words and 39.8%**, 41 of 99 panels anchored instead of 3. Nine times the content -
      and still 655.28s, still the token ceiling, still refused. Adopted for the voice quality, not
      as a way to lengthen takes. Never fatal: no whisper, or an unreadable recording, falls back to
      the embedding exactly as before.
  - Rates worth not re-deriving: **22.5 chars per second** of generated speech (a batch, untrimmed);
    18.9 is the per-panel figure AFTER trimming and is the wrong one for planning batches.
- **Make video and Remake video both start from nothing (user request, 2026-09-21).**
  `workflow/cleanup.py:drop_audio_and_video` deletes `audio/`, `audio_modified/`, `subtitles/` and
  `video/` for that chapter before every run, forced or not, so a run means the same thing every
  time and what is on disk after it is what it produced. The user chose this knowing it costs the
  reuse - a chapter is narrated again (~20 min) whether or not anything changed. **The PDF is never
  touched**, and neither is anything under `chapters/` (pages, panels, crops.json, narration.json) -
  see `REMADE_KINDS`. It also solves folders left mixed by a change of approach: the per-panel clips
  hung around after the switch to batched takes. Side effect: Remake video now does exactly what
  Make video does, and the menu says so.
- **Remix video = the one path that does NOT start from nothing (user request, 2026-09-24).** For a
  music/sound/video-setting change: `workflow.remix_video` (menu "Remix video", CLI `video --remix`)
  deletes nothing, narrates nothing - forced mix, then an unforced render (picture reused when its
  fingerprint holds, so a 14-min chapter is ~50 s). It refuses when narration.json's (panel_id, text)
  list differs from audio_timing.json's, and only warns when the voice setting changed.
  **Testing tip:** use `.venv/bin/python`, never `bin/uv run --project <repo>` - that wrote a
  uv.lock and re-synced the repo's .venv (swapped 4 packages).
- **Settings are global - no per-project overrides (user request, 2026-10-01: "avoid confusing
  users").** History: on 2026-09-25 a project's own `project.json` "settings" made a chapter narrate
  in 1-minute takes while Settings showed one take per panel; markers (●/◆, "Use the defaults") were
  added then. Now the whole mechanism is gone: `RemangaConfig.for_project`, scoped `save`, the
  markers and the row. Every screen edits config.json. Old project.json "settings" blocks are left in
  the user's files (never modify projects/) and are simply not read. Verified in Pilot: a stale
  override is ignored, the top bar says "applies to every project", a change writes config.json.
- **Remake from source** (menu, CLI `video --from-source`): `workflow.drop_derived` deletes the cut
  panels + pdf/audio/audio_modified/subtitles/video for the chapter, keeping pages, crops.json and
  narration.json; then panels are re-cut and the normal video run follows (intro included).
- **Testing from a scratch cwd: symlink `checkpoints/` (and `global/`)** - model paths are
  relative to cwd (`checkpoints/qwen3_tts`, `checkpoints/kokoro_82m`, `checkpoints/magiv3`). Without
  the link a narration test re-downloaded 5.9 GB of Qwen into /tmp (a 7.5 GB tmpfs) and filled it.
- **Chapter menu (user report, 2026-09-25):** the user picked "Remake audio" expecting it to KEEP
  the narration and rebuild the video (its last step read "Keep the narration, drop the mix and
  video") - it re-narrates. Now: **Rebuild video** (the old Remix: narration kept, mix + render +
  intro) is listed first whenever a chapter is narrated; **Make video** says it narrates the whole
  chapter and asks before replacing an existing narration; "Remake audio" is **Narrate again, no
  video**; the duplicate "Remake video" is gone. Wording rule: say what is KEPT and what is REDONE,
  and name the slow part.
- **Settings layout (user request, 2026-09-25: "clear what does what, no duplicate"):** still one
  flat list (never a wizard), now 4 columns - group (Narration/Sound/Video/PDF, shown once on a
  group's first row), setting, value, and a <=38-char "What it does" (`Row.help`, `Row.group`).
  "Design a new voice" is an action and no longer repeats the voice name the row above shows;
  Music level hides while music is off. Checked by exporting a Pilot screenshot
  (`app.export_screenshot()` -> cairosvg -> PNG) at 116 cols (fits, no scrollbar) and 100.
- **Custom music level (user request, 2026-09-25):** Settings - Music level has "Custom..."
  (3-30 LU, number_check); the typed value is kept in `audio.bgm_custom_lu` and offered
  again beside the presets next time, whatever level is active. Tested with Pilot from a
  scratch cwd with a copied config.json (the settings screen saves to ./config.json).
- **Intro (user request, 2026-09-25):** Settings - Intro picks a video from `global/intro/`
  (or "No intro"), exactly like Background music; `video.intro_enabled` + `video.intro_path`,
  default off (the user's config has `global/intro/evil_intro.mp4` on). `video/intro.py`
  re-encodes the intro once per chapter into `_work/intro_leader.mp4` with the SAME encoder
  args/size/fps/colour tags/sample rate as the recap, then stream-copies it in front
  (concat demuxer) - only when `encoding.stream_signature` matches byte for byte, else it
  re-encodes the join. The intro fields are excluded from the picture fingerprint (adding
  them would have re-encoded every cached picture); `_work/final_intro.json` records which
  intro the final MP4 carries, so switching it re-joins. Verified on a zz copy of a real
  4K chapter: 11.0 + 826.83 = 837.83 s, full decode clean, stream-copy path taken, 56 s
  including the forced remix. The intros themselves are made in AMV_CD
  (`./amv.sh montage`), copies in /mnt/datadisk/channel_intro/.
- **Edge fade** (`audio.edge_fade_ms`, `audio/clips.py:apply_edge_fades`) is applied in
  `audio/master.py:panel_segments` at mix time, never baked into the clip on disk - it is part of the
  fingerprint, so changing it re-mixes without re-narrating. It is asymmetric on purpose: at the
  start it is capped by the clip's own leading silence (a flat 35 ms once ramped the opening
  consonant of 52 of 60 clips in a chapter, ~36x down), at the end it may ramp speech up to
  `TAIL_INTO_SPEECH` (15%) because clips often end within 10 ms of the last word.
- **The clone read a sentence nobody wrote into a chapter (2026-09-22, user report): "It's going to
  be the danger of the future."** It is the last line of the reference TRANSCRIPT, and it is in no
  recording anywhere. `_reference_clip` cut the user's 31s recording at a flat 15.000s, mid-sentence
  ("And that danger is | our contagiously handsome main guy"), whisper invented an ending for the
  cut, and that went to Qwen as `ref_text`. Qwen clones in context, so a word in ref_text that is
  not in ref_audio is a sentence it is shown and never hears finished - and it finishes it out loud.
  **A whisper hallucination has a shape: zero-length words stamped against the clip's last frame**
  (real words in that recording run 120-300 ms) - that is how `_drop_invented_tail` finds them.
  `plugins/qwen_tts/reference_text.py` now builds clip and transcript as ONE pair (cached as
  `{stem}.reference.json` + `.reference.wav`), cutting both at the last sentence that finishes
  inside the limit; `synth/qwen_reference.py:reference_pair` is the only way to get them, so a transcript can
  never sit beside a clip it is not of. No transcript = x_vector_only_mode = nothing to leak.
  **Rule: never hand a cloning model text you have not proved is in the audio it gets.**
- **A cloned voice drifts off its reference inside a long take (2026-09-22, user report).** Qwen3-TTS
  clones in context: the reference conditions the start, and the further a single generation runs the
  more it is conditioned on its own output (upstream calls it ICL speaker inconsistency; every
  long-form TTS has it, and the fix everywhere is to re-anchor more often = a shorter take).
  Measured in the user's own clone, as distance from their reference in units of its own spread
  (their windows 0.09-0.17, a clone 0.20, another narrator 0.7-0.9): one 240s take ran 0.22 -> 0.45
  with F0 down 12 Hz; three 60s takes stayed 0.16-0.24, drifting 0.01-0.03 each. A seam costs
  almost nothing (step across one 0.24 vs 0.17 between adjacent windows inside a take) and no time
  (both generate at 1.4x real time). So `CLONE_MAX_TAKE_SECONDS` is 60 and `batch_target_minutes`
  defaults to 1.
  - **Only clones are capped at 60s (2026-10-04, user asked for longer takes).** The drift is
    in-context cloning; a preset or Kokoro has no reference to drift from. Each synthesizer has
    `max_take_seconds`: `MAX_TAKE_SECONDS` 300 by default, Qwen in clone mode 60. Menu offers
    0/0.5/1/2/3/5 min. Verified: Golem Master ch1's longest 5-min batch in Qwen preset Ryan
    (37 panels, 3,814 chars) -> 284s vs 283s estimated, not collapsed, longest gap 1.1s, whisper
    matched 99.8%, 37/37 panels anchored, 0 hums; generated in 424s (1.5x real time). Timbre
    drift over a long preset take is NOT measured - rebuild voiceprint.py if it ever sounds off.
  - **Music loop crossfades (2026-10-04, user asked to check the loop).** `music_bed` used to
    repeat the song end to end (`bgm * n`): no clicks (sample step ~0), but every track's own
    fade-out + download padding left a DROPOUT at each seam - 1.5s of digital silence on
    ThapinByTheSea, up to 10.5s on others - then a cold restart on the intro. Now:
    `trim_dead_air` (30 dB under the song's median, 50 ms steps) + 4s equal-power crossfade
    (`BGM_LOOP_CROSSFADE_MS`). Measured on all 10 global/bgm tracks looped to 17 min: no silence
    at any seam; 8/10 never dip 25 dB under typical near a seam, Thapin/unravel dip -38/-30 dB
    for 0.7s (their own soft ending into soft opening; a deeper 20 dB trim did not change it).
    `BED_VERSION` is in mix.py's fingerprint so old mixes re-mix. Side note: the master WAV is
    -1.1 dBTP but the 192k AAC in the MP4 measured -0.7 dBTP (encoder overshoot) - not clipping.
  - **Ming-3.0-tts-0.5B engine (`ming`, 2026-10-24, user asked for a better TTS; MIT).** Plug-in
    `plugins/ming_tts/`, venv `ming-tts` (torch 2.8 - upstream pins 2.6, no cu129 wheels;
    transformers 4.46.3 pinned; pynini for text normalization). Upstream is NOT pip-installable: its
    source is a tarball at `setup.MING_COMMIT` in `.tools/ming-tts-src-<sha12>`, put on the worker's
    sys.path. Task "IP" (built-in voice, zero speaker embedding), 5 English voices. Footguns: its own
    save writes 32-bit float WAV, which `audio_seconds` (stdlib wave) can't open - the worker writes
    PCM_16 itself. run.sh exports HF_HUB_ENABLE_HF_TRANSFER=1 but no venv has hf_transfer, so a
    first weight download through run.sh fails - download_ming_tts.py forces it to 0 when missing
    (the other engines' downloaders still have this latent bug). Verified GhostStoryClubRemake ch2:
    14,890 chars -> one 798.6s take in 1045s (RTF 1.31, 18.65 chars/s), whisper 98.8% matched,
    pauses after sentences median 340ms (17/119 under 150ms - Kokoro's were ~420), raw -23.1 LUFS.
    Preset `plain-narrator` (the default then; presets removed 2026-10-25) = Ming US_Stella, whole chapter, every effect off,
    no limiter, loudness off (user: "don't add any effect or anything").
    **Male voice = UK_George, never US_James (2026-10-24, user asked for "its best male vocal").**
    Same 2,064 chars of HimeSama ch1: James matched the script 96.8% and SPOKE TWO SENTENCES THAT
    ARE NOT IN IT ("he is so happy that he doesn't want to leave the palace", "the girl stands up and
    says") at a rushed 213 wpm, pitch spread 5.82 st; George 98.4% (only name spellings), nothing
    invented, 169 wpm, 4.52 st. Preset `plain-narrator-male` (presets removed 2026-10-25). George reads ~15.3 chars/s, slower than
    the engine's 18.7 (Stella's) - takes run ~1.2x their estimate, inside RUNAWAY_FACTOR 1.4. Check a
    voice's script match with whisper before shipping it: an invented sentence passes every other check.
    **Ming's built-in voices wander over a long chapter (2026-10-24, user: "the vocal changes, at the start
    it is ok but as it becomes lengthy it becomes different", plus "low volume").** Not drift: upstream
    splits text into ~24-char fragments and generates each INDEPENDENTLY with a zero speaker embedding, so
    every fragment re-samples the voice. Measured on 6 fragments of HimeSama ch1 (MFCC-mean pairwise
    distance; content alone puts a floor ~12): George plain 32.0; anchored to a fixed George reference via
    prompt_wav + prompt_text + use_spk_emb 25.7 (the reference text never leaked, 0/18); reference audio
    without the embedding 36.1 (worse); sigma 0.25 -> 0.1/0.0 changes nothing (24.8-26.4); temperature is
    already 0. Kokoro am_fenrir (deterministic) 11.9. Shorter takes cannot help - fragments are already
    independent. Plain narrator presets have loudness OFF: the long video measured -21.1 LUFS. Preset
    `plain-narrator-kokoro-male` = Fenrir 1.0x, whole chapter, no effects, limiter, -14 LUFS.
  - **Edge voices engine (`edge`, 2026-10-24, user asked for Edge's Guy).** Plug-in `plugins/edge_tts/`,
    venv `edge-tts` (edge-tts 7.3, no torch, no weights - `NoWeights` hands the worker base a dummy dir).
    Worker: Communicate(text, voice, rate).save(mp3) with 4 tries, then system ffmpeg -> 24 kHz PCM_16 WAV.
    edge-tts splits a whole chapter itself; the voice doesn't sample, so whole-chapter takes are safe.
    Guy measured on HimeSama ch1: 14,156 chars -> 842.9s in 90s (16.8 chars/s; `speed` -> rate "+N%"),
    timbre distance 4.1-8.6 over 14 min (George 5.5-18.3, Fenrir 2.0-4.7), F0 150-154 Hz. Preset
    `plain-narrator-edge-guy`. Online + not a licensed API - said in the README; don't hide it.
  - **Fish Audio Drama 3 engine (`drama3`, 2026-10-25, user asked for the #1 of Artificial Analysis's
    open-weights TTS board).** 35B MoE (3B active), Fish Audio Community License (free < US$500k/yr,
    "Built with Fish Audio"). The official checkpoint needs 24 GB+ (int4 is 20.8 GB of weights), so it
    runs through speech.cpp (nyosegawa, MIT, C++/ggml, prebuilt Linux **Vulkan** release - no CUDA
    toolkit) and its Q4_K GGUF (sakasegawa/drama-3-GGUF, 20.8 GB, `speech pull` into
    checkpoints/speech_cpp/<owner>--<repo>/<sha256>/, path + size pinned in synth.py so a load never
    re-hashes it). Plug-in `plugins/drama3/`: empty venv `drama3` for a stdlib worker that bridges
    remanga's one-line protocol to `speech worker` JSON Lines (protocol 3: base64 PCM chunks -> WAV).
    **DEFAULT IS THE VOICE FILE (`voice_file: true`), since 2026-10-25.** The user first chose the built-in voice
    by ear ("for best quality lets go with it's builtin vocal"), then heard the full chapter: "voice don't
    match" - the built-in narrator changes from page to page. Built-in (voice "none", cue + seed per take):
    Built-in has NO chunk-join clicks (0 on the 2048 grid over 2,000 chars in one request), so a take is one
    request; its sentence drops are what page takes + retake_mismatches are for. Its other failure: a take
    STICKS ON A DRONE (steady ~150/300/450 Hz tone at -45 dB for ~20 s, sometimes then "thanks for watching")
    instead of reading its last sentence - seed-specific (one panel: seeds 1, 1001 stuck; 2001, 3001 fine).
    So `takes._make_take` rereads a collapsed take under COLLAPSE_RESEEDS 3 other seeds (21-23) before
    splitting it. Full HimeSama ch1, built-in: 32 takes, one reseed, all >= 90% (lowest 90, 94, 96), 16.8 min
    in 27.5 min, -14.1 LUFS - BUT per-take median F0 79-123 Hz (spread 11.2 Hz; the voice file's was 90-107,
    4.2): in its own voice the narrator's pitch moves between pages. Kept for the user to judge by ear:
    `global/voice/samples/drama3/9-HimeSama-ch1-FULL-CHAPTER-builtin-voice-with-music.mp3`.
    Then the same chapter with the voice file (a sentence per request, the default again): 32 takes, no
    reseed or retake, all >= 90%, 16.2 min in 25.8 min, -14.1 LUFS, per-take F0 91-103 Hz (spread 2.9), grid
    jumps at chance level (16 vs 18.8 of 38,507), none of the strong kind: `.../10-...voice-file-with-music.mp3`.
    Drama 3 is a cloning model - a "voice" is a reference recording; a real-recording clone is not built yet
    (offered; licence forbids imitating a person without consent).
    **Voice "none" drops sentences in long takes; a voice file fixes that but sounds less natural.** Read with the model's own pick
    (a bracketed cue `[deep, calm male narrator voice]` + seed, cue not spoken - whisper-checked), Drama 3
    DROPS WHOLE SENTENCES and babbles (whisper hears "thanks for watching"): HimeSama ch1 as one take 73%
    of the script, in ~3-min takes 33-100% (3 of 9 under the 90% alignment floor). The user guessed it
    first: "most likely it's not for generating very long audio". speech.cpp's own benchmark is one
    sentence per request AND a voice file - that is the regime it works in. Now: the worker makes, per
    described voice, `checkpoints/speech_cpp/voices/<voice>-s<seed>-v1.voice.gguf` once (the reference line
    read with cue+seed under voice "none", then `speech voice MODEL ref.wav --transcript ... out`, ~10 s on
    CPU) and `add_voice`s it; every take is read from it, so the seed only changes delivery (retakes are
    safe, `synth.seed` -> request seed + 1000*n). Takes ~one page (max_take_seconds 45). Measured, same
    chapter: 32 takes, 29 >= 95%, median 99%, two dropped a sentence (85%, 49%) -> `audio/retakes.py:
    retake_mismatches` (any engine with a `seed`): a take under align.MIN_MATCH_RATIO is read again under
    seeds 11-13 (hum retakes use 1-2), the better reading kept; both came back on retake 1 (100%, 96%),
    32/32 pass. End to end on merged main (2026-10-25): 103 panels, 32 takes, one retake (89.6% -> 97%),
    17.2 min of narration in 28.7 min incl. whisper; per-take median F0 90-107 Hz (one narrator), quiet at
    the 32 joins median 430 ms (min 200), master -14.2 LUFS / -1.8 dBTP.
    temperature/top_p 0.7 made things worse (ran to max_seconds, 30%).
    **Clicks at speech.cpp's chunk joins (user heard them, 2026-10-25: "artifact repeatedly, first at 9-10
    seconds").** speech.cpp cuts a request into ~300-byte chunks; with a voice file, each join landed on a
    sentence onset as a click - all three found sat EXACTLY on the codec's 2048-sample frame grid (frames
    204/442/779 of their request; find them with `(i + 1) % 2048 == 0` on sample-step outliers - plain
    step detection also flags real consonants, so filter by the grid). Fix: the worker sends ONE SENTENCE
    PER REQUEST (`sentences()`: split after .!? before a capital/digit) -> 0 on-grid jumps, 98% match, same
    speed (0.66x). Each request ends on its own silent tail, so butted joins left 600-1000 ms (outliers 1.8,
    2.9 s): `trim_tail` cuts a sentence's trailing silence to 350 ms (10 ms fade); in-sentence comma pauses
    (500-800 ms in deep_male) are the model's delivery and are left alone. The user found voice "none"
    smoother and more natural than the voice file, but "none" drops sentences.
    **Footgun: speech.cpp OOMs a 12 GB card** (`ErrorOutOfDeviceMemory` on the first request, or at load
    "cannot reserve the memory of the codec's decoding"): it puts as many layers' experts on the GPU as
    free memory at load holds beside a fixed 1.5 GiB allowance, too little under NVIDIA's Vulkan driver,
    and has no knob (no env var either - checked `strings`). Fix: the worker holds `gpu_headroom_gb`
    (2.5) through libcuda/ctypes (cuMemAlloc + cuMemsetD8 + 1 s so the Vulkan budget sees it) while
    speech.cpp loads, frees it once ready, and retries a load that OOMs with +1 GiB (3 tries); 2.0 and
    2.5 each failed once without the memset/retry. Measured: 1.5 GiB -> 11 of 40 layers on GPU, 2.0 -> 10,
    3.0 -> 7; load 46-61 s; RTFx 0.82 on a line, ~0.7 a chapter in page takes; ~15 GB RAM; deep_male 10.3
    chars/s over a chapter (12.6-14.1 on a line, others 15.5-17.2); F0 deep/warm male ~100 Hz, females ~165.
- **Delete chosen (user request, 2026-09-30)** - chapter menu "Delete chosen...":
  `workflow.cleanup.DELETABLES` (pages, strip, marks, panels, pdf, narration, review, audio, mix,
  subtitles, video) -> `deletable_items` (only what exists, sizes, "n of m" chapters) ->
  `ui/dialogs.Checklist` (SafeOptionList rules kept: Enter/Space/double click tick, `a` all, `d`
  done - Enter never proceeds) -> Confirm -> `delete_items`, every path checked to be that
  chapter's own inside the project, empty folders pruned. Red = can't be rebuilt (pages, marks,
  narration, review). Verified with Pilot on a zz project, screenshot at 116 cols fits one line/row.
- **Check narration + Pick all (user request, 2026-10-14).** Chapter menu "Check narration" (right
  after Long video; also offered when only some picks are downloaded) runs `workflow.check_chapter`
  per picked chapter: Make video's narration check (panels vs narration.json, voice rules, video-size
  warning) plus `narration_changed` (audio_timing.json vs narration.json - the same test Rebuild
  video refuses on). Never raises; state ok / problems / not ready, one report for all chapters,
  fix requests written as Make video does; each failing chapter lists its narration.json and fix
  request path, both copied by Copy paths (c). `p` on the chapters screen:
  pick all / all downloaded (status downloaded or local) / none. Verified with Pilot on a scratch copy.
- **Terminal menus: Android 17 look (user request, 2026-10-14)** - `ui/look.py`: Textual themes
  android-dark (default) / android-light with theme-android.css's M3 palette, plus ANDROID_CSS scoped
  to the App's `android` class (tonal cards instead of round borders, tonal top bar, one-line pill
  buttons, secondary-container row highlight). `menus.look` in config.json; Settings > Menus > Look
  switches live; "terminal" = textual-dark, verified pixel-identical to the old menus. Screenshots:
  Pilot `save_screenshot` SVG -> cached chrome-headless-shell `--screenshot` PNG.
- **Marking by hand without the marker UI (2026-10-24, user: "MAGI marks wrong 20% of the time,
  mark them all manually").** Write crops.json directly: `box_1000` is **[ymin, xmin, ymax, xmax]**
  (geometry.calculate_pixel_bounds), NOT l,t,r,b - the first cut came out transposed. Panels are cut
  in list order (no re-sort), `src: "manual"`, `custom_order: true`. Page `"exact": true` skips
  snapping/trim for a page where the snapper ate a caption letter at the page edge. **`page_index`
  names the panels, `page_filename` finds the file** - so a scanlation that put a page out of order
  (HimeSama ch2: printed page 32 shipped as file 002_041) is fixed by listing pages in story order
  with sequential indexes. Check every cut panel on contact sheets - a box edge through a bubble
  only shows there.
  When reading boxes off a gridded overlay, read the GRID LABELS (units), never the image's pixel
  rows: at a 1250-px-tall overlay the two differ by 1.25x, and 5 of 26 pages of HimeSama 3.x were cut
  through panels that way before the contact sheets caught it.
- **comix.to: "Error: Could not establish connection. Receiving end does not exist." (2026-10-24)** - the
  extension's message when a job reaches the helper's tab while it is closing/reloading (a --force re-run
  straight after the last one). Nothing is lost (pages are only swapped in after a whole, checked
  download); running it again works. Downloads that sit silent for 10-20 min with no check showing are
  the helper waiting on Firefox's background tab - they finished on their own (ch 3.1 took ~20 min).
  Three --force passes of HimeSama 3.1-3.3 were byte-identical (34 pages, SHA-256).
- **Panel Marker opens in Adjust (user request, 2026-10-14)** for every chapter, marked or not
  (chapter-nav.js applyChapter); Adjust draws new boxes too, D switches to Draw.
- **Job queue (user request, 2026-09-29).** `workflow/queue.py` holds jobs (project, chapter,
  action) in `projects/queue.json`; only unattended actions (download, pdf, video, remix, reaudio,
  source) - marking and the narration passes need the browser. Menus: a chapter's "Add to queue",
  `j` opens `ui/screens/queue.py` (r run, x remove, shift+up/down reorder, c clear finished); the
  run is one TaskScreen with `keep_going=True`, so a failed job is marked and the next starts,
  Ctrl+C leaves the rest waiting. CLI: `./run.sh queue [--run]`. Jobs are matched back by `id`.
- **A take can hum between two words (2026-09-29, user report, HimeSama ch1 50-51s).** Qwen samples
  (temp 0.9) and now and then holds a note after a sentence instead of speaking: 0.6s silence, then
  1.2s at -22 dB, ~450 Hz, flatness 0.01, no word in it. Every script word is still there, so the
  collapse check and alignment pass it. `audio/hums.py:find_hums` flags a >=0.3s run of loud, tonal
  frames inside a gap between whisper's words; swept over 26 real takes it fired on that one only.
  `audio/retakes.py:retake_hums` redoes a humming take under seed 1, 2 (`QwenSynthesizer.seed`,
  sent per request) and keeps a retake only if it hums less AND still matches its script; each batch
  row records `retakes` so a reused take is not retaken every run. Retake, never cut: whisper can
  miss a real word (names), and cutting would drop it. The detector frames go through `load_audio`
  - pydub's resampler raised flatness 3-5x and nearly hid the hum.
- **Resampling:** clips go 24 kHz -> 44.1 kHz through `audio/resample.load_audio` (ffmpeg), never
  pydub's `set_frame_rate` (folds imaging noise above 12 kHz).
- **Frame cuts** snap into the pause between pages (`video/frame_timeline.py`) so a picture changes
  just before its narration starts.
- **Panels, not pages (2026-09-18, user request):** the video plays one panel per clip.
  `workflow.mark` opens the marker (blocking until the browser saves), `workflow.cut_panels` recuts
  whenever crops.json is newer than panels/, and `make_pdf` calls it first. crops.json and the pasted
  narration are the only things nothing can rebuild - Reset deletes panels/ but keeps crops.json.
- **Gutter snapping must never reach past the panel it is snapping (2026-09-22, user report):** a
  panel came out blank in the PDF and the LLM answered `skip: "blank"`, while the mark in the marker
  looked perfect (ch 1 page 3 panel 5, the black caption banner). The search radius is scaled to the
  PAGE (`panel_boxes.adaptive_gutter_radius`, a tenth of the longer side = 160px there) and the
  banner is 150px tall, so `seams.reconcile_adjacent_seams` searched 167px for the border between it
  and the art below, found the white gutter ABOVE the banner, and moved BOTH facing edges there:
  918x150 -> 918x4 of blank paper, and the panel below grew to swallow the banner. The old guard
  (`t1 < mid < b2`) allows a seam anywhere inside either panel, and refine's inversion check passes
  a 4px box happily. Now the seam search is also bounded by the two panels (`_seam_search_radius`:
  it must leave half of each standing) and no single edge may search past the middle of its own box
  (`gutter/refine.py`). **Symptom to remember: a blank or sliver crop under a correct-looking mark is
  the snapper, not the marker** - compare `resolve_page_panel_boxes`'s marked vs refined boxes before
  suspecting anything upstream. Over chapter 1's 138 panels the fix changed exactly those two boxes,
  and the seam pass still moves 47 of them.
- **A worker thread parked in one `Event.wait()` cannot be stopped:** the menus stop work by raising
  KeyboardInterrupt into the thread (`PyThreadState_SetAsyncExc`), and that is only delivered when
  the thread next runs Python - never, inside a single C-level lock acquire. Opening the marker and
  stopping it left "stopping..." on screen forever. Any blocking wait in work code waits in short
  steps instead (`webui/launch.py:RunningUI.wait`), and takes its server down on the way out.
- **Three web UIs, one look:** the Panel Marker (pages, drawing), the Narration Writer (`write`) and
  the Narration Reviewer (`review`) - the last two brought back on 2026-09-18 and adapted to the
  current narration shape (`narration.narration_document` / `written_panels` / `read_reply`; the
  Writer's OCR button went with DeepSeek-OCR). They share `webui/static_shared/`: the logo, the
  favicon and `css/theme.css`, which holds the terminal menus' palette (Textual textual-dark:
  #121212/#1e1e1e, accent #fea62b, muted #9a9a9a) - every stylesheet reads those names, so the look
  changes in one file (user request).
- **Reading order is `webui/mark_ops.py` (recursive XY-cut) and the direction comes from
  project.json** (`marker_session.reading_direction`), never guessed. Edge case fixed 2026-09-18: a
  banner/strip across the top overlapping the tops of two tall columns was read second, because it
  and the tall column had tops within a few pixels and counted as one row. A mark spanning >=80% of
  the group's width and <=35% of its height is now its own tier (`_strip`). Checked against 56 real
  pages (their chapter 1 + a MAGI-marked chapter): no other page's order changed.
- **The marker needs a browser**; in the Textual UI it runs as a task whose step just waits.
  Headless checks that work: `MarkerSession(project, [ch])` + `webui.detection.run_detection(state,
  config.marker)` + `session.save_chapter(ch)` writes crops.json; `create_app(session,
  config.marker).run(port=…)` then GET `/`, `/api/chapter`, `/api/pages/<file>`, `/api/outline`.
- **Every page of a chapter's PDF is one size and black** - the chapter's biggest panel, panels
  centred on it, and the text page white-on-black with its type scaled to the page
  (`pdf/writer.py:build_pdf(canvas=...)` + `pdf/textpage.py:text_layout`, canvas passed from `builder.py`) - panels
  are all different shapes, and a PDF that changes shape per page reads badly (user request).
  Geometry only: the image streams, the JPEG passthrough and the file size are unchanged, and the
  text still extracts with pdftotext.
- **`video.max_upscale` (3x, user 2026-09-18) caps how far a SMALL panel is enlarged** - at 4K the
  median panel was being blown up 4x and the smallest 8x, which is soft for nothing. Looked at
  rendered frames to pick it: 2x leaves a tall panel at 13% of frame width (lost), 3x reads well and
  stays sharp. `FrameCompositor._capped` applies it in both fit paths, so `scale_for` - and the
  quality warning - see the same number.
- **Panels bigger than the video are warned about** (user request: don't lose quality silently).
  `video/compose.py:quality_warning` uses the compositor's own `scale_for`, so the number is the real
  fit scale, and suggests the smallest offered size that fits. Said ONCE (user: "remove duplicates from
  the terminal", 2026-10-01): in the pre-check (result screen / CLI, NARRATED panels only); the
  compositing step no longer repeats it. Measured
  on a real chapter: 8 of 60 panels shrink at 1080p, 2 at 1440p, none at 4K.
- **Video is 4K (3840x2160) since 2026-09-18 - the user asked for best quality** after the panel
  warning showed 8 of 59 panels shrinking at 1080p. Measured on a real 4m23s chapter: frames
  composite in 3s, the NVENC encode takes 1m12s, the MP4 is 42MB (still panels compress hard; the
  encoder is CQ 18 VBR, not bitrate-capped) and a rendered frame is 50dB PSNR against its source.
  Frame cache is ~126MB a chapter. Don't trade this back for speed unasked.
- **TTS engines are plug-ins** (2026-09-18, and since 2026-10-01 self-contained folders). An engine
  is one folder `remanga/plugins/<name>/`: `__init__.py` registers a `TTSEngine` + its `ToolSpec`
  (references only, no heavy imports), `config.py` (its block: `voice_options()`, `voice_label`,
  `voice_detail`, `identity()`), `synth.py` (a `BaseWorkerSynthesizer`), `rows.py` (Settings rows),
  optional `prepare` hook (Qwen: reference_text.py, whisper before the model loads), and `scripts/`
  (worker + weight download; `spawn_script_worker(tool, "plugins/<name>", script)`,
  `ModelManager(download_script=<Path>)`). `config/tts.py` BUILDS `TTSConfig` with pydantic
  `create_model` - one field per registered engine named after it - so `config.tts.kokoro` and
  config.json are unchanged. Nothing outside asks which engine is running.
- **Cloning a recording needs NO transcript - and must not be given a wrong one.** Qwen's
  `create_voice_clone_prompt` refuses in-context mode without `ref_text`, so a supplied recording
  clones with `x_vector_only_mode=True` (speaker embedding). Passing a transcript that is not what
  the clip says (remanga did: it handed the designed-voice line to a user's recording) makes
  generation crawl - one 260-char line blew a 300s timeout; with the fix the same line is 19s.
  A sample remanga designed itself DOES know its text (`designed_text`), and uses it. References
  over 15s are trimmed to a cached `*.first15s.wav` copy: the reference sits in the context of every
  generation. Verified by cloning a 31s recording: median pitch 146Hz against the reference's 147Hz,
  pitch spread 3.91 vs 3.90 st.
- **Qwen3-TTS acts unless told not to** (user: "like a bad actor trying his best"). Measured on one
  line, same voice, pitch spread in semitones: no instruct 5.89, "a calm narrator telling a story"
  3.98, "flat, like a documentary voice-over" 4.02 (no better), "monotone... like reading a technical
  manual" 3.09 - which is the default now. The VOICE matters as much: Serena and Ono_Anna read at
  2.66 st, Ryan 4.02 (flattest male), Aiden and Uncle_Fu 5.17. Samples live in
  global/voice/samples/qwen/ (`remanga voices`, or Settings - Hear the voices), delivery/ has the
  four registers. Measure flatness rather than guessing: autocorrelation F0 per 40ms frame, spread in
  semitones about the median.
- **Nothing in the UI names an engine.** The video step's label is
  `config.tts.spec.display_name` - it said "(Kokoro)" while Qwen was narrating (user report).
- **Engines today:** `kokoro` (default, fixed voices, a 60-panel chapter in seconds) and `qwen`
  (Qwen3-TTS 1.7B, Apache 2.0, `.tools/venv-qwen-tts`): preset narrator + `instruct`, or a voice
  DESIGNED from a description. Designed = VoiceDesign model makes one sample once
  (`synth/qwen.py:design_voice`, a one-shot run, not the worker), then the Base model clones THAT
  sample for every panel - re-describing per panel is what makes a designed voice drift. Three
  variants, ~4.3GB each, downloaded only for the way actually used.
- **Kokoro's voice is a NAME** from `plugins/kokoro/voices.py` (`tts.kokoro.voice`).
  **Chatterbox voice cloning was tried on 2026-09-18 and rejected the same day** - the user found the
  clone bad and the music too loud under it - so it was removed again; that version is on the branch
  `backup/chatterbox-2026-09-18`. Don't re-propose cloning unasked.
- **Kokoro lang_code** is derived from the voice (a mismatch speaks with the wrong accent silently).
- **Config migration:** a config.json from the multi-engine version keeps Kokoro's settings in a
  `kokoro` block (lifted to `tts.*` by `config/tts.py:_from_engine_blocks`), and a Chatterbox-era one
  has a voice that is a FILE PATH plus no speed - `TTSConfig` drops what it does not know and falls
  back to defaults; old project.json override keys are mapped in `config/root.py`.
- **Sound settings: speed 1.0 and background music OFF (user, 2026-09-18** - they asked for normal
  narration with no speed-up, and no music by default; the 1.33 speed tuned on 2026-09-17 is gone).
  Boost 0, loudnorm on to -14 LUFS / -1 dBTP. When music IS turned on it sits 14 LU under the voice.
  Kokoro speed is NOT linear: 1.0=185 wpm, 1.3=225, 1.33=237, then 1.36=266 (sentence pauses start
  disappearing) - don't go past ~1.35 if they ever ask for faster. Music gain is computed at mix time from the integrated loudness of the narration and of the exact
  looped bed the mix plays (whole-file measurement was ~1 LU off - songs' openings are quieter);
  verified 14.0 LU on all three global/bgm tracks. The tracks are mastered -9.9 to -12.7 LUFS, which
  is why the old fixed `bgm_volume_db` (removed) put them 18-20 LU under = barely audible.
- **Normalizing is measure + one gain, NOT loudnorm (2026-10-01).** Two loudnorm passes took 22 of a
  7.4-min chapter's 24 s of mixing (loudnorm upsamples to 192 kHz). `audio/master.py:measure_loudness`
  reads I and true peak with `ebur128=peak=true` (~1 s), then `volume=<target-I>dB`, plus
  `alimiter` (sample peaks, 0.5 dB under the -1 dBTP ceiling) only when the gain would push peaks
  over. Measured vs the old master: -14.1 vs -14.0 LUFS, LRA 1.3 both, TP -1.4 vs -1.0, same length;
  mix 24.4 -> 5.4 s. Never single-pass dynamic loudnorm - it pumps music between sentences.
- The voice identity in audio_timing.json includes SPEED; before, a speed change silently reused
  clips at the old speed.
- **Projects are created from a MangaDex URL/ID/title** (`workflow.create_project`): named from the
  English title (`title.en`, else the first `altTitles` en) in PascalCase cut at 40 chars, reading
  direction from `originalLanguage`; same manga_id -> opens the existing project. The chapter screen
  (`wizard.chapters_screen`) refetches MangaDex's list on opening; reset/delete go through
  `workflow.reset_chapter`, whose `_chapter_paths` refuses blank names and anything not a
  `chapter_*`/`narration.json` strictly inside the project.
- **2026-09-17: the user's whole `projects/` directory vanished at 18:58:36** - between turns, not by
  any command run in the session (last one 18:37), and no remanga code can delete it. Test anything
  that writes under `projects/` from a scratch cwd (`cd scratch; PYTHONPATH=repo python -m
  remanga.cli ...` with a copied config.json) - `get_projects_dir()` even mkdirs `projects/` in cwd.
- **The UI is Textual, full-screen (user requests: the old line menus looked ugly and left messy
  logs behind; then mouse input).** TopBar / body / Footer on every screen. Flows are `@work` async
  methods that `await app.push_screen_wait(Choice|Ask|Confirm|TaskScreen|Result)`. Work runs in
  `TaskScreen`'s thread worker: `console.file` redirected to `projects/P/logs/chapter_N.log` (or
  `project.log`), progress via `remanga.activity` (never create a Rich Progress directly), Ctrl+C =
  async KeyboardInterrupt into the thread + SIGTERM to child processes (`pgrep -P`), then
  **SIGKILL after `STOP_GRACE_SECONDS` (3s)** for any still alive (`ui/task_io.py`).
  - **Why the kill (fixed 2026-10-04, user: "can't stop while make video is running"):** ffmpeg
    catches SIGTERM to finish its file cleanly, and on the real chapter encode (concat of PNGs ->
    h264_nvenc + the sound as a 2nd output) it never does - all threads in futex waits, no
    signal pending, forever. The work thread is blocked in `for line in proc.stdout`
    (ffmpeg_io), so the async KeyboardInterrupt never lands either: screen stuck on
    "stopping…", GPU still encoding. A 320x240 libx264 test encode stops fine, which is why
    this was missed - reproduce stops on the REAL render (Pilot + TaskScreen + workflow.render on
    a `cp -al` copy of a project, after unlinking the copy's picture/concat/final_intro so
    writes can't reach the original through the hard links). Now stops in ~3.4s.
- **Settings stay a flat list of rows, never a wizard** (user request, asked directly whether the
  Qwen rows should fold into a pick-how-you-want-a-voice walkthrough: "better this way as a simple
  settings instead of a walkthrough"). One row per thing, each opening one dialog. A row that does
  not apply hides itself - as Delivery does for a cloned voice - rather than becoming a step.
- **Nothing is highlighted until an arrow key or click; single click only highlights, double click
  (or Enter) chooses** (user request). `SafeTable`/`SafeOptionList` enforce it. Textual gotchas hit:
  a subclass `_on_click` must call `event.prevent_default()` or the base class handler still runs
  (and chooses); `OptionList.__init__` highlights option 0 itself; a focused widget's hidden Enter
  binding hides the screen's footer hint (so the widgets carry shown Enter bindings, and `Result`
  has `AUTO_FOCUS = ""`); `log` is a Widget property - don't name an attribute `log`; a box squeezed
  to zero height still draws scrollbars (user saw it in VS Code's short terminal panel) - output boxes
  are wrapping `RichLog`s with `overflow-x: hidden`, and the task screen hides its box when too short.
  Test small sizes too (116x18, 116x12).
- **Small windows must still scroll** (user hit this in VS Code's terminal panel): a Textual box
  with `height: auto` clips its overflow and CANNOT be scrolled, so every dialog caps its scrolling
  part to the window in `dialogs.fit_to_window` (called after a refresh, twice - the first pass
  measures a clipped box). It measures what is around the box instead of guessing, skips hidden
  children, scrolls the box home (a stale offset hides the title) and `refresh(layout=True)`s it (a
  stale scrollbar otherwise stays on). Under 14 rows `.cramped` drops the border/padding and goes
  full width; the Result screen hides its buttons under 20 rows (the keys are in the footer) and
  focuses `#result-text` so arrows scroll it while Enter still continues.
- Test the UI with Textual's `app.run_test()` Pilot (keys, `click(times=2)`) and once in a real pty
  (TERM=xterm-256color, pyte via `bin/uv run --no-project --with pyte`, SGR mouse `\x1b[<0;x;yM`)
  from a scratch cwd; a test that presses Enter without an arrow first "hangs" - that is the rule.
  Check 100x12 and 40x10 too: `virtual_size.height > region.height and not allow_vertical_scroll`
  on any visible widget means content nobody can reach.
- Decimal chapters are chapters of their own: `1-5` takes 4.5, not 5.1 (`chapters.expand_chapter_selection`).
- MangaDex chapter list is cached 24h in manifest.json.

- **Long-strip manga / webtoons (user request, 2026-09-30)** - `remanga/plugins/long_strip/` (was `longstrip/`). A webtoon
  chapter is ~15 images of 720x5000-9900 cut through panels. `layout.is_long_strip`: project.json
  `layout` (set from MangaDex tag Long Strip `3e2b8dae-...` at create) else median image h/w >= 2.5.
  - **No MAGI for webtoons (user verdict):** "magi is trained for pages type of manga". Don't bring it
    back for long strips. The mangaEasy port (recursive gutter split) is gone too (2026-09-30): it
    re-guessed the gutter colour inside every piece - **425 colours** on one chapter, 89% of 15.5 s -
    and scored by MOST panels, so a flat sky inside a panel cut it. Now `gutters.py` VERIFIES colours
    first: solid rows (median colour, 97% within 8) -> runs >= 12 rows with one 99.5% row -> grouped
    by colour (within 16) -> a gutter only if its colour separates the strip 3x ("strong") or 2x within
    6000 rows ("local": black flashbacks, coloured scenes). **A repeat only counts with art between**:
    the steps of one black-to-white fade "verified" each other as six gutters until that rule. Then
    `detect.py`: blocks between gutters, small ones (< 0.45 w) glued across the narrower gap,
    featureless dropped, (superseded by detector v3 below). Measured ch 25:
    2.4 s vs 15.6, 84 panels vs 87, differences looked at - same quality, no colour guessing. GPU
    considered and declined (user agreed): torch + CUDA init alone is 3.8 s.
  - **Detector v3, 2026-09-30 (user: "cuts panels in half most of the time", "drop my logic, apply
    yours, multiple methods at once").** On their manhua (1000 px wide, zh) the panels are mostly
    STACKED art with a hard edge and no white gutter, so gutters alone saw 2-3 panels as one block and
    the mangaEasy auto-split then cut every tall block at fixed points through faces (13 forced cuts).
    Now votes: `gutters.py` (unchanged) + `signals.py` (edge = share of width changing > 40 grey
    levels; decor = 1 - adjacent-row correlation; band = colour of 16 rows above vs below; energy =
    rolling max of row spread +/-30) fused in `borders.py` (0.5 edge + 0.3 band + 0.2 decor >= 0.5, a
    lone peak, >= 40 rows apart) + glue small + drop blank + `quiet.py` (split > 1.8 w only at a stretch
    under 0.25 x the picture's median energy, middle half, never forced; else flagged `tall`).
    **Scored against the user's own strip_marks.json** (57 panels): F1 0.86 vs 0.69 for the old
    detector (46-48 of their panels found, 48 of 54 proposed right); thresholds swept on a coarse grid
    and stable across border scores 0.45-0.55. 6 of their 16 art-to-art borders have NO signal at all:
    they are editorial splits of one continuous picture, at rows quieter than 92-99% of the rows
    around - which is what quiet.py imitates. Visually checked on Skeleton Soldier too (sword + SFX
    kept together, bubbles attached, fade dropped). Evaluation scripts were in the scratchpad
    (proto/evalnew/compare/signals.py) - rebuild them the same way: score IoU >= 0.8 both ways.
  - **Detector v4, 2026-10-19 (user, Ghost Story Club ch 2 screenshots: one picture cut at its fence
    line and again mid-ground; "more accurately detect panels").** Scored on all three hand-marked
    chapters (Ghost ch1, Urban ch1, Invincible ch1; 250 cuts, a cut matches within 60 rows): ~140
    rows passed the border vote and only 3 were cuts the user kept - a horizon, fence, desk or caption
    box edge scores like a cut, and those were the false cuts. Their gutterless cuts are almost all
    editorial splits at calm rows (score ~0). So: **borders never cut on their own**; in `quiet.py`
    a too-tall picture is split at its strongest border (score >= 0.6) in the middle part first, else
    at the calmest stretch. Also `gutters.py` trims each gutter to its CLEAN rows (full width, <= 1 ink
    pixel > 48 off the colour) and drops one with none - a bubble hanging across a white gutter was
    being cut in half (Urban ch1 x2). `FEATURELESS` 4 -> 15 (every user panel has a row with spread
    >= 36; a white fade between two gutters had 6) and touching gutters leave no zero-height piece.
    Result: same 18 misses, false cuts 37 -> 24 (rest: credits pages, debatable calm splits).
    `SLICER_VERSION` 5. A chapter whose proposal was already auto-saved keeps it until Auto (R).
    Rejected: smaller glue share (0.35/0.25: more false cuts), border-only thresholds (0.8/0.9 = none).
  - **Strip Marker visibility (same day, user):** "hard to see what I'm marking, no focus, no option
    to make a new mark". Now: per-panel colours (overlay.js PALETTE) with a dark double edge (reads on
    white and black art) and no tint, big number badge, hatched rows no panel covers; the selected
    panel is spotlit (box-shadow 100000px dim) with a selection bar (`selbar.js`: rows, Split, Merge,
    Delete); **＋ New panel** button/A (`state.mode = "new"`, next drag draws even over panels);
    **double-click fits** a panel between the nearest gutter/border/panel edges (`fit.js`); **M merges**
    with the next (`edits.js`). All verified in headless Chromium on a copy of the user's chapter.
  - Package is one job per module: runs, gutters, detect, marks, pages, crops, tiles, build (see the
    package docstring). Marks = [top, bottom, left, right] (left/right always 0/1 since 2026-10-16), **overlap
    allowed**; `pages.py` never splits touching/overlapping marks across pages. `crops.py` writes
    `box_pixel` + page `"exact": true` -> `cropper/crop_page.py` turns off snapping, trim and padding
    for that page (snapping pulled overlapping edges apart). **Footgun fixed:** panel_boxes guessed
    thousandths from `max(box) <= 1000`, so a pixel box on a page under 1000 px tall was misread -
    now the key decides.
  - **Strip Marker v2** (`plugins/long_strip/web/`: `session.py` state, `server.py` routes, `static/js/`
    = api state geometry history viewport hit gestures keys sidebar actions status main): tiles of
    run-width x 2 rows (<= 900 px wide JPEG) mounted only within +/-1 screen, marks as DOM bands only
    in that window; Panel Marker rules (click selects, only the selected moves, drag elsewhere draws,
    Shift = no snap to gutters/other marks), Tab/arrows nudge, J/K, undo/redo,
    autosave. Measured: load 3.3 s (was 19), 2-3 tiles mounted anywhere in the chapter, 10 MB JS heap;
    every gesture verified in headless Chromium, overlap carried to exact crops (869 + 284 rows cut
    exactly). **CSS footgun:** `.forced` was both the strip's dashed line (position absolute) and the
    sidebar flag - the flags flew to the window's left edge; the line is `.forced-cut` now.
  - Panel Marker **`s` = split the mark under the mouse** into top/bottom at the mouse's height
    (`marks.js:splitMark`, `ShortcutsConfig.split_mark`). Shift+S cannot be a second binding:
    shortcuts.js lowercases printable keys, so it normalizes to "s". Verified in headless Chromium
    (Playwright into the scratchpad - no node on this box): 315-1307 -> 315-711 + 711-1307, autosaved.
  - **S direction + Ctrl+Z (user request, 2026-09-30):** Options -> "S splits a mark" = across
    (top/bottom) or down (left/right), `MarkerConfig.split_direction`, saved via POST
    /api/settings; left/right halves are numbered in reading order (right first for rtl).
    `undo` (mod+z) is per page: `markDirty` records the page's previous JSON state (so every
    gesture is undoable for free, and a click that moved nothing records nothing);
    `settleHistory` runs wherever marks arrive from outside (page load, poll, reload, server
    reorder) and records a server change as a step too. No redo. Verified in headless Chromium:
    split across/down, delete, each undone and autosaved; extra undo -> "Nothing to undo".
  - Not done (ask first): a vertical pan over very tall panels, a "join two marks" key, redo.
  - **Strip Marker canvas (user request, 2026-10-16):** the gestures listen on `#reader`, not
    `#stage`: a drag that starts on the empty canvas beside the strip draws a new mark
    (`hit.js:at` holds off-strip points to the strip's edges), a click
    there deselects (and drops a started line / New panel mode). A press beside the strip never grabs
    the selected mark; presses on the reader's scrollbar are ignored. Verified in headless Chromium.
  - **Strip marks are full width, y only (user request, 2026-10-16).** No Alt-narrowing, no side
    handles, no sideways move; `marks.py:normalize` and `history.js:tidy` force left/right to 0/1, so
    old marks with sides read as full width. While drawing, `#dragBox` (dashed) shows the box dragged
    out from the start point to the mouse - canvas included - and the band shows the mark it makes.
    **Footgun fixed:** the selection bar sits above `#reader`; showing it on the first draw step
    pushed the strip 45 px down under the mouse - `selbar.js` now scrolls by the shift.
  - **Marking and creating panels are separate steps (user request, same day).** Strip Marker Finish
    only saves strip_marks.json (no ensure_strip); chapter menu **Create panels** =
    `workflow.cut_panels(force=True)` (strip/ + crops.json + panels/), **Remark panels** =
    `workflow.remark` (delete_items marks/strip/panels, then mark - the marker proposes afresh).
    `has_marks` counts strip_marks.json too, so a marked-but-uncut strip shows "create the panels".
    Make PDF still cuts when the panels are stale. Verified: headless Chromium, cut 142 panels on a
    copy, remark left only pages/, Pilot menu lists Mark / Remark / Create panels.
  - MangaDex lists officially licensed chapters with `externalUrl` and 0 pages; downloading one
    prints "All 0 pages verified" and gets nothing. Test webtoon: Skeleton Soldier
    (d993f789-e7e5-4832-92fd-37614220b427) ch 25 is hosted.

- **Several sources per project (user request, 2026-10-24: HimeSama ch1-2 on MangaDex, ch3+ only on
  comix.to).** `remanga/sources.py` owns it: project.json `"sources"` list (first = preferred; top-level
  source/manga_id/manga_url = the first, so one-source projects have no list and read as before).
  **Clients never write the top-level identity** - `remember_source(project, name, id, url)` updates only
  their entry (comix used to overwrite manga_id/source, which would hand MangaDex comix's id). Core always
  passes each client its own link (`chapter_listing`, `plan_downloads`): chapter -> the source that
  downloaded it (manifest pages.source; MangaDex records now carry "source" too, old ones default to it),
  else first with pages (MangaDex lists licensed chapters with pages 0). Planning never opens Firefox: cheap
  sources (fresh_on_open) are asked, the browser source takes the rest and looks them up itself. Chapter
  lists are cached per manga id (`manifest.remote_chapter_lists`; the old single `remote_chapters` slot is
  still read). `refresh=None` = each source as on opening; `list_fresh_on_open` is gone. `list_projects`
  has `manga_ids`, so `new` with any source's link opens the project. UI: `o` Sources on Chapters; rows
  name their source when there are several. Verified on a scratch copy + Pilot with the comix list stubbed.
- **Browser sites (comix.to, `remanga/plugins/browser/`), 2026-10-15.** comix.to = Cloudflare
  managed challenge + signed/encrypted API, so the user's own Firefox does the work through the
  remanga helper extension (temporary add-on, polls 127.0.0.1:47615). Don't "simplify" to
  Playwright/Selenium/BiDi: a remote-controlled Firefox has `navigator.webdriver = true` and sits on
  "Just a moment..." forever (measured). Don't copy the user's profile cookies into another browser
  either - the auto-mode classifier refuses it (credential exploration), rightly. A profile's
  display name (Firefox's profile menu) lives in `Profile Groups/*.sqlite`, not profiles.ini, so
  `-P <name>` can fail - helper.py resolves it to `--profile <folder>`, and passes no flag at all
  for the default profile (a running Firefox reached with `--profile` can refuse). Keep the repo
  free of the user's own details (profile names, paths, keys): it is public; per-user values live
  in config.json and global/ (both gitignored). The helper's add-on ID is per copy
  (global/browser-helper/extension-id) because Mozilla ties an ID to the first account to sign it.
  `filterResponseData`'s onstop can fire BEFORE that request's onHeadersReceived: committing on
  onstop lost ~1/3 of pages (re-fetched them). Commit when both have arrived. Test plumbing with the
  mock site + throwaway headless Firefox (BiDi `webExtension.install`); real-site behaviour needs
  the user to load the helper. Snap Firefox has a private /tmp: its profile/extension test copies
  go under ~/snap/firefox/common/.
  comix.to facts (measured): reader is VIRTUALIZED (~4 `img.rpage-page__img` in the DOM at once,
  940px webp from rotating `*/hi/...` hosts) - collect pages while scrolling, sort by offset, check
  against the reader's own "n / N". Chapter list is client-drawn after load, 20/page (`npager`,
  "Showing a to b of N items"), and REOPENS ON THE LAST PAGE VIEWED; uploads per chapter from many
  groups ("Official", Tapas, scan groups). Its API FIREWALL: the list API answered 403 + an
  in-page check (`iframe /@waf/challenge`, NOT drawn while the tab is in the background) to the
  very first SCRIPTED pager click, while the request made by a page load passed - so list pages
  are opened by address (`/title/<hid>-<slug>?page=N`, the user's tip; the SSR has no list, the
  page fetches it), oldest first, 8 s apart, counting only rows seen in the list (`listed`) toward
  its "of N items" total; a /@waf/ frame counts as a check even hidden (tab brought forward).
  A Firefox remanga starts must get `--profile <folder>`: with a profile chooser set to show at
  startup, a bare `firefox URL` sits at the chooser with no profile and no helper (measured).
  Comment "Dislike 0" buttons are digits too - page
  numbers only from the pager's own box. Mock tests MUST use their own port (47699): the user's
  real helper polls 47615 and would take test jobs. Helper updates: temporary install ->
  `runtime.reload()` re-reads the xpi (verified); signed install -> new signed version offered.
  List, efficiently (comix_list.ListState): probed - `?limit=100` is ignored (API stays limit=20)
  and the reader fetches only its own chapter, so: overview = page 1 + last page, placeholders for
  numbers between; a download locates its chapter by interpolation, reading pages until its
  uploads' start and end are known (simulated 82-ch/413-upload lists: 0-2 reads per chapter, all
  chapters in order = exactly 21 reads, no re-reads). A grown list resets page bookkeeping.
  Readers reopen chapters where you left off: reader.js toTop() holds the top, scrollThrough undoes
  jumps. Page checks (comix has no checksums): comix.page_checks compares pages saved vs the reader's
  "n / N", its page bar (aria-label "Go to page N"), the site's chapter JSON the reader fetched
  (captured in background.js chapterAnswers; may be {"e":...} encrypted -> "not counted", and
  image hosts rotate, so URLs compare by path) and per-page natural sizes; any False -> nothing
  saved. Record in manifest pages.checks; workflow.page_check feeds the "192 ✓" Pages column and
  the chapter menu's Page check. Pilot tip: Choice starts unhighlighted - press down index+1 times.
  Security model (attack-tested 2026-10-15, 19/19 blocked): HMAC pairing key per copy
  (bridge.py `proof`, extension/pairing.js written by build_xpi - never commit it; lint the xpi
  with a dummy key), Host must be 127.0.0.1/localhost:<port> (DNS rebinding), nonces never reused,
  unpaired helpers get only "reload"; helper refuses a tab that left the site (incl. inside
  passChecks - it used to loop forever there), fallback fetch only http(s) image hosts the reader
  used (no private/local hosts, cookies only to the site); chapter numbers/ids/links validated in
  comix.py; pages capped at 50 Mpx before decode. Firefox itself won't draw a 900 Mpx image, so a
  bomb must be tested against `_check_image` directly. Test harnesses must stub
  session.explain_loading - otherwise a stuck test opens about:debugging in the USER's Firefox.
  addons-linter (official Node 22 in scratch; nodejs-bin ships too-old v18): description <= 250
  chars, `data_collection_permissions` required (we declare websiteContent - pages go to a program
  outside the browser) + gecko_android min 142.

## Verified 2026-09-17 (light version)

`download -c 1 --url ...` (40 pages, checksums) -> `pdf` (29.6MB, all lossless, text page ok) ->
bad reply refused with fix request -> good reply -> Kokoro (af_heart) -> mix with BGM -> h264_nvenc
render; frame checked; rerun reused clips/mix/video; next chapter's PDF carried the previous chapter's memory section; Textual
UI walked in Pilot + a real pty with mouse (projects, chapters, actions, download, Ctrl+C stop, PDF result, copy, log, settings, quit); `setup` installs Kokoro's venv and weights.

## Verified 2026-09-18 (TTS engines)

Qwen3-TTS measured on this box (RTX 3060): preset narrator 12.5s for an 8.4s line; voice design ->
one 8.8s sample; the designed voice's clone mode then narrated panels in 8.6s and 7.1s (~1.4x
realtime). So a 60-panel chapter is ~10 minutes against Kokoro's ~7 seconds. Model load is slow the
first time (~4.3GB per variant, three variants). Kokoro still narrates through the same interface -
only `config.tts.engine` decides.

## Verified 2026-09-18 (panels back)

Scratch copy of the user's manga, chapter 2.2: MAGI detection over 16 pages -> 60 panels ->
crops.json -> cut (36 snapped to gutters, 53 trimmed) -> panels_1.pdf 17.7MB, text page listing every
panel ID in reading order -> stand-in narration -> 59 Kokoro clips -> h264_nvenc render, 4m23s of
video. Marker served headlessly: index, /api/chapter (with MAGI marks), page images, outline, static
assets all 200. Earlier the same day: changed-setting reruns (720p<->1080p, background, music level),
and Chatterbox installed, verified and then removed at the user's request.

## Maintenance rule (do this, don't just read this)

Whenever a session hits a non-obvious bug, wrong assumption, or footgun and fixes/works around it -
before ending that turn - append a terse entry here (or tighten one; delete anything a code change made
stale). Symptom -> root cause -> fix/rule. Skip what's obvious from the code.
