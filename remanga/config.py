from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
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
    create_zip: bool = False


class CropperConfig(BaseModel):
    margin_padding_pixels: int = 8
    auto_contrast_clean: bool = False
    save_format: str = "PNG"
    vision_asset_type: str = "sheets"  # 'sheets' (2x2 contact sheets) or 'panels' (individual panel crops)
    # Forcing this on always generates sheet_*.png contact sheets even in
    # 'panels' mode, which doesn't use them for anything - wasted work/disk.
    # Off by default; package_outputs() (cropper/crop_report.py) still builds
    # them automatically whenever vision_asset_type is actually 'sheets', so
    # that mode keeps working with no extra config needed. Only turn this on
    # to get sheets alongside 'panels' mode for some other reason.
    create_sheets: bool = False
    panels_per_sheet: int = 4
    create_zip: bool = True

    @property
    def expected_zip_name(self) -> str:
        """The vision-archive filename this `vision_asset_type` implies - computed
        on demand instead of stored, so it can never drift out of sync with it."""
        return "panels.zip" if self.vision_asset_type.lower() == "panels" else "sheets.zip"

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

    # Duplicate-crop safety net: drops any crops.json panel whose box duplicates or
    # heavily overlaps an earlier one on the same page (same frame cropped twice),
    # keeping the earlier crop. See remanga/cropper/dedupe.py and crop prompt Rule 8.
    dedupe_duplicate_panels: bool = True
    duplicate_iou_threshold: float = 0.6          # intersection-over-union that counts as a duplicate
    duplicate_containment_threshold: float = 0.85  # or: this fraction of the smaller box swallowed by the other

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
    # flatter, more robotic delivery. This is independent of the flat
    # emotion_vectors below (which stay locked to neutral for narration
    # consistency) - temperature/top_p control sampling variety within
    # whatever emotion is requested, not which emotion is requested.
    temperature: float = 0.8
    top_p: float = 0.8
    sample_rate: int = 22050
    # How long to wait for one panel's synthesize response before treating the
    # worker as hung and killing it (see audio/synth.py:synthesize). A single
    # 10-26 word panel normally finishes in well under a minute even on modest
    # hardware, so this is a generous ceiling, not a tight budget.
    synth_timeout_seconds: int = 180
    emotion_vectors: Dict[str, List[float]] = Field(
        default_factory=lambda: {
            "neutral": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "hype": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "tense": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "serious": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "shock": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "emotional": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "mysterious": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
    )


class AudioConfig(BaseModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    pause_between_panels_ms: int = 300
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
