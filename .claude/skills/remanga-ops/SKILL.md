---
name: remanga-ops
description: Fast-start reference + known-bugs log for the remanga repo (manga pages -> PDF for an LLM -> Kokoro narration -> recap video). Load before any remanga work. Keep it updated (see maintenance rule at bottom).
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
- The user wants this LIGHT. The multi-feature version (panel cropping, marker/MAGI, Gemini crop
  grid, sheets/zips, Chatterbox, DeepSeek-OCR, review/writer web UIs, pipeline editor, full-recap,
  remix, status/verify/wipe, extensions) was removed on 2026-09-17; it lives on branch
  `backup/main-2026-09-17`. Don't reintroduce any of it unasked.

## The workflow (the whole product)

```
download  -> projects/P/chapters/chapter_N/pages/          (MangaDex, checksum-verified)
pdf       -> projects/P/pdf/chapter_N/pages_1.pdf, ...     (+ empty narration.json to paste into)
[user uploads prompts/narration.md + the PDF to an LLM, pastes the one JSON reply into narration.json]
video     -> check reply -> Kokoro clip per story page -> mix with BGM -> render pages
             -> projects/P/video/chapter_N/P_chN_recap.mp4
```

Code map (`remanga/`): `workflow.py` (download / make_pdf / make_video - the CLI and menus both
call these), `cli.py`, `wizard.py` (menus), `settings.py` (voice/music/video/pdf screen),
`narration.py` (reply check, fix request, memory), `chapters.py` (ranges, sort, page naming),
`pdf/` (builder, writer, text page), `downloader/`, `audio/` (tts, mix, master, synth/kokoro),
`video/` (compose, frame_timeline, render, encoding), `config/`, `paths/`, `tool_envs/` +
`workers/` + `models/` (Kokoro's isolated venv + weights), `tui/` (menus).

## Narration reply (prompts/narration.md is the contract)

`{"chapter", "problems", "pages": [{"page", "story", "skip", "panels": [notes], "text"}], "memory"}`
- One entry per page ID, in order. Story page: `panels` = one note per panel in reading order (forces
  per-panel coverage, never read aloud) + `text`. Non-story: `skip` in credits/ad/blank/duplicate.
- `narration.load_narration` errors -> nothing synthesized, `pdf/chapter_N/fix_request.md` written.
  Warnings only: <12 words per listed panel; quotes/?/!/.../contractions (the user's narration style:
  reported speech, complete content, no quote marks, no ?/!, no contractions, one steady narrator).
- `memory` -> `memory.json` (with `last_chapter_processed`), never rolled back by re-running an
  earlier chapter; `make_pdf` puts it on the PDF text page only if it's from an EARLIER chapter.

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
- **Kokoro lang_code** is derived from the voice (a mismatch speaks with the wrong accent silently).
- **Config migration:** old config.json nested `tts.kokoro.*` is lifted to `tts.*`; old
  project.json override keys (`tts.kokoro.*`, `audio.pause_between_panels_ms`, `video.panel_*`) are
  mapped in `config/root.py:_migrate_override_key`; pydantic AliasChoices cover the renamed fields.
- The user's `tts.volume_boost_db` is 8 and speed 1.3: Kokoro clips clip at +8 dB (the run says so).
- Decimal chapters are chapters of their own: `1-5` takes 4.5, not 5.1 (`chapters.expand_chapter_selection`).
- MangaDex chapter list is cached 24h in manifest.json.

## Verified 2026-09-17 (light version)

`download -c 1 --url ...` (40 pages, checksums) -> `pdf` (29.6MB, all lossless, text page ok) ->
bad reply refused with fix request -> good reply -> Kokoro (af_heart) -> mix with BGM -> h264_nvenc
render; frame checked; rerun reused clips/mix/video; next chapter's PDF carried memory.json; menus
walked in non-tty fallback; `setup` recognizes the installed Kokoro env.

## Maintenance rule (do this, don't just read this)

Whenever a session hits a non-obvious bug, wrong assumption, or footgun and fixes/works around it -
before ending that turn - append a terse entry here (or tighten one; delete anything a code change made
stale). Symptom -> root cause -> fix/rule. Skip what's obvious from the code.
