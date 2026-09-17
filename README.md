# remanga

Manga pages to recap video, in four steps:

1. **Download** chapters from MangaDex.
2. **Make a PDF** of each chapter's pages.
3. **Give the PDF and `prompts/narration.md` to an LLM** (Gemini, ChatGPT, Claude, ...) and paste its
   reply into the chapter's `narration.json`.
4. **Make the video**: each page shown whole while Kokoro-82M reads that page's narration, with
   background music underneath.

No panel cropping: the LLM narrates each page, telling every panel on it in reading order.

## Install

```bash
./bootstrap.sh
```

It sets up everything inside this folder: Python, ffmpeg, and Kokoro-82M in its own environment
(`.tools/venv-kokoro`) with its weights. Linux, macOS or Windows (Git Bash); NVIDIA, AMD, Apple
Silicon or CPU. Run `./run.sh setup` later to repair the Kokoro install.

## Use it with the menus

```bash
./pipeline.sh
```

remanga takes over the terminal while it runs and leaves nothing behind when you quit. Every screen
has the same layout: where you are at the top, the list or dialog in the middle, and the keys you
can press at the bottom. Nothing is highlighted until you press an arrow key, so an Enter pressed
too early does nothing. `q` quits from anywhere; `Esc` goes back.

| Screen | What it does |
|---|---|
| **Projects** | Your projects. `Enter` opens one, `n` starts a new one: paste the manga's MangaDex URL (or ID, or a title to search). The project is named after the manga's English title, and its reading direction comes from the manga's original language. |
| **Chapters** | The chapter list, fetched fresh from MangaDex each time, as a table: status (✓ downloaded, ◐ partial, + new), pages, what comes next (PDF ready, narration pasted, video done) and title. `Enter` opens a chapter's actions: download, make PDF, make video, check pages, re-download, reset (deletes the PDF, narration, audio and video, keeps the pages) or delete. `space` picks several chapters to act on together, `a` downloads every new chapter. Reset and delete ask first. |
| **Work** | Downloads, PDFs and videos run in a task view: the steps, a progress bar and the last few lines of output. `Ctrl+C` stops. When the work ends you get a result: what was made and what to do next (for a PDF: which files to upload, where to paste the reply), or what went wrong. `l` opens the full log. |
| **Settings** (`s`) | Narrator voice and speed, background music and volume, video size, PDF size cap - for the open project, or the defaults from the projects screen. |

Logs are kept in `projects/<name>/logs/`: `chapter_N.log` for a chapter's PDF and video,
`project.log` for downloads.

## Or with commands

```bash
./run.sh new "https://mangadex.org/title/..."   # prints the project name, e.g. MyMangaTitle
./run.sh download -p MyMangaTitle               # MangaDex's chapter list, with what you have
./run.sh download -p MyMangaTitle -c 1-5        # or -c new for every chapter you don't have
./run.sh pdf      -p MyMangaTitle -c 1-5
# give pdf/chapter_N/pages_*.pdf + prompts/narration.md to the LLM, paste the reply into
# projects/MyMangaTitle/chapters/chapter_N/narration.json
./run.sh video    -p MyMangaTitle -c 1-5
./run.sh chapters -p MyMangaTitle
```

`-c` takes a chapter, a range, several (`1-5,8`) or `all` (the default). Decimal chapters are
chapters of their own: `1-5` includes 4.5 but not 5.1.

## The LLM step

Upload **`prompts/narration.md`** and the chapter's PDF (all parts, if it was split) - that's all.
The PDF's first page tells the LLM the manga, the chapter, the reading direction, the page list, and
the story so far, so there is nothing to type.

The LLM replies with one JSON block in two sections. Paste all of it into
`chapters/chapter_N/narration.json` (the code fence can come along):
- `narration` - for every page: whether it is story, a short note per panel in reading order, and the
  page's narration;
- `memory` - the story so far after this chapter. The next chapter's PDF reads it straight from this
  file and prints it on its first page, so continuity carries forward with no extra step.

**Make video** checks the reply first. If a page is missing, a story page has no narration, or a
skipped page has no reason, nothing is narrated: the problems are listed and written to
`pdf/chapter_N/fix_request.md` - paste that into the same chat and save the new reply over
`narration.json`. It also warns (without stopping) when a page's narration looks too short for its
panels, or uses quotation marks, `?`, `!`, `...` or contractions, which the voice reads badly.

Make each chapter's PDF after pasting the previous chapter's narration, so its story so far is up to
date (the PDF step says so when an earlier chapter has none yet).

## How the files work

```
projects/<name>/
  project.json            the manga, its reading direction, per-project settings
  chapters/chapter_N/
    pages/                downloaded pages
    narration.json        the LLM's reply: narration + memory
  pdf/chapter_N/          pages_1.pdf, ... and fix_request.md
  audio/chapter_N/        one clip per page + audio_timing.json
  audio_modified/chapter_N/  the mixed track
  video/chapter_N/        the video
global/bgm/               your background music files
```

Every step reuses what is still current: re-running **Make video** after changing the music only
re-mixes and re-muxes; after changing the voice it narrates again. Stopping with Ctrl+C is safe - run
it again to carry on.

**PDF size:** no PDF is larger than the cap (50MB by default). JPEG pages go in exactly as
downloaded, other pages losslessly; a chapter too big for one file is split into parts. Only a single
page too big for a file on its own is stored near-losslessly.

## Settings

Settings opened from a project are saved for that project (`project.json`); from the project list,
for every project (`config.json`). Everything else is in `config.json`:

| Key | Default | Meaning |
|---|---|---|
| `tts.voice` / `tts.speed` | `af_heart` / 1.0 | Kokoro voice (see Settings for the list) and speaking speed - Kokoro at 1.33 is about 237 words a minute; past about 1.35 it starts dropping the pauses between sentences |
| `tts.volume_boost_db` | 0 | gain on each clip; leave at 0 when loudness normalization is on |
| `audio.bgm_enabled` / `bgm_path` | off / - | background music |
| `audio.bgm_below_voice_lu` | 14 | how far the music sits under the voice, in LU - measured per track and chapter, so every music file sits at the same level (12 energetic, 14 balanced, 18 subtle) |
| `audio.pause_between_pages_ms` | 350 | silence between pages |
| `audio.enable_loudnorm` / `loudness_target_lufs` | true / -14 | normalize the finished audio (two-pass, linear) to YouTube's -14 LUFS |
| `video.width` / `height` / `fps` | 1920 / 1080 / 24 | video size |
| `video.background_style` | `blur` | `blur` (the page, blurred) or `solid` (`background_color`) |
| `pdf.max_mb` | 50 | largest PDF file |
| `downloader.language` | `en` | MangaDex translation language |
