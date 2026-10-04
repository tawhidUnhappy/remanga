---
name: remanga-thumbnails
description: How to make a remanga chapter's YouTube thumbnail (1280x720 from its own cut panels, yellow labels + arrows), title and description. Use when the user asks for a thumbnail, title, description or upload text for a recap video.
---

# remanga: thumbnails, titles, descriptions

First done 2026-09-30 for chapter 1 of HimeSama, IDied and IReincarnated (user asked for all three;
black and white is fine - the panels are manga). `specs.example.json` is exactly those three (plus Golem Master, 2026-10-04):
`thumb.py render` on it reproduces the shipped thumbnails pixel for pixel.

Outputs go beside the video, named like it:
`projects/<P>/video/chapter_<N>/<P>_ch<N>_{thumbnail.jpg,title.txt,description.txt}`.
**Make video / Remake from source empty that folder** (`workflow/cleanup.drop_audio_and_video`), so a
re-render deletes them - rerun `thumb.py render` from the spec and rewrite the text afterwards, or
tell the user to copy them out first.

## Style (the user's references: /mnt/datadisk/thumbnail_examples)

One strong image, then 1-3 SHORT all-caps labels in yellow `#FFE600` Anton with a thick black outline,
each with a fat yellow block arrow at the face it names ("VILLAIN", "SECRET SSS GENIUS", "YANDERE").
Real art only, never generated. Bottom-right corner kept clear (YouTube's duration badge). Same house
style as the AMV Shorts (`/mnt/datadisk/AMV_CD/amv/shorts/thumb.py`; font from
`AMV_CD/assets/fonts/Anton-Regular.ttf` - remanga has no fonts of its own).

What worked for a recap: **two panels side by side, one per side of the hook**, a black divider,
one label each - the two roles of the premise:

| chapter | left | right |
|---|---|---|
| HimeSama | Sofia "please kindly die" -> SADIST PRINCESS | Alfred sweating -> DOOMED TUTOR |
| IDied | Astrefia with wings -> VAMPIRE MOM | the baby -> LEGENDARY HERO |
| IReincarnated | Lloyd smirking -> VILLAIN | Cain on his knees -> REAL HERO |
| Golem Master | tired salaryman (001_003_02) -> COMPANY SLAVE | elf from the title spread (001_002_02, zoom 2.8 top-left: clears the logo and caption boxes) -> GOLEM MASTER |

## Steps (run with remanga's `.venv/bin/python`)

1. **Read the story** - `audio/chapter_N/audio_timing.json` `panels[].text` joined is the whole
   narration. Find the hook: who the main character is and what the twist makes them.
2. **Pick panels**: `thumb.py sheet <Project> [chapter]` writes named contact sheets of every cut
   panel to /tmp/remanga-thumbs/. Look at them, then view the few candidates at full size. Prefer a
   face turned toward the viewer, and panels big enough to scale up (a 250px-wide panel still reads as
   manga line art at 2x, but it's soft). A colour cover panel usually carries scanlation/series text.
3. **Crop**: write the spec (tiles only, `labels: []`), `thumb.py grid spec.json`, and LOOK at the
   gridded render. Fix `zoom`/`cx`/`cy` until each tile shows a face and upper body, not a torso.
   **Crop out scanlator watermarks** (HimeSama's Alfred panel has "KUMO TRANSLATION" in its top ~10%:
   zoom 1.6 with cy 0.45 clears it, zoom 1.9 cut his head off).
4. **Labels**: read `to` (the face) and `at` (clear space near it) off the grid, in canvas fractions.
   Never guess an arrow - the AMV skill's lesson: guessed arrows point at nothing. Keep labels off the
   divider (HimeSama's DOOMED TUTOR straddled it at x 0.64, fine at 0.67). Size 72-90; two short
   lines beat one long one.
5. `thumb.py render spec.json` writes the thumbnail beside the video. **View it** before saying done.

## Title

Match the user's shipped Shorts titles (`/mnt/datadisk/shorts/*/..._title.txt`): Title Case on every
word, the premise as a story sentence, ONE all-caps emphasis word, ending `| Manga Recap`. YouTube
cuts at 100 characters - the three shipped ones are 93-98. Examples:

- Genius Reincarnates As The Tutor Of A Sadistic Princess Who Kills Him In EVERY Route | Manga Recap
- He Reincarnated As The Villain Leader, So He Kicked HIMSELF Out Before The Revenge | Manga Recap

## Description

In this order: a two-paragraph hook from the chapter (setup, then twist - no ending spoilers past
the chapter); `Manga:` official English title, the romaji title in brackets; `Story: ... · Art: ...`;
`Chapter N`; 5-7 hashtags (#mangarecap #manga #isekai ...); fair-use note; `Narration voice: AI
text-to-speech.` (honest, and YouTube asks for synthetic-content disclosure - the user may drop it);
`Support the official release of <title>.`

**Titles and credits come from MangaDex, never from memory:**
`curl -s "https://api.mangadex.org/manga/<manga_id>?includes[]=author&includes[]=artist"` -
`manga_id` is in `projects/<P>/project.json`; English title = the `en` entry of `altTitles`,
people = `relationships` of type author/artist. When MangaDex lists several artists without roles
(IDied: Hiyashimira's, Hino Tomoyuki), credit all as Art and tell the user - never invent who did what.
