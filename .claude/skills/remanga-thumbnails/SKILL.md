---
name: remanga-thumbnails
description: How to make a remanga chapter's YouTube thumbnail (1280x720 from its own cut panels, yellow labels + arrows), title and description. Use when the user asks for a thumbnail, title, description or upload text for a recap video.
---

# remanga: thumbnails, titles, descriptions

First done 2026-09-30 for chapter 1 of HimeSama, IDied and IReincarnated (user asked for all three;
black and white is fine - the panels are manga). `specs.example.json` is exactly those three (plus Golem Master, 2026-10-04, and If Her Flag Breaks, 2026-10-05):
`thumb.py render` on it reproduces the shipped thumbnails pixel for pixel.

## One set per project (since 2026-10-06)

The user wants ONE title, description and thumbnail per project, not one per chapter. They live in
`projects/<P>/upload/` and are never deleted by a re-render:

- `title.txt` - the title; ` ({num})` is appended unless it holds `{num}` itself
- `description.txt` - may hold `{num}` and `{chapter}`
- `thumbnail.json` - one spec (format: `remanga/video/thumbnail.py`); tiles may name their own
  `chapter`; a label may hold `{num}` and may leave out `to` (no arrow) - the `CH {num}` badge

`{num}` = chapter zero-padded (01, 05.5, 01-02 for a long video), `{chapter}` = Chapter 1 / Chapters 1-2.
`remanga/workflow/upload.py` stamps them beside every video after Make video, Remix and a long-video
join: `<P>_ch<N>_{title.txt,description.txt,thumbnail.jpg}`. After editing the templates run
`remanga upload -p <P>` to restamp every finished video. So: write the series hook, not chapter 1's -
the same text has to fit chapter 30. Keep the title at 92 characters or under (` (01-02)` is 8 more,
YouTube cuts at 100).

## Style (the user's references: /mnt/datadisk/thumbnail_examples)

One strong image, then 1-3 SHORT all-caps labels in yellow `#FFE600` Anton with a thick black outline,
each with a fat yellow block arrow at the face it names ("VILLAIN", "SECRET SSS GENIUS", "YANDERE").
Real art only, never generated. Bottom-right corner kept clear (YouTube's duration badge). Same house
style as the AMV Shorts (`/mnt/datadisk/AMV_CD/amv/shorts/thumb.py`; the same Anton font, copied
into remanga's `assets/fonts/` with its OFL licence).

What worked for a recap: **two panels side by side, one per side of the hook**, a black divider,
one label each - the two roles of the premise:

| chapter | left | right |
|---|---|---|
| HimeSama | Sofia "please kindly die" -> SADIST PRINCESS | Alfred sweating -> DOOMED TUTOR |
| IDied | Astrefia with wings -> VAMPIRE MOM | the baby -> LEGENDARY HERO |
| IReincarnated | Lloyd smirking -> VILLAIN | Cain on his knees -> REAL HERO |
| Golem Master | tired salaryman (001_003_02) -> COMPANY SLAVE | elf from the title spread (001_002_02, zoom 2.8 top-left: clears the logo and caption boxes) -> GOLEM MASTER |
| If Her Flag Breaks (upload/, series) | Souta + Akane under five friendship flags, "I WANNA BREAK THEM" bubble (002_031_05 from ch2, cy 0.54) -> FLAG BREAKER at Souta | Nanami colour cover (same box) -> NO FLAG?!; `CH {num}` badge top-left |
| If Her Flag Breaks (ch1, old) | Souta beside a flag on a classmate's head (001_034_02, zoom 1.2 cx 0.4: crops out a YEAH. bubble) -> FLAG BREAKER | Nanami from the COLOUR cover (page 001_002.jpg, box 530,60,1085,1000 - between the title text and the spine) -> NO FLAG?! |

## Steps (run with remanga's `.venv/bin/python`)

1. **Read the story** - `audio/chapter_N/audio_timing.json` `panels[].text` joined is the whole
   narration. Find the hook: who the main character is and what the twist makes them.
2. **Pick panels**: `thumb.py sheet <Project> [chapter]` writes named contact sheets of every cut
   panel to /tmp/remanga-thumbs/. Look at them, then view the few candidates at full size. Prefer a
   face turned toward the viewer, and panels big enough to scale up (a 250px-wide panel still reads as
   manga line art at 2x, but it's soft). A colour cover panel usually carries scanlation/series text.
   **Check the colour pages too** (pages/ before the first panel, often never cut into panels): the user
   wants the cute heroine in colour when there is one (If Her Flag Breaks, 2026-10-05). A tile takes
   `"page": "001_002.jpg", "box": [l, t, r, b]` instead of `panel` - box out the logo, title text and spine.
3. **Crop**: write the spec (tiles only, `labels: []`), `thumb.py grid spec.json`, and LOOK at the
   gridded render. Fix `zoom`/`cx`/`cy` until each tile shows a face and upper body, not a torso.
   **Crop out scanlator watermarks** (HimeSama's Alfred panel has "KUMO TRANSLATION" in its top ~10%:
   zoom 1.6 with cy 0.45 clears it, zoom 1.9 cut his head off).
4. **Labels**: read `to` (the face) and `at` (clear space near it) off the grid, in canvas fractions.
   Never guess an arrow - the AMV skill's lesson: guessed arrows point at nothing. Keep labels off the
   divider (HimeSama's DOOMED TUTOR straddled it at x 0.64, fine at 0.67). Size 72-90; two short
   lines beat one long one.
5. Save it as `projects/<P>/upload/thumbnail.json`, run `remanga upload -p <P>`, and **view** a
   stamped thumbnail (a long one too - its `CH 01-02` is wider) before saying done.

## Title

Match the user's shipped Shorts titles (`/mnt/datadisk/shorts/*/..._title.txt`): Title Case on every
word, the premise as a story sentence, ONE all-caps emphasis word, ending `| Manga Recap`. YouTube
cuts at 100 characters - the three shipped ones are 93-98. Examples:

- Genius Reincarnates As The Tutor Of A Sadistic Princess Who Kills Him In EVERY Route | Manga Recap
- He Reincarnated As The Villain Leader, So He Kicked HIMSELF Out Before The Revenge | Manga Recap

## Description

In this order: a two-paragraph hook from the chapter (setup, then twist - no ending spoilers past
the chapter); `Manga:` official English title, the romaji title in brackets; `Story: ... · Art: ...`;
`{chapter}`; 5-7 hashtags (#mangarecap #manga #isekai ...); fair-use note; `Narration voice: AI
text-to-speech.` (honest, and YouTube asks for synthetic-content disclosure - the user may drop it);
`Support the official release of <title>.`

**Titles and credits come from MangaDex, never from memory:**
`curl -s "https://api.mangadex.org/manga/<manga_id>?includes[]=author&includes[]=artist"` -
`manga_id` is in `projects/<P>/project.json`; English title = the `en` entry of `altTitles`,
people = `relationships` of type author/artist. When MangaDex lists several artists without roles
(IDied: Hiyashimira's, Hino Tomoyuki), credit all as Art and tell the user - never invent who did what.
