# LLM crop - cropping a chapter with Gemini

A second way to make a chapter's `crops.json`, next to the Panel Marker. Gemini reads gridded
pages and plans the crops: which speech bubbles belong to which panel, when several small
panels should be one image, and which art breaks out of a border. remanga checks the reply,
turns it into `crops.json`, and cuts the crops.

| | Panel Marker (`mark`) | LLM crop (`crop-grid` + `llm-crop`) |
|---|---|---|
| Who finds the panels | MAGI v3 on your GPU, then you | Gemini, from gridded page images |
| Speech bubbles | a box is a box | each bubble, caption and sound effect goes to the crop it belongs to, whole |
| Art breaking out of a panel | cut at the box edge | listed, and kept |
| Slivers of the next panel | whatever the box covers | painted out |
| Several panels as one image | draw one big box | `group` crops |
| Reading order | XY-cut, or your drag | Gemini, from the story |

Everything after `crops.json` is unchanged: `crop` → `package` → `narration` → `review` → `tts` →
`mix` → `render`.

---

## The workflow

### 1. Download the chapter
```bash
./run.sh download -p my_manga -c 2
```

### 2. Build the grid upload
```bash
./run.sh crop-grid -p my_manga -c 2
```
It creates:

| Path | What |
|---|---|
| `projects/my_manga/grid_pages/chapter_2/` | every page as a gridded square image, plus a `000_info` image |
| `projects/my_manga/grid_zip/chapter_2/grid_1.zip` | those images + `chapter_info.json` - **the file you upload** |
| `projects/my_manga/grid_pdf/chapter_2/grid_1.pdf` | the same as a PDF (off by default) |
| `projects/my_manga/chapters/chapter_2/llm_crops.json` | **empty (0 bytes)** - where Gemini's reply goes |

It then prints exactly what to upload and where to paste. An existing `llm_crops.json` is never
overwritten.

### 3. Send it to Gemini
Upload **`grid_1.zip`** and **`prompts/llm_crop.md`** in one message. Everything else Gemini needs
- chapter, reading direction, grouping setting, each page's area - is inside the zip's
`chapter_info.json`, so there is nothing to type.

### 4. Paste the reply
Gemini answers with one JSON block. Paste it into `chapters/chapter_2/llm_crops.json` and save.
Pasting the whole reply, code fence and any stray sentence included, is fine.

### 5. Import it
```bash
./run.sh llm-crop -p my_manga -c 2
```
- **Checks the reply** against the real pages: every page present, boxes valid and inside the
  page, order numbers, groups well formed.
- **If something is wrong**, it writes `projects/my_manga/llm_crop/chapter_2/fix_request.md`.
  Paste that into the same Gemini chat, paste the new reply over `llm_crops.json`, and press
  Enter - it checks again.
- **If it passes**, it writes `crops.json` and preview images in
  `projects/my_manga/llm_crop/chapter_2/preview/`, and lists anything worth a look (for example an
  order that differs from the layout's usual order).
- **If the chapter already has Panel Marker marks**, it asks before replacing them (`--force` on
  the CLI replaces without asking).

`llm-crop` also works as one step from the start: it builds the grid if it isn't there, prints the
hand-off, and waits for you to paste.

### 6. Look at the previews
In each preview: **green** = frames, **blue** = text outside a frame, **magenta** = art outside a
frame, **red box** = what will be cut (with its order number), **red tint** = what will be painted
over. To fix a box by hand, open the chapter in `mark`. Boxes you don't touch keep their LLM
details; a box you move becomes a plain hand-drawn box.

### 7. Carry on as usual
```bash
./run.sh crop -p my_manga -c 2      # add --force if the chapter was cropped before
./run.sh package -p my_manga -c 2
```

### Whole project, and the pipeline
- `crop-grid-all -p my_manga` builds every downloaded chapter's upload at once.
- `llm-crop-all -p my_manga` imports every chapter whose `llm_crops.json` has a reply in it, and
  names the chapters still waiting and any reply that needs a fix.
- In the pipeline checklist, pick **`llm-crop`** instead of **`mark`**. It is not in the default
  order, so projects that never chose keep marking as before.

---

## Settings

Settings → **LLM crop (Gemini)**, also offered from inside `crop-grid` and `llm-crop`. Per project,
like every work setting. Stored under `extensions.llm_crop` in `config.json`, except paint-out,
which is the cropper's own `cropper.paint_out`.

| Setting | Default | Meaning |
|---|---|---|
| `grid_pages` | on | the folder of grid images |
| `grid_zip` / `grid_zip_splites` | on / off | the zip, single or split into parts |
| `grid_pdf` / `grid_pdf_splite` / `grid_pdf_zip` / `grid_pdf_zip_splite` | off | the PDF forms, same meaning as the panels PDF switches |
| `max_mb` | 50 | size cap per part, for the split forms |
| `grouping` | `balanced` | `none` / `balanced` / `generous` - how readily Gemini shows several frames as one crop |
| `cropper.paint_out` | on | paint other crops' frames and bubbles out of each crop |
| `preview` | on | write preview images on import |
| `grid_image_size` | 2048 | side of the square grid image, in pixels |
| `grid_line_step` / `grid_label_step` | 25 / 100 | light lines / labeled lines, in 0-1000 units |
| `grid_tick_step` | 5 | ruler ticks, in 0-1000 units (0 draws none) |

`grouping` and the grid settings are written into the upload, so run `crop-grid` again after
changing them.

---

## The grid image

- A **square** image, `grid_image_size` pixels a side.
- The page is scaled evenly to fit and placed in the **top-left corner**; the rest is **black**.
  A tall page leaves a black strip on the right, a wide spread leaves one at the bottom.
- A green ruler over the **whole square** in the 0-1000 units Gemini's bounding boxes use, in three
  weights: **labeled lines every 100** (heaviest, numbered on all four edges), **light lines every
  25** (numbered in smaller tags along the top and left), and **ticks every 5** along the four
  edges and across every labeled line.
- The **page ID** (e.g. `002_019`) is stamped in the black strip, so it covers no art.
- `chapter_info.json` → `page_areas` gives each page's area on the square, e.g. `[0, 0, 1000, 696]`
  for a tall page. Gemini's boxes must stay inside it.

Why square: one unit is the same distance across and down, so Gemini doesn't have to correct for
the page's shape. Why top-left: converting a box back to the page is one division per axis, with
no offset.

Why lines every 25 and ticks every 5: with lines every 50 a border could sit 25 units from the
nearest numbered line, Gemini rounded toward the line, and crops landed a few units out. Every 25
halves the worst case to 12.5 units, and the ticks split each cell into 5-unit steps, so an edge is
counted rather than estimated. The cost is more green over the art: lines every 25 do cross more
bubbles and screentone, which is accepted for the precision. A full 5-unit mesh would not be, so
the fine scale stays ticks, at the edges and along the labeled lines. The three weights matter too:
drawn alike, a labeled line and a light line are the same line once the model scales the image
down. On the 2048 px square the ticks are 10 px apart, which separates when a model reads a page
closely (around 2000 px) and blurs when it shrinks the page to around 1000 px; the 25-unit lines
still read there. `grid_tick_step: 0` turns the ticks off; finer than 5 needs a bigger
`grid_image_size` to stay legible.

---

## What `crops.json` gets

Each Gemini crop becomes one panel entry with `src: "llm"`, its boxes converted from the square to
the page:

```json
{"panel_id": 1, "box_1000": [58, 639, 363, 936], "src": "llm", "kind": "panel",
 "frames": [[58, 639, 363, 909]], "text_outside": [[67, 707, 126, 936]], "art_outside": []}
```

`box_1000` is the rectangle around all of them, so anything that only reads `box_1000` still sees
the right crop. A skipped page (credits, ads, blank, duplicate) is written as not a story page and
marked decided, so a later MAGI Detect won't fill it in.

## How the crops are cut

Only entries with `frames` take this path; marker-made chapters crop exactly as before.

1. **Frames are gutter-snapped** like marked boxes, with every other frame on the page as a
   neighbour they can't cross.
2. **The rectangle** is the box around the snapped frames plus `text_outside` and `art_outside`,
   plus the usual margin.
3. **Paint-out:** inside that rectangle, paper colour goes over other crops' frames (where they lie
   outside this crop's own frames) and over other crops' `text_outside`. This crop's own
   `text_outside` and `art_outside` always stay. So a bubble appears whole in its own crop and
   nowhere else, and another crop's art drawn over this frame (a head rising into the tier above)
   stays in the picture.
4. **Trim** removes leftover blank edges, as before.

---

## What has been verified, and what hasn't

Checked on real pages from this repo (Yandere chapters 1 and 2):
- grid images and zips build for tall pages and spreads, with correct `page_areas`;
- the prompt's examples pass the importer's checks; broken replies (missing page, inverted box,
  box in the padding, wrong kind, not JSON) each produce the right fix request;
- a reply imports, and its boxes convert back to page coordinates within 1 unit;
- previews, paint-out and group crops cut as intended;
- the existing `panels_zip`, `panels_pdf`, `sheets` and `sheets_zip` outputs are byte-identical to
  before, and marker-made chapters crop exactly as before;
- the marker keeps LLM crops through a save, and turns a moved one into a manual box.

**Not yet measured:** how accurate Gemini's crops actually are. The cheapest check is a chapter
you have already marked by hand: run it through Gemini and compare the previews (or the panels)
with your own marks.
