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

## The workflow (the whole product)

```
download  -> projects/P/chapters/chapter_N/pages/          (MangaDex, checksum-verified)
mark      -> Panel Marker web UI (Flask, browser): Detect = MAGI v3, hand fixes -> crops.json
pdf       -> cuts panels/ from crops.json, then projects/P/pdf/chapter_N/panels_1.pdf, ...
             (+ empty narration.json to paste into)
[user uploads prompts/narration.md + the PDF to an LLM, pastes the one JSON reply into narration.json]
video     -> check reply -> Kokoro clip per panel -> mix with BGM -> render panels
             -> projects/P/video/chapter_N/P_chN_recap.mp4
```

Code map (`remanga/`): `workflow.py` (download / make_pdf / make_video - the CLI and menus both
call these), `cli.py`, `ui/` (full-screen menus on Textual: `app.py` styles/quit, `screens.py` projects/chapters/settings, `dialogs.py` choice/ask/result/log, `tasks.py` task screen, `widgets.py` SafeTable/SafeOptionList/TopBar), `activity.py` (progress bars: CLI Rich bar or UI task view),
`narration.py` (reply check, fix request, memory), `chapters.py` (ranges, sort, page naming),
`webui/` (the Panel Marker: Flask routes, MarkerSession/MarkerState, magi_assist + its worker,
static/), `cropper/` (crops.json -> panels/: crop_page, panel_boxes, gutter/, seams, trim, dedupe),
`pdf/` (builder, writer, text page), `downloader/`, `audio/` (tts, mix, master, synth/kokoro),
`video/` (compose, frame_timeline, render, encoding), `config/`, `paths/`, `tool_envs/` +
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
- **The marker needs a browser**; in the Textual UI it runs as a task whose step just waits.
  Headless checks that work: `MarkerSession(project, [ch])` + `webui.detection.run_detection(state,
  config.marker)` + `session.save_chapter(ch)` writes crops.json; `create_app(session,
  config.marker).run(port=…)` then GET `/`, `/api/chapter`, `/api/pages/<file>`, `/api/outline`.
- **Narration is Kokoro-82M** (fixed built-in voices, `tts.voice` a NAME from `config/kokoro_voices.py`).
  **Chatterbox voice cloning was tried on 2026-09-18 and rejected the same day** - the user found the
  clone bad and the music too loud under it - so it was removed again; that version is on the branch
  `backup/chatterbox-2026-09-18`. Don't re-propose cloning unasked.
- **Kokoro lang_code** is derived from the voice (a mismatch speaks with the wrong accent silently).
- **Config migration:** a config.json from the multi-engine version keeps Kokoro's settings in a
  `kokoro` block (lifted to `tts.*` by `config/tts.py:_from_engine_blocks`), and a Chatterbox-era one
  has a voice that is a FILE PATH plus no speed - `TTSConfig` drops what it does not know and falls
  back to defaults; old project.json override keys are mapped in `config/root.py`.
- **Sound settings (tuned 2026-09-17, measured):** speed 1.33, boost 0, music 14 LU under the voice,
  loudnorm on to -14 LUFS / -1 dBTP. Kokoro speed is NOT linear: 1.0=185 wpm, 1.3=225, 1.33=237,
  then 1.36=266 (sentence pauses start disappearing) - don't go past ~1.35 for "a little faster".
  Music gain is computed at mix time from the integrated loudness of the narration and of the exact
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
