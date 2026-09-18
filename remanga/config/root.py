"""RemangaConfig: every subsystem's settings, config.json load/save, and the
per-manga layer over it.

config.json is this machine. The settings that describe the work rather than
the computer - tts.*, audio.*, video.*, pdf.* - can be overridden per project,
in that project's project.json under "settings". `for_project()` layers them
over config.json; `save()` on the result writes each change back to whichever
file owns it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from remanga.config.base import ConfigModel
from remanga.json_io import read_json, write_json
from remanga.paths import (
    CONFIG_EXAMPLE_PATH,
    CONFIG_PATH,
    load_project_metadata,
    save_project_metadata,
)

from .audio import AudioConfig
from .cropper import CropperConfig
from .downloader import DownloaderConfig
from .marker import MarkerConfig, ShortcutsConfig
from .pdf import PdfConfig
from .reviewer import ReviewerConfig
from .system import SystemConfig
from .tts import TTSConfig
from .video import VideoConfig
from .writer import WriterConfig

# Where a project's own overrides live inside its project.json.
PROJECT_SETTINGS_KEY = "settings"

# What a manga is allowed to have its own answer for: the voice that reads it,
# the music under it, the size and look of its video, its PDF cap.
PROJECT_SCOPED_PREFIXES = ("tts.", "audio.", "video.", "pdf.", "cropper.")


def is_project_scoped(dotted: str) -> bool:
    """Whether this dotted field is something a project may override, rather
    than a fact about this computer."""
    return dotted.startswith(PROJECT_SCOPED_PREFIXES)


def _flatten(model: BaseModel, prefix: str = "") -> dict[str, Any]:
    """Every leaf field of a config model as {dotted name: value}. Nested
    models recurse; anything else (including lists) is a leaf."""
    flat: dict[str, Any] = {}
    for name in type(model).model_fields:
        value = getattr(model, name)
        dotted = f"{prefix}{name}"
        if isinstance(value, BaseModel):
            flat.update(_flatten(value, f"{dotted}."))
        else:
            flat[dotted] = value
    return flat


def _migrate_override_key(dotted: str) -> tuple[str, ...]:
    """The dotted path an override written by an older version applies to
    today: Kokoro's settings moved from `tts.kokoro.*` to `tts.*`; other
    engines' settings no longer exist."""
    renamed = {"audio.pause_between_panels_ms": "audio.pause_between_pages_ms",
               "video.panel_padding_percent": "video.page_padding_percent",
               "video.panel_border_width": "video.page_border_width",
               "video.panel_border_color": "video.page_border_color"}
    if dotted in renamed:
        return (renamed[dotted],)
    if dotted.startswith("tts.kokoro."):
        return ("tts." + dotted[len("tts.kokoro."):],)
    if dotted.startswith("tts.") and dotted.count(".") > 1:
        return ()
    return (dotted,)


def _apply(model: BaseModel, dotted: str, value: Any) -> None:
    """Sets one dotted field, ignoring a path that no longer exists - an
    override written by an older version must not break loading."""
    *parents, attr = dotted.split(".")
    target: Any = model
    for name in parents:
        target = getattr(target, name, None)
        if target is None:
            return
    if hasattr(target, attr):
        setattr(target, attr, value)


class RemangaConfig(ConfigModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)
    pdf: PdfConfig = Field(default_factory=PdfConfig)
    cropper: CropperConfig = Field(default_factory=CropperConfig)
    marker: MarkerConfig = Field(default_factory=MarkerConfig)
    shortcuts: ShortcutsConfig = Field(default_factory=ShortcutsConfig)
    reviewer: ReviewerConfig = Field(default_factory=ReviewerConfig)
    writer: WriterConfig = Field(default_factory=WriterConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)

    # The manga this instance is scoped to, if any. Set by for_project() and
    # read by save() - it's the whole difference between "change this setting"
    # and "change this setting for this manga".
    _project: str | None = PrivateAttr(default=None)

    @property
    def project(self) -> str | None:
        return self._project

    def for_project(self, project_name: str) -> RemangaConfig:
        """This machine's configuration as it applies to one manga: a copy
        with that project's saved overrides layered on, tagged so that saving
        it writes them back where they came from.

        Always a copy - the caller's own config object is shared by everything
        else in the process and must not quietly become one project's."""
        scoped = self.model_copy(deep=True)
        overrides = load_project_metadata(project_name).get(PROJECT_SETTINGS_KEY)
        if isinstance(overrides, dict):
            for dotted, value in overrides.items():
                if is_project_scoped(str(dotted)):
                    for target in _migrate_override_key(str(dotted)):
                        _apply(scoped, target, value)
        scoped._project = project_name
        return scoped

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> RemangaConfig:
        """Load configuration from JSON file or create with defaults."""
        target_path = Path(config_path) if config_path else CONFIG_PATH
        if not target_path.exists():
            target_path = CONFIG_EXAMPLE_PATH

        if target_path.exists():
            return cls.model_validate(read_json(target_path))
        return cls()

    def save(self, output_path: Path | str = CONFIG_PATH) -> None:
        """Writes the configuration back where it belongs.

        Unscoped, that's config.json, exactly as it always was. Scoped to a
        project (see for_project), each changed field goes to whichever file
        owns it: a manga-level setting to that project's project.json, a
        machine-level one still to config.json - so turning on GPU encoding
        from inside a project doesn't silently become that project's private
        opinion, and choosing its narrator doesn't rewrite every other
        project's."""
        if self._project is None:
            write_json(output_path, self.model_dump())
            return

        base = RemangaConfig.load()
        mine, theirs = _flatten(self), _flatten(base)
        changed = {key: value for key, value in mine.items() if value != theirs.get(key)}

        machine = {key: value for key, value in changed.items() if not is_project_scoped(key)}
        if machine:
            for dotted, value in machine.items():
                _apply(base, dotted, value)
            write_json(output_path, base.model_dump())

        # Recomputed in full rather than merged: a setting put back to what
        # config.json says stops being an override and drops out of the file,
        # instead of lingering as an override that happens to match.
        overrides = {key: value for key, value in mine.items()
                     if is_project_scoped(key) and value != theirs.get(key)}
        save_project_metadata(self._project, {PROJECT_SETTINGS_KEY: overrides})
