---
name: remanga-ops
description: Fast-start reference + known-bugs log for the remanga repo (manga pages -> PDF for an LLM -> Chatterbox voice-cloned narration -> recap video). Load before any remanga work. Keep it updated (see maintenance rule at bottom).
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
- Verify by running, not by asserting (real download / PDF / Chatterbox TTS / render, pdfimages for PDFs).
- The user wants this LIGHT. The multi-feature version (panel cropping, marker/MAGI, Gemini crop
  grid, sheets/zips, Chatterbox, DeepSeek-OCR, review/writer web UIs, pipeline editor, full-recap,
  remix, status/verify/wipe, extensions) was removed on 2026-09-17; it lives on branch
  `backup/main-2026-09-17`. Don't reintroduce any of it unasked.

## The workflow (the whole product)

```
download  -> projects/P/chapters/chapter_N/pages/          (MangaDex, checksum-verified)
pdf       -> projects/P/pdf/chapter_N/pages_1.pdf, ...     (+ empty narration.json to paste into)
[user uploads prompts/narration.md + the PDF to an LLM, pastes the one JSON reply into narration.json]
video     -> check reply -> Chatterbox clip per story page -> mix with BGM -> render pages
             -> projects/P/video/chapter_N/P_chN_recap.mp4
```

Code map (`remanga/`): `workflow.py` (download / make_pdf / make_video - the CLI and menus both
call these), `cli.py`, `ui/` (full-screen menus on Textual: `app.py` styles/quit, `screens.py` projects/chapters/settings, `dialogs.py` choice/ask/result/log, `tasks.py` task screen, `widgets.py` SafeTable/SafeOptionList/TopBar), `activity.py` (progress bars: CLI Rich bar or UI task view),
`narration.py` (reply check, fix request, memory), `chapters.py` (ranges, sort, page naming),
`pdf/` (builder, writer, text page), `downloader/`, `audio/` (tts, mix, master, synth/chatterbox),
`video/` (compose, frame_timeline, render, encoding), `config/`, `paths/`, `tool_envs/` +
`workers/` + `models/` (Chatterbox's isolated venv + weights).

## Narration reply (prompts/narration.md is the contract)

One JSON block, two sections (user request - NOT two blocks):
`{"narration": {"chapter", "problems", "pages": [{"page", "story", "skip", "panels": [notes], "text"}]}, "memory": {...}}`
(`narration.read_reply` also accepts `pages`+`memory` side by side, and two separate blocks.)
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
- **Narration is Chatterbox Turbo (2026-09-18, user request: voice cloning), at its own defaults.**
  No speed change, no volume boost, no edge fades, no atempo - the model's clips go to the mix as
  they come back, only resampled (temperature 0.8, top_p 0.95, fixed seed 0, Turbo ignores
  exaggeration/cfg). Kokoro and every speed/gain setting are GONE; don't reintroduce voice
  post-processing without being asked. The music level and the -14 LUFS master stay - they are the
  finished video's balance, not voice processing.
- **The voice is a recording to clone** (`tts.voice`, default `global/voice/narrator.wav`, chosen
  from `global/voice/` in Settings): one speaker, no music, >5s or Turbo asserts; conditionals are
  built once per clip in the worker. Turbo truncates silently past ~1000 speech tokens, hence
  `chunk_max_chars = 300` in the synthesizer.
- **A `model_validator(mode="before")` also runs on ASSIGNMENT** (ConfigModel has
  `validate_assignment`): returning a shortlist of keys left the model WITHOUT its other fields, and
  saving the settings then died on `'TTSConfig' object has no attribute 'hf_repo_id'` (user hit it
  picking a voice). Keep every key in `cls.model_fields`; drop only what is wrong for this engine.
- **Changed settings must reach the finished video** (user asked where the remake option was):
  `render_video` used to accept an existing MP4 before consulting the picture fingerprint, and
  `prepare_composited_frames` reused frames per page with no regard for the video settings - so a
  new size or background changed nothing. Both are fixed (`stale_picture`, `frames_settings.json`);
  the chapter menu also has **Remake video** (narrate + mix + render with force). Verified on a
  2-page scratch chapter: size 720p<->1080p and background style recomposite and re-encode, music
  level re-mixes and re-encodes the sound only, an unchanged re-run does nothing.
- **Config migration:** Kokoro's settings (voice NAME, speed, volume_boost, its model/sample_rate)
  are dropped on load - `config/tts.py:_from_older_versions` keeps only voice/timeout and
  `_voice_is_a_recording` falls back to the default clip when `voice` is not an audio path; old
  project.json override keys are mapped in `config/root.py:_migrate_override_key`.
- **Sound settings (measured 2026-09-17):** music 14 LU under the voice, loudnorm on to -14 LUFS /
  -1 dBTP. Music gain is computed at mix time from the integrated loudness of the narration and of the exact
  looped bed the mix plays (whole-file measurement was ~1 LU off - songs' openings are quieter);
  verified 14.0 LU on all three global/bgm tracks. The tracks are mastered -9.9 to -12.7 LUFS, which
  is why the old fixed `bgm_volume_db` (removed) put them 18-20 LU under = barely audible.
- Loudnorm is two-pass linear (first pass `print_format=json`, JSON is the last {...} on stderr with
  ffmpeg summary lines AFTER it - parse to the last `}`). Single-pass dynamic loudnorm pumps music.
- The voice identity in audio_timing.json is engine + clip path + its size/mtime, so swapping OR
  editing the recording re-narrates instead of mixing two voices in one chapter.
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
bad reply refused with fix request -> good reply -> Chatterbox (clone of the recording in global/voice/) -> mix with BGM -> h264_nvenc
render; frame checked; rerun reused clips/mix/video; next chapter's PDF carried the previous chapter's memory section; Textual
UI walked in Pilot + a real pty with mouse (projects, chapters, actions, download, Ctrl+C stop, PDF result, copy, log, settings, quit); `setup` installs Chatterbox's venv (7.6GB) and weights (2.8GB).

## Verified 2026-09-18 (Chatterbox)

`setup` (venv + weights, SHA256-verified) -> full `video -c 2.2` on a scratch copy: 16 pages narrated,
mixed, h264_nvenc render, 9m43s wall, 3.9GB VRAM, ~10.5GB RAM of this 14GB box; clips ~-26.5 LUFS
before the master pass. Kokoro's venv and weights deleted (7.6GB reclaimed).

## Maintenance rule (do this, don't just read this)

Whenever a session hits a non-obvious bug, wrong assumption, or footgun and fixes/works around it -
before ending that turn - append a terse entry here (or tighten one; delete anything a code change made
stale). Symptom -> root cause -> fix/rule. Skip what's obvious from the code.
