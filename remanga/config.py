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
    # never confused with cropper.package below, which zips something
    # completely different (the cropped panels/sheets).
    zip_pages_enabled: bool = False


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
    setup - `remanga setup-config` (step 3) and the "adjust what gets
    generated/zipped" prompt in the main interactive wizard both call
    remanga.setup.configure_vision_outputs for this."""

    sheets: bool = True
    sheets_zip: bool = False
    sheets_folders: bool = False
    pdf: bool = False
    pdf_splite: bool = False
    pdf_zip: bool = False
    pdf_zip_splite: bool = False
    panels_zip: bool = False
    panels_zip_splites: bool = False
    # Only consulted when a `_zip_splite`/`_splites` switch above is on: each
    # part is kept at or under this size by splitting on image/page
    # boundaries. A single image larger than this on its own still gets its
    # own (oversized) part rather than being split or dropped. Shared by
    # every format.
    max_mb: float = 50.0

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

# Every TTS engine remanga can drive, each in its own isolated `.tools/venv-*`
# environment (see remanga/venvs.py) so their dependency pins - PyTorch,
# transformers, whatever else - never have to share a resolution. Adding a
# third engine later means: a new *Config class below, an entry here, a new
# worker script/Synthesizer subclass (remanga/audio/synth.py), and a new
# isolated-venv provisioning block in bootstrap.sh - the same shape every
# existing engine already follows.
TTS_ENGINES = ("indextts-2.5", "audio8-tts-0.1b")


class Audio8Config(BaseModel):
    """Settings specific to the audio8-tts-0.1b engine (see TTSConfig.engine) -
    Audio8/Audio8-TTS-Preview-0.1b on Hugging Face, a ~170M-parameter
    Falcon-H1-based zero-shot voice-cloning model with its own 44.1kHz codec
    decoder. Runs in its own isolated `.tools/venv-audio8` (transformers>=4.57,
    trust_remote_code=True - a different, sometimes incompatible pin from
    IndexTTS-2.5's own environment, hence the separate venv rather than
    sharing IndexTTS's)."""
    hf_repo_id: str = "Audio8/Audio8-TTS-Preview-0.1b"
    model_dir: str = "checkpoints/audio8_tts_0.1b"
    # Unlike IndexTTS-2.5 (a pure audio reference is enough for zero-shot
    # cloning), this model's processor also wants a transcription of
    # tts.spk_audio_prompt - accuracy of the transcript measurably affects
    # cloning quality per the model card, so this is asked for explicitly
    # rather than guessed/auto-transcribed.
    reference_text: str = ""
    use_bf16: bool = True
    temperature: float = 0.7
    top_p: float = 0.9
    max_new_tokens: int = 512
    sample_rate: int = 44100


class TTSConfig(BaseModel):
    # Which engine actually synthesizes speech - one of TTS_ENGINES. Every
    # other top-level field below is IndexTTS-2.5's own settings (kept
    # unprefixed/unnested for backward compatibility with existing
    # config.json files); audio8-tts-0.1b's settings live in the nested
    # `audio8` block instead, since the two engines' knobs don't overlap
    # cleanly (different sample rate, different sampling defaults, a
    # reference transcript the other engine has no use for). Switch engines
    # by changing this one field - remanga/audio/synth.py picks the matching
    # Synthesizer, isolated venv, and model directory automatically.
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
    audio8: Audio8Config = Field(default_factory=Audio8Config)


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
