# Page mode: narrate whole pages

Page mode skips marking, cropping and packaging. The chapter's pages go to the LLM as they are, it
writes one narration per page that covers every panel on that page in reading order, and the video
shows each page whole while its narration plays.

| | Panel mode (default) | Page mode |
|---|---|---|
| What's on screen | one cropped panel at a time | one whole page at a time |
| Steps before narration | mark or llm-crop → crop → package | none |
| Narration | one entry per panel | one entry per page, every panel narrated in it |
| Prompts | `prompts/narration.md` | `prompts/page_narration.md` + `prompts/narration.md` |

## Steps

### 1. Download the chapter
```bash
./run.sh download -p my_manga -c 2
```

### 2. Build the pages upload
```bash
./run.sh page-upload -p my_manga -c 2 --formats pages_pdf
```
In the wizard: **Package for the LLM → page-upload**, with a checklist of formats: `pages_pdf`,
`pages_pdf_splite`, `pages_pdf_zip`, `pages_pdf_zip_splite`. The choice is saved for the project.

It writes `projects/my_manga/page_upload/chapter_2/pages_1.pdf`: a leading page with the chapter's
identity, reading direction and page list, then every page. No file is ever over the size cap
(`max_mb`, 50 by default, Settings → **Page narration**). JPEG pages are embedded as their own
bytes and other pages losslessly; only a single-file PDF that would go over the cap moves some pages
to near-lossless encoding (see the panels PDF note in the README). It also creates an empty
`chapters/chapter_2/page_narration.json`.

### 3. Send it to the LLM
Upload **`prompts/page_narration.md`**, **`prompts/narration.md`** (the style it follows), the PDF,
and `memory.json` / `narration_lessons.json` when they have content. The LLM replies with two JSON
blocks.

### 4. Paste the replies
- Block 1 → `projects/my_manga/chapters/chapter_2/page_narration.json`
- Block 2 → `projects/my_manga/memory.json`

### 5. Import
```bash
./run.sh page-narration -p my_manga -c 2
```
In the wizard: **Narration → page-narration**. It checks the reply:
- every page is there, once; a story page lists its `panels` and has narration; a skipped page
  (credits, ad, blank, duplicate) has a reason and no narration;
- **warnings** for a page whose narration is short for the number of panels it lists (under 12 words
  a panel - usually panels summed up instead of narrated), and for quotation marks, `?`, `!`, `...` or
  contractions.

A reply with errors gets `projects/my_manga/page_upload/chapter_2/fix_request.md` to paste back into
the same chat. A reply that passes becomes:
- `chapters/chapter_2/panels/` - one image per story page, named `<page>_01` (`002_014_01.jpg`);
- `chapters/chapter_2/narration.json` - one entry per story page.

If the chapter already has cropped panels or a narration.json, it asks before replacing them
(`--force` replaces without asking).

### 6. Carry on as usual
```bash
./run.sh tts -p my_manga -c 2
./run.sh mix -p my_manga -c 2
./run.sh render -p my_manga -c 2
```
`review`, `verify`, `full-recap` and `remix` work the same way, with each page as one "panel".

## The pipeline

In the pipeline checklist, pick **`page-narration`** instead of `mark`, `crop`, `package` and
`narration` - for example `download → page-narration → tts → mix → render`. The step builds the
upload if it isn't there, shows what to upload, waits for the paste, and imports. It is not in the
default order, and does nothing for a chapter that already has narration.json.

`page-upload-all` builds every downloaded chapter's upload at once.

## What was verified

On a 4-page chapter (three story pages, JPEG and PNG, and a credits page): the upload built with
JPEG pages byte-identical inside the PDF; the reply imported into 3 panels and 3 narration entries,
skipping the credits page; the panels-vs-narration gate passed; and `tts` (Chatterbox Turbo),
`mix` and `render` produced a 23-second video showing each page whole. A full 40-page chapter's
pages PDF came to 29.6MB, every page lossless.
