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
   (MAGI)      crop-grid draws MAGI's panels on the grid as orange P1, P2 labels (3.2)
4. YOU CROP    page by page: decide crops on the grid page, THEN borrow MAGI borders that fit (3.3)
               append each page to a scratch file; assemble chapters/chapter_N/llm_crops.json
5. import      ./run.sh llm-crop -p P -c N --force   (fix and re-run until it passes)
6. check       look at EVERY llm_crop/chapter_N/preview/* page
7. cut         ./run.sh crop -p P -c N --force        then look at the tricky panels (3.5)
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
./run.sh crop-grid -p P -c N --formats grid_pages,grid_zip </dev/null
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

### 3.2 MAGI's panel labels on the grid

MAGI v3 is a manga panel detector already installed in `.tools/venv-magi`. It draws **rectangles**
around things that look like panels. It doesn't know about bubbles, story beats or reading order,
and it often boxes things that aren't panels. Its one strength is exact border positions on clean
rectangular panels.

**MAGI proposes; you decide.** Its boxes are measurements you may borrow, never a list of crops.
Copying MAGI's boxes into `llm_crops.json` is the most common way this step goes wrong.

`crop-grid` runs MAGI for you: every grid page has MAGI's panels drawn on it as **orange outlines
labeled `P1`, `P2`, ...** in reading order, and `projects/P/llm_crop/chapter_N/detected_panels.json`
lists each label's box in grid units (`{"pages": {"001_015": {"P1": [ymin, xmin, ymax, xmax]}}}`, also
in chapter_info's `detected_panels`). A frame in the reply can be given as its label (`"P3"`); the
importer swaps in the box. **Never write your own files into `chapters/chapter_N/`**, which holds
source files only.

- MAGI loads once, about a minute for 40 pages on the GPU. The result is cached and reused while the
  pages are unchanged. Run nothing else on the GPU at the same time.
- If it can't run (no CUDA, MAGI off), `crop-grid` says so and draws no labels: measure every frame
  off the grid. That is a fully supported route.

### 3.3 Crop one page at a time - decide, then measure, then write

Work **one page at a time, in `full_manifest` order**, and finish each page before opening the
next. The grid's labels are legible at the size your tool displays (heavy labeled lines every 100,
light labeled lines every 25, ticks every 5; no edge is more than 12.5 units from a numbered line).
For every page, do these steps in this order:

**Step A - Decide the crops by reading the page.** Open the grid page
(`grid_pages/chapter_N/NNN_PPP.png`) and decide from the art and the story, not from the orange
outlines - they are measurements, not crops.
Follow `<process>` in `prompts/llm_crop.md`:
1. Is it a story page? If not: `story: false` with a `skip` reason. Next page.
2. Find every frame: each bordered panel (rectangular or slanted), each inset, each region of
   borderless art.
3. Read every bubble, caption and sound effect, and decide which frame owns it (follow the tail).
4. Decide the crops: which frames stand alone and which form a group (`grouping` in chapter_info,
   usually `balanced`).
5. Number the crops in reading order from `reading_direction` (for `right_to_left`: top tier first,
   right to left within a tier).

Write that plan down in one line per crop before measuring, for example
`1: top-right panel, knight swings, owns bubble "Die"`. The plan is what you check the numbers
against.

**Step B - Name or measure each frame.** For each frame in your plan:
- **One orange outline is exactly that frame** (same four edges, nothing extra, nothing missing):
  write its label, e.g. `"P3"`. Each label at most once per page - the importer rejects a label used
  twice.
- **Anything else** - no outline, one outline around two frames, an outline around lettering, an
  outline whose edge is visibly off the border: measure that frame off the grid.
- The importer warns about any outline in no crop ("detected panel(s) P2 are in no crop"). Either it
  isn't a panel, or you left a panel out of the video - check which.

**Step C - Measure what MAGI can never give you.** On the grid page:
- The page's `text` list: **every** bubble, caption and SFX on the page - inside frames, across
  borders, in gutters - as `{"crop": <owner's order>, "box": [...]}`, one box around the **whole**
  element including the tail. The importer derives each crop's `text_outside` from it (pieces
  that reach past the owner's frames or overlap another crop's frame, slanted borders included),
  so don't write `text_outside` yourself. Captions spanning the gutter between two panels are the
  ones that get missed and cut in half.
- `art_outside` per crop: art it owns that breaks out of its frames.

**Step D - Check the page against your plan, then write it.** Crop count and order match the
plan. No label number leaked into `order`. Every bubble is owned by exactly one crop. Every box lies
inside the page area. Then **append this page's entry to your scratch file right away**, before
opening the next page.

#### What MAGI gets wrong - real cases from `nakamaMamotte` chapter 1

| Page | What MAGI returned | What to do |
|---|---|---|
| `001_002` | Big borderless action area `P5` with a bordered inset `P4` drawn inside it | Correct: two frames, two crops (an inset is its own frame). Use both labels. |
| `001_003` | Middle tier of **slanted** panels: rectangles `P2`, `P3`, `P4` overlap each other | The rectangles are the right frames and must overlap. List the hero's bubble "CHANGE OUR FATE" in `text` with the hero's crop (step C); it sits inside the next panel's rectangle, so the importer removes it from that crop. |
| `001_003` | `P5` a black caption strip, `P6` a box around applause lettering only | Neither is a crop on its own. The caption and its sound are one moment, so group them as one crop, or attach them to the shot they narrate. |
| `001_001` | `P1` stops short of the blurb "The long-awaited new series" at its left edge | Frame from MAGI is fine. The blurb is publisher lettering, not story text: list it nowhere. |
| `001_001` | Vertical publisher disclaimer in the margin, partly inside `P2` | Belongs to no crop, same as watermarks and page numbers. |
| any | Labels follow the layout's reading order | `order` comes from step A, never from label numbers - the story can reorder. |

#### Reply format

The file content is plain JSON; code fences are tolerated but not needed:

```json
{
  "chapter": "3",
  "problems": [],
  "pages": [
    {"page": "003_001", "story": false, "skip": "credits", "crops": [], "text": []},
    {"page": "003_002", "story": true, "crops": [
      {"order": 1, "kind": "splash", "frames": [[0, 0, 1000, 696]], "art_outside": []}
    ], "text": []},
    {"page": "003_003", "story": true, "crops": [
      {"order": 1, "kind": "panel", "frames": [[48, 42, 470, 654]], "art_outside": []},
      {"order": 2, "kind": "group", "frames": [[492, 362, 690, 654], [492, 42, 690, 352]], "art_outside": []}
    ], "text": [
      {"crop": 1, "box": [440, 49, 540, 230]},
      {"crop": 2, "box": [520, 390, 598, 470]}
    ]}
  ]
}
```

- Boxes are `[ymin, xmin, ymax, xmax]`, integers 0-1000, in **square** (grid) units, the same units
  as `detected_panels.json`. A frame can instead be a label string, `"P3"`.
- Every page in `full_manifest` appears exactly once, in order. `skip` is one of `credits`, `ad`,
  `blank`, `duplicate`. A title page counts as story (a `splash`).
- `kind`: `panel` (1 frame), `group` (2+ frames, one narration line), `splash` (one frame covering
  most of the page).
- Each crop becomes one image on screen with one narration line. **Crops that are too small to
  carry a line should be grouped. A crop that covers two separate beats should be split.**
- When unsure where a border is, put the edge **on the gutter side**. `crop` snaps edges that land in
  a gutter; an edge inside the art cuts the art.

### 3.4 Import and check

```bash
./run.sh llm-crop -p P -c N --force </dev/null
```

- **Pass:** prints `crops.json written from Gemini's reply (... pages · ... crops ...)` and writes
  previews to `projects/P/llm_crop/chapter_N/preview/`. (`--force` replaces any existing Panel
  Marker marks without asking; without it a headless run keeps the old marks.)
- **Fail:** exits 1 and writes `projects/P/llm_crop/chapter_N/fix_request.md`. Read it, fix only
  what it names, overwrite `llm_crops.json`, run again.
- Read every warning it prints. "The order differs from the layout's reading order" and "nearly the
  same frame" are usually MAGI boxes copied without step B.

**Look at every preview**, not a sample. Left half: green = frames, blue = text outside a frame,
magenta = art outside a frame, red box = the rectangle each crop covers, with its order number.
Right half: every crop exactly as `crop` will cut it (snapped, painted out, trimmed) - judge those. Where
red rectangles overlap (slanted panels), the order number sits at each rectangle's top-left corner.
Fix any bubble that is cut in half, any frame that is clipped or includes a neighbour, and any
order that is wrong. Then re-import.

### 3.5 Cut, and look at the result

```bash
./run.sh crop -p P -c N --force </dev/null
```

Panels land in `projects/P/chapters/chapter_N/panels/NNN_PPP_KK.png` (e.g. `003_012_02.png` =
chapter 3, page 12, 2nd crop on that page). `--force` is needed when the chapter was cropped before;
it wipes `panels/` and cuts again.

**Look at the cut panels** for every page with slanted borders, groups, insets or `text_outside`,
since the preview can't show everything the cut does. Half a bubble in a panel means that bubble
is missing from the page's `text` list, or listed with the wrong crop (step C). A blank hole means a group's rectangle took in
a frame that isn't a member. A thin strip of the neighbouring panel along a slanted edge is expected
and fine. Fix in `llm_crops.json`, then re-run `llm-crop` and `crop`.

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
