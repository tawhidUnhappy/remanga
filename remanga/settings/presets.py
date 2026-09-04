"""Declarative option tables for the settings screens that offer a small,
fixed set of sensible values: video resolution, canvas background, and
narration language.

These are the only genuinely hand-written lists left in the settings
package - there is no file on disk or model metadata to derive them from -
so they're kept here, as data, in one place rather than inline in the
screens that show them. Every one of them stays open-ended: resolution has
Custom, language has "Other…", so the table is a set of shortcuts rather
than a limit on what can be configured."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from remanga.config import RemangaConfig
from remanga.tui import Choice


@dataclass(frozen=True)
class Resolution:
    label: str
    width: int
    height: int
    note: str


RESOLUTIONS: Tuple[Resolution, ...] = (
    Resolution("1080p Full HD", 1920, 1080, "standard YouTube 1080p broadcast"),
    Resolution("1440p 2K QHD", 2560, 1440, "higher YouTube VP9/AV1 bitrate allocation"),
    Resolution("2160p 4K UHD", 3840, 2160, "master render quality, slowest encode"),
    Resolution("720p HD", 1280, 720, "fast preview renders"),
)

BACKGROUND_STYLES: Tuple[Tuple[str, str, str], ...] = (
    ("blur", "Bokeh canvas blur", "blurred copy of the current panel behind it"),
    ("solid", "Solid color canvas", "flat background_color behind every panel"),
)

# Language codes remanga passes straight through to the TTS engine. Any code
# the engine accepts works - see language_choices()'s "Other…" row.
LANGUAGES: Tuple[Tuple[str, str], ...] = (
    ("EN", "English"),
    ("JA", "Japanese"),
    ("ZH", "Chinese (Mandarin)"),
    ("ES", "Spanish"),
    ("AR", "Arabic"),
    ("KO", "Korean"),
    ("FR", "French"),
    ("DE", "German"),
)

CUSTOM = "__custom__"


def resolution_choices(config: RemangaConfig) -> List[Choice]:
    current = (config.video.width, config.video.height)
    rows = [
        Choice(label=res.label, hint=f"{res.width}x{res.height}", detail=res.note,
               value=(res.width, res.height),
               badge="current" if (res.width, res.height) == current else "")
        for res in RESOLUTIONS
    ]
    if current not in [(r.width, r.height) for r in RESOLUTIONS]:
        rows.insert(0, Choice(label="Keep current", hint=f"{current[0]}x{current[1]}",
                              value=current, badge="current"))
    rows.append(Choice(label="Custom…", hint="enter width and height", value=CUSTOM))
    return rows


def background_choices(config: RemangaConfig) -> List[Choice]:
    return [
        Choice(label=label, hint=note, value=value,
               badge="current" if config.video.background_style == value else "")
        for value, label, note in BACKGROUND_STYLES
    ]


def language_choices(config: RemangaConfig) -> List[Choice]:
    current = (config.tts.lang or "EN").upper()
    rows = [
        Choice(label=name, hint=code, value=code, badge="current" if code == current else "")
        for code, name in LANGUAGES
    ]
    if current not in [code for code, _ in LANGUAGES]:
        rows.insert(0, Choice(label=current, hint="from config.json", value=current, badge="current"))
    rows.append(Choice(label="Other…", hint="enter a language code", value=CUSTOM))
    return rows


def resolution_label(config: RemangaConfig) -> str:
    match = next((r for r in RESOLUTIONS if (r.width, r.height) == (config.video.width, config.video.height)), None)
    size = f"{config.video.width}x{config.video.height}"
    return f"{match.label} ({size})" if match else size


def language_label(config: RemangaConfig) -> str:
    code = (config.tts.lang or "EN").upper()
    name: Optional[str] = next((n for c, n in LANGUAGES if c == code), None)
    return f"{name} ({code})" if name else code


def background_label(config: RemangaConfig) -> str:
    return next((label for value, label, _ in BACKGROUND_STYLES
                 if value == config.video.background_style), config.video.background_style)
