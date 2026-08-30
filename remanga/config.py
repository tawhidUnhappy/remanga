from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from remanga.json_io import read_json, write_json


class SystemConfig(BaseModel):
    prefer_gpu: bool = True
    gpu_codec: str = "h264_nvenc"
    fallback_codec: str = "libx264"
    threads: int = 4
    log_level: str = "INFO"


class DownloaderConfig(BaseModel):
    language: str = "en"
    image_quality: str = "data"  # 'data' (high quality) or 'data-saver'
    max_retries: int = 3
    retry_delay_seconds: int = 2
    request_delay_seconds: float = 0.35
    # pages.zip is a standalone convenience bundle of the raw downloaded page
    # images - nothing downstream in the pipeline reads it (cropping reads
    # straight from pages/), it's only useful for manually handing a chapter's
    # pages to an LLM, which isn't the marking workflow anymore (see
    # remanga/webui/). Off by default so a normal run doesn't spend time/disk
    # zipping something nothing needs; flip to true if you still want it.
    # Named for exactly what it does (zips the downloaded pages) so it's
    # never confused with cropper.primary_archive_enabled below, which zips
    # something completely different (the cropped panels/sheets).
    zip_pages_enabled: bool = False


class LLMBundleConfig(BaseModel):
    """Vision archives built purely for uploading to an LLM chat interface,
    losslessly re-encoded smaller than the raw cropped files either way (see
    remanga/cropper/image_codec.py, remanga/cropper/pdf_writer.py) - never by
    degrading image quality. No format ever touches panels/ (still the
    full-quality source video rendering reads from) or the primary
    sheets.zip/panels.zip (CropperConfig.primary_archive_enabled) - all three
    are purely additional, on top of whatever that's already doing.

    Three independent formats, each named for exactly what it packages and
    the folder it lands in - no field here is ever just "zip" on its own,
    specifically so it can't be confused with cropper.primary_archive_enabled
    (a completely different zip):
    - `panels_zip` - individual panel crops, one file per panel (remanga/
      cropper/llm_zip.py), in panels_zip/. On by default - a
      losslessly-shrunk zip is a safe, no-downside win over the primary
      archive for LLM upload.
    - `panels_pdf` - the same individual panel crops, one per PDF page
      (remanga/cropper/llm_pdf.py), in panels_pdf/. Off by default - a less
      universally-supported format, and PDF has no dedicated lossless image
      codec of its own to lean on (see that module).
    - `sheets_zip` - 2x2 contact sheet composites instead of individual
      panels, still packaged as a zip (remanga/cropper/llm_sheets.py), in
      sheets_zip/ - fewer, denser images, for lower LLM vision-token cost.
      Every composite is merged from the panels' full original resolution,
      never downscaled (see remanga/cropper/sheets.py) - only smart lossless
      re-encoding is used to keep the file size down, the same guarantee
      every other format here makes. Off by default; independent of
      `CropperConfig.primary_archive_format`, so this can be built even
      while the primary archive is packaging plain panels.zip.

    Each format is a checklist of two independent things to generate, not a
    mode to pick - check either, both, or neither:
    - `<format>_enabled`: generate it as **one single file** holding every
      image, regardless of size.
    - `<format>_split_enabled`: generate it **split into multiple
      size-capped parts** instead (`..._1.zip`/`.pdf`, `..._2.___`, ...),
      each kept at or under `max_mb`. Only check this if your LLM interface
      actually enforces an upload size cap you're hitting - the plain
      single-file default is simpler and works everywhere else.

    Checking `_split_enabled` builds the split version regardless of
    `_enabled` (see the `*_active` properties below - either one is enough
    to generate something for that format); checking both together still
    only produces the split version, not two separate outputs.

    Written to panels_zip/panels_1.zip, ... and/or panels_pdf/panels_1.pdf,
    ... and/or sheets_zip/sheets_1.zip, ... in the chapter folder -
    remanga/cropper/llm_bundles.py coordinates whichever are active behind
    one call, so the rest of the crop pipeline never needs to know about any
    format individually.

    Interactively editable as a checklist any time, not just during initial
    setup - `remanga setup-config` (step 3) and the "adjust LLM upload
    bundles" prompt in the main interactive wizard both call
    remanga.setup.configure_llm_bundle_formats for this."""

    panels_zip_enabled: bool = True
    panels_zip_split_enabled: bool = False
    panels_pdf_enabled: bool = False
    panels_pdf_split_enabled: bool = False
    sheets_zip_enabled: bool = False
    sheets_zip_split_enabled: bool = False
    # Only consulted when the matching *_split_enabled above is on: each part
    # is kept at or under this size by splitting on image boundaries. A
    # single image larger than this on its own still gets its own (oversized)
    # part rather than being split or dropped. Shared by all three formats.
    max_mb: float = 50.0

    @property
    def panels_zip_active(self) -> bool:
        """Whether the panels_zip bundle should be built at all - checking
        either `panels_zip_enabled` or `panels_zip_split_enabled` is enough
        (see class docstring); `panels_zip_split_enabled` also picks the
        split-into-parts form over the single-file default."""
        return self.panels_zip_enabled or self.panels_zip_split_enabled

    @property
    def panels_pdf_active(self) -> bool:
        """Same as panels_zip_active, for the panels_pdf bundle."""
        return self.panels_pdf_enabled or self.panels_pdf_split_enabled

    @property
    def sheets_zip_active(self) -> bool:
        """Same as panels_zip_active, for the sheets_zip bundle."""
        return self.sheets_zip_enabled or self.sheets_zip_split_enabled


class CropperConfig(BaseModel):
    margin_padding_pixels: int = 8
    auto_contrast_clean: bool = False
    save_format: str = "PNG"
    # 'sheets' (2x2 contact sheets) or 'panels' (individual panel crops) -
    # which one primary_archive_enabled below actually builds. Sheets off by
    # default (i.e. this is 'panels').
    primary_archive_format: str = "panels"
    # Forcing this on always generates sheet_* contact sheet composites even when
    # primary_archive_format is 'panels', which doesn't use them for
    # anything - wasted work/disk. Off by default; package_outputs()
    # (cropper/crop_report.py) still builds them automatically whenever
    # primary_archive_format is actually 'sheets' (or the sheets_zip LLM
    # bundle is active), so those keep working with no extra config needed.
    # Only turn this on to get sheets alongside 'panels' mode for some other
    # reason.
    always_generate_sheets: bool = False
    panels_per_sheet: int = 4
    # Whether to build sheets.zip/panels.zip (whichever primary_archive_format
    # says) at the chapter root at all. Separate from everything under
    # llm_bundle below - named "primary" specifically to keep it distinct
    # from those, since a chapter can perfectly well have this off and only
    # the LLM upload bundles on (or vice versa).
    primary_archive_enabled: bool = True

    # Everything about the optional, size-capped LLM upload bundles lives
    # under this one key - see LLMBundleConfig above for what each field does.
    llm_bundle: LLMBundleConfig = Field(default_factory=LLMBundleConfig)

    @property
    def expected_zip_name(self) -> str:
        """The vision-archive filename this `primary_archive_format` implies -
        computed on demand instead of stored, so it can never drift out of
        sync with it."""
        return "panels.zip" if self.primary_archive_format.lower() == "panels" else "sheets.zip"

    # Gutter-snap refinement: treats the LLM's crops.json box as a best guess and
    # corrects each edge against real pixel evidence (see remanga/cropper/gutter.py)
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
    # remanga/cropper/gutter.py:reconcile_adjacent_seams.
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

class TTSConfig(BaseModel):
    engine: str = "indextts-2.5"
    hf_repo_id: str = "IndexTeam/IndexTTS-2.5"
    model_dir: str = "checkpoints/indextts_2.5"
    cfg_path: str = "checkpoints/indextts_2.5/config.yaml"
    spk_audio_prompt: str = ""
    lang: str = "EN"
    use_bf16: bool = True
    speed: float = 1.0
    # IndexTTS-2.5's own defaults (indextts/infer_v2_5.py's infer_generator),
    # for natural-sounding prosody - a much lower temperature/top_p sounds
    # more "consistent" but trades away natural pitch/pacing variation for a
    # flatter, more robotic delivery. Emotion itself isn't configured here at
    # all: audio/synth.py sends no emo_vector, so IndexTTS-2.5 infers its own
    # emotion straight from each panel's text and punctuation (see
    # prompts/narration.md Rule 3) - temperature/top_p just control sampling
    # variety within whatever emotion that inference lands on.
    temperature: float = 0.8
    top_p: float = 0.8
    sample_rate: int = 22050
    # How long to wait for one panel's synthesize response before treating the
    # worker as hung and killing it (see audio/synth.py:synthesize). A single
    # 10-26 word panel normally finishes in well under a minute even on modest
    # hardware, so this is a generous ceiling, not a tight budget.
    synth_timeout_seconds: int = 180


class AudioConfig(BaseModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    # The gap inserted between one panel's narration clip and the next in the
    # assembled master track (audio/mix.py) - not the silence a reaction-beat
    # panel's own empty-text clip gets (that's a fixed 500ms floor in
    # audio/tts.py, since it's the panel's content, not a gap between two
    # panels' audio). 0 means panels play back to back with no dead air
    # between them at all.
    pause_between_panels_ms: int = 0
    bgm_enabled: bool = False
    bgm_path: str = ""
    bgm_volume_db: float = -22.0
    enable_loudnorm: bool = True


class VideoConfig(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: int = 30
    background_style: str = "blur"  # 'blur' (Fast bokeh blur) or 'solid' (black canvas)
    blur_brightness: float = 0.42   # Dimming multiplier for canvas blur (0.35 to 0.55 recommended)
    background_color: str = "#000000"
    panel_padding_percent: int = 4
    auto_adaptive_padding: bool = True
    panel_border_width: int = 2
    panel_border_color: str = "#222222"


class ShortcutsConfig(BaseModel):
    """Panel-marker keyboard shortcuts, editable from the webui's own Shortcuts
    menu (Settings gear in the topbar -> saved via POST /api/shortcuts, which
    writes straight back into this section of config.json - see
    remanga/webui/shortcuts_store.py:persist_shortcuts). Each action maps to a list of
    key combos so more than one chord can trigger it (e.g. Delete AND
    Backspace); the frontend renders/parses these itself.

    Combo syntax (parsed client-side in remanga/webui/static/js/shortcuts.js):
    '+'-separated tokens, lowercase. 'mod' means Ctrl on Windows/Linux and Cmd
    on macOS - never hardcode 'ctrl' or 'cmd' directly so a saved binding
    still makes sense on whichever OS opens it next. The non-modifier token is
    whatever KeyboardEvent.key lowercases to (e.g. 'arrowleft', 'delete', 's').
    """
    save: List[str] = Field(default_factory=lambda: ["mod+s"])
    mark_full_page: List[str] = Field(default_factory=lambda: ["mod+f"])
    tool_draw: List[str] = Field(default_factory=lambda: ["d"])
    tool_adjust: List[str] = Field(default_factory=lambda: ["v"])
    prev_page: List[str] = Field(default_factory=lambda: ["arrowleft"])
    next_page: List[str] = Field(default_factory=lambda: ["arrowright"])
    delete_mark: List[str] = Field(default_factory=lambda: ["delete", "backspace"])
    # A bare, unmodified key on purpose - not "mod+tab" (reserved by every
    # major browser for switching tabs) or "mod+0" (reserved for resetting
    # the *browser's* page zoom). Both fire a browser-chrome action a page can
    # never preventDefault() its way out of, on every mainstream browser, so
    # either one would have been permanently dead as an actual default. A
    # bare digit has no such reservation, is easy to reach, and "0" reads
    # naturally as "reset to zero."
    reset_view: List[str] = Field(default_factory=lambda: ["0"])


class MarkerConfig(BaseModel):
    """The panel-marking web UI: where crops.json comes from now, in place of the
    old paste-from-an-LLM step. See remanga/webui/."""
    host: str = "127.0.0.1"
    port: int = 8765
    auto_open_browser: bool = True

    # MAGI v3 (https://github.com/ragavsachdeva/magi) pre-fills every page's panel
    # boxes on launch so the user only has to adjust, not draw from scratch.
    # Research/non-commercial license (ragavsachdeva/magiv3 model card) - fine for
    # personal use, but not something to redistribute commercially as-is.
    magi_enabled: bool = True
    magi_repo_id: str = "ragavsachdeva/magiv3"
    magi_model_dir: str = "checkpoints/magiv3"
    magi_panel_score_threshold: float = 0.5

    # A mark's body/handles only become draggable once it's already selected
    # (a first click selects; a second, deliberate drag on the now-selected
    # mark actually moves/resizes it) - and while the Draw tool is active,
    # every OTHER mark is frozen (not selectable or draggable at all), so
    # starting a new box that happens to overlap one never nudges it by
    # accident. The mark currently selected - i.e. the one just drawn - stays
    # adjustable in Draw mode too, and loses that status the moment a new box
    # is drawn or the selection is cleared by clicking outside the page. The
    # Adjust tool has none of these restrictions: every mark is always
    # selectable/draggable, and it can still draw new boxes too. Set False to
    # restore the old behavior where any drag immediately grabs whatever
    # mark is under the cursor, selected or not, even in Draw mode.
    click_to_select: bool = True

    shortcuts: ShortcutsConfig = Field(default_factory=ShortcutsConfig)


class RemangaConfig(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)
    cropper: CropperConfig = Field(default_factory=CropperConfig)
    marker: MarkerConfig = Field(default_factory=MarkerConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)

    @classmethod
    def load(cls, config_path: Optional[Path | str] = None) -> "RemangaConfig":
        """Load configuration from JSON file or create with defaults."""
        target_path = Path(config_path) if config_path else Path("config.json")
        if not target_path.exists():
            target_path = Path("config.example.json")

        if target_path.exists():
            return cls.model_validate(read_json(target_path))
        return cls()

    def save(self, output_path: Path | str = "config.json") -> None:
        """Save current configuration to a JSON file."""
        write_json(output_path, self.model_dump())
