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
`audio/` (tts, mix, master, clips, manifest, synth/ per engine),
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
    11,673 characters. `MAX_BATCH_SECONDS` is now **240s** and the settings offer 2 and 4 minutes,
    not 9.
    - `audio/batched.py:_collapsed` catches it **before transcription**, on two signals: a take at
      the token ceiling, or one more than `RUNAWAY_FACTOR` (1.4) longer than its own estimate. The
      estimate is good enough for that - a healthy take asked for ~205s and came back 203s.
    - It then **splits at a page boundary and retries**, up to `MAX_SPLIT_DEPTH` (3). A collapse is
      the model losing the thread on a long text, so the answer is a shorter text.
    - **In-context cloning helps a lot and does NOT fix it (tested 2026-09-21).** The clone used to
      run in `x_vector_only_mode` because `designed_text` was empty. Whisper now reads the reference
      recording once and caches it beside the file (`audio/reference_text.py`,
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
  `audio/reference_text.py` now builds clip and transcript as ONE pair (cached as
  `{stem}.reference.json` + `.reference.wav`), cutting both at the last sentence that finishes
  inside the limit; `synth/qwen.py:reference_pair` is the only way to get them, so a transcript can
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
  (both generate at 1.4x real time). So `MAX_BATCH_SECONDS` is 60 and `batch_target_minutes`
  defaults to 1. **A longer reference is not the lever**: 30s instead of 15 blew the 670s timeout on
  a take the 15s reference finished in 325s. The tooling for this lives in the scratchpad
  (voiceprint.py: MFCC means over voiced frames + median F0, calibrated before use) - rebuild it the
  same way if this comes back, and calibrate before trusting any number.
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
