"""What each kind of plug-in describes. Every field that is code is a
reference ("module:attr", see _registry.resolve) so registering a plug-in
imports nothing heavy. A `tool` plug-in is a tool_envs.ToolSpec as it is.

    tts     TTSEngine - a narrator
    layout  Layout    - how a chapter's images are marked into panels
    source  Source    - where manga come from
    job     Job       - something the queue can do to a chapter, unattended
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Ref = Any   # "package.module:attr", or the object itself


@dataclass(frozen=True)
class TTSEngine:
    """A narrator engine. config.json keeps its settings in `tts.<name>`.

    config          its settings block - a remanga.config.base.ConfigModel
                    with voice_options(), voice_label, voice_detail and
                    identity() (see plugins/kokoro/config.py)
    synthesizer     an audio.synth.BaseWorkerSynthesizer subclass, built
                    with (tts_config, audio_config)
    settings_rows   (config) -> list[ui.voice_rows.Row]: its own rows on the
                    Settings screen, under the engine row
    prepare         (tts_config, subtitles_config) -> None, run before the
                    model loads each chapter - optional
    tool_name       its isolated environment (`.tools/venv-<tool_name>`),
                    registered as a `tool` plug-in
    clones_voice    whether its voice is built from a recording/description
                    rather than picked from a list"""

    name: str
    display_name: str
    summary: str
    tool_name: str
    config: Ref
    synthesizer: Ref
    settings_rows: Ref = None
    prepare: Ref = None
    clones_voice: bool = False
    order: int = 100

    @property
    def config_attr(self) -> str:
        return self.name


@dataclass(frozen=True)
class Layout:
    """How a chapter's images become panels.

    matches     (project, chapter) -> bool: whether a chapter whose project.json
                names no layout is this kind, from its images. The last
                layout in order should match everything (the fallback)
    mark        (project, chapters, config) -> list[str]: opens whatever is
                used to mark these chapters, waits, returns those saved
    pages_dir   (project, chapter, build=True) -> Path: the images the marks
                are on, which the cropper cuts from
    detect      (pages_dir, page_paths, marker_config, on_page_done) ->
                {filename: boxes}: the Panel Marker's "find the panels"
    prepare_cut (project, chapter) -> None: run before cutting - optional"""

    name: str
    display_name: str
    summary: str
    matches: Ref
    mark: Ref
    pages_dir: Ref
    detect: Ref = None
    prepare_cut: Ref = None
    order: int = 100


@dataclass(frozen=True)
class Source:
    """Where manga come from. `client` is built with the DownloaderConfig and
    answers:
        parse_manga_id(source) -> str
        get_manga_info(manga_id) -> dict (title, english_title,
            original_language, layout or None)
        list_chapters_with_status(project, url, force_refresh=False)
        download_chapters(project, chapters, url, force=False)
    `handles(source) -> bool` says whether a link/ID/title is this source's;
    the first source in order is the default for anything none claims."""

    name: str
    display_name: str
    client: Ref
    handles: Ref
    order: int = 100


@dataclass(frozen=True)
class Job:
    """One thing the queue can do to a chapter - the same words as the chapter
    menu. `run` is (project, chapter, config) -> anything; `needs_pages` says
    the chapter must be downloaded first."""

    name: str
    label: str
    help: str
    run: Ref
    needs_pages: bool = True
    order: int = 100
