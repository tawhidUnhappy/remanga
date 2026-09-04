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
remanga/                                     # package: json_io.py, ffmpeg_io.py, proc_io.py, humanize.py, pipeline.py, ...
  tui/                                       # arrow-key menus (select/multiselect/confirm) + non-tty fallback
  commands/{spec,selection,registry}.py + handlers/{setup,chapter,project,cleanup}.py
  wizard/{app,projects,chapters,params,narration,review,uploads,handoff,pipeline_edit,checks}.py
  settings/{files,fields,assets,vision,presets,engine,video,sections,summary,wizard,paths_ui}.py
  full_recap/{discovery,timeline,compiler}.py   verify/{models,panels,probe,runner,report}.py
  reset/{modes,entries,actions}.py              status/{compute,panel}.py
  audio/{tts.py,mix.py,synth/{base,indextts,audio8}.py,scripts/*_worker.py}
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

**Three attempts, in order, self-supervised - not a static env-var guess.**
`download_deepseek_ocr.py` runs each `snapshot_download()` attempt as its
own child subprocess (`_run_hf_attempt()`) so it can watch and kill one that
stalls instead of just picking a transfer mode and hoping:
1. **HF Hub, Xet enabled** (HF's official high-performance transfer -
   genuinely much faster when it works). Watched: polls total bytes across
   every `*.incomplete` file under `<model_dir>/.cache/huggingface/download/`
   every `POLL_INTERVAL_SECONDS`; if that total hasn't grown for
   `XET_STALL_TIMEOUT_SECONDS` (after an initial `XET_STALL_GRACE_SECONDS`
   warm-up), it's killed and attempt 2 runs. Confirmed live, repeatedly:
   Xet hangs at 0 bytes/0% in this sandbox (process alive, ~2% CPU, no
   progress) - possibly this sandbox's network blocking Xet's transfer
   endpoint specifically, not a fact about every machine, which is exactly
   why this earns a real supervised shot each run instead of a permanent
   disable.
2. **HF Hub, Xet explicitly disabled** (classic HTTP/LFS) - confirmed live
   to make steady, unstalled progress once attempt 1 is killed. Not
   stall-watched the same way; `MAX_ATTEMPTS` retries on outright failure/
   exception instead (dropped connection etc.), same reasoning
   `download_audio8.py`'s own retry loop uses. Still single-connection and
   throttled - unauthenticated ~1-3MB/s observed - the Hub's own warning
   ("set a HF_TOKEN...") is a real lever, see the HF-token section above.
3. **ModelScope mirror**, last resort - a real run once saw *its* mirror
   stall over an hour on the one big shard (repeated read-timeouts, one
   hash-validation retry alone took 90+ min), which is why it's last here,
   opposite priority from `download_indextts.py` (ModelScope first).

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
(`models/weights.py` - covers IndexTTS-2.5, Audio8 TTS, DeepSeek-OCR-2, i.e.
every `Command`/synthesizer that goes through `ModelManager`) and MAGI v3's
own separate subprocess call (`webui/magi_assist.py:ensure_weights_downloaded`,
doesn't use `ModelManager`) both call `resolve_hf_token()` and append it as
an optional 4th positional CLI arg (`<model_dir> <repo_id> [hf_token]`) to
their download script - every `download_*.py` script accepts it now
(`models/scripts/download_{indextts,audio8,deepseek_ocr}.py`,
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
(`models/weights.py`) was missing it (worker spawns elsewhere - indextts_
worker/audio8_worker/deepseek_ocr_worker - already had it right) and it
looked hung: `Downloading DeepSeek-OCR-2 model weights...` printed, then
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
  automatable; don't replace it with a positional guess.
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
- Every model downloader (`models/scripts/download_{indextts,audio8,
  deepseek_ocr}.py`, `webui/scripts/download_magi.py`) now verifies each
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

## GPU/ffmpeg

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

## Maintenance rule (do this, don't just read this)

Whenever a session on this repo hits a non-obvious bug, wrong assumption, or
footgun and fixes/works around it — **before ending that turn**, append a
terse entry here (or tighten an existing one; delete anything a code change
made stale). One or two lines: symptom → root cause → fix/rule. Skip
anything already obvious from reading the code. This file is only worth
loading if it stays a shortcut past mistakes already made, not a duplicate
of the source.
