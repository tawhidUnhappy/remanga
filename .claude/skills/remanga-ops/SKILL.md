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
.venv, .tools/venv-{indextts,audio8,magi}   # 4 hermetic uv venvs, own torch/transformers pin each
remanga/                                     # package: paths.py, config.py, ffmpeg_io.py, proc_io.py, full_recap.py, verify.py, ...
  audio/{tts.py,mix.py,synth.py,scripts/*_worker.py}
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

## TTS engines (`config.json` → `tts.engine`)

| | `indextts-2.5` | `audio8-tts-0.1b` |
|---|---|---|
| cloning | audio-only zero-shot | needs `tts.audio8.reference_text` = accurate transcript of the ref clip, or synth raises |
| arch | — | Falcon-H1 (Mamba/state-space), `trust_remote_code=True` |
| speed | — | needs fused `mamba-ssm`/`causal-conv1d` kernels or silently falls back to naive per-token loop (~2-3x slower) |

Audio8 worker (`remanga/audio/scripts/audio8_worker.py`) fixed bugs, don't
reintroduce:
- `model.generate(..., return_dict_in_generate=True)` required, else you get
  a bare Tensor with no `.codes`.
- sample rate = `model.config.codec_sample_rate` (44100), NOT `sampling_rate`
  (doesn't exist on this model - was silently defaulting instead of erroring).
- `download_audio8.py` has no ModelScope mirror + needs a manual retry loop
  (`snapshot_download`'s `max_retries` kwarg doesn't exist in this
  `huggingface_hub` version).

## DeepSeek-OCR-2 (`config.json` → `ocr`) - powers the Narration Writer's OCR button

`deepseek-ai/DeepSeek-OCR-2` weights download via `remanga setup-models`
(`config/ocr.py`, `models/scripts/download_deepseek_ocr.py`, via
`OCREngine(config.ocr).model_manager` - `commands.py:_h_setup_models` reuses
`OCREngine`'s own `ModelManager` rather than building a second one), into
`checkpoints/deepseek_ocr_2`, with its own isolated `.tools/venv-deepseek-ocr`
(provisioned in `bootstrap.sh` with a real torch/transformers inference
stack, not download-only). Real repo layout (confirmed by an actual run):
17 files, the weights themselves a single ~6.8GB
`model-00001-of-000001.safetensors` (not sharded) - `ModelManager`'s
`expected_files` uses that exact name now.

**HF Hub first, hf_transfer enabled, ModelScope fallback** - the opposite
priority from `download_indextts.py` (ModelScope first). Flipped because a
real run against this exact repo saw ModelScope's mirror stall over an hour
on that one big shard (repeated read-timeouts, one hash-validation retry
alone took 90+ min) at ~1MB/s. `hf_transfer` (HF's own official Rust
multi-connection client - legitimate, not ToS-adjacent) is what actually
makes this fast; it needs the `hf_transfer` package in this venv
specifically (bootstrap.sh) and `HF_HUB_ENABLE_HF_TRANSFER=1` (this script
only - `download_indextts.py` deliberately leaves it `"0"`, don't change
that one, it doesn't have the package installed). If ModelScope turns out
fine on a different network this isn't a permanent verdict - just what
happened on that one run.

Inference itself lives in `remanga/ocr/engine.py` (`OCREngine`) +
`remanga/ocr/scripts/deepseek_ocr_worker.py` - a persistent worker
subprocess mirroring `audio/synth.py`'s `_BaseWorkerSynthesizer` lifecycle
(spawn, ready-handshake, auto-heal a missing dependency, bounded-timeout
request/response, stderr draining, clean shutdown), NOT subclassed from it
(TTS-specific interface) but hand-copied with the same reasoning. GPU
preferred: `device = "cuda" if torch.cuda.is_available() else "cpu"` in the
worker, same pattern as `audio8_worker.py`.

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

**Unverified, flag if it breaks**: DeepSeek-OCR-2's actual HF repo/API
wasn't reachable while building this. The worker calls
`model.infer(tokenizer, prompt=, image_file=, output_path=, base_size=1024,
image_size=640, crop_mode=True, save_results=True)` and falls back to
reading a `.md`/`.mmd`/`.txt` file from `output_path` if `.infer()` doesn't
return text directly - this mirrors DeepSeek-OCR (v1)'s published model
card, assumed (not confirmed) to carry over to v2. `ModelManager`'s
`expected_files=("config.json", "model.safetensors")` is similarly a guess
at the repo's file layout; if the real weights ship sharded
(`model-0000X-of-0000Y.safetensors`) the skip-if-present check just never
short-circuits (redundant re-check each `setup-models` run, not a
correctness bug - `snapshot_download` still skips/resumes correctly either
way). Fix both once the real repo/API is confirmed.

Building the fused kernels in `bootstrap.sh` (best-effort, non-fatal):
nvcc must match `torch.version.cuda` **major** (minor mismatch = warning
only) → install `nvidia-cuda-nvcc` into `venv-audio8` itself, don't rely on
system CUDA. Locate its nvcc by `find` (importable module path is
unreliable) at `lib/python3.11/site-packages/nvidia/cu13/bin/nvcc` — **6
levels under `$VENV/lib`, so `-maxdepth` must be ≥6** (an off-by-one at 5
silently broke this once). Set `TORCH_CUDA_ARCH_LIST` from
`nvidia-smi --query-gpu=compute_cap`. Always wrap in
`(set -e; ...) && ok || warn-and-continue` - never let this abort bootstrap.

## Subprocess output: use `remanga/proc_io.py`, never plain line iteration

`for line in proc.stdout` (text mode) translates `\r`→`\n`, so any process
with its own redrawing progress (ffmpeg `-stats`, tqdm downloads) floods the
console with one new line per refresh instead of overwriting in place -
verified directly (a 15s test encode: 48 real newlines vs 68 `\r` refreshes
that must collapse to one line). Use `stream_subprocess()` /
`run_ffmpeg(..., show_progress=True)` - byte-level, only newlines on real
`\n`. Never use bare `capture_output=True` for anything long-running either
(silent until exit, looks hung).

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

The wizard's step order (download→mark→crop→narration→review→tts→mix→render)
lives in `STEP_REGISTRY`, not hardcoded per-project. Each project can have
`projects/<name>/pipeline.json` = `{"steps": ["download", "mark", ...]}`;
missing/empty falls back to `DEFAULT_STEPS` (that exact order) unchanged.
Edit it via the wizard's `edit-pipeline` item, or `remanga run -p <p> -c <c>`
(uses pipeline.json) / `remanga run -p <p> -c <c> -s crop,narration` (one-off
explicit subset, doesn't touch pipeline.json). Every existing single-step
subcommand (`download`/`mark`/`crop`/`write`/`review`/`tts`/`mix`/`render`)
still works unchanged - `run` just wraps the same underlying calls.

## Wizard menu is registry-driven, no hardcoded "modes"

`remanga/commands.py`'s `COMMAND_REGISTRY` is the single source of truth for
every remanga command - both `cli.py`'s argparse subcommands and the
interactive wizard's menu are built from it. The wizard has no curated
"process a chapter" / "mark-then-write" combo modes - it's a two-level
nested menu: main menu = each `Command.category` ("Setup" / "Chapter
Production" / "Project-wide", plus wizard-only "Pipeline" for
edit-pipeline), grouped by `wizard._group_by_category()`; picking one opens
that category's own submenu of commands. `0` is always "back"/"quit" at
every level (`console.ask_index(..., zero_label="Back to main menu")`) -
fixed, not a numbered item that shifts depending on how many entries that
particular menu has, so the same key backs out anywhere. Running a command
re-shows the same submenu (so chaining mark → crop → write is just picking
them one after another within "Chapter Production") until `0` is chosen. Adding a
command means one `Command` entry (with a `category`) in `commands.py` -
nothing in `wizard.py` needs to change; adding a *category* means giving a
command a new `category` string, nothing to register separately.

`select_chapter` (wizard_prompts.py) is a pure picker now - it used to also
call `offer_chapter_restart` (a "resume or pick a restart tier" gate) on
every chapter selection, which fired for *any* command needing a chapter,
including single-tool ones like `write` - selecting a chapter to hand-write
narration for would bounce into a restart menu that had nothing to do with
what was being run. `offer_chapter_restart`/`_RESTART_MENU` were deleted
entirely; that capability is just the standalone `restart` command
(`--mode hard/marks_only/remark/soft`), reachable from the same menu like
everything else. Multi-choice prompts with more than a few options use
`console.ask_index()` (loops on invalid input) instead of Rich's
`Prompt.ask(..., choices=[...])`, which echoes every choice inline
(`[1/2/.../20]`) and gets unreadable past a handful of options.
`ask_index`'s `zero_label` param is what makes `0` a fixed back/quit shortcut
- pass it whenever a menu needs a "back out" option instead of appending one
as item N+1.

## GPU/ffmpeg

Bundled `bin/ffmpeg` (pinned BtbN build) has working `h264_nvenc` on this
box (RTX 3060) - confirmed by direct probe (`ffmpeg -f lavfi -i
nullsrc=s=256x256:d=0.1 -c:v h264_nvenc -f null -`). `_resolve_gpu_ffmpeg()`
already falls back bundled→system-ffmpeg→CPU correctly. Before "fixing" GPU
selection, probe directly first - a silent CPU-only phase (pydub audio
concat, PIL frame compositing) running *before* the GPU encode is normal,
not a bug; don't confuse the two.

## Maintenance rule (do this, don't just read this)

Whenever a session on this repo hits a non-obvious bug, wrong assumption, or
footgun and fixes/works around it — **before ending that turn**, append a
terse entry here (or tighten an existing one; delete anything a code change
made stale). One or two lines: symptom → root cause → fix/rule. Skip
anything already obvious from reading the code. This file is only worth
loading if it stays a shortcut past mistakes already made, not a duplicate
of the source.
