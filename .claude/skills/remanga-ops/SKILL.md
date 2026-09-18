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
styles/quit, `screens/` = `projects` `chapters` (table + menu) `chapter_work` (what the menu does,
a mixin) `settings` `common`, `dialogs.py`, `tasks.py`, `widgets.py`, `voice_settings.py`),
`activity.py` (progress bars: CLI Rich bar or UI task view),
`narration.py` (reply check, fix request, memory), `chapters.py` (ranges, sort, page naming),
`webui/` (the Panel Marker: Flask routes, MarkerSession/MarkerState, magi_assist + its worker,
static/), `cropper/` (crops.json -> panels/: crop_page, panel_boxes, gutter/, seams, trim, dedupe),
`pdf/` (`encode` one panel -> a PDF page, `pack` panels -> parts under the cap, `builder` wires
them, `writer` the PDF itself, `manifest_info` the text page), `downloader/`,
`audio/` (tts, mix, master, clips, synth/ per engine),
`video/` (`canvas` one panel on one frame, `quality` is this size enough, `frames` the frame cache,
`compose` re-exports those three, `frame_timeline`, `render`, `encoding`), `config/`, `paths/`, `tool_envs/` +
`workers/` + `models/` (Kokoro's and MAGI's isolated venvs + weights).

## Narration reply (prompts/narration.md is the contract)

One JSON block, two sections (user request - NOT two blocks):
`{"narration": {"chapter", "problems", "panels": [{"panel", "skip", "text"}]}, "memory": {...}}`
one entry per PANEL id (`2.2_004_02` = chapter_page_panel), in reading order.
(`narration.read_reply` also accepts `panels`+`memory` side by side, and two separate blocks.)
- One entry per page ID, in order. Story page: `panels` = one note per panel in reading order (forces
  per-panel coverage, never read aloud) + `text`. Non-story: `skip` in credits/ad/blank/duplicate.
- `narration.load_narration` errors -> nothing synthesized, `pdf/chapter_N/fix_request.md` written.
  Warnings only: <12 words per listed panel; quotes/?/!/.../contractions (the user's narration style:
  reported speech, complete content, no quote marks, no ?/!, no contractions, one steady narrator).
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
- **Resampling:** clips go 24 kHz -> 44.1 kHz through `audio/resample.load_audio` (ffmpeg), never
  pydub's `set_frame_rate` (folds imaging noise above 12 kHz).
- **Frame cuts** snap into the pause between pages (`video/frame_timeline.py`) so a picture changes
  just before its narration starts.
- **Panels, not pages (2026-09-18, user request):** the video plays one panel per clip.
  `workflow.mark` opens the marker (blocking until the browser saves), `workflow.cut_panels` recuts
  whenever crops.json is newer than panels/, and `make_pdf` calls it first. crops.json and the pasted
  narration are the only things nothing can rebuild - Reset deletes panels/ but keeps crops.json.
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
  (`pdf/writer.py:build_pdf(canvas=...)` + `_text_layout`, canvas passed from `builder.py`) - panels
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
  fit scale, and suggests the smallest offered size that fits. It fires twice on purpose: in the
  pre-check (the result screen / CLI, counting only NARRATED panels) and while compositing. Measured
  on a real chapter: 8 of 60 panels shrink at 1080p, 2 at 1440p, none at 4K.
- **Video is 4K (3840x2160) since 2026-09-18 - the user asked for best quality** after the panel
  warning showed 8 of 59 panels shrinking at 1080p. Measured on a real 4m23s chapter: frames
  composite in 3s, the NVENC encode takes 1m12s, the MP4 is 42MB (still panels compress hard; the
  encoder is CQ 18 VBR, not bitrate-capped) and a rendered frame is 50dB PSNR against its source.
  Frame cache is ~126MB a chapter. Don't trade this back for speed unasked.
- **TTS engines are plug-ins (user request 2026-09-18: "make this modulous").** Adding one is four
  pieces and nothing else: a `*Config` block in `config/tts.py` (with `voice_label`, `voice_detail`,
  `identity()`), a `TTSEngineSpec` in `config/tts_engines.py`, a Synthesizer in `audio/synth/` +
  worker in `audio/scripts/` registered in `SYNTHESIZERS`, and a `ToolSpec` in `tool_envs/catalog.py`.
  Settings rows come from `ui/voice_settings.py:ENGINE_ROWS` (a `Row` is label/value/change), so the
  screen itself never changes. Nothing outside asks which engine is running: `audio/tts.py` calls
  `synth.synthesize(text, output_wav)` and `config.tts.identity()`.
- **Engines today:** `kokoro` (default, fixed voices, a 60-panel chapter in seconds) and `qwen`
  (Qwen3-TTS 1.7B, Apache 2.0, `.tools/venv-qwen-tts`): preset narrator + `instruct`, or a voice
  DESIGNED from a description. Designed = VoiceDesign model makes one sample once
  (`synth/qwen.py:design_voice`, a one-shot run, not the worker), then the Base model clones THAT
  sample for every panel - re-describing per panel is what makes a designed voice drift. Three
  variants, ~4.3GB each, downloaded only for the way actually used.
- **Kokoro's voice is a NAME** from `config/kokoro_voices.py` (`tts.kokoro.voice`).
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
- Loudnorm is two-pass linear (first pass `print_format=json`, JSON is the last {...} on stderr with
  ffmpeg summary lines AFTER it - parse to the last `}`). Single-pass dynamic loudnorm pumps music.
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
  async KeyboardInterrupt into the thread + SIGTERM to child processes (`pgrep -P`).
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
