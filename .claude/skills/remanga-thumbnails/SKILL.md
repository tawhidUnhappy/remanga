---
name: remanga-thumbnails
description: How remanga's upload set works and how to make a good one - YouTube titles, 1280x720 thumbnails from the manga's own cut panels (yellow Anton labels, duotones, the CH badge) and the description. Use when making or fixing a project's titles, thumbnails, description or upload text, by the LLM round trip (upload-pdf / upload-from-reply) or by hand (thumb.py, thumbnail.json).
---

# remanga: titles, thumbnails, descriptions

## The upload set

One set per project, used by every video of it - each chapter's and each long video. It lives in
`projects/<P>/upload/` and is never deleted by a re-render:

- `title.txt` - the title; ` ({num})` is appended unless it holds `{num}` itself
- `description.txt` - may hold `{num}`, `{chapter}` and `{timestamps}` (a long video's YouTube
  chapter list, `0:00 Chapter 1` a line, from long.json; empty for a chapter's own video, and the
  blank lines around it close up)
- `thumbnail.json` - one spec (format below); a label may hold `{num}`

`{num}` = the chapters zero-padded (01, 05.5, 01-02 for a long video), `{chapter}` = Chapter 1 /
Chapters 1-2. `remanga/workflow/upload.py` stamps them beside every video after Make video, Rebuild
video and a long-video join. `title_b.txt`, `thumbnail_b.json`, `_c`, ... are A/B variants for
YouTube's Test & Compare (three is its maximum): with variants each video gets a folder per letter
(`A/ B/ C/`, each a title.txt and thumbnail.jpg) and the ONE description is written once beside the
video. `description_b.txt` ... put a description in each folder instead - only when asked for;
Test & Compare tests titles and thumbnails only. After editing the templates, `./run.sh upload -p P`
stamps every finished video again.

## Making it: the LLM round trip

```bash
./run.sh upload-pdf -p P -c 1-3        # the chapters whose panels may be used
# prompts/upload.md + pdf/upload/upload_*.pdf to the LLM; its JSON reply into upload/upload_reply.txt
./run.sh upload-from-reply -p P        # writes the templates, renders upload/preview_a.jpg ..., stamps
```

The PDF offers each chapter's largest panels (an even share of 320 across the chapters - the
artist's emphasis moments) and its colour pages, each with its id stamped, plus the manga's titles,
link and credits (from MangaDex via the source's `get_manga_credits`, cached as `credits` in
project.json), the story so far and the line narrated over each panel. The reply (contract in
remanga-ops) says only WHAT: the image, a box around the face, boxes to keep out, a framing, a tint,
the words. `remanga/upload_plan/framing.py` lays it out and writes an ordinary `thumbnail.json`, so a
weak result can be fixed in the reply (another image, a tighter framing, an `avoid` box) or tuned by
hand. What a reply replaces is kept in `upload/old_<time>/`. Claude can write the reply itself: make
the upload PDF, look at what it offered (`thumb.py offered P` - contact sheets by id), read the boxes
off the chosen images (`thumb.py boxes P ID ...` - each with the reply's 0-1000 grid), write
`upload_reply.txt`, use it, LOOK at the previews.

How `framing.py` crops decides what a reply can achieve:
- The crop's height is the subject box's height divided by the framing's fill (close 0.62, medium
  0.42, wide 0.86), its width the tile's shape; it may shift by up to 30% and tighten to 80% to keep an
  `avoid` box out, but never cuts more than 3% of the subject. So a balloon right beside a face cannot
  be avoided while the subject box takes in the whole head: box just the face, or pick an image whose
  balloons sit clear of it.
- The CH badge takes the first corner - top left, top right, bottom left - that no face box or label
  touches. A tightened crop lifts the face into the top corners; a long label on the right-hand tile
  goes to the top band (YouTube's length stamp holds the bottom right). `upload-from-reply` warns when
  a set gets no badge: box a subject tighter, or swap the tiles.

## Making it by hand

`thumb.py` (this folder, run with remanga's `.venv/bin/python` from the repo root; `offered` and
`boxes` are for the reply, the rest for a hand-made spec):

1. **Read the story** - the narration in `chapters/chapter_N/narration.json`. Find the hook: who the
   main character is and what the twist makes them.
2. **Pick panels**: `thumb.py sheet <Project> [chapter]` writes named contact sheets of every cut
   panel; view the candidates at full size. Check the colour pages too (`pages/` before the first
   panel, often never cut into panels): a tile takes `"page": "001_002.jpg", "box": [l, t, r, b]`
   instead of `panel` - box out the logo, title lettering and spine. Two faces at different heights
   on one colour spread make two tiles, each with its own box (one box spanning both cuts a face at
   the eyes).
3. **Crop**: write the spec (tiles only, `labels: []`), `thumb.py grid spec.json`, and LOOK at the
   gridded render. Fix `zoom`/`cx`/`cy` (or `box`) until each tile shows a face and upper body, not a
   torso, and crop out scanlator watermarks. A short wide panel cannot be zoomed out past its height.
4. **Labels**: read `at` (the label's centre) and `to` (an arrow's tip, optional) off the grid, in
   canvas fractions - never guess them. Keep labels off the divider and the bottom-right corner.
   Size 72-110; two short lines beat one long one.
5. Save it as `projects/<P>/upload/thumbnail.json`, run `./run.sh upload -p P`, and view a stamped
   thumbnail (a long video's too - its `CH 01-12` is wider).

The spec (`remanga/video/thumbnail.py`; `specs.example.json` has two):

```json
{"project": "MyManga", "chapter": "1",
 "tiles": [{"panel": "001_012_01", "w": 0.55, "zoom": 1.25, "cx": 0.5, "cy": 0.35,
            "tint": ["#06172e", "#d8ecff"], "contrast": 1.15},
           {"page": "001_002.jpg", "box": [530, 60, 1085, 1000], "w": 0.45, "saturation": 1.15}],
 "labels": [{"text": "ICE\nCOLD", "at": [0.25, 0.86], "size": 96, "color": "#8FE3FF"},
            {"text": "CH {num}", "at": [0.12, 0.07], "size": 50}]}
```

`chapter` is where the tiles come from (a tile's own `chapter` overrides it). `w` is a tile's share of
the width; `zoom`/`cx`/`cy` crop around a point; `box` crops to exact pixels first; `tint` makes a
black-and-white panel a duotone; `contrast` firms a flat grey one; `saturation` enriches colour.

## Style

- **One strong image**, or - what works best for a recap - **two panels side by side, one per side
  of the hook**, a black divider between: the villain's smirk and the victim's shock, the cold stare
  and the secret blush, the "weak" hero and the monster he flattens.
- **1-3 short ALL-CAPS labels**, three or four words at most, in the house yellow `#FFE600` Anton
  with a thick black outline: `VILLAIN`, `SHE HATES ME?!`, `SECRETLY IN LOVE`, `ONE HIT`. A label sits
  under or beside the face it names - **never on a face** - and an arrow, when there is one, stops
  short of it. Pick a colour that stands out from what is behind it: yellow disappears on blonde
  hair (pink or white there); red suits a villain, light blue a cold character.
- **Duotones** make black-and-white art pop and tell the roles apart: blue for the cold or the old,
  red for the threat, pink for the crush. Sharp black-and-white panels beat a soft, low-resolution
  colour page.
- **Real art only**, never generated. Faces turned towards the viewer; panels big enough to fill
  their tile (a ~250 px panel blown up 2-3x reads as line art but soft).
- **The bottom-right corner stays clear** (YouTube prints the length there); the `CH {num}` badge in
  a free corner.
- **No gore** - YouTube limits the reach of a video whose thumbnail shows it, and a creepy face sells
  as well. **Nothing sexual**, and never about a character the story calls young; "fanservice" means
  the heroine in colour.
- **Three different angles** for A/B/C (premise, role reversal, power, mystery) - not one idea
  reworded - and the thumbnail never repeats its own title's words: each carries half the hook.

## Title

Title Case on every word, the premise as a story sentence, ONE all-caps emphasis word, ending
`| Manga Recap`; 92 characters at most (` (01-02)` is added; YouTube cuts at 100). Write the series'
hook, not one chapter's - the same text is stamped on chapter 1 and chapter 30. For example:

- Genius Reincarnates As The Tutor Of A Sadistic Princess Who Kills Him In EVERY Route | Manga Recap
- He Reincarnated As The Villain Leader, So He Kicked HIMSELF Out Before The Revenge | Manga Recap

## Description

In this order (the LLM round trip writes it this way): a two-paragraph hook - setup, then twist,
the hook's keywords in the first ~150 characters, nothing past the start of the story; `▶ {chapter}`;
`{timestamps}`; `📖 Read the manga: <manga_url>`; `Manga:` the English title with the original in
brackets; `Story: ... · Art: ...`; 5-7 hashtags (the first three show above the title); a fair-use
note; `Narration voice: AI text-to-speech.` (YouTube asks creators to disclose synthetic content);
`Support the official release of <title>.`

**Titles and credits come from the source, never from memory**: `get_manga_credits` asks MangaDex
(`/manga/<id>?includes[]=author&includes[]=artist` - the `en` title or `altTitles` entry, authors and
artists). When MangaDex lists several people without roles, all are credited and none is assigned a
role it did not give. A project from a site without credits (comix.to) gets none unless it also has
a MangaDex source (`./run.sh sources -p P --add <MangaDex link>`).
