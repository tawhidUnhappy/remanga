"""Every configurable area of remanga, as one list.

A `Section` is a title, a function that renders the setting's *current*
value, and a function that changes it. That's what turns the old fixed
eight-step walkthrough - which made you answer all eight questions to fix
one - into a menu you can enter anywhere and leave at any point, while
keeping "walk me through everything, in order" available for a first run
(the list is ordered, so running it top to bottom is exactly the original
walkthrough).

`current` is what makes the menu worth reading: the resolution row says
"1080p Full HD (1920x1080)" before you open it, so the settings screen
doubles as the status screen for settings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from remanga.config import RemangaConfig
from remanga.settings import engine, tuning, video
from remanga.settings.assets import ASSETS, asset_relevant, asset_status, run_asset_menu
from remanga.settings.presets import background_label, language_label, resolution_label
from remanga.settings.vision import configure_vision_outputs, package_summary


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    describe: Callable[[RemangaConfig], str]
    run: Callable[[RemangaConfig], None]
    detail: str = ""


def _assets_summary(config: RemangaConfig) -> str:
    parts: list[str] = []
    for spec in ASSETS:
        if not asset_relevant(config, spec):
            continue
        _ok, badge, _ = asset_status(config, spec)
        parts.append(f"{spec.key}: {badge}")
    return ", ".join(parts)


SECTIONS: tuple[Section, ...] = (
    Section(
        "engine", "TTS engine",
        # The voice belongs to the engine now (see config/tts.py), so the
        # engine row states both: picking an engine IS picking a narrator,
        # and a row that named only the model would hide half of what
        # changing it does.
        lambda c: f"{c.tts.spec.display_name} · {c.tts.kokoro.spec.label}"
        if c.tts.active_voice else f"{c.tts.spec.display_name} · no voice set",
        engine.configure_engine,
        detail="which model synthesizes the narration, and the voice it narrates in",
    ),
    Section(
        "voice", "Narrator voice",
        lambda c: f"{c.tts.kokoro.spec.label} ({c.tts.kokoro.spec.name}, grade {c.tts.kokoro.spec.grade})"
        if c.tts.active_voice else "no voice set",
        engine.configure_voice,
        detail="which of the engine's built-in voices reads every panel",
    ),
    Section(
        "assets", "Assets (BGM)",
        _assets_summary, run_asset_menu,
        detail="the shared files every project mixes with",
    ),
    Section(
        "language", "Narration language",
        language_label, engine.configure_language,
    ),
    Section(
        "pacing", "Narration pacing",
        lambda c: f"{c.tts.speed:g}x speed · {c.audio.pause_between_panels_ms}ms between panels",
        tuning.configure_pacing,
        detail="how fast the narration reads, and how long each panel is held after it",
    ),
    Section(
        "levels", "Audio levels",
        lambda c: (f"voice {c.tts.kokoro.volume_boost_db:+.1f}dB · music {c.audio.bgm_volume_db:+.1f}dB"
                   + (f" ducked {c.audio.duck_depth_db:+.1f}dB" if c.audio.duck_music_under_narration
                      else " (fixed)")
                   + f" · {'normalized' if c.audio.enable_loudnorm else 'not normalized'}"),
        tuning.configure_levels,
        detail="voice-vs-music balance, ducking the music under speech, and loudness normalization",
    ),
    Section(
        "detection", "Panel detection",
        lambda c: ", ".join(n for n, on in (
            ("MAGI", c.marker.magi_enabled), ("gutter-snap", c.cropper.snap_to_gutters),
            ("trim", c.cropper.trim_panel_whitespace),
            ("dedupe", c.cropper.dedupe_duplicate_panels)) if on) or "all passes off",
        tuning.configure_panel_detection,
        detail="which cleanup passes run between downloading a page and narrating it",
    ),
    Section(
        "framing", "Panel framing",
        lambda c: (f"{c.video.panel_padding_percent:g}% padding"
                   f"{' (adaptive)' if c.video.auto_adaptive_padding else ''}"
                   f" · {c.video.panel_border_width}px border"),
        tuning.configure_framing,
        detail="how each panel sits inside the video frame",
    ),
    Section(
        "vision", "Vision outputs (what to generate/zip)",
        lambda c: package_summary(c.cropper.package), configure_vision_outputs,
        detail="what a cropped chapter gets packaged into for an LLM upload",
    ),
    Section(
        "resolution", "Video resolution",
        resolution_label, video.configure_resolution,
    ),
    Section(
        "background", "Canvas background",
        background_label, video.configure_background,
    ),
    Section(
        "hardware", "Hardware acceleration",
        lambda c: (f"{c.system.gpu_codec} preferred" if c.system.prefer_gpu
                   else f"{c.system.fallback_codec} (CPU only)"),
        video.configure_hardware,
    ),
)

SECTION_BY_KEY = {section.key: section for section in SECTIONS}
