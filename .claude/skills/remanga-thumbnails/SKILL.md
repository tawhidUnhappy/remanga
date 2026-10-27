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
- `description.txt` - may hold `{num}`, `{chapter}` and `{timestamps}` (a long video's YouTube
  chapter list, `0:00 Chapter 1` a line, from long.json `starts`; empty for a chapter's own video,
  and the blank lines around it close up)
- `thumbnail.json` - one spec (format: `remanga/video/thumbnail.py`); tiles may name their own
  `chapter`; a label may hold `{num}` and may leave out `to` (no arrow) - the `CH {num}` badge

`{num}` = chapter zero-padded (01, 05.5, 01-02 for a long video), `{chapter}` = Chapter 1 / Chapters 1-2.
`remanga/workflow/upload.py` stamps them beside every video after Make video, Remix and a long-video
join: `<P>_ch<N>_{title.txt,description.txt,thumbnail.jpg}`. After editing the templates run
`remanga upload -p <P>` to restamp every finished video. So: write the series hook, not chapter 1's -
the same text has to fit chapter 30. Keep the title at 92 characters or under (` (01-02)` is 8 more,
YouTube cuts at 100).

## A/B variants (user request, 2026-10-14)

`title_b.txt`, `thumbnail_b.json`, `_c`, ... beside the plain ones are stamped too - one per angle
of the hook, title and thumbnail paired by letter, for YouTube Test & Compare. With variants, each
video gets a folder per letter beside it - `A/` `B/` `C/`, each holding title.txt and thumbnail.jpg
(user: flat `_b`/`_c` files were confusing to pair), and the ONE description is written once beside
the video as `<P>_ch<N>_description.txt` (user, 2026-10-27: not a copy per folder); a single set stays
flat files. `description_b.txt`, ... give a set its own description inside its folder (user asked for three, 2026-10-24); a set without one then gets description.txt. **Newer word (2026-10-27, Lilina-san): "ab testing material (thumbnail, title) three times and make description just one time"** - three title/thumbnail pairs (A/B/C, YouTube Test & Compare's maximum) and ONE description.txt shared by all; only write description_b/_c when asked. YouTube's Test & Compare only tests titles and thumbnails, so a B/C description is pasted by hand. Each variant a different angle (premise / role swap /
power), not the same idea reworded. Keep graphic gore out of a thumbnail (Ghost Story Club's bleeding eye 001_114_01): YouTube restricts it, which costs reach - a creepy face sells as well.

**The user's corrections (2026-10-14), over the style below:** never let an arrow touch a face - a
label sits under or beside the face, arrows are optional and stop short; sharp B&W panels beat
low-resolution colour pages (chapter 1's colour spread is only 1000x719 - it looked soft). The user
gave full creative freedom: labels may be any `color`, tiles may be duotoned (`tint` [dark, light])
and firmed (`contrast`) so B&W art still pops - blue for the old villain, red for the new.

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
| IReincarnated A (upload/, 2026-10-14) | Lloyd's menacing smirk 001_013_03 | Cain stunned 001_027_03; one line across the bottom HE KICKED HIMSELF OUT?!, red VILLAIN top-left, no arrows |
| IReincarnated B (thumbnail_b) | villain Lloyd "So long, Cain!" 001_014_02, blue duotone -> OLD VILLAIN | Cain's grin 4.2_017_03, red duotone -> red NEW VILLAIN?! |
| IReincarnated C (thumbnail_c) | one tile: Lloyd grinning, hand out, 4.2_006_03 zoom 1.35 (crops out both bubbles), cyan duotone; red STEALS + yellow ANY SKILL | |
| Ghost Story Club A (upload/, 2026-10-18) | principal's swollen grin 001_056_02 (zoom 1.08 cy 0.47 clears his bubble), w 0.55 -> red WELCOME | teacher frozen in terror 001_067_01 zoom 1.15 -> YOU'RE NEXT under her chin |
| Ghost Story Club B (thumbnail_b) | Lee Jun's blank stare 001_063_01 zoom 1.25 cy 0.47 -> HE DIED. | the "Restarting from the checkpoint." window 001_117_01 zoom 1.3 cx 0.6 -> red LOOP?! |
| Ghost Story Club C (thumbnail_c) | teacher's cheeks bulging 001_076_01 zoom 1.9 cx 0.74 cy 0.58 -> red CURSED top-left | Lee Jun panicking 001_084_01 zoom 1.55 cx 0.38 cy 0.43 -> NO WAY OUT; CH badge bottom-left |
| Lilina-san A (upload/, 2026-10-27) | colour COVER page 001_001.jpg box [395,300,912,918] (right edge stops before the orange logo, which starts ~x 920 at her shoulder; heart hands kept) w 0.47 | Rex sweating, bread in arms 001_014_02 cy 0.47 (caption box below cropped out) -> SHE HATES ME?! (was WHY ONLY ME?!, which repeated the title's "every adventurer but me") |
| Lilina-san B (thumbnail_b) | cold stare 001_014_01 zoom 1.5 cx 0.57 cy 0.475 (clears her bubble's tail), navy/ice duotone -> light-blue ICE COLD | blushing, hands on cheeks 001_050_01 zoom 1.8 cx 0.69 cy 0.33, maroon/pink duotone -> SECRETLY IN LOVE |
| Lilina-san C (thumbnail_c) | roaring red bear 001_030_01 zoom 1.5 cy 0.3, maroon/peach duotone -> ONE HIT (116) | Rex calm 001_034_02 zoom 2.1 cx 0.77 cy 0.62 (zoomed past Belze and a bubble tail) |
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

**The user wants the manga link and the chapter range in every set (2026-10-14):** the range is
`({num})` on the title, the `CH {num}` badge on the thumbnail and `▶ {chapter}` in the description;
the link is `📖 Read the manga: <manga_url from project.json>` in the description.

**Viral asks (2026-10-14):** what the research supports - an expressive face, 3-4 words a label,
thumbnail and title each carrying half the hook (never the same words), the hook's keywords in the
first ~150 characters of the description, chapter timestamps on long videos, 5 hashtags (the first
three show above the title). "Fanservice" means the cute heroine in colour and the official Harem
tag - never a sexual angle on a character the story calls young (Lilina is "a young beastkin girl").

In this order: a two-paragraph hook from the chapter (setup, then twist - no ending spoilers past
the chapter); `Manga:` official English title, the romaji title in brackets; `Story: ... · Art: ...`;
`{chapter}`; 5-7 hashtags (#mangarecap #manga #isekai ...); fair-use note; `Narration voice: AI
text-to-speech.` (honest, and YouTube asks for synthetic-content disclosure - the user may drop it);
`Support the official release of <title>.`

**Titles and credits come from MangaDex, never from memory:**
`curl -s "https://api.mangadex.org/manga/<manga_id>?includes[]=author&includes[]=artist"` -
`manga_id` is in `projects/<P>/project.json`; English title = the `en` entry of `altTitles`,
people = `relationships` of type author/artist. A project from comix.to has no MangaDex id: search `manga?title=...` instead (Ghost Story Club: authors OnlyFun, Parrot Kim; artist HayaroB - no roles given, so none are credited). When MangaDex lists several artists without roles
(IDied: Hiyashimira's, Hino Tomoyuki), credit all as Art and tell the user - never invent who did what.
