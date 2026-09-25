<img src="assets/logo.png" alt="remanga" width="96" align="left" hspace="14" vspace="4">

# remanga

Manga panels to recap video, in five steps:

1. **Download** chapters from MangaDex.
2. **Mark the panels** in the Panel Marker, a web UI: MAGI v3 finds them when you press Detect, and
   you fix whatever it got wrong by hand.
3. **Make a PDF** of the chapter's cut panels, in reading order.
4. **Give the PDF and `prompts/narration.md` to an LLM** (Gemini, ChatGPT, Claude, ...) and paste its
   one JSON reply into the chapter's `narration.json` - or write it yourself in the Narration Writer,
   and check what the LLM wrote in the Narration Reviewer.
5. **Make the video**: each panel on screen while Kokoro-82M reads that panel's narration, with
   background music underneath.

## Install

```bash
./bootstrap.sh
```

It sets up everything inside this folder: Python, ffmpeg, MAGI v3 and the narrator you use, each
in its own environment (`.tools/venv-magi`, `.tools/venv-kokoro`, ...) with its weights. Linux, macOS or Windows (Git Bash); NVIDIA, AMD, Apple
Silicon or CPU. Run `./run.sh setup` later to repair either install.

## Use it with the menus

```bash
./pipeline.sh
```

remanga takes over the terminal while it runs (built on [Textual](https://textual.textualize.io/))
and leaves nothing behind when you quit. Every screen has the same layout: where you are at the top,
the list or dialog in the middle, and the keys you can press at the bottom - click those too.
`q` quits; `Esc` goes back.

Nothing is highlighted until you press an arrow key or click a row, so an Enter pressed too early
does nothing. The mouse works everywhere: the wheel scrolls, **a click highlights a row, a double
click chooses it** - a single click never starts anything.

| Screen | What it does |
|---|---|
| **Projects** | Your projects. `Enter` opens one, `n` starts a new one: paste the manga's MangaDex URL (or ID, or a title to search). The project is named after the manga's English title, and its reading direction comes from the manga's original language. |
| **Chapters** | The chapter list, fetched fresh from MangaDex each time, as a table: status (✓ downloaded, ◐ partial, + new), pages, what comes next (mark the panels, make the PDF, make the video, video done) and title. `Enter` opens a chapter's actions: download, **mark panels**, make PDF, make video, check pages, re-download, reset (deletes the cut panels, PDF, narration, audio and video, and the folders that leaves empty - the marks and pages stay) or delete. `space` (or clicking a row's `·`) picks several chapters to act on together, `a` downloads every new chapter. Reset and delete ask first. |
| **Work** | Downloads, panel cutting, PDFs and videos run in a task view: the steps, a progress bar and the last few lines of output. `Ctrl+C` stops. When the work ends you get a result: what was made and what to do next (for a PDF: which files to upload, where to paste the reply), or what went wrong. `l` opens the full log, `c` copies the paths to upload. |
| **Settings** (`s`) | One flat list, grouped (Narration, Sound, Video, PDF), each row with a one-line "What it does": narrator engine and voice, take length, pauses, background music and its level (custom values kept), intro, video size, panel enlargement limit, PDF file size limit - for the open project, or the defaults from the projects screen. |

Logs are kept in `projects/<name>/logs/`: `chapter_N.log` for a chapter's PDF and video,
`project.log` for downloads.

## Or with commands

```bash
./run.sh new "https://mangadex.org/title/..."   # prints the project name, e.g. MyMangaTitle
./run.sh download -p MyMangaTitle               # MangaDex's chapter list, with what you have
./run.sh download -p MyMangaTitle -c 1-5        # or -c new for every chapter you don't have
./run.sh mark     -p MyMangaTitle -c 1-5        # the Panel Marker, in your browser
./run.sh write    -p MyMangaTitle -c 1          # write the narration yourself
./run.sh review   -p MyMangaTitle -c 1          # flag what the LLM got wrong
./run.sh voices                                 # one line in every voice, to listen to
./run.sh pdf      -p MyMangaTitle -c 1-5        # cuts the panels, then their PDF
# give pdf/chapter_N/panels_*.pdf + prompts/narration.md to the LLM, paste the reply into
# projects/MyMangaTitle/chapters/chapter_N/narration.json
./run.sh video    -p MyMangaTitle -c 1-5
./run.sh chapters -p MyMangaTitle
```

`-c` takes a chapter, a range, several (`1-5,8`) or `all` (the default). Decimal chapters are
chapters of their own: `1-5` includes 4.5 but not 5.1.

## Marking the panels

```bash
./run.sh mark -p MyMangaTitle -c 1-5
```

or **Mark panels** in a chapter's menu. It opens one browser tab for every chapter you picked:

- **Detect** runs MAGI v3 over the pages and draws the panels it finds (a GPU takes a few seconds a
  page; without one, mark by hand).
- Fix what it got wrong: drag a box, resize it, delete it, draw a missing one, mark a full page as
  one panel. The sidebar lists the pages and what each one has.
- The reading order follows the manga's direction (right to left for Japanese), and the panel
  numbers show it.
- **Save** writes the chapter's `crops.json` and moves to the next chapter in the tab.

The marks are yours: nothing overwrites them, and Reset keeps them. Making the PDF cuts the panels
again whenever the marks are newer than them.

## The narrator

Two engines, switchable in **Settings → Narrator engine**; each keeps its own voice, so switching
back and forth changes nothing else. A chapter narrated by the other one is narrated again.

| Engine | Voice | Speed |
|---|---|---|
| **Kokoro-82M** (default) | its own studio voices, picked from a list | a 60-panel chapter in seconds |
| **Qwen3-TTS** | nine preset narrators, steered by a line of plain English ("calm and unhurried") - or **a voice you design**: describe the narrator, and one sample is made and kept | about ten minutes for the same chapter |

**Hearing them first:** `./run.sh voices` (or Settings → Hear the voices) reads one line in every
voice the engine has, into `global/voice/samples/<engine>/`, with a text file saying which is which.
The model loads once for the whole set.

**Delivery** (Qwen3-TTS): a line of plain English steering how it reads, and it matters more than it
sounds like it should. Left to itself the model performs; asked for "a calm narrator telling a story"
it still performs. The default asks for a technical manual, which is what actually reads level -
measured on one line, pitch swing fell from 5.9 semitones (no instruction) and 4.0 ("calm narrator")
to 3.1. `global/voice/samples/qwen/delivery/` has the same line in all four, to hear for yourself.

**Cloning a recording** (Qwen3-TTS): put a clean recording of one person in `global/voice/` and pick
`Clone <file>` in Settings → Narrator voice. Every panel is then read in that voice. Ten to fifteen
seconds of speech is plenty - a longer file is trimmed to its first 15 seconds, because the whole
reference rides along in the model's context and only slows every line down.

**Designing a voice** (Qwen3-TTS only): Settings → Design a voice, describe the narrator, and one
sample is generated into `global/voice/designed.wav`. Listen to it; design again if it is not right.
Every panel is then spoken *from that sample*, which is what keeps one voice across a chapter -
describing the voice again for each panel is what makes a designed voice wander.

An engine's environment and weights download the first time you use it, not at install time.

## The other two web UIs

Both are optional, both work on the same `narration.json`, and both are in a chapter's menu.

**Narration Writer** (`write`) - one card per panel, its image and a field: type the line for that
panel. It saves in exactly the shape an LLM's reply has, so a chapter written by hand and one pasted
from a chat go through the same checks.

**Narration Reviewer** (`review`) - the same list, but showing what the narration already says, with
a field to flag a panel and say what is wrong. Submitting writes `narration_review.json`; give that
to the LLM with `prompts/narration_review.md` and paste the corrected reply back. Rounds are kept in
`narration_reviews/`, so a flag you raised last round is still there if the fix missed.

## The LLM step

Upload **`prompts/narration.md`** and the chapter's PDF (all parts, if it was split) - that's all.
The PDF's first page tells the LLM the manga, the chapter, the reading direction, the panel list, and
the story so far, so there is nothing to type.

The LLM replies with one JSON block in two sections. Paste all of it into
`chapters/chapter_N/narration.json` (the code fence can come along):
- `narration` - one entry per panel, in reading order: the narration read while that panel is on
  screen, or a skip reason for a panel that is not story (a credits box, a title);
- `memory` - the story so far after this chapter. The next chapter's PDF reads it straight from this
  file and prints it on its first page, so continuity carries forward with no extra step.

**Make video** checks the reply first. If a panel is missing, has no narration, or is skipped for no
reason, nothing is narrated: the problems are listed and written to `pdf/chapter_N/fix_request.md` -
paste that into the same chat and save the new reply over `narration.json`. It also warns (without
stopping) when a panel's narration looks too short, or uses quotation marks, `?`, `!`, `...` or
contractions, which the voice reads badly.

Make each chapter's PDF after pasting the previous chapter's narration, so its story so far is up to
date (the PDF step says so when an earlier chapter has none yet).

## How the files work

```
projects/<name>/
  project.json            the manga, its reading direction, per-project settings
  chapters/chapter_N/
    pages/                downloaded pages
    crops.json            the panel marks from the Panel Marker
    panels/               the panels cut from the pages
    narration.json        the LLM's reply (or the Writer's): narration + memory
    narration_review.json what the Reviewer flagged, for the LLM's fix pass
  pdf/chapter_N/          panels_1.pdf, ... and fix_request.md
  audio/chapter_N/        one clip per panel + audio_timing.json
  audio_modified/chapter_N/  the mixed track
  video/chapter_N/        the video
global/bgm/               your background music files
global/intro/             intro videos (Settings - Intro)
```

Narrating is the slow part, so the chapter menu keeps it apart:
- **Rebuild video** keeps the narration and remakes the music, intro and video - use it after
  changing the music, its level, the intro or the video size (about a minute).
- **Make video** narrates the whole chapter from narration.json, then makes the video - needed only
  when narration.json or the voice changed. On a chapter that already has a narration it asks first.
- **Narrate again, no video** replaces the narration and keeps only that.
- **Remake from source** deletes everything but the pages, the panel marks and narration.json, then
  cuts, narrates and makes the whole video again.

Settings exist twice: the defaults (from the projects screen) and a project's own values (from inside
it). In a project, `●` marks a value that project sets for itself, and **Use the defaults** clears
them; on the defaults screen, `◆` marks a setting some project overrides.

Stopping with Ctrl+C is safe.

**Panel quality:** panels are cut at the page's full resolution, so their size varies a lot.
- A panel **bigger than the video** would be shown smaller than it is: making a video says so - how
  many, the worst one, and which video size would show them all whole.
- A panel **smaller than the video** is enlarged to fill the frame, and past a point that only makes
  it soft - there is nothing in the source to fill those pixels with. `video.max_upscale` (3x by
  default, Settings - Panel enlargement limit) caps it: a small panel sits smaller on screen, sharp, with more
  of the blurred background around it.

**PDF pages:** every page is the same size - the chapter's biggest panel - and black: the panels are
centred on it, and the leading text page is white text on the same black, with its type scaled to the
page. Nothing changes shape as you scroll. The panel images are untouched by this - it is page
geometry, not a re-encoding - so it costs no quality and no size.

**PDF size:** no PDF is larger than the cap (50MB by default). Panels go in losslessly; a chapter too
big for one file is split into parts. Only a single panel too big for a file on its own is stored
near-losslessly.

## Settings

Settings opened from a project are saved for that project (`project.json`); from the project list,
for every project (`config.json`). Everything else is in `config.json`:

| Key | Default | Meaning |
|---|---|---|
| `tts.engine` | `kokoro` | who narrates: `kokoro` (fixed voices, seconds a chapter) or `qwen` (preset narrators or a voice you design, minutes a chapter) |
| `tts.kokoro.voice` / `.speed` | `af_heart` / 1.0 | Kokoro's voice and pace - 1.0 is its own (about 185 words a minute); past about 1.35 it drops the pauses between sentences |
| `tts.qwen.speaker` / `.instruct` | `Ryan` / monotone... | Qwen3-TTS's preset narrator and how it reads - the default asks for a monotone read, because anything warmer makes the model act |
| `tts.qwen.design` / `.designed_sample` | - | the voice you described, and the sample every panel is then spoken from |
| `tts.volume_boost_db` | 0 | gain on each clip; leave at 0 when loudness normalization is on |
| `audio.bgm_enabled` / `bgm_path` | off / - | background music |
| `audio.bgm_below_voice_lu` | 14 | how far the music sits under the voice, in LU - measured per track and chapter, so every music file sits at the same level (12 energetic, 14 balanced, 18 subtle) |
| `audio.pause_between_panels_ms` | 0 | silence between panels (Settings - Pause between panels), and now the whole of it: each clip's own uneven lead-in is trimmed back to an even 25 ms margin first, so 0 is continuous narration with about 50 ms at each join rather than a hard butt-join |
| `audio.edge_fade_ms` | 35 | fade at each clip's edges, applied when the chapter is mixed (Settings - Fade at line edges). The start is only ever faded across the silence the clip already has, so the first word is never ramped; the end may ramp up to 15% into the speech, which is what stops a line sounding cut off. Changing it re-mixes, it does not narrate again |
| `audio.enable_loudnorm` / `loudness_target_lufs` | true / -14 | normalize the finished audio (two-pass, linear) to YouTube's -14 LUFS |
| `video.width` / `height` / `fps` | 1920 / 1080 / 24 | video size - 2560x1440 and 3840x2160 keep big panels sharp (see the quality warning), at a slower render |
| `video.max_upscale` | 3 | how far a small panel may be enlarged to fill the frame; 0 means no cap |
| `video.background_style` | `blur` | `blur` (the panel, blurred) or `solid` (`background_color`) |
| `pdf.max_mb` | 50 | largest PDF file |
| `marker.port` / `writer.port` / `reviewer.port` | 8765 / 8767 / 8766 | where each web UI listens |
| `marker.magi_enabled` / `magi_panel_score_threshold` | true / 0.5 | MAGI v3's panel detection in the Panel Marker, and how sure it must be |
| `marker.min_mark_ratio` | 0.03 | the smallest a panel mark may be, as a fraction of the page's shorter side. A drag under it makes no mark (the box says so while you drag), and a resize handle stops there instead of collapsing a panel to a sliver |
| `cropper.margin_padding_pixels` / `snap_to_gutters` | 8 / true | breathing room around a cut panel, and snapping its edges to the real gutters |
| `downloader.language` | `en` | MangaDex translation language |
