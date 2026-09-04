"""Panel-cropping and vision-upload-packaging settings - see remanga/cropper/."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PackageConfig(BaseModel):
    """The single 'what to make out of a chapter's marked panels' checklist -
    one flat list of independent yes/no switches, not a mode to pick or two
    separate sections to coordinate. Every format is losslessly re-encoded
    smaller than its raw source either way (see remanga/cropper/
    image_codec.py, remanga/cropper/pdf_writer.py), never by degrading image
    quality, and never touches panels/ itself - still the full-quality
    source video rendering reads from.

    - `sheets` - generate 2x2 labeled grid composites merged from the
      panels' full original resolution (never downscaled - see remanga/
      cropper/sheets.py), written to sheets/sheet_001.___, sheet_002.___,
      .... On by default. Only needed to inspect sheets/ yourself or as raw
      material for `sheets_zip` below - `sheets_zip` generates them
      automatically the moment it's checked, whether or not this is also on.
    - `sheets_zip` - zip up those contact sheets (remanga/cropper/
      llm_sheets.py) into sheets_zip/sheets_1.zip - fewer, denser,
      full-resolution images than individual panels, for lower LLM
      vision-token cost. Off by default. Single-file only - no split option
      for sheets today.
    - `sheets_folders` - the plain-folder alternative to `sheets`: no grid
      compositing at all, just each panel crop copied as-is into small
      numbered subfolders of `panels_per_folder` panels each (remanga/
      cropper/sheet_folders.py), written to sheets_folders/folder_001/,
      folder_002/, .... Off by default.
    - `pdf` - individual panel crops, one per PDF page (remanga/cropper/
      llm_pdf.py), as a single file: panels_pdf/panels_1.pdf. Off by
      default - a less universally-supported format, and PDF has no
      dedicated lossless image codec of its own to lean on (see that
      module).
    - `pdf_splite` - the same PDF content, split into multiple size-capped
      raw `.pdf` files instead - panels_pdf/panels_1.pdf, panels_2.pdf,
      ... - **not zipped**. Only check this if your LLM interface actually
      enforces an upload size cap you're hitting and you don't want a zip
      wrapper.
    - `pdf_zip` - the single PDF, wrapped in a zip (panels_pdf/panels_1.zip)
      - for upload interfaces that only accept zip attachments.
    - `pdf_zip_splite` - the PDF split into multiple size-capped parts,
      each zipped separately (panels_pdf/panels_1.zip, panels_2.zip, ...,
      each kept at or under `max_mb`).

    Each PDF switch's name says exactly what it produces: `pdf` = single
    raw file, `pdf_splite` = split raw files (no zip), `pdf_zip` = single
    file zipped, `pdf_zip_splite` = split files, each zipped. Check any
    combination - building any of them always builds the underlying PDF
    content, whether or not `pdf` itself is also checked; whenever any
    `_splite` switch is on, every active PDF format uses the split form.
    - `panels_zip` - individual panel crops, one file per panel (remanga/
      cropper/llm_zip.py), as a single file: panels_zip/panels_1.zip. Off
      by default.
    - `panels_zip_splites` - the same panels zip, split into multiple
      size-capped parts instead (panels_zip/panels_1.zip, panels_2.zip,
      ..., each kept at or under `max_mb`). Checking this alone still
      builds it, same rule as `pdf_zip_splite` above.

    Written to sheets_zip/, panels_pdf/, and/or panels_zip/ in the chapter
    folder - remanga/cropper/llm_bundles.py coordinates whichever are active
    behind one call, so the rest of the crop pipeline never needs to know
    about any format individually.

    Interactively editable as a checklist any time, not just during initial
    setup - `remanga setup-config` and the "adjust what gets generated/
    zipped" prompt in the main interactive wizard both call
    remanga.settings.configure_vision_outputs for this. That checklist is
    built from the Field metadata below, so this model is the only place
    any of these switches is described."""

    # Each switch carries its own menu text (title/what it produces/the fine
    # print), so the interactive checklist that edits these is *generated*
    # from this model rather than being a second hand-written list of the
    # same nine switches that has to be kept in step with it - see
    # remanga/settings/vision.py:package_toggles. `produces` is the example
    # output path shown next to the switch; `group` only orders the list.
    sheets: bool = Field(
        True, title="sheets", description="2x2 labeled grid composites, merged at full original resolution - fewer, denser images for lower LLM vision-token cost",
        json_schema_extra={"produces": "sheets/sheet_1.___, sheet_2.___, ...", "group": "sheets"},
    )
    sheets_zip: bool = Field(
        False, title="sheets_zip", description="Zips those contact sheets; builds sheets/ automatically even when `sheets` itself is off",
        json_schema_extra={"produces": "sheets_zip/sheets_1.zip", "group": "sheets"},
    )
    sheets_folders: bool = Field(
        False, title="sheets_folders", description="No compositing at all - each panel crop copied as-is into small numbered subfolders",
        json_schema_extra={"produces": "sheets_folders/folder_1/ .. folder_N/", "group": "sheets"},
    )
    pdf: bool = Field(
        False, title="pdf", description="Individual panels, one per PDF page, as a single file",
        json_schema_extra={"produces": "panels_pdf/panels_1.pdf", "group": "pdf"},
    )
    pdf_splite: bool = Field(
        False, title="pdf_splite", description="That same PDF content split into size-capped raw .pdf files, not zipped",
        json_schema_extra={"produces": "panels_pdf/panels_1.pdf, panels_2.pdf, ...", "group": "pdf"},
    )
    pdf_zip: bool = Field(
        False, title="pdf_zip", description="That same single PDF, wrapped in a zip - for upload interfaces that only accept zips",
        json_schema_extra={"produces": "panels_pdf/panels_1.zip", "group": "pdf"},
    )
    pdf_zip_splite: bool = Field(
        False, title="pdf_zip_splite", description="The PDF split into size-capped parts, each zipped separately",
        json_schema_extra={"produces": "panels_pdf/panels_1.zip, panels_2.zip, ...", "group": "pdf"},
    )
    panels_zip: bool = Field(
        False, title="panels_zip", description="Individual panel crops, one file per panel, as a single zip",
        json_schema_extra={"produces": "panels_zip/panels_1.zip", "group": "panels"},
    )
    panels_zip_splites: bool = Field(
        False, title="panels_zip_splites", description="That same panels zip, split into size-capped parts",
        json_schema_extra={"produces": "panels_zip/panels_1.zip, panels_2.zip, ...", "group": "panels"},
    )
    # Only consulted when a `_zip_splite`/`_splites` switch above is on: each
    # part is kept at or under this size by splitting on image/page
    # boundaries. A single image larger than this on its own still gets its
    # own (oversized) part rather than being split or dropped. Shared by
    # every format.
    max_mb: float = Field(
        50.0, title="max_mb",
        description="Size cap per part for every split format above, in MB",
        json_schema_extra={"group": "limits"},
    )

    @property
    def sheets_zip_active(self) -> bool:
        """Whether the sheets_zip bundle should be built at all."""
        return self.sheets_zip

    @property
    def pdf_active(self) -> bool:
        """Whether any PDF output (single file, split raw, zipped, or
        split-zipped) should be built at all - checking any of `pdf`/
        `pdf_splite`/`pdf_zip`/`pdf_zip_splite` is enough."""
        return self.pdf or self.pdf_splite or self.pdf_zip or self.pdf_zip_splite

    @property
    def pdf_split(self) -> bool:
        """Whether the PDF content should be packed into multiple
        size-capped parts - true the moment either `pdf_splite` or
        `pdf_zip_splite` is checked."""
        return self.pdf_splite or self.pdf_zip_splite

    @property
    def panels_zip_active(self) -> bool:
        """Whether the panels_zip bundle should be built at all - checking
        either `panels_zip` or `panels_zip_splites` is enough;
        `panels_zip_splites` also picks the split-into-parts form over the
        single-file default."""
        return self.panels_zip or self.panels_zip_splites


class CropperConfig(BaseModel):
    margin_padding_pixels: int = 8
    auto_contrast_clean: bool = False
    save_format: str = "PNG"
    panels_per_sheet: int = 4
    # Group size for the `sheets_folders` package format (see PackageConfig
    # above / remanga/cropper/sheet_folders.py) - how many panels go into
    # each numbered subfolder. Independent of panels_per_sheet, since the
    # two formats serve different upload interfaces.
    panels_per_folder: int = 10

    # One flat checklist - see PackageConfig above - of everything a chapter
    # can produce/zip/PDF for upload. There's no separate "primary archive"
    # concept - every zip a chapter gets, sheets or panels, goes through
    # `package` alone.
    package: PackageConfig = Field(default_factory=PackageConfig)

    # Gutter-snap refinement: treats the LLM's crops.json box as a best guess and
    # corrects each edge against real pixel evidence (see remanga/cropper/gutter/)
    # before margin_padding_pixels is applied. The actual search radius used per page
    # is adaptive: max(gutter_search_radius_pixels, page's longer side * fraction) -
    # a flat pixel floor undershoots badly on large scans when the LLM's guess is off
    # by more than a few dozen pixels, which is common enough to matter.
    snap_to_gutters: bool = True
    gutter_search_radius_pixels: int = 60         # floor: how far to look, even on small pages
    gutter_search_radius_fraction: float = 0.10   # scales the search radius with page size
    gutter_bg_tolerance: float = 20.0             # gray-level tolerance for "counts as background"
    gutter_min_run_pixels: int = 3                # minimum gutter band width to trust as real, not noise
    gutter_min_background_fraction: float = 0.96  # fraction of a row/col that must match bg to call it gutter

    # Seam reconciliation: a second pass over one page's already gutter-snapped
    # panels that re-derives shared borders between reading-order-adjacent tiles
    # jointly instead of independently, so neither panel can undershoot (a visible
    # gutter gap) while the other overshoots into it (bleeding the neighbor's tail
    # into its own crop) - both symptoms of one wrong seam. See
    # remanga/cropper/seams.py:reconcile_adjacent_seams.
    reconcile_panel_seams: bool = True
    seam_max_gap_fraction: float = 0.15           # ignore pairs whose facing edges are this far apart (not really adjacent)
    seam_min_axis_overlap_fraction: float = 0.5   # how much of the shared axis must overlap to count as "stacked/side-by-side"
    gutter_background_sample_strip_pixels: int = 12  # page-margin strip used to sample the background color

    # Final per-panel whitespace trim: after a panel is cropped (gutter-snapped,
    # seam-reconciled, and padded), trims any leftover thin band of pure background
    # still baked into the saved image - the last safety net for panels with no
    # neighbor to reconcile a seam against. See remanga/cropper/trim.py.
    trim_panel_whitespace: bool = True
    trim_min_background_fraction: float = 0.985   # stricter than gutter detection - only trims near-pure blank bands
    trim_max_margin_fraction: float = 0.04        # never trims more than this fraction of a panel's width/height per side

    # Duplicate-crop safety net: drops any crops.json panel whose box is
    # near-identical in both position and size to an earlier one on the same
    # page (same frame marked twice), keeping the earlier crop. Deliberately
    # IoU-only - a small panel nested inside/heavily overlapping a much larger
    # one is a normal manga layout, not a duplicate, and must never be
    # silently dropped just because it sits mostly inside another panel's
    # box. See remanga/cropper/dedupe.py.
    dedupe_duplicate_panels: bool = True
    duplicate_iou_threshold: float = 0.6  # intersection-over-union that counts as a duplicate
