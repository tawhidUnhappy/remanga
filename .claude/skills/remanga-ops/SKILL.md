---
name: remanga-ops
description: Fast-start reference + known-bugs log for the remanga repo (manga-to-recap-video pipeline). Load before any remanga work - saves re-deriving venv layout, TTS engine internals, project schema, and already-fixed footguns from scratch. Keep it updated (see maintenance rule at bottom).
---

# remanga fast-start

Repo: github.com/tawhidUnhappy/remanga · push straight to `main`, no PR flow.
Entry points: `./bootstrap.sh` (idempotent env setup) · `./pipeline.sh`
(interactive wizard) · `./run.sh <cli-args>` (`remanga.cli` directly).

**User habit: after making code/repo changes here, commit and push to
`origin/main` without needing to be asked separately each time** - this has
been requested after nearly every change this repo has seen. Still hold off
on pushing something clearly unfinished/untested/broken, and skip it for
pure local experiments the user didn't ask to keep.

## Layout in one pass

```
.venv, .tools/venv-{kokoro,magi,deepseek-ocr}  # 4 hermetic uv venvs, own torch/transformers pin each
remanga/                                     # package: json_io.py, ffmpeg_io.py, proc_io.py, humanize.py, pipeline.py, hardware.py, ...
  tui/                                       # arrow-key menus (select/multiselect/confirm) + non-tty fallback
  commands/{spec,selection,registry,categories,setup_rows,help_text}.py + catalog/{setup,chapter,project}.py + handlers/{setup,chapter,project,cleanup}.py
  wizard/{app,projects,chapters,params,narration,review,uploads,handoff,pipeline_edit,checks}.py
  settings/{files,fields,assets,vision,presets,engine,video,tuning,sections,summary,wizard,paths_ui}.py
  full_recap/{discovery,timeline,compiler}.py   verify/{models,panels,probe,runner,report}.py
  reset/{modes,entries,actions}.py              status/{compute,panel,badges}.py
  audio/{tts.py,mix.py,clips.py,resample.py,synth/{base,kokoro}.py,scripts/kokoro_worker.py}
  cropper/{crop*.py,gutter/{sampling,bands,refine}.py,...}
  video/{compose.py,render.py}
  models/{weights.py,scripts/download_*.py}
projects/<name>/
  project.json  manifest.json  memory.json
  chapters/chapter_N/{pages/,panels/,crops.json,narration.json}   # SOURCE only
  {audio,video,panels_zip,sheets,...}/chapter_N/                  # GENERATED (paths.py GENERATED_KINDS)
```

`narration.json` = `{"chapter","total_panels","narration":[{"panel_id","text"}]}`.
`panel_id` MUST equal the stem of a file in `panels/` (render.py globs
`panels/*.png|*.jpg`, keys off `.stem`). A chapter counts as "already
cropped" purely via `manifest.json["chapters"][N]["panels"]` existing - not
`crops.json` - so hand-imported pre-cropped panels skip the crop step for
free once that manifest entry is written.

## venvs

`uv venv` gives **no pip** → always `bin/uv pip install --python .tools/venv-X <pkg>`,
never `.tools/venv-X/bin/pip`. GPU work never touches the main env - see
`remanga/venvs.py` (`get_tool_python`). `bootstrap.sh` provisions all 4
venvs unconditionally; switching `config.json`'s `tts.engine` later never
needs a re-bootstrap, only that engine's weights lazy-fetch on first use.

## Full-manga recap: does it delete/regenerate previous audio/video?

No - `FullRecapCompiler.compile_full_manga` (`full_recap/compiler.py`) is
resumable by construction, same as every per-chapter step: each chapter's
own TTS/mix/render calls its own already-cached-and-resumable machinery
(`TTSEngine.generate_narration_audio` skips clips already on disk,
`AudioProcessor`/`VideoRenderer` have their own mtime-staleness checks), and
the whole-manga MP4 itself is only rebuilt from scratch with an explicit
`--force` (checked via `final_video.exists()` up front - already-compiled
means "done", not "reconfirm every chapter first"). `force_chapters`
(defaults to `force`) can also be set False on its own to force only the
join, not every chapter's per-chapter render - see remix.py's rejoin.
Nothing here needed adding - it already behaves the way "don't blow away
what's already built" implies.

`--rebuild everything` was added on top for the actual "start over from
scratch" case: unlike plain `--force` (which only ever re-renders/re-joins,
never re-synthesizes or re-mixes), this forces TTS + mix + render + join
for every included chapter, ignoring all of their own staleness caching.
It still never touches pages/, crops.json, or narration.json - those are
fetched/hand-authored, not regenerable from anything else remanga has.
`FullRecapCompiler._ensure_chapter_video` grew `force_tts`/`force_mix`
kwargs (separate from `force`, which kept its old render-only meaning) for
this.

The joined video's filename now carries its own start/end chapter
(`get_full_recap_video_path(project, start, end)` -> e.g.
`..._ch1-ch12_full_recap.mp4`, or `..._ch3_full_recap.mp4` for one
chapter) instead of one fixed name - so two different partial recaps, or
the same project after its chapter range changed, never collide, and
which chapters a file covers reads off the filename alone. Callers that
need to find "the" existing full-recap without already knowing its exact
range (remix.py's rejoin check, verify's report) use the new
`find_full_recap_video(project)` glob-based lookup (newest by mtime)
instead.

## Chapter downloads: chapter picker + MangaDex chapter-list caching

`download` (`remanga download -p <project> -c <chapter>`) is unchanged -
one chapter, by number, same idempotent verify-and-fill-in-what's-missing
behavior it always had (picking the same chapter twice is always safe:
stray files get swept, only actually-missing pages get fetched).

`download-chapters` (`remanga/wizard/downloads.py`,
`downloader/mangadex.py:list_chapters_with_status`/`download_chapters`) is
new - the "which chapters do I actually have" screen:
- `MangaDexResolver.list_chapters`'s feed fetch is cached per-project in
  `manifest.json["remote_chapters"]` (`paths/metadata.py:read_remote_chapter_cache`/
  `write_remote_chapter_cache`) for `CHAPTER_LIST_CACHE_TTL_SECONDS` (24h);
  the wizard's "Refetch chapter list from MangaDex" row (or `--refetch`)
  bypasses it regardless of age. `find_chapter_id`'s own feed fetch inside
  `download_chapter` is NOT covered by this cache (pre-existing, its own
  separate call) - only the picker's listing is.
- Each entry is annotated with a local-disk-only status (`_local_chapter_status`:
  "downloaded"/"partial"/"missing", no network call) so the picker always
  reflects what's actually on disk even against a cached remote listing.
- The wizard screen: pick chapters (multiselect, ctrl+a = all, pre-checked
  with everything not already "downloaded") or Refetch, then a confirm for
  "reverify and download clean" (`force=True`: wipes each selected
  chapter's `pages/` first, so even an already-verified chapter is fully
  redownloaded from scratch - the deliberate escape hatch for a chapter
  suspected corrupted or re-uploaded upstream). Non-interactive/CLI use
  passes `--select` instead (comma list and/or ranges - `1,3,7-9` - or
  `all`; ranges expand against MangaDex's own listing via
  `downloader/selection.py:parse_remote_chapter_selection`, the download-
  side counterpart to `commands/selection.py`'s local-chapters version)
  and requires it when stdin isn't a tty.
- The three flags `--select`/`--force`/`--refetch` are marked
  `Param(cli_only=True)` (new field, honored in `wizard/params.py:
  collect_params`, which leaves them at `default` unasked). Without it the
  wizard put three generic text/yes-no boxes *in front of* the picker - and
  asked about force twice, since the picker asks it again itself. Only ever
  set `cli_only` on a flag the handler genuinely re-asks in its own screen;
  otherwise the wizard silently runs with the default and the menu has no
  way to change it.
- `Param.name` for this had to avoid `"chapters"` - that name is
  special-cased in `wizard/params.py` to mean "pick from chapters this
  project already has on disk" (`select_chapters`/`discover_chapters`),
  which is backwards here (this picks from MangaDex's upstream listing,
  chapters very possibly not downloaded yet) - the flag is `--select`
  instead.

## TTS engine (`config.json` → `tts.engine`)

One engine: `kokoro` (hexgrad/Kokoro-82M, 82M params, StyleTTS 2 + iSTFTNet,
Apache-2.0 code *and* weights). IndexTTS-2.5 and Audio8 TTS were removed -
see branch `legacy/indextts-audio8` for what they did.

- **No cloning.** `tts.kokoro.voice` is a NAME from the model's own
  catalogue (`config/kokoro_voices.py`), not a path. There is no reference
  clip, no reference transcript, and no voice AssetSpec - the voice is a
  `select()` picker, not a file browser.
- **Voice grades are Kokoro's own** and the spread is wide (A down to F).
  Default `af_heart` is its only grade-A voice; the best male is `am_fenrir`
  at C+, three grades down. The picker shows grades for that reason.
- **`lang_code` is derived from the voice, never configured** (`a` American /
  `b` British). Kokoro takes it separately from the voice name and a mismatch
  makes a voice speak through the wrong accent's phonemes instead of raising.
- **Everything loads from `model_dir`, no Hub call at synth time.**
  `download_kokoro.py` pulls weights + config + *every* voice pack; the
  worker passes the voice as a `.pt` PATH, which is the one form Kokoro's
  loader accepts without reaching for `huggingface_hub`.
- **misaki (the G2P) needs spaCy's `en_core_web_sm`**, and `python -m spacy
  download` SILENTLY NO-OPS under uv - it prints "Download and installation
  successful" and installs nothing. Install the release wheel URL directly;
  bootstrap.sh does.
- Native rate 24 kHz (not 22.05k) - see the resampling note further down.

## DeepSeek-OCR-2 (`config.json` → `ocr`) - powers the Narration Writer's OCR button

`deepseek-ai/DeepSeek-OCR-2` (Apache-2.0, ~3B, ~6.8GB) downloads via
`remanga setup-models` (`config/ocr.py`,
`models/scripts/download_deepseek_ocr.py`, via
`OCREngine(config.ocr).model_manager` - `commands.py:_h_setup_models` reuses
`OCREngine`'s own `ModelManager` rather than building a second one), into
`checkpoints/deepseek_ocr_2`, with its own isolated `.tools/venv-deepseek-ocr`.

This repo drove LightOnOCR-2 for exactly one day in between; it was replaced
on preference. Its worker/downloader are in git history if wanted.

- **`transformers==4.46.3` is pinned exactly, torch is NOT.** The card pins
  both, but the pins are not equally load-bearing: pinned transformers is
  what the `trust_remote_code` modeling code is written against, whereas
  torch 2.6 is simply absent from the index this machine resolves to (cu129
  jumps <2.6 -> >2.7). Honouring the torch pin would mean installing wheels
  built for a different machine. Verified: 4.46.3 + torch 2.13.0+cu129
  resolves and loads.
- **The API is `model.infer(tokenizer, prompt=, image_file=, output_path=,
  base_size=1024, image_size=768, crop_mode=True, save_results=True)`** -
  confirmed against the v2 card. An older version of the worker guessed this
  from the v1 card and flagged itself as unverified; the guess was right
  except `image_size`, which is 768 not 640.
- **flash-attn deliberately not installed** even though the card uses it -
  long fragile CUDA extension build, and transformers falls back on its own
  attention. Same policy as every other optional kernel build.
- **`einops`/`addict`/`easydict` are undeclared imports** the remote modeling
  code needs; installing them up front saves an auto-heal round trip.
- **Pass `torch_dtype` AND `low_cpu_mem_usage=True` at load.** The model
  card's `.from_pretrained(...).cuda().to(torch.bfloat16)` casts too late:
  without a dtype, transformers stages all ~3B params in float32 in SYSTEM
  RAM (~12GB) before moving them. On this 14GB machine that invoked the
  kernel OOM killer and took the desktop down - measured, anon-rss
  11,967,492kB at the kill. The GPU was never the constraint. Asking for
  bfloat16 up front halves it; the worker also preflights MemAvailable and
  refuses below 8GB rather than letting the OOM killer choose a victim.
- **Don't cap the test with `ulimit -v`.** CUDA reserves tens of GB of
  virtual address space it never touches (30GB virtual vs 12GB resident in
  that same OOM record), so a virtual cap kills a healthy process with
  "Cannot allocate memory (os error 12)". Watch/limit RSS instead.
- **It answers a picture-only panel in Chinese**: "（图中无可辨识的文字）"
  ("no recognizable text in the image") instead of returning nothing.
  `ocr/cleanup.py` strips it. Unlike LightOnOCR it does NOT emit LaTeX, but
  it does transliterate stylized sound effects as Japanese katakana.
- Prompt presets: `"<image>\nFree OCR."` (used - text only) and
  `"<image>\n<|grounding|>Convert the document to markdown."` (layout markup,
  meaningless for a speech bubble).

**OCR output needs cleaning either way** (`ocr/cleanup.py`). Document-OCR
models treat a manga panel as a page: LightOnOCR wrapped sound effects as
LaTeX (`$\frac{2}{7}\text{Gulp...}$`) and described the artwork when a panel
was mostly picture. Measured then: **prompting does not fix this** - an
explicit "plain text only, no LaTeX, no description" instruction left the
LaTeX untouched and made descriptions worse. Cleanup keeps punctuation-only
lines on purpose - `...` is a real manga bubble.

**Hub download reliability - hard-won, keep.** `download_lighton_ocr.py` is
deliberately simple (retry `snapshot_download()` up to 3x, HF Hub only), but
it sets `HF_HUB_DISABLE_XET=1` and that is not cosmetic:

- **Xet hangs at 0 bytes in this sandbox**, repeatedly and reproducibly -
  process alive, ~2% CPU, no progress, no error, and no timeout of its own.
  It just sits there. Classic HTTP/LFS is slower but actually finishes.
- Unauthenticated Hub transfers are throttled (~1-3MB/s observed); an
  `HF_TOKEN` is a real lever, see the HF-token section above.
- The retired DeepSeek downloader ran each attempt as its own child
  subprocess so it could watch `*.incomplete` byte growth and kill a stalled
  one. That machinery is gone with it - if a big-model download ever wedges
  again, that is the pattern to bring back, not a bigger timeout.
- A ModelScope mirror is deliberately NOT used here: LightOn publishes on the
  Hub, and a mirror that may not carry the repo is a second way to fail
  slowly rather than a fallback. (A real run once saw ModelScope's mirror
  stall over an hour on one shard, with a single hash-validation retry taking
  90+ min.)

Every attempt's subprocess output is relayed live, raw bytes straight
through (`os.write(1, chunk)`), which is what makes the stall-then-fallback
actually visible instead of another silent gap - see the `-u`/buffering
note above; this script's *own* invocation needs `-u` too (`weights.py`
already passes it) or none of this relaying reaches the terminal either.

Dead end already ruled out, confirmed live: `HF_HUB_ENABLE_HF_TRANSFER=1`
(the old `hf_transfer` package/env var) - this `huggingface_hub` version
(1.30.0) has dropped it entirely, warns and silently ignores it ("Please
use `HF_XET_HIGH_PERFORMANCE` instead").

Inference itself lives in `remanga/ocr/engine.py` (`OCREngine`) +
`remanga/ocr/scripts/lighton_ocr_worker.py` - a persistent worker
subprocess mirroring `audio/synth.py`'s `_BaseWorkerSynthesizer` lifecycle
(spawn, ready-handshake, auto-heal a missing dependency, bounded-timeout
request/response, stderr draining, clean shutdown), NOT subclassed from it
(TTS-specific interface) but hand-copied with the same reasoning. GPU
preferred: `device = "cuda" if torch.cuda.is_available() else "cpu"` in the
worker, same pattern as `kokoro_worker.py`.

Wired into the Narration Writer web UI: each panel card has a
"🔎 OCR this panel" button (`app.js:runOcr()`) hitting
`POST /api/ocr/<panel_id>` (`writer_routes.py`) - fills an empty field
directly, or offers Replace/Append/Dismiss if the field already has text
(never silently overwrites). `launch_and_wait_writer` now takes an
`OCRConfig` too (`config.ocr`, threaded from `commands.py:_h_write`) and
builds one `OCREngine` per Narration Writer session, shut down explicitly
when that session ends (`writer_server.py`) rather than left idle until the
whole `remanga` process exits - a wizard session can run several commands
back to back (see the nested-menu section above), so this frees the
GPU/worker between commands instead of holding it the whole time.

`OCREngine`/worker are lazy: nothing model-related happens just from opening
the Narration Writer - the first "OCR this panel" click is what triggers
`ensure_model()` (downloading the weights first if `setup-models` was never
run) and spawns the worker; every click after that in the same session reuses
the already-loaded model.

**`expected_files=("config.json", "model.safetensors")`** is the
skip-if-present check. If the real weights ship sharded
(`model-0000X-of-0000Y.safetensors`) that check simply never short-circuits
- a redundant re-verify each `setup-models` run, not a

A best-effort optional build in `bootstrap.sh` (no longer any such build,
but the rules cost nothing to keep): nvcc must match `torch.version.cuda`
**major** (minor mismatch = warning only) → install `nvidia-cuda-nvcc` into
the target venv itself, don't rely on system CUDA. Locate its nvcc by `find`
(importable module path is unreliable) — it sits **6 levels under
`$VENV/lib`, so `-maxdepth` must be ≥6** (an off-by-one at 5 silently broke
this once). Always wrap in `(set -e; ...) && ok || warn-and-continue` -
never let an optional build abort bootstrap.

## Swapping an engine leaves stale CHECKS behind, not just stale names

The highest-yield bug class in this repo, and it has bitten three times.
Renaming strings is the easy half; the dangerous half is code that still
*tests* the old model's assumptions and now quietly answers wrong. None of
these raised anything - each looked fine and reported something false:

- **`status/panel.py` stat()'d the narrator voice as a file.** True when the
  engine cloned from a WAV. After Kokoro, `tts.kokoro.voice` is a NAME, so
  `Path("af_heart").exists()` is False and EVERY run reported
  "Reference Voice Audio: Not set / Missing" for a correctly configured
  voice.
- **`bootstrap.sh` created `assets/voices` + `assets/bgm`.** Nothing has read
  `assets/` in ages - assets live under `global/` (`GLOBAL_DIR`). A new user
  would put their music in the folder bootstrap had just made for them and
  remanga would never see it. Now creates `global/bgm`.
- **`OCRConfig` had no migration.** Field names overlap between OCR models
  (`hf_repo_id`, `model_dir`, `prompt`), so a config.json naming the retired
  model does NOT fail validation - it silently keeps pointing at it and the
  first click downloads GBs of the wrong model. Both `TTSConfig` and
  `OCRConfig` now name their retired ids/blocks explicitly and reset them.

**When retiring an engine, grep for its ASSUMPTIONS, not its name:**
`.exists()`/`Path(` on anything that used to be a path, `mkdir` of folders it
owned, overlapping config field names, and any `expected_files` tuple.

## The render guard: panels vs narration is ENFORCED, not warned about

`verify/gate.py:ensure_panels_match_narration` raises at the top of
`tts.generate_narration_audio`, `mix.mix_master_audio` and
`render.render_video`. Both directions fail: a narrated panel_id with no
image, and a cropped panel with no narration entry.

- **In the engines, not in pipeline.py's step list** - full-recap does not go
  through those steps, and it is the long unattended run where a bad chapter
  costs most.
- The check itself (`verify/panels.py`) is old and was only ever a wizard
  NOTICE. A notice shown minutes before the step it matters to is walked
  past, and the resulting video is silently defective.
- Counts matching is NOT sufficient: 2 panels + 2 narration entries naming a
  panel that isn't there is a real failure, and is covered.

## audio/ is the artifact, audio_modified/ is the cache

```
projects/{manga}/audio/chapter_N/           raw TTS clips + audio_timing.json   <- EXPENSIVE, never auto-deleted
projects/{manga}/audio_modified/chapter_N/  processed clips + master_audio.wav + .recipe.json
```

The standard build-pipeline split: a cache is what you keep when absence is
harmless and regeneration is correct; an artifact is what must be handed on
exactly. TTS output is the artifact (minutes of GPU per chapter); everything
processing turns it into is a cache (seconds).

- **One fingerprint** (`audio/recipe.py`), covering BGM/loudnorm/gaps -
  everything the mix does. There was briefly a second for a per-clip voice
  chain (warmth/presence/compression + music ducking); that stage was
  REMOVED on 2026-09-09 because it cost ~0.26 RTF per chapter for a result
  too subtle to justify. Narration is now used exactly as synthesized. The
  code is on the `audio-effects` branch if it is ever wanted back.
- `audio_modified/` therefore holds only the mixed master now, not processed
  clip copies - so it stays a cheap cache and does not duplicate `audio/`.
- `mix_fingerprint` includes the BGM file's **size+mtime**, not just its
  path. Swapping the contents of `global/bgm/track.wav` under the same name
  is a real change; a path-only key happily serves a stale master. Not a
  content hash - the file can be hundreds of MB and this runs every mix.
- **The recipe is written LAST**, after the master exists, so an interrupted
  run leaves a cache that reads as invalid rather than as complete.
- `full_recap/timeline.py` reads the same cache - that is where it pays off
  most, since the join covers every chapter at once (499 panels here).
- Wipes: `wipe_project` (everything) vs `wipe_derived_audio_and_video`
  (`DERIVED_KINDS = audio_modified, video` - keeps the narration). Exposed as
  `full-recap --rebuild outputs` against `--rebuild everything`.
- **Four rebuild depths, strictly ordered** (`reset.REBUILD_MODES`):
  `missing` (nothing) < `outputs` (audio_modified/ + video/) <
  `everything` (+ audio/) < `sources` (+ each chapter's panels/, keeping only
  pages/crops.json/narration.json). One ordered choice, not three booleans -
  the old --force/--regenerate-effects/--regenerate-all trio could express
  combinations that were redundant or contradictory.
- **panels/ is NOT source.** It is crop output, and a stale one surviving a
  re-crop is how panel_ids stop matching narration.json - which
  verify/gate.py then refuses to render from.

## BGM formats: the vendored ffmpeg must be ON PATH, and only run.sh did that

pydub reads WAV itself and shells out for everything else, finding ffmpeg
via `which`. The repo vendors ffmpeg/ffprobe in bin/ and run.sh prepends it -
so `python -m remanga.cli`, an editor run button, or importing remanga from a
script all fell through to the system's copy, and on a machine without one
every non-WAV bed failed with `FileNotFoundError: 'ffprobe'`. Measured: mp3,
m4a, ogg, opus, flac and aac all failed while WAV kept working, which reads
as "my file is broken" rather than "a binary is missing".

`remanga/bundled_bin.py` now prepends bin/ at package import, so it holds
however remanga is started. Prepending PATH rather than setting pydub's
`AudioSegment.converter` fixes pydub's decoder, pydub's separate ffprobe
call, and remanga's own ffmpeg_io in one go.

`AUDIO_EXTENSIONS` (settings/files.py) is 16 formats, each verified by
decoding a real file with NO system ffmpeg present. It includes .webm and
.mp4 on purpose: downloaded music routinely arrives in those with an
audio-only stream.

**`bgm_volume_db` is relative to the FILE's own loudness**, not absolute, so
a value tuned for one track is wrong for the next. Fixed by an ACTION, not by
runtime magic: Settings -> Audio levels offers "Measure your narration and
music, and correct the music level?", which measures both
(`audio/leveling.py`) and WRITES a plain number into config.json.

Deliberately not computed at mix time. A level the mix works out on every run
is invisible in the config, unquestionable, and un-nudgeable; a number
somebody can read and adjust is what a settings file is for.

- **Both sides are measured as ITU-R BS.1770 loudness (LUFS), not RMS**, via
  ffmpeg `ebur128`. Not pedantry - they disagree by an amount that depends on
  the material: this repo's bed reads -12.61 dBFS RMS but -9.90 LUFS, 2.7
  units louder, because BS.1770 K-weights and gates while music is
  spectrally dense where speech is not. Narration reads nearly the same
  either way. An RMS-derived gain therefore leaves the music louder than
  intended - measured, an "18 dB" RMS setting was really 15.9 LU.
- It is also the unit the pipeline already speaks: the master is normalized
  with EBU R128, so a balance set in LU survives that pass.
- `ebur128` single-pass, not `loudnorm`'s two-pass JSON: same figure within
  0.07 LU, 122ms against 3409ms.
- Narration = MEDIAN of 5 clips. Six real clips measured within 0.34 LU of
  each other, so a handful is at the noise floor of the question; median
  rather than mean so one clip that is a single quiet word cannot drag it.
  Falls back to `TYPICAL_NARRATION_LUFS = -25.7` on a fresh install.
- Whole action costs ~250ms. It is a deliberate one-shot the user navigates
  to, so correctness beats shaving milliseconds.

## Where the knobs live (`settings/sections.py` + `commands/setup_rows.py`)

Two registries, both data-driven, and adding a setting means adding a row -
never a hardcoded menu entry:

- `SECTIONS` (settings/sections.py) is the full settings menu. Each `Section`
  is title + `describe(config)` + `run(config)`. **`describe` must render the
  live value** ("1x speed · 350ms between panels", not "Narration pacing") -
  that is what makes the settings menu double as the status screen.
- `TTS_SETUP` / `BGM_SETUP` / `VIDEO_SETUP` / `CROP_SETUP`
  (commands/setup_rows.py) are per-command subsets, attached via a Command's
  `setup=`, so `tts` offers pacing and `render` offers framing without three
  menus of noise. `section_setup(key)` POINTS at a Section - it never
  re-implements one, so a row cannot describe a screen differently.

Screens themselves live in `settings/{engine,video,tuning,vision}.py` and
write through `set_field(config, "dotted.path", value)`, which saves
immediately - every screen is escapable at any point, so an answer already
given must survive backing out of the next question.

**Audited 2026-09-09: 96 config fields, 18 reachable from the UI.** The
remaining 78 are mostly internals, but check before assuming a setting is
exposed - `tuning.py` exists because a dozen genuinely user-facing ones
(narration speed, inter-panel pause, voice/music gain, MAGI on/off, the
cropper's cleanup passes, panel padding/border) were config.json-only, and a
knob you must hand-edit JSON to turn is a knob nobody turns.

**There are no tests in this repo.** "It imports" and "the code reads
correctly" prove nothing here - the voice-as-path bug above would have died
to a single assertion. Run the actual path on real project data before
reporting that anything works.

## Optional HF token for every model download (`config.json` → `system.hf_token_path`)

`remanga/hf_token.py`'s `resolve_hf_token()` is the one place this is
resolved - points at a JSON file (`{"token": "hf_..."}`), not a raw token
value, so the actual secret never has to sit in `config.json` itself.
Defaults to `global/hf_token.json`, auto-created (blank `"token"` + a
self-documenting `"_hint"` field, via `paths/global_assets.py:
ensure_hf_token_file()`) the first time any model download runs - so
there's a real file to drop a token into from the start, no manual setup
step first. A **blank** token there is the normal "nothing configured yet"
state and falls back to unauthenticated silently, no warning; a genuinely
broken file (malformed JSON, or missing the `"token"` field/wrong type)
does warn - the distinction matters, don't collapse it back into one
"anything wrong → warn" check. Pointing `hf_token_path` at a *custom* path
instead is also supported, but that one is never auto-created - missing
there is treated as a real misconfiguration (warns), not the default
unconfigured state. Either way it's a soft fallback, never a hard failure -
a bad token setup should never break a download that would work fine
unauthenticated.

Wired into every model download the same way: `ModelManager.ensure_model()`
(`models/weights.py` - covers Kokoro-82M, LightOnOCR-2, i.e.
every `Command`/synthesizer that goes through `ModelManager`) and MAGI v3's
own separate subprocess call (`webui/magi_assist.py:ensure_weights_downloaded`,
doesn't use `ModelManager`) both call `resolve_hf_token()` and append it as
an optional 4th positional CLI arg (`<model_dir> <repo_id> [hf_token]`) to
their download script - every `download_*.py` script accepts it now
(`models/scripts/download_{kokoro,lighton_ocr}.py`,
`webui/scripts/download_magi.py`), passed straight through to
`huggingface_hub.snapshot_download(..., token=hf_token)`. Deliberately HF
Hub only, never ModelScope (a different service/token scheme - passing an
HF token there wouldn't do anything). Visible to `ps`/`/proc/<pid>/cmdline`
on a shared machine for the download's duration (plain positional arg, same
as every other one these scripts take) - fine for remanga's single-user
local-machine use case.

Add a new model download later? Call `resolve_hf_token()` in whatever builds
that subprocess command and accept the same optional 4th arg in its
download script - don't invent a second token-resolution path.

## Subprocess output: use `remanga/proc_io.py`, never plain line iteration

`for line in proc.stdout` (text mode) translates `\r`→`\n`, so any process
with its own redrawing progress (ffmpeg `-stats`, tqdm downloads) floods the
console with one new line per refresh instead of overwriting in place -
verified directly (a 15s test encode: 48 real newlines vs 68 `\r` refreshes
that must collapse to one line). Use `stream_subprocess()` /
`run_ffmpeg(..., show_progress=True)` - byte-level, only newlines on real
`\n`. Never use bare `capture_output=True` for anything long-running either
(silent until exit, looks hung).

**Also always pass `-u` (unbuffered) to a spawned `python`**, not just
piping it through `stream_subprocess()` - `ModelManager.ensure_model()`
(`models/weights.py`) was missing it (worker spawns elsewhere -
kokoro_worker/lighton_ocr_worker - already had it right) and it
looked hung: `Downloading model weights...` printed, then
nothing for a long stretch, even though the download was actually
progressing fine underneath (confirmed live: the on-disk `.incomplete` file
was growing the whole time). Root cause: CPython switches stdout from
line-buffered to block-buffered the instant it isn't a real terminal - which
`subprocess.PIPE` always makes true - so tqdm's small `\r` updates sit in a
buffer instead of reaching the parent process until it happens to fill.
Fixed by adding `-u` to that one Popen call too.

One separate, *not-a-bug* thing to know about `snapshot_download()`
specifically once that fix is in: its progress reporting is file-count-level
(`Fetching N files: X%`), not byte-level - once every small file is done and
only the one big multi-GB shard is left, the counter just sits at e.g.
`14/16` with zero visible movement until that file fully lands, no matter
how unbuffered anything is. The `.incomplete` file under
`<model_dir>/.cache/huggingface/download/` is the only way to see it's
actually still moving during that stretch - don't mistake that quiet phase
for a hang and go re-diagnosing buffering again.

## Verify vs. normal runs

`remanga verify` (pipeline option 4) does real ffprobe decode checks on
`master_audio.wav`/final MP4 - the two files ffmpeg writes non-atomically
(kill mid-write can corrupt them). Normal runs only do cheap exists/size
checks there. Per-panel TTS clips can't be corrupt-but-present
(`atomic_export` = temp+rename), only missing → auto-regenerate next run.
Run `verify` after a crash/kill, not routinely.

## Importing a non-native chapter dump

1. Confirm narration-entry count == panel-image count per chapter first.
2. Raw pages → `chapters/chapter_N/pages/`; pre-cropped panels (unchanged
   filenames) → `chapters/chapter_N/panels/`.
3. Rewrite narration to remanga's schema, `panel_id` = image filename stem,
   original order preserved.
4. Write `manifest.json["chapters"][N]` = `{"pages":{"total_pages":n},
   "panels":{"total_panels":n}}` per chapter → downloader/crop steps read as
   already-done.
5. Seed `project.json`/`memory.json` from whatever summary/continuity data
   the dump has (freeform, no schema beyond "non-empty JSON").
6. Sanity-check via `remanga status --project <p> --chapter <n>` and
   `remanga.paths.list_projects()` before running anything expensive.

## Pipeline step registry (`remanga/pipeline.py`)

The wizard's step order (download→mark→crop→package→narration→review→tts→mix→render)
lives in `STEP_REGISTRY`, not hardcoded per-project. Each project can have
`projects/<name>/pipeline.json` = `{"steps": ["download", "mark", ...]}`;
missing/empty falls back to `DEFAULT_STEPS` (that exact order) unchanged.
Edit it via the wizard's "Pipeline" menu row (an ordered checklist -
check order is run order), or `remanga run -p <p> -c <c>`
(uses pipeline.json) / `remanga run -p <p> -c <c> -s crop,narration` (one-off
explicit subset, doesn't touch pipeline.json). Every existing single-step
subcommand (`download`/`mark`/`crop`/`package`/`write`/`review`/`tts`/`mix`/
`render`) still works unchanged - `run` just wraps the same underlying calls.

`crop` does NOT package. It cuts panels and stops; building sheets/zips/PDFs
is `package` (the command, and the pipeline step of the same name), one
implementation in `remanga/packaging.py:package_chapter` shared by both. It
used to happen automatically on every crop - including a top-up on the
resume path - which meant a ~30MB zip rebuilt by a command asked only to cut
panels. The `reading_direction` guard moved with it: cropping never used
that field, only the bundles' chapter_info.json does.

## Wizard menu is registry-driven, no hardcoded "modes"

`remanga/commands/registry.py`'s `COMMAND_REGISTRY` is the single source of
truth for every remanga command - both `cli.py`'s argparse subcommands and
the wizard's menus are built from it. The wizard has no curated combo modes:
main menu = each `Category` (`CATEGORIES` in that module, ordered and
described) via `commands_by_category()`, plus a "Pipeline" row (the step
editor) and "Switch project"; picking a category opens its command submenu,
which stays open after running one (chaining mark → crop → write is picking
them one after another). Adding a command is one `Command` entry with a
`category`; nothing under `remanga/wizard/` changes. Adding a *category*
means giving a command a new category string - an unknown one still gets its
own group rather than vanishing.

A `choice` param can carry `choice_help`/`choice_detail` dicts (see
`commands/spec.py`), filled from whichever module owns those choices
(`reset.RESTART_MODES`, `narration.NARRATION_FILE_MODES`) - that's what
makes the wizard's menu explain each option without any screen re-describing
behavior that lives elsewhere.

Command parameters are prompted from their own `Param` specs
(`remanga/wizard/params.py`), so new flags become wizard questions for free.
The `_SPECIAL` table there overrides the generic prompt for the parameters
whose answer is discoverable: `chapter`/`chapters` (this project's chapters +
status), `keep` (what the chapter actually has on disk, as a checklist),
`formats` (packaging checklist), `steps` (ordered checklist of
`STEP_REGISTRY`), and the ones it deliberately does NOT ask at all (the
`_not_asked` factory: state what's configured, return None) - `url` (once
project.json has a manga source) and `engine`/`voice`/`bgm`, all three set
once and kept for months, so the CLI flags cover the rare one-off and the
settings screens cover a permanent change. Rule when adding a parameter: if
remanga can find the answer, don't ask for it - and if the answer changes
about once a year, state it instead of asking.

`tts --engine` is a CLI-only per-run override - it deep-copies TTSConfig and
sets `engine` there, never writing config.json: "try the other model on this
chapter" must not silently redefine every later run.
`settings/files.py:discover_files` scopes its search to the asset's own
folder (`global/voice/`, `global/bgm/`) and widens to all of `global/` only
when that folder turns up nothing - a voice picker listing the BGM track is
noise, since neither is a plausible answer to the other's question.

## Interactive terminal: `remanga/tui/`

All interactive input goes through `remanga.tui` - `select` (arrow keys,
type-to-filter, Esc backs out), `multiselect` (space toggles; `ordered=True`
makes check order = run order, used by the pipeline editor), `confirm`, and
`ask_text`/`ask_number`/`ask_path`. Menus render transiently via Rich `Live`
and leave one `✓ question  answer` line behind. Build screens as `Choice`
lists (label/hint/detail/badge, `checked` pre-selected from current state) -
never a hand-rolled `console.print` loop, and never Rich markup in a label
(labels carry filenames; `frame.py` builds `Text` so `[` can't be parsed as a
tag). Cancellation is the `CANCEL` sentinel (`is_cancel()`), never `None` -
`None` is a real answer for optional params.

Every menu ends with an **Exit remanga** row, and **ctrl+q** does the same
from any prompt at any depth: both raise `PromptExit`, which is a
*BaseException* on purpose - every `except Exception` in between (the
wizard's own "command failed, back to the menu" guard included) would
otherwise swallow the user's request to leave. `cli.main` catches it. Note
`tui/keys.py` clears IXON/IXOFF: with flow control on, the tty eats ctrl+q
(XON) and it never reaches the program.

Filtering ranks label matches above hint matches (typing "package" + Enter
must run `package`, not `crop`, whose description mentions the word), and
Space types a space in single-select menus but toggles in checklists.

Non-tty stdin (piped, CI, an editor output pane) auto-falls back to the old
numbered prompts (`tui/fallback.py`, `0` = back/quit at every level, Exit as
its own numbered row) - `keys.is_interactive()` decides, so both paths stay
live.

`tui/keys.py` owns the only raw-tty code: cbreak with ISIG off (so Ctrl+C
arrives as `\x03` and `cli.main` catches `KeyboardInterrupt` with the
terminal already restored), OPOST left ON (turning it off, as `tty.setraw`
does, staircases Rich output), and reads via `os.read` on the raw fd - NOT
`sys.stdin.read`, whose buffering swallows the rest of an escape sequence and
makes every arrow key read as a bare Esc (i.e. Down silently backs out).
Mouse input is actively neutralized: it disables mouse reporting (`?1000/
?1002/?1003/?1006/?1015`) on entry and fully consumes-and-ignores X10
(`ESC[M`+3 raw bytes) and SGR (`ESC[<…M/m`) reports plus bracketed pastes.
That's the "clicking the scroll wheel crashes the terminal" bug: a mouse
report's raw coordinate bytes land in the input stream as fake keystrokes
(one of them being `\r` = Enter, or `\x03` = Ctrl+C), and X11 middle-click
additionally pastes the PRIMARY selection - newlines included - straight
into stdin. Never parse escape sequences outside this module.

`select_chapter` (`remanga/wizard/chapters.py`) is a pure picker - it used to
also call `offer_chapter_restart` (a "resume or pick a restart tier" gate) on
every chapter selection, which fired for *any* command needing a chapter,
including single-tool ones like `write`. That capability is just the
standalone `restart` command (`--mode hard/marks_only/remark/soft`, presets
defined once in `remanga/reset/modes.py` with their labels and what each
keeps), reachable from the menu like everything else.

## New commands/checks added post-writeup (keep COMMAND_REGISTRY the source of truth, this is just a pointer)

- `narration-init` (Chapter Production): creates narration.json either as a
  full per-panel template or as a genuinely empty (0-byte) file. The
  document shape lives in `remanga/narration.py:narration_document` and
  WriterState builds through it too, so a hand-started template and a
  Writer-produced file are identical by construction - don't hand-write that
  dict anywhere else. Refuses to clobber real content without `--force`; a
  blank file is not content (`has_real_json_content`), so blank → template
  needs no flag.
- `normalize-narration` (Chapter Production): rewrites narration.json into
  TTS-safe text. Rules live in `remanga/narration/normalize.py` as named
  `Rule` objects applied in order, and `normalize_text` reports which fired -
  that report is what the command previews. Two invariants when touching it:
  `?`, `!` and `...` are never removed (only de-duplicated) because the
  engines infer emotion from them with no emo_vector sent, and the final
  `charset` pass is a WHITELIST (`ALLOWED_PUNCTUATION`) - a missed exotic
  character is a glitch mid-chapter, which is worse than dropping it. Order
  matters: `charset` runs before `punctuation` so the gap a removed emoji
  leaves gets cleaned up rather than frozen in ("mage , meets"). Must stay
  idempotent - the command's second run has to report "already TTS-safe".
  `normalize.py` holds the safety rules; `delivery.py` holds the ones that
  change how a line is *performed* (single->double speech quotes, capitalized
  speech, Mr.->Mister, A rank->A-rank) and runs last, on already-clean text.
  The quote conversion is safe because an apostrophe is the only single quote
  with letters on BOTH sides - that one distinction is what makes it
  automatable; don't replace it with a positional guess. `advisories.py` is
  the deliberate other half: problems only a rewrite fixes (empty lines,
  Rule 4's 26-word ceiling, narration duplicated across panels, and >35% of
  lines opening with an "-ing" participle - measured at 46% on a real chapter
  and audible as a drone). Those are REPORTED on every run, including the run
  where nothing needed changing, and never auto-rewritten. When a new
  narration problem turns up that has no mechanical answer, it belongs there
  plus a line in prompts/narration.md - not as a rule that guesses.
- `package` (Chapter Production): (re)builds sheets/zips/pdf from an
  already-cropped chapter's panels/, standalone from `crop` - previously
  only happened as a side effect of crop's resume-check top-up.
- Per-project choices (`settings/project_prefs.py`, stored in that project's
  `project.json`): `package_formats` and `wipe_keep`. Precedence everywhere
  is explicit answer > project memory > `config.json` - a project-scoped
  choice never rewrites the global defaults. `package --formats a,b` and the
  wizard's checklist both write it; `crop` reads it too (via
  `cropper_config_for`, which returns a *copy* of CropperConfig - never
  mutate the shared one), so a project's chosen upload formats apply to
  every chapter without re-asking.
- `wipe` (Chapter Production, single chapter) / `wipe-chapters`
  (Project-wide, comma list and/or 'N-M' ranges): fully dynamic counterpart
  to `restart`'s 3 fixed modes - keeps whatever `--keep` names, default
  (unset) keeps `pages,crops.json,narration.json` (`DEFAULT_WIPE_KEEP` in
  `commands/selection.py`), `--keep none` for an absolute full wipe. Always
  re-verifies/re-fetches downloads afterward regardless of what was kept.
- Every model downloader (`models/scripts/download_{kokoro,
  lighton_ocr}.py`, `webui/scripts/download_magi.py`) now verifies each
  LFS file's sha256 against the Hub's own recorded hash after downloading
  (`models/scripts/_hash_verify.py`) - `snapshot_download()`'s own check is
  size-only, never a real hash compare. One retry (delete+re-fetch just the
  bad file(s)) before hard-failing.
- Wizard: skips re-prompting `download`'s manga URL/title once one's saved
  in project.json (was asking every time even though download_chapter
  already falls back to the saved source on `None`). Also now auto-runs
  `verify.project_panel_narration_mismatches()` the instant a project is
  selected (cheap - dir listing + one JSON read, no ffprobe) and warns if
  any chapter's panels/ and narration.json panel_id sets have drifted apart
  (post-recrop/post-rewrite skew) - same check feeds the `verify` command
  too, one implementation for both.

## Panel marker is a SESSION now (one tab, many chapters)

`webui/marker_session.py:MarkerSession` owns the chapter list + cursor and one
`MarkerState` per chapter (built lazily - never open every chapter's images up
front). `launch_and_wait_all(project, [chapters], config)` is the entry point;
`launch_and_wait(project, chapter, config)` is a one-item list, so `mark`, the
pipeline's mark step and a "remark" restart are unchanged. `POST /api/finish`
saves + advances (`{"end": true}` stops early); `POST /api/goto {"index": n}`
jumps and saves the chapter being left. Frontend split: `page-nav.js` = pages,
`chapter-nav.js` = chapters/save/init, one-way import (page-nav must never
import chapter-nav). Command: `mark-all` (Project-wide).

`view-marks` is the same session with `MarkerSession(read_only=True)`: the
server 403s `/api/marks` and `/api/detect`, `save_current()` no-ops, and
`start_detection()` returns early (MAGI WRITES marks - a viewer that runs it
fills up with boxes nobody saved). The browser hides the editing chrome, and
`flushSave()` returns early - without that, every chapter change in a viewer
POSTs marks and logs a 403. Sidebar has two panes (`sidebar.js`): the page's
panel list, and `outline.js`'s session tree (chapter > page > panel, lazily
built - only expanded branches exist in the DOM). Outline counts come from
live client state for the chapter on screen and from `crops.json` for the
rest, which is why each chapter reports `loaded`.

MAGI detection is a QUEUE on the session, not a call per request
(`MarkerSession._jobs` + one worker thread; `detection.run_detection` is just
the unit of work). `POST /api/detect` takes `scope`: page / chapter / range
(`from`+`to` as chapter NUMBERS, reversed accepted) / all. `POST /api/settings`
writes `auto_detect_scope`, `auto_detect_all` (queue the whole session and keep
going in the background) and `auto_save` into config.json via
`settings_store.persist_marker_settings` - config.json's marker section is
merged, never rewritten. A chapter detected in the background is saved as soon
as its pass ends (auto_save on) so a closed tab costs nothing computed; with
auto_save off the session tracks `dirty` and the browser offers to write them
before closing. `state_for(chapter)` (never `current`) is what background work
uses - the cursor moves while it runs.

Footguns hit while building it, all still live:
- **Page filenames repeat across chapters** (every chapter has a `page_001`).
  `magi.js:pollDetectStatus` merges server marks by filename, so a poll that
  was in flight during a chapter switch writes the OLD chapter's marks into
  the new chapter's cache. `/api/detect/status` returns `chapter` for exactly
  this; the poller drops any response that isn't the chapter on screen.
- **`state.pageLoaded = false` before `loadPage(0)` on a chapter change**, or
  loadPage's "flush the page we're leaving" posts the previous chapter's marks
  into the new chapter's state.
- **`session.goto(i, save=False)` from /api/finish** - it already saved; the
  default `save=True` would write that crops.json twice and report it twice.
- **MAGI must start once per chapter, on arrival** (`detection.start_once`,
  guarded by `MarkerState.detect_started`) - every navigation back would
  otherwise spawn another worker and reload the model.
- A route that returns `{"queued": x, **detection_status()}` has TWO "queued"
  keys and the spread wins - the response silently reported the live queue
  instead of what the request added. Named `accepted` vs `queued` now; watch
  for the same collision whenever spreading a status dict over literal keys.
- Testing `/api/settings` WRITES THE REAL config.json (that is its job).
  Snapshot and restore the `marker` section around any such test, or the
  user's file is left holding test values.
- MAGI can be stubbed for tests: `remanga.webui.magi_assist.detect_panels_for_pages`
  is imported inside `run_detection` at call time, so patching the module
  attribute before starting the server is enough - the whole queue, every
  scope and the background saving are testable with no GPU.
- CSS: `.chapter-nav`/`.ghost-btn` set `display:flex`, which beats the UA's
  `[hidden]{display:none}` - each needs its own explicit `[hidden]` rule or
  `el.hidden = true` does nothing.

**How to actually TEST the web UIs from here** (worked out 2026-09-10;
supersedes an earlier "there is no JS runtime" note):

```bash
uv venv /tmp/jscheck && uv pip install --python /tmp/jscheck/bin/python nodejs-wheel-binaries
NODE=/tmp/jscheck/lib/python3.12/site-packages/nodejs_wheel/bin/node   # v24
$NODE --check remanga/webui/static/js/*.js                            # ESM-aware
```

Better than a syntax check: **boot the real frontend under node against a real
running Flask session.** Stub `document`/`window`/`navigator`/`CSS` with plain
objects whose elements accept anything, point `globalThis.fetch` at the
server's base URL, `await import("main.js")`, and every module's top-level
code + `init()` + first render runs for real. Store handlers in
`addEventListener` and you can dispatch clicks and drive the UI (this is how
the outline tree's expand/navigate was verified). Gotchas: `navigator` is
getter-only in node (`Object.defineProperty`), the fake `<img>` must fire
`onload` when `.src` is set or `loadPage()` awaits forever, and node won't
exit on its own (`setInterval` poll) - end with `process.exit(0)`.

Dead ends: snap firefox `--headless --screenshot` hangs (both `PATH` and
`=PATH` forms, 100s+). esprima-python parses only to ES2017 so it false-fails
on this repo's `?.` and `catch {}` - not a real signal.

Also cheap and worth keeping: every `import {x} from "./y.js"` must resolve to
a real export, and every `getElementById` in dom.js must match an id in
index.html (a miss is a module-scope TypeError that kills the whole UI).

**`pkill -f <pattern>` kills the shell running the command** when the pattern
appears in that command's own text - the tool call dies with exit 144 and the
rest of the command never runs. Use a pattern that doesn't literally match
itself: `pkill -f "serve2[.]py"`.

## ffmpeg output: `-progress`, never raw stats

`ffmpeg_io.run_ffmpeg(show_progress=True)` injects `-hide_banner -nostats
-loglevel error -progress pipe:1` and renders a Rich bar from the key=value
stream, with `total_seconds` passed by the caller (the encode's length is
always already known - the frame timeline for a render, the master audio's
own length for a loudnorm pass). Never let ffmpeg write to the terminal
itself: at default loglevel it prints a 40-line ./configure dump on every
start, and its own status line assumes a terminal that honors `\r` - in
anything that doesn't, a long encode lands thousands of near-identical
`frame=... fps=...` lines in the scrollback. `proc_io.stream_subprocess` is
still the right tool for the model downloaders (tqdm bars, no `-progress`
equivalent), just not for ffmpeg.

## Hardware detection / cross-platform install (`remanga/hardware.py`)

One stdlib-only module answers "what is this machine and what should be
installed on it"; `bootstrap.sh` evals it (`--shell`) before any venv
exists, and the app imports it, so installer and app can never disagree.
`./run.sh hardware` prints what it decided. Footguns found the hard way:

- **PyTorch wheel indexes do NOT all carry the same torch versions.** The
  selection rule is "newest index the driver can run that ALSO has the torch
  this project targets" (`_CUDA_INDEX_BY_DRIVER`: 580+ → cu129, 525+/528+win
  → cu128, older → cpu + a warning) - never "newest CUDA index" and never
  "whatever the driver supports".
- **That target is `2.8`, and it is now VESTIGIAL.** It existed because
  IndexTTS-2.5 pinned `torch==2.8.*`. Nothing pins it any more: measured,
  venv-kokoro resolves 2.13, venv-magi 2.13, venv-deepseek-ocr 2.14. The rule
  is therefore conservative rather than wrong - it needlessly excludes cu130
  - and is safe to revisit, but do it deliberately, with all three venvs
  re-resolved, not as a drive-by.
- **A package's own `[tool.uv.sources]` silently overrides `--torch-backend`.** Hit with `git+index-tts` (since removed): that
  package's own pyproject declares a `pytorch-cuda` index pinned to cu128
  via `[tool.uv.sources]`, and it wins: `--torch-backend cpu` alone gives
  `2.8.0+cpu`, but the same flag *alongside the git package* gives
  `2.8.0+cu128` - i.e. CUDA wheels on CPU-only and AMD machines. Fix is the
  re-pin step after that install (`torch==2.8.* torchaudio==2.8.*` with the
  backend flag). Verified by dry-run both ways; don't drop that step.
- Pass `--torch-backend` to **every** ML install, not just the first: a
  later install re-resolves torch as a dependency and will happily replace
  a machine-matched build with the plain-PyPI one. Before this, the four
  venvs on one box had drifted to cu128/cu130/cu130/cu130.
- `bootstrap.sh` deliberately has **no `set -e`** - `die` for critical
  steps, `try_step` for optional ones, warnings summarized at the end. An
  optional CUDA-kernel build must never abort a run that already fetched
  several GB.
- ffmpeg: BtbN publishes `linux64`/`linuxarm64`/`win64`/`winarm64` only -
  macOS has no static build and uses the system one, which is normal there,
  not a fallback. Windows assets are `.zip` (needs `unzip`), others
  `.tar.xz`.

## GPU/ffmpeg

`system.gpu_codec` defaults to **`"auto"`** now, resolved per-machine by
`SystemConfig.resolve_gpu_codec()` → `hardware.detect_cached().video_encoder`
(nvenc / videotoolbox / vaapi / libx264). An explicit codec string still
wins. The old bare `"h264_nvenc"` default was simply wrong on any non-NVIDIA
machine. Note the encoder is chosen from GPU *vendor presence*, not from the
torch backend - an old-driver NVIDIA box gets cpu torch but still gets
`h264_nvenc`, because NVENC is separate silicon and `_resolve_gpu_ffmpeg()`
probes it for real anyway.

Bundled `bin/ffmpeg` (pinned BtbN build) has working `h264_nvenc` on this
box (RTX 3060) - confirmed by direct probe (`ffmpeg -f lavfi -i
nullsrc=s=256x256:d=0.1 -c:v h264_nvenc -f null -`). `_resolve_gpu_ffmpeg()`
already falls back bundled→system-ffmpeg→CPU correctly. Before "fixing" GPU
selection, probe directly first - a silent CPU-only phase (pydub audio
concat, PIL frame compositing) running *before* the GPU encode is normal,
not a bug; don't confuse the two.

"The CPU is working harder than the GPU during render" is also normal and
NOT a misconfiguration. Measured mid-encode on this box: `utilization.gpu`
8%, `utilization.encoder` **100%**, ffmpeg ~295% CPU (3 of 12 cores).
nvidia-smi's headline GPU-Util reports SM (CUDA core) occupancy, and NVENC
is separate fixed-function silicon that it doesn't count - so a saturated
encoder reads as an idle GPU. Query `utilization.encoder` before concluding
anything - Ubuntu's default Resources app (net.nokyan.Resources, NVML-backed)
shows the same split as a "Video Encoder" figure on its GPU tab, and as an
optional per-process column. The CPU side is the unavoidable prep: PNG decode, rgb24→yuv420p,
duplicating each panel's frame out to fps, AAC, muxing.

## Audio quality: three post-synthesis bugs, all fixed - don't reintroduce

The engine's raw output was fine; everything after it degraded the audio.
Symptom was "words run together, metallic/glitchy".

- **Never resample with pydub** (`AudioSegment.set_frame_rate`) - it's
  `audioop.ratecv`, linear interpolation with no anti-imaging filter.
  Converting a TTS engine's native 22.05k to the project's 44.1k mirrored the
  signal around the old Nyquist: measured on a fresh clip, the 11.5-16 kHz
  image came back **louder than the real 8-11 kHz speech**. Use
  `audio/resample.py:load_audio` (ffmpeg soxr) - puts it 47 dB down.
- **Edge fades must be clamped to each clip's own silence**
  (`audio/clips.py:apply_edge_fades`). A flat `edge_fade_ms` ramped the
  opening consonant, because the TTS engine returns audio trimmed tight to the
  speech (measured lead-in ranged 10ms-180ms across clips; a flat 35ms left
  the first 35ms of 52/60 panels ~36x quieter than the speech after it).
  `edge_fade_ms` is a ceiling, with a 6ms de-click floor.
- **`audio.pause_between_panels_ms` must not be 0** (now 350). Panels were
  butt-joined; with a median 35ms lead-in and 81ms tail that left ~115ms
  between one sentence's last phoneme and the next's, where a narrator
  takes 300-600ms. That was the run-together, and it was the *assembly*,
  not the synthesis.
- A kwarg an ML library forwards into HF `generate()` fails with
  **ValueError, not TypeError**, so an `except TypeError` guard will not
  catch a misspelled generation kwarg. Match extra kwargs against the real
  signature before passing them.

## Maintenance rule (do this, don't just read this)

Whenever a session on this repo hits a non-obvious bug, wrong assumption, or
footgun and fixes/works around it — **before ending that turn**, append a
terse entry here (or tighten an existing one; delete anything a code change
made stale). One or two lines: symptom → root cause → fix/rule. Skip
anything already obvious from reading the code. This file is only worth
loading if it stays a shortcut past mistakes already made, not a duplicate
of the source.
