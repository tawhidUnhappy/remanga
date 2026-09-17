# AGENTS.md - running remanga as an LLM agent

This file is for an LLM agent (Claude Code, Codex, Gemini CLI, or anything else that can run shell
commands and look at images) that has been asked to **turn MangaDex chapters into narrated recap
videos with remanga, on its own, with no human at the keyboard**.

The human workflow in [README.md](README.md) has two copy/paste round trips through a chat LLM
(Gemini crops the panels, a chat LLM writes the narration) and two browser UIs (Panel Marker,
Narration Reviewer). **You are the LLM in both round trips.** You look at the pages, write the crop
plan, look at the panels, write the narration, then let remanga do everything else: download,
cutting, speech, mixing, rendering.

Everything in this file was run on this machine (RTX 3060 12 GB, 14 GB RAM) in September 2026:
download, grid, crop import, crop, narration template, TTS, mix, render, status, and MAGI detection
called from a script.

---

## 0. The job, in one screen

A typical request: *"Make the video for https://mangadex.org/title/<uuid>/... chapters 3-5."*

```text
1. project     pick/create the project, make sure project.json has reading_direction
2. download    ./run.sh download-range -p P -u URL -r 3-5
   per chapter N, in order:
3. grid        ./run.sh crop-grid -p P -c N
4. YOU CROP    look at grid_pages/chapter_N/*.png, write chapters/chapter_N/llm_crops.json
   (MAGI)      optional: run MAGI for exact panel borders and check your frames against them
5. import      ./run.sh llm-crop -p P -c N --force   (fix and re-run until it passes)
6. check       look at llm_crop/chapter_N/preview/*
7. cut         ./run.sh crop -p P -c N --force
8. template    ./run.sh narration-init -p P -c N --mode template --force
9. YOU NARRATE look at chapters/chapter_N/panels/*, fill narration.json, update memory.json
10. voice+mix  ./run.sh tts -p P -c N  &&  ./run.sh mix -p P -c N
11. video      ./run.sh render -p P -c N
   after all chapters:
12. join       ./run.sh full-recap -p P -c 3,4,5     (only when several chapters were asked for)
13. verify     ./run.sh verify -p P -c 3,4,5
```

Do chapters **one at a time and in order**: chapter N's narration depends on the `memory.json`
written by chapter N-1.

---

## 1. Ground rules for running it headless

- **Always go through `./run.sh <command>`** from the repo root (`/mnt/datadisk/remanga`). It pins
  PATH, caches and PYTHONPATH to this folder. Never `pip install` anything; environments are
  managed by `bootstrap.sh` / `./run.sh setup-tools`.
- **Run every command with `</dev/null`.** Without a TTY remanga never waits for a keypress. Menus
  fall back to defaults, and a step that needs a human either proceeds on explicit flags or
  **raises with a message saying what file to fill**. Read that message; it is your instruction.
- **Never run these as an agent:** `interactive` / `pipeline.sh` (the wizard), `mark`, `mark-all`,
  `view-marks`, `write`, `review` (browser UIs that block until a human clicks Save), and
  `run` with its default step list (it includes `pause`, `narration` and `review`, which are human
  hand-offs). Call the single-step commands instead.
- **Every command's help is accurate:** `./run.sh --help`, `./run.sh <command> --help`.
  Exit codes: `0` ok, `1` failed, `130` interrupted.
- **Do not change `config.json`** (voice, music, resolution, engine) unless the user asks. Those are
  the channel's look and sound. Per-run overrides exist: `tts --voice`, `mix --bgm`.
- **Check before claiming it works.** A clean exit plus `./run.sh status -p P -c N` is how you know
  a chapter is done. There are no unit tests in this repo.
- **Resource limits:** 14 GB RAM, one 12 GB GPU. Run GPU jobs (MAGI, TTS, render) **one at a time**,
  never in parallel. Don't load DeepSeek-OCR (the Narration Writer's OCR button); you read the
  bubbles yourself.
- Decimal chapters (1.1, 5.1) are chapters in their own right. A range `1-5` includes 1.1 and 4.5,
  but not 5.1.

---

## 2. Projects and the MangaDex link

A **project** is one manga: `projects/<name>/`. Pick a short camelCase name from the title
(existing ones: `Yandere`, `mermaidWife`, `reincarnatedAsTheLeaderOfAVillainParty`). If a project's
`project.json` already has the same `manga_id`, reuse that project. Don't create a second one.

```bash
ls projects/
grep -l '"manga_id": "<uuid>"' projects/*/project.json
```

`-u/--url` accepts a title URL (`https://mangadex.org/title/<uuid>/<slug>`), a chapter URL
(`https://mangadex.org/chapter/<uuid>`, which resolves to its manga), a bare UUID, or a title search
query. Once `project.json` records the manga, `-u` can be left out.

### Download

```bash
./run.sh download-range -p P -u "<mangadex url>" -r 3-5 </dev/null   # a range: '3-5', '1-5,8,10-12'
./run.sh download       -p P -u "<mangadex url>" -c 3   </dev/null   # one chapter
```

It prints the chapter list MangaDex has, downloads, and verifies every page against its SHA-256.
Re-running it is safe: it re-verifies and fetches only what is missing. A chapter MangaDex doesn't
list is refused up front, so a failure here usually means a wrong number or the wrong
`downloader.language` (default `en`).

Pages land in `projects/P/chapters/chapter_N/pages/NNN_PPP.jpg` (chapter and page zero-padded to 3,
e.g. `003_012.jpg`).

### reading_direction (required before cropping)

A fresh project's `project.json` has no `reading_direction`, and `crop-grid` **fails** without it
(the wizard normally asks). Set it yourself from `original_language`, which download writes:
`ja` → `right_to_left` (manga); `ko`, `zh`, and most others → `left_to_right` (manhwa/manhua);
anything unclear → look at a page and decide.

```bash
.venv/bin/python - <<'EOF'
import json; p = "projects/P/project.json"; d = json.load(open(p))
d.setdefault("reading_direction", "right_to_left" if d.get("original_language") == "ja" else "left_to_right")
json.dump(d, open(p, "w"), indent=2)
EOF
```

---

## 3. Cropping - you plan the crops

remanga's "LLM crop" extension was built for Gemini. You play Gemini's part. **Read
[prompts/llm_crop.md](prompts/llm_crop.md) in full before cropping your first chapter**: it is the
spec your reply is checked against, and it has worked examples. [docs/llm_crop_guide.md](docs/llm_crop_guide.md)
explains what the program does with the reply.

### 3.1 Build the grid

```bash
./run.sh crop-grid -p P -c N </dev/null
```

Creates:

| Path | What it is |
|---|---|
| `projects/P/grid_pages/chapter_N/NNN_PPP.png` | each page on a 2048 px black square with a green 0-1000 ruler, **the images you look at** |
| `projects/P/grid_zip/chapter_N/grid_1.zip` | same images + `chapter_info.json` |
| `projects/P/chapters/chapter_N/llm_crops.json` | empty (0 bytes) - **your reply goes here** |

Get the chapter info (manifest, reading direction, grouping, each page's area) without unzipping
by hand:

```bash
.venv/bin/python -c "import zipfile,json; print(json.dumps(json.loads(zipfile.ZipFile('projects/P/grid_zip/chapter_N/grid_1.zip').read('chapter_info.json')), indent=1))"
```

`page_areas["003_004"] = [0, 0, 1000, 696]` means that page fills the square's top-left, x 0-696
(a tall page). `[0, 0, 718, 1000]` is a wide spread. **Every box you write must lie inside its page
area.** Measure in square units, exactly what the ruler shows.

### 3.2 Look, then write

Open the grid images with your image-reading tool **one page at a time, in `full_manifest` order**.
The labels are legible at the size your tool displays (heavy lines every 100, light lines every 50,
ticks every 10). For each page, follow `<process>` in the prompt: story page or not, find every
frame, assign every bubble, caption and SFX to exactly one crop, decide groups (`grouping`, default
`balanced`), number crops in reading order, and measure `frames`, `text_outside`, `art_outside`.

A long chapter is 40+ images. Don't hold the whole plan in your head: write each page's entry to a
scratch file as you finish it, then assemble.

Reply format (the file content is plain JSON; code fences are tolerated but not needed):

```json
{
  "chapter": "3",
  "problems": [],
  "pages": [
    {"page": "003_001", "story": false, "skip": "credits", "crops": []},
    {"page": "003_002", "story": true, "crops": [
      {"order": 1, "kind": "splash", "frames": [[0, 0, 1000, 696]], "text_outside": [], "art_outside": []}
    ]},
    {"page": "003_003", "story": true, "crops": [
      {"order": 1, "kind": "panel", "frames": [[48, 42, 470, 654]], "text_outside": [[440, 49, 540, 230]], "art_outside": []},
      {"order": 2, "kind": "group", "frames": [[492, 362, 690, 654], [492, 42, 690, 352]], "text_outside": [], "art_outside": []}
    ]}
  ]
}
```

- Boxes are `[ymin, xmin, ymax, xmax]`, integers 0-1000, in **square** units.
- Every page in `full_manifest` appears exactly once, in order. `skip` is one of `credits`, `ad`,
  `blank`, `duplicate`. A title page counts as story (a `splash`).
- `kind`: `panel` (1 frame), `group` (2+ frames, one narration line), `splash` (one frame covering
  most of the page).
- Each crop becomes one image on screen with one narration line. **Crops that are too small to
  carry a line should be grouped. A crop that covers two separate beats should be split.**
- When unsure where a border is, put the edge **on the gutter side**. `crop` snaps edges that land in
  a gutter; an edge inside the art cuts the art.

### 3.3 MAGI - exact panel borders (optional, recommended for dense pages)

MAGI v3 is a manga panel detector already installed in `.tools/venv-magi`. It finds bordered
panels precisely but knows nothing about bubbles, groups or story order. The way to combine it
with your judgement: **you decide what the crops are; MAGI tells you where the borders are.** Run it
on a chapter's pages, convert its boxes to square units, and compare them to your `frames`.

Save as a scratch script (not in the repo) and run it with the repo env:

```python
# magi_boxes.py  - usage: magi_boxes.py <project> <chapter> [page_stem ...]
import json, sys, zipfile
from pathlib import Path
from PIL import Image
from remanga.config import RemangaConfig
from remanga.webui.magi_assist import detect_panels_for_pages

project, chapter, only = sys.argv[1], sys.argv[2], set(sys.argv[3:])
root = Path("projects") / project
info = json.loads(zipfile.ZipFile(root / f"grid_zip/chapter_{chapter}/grid_1.zip").read("chapter_info.json"))
pages = [p for p in sorted((root / f"chapters/chapter_{chapter}/pages").iterdir())
         if not only or p.stem in only]
results = detect_panels_for_pages(pages, RemangaConfig.load().marker)   # {filename: [[x1,y1,x2,y2] px]}
for page in pages:
    w, h = Image.open(page).size
    _, _, ay, ax = info["page_areas"][page.stem]          # page area on the square
    sq = [[round(y1 / h * ay), round(x1 / w * ax), round(y2 / h * ay), round(x2 / w * ax)]
          for x1, y1, x2, y2 in results.get(page.name, [])]
    print(page.stem, json.dumps(sq))                       # [ymin,xmin,ymax,xmax] in square units
```

```bash
PATH="$PWD/bin:$PATH" HF_HOME="$PWD/.cache/huggingface" PYTHONPATH="$PWD" \
  .venv/bin/python /path/to/scratch/magi_boxes.py P N </dev/null
```

- Loads once, then about a second per page on the GPU. Weights are in `checkpoints/magiv3`.
  RAM was fine on this machine (≥ 8.7 GB stayed free). Output order is **not** reading order.
- Use its borders for `frames` when they agree with what you see. It misses borderless art, merges
  or splits odd layouts, and can't see `text_outside` / `art_outside`; those stay your call.
- Requires CUDA. If it errors, skip it. Your own measurements are acceptable input.

### 3.4 Import and check

```bash
./run.sh llm-crop -p P -c N --force </dev/null
```

- **Pass:** prints `crops.json written from Gemini's reply (... pages · ... crops ...)` and writes
  previews to `projects/P/llm_crop/chapter_N/preview/`. (`--force` replaces any existing Panel
  Marker marks without asking; without it a headless run keeps the old marks.)
- **Fail:** exits 1 and writes `projects/P/llm_crop/chapter_N/fix_request.md`. Read it, fix only
  what it names, overwrite `llm_crops.json`, run again.

**Look at the previews** before cutting: green = frames, blue = text outside a frame, magenta = art
outside a frame, red box = the actual cut with its order number, red tint = painted out. Fix any
bubble that is cut in half, any frame that is clipped or includes a neighbour, and any order that
is wrong. Then re-import.

### 3.5 Cut

```bash
./run.sh crop -p P -c N --force </dev/null
```

Panels land in `projects/P/chapters/chapter_N/panels/NNN_PPP_KK.png` (e.g. `003_012_02.png` =
chapter 3, page 12, 2nd crop on that page). `--force` is needed when the chapter was cropped before;
it wipes `panels/` and cuts again. **Look at a sample of the panels.** They are what the viewer
sees and what you will narrate.

> Re-cropping renumbers panels. If `narration.json` already exists for that chapter, it has to be
> rebuilt to match (step 4), or TTS/mix/render will refuse to run.

---

## 4. Narration - you write the script

**Read [prompts/narration.md](prompts/narration.md) in full before narrating your first chapter.**
It is the style contract, and the user cares about it a lot. The rules that most often get broken:

- **Told retelling:** third person, present tense, one narrator, never in the scene.
- **Reported speech, never quoted.** No quotation marks, no `?`, no `!`, no `...`, **no
  contractions**. Every sentence ends in a period.
- **Complete, not summarized.** Every bubble, thought and caption is reported, with every claim,
  threat, question and insult. Report the attitude through the verb (*admits*, *insists*,
  *demands to know*).
- **One steady register.** The narrator does not emote, joke, address the viewer, or tease what's
  coming. Emotion belongs to the characters, reported.
- **For the TTS voice:** no stammers spelled out (`W-what`), no transcribed interjections (`Huh`,
  `Tch`), no ALL-CAPS emphasis, no markdown or emoji. Spell out numbers that read badly.
- **No spoilers:** names only once the story gives them; nothing revealed early.
- Connect each entry to the one before it (cause, contrast, timing); mark scene changes.

If `global/narration_lessons.json` exists, read it too. It holds rules learned from past review
rounds, and they apply to every manga.

### 4.1 Template

```bash
./run.sh narration-init -p P -c N --mode template --force </dev/null
```

Writes `projects/P/chapters/chapter_N/narration.json` with one entry per panel, every `text`
empty, and the exact `panel_id`s:

```json
{"chapter": "3", "total_panels": 42, "narration": [{"panel_id": "003_001_01", "text": ""}, ...]}
```

`panel_id` must equal a file stem in `panels/` exactly (3-digit chapter, 3-digit page, 2-digit
panel). Filling the template keeps the ids right. Don't add or remove entries.

### 4.2 Write it

1. Read `projects/P/memory.json`. If it has content, this chapter continues the story: keep names,
   relationships and open threads consistent, and open by picking up where it left off. If it's
   empty (`{}` or 0 bytes), this is the first chapter: open by orienting the viewer.
2. Open the panel images **in panel order, one at a time**, and write each entry before opening the
   next. Skipping or swapping one shifts every entry after it onto the wrong image, which is the
   most damaging mistake here. Reading neighbouring pages in `pages/` for context is fine.
3. Revise the whole script as an editor, using the checklist in `<process>` step 4 of the prompt.
   Then run a mechanical check:

```bash
.venv/bin/python - <<'EOF'
import json, re
from pathlib import Path
ch = Path("projects/P/chapters/chapter_N")
d = json.load(open(ch / "narration.json"))
stems = sorted(p.stem for p in (ch / "panels").iterdir())
ids = [e["panel_id"] for e in d["narration"]]
assert ids == stems, "panel ids do not match panels/ in order"
assert d["total_panels"] == len(ids)
symbols = re.compile(r"[\"“”?!*_#`]|\.\.\.|…|\b[A-Za-z]-[a-z]")          # quotes, ?, !, ..., stammers, markdown
contraction = re.compile(r"\b\w+(n't|'re|'ll|'ve|'m|'d)\b|\b(it|that|he|she|there|what|let|who)'s\b", re.I)
caps = re.compile(r"\b[A-Z]{3,}\b")                                           # shouted words (acronyms are ok)
for e in d["narration"]:
    assert e["text"].strip(), f"empty: {e['panel_id']}"
    for rx in (symbols, contraction, caps):
        for m in rx.finditer(e["text"]):
            print(e["panel_id"], "->", repr(m.group()))
print("checked", len(ids), "entries")
EOF
```

(The pattern is deliberately broad. Possessives like *Hana's* are allowed, and so are real acronyms
like `HP`. Judge each hit; don't blindly delete it.)

4. **Update `projects/P/memory.json`** in place, following Block 2 of `<output_format>` in the prompt:
   keep existing characters and threads, append this chapter's `key_plot_points`, resolve or add
   `unresolved_cliffhangers`, and set `last_chapter_processed`. Do this before starting the next
   chapter.

You are also the reviewer. There is no human review round in the agent flow, so re-read the
script against the panels once more before TTS.

---

## 5. Voice, mix, video

```bash
./run.sh tts    -p P -c N </dev/null   # Kokoro-82M, configured voice; resumes; --force redoes all
./run.sh mix    -p P -c N </dev/null   # narration + configured BGM + EBU R128 to -16 LUFS
./run.sh render -p P -c N </dev/null   # 1080p MP4 (NVENC if available)
./run.sh status -p P -c N </dev/null   # every row should be ✓ for the steps above
```

Output: `projects/P/video/chapter_N/P_chN_recap.mp4`. A 3-panel test chapter took ~17 s for all
three steps. A real chapter's TTS is well under a minute.

All three refuse to run if panels and narration disagree (a panel with no entry, or an entry with
no panel). The fix is in step 3.5/4, never a workaround.

After editing `narration.json` for a chapter that already has audio, run **`tts --force`**, then
`mix` and `render`. TTS resume only checks that a clip exists, not whether its text changed, so
plain `tts` keeps the old lines. Changing only music or volume: `./run.sh remix -p P -c N`.

### Several chapters → one video

```bash
./run.sh full-recap -p P -c 3,4,5 </dev/null   # comma list; builds anything missing, then joins
./run.sh verify     -p P -c 3,4,5 </dev/null   # decodes audio/video end to end
```

It keeps each chapter's own MP4 and writes the joined one under `projects/P/video/` (the filename
carries the chapter span, e.g. `P_ch3-ch5_full_recap.mp4`), with one continuous music bed and one
loudness pass. Only use `--rebuild outputs|everything|sources` when something upstream was really
redone. They delete work, project-wide.

When the user asks for "the video" of a range, render every chapter **and** run `full-recap` for
that range, then report both locations.

---

## 6. Where things live

```text
projects/P/
  project.json                         manga id/url/title, reading_direction, remembered choices
  memory.json                          story continuity - read before, update after each chapter
  manifest.json                        bookkeeping (download verification, panel counts)
  chapters/chapter_N/
    pages/NNN_PPP.jpg                  downloaded pages (source)
    llm_crops.json                     your crop plan (source)
    crops.json                         imported crops (source; also what Panel Marker edits)
    panels/NNN_PPP_KK.png              cut panels (generated by crop)
    narration.json                     your script (source)
  grid_pages/ grid_zip/ llm_crop/      crop hand-off + previews/fix requests (generated)
  audio/chapter_N/                     TTS clips + audio_timing.json (expensive - don't delete)
  audio_modified/chapter_N/            master_audio.wav (cheap cache)
  video/chapter_N/                     chapter MP4 (+ _work/ caches)
prompts/llm_crop.md                    crop spec - read before cropping
prompts/narration.md                   narration spec - read before narrating
prompts/narration_review.md            fix-pass spec (human review flow)
prompts/youtube.md                     title/description/thumbnail text, if the user asks for upload text
global/bgm/, global/voice/             music beds, cloning references
global/narration_lessons.json          cross-manga narration lessons (may not exist)
config.json                            machine-wide settings (don't edit unasked)
```

---

## 7. When something goes wrong

| Symptom | Cause / fix |
|---|---|
| `Missing 'reading_direction' for project` | Add it to `project.json` (section 2). |
| `llm_crops.json is still empty` | You haven't written the reply yet, or wrote it to the wrong chapter folder. |
| `Gemini's reply ... didn't check out - see fix_request.md` | Read it, fix exactly those pages, re-run `llm-crop`. |
| TTS/mix/render: panels and narration don't match | Re-cropped after narrating, or edited ids. Regenerate the template and carry texts over by content, or re-narrate. |
| `crop` says the chapter is already cropped | Add `--force`. |
| A command waits or asks something | You forgot `</dev/null`, or you called a web-UI command. Stop it; use the single-step commands. |
| `--range is required` / `--select is required` | Headless runs must pass the chapter selection as a flag. |
| MAGI: `No CUDA GPU available` | Another GPU job is running, or no GPU. Skip MAGI. |
| Render or master audio looks broken after a kill | `./run.sh verify -p P -c N`, then re-run what it names. |

Something not covered here: `.claude/skills/remanga-ops/SKILL.md` is the maintainers' fast-start
and known-bugs log, and `README.md` is the full reference.

---

## 8. Finishing a job

Report back to the user with:
- the MP4 path(s), and `full-recap`'s joined file if one was made;
- per chapter: pages downloaded, crops made (groups, skipped pages), panels narrated;
- anything you weren't sure about (an ambiguous reading order, a bubble you couldn't read, a page
  you skipped) so they know what to spot-check;
- anything that failed, with the command and its error, not a summary of it.

If you changed code or docs in this repo (not project data - `projects/` is gitignored), the user
expects a commit and push to `origin/main` afterwards.
