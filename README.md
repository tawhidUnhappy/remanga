<img src="assets/logo.png" alt="remanga" width="96" align="left" hspace="14" vspace="4">

# remanga

Manga panels to recap video, in five steps:

1. **Download** chapters from MangaDex - or from comix.to, through your own Firefox
   ([Sites that need a real browser](#sites-that-need-a-real-browser)).
2. **Mark the panels** in the Panel Marker, a web UI: MAGI v3 finds them when you press Detect, and
   you fix whatever it got wrong by hand.
3. **Make a PDF** of the chapter's cut panels, in reading order.
4. **Give the PDF and `prompts/narration.md` to an LLM** (Gemini, ChatGPT, Claude, ...) and paste its
   one JSON reply into the chapter's `narration.json` - or write it yourself in the Narration Writer,
   and check what the LLM wrote in the Narration Reviewer.
5. **Make the video**: each panel on screen while the narrator (Kokoro-82M by default) reads that panel's narration, with
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
| **Projects** | Your projects. `Enter` opens one, `d` deletes the highlighted one (after you type its name), `n` starts a new one: paste the manga's MangaDex URL (or ID, or a title to search). The project is named after the manga's English title, and its reading direction comes from the manga's original language. |
| **Chapters** | The chapter list, fetched fresh from MangaDex each time, as a table: status (✓ downloaded, ◐ partial, + new), pages, what comes next (mark the panels, make the PDF, make the video, video done), how many versions are kept (Ver) and title. `Enter` opens a chapter's actions: download, **mark panels**, make PDF, make video, **make video fresh**, **versions**, check pages, re-download, **delete chosen** (a checklist of what the chapter has on disk - pages, marks, panels, PDF, narration, audio, video - with sizes; tick what to delete, `d` deletes, red rows are what remanga can't make again), reset (deletes the cut panels, PDF, narration, audio and video, and the folders that leaves empty - the marks and pages stay) or delete. `space` (or clicking a row's `·`) picks several chapters to act on together, `r` picks every chapter from the last one picked to the highlighted one (chapter n to m), `a` downloads every new chapter. With several picked, **Long video...** makes one video of them - see [Long videos](#long-videos). Reset and delete ask first. |
| **Work** | Downloads, panel cutting, PDFs and videos run in a task view: the steps, a progress bar and the last few lines of output. `Ctrl+C` stops. When the work ends you get a result: what was made and what to do next (for a PDF: which files to upload, where to paste the reply), or what went wrong. `l` opens the full log, `c` copies the paths to upload. |
| **Settings** (`s`) | One short flat list, grouped (Narration, Sound, Video, PDF), each row with a one-line "What it does": narrator engine and voice, volume, background music and its volume (custom values kept), intro, video size, panel enlargement limit, PDF file size limit - one set for every project. |

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
./run.sh plugins                                # the plug-ins loaded: engines, layouts, sources, jobs
./run.sh pdf      -p MyMangaTitle -c 1-5        # cuts the panels, then their PDF
# give pdf/chapter_N/panels_*.pdf + prompts/narration.md to the LLM, paste the reply into
# projects/MyMangaTitle/chapters/chapter_N/narration.json
./run.sh video    -p MyMangaTitle -c 1-5
./run.sh long     -p MyMangaTitle -c 1-5        # one video of chapters 1 to 5 (--from-source, --delete)
./run.sh long     -p MyMangaTitle             # the long videos made so far
./run.sh chapters -p MyMangaTitle
./run.sh sources  -p MyMangaTitle --add "https://comix.to/title/..."  # the same manga on another site
./run.sh delete   -p MyMangaTitle               # the whole project, for good (asks you to type its name)
```

`-c` takes a chapter, a range, several (`1-5,8`) or `all` (the default). Decimal chapters are
chapters of their own: `1-5` includes 4.5 but not 5.1.

### One manga, several sites

A project can download from more than one site: MangaDex often only links to a licensed chapter (no
pages), while comix.to has it. `./run.sh sources -p MyMangaTitle --add <link>` (or `o` on the
Chapters screen) adds the same manga on another site; `--remove comix` takes one away, and
`./run.sh sources -p MyMangaTitle` lists them, first = preferred. The chapter list then shows every
site's chapters together, each row naming its site, and a download takes each chapter from the site
that downloaded it before, else from the first site that has its pages. project.json keeps them as
`"sources"`; a project with one site has no list and works as it always did.

### Sites that need a real browser

comix.to only serves a real person - Cloudflare's "Just a moment..." check stands in front of it,
and its own API is signed and encrypted. So remanga downloads it **through your Firefox, in your
own profile**, with a small extension, the remanga helper:

```bash
./run.sh new "https://comix.to/title/mwx7e-ghost-story-club-remake/1513233-chapter-1"
./run.sh download -p GhostStoryClubRemake -c 1-5
```

- **Installing the helper for good** (once): Mozilla signs it as a private ("unlisted") add-on -
  free, never listed anywhere. Sign in (or sign up) at addons.mozilla.org, press "Generate new
  credentials" on <https://addons.mozilla.org/en-US/developers/addon/api/key/>, then
  `./run.sh helper --set-key` (paste the two values) and `./run.sh helper --install`: a few minutes
  later Firefox asks to add it. It stays through restarts like any extension, and when remanga has a
  newer helper it is signed and offered the same way. `./run.sh helper` shows where it stands.
  Without that, remanga offers it as a temporary add-on (`about:debugging` → **Load Temporary
  Add-on...**), gone when Firefox restarts. `downloader.browser_profile` is the profile it opens
  Firefox in (the name Firefox's profile menu shows; empty = Firefox's default).
- **It stays out of your browsing.** Between downloads the helper only asks remanga whether there is
  work. It listens to requests only during a job and only in its own remanga tab, and runs its
  page script only there - nothing is added to any other site (your bank, YouTube Studio, ...), and
  your Firefox is never put under remote control (no `navigator.webdriver`). Its toolbar button
  shows what it is doing: nothing, `…` working, `!` waiting for you to solve a check.
- **One background tab in your own window.** The helper reads the site in a tab of its own at the
  back of your Firefox window - you keep browsing in the others - and keeps that tab from chapter to
  chapter; it closes a little after the last one (or when remanga exits).
- **Checks are yours.** When the site shows a check, the remanga tab comes to the front and remanga
  says so; solve it and the download carries on by itself.
- **Saved, not re-asked.** The chapter list is saved with the project and shown from there - no
  Firefox, no request - when you open it; `u` (Update list) asks the site for new chapters (page 1
  only, unless the list grew). A list over a day old is read again only if the helper is already
  running (Firefox is never started just to show a list), and a download asks again only for a
  chapter the saved list doesn't have. The manga's details, every upload seen and every chapter
  downloaded (checked on disk) are kept too.
- **In the menus** it is just another source: `n` on Projects takes a comix.to link, the chapter list
  and every download work as for MangaDex, the chapter list's top bar says what Firefox is doing
  (and when a check waits for you), and Settings → Downloads holds the Firefox profile, the pace and
  the helper (install or update it from there).
- **Highest quality.** The pages are the image files the site serves, byte for byte - never a
  screenshot, never re-encoded. When the page's own data names larger originals than the reader
  shows, those originals are what is saved.
- **Every page, checked.** comix.to gives no checksums (MangaDex does), so a chapter is saved only
  when every count of its pages agrees: the pages downloaded (all there, numbered 1 to N, each a
  whole image), the reader's own numbering ("1 / 192"), its page bar, the site's own page list (the
  answer its reader got - also checked to name the very images downloaded; when the site sends it
  encrypted it is said so, not counted) and the size each page was shown at. Anything off and
  nothing is saved. The chapter list's Pages column shows `192 ✓` for a chapter that checked out
  (MangaDex ones too - their checksums), and a chapter's **Page check** lists every check.
- **Politely.** One chapter at a time, read at a reader's pace (`browser_scroll_seconds` per screen),
  a pause between chapters (`browser_chapter_pause_seconds`), and nothing fetched twice: the pages
  are the ones the reader already loaded. A chapter already here and whole is checked on disk, with
  no browser at all. The chapter list is read only as far as needed, each page opened by its own
  address (`?page=N` - never by clicking its pager, which comix.to's firewall answers with a check),
  `browser_list_pause_seconds` apart: its first and last pages list every chapter between (2 page
  loads instead of 21 for an 82-chapter manga), and a chapter about to be downloaded is looked up
  on the page it should be on - usually 1-2 page loads, every group's upload of it found. Every
  page read is kept in the project's `comix-uploads.json`, so none is read twice.
  It is fetched at most every 15 minutes (kept for a day).
- **A check mid-way** (the site's own "verify you are human" inside the page) pauses the helper: its
  tab comes to the front, its button shows `!`, remanga says so, and it carries on once you solve it.
- **Security.** remanga and its helper share a secret key made for your copy
  (`global/browser-helper/pairing-key`, built into your helper, never committed): every request
  and every job carries an HMAC of it over a fresh nonce, so no other program on the computer and
  no web page can give the helper work, pose as it, or replay a request. remanga only answers
  `127.0.0.1`/`localhost` (no DNS rebinding) and never a web page's request. The helper opens only
  the sites it knows, reads a page only while its tab is still on one of them, and fetches nothing
  a page merely names - only images from hosts the reader itself loaded, never this computer or the
  local network, and the site's cookies go only to the site. What a site says a chapter is (its
  number, id, link) is checked before it becomes a folder or a link, and a page must be a whole
  image of at most 50 million pixels (a decompression bomb is refused). The key, your Mozilla API
  key, the built helper and the saved page snapshots are readable only by you.
- When the site changes its reader, the last page the helper looked at is in `.cache/browser/` -
  what to read to fix `remanga/plugins/browser/extension/reader.js`.

## Marking the panels

```bash
./run.sh mark -p MyMangaTitle -c 1-5
```

or **Mark panels** in a chapter's menu. It opens one browser tab for every chapter you picked:

- **Detect** runs MAGI v3 over the pages and draws the panels it finds (a GPU takes a few seconds a
  page; without one, mark by hand).
- Fix what it got wrong: drag a box, resize it, delete it, draw a missing one, mark a full page as
  one panel, or press **S** with the mouse on a mark to split it there - across (top / bottom) or
  down (left / right), whichever **Options → S splits a mark** is set to. **Ctrl+Z** undoes the
  last change on the page, a Detect or Remark included. The sidebar lists the pages and what each
  one has.
- The reading order follows the manga's direction (right to left for Japanese), and the panel
  numbers show it.
- **Save** writes the chapter's `crops.json` and moves to the next chapter in the tab.

The marks are yours: nothing overwrites them, and Reset keeps them. Marking only saves the marks;
**Create panels** in the chapter's menu cuts them out (Make PDF also cuts them again whenever the
marks are newer than the panels). **Remark panels** throws the saved marks (and the panels cut from
them) away and opens the marker to mark again from scratch - MAGI, or the gutters on a long strip,
propose every panel afresh.

### Long-strip manga (webtoons)

A webtoon chapter arrives from MangaDex as a few very tall images, sliced wherever the uploader
chose, often straight through a panel. remanga recognises one by MangaDex's "Long Strip" tag
(recorded as `"layout": "long_strip"` in project.json when the project is made) or, for a project
without that line, by the chapter's images being several times taller than they are wide. Write
`"layout": "pages"` or `"long_strip"` in project.json to decide it yourself. Both are layout
plug-ins (`remanga/plugins/pages/`, `remanga/plugins/long_strip/`).

MAGI is trained on printed pages, so a webtoon's panels are found by several methods voting
together: gutters (rows of one colour - trusted only once the strip proves that colour separates
panels, so a flat sky never cuts one), borders with no gutter (a straight cut across the width, a
new picture starting, two scenes' colours meeting), small pieces such as a floating bubble glued to
the nearest panel, plain fades dropped, and a picture taller than 1.8x the width split only at a
genuinely calm stretch - never through a face. A tall picture with no calm place stays whole and is
flagged in the list. On a real chapter this matched the user's own marks at F1 0.86, against 0.69
for the gutter splitter it replaced.

**Mark panels** on such a chapter opens the **Strip Marker**: the whole chapter as one strip,
scrolled top to bottom as you would read it (only the part near the screen is loaded, so a long
chapter stays smooth). Every panel is a band in its own colour with a big number; rows no panel
covers are hatched, so you can see what would be left out.

- **＋ New panel** (or **A**), then drag down the strip over its art - or just drag on bare strip
  or on the empty canvas beside it; the box you drag out is shown as you go. A panel is always the
  strip's full width - only its rows are marked. **Click** the canvas beside the strip to deselect.
  **Double-click** art no panel covers to fit a panel to it. Panels may overlap - a bubble can
  belong to two.
- **Click** a panel to focus it: everything else dims and a bar shows its rows, with **Split**
  (**S**, at the mouse), **Merge with next** (**M** - the fix for a panel cut in half) and
  **Delete**. Drag it to move, drag its top or bottom edge to resize; edges snap to gutters
  and other panels (hold **Shift** not to).
- **↑/↓** nudge the selected edge (**Shift** ×10, **Tab** picks top / bottom / whole), **J/K**
  step through the panels, **N** starts a line after the last one, **R** proposes them all again,
  **C** clears, **+/-/0** zoom, **G** shows or hides the gutters, **Esc** leaves focus.
- **Ctrl+Z / Ctrl+Y** undo and redo, every change is saved as you go (`strip_marks.json`), and
  **Finish** (Ctrl+S) saves them and closes - it cuts nothing.

**Create panels** in the chapter's menu then cuts the strip into `strip/` pages between the panels (overlapping ones always on one page)
and `crops.json` is written from them, cut exactly as marked; the downloaded images in `pages/` are
never touched. From there the PDF and the video work as for any manga.

## The narrator

Three engines built in (each a plug-in - see [Plug-ins](#plug-ins)), switchable in **Settings → Narrator engine**;
each keeps its own voice, so switching back and forth changes nothing else. A chapter narrated by another one is
narrated again.

**The first time remanga opens** it looks at the machine - the GPU and its memory, the RAM, the free disk, the
internet - and asks which engine to narrate with, listing only the ones this machine can run (and why the others
can't). The one picked gets its recommended settings: its best voice and how it is read. Settings → Narrator
engine changes it later.

**The sound is the narrator as it read:** no effects, no pauses cut, the whole chapter read in as few
takes as the engine handles well (one, for most), with a narrator's pause (420 ms) between takes. Three things are yours to set: the
**Volume** of the finished chapter (-14 LUFS, YouTube's level, by default), the **Background
music**, and how far under the voice the **Music volume** sits. (The narration presets and the voice
effects - compressor, bass, microphone, breath, phone - are kept on the branch
`backup/presets-effects-2026-10-25`, as are the Ming-3.0-tts, Qwen3-TTS and IndexTTS-2.5 engines.)

| Engine | Voice | Speed | Needs |
|---|---|---|---|
| **Fish Audio Drama 3** | the #1 open-weights voice on Artificial Analysis's leaderboard (Oct 2026); no named voices - a narrator described in words (deep male, warm male, warm female, calm female, or the model's own choice) under a fixed seed. Drama 3 is a voice-cloning model, so the first time a voice is used it reads a reference line in it and keeps that as a voice file; every page is read from the file, a sentence at a time, so it is the same narrator all chapter and every chapter. A take that leaves words out, or sticks, is read again. (`tts.drama3.voice_file: false` reads in the model's own voice instead - smoother, but the narrator changes from page to page.) Fish Audio Community License - free under US$500k a year of revenue, and say "Built with Fish Audio" | about 0.65x real time on a 3060 - a 16-minute chapter in about 26 minutes | a GPU with Vulkan and 6 GB+ of memory, its memory and the RAM together 26 GB+ (the experts that don't fit the GPU run on the CPU), 22 GB of disk |
| **Kokoro-82M** | its own studio voices, picked from a list | a chapter in seconds | nothing special - runs on the CPU too |
| **Edge voices** | Microsoft Edge's online US neural voices (Guy, Andrew, Brian, Christopher, Aria, Jenny...) - it is Edge's Read Aloud service, not a licensed API: check Microsoft's terms before monetizing | a 14-minute chapter in ~90 seconds | the internet, no GPU |

**Hearing them first:** `./run.sh voices` (or Settings → Hear the voices) reads one line in every
voice the engine has, into `global/voice/samples/<engine>/`, with a text file saying which is which.
The model loads once for the whole set.

An engine's environment and weights download the first time you use it, not at install time.

## Versions: nothing is lost, nothing is made twice

Everything slow that remanga makes - each narration take, its word timings, each finished video - goes
into the project's `store/`, filed under the exact recipe that made it (the text, engine, voice, seed,
music file, levels, video settings, panels, intro). A store file is written once, in one step, with its
SHA-256 recorded, and is read-only from then on; a chapter's own folders (`audio/`, `subtitles/`,
`video/`) only link to it. So:

- **Nothing is made twice.** Before a take is narrated or a video rendered, remanga looks for that exact
  recipe; changing one page's narration re-narrates only that page, switching the voice back brings the
  old takes back at once, and the same settings again cost seconds. Every file is checked against its
  SHA-256 before it is reused; a damaged one is never used - it is moved to `store/damaged/` and made
  again.
- **Nothing is overwritten or lost.** Every video made of a chapter is a *version* of it, kept with what it
  was made with. The chapter menu's **Versions** lists them (the chapter list's **Ver** column counts
  them): pick one to use it again - its narration and video come back from the store, nothing is made
  again - or delete it (only the files no other version uses go). What a chapter held before versions
  existed is kept as its first version the first time it is made again. A long video made again keeps the
  one before it in the store too (listed in its `long.json`).
- **One job per chapter.** A chapter being narrated, mixed or rendered is locked: the queue, a menu action
  and another terminal can never write it at once.
- **Kept: what is slow to make.** Every version's takes, word timings and video stay; the mixed master
  (large, and made again in about 30 seconds) is kept for the version in use only.

**Don't trust the reuse? Make it fresh.** The chapter menu's **Make video fresh** makes everything again
from scratch - no take or video reused - and keeps it as a new version beside the others, so nothing is
replaced. At the end it says how its takes compare with the ones made before: byte for byte, or the same
reading (the same words at the same moments - a model on a GPU never repeats its arithmetic exactly).
**Versions → c (Check files)** reads every file of every version back against its SHA-256 and shows ✓ or
what is wrong, at a glance.

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

**A chapter that is not out in English** is still downloaded, in another language: MangaDex's
English upload is taken when there is one, and otherwise the newest upload in any language
(`downloader.fallback_languages`, `["*"]`; list languages there, like `["es", "*"]`, to prefer some, or
`[]` for English only). The chapter list shows such a chapter's language (`id`, `pt-br`, ...), and its
PDF says `lettering: Indonesian (id)`, so the LLM reads the bubbles in that language and narrates in
English as always. In a project with several sites, a chapter in English on any of them comes first.

The LLM replies with one JSON block in two sections. Paste all of it into
`chapters/chapter_N/narration.json` (the code fence can come along):
- `narration` - one entry per panel, in reading order: the narration read while that panel is on
  screen, or a skip reason for a panel that is not story (a credits box, a title);
- `memory` - the story so far after this chapter. The next chapter's PDF reads it straight from this
  file and prints it on its first page, so continuity carries forward with no extra step.

**Make video** checks the reply first. If a panel is missing, has no narration, or is skipped for no
reason, nothing is narrated: the problems are listed and written to `pdf/chapter_N/fix_request.md` -
paste that into the same chat and save the new reply over `narration.json`. It also warns (without
stopping) when a panel's narration looks too short, or uses quotation marks or contractions, which
the voice reads badly. `?`, `!` and `...` are welcome where a sentence really is a question, an
exclamation or a trailing-off. Whatever no voice can say - emoji, symbols like ★ or ♪, Japanese,
Chinese or Korean text - is taken out before the narrator reads it (`narration.json` keeps it), and
accents, money and fractions are written plainly (Chloé -> Chloe, $5 -> 5 dollars, 3/4 -> 3 out of 4).

Make each chapter's PDF after pasting the previous chapter's narration, so its story so far is up to
date (the PDF step says so when an earlier chapter has none yet).

## How the files work

```
projects/<name>/
  project.json            the manga, its reading direction
  chapters/chapter_N/
    pages/                downloaded pages
    strip_marks.json      a long strip's panels, from the Strip Marker (rows of the whole chapter)
    strip/, strip.json    a long strip's pages, cut between those panels
    crops.json            the panel marks from the Panel Marker
    panels/               the panels cut from the pages
    narration.json        the LLM's reply (or the Writer's): narration + memory
    narration_review.json what the Reviewer flagged, for the LLM's fix pass
  pdf/chapter_N/          panels_1.pdf, ... and fix_request.md
  audio/chapter_N/        one clip per panel + audio_timing.json
  audio_modified/chapter_N/  the mixed track
  video/chapter_N/        the video
  video/long/ch1-5/       a video of several chapters (Long video)
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

### Long videos

One video of several chapters - chapter n to chapter m. Pick them on the Chapters screen (`space` on
the first, `r` on the last) and choose **Long video...**:

- **Join chapter videos** - each chapter's video as it is now, one after another, with the intro
  once at the front. A chapter whose video is missing or out of date for the current settings is
  rendered first, and one never narrated is narrated first; the rest is a stream copy, seconds
  for an hour of video.
- **Make from source** - every chapter remade from its pages, panel marks and narration.json
  (Remake from source, chapter by chapter), then joined.
- **Delete long videos...** - a checklist of the long videos holding any picked chapter. Only the
  long video goes; every chapter keeps its own.

They live in `video/long/ch1-5/` (`ch1-3+7` when chapters were skipped), with
`logs/long_ch1-5.log`. Each chapter's sound is fitted to its picture's exact length before the
join, so one chapter can never pull the ones after it out of sync.

Settings are one set for every project: whichever screen you open them from, a change applies
everywhere.

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

## Plug-ins

Everything that comes in more than one kind is a plug-in, and the rest of remanga never names a
particular one:

| Kind | What it is | Built in (`remanga/plugins/`) |
|---|---|---|
| `tts` | a narrator engine: its settings block, synthesizer, worker, Settings rows | `kokoro/`, `drama3/`, `edge_tts/` |
| `tool` | an isolated environment (`.tools/venv-<name>`) | registered by `kokoro/`, `drama3/`, `edge_tts/`, `magi/`, `faster_whisper/` |
| `layout` | how a chapter is marked into panels | `pages/` (Panel Marker + MAGI), `long_strip/` (Strip Marker) |
| `source` | where manga come from | `mangadex/` |
| `job` | something the queue can do to a chapter | `jobs/` |

Each built-in is one folder holding all of its own code; its `__init__.py` only registers a short
description that names that code. `./run.sh plugins` lists what is loaded and where from.

**Each tool sets itself up:** every plug-in that runs in its own environment (Kokoro, Drama 3,
Edge voices, MAGI, faster-whisper) has a `setup.py` in its folder that builds that environment and fetches its
weights. remanga runs it the first time the tool is used, from `bootstrap.sh`, or on request:
`./run.sh setup --tool drama3` (no `--tool`: the chosen narrator and MAGI). Each also runs on its
own: `.venv/bin/python -m remanga.plugins.kokoro.setup [--force] [--no-weights]`.

**Your own:** drop a `.py` file or a package into the top-level `plugins/` folder (see
`plugins/README.md` and `plugins/_example_job.py`), or ship a package with a `remanga.plugins` entry
point. One with the same kind and name as a built-in replaces it; one that fails to load is reported
and skipped. A new narrator engine appears in Settings, and in config.json as `tts.<name>`, by
itself.

## Settings

Every setting is in `config.json` and applies to every project:

| Key | Default | Meaning |
|---|---|---|
| `tts.engine` | picked the first time remanga opens | who narrates - any `tts` plug-in: `drama3` (best quality, slow, a big GPU), `kokoro` (fixed voices, seconds a chapter, any machine) or `edge` (online, fast) |
| `tts.drama3.voice` / `.seed` / `.voice_file` | `deep_male` / 1 / true | Drama 3's described narrator (`deep_male`, `warm_male`, `warm_female`, `calm_female`, `model`), the seed that picks it - another seed is another narrator - and whether takes are read from a voice file of it (`checkpoints/speech_cpp/voices/`) |
| `tts.drama3.gpu_headroom_gb` | 2.5 | GPU memory kept free for Drama 3's working buffers; 0 ran a 12 GB card out of memory |
| `tts.kokoro.voice` / `.speed` | `af_heart` / 1.0 | Kokoro's voice and pace - 1.0 is its own (about 185 words a minute); past about 1.35 it drops the pauses between sentences |
| `tts.volume_boost_db` | 0 | gain on each clip; leave at 0 - `audio.volume_lufs` sets the level |
| `audio.bgm_enabled` / `bgm_path` | off / - | background music |
| `audio.bgm_below_voice_lu` | 18 | how far the music's LOUD PARTS sit under the voice, in LU - the music measured by its loud parts (a chorus, a drop), per track and chapter, so every music file, loud or quiet, peaks at the same level under the words (14 balanced, 18 subtle, 20 barely there) |
| `audio.volume_lufs` | -14 | how loud the finished chapter is (Settings - Volume): measured, then one linear gain over the whole mix, with a peak guard only where that gain would pass -1 dBTP. -14 is YouTube's level |
| `video.width` / `height` / `fps` | 1920 / 1080 / 24 | video size - 2560x1440 and 3840x2160 keep big panels sharp (see the quality warning), at a slower render |
| `video.max_upscale` | 3 | how far a small panel may be enlarged to fill the frame; 0 means no cap |
| `video.background_style` | `blur` | `blur` (the panel, blurred) or `solid` (`background_color`) |
| `pdf.max_mb` | 50 | largest PDF file |
| `marker.port` / `writer.port` / `reviewer.port` | 8765 / 8767 / 8766 | where each web UI listens |
| `marker.magi_enabled` / `magi_panel_score_threshold` | true / 0.5 | MAGI v3's panel detection in the Panel Marker, and how sure it must be |
| `marker.min_mark_ratio` | 0.03 | the smallest a panel mark may be, as a fraction of the page's shorter side. A drag under it makes no mark (the box says so while you drag), and a resize handle stops there instead of collapsing a panel to a sliver |
| `cropper.margin_padding_pixels` / `snap_to_gutters` | 8 / true | breathing room around a cut panel, and snapping its edges to the real gutters |
| `downloader.language` | `en` | MangaDex translation language |
| `downloader.fallback_languages` | `["*"]` | the languages a chapter not out in `language` is taken in, in order; `*` = any (the newest upload), `[]` = none |
| `downloader.browser_profile` | `""` | the Firefox profile a [browser site](#sites-that-need-a-real-browser) is downloaded in (Firefox's default when empty) |
| `downloader.browser_chapter_pause_seconds` / `browser_scroll_seconds` / `browser_list_pause_seconds` | 10 / 0.8 / 8 | the pause between two chapters, between two screens of one, and between two pages of the chapter list, each varied by ±30% |
