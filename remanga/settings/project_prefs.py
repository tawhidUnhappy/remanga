"""Choices remembered per project, across its chapters.

config.json holds the defaults for every project on this machine. A few
choices, though, belong to *one manga*: which upload formats that project's
LLM workflow wants built, what a wipe should keep for it, and which pipeline
steps `run` executes for it. Re-answering those identically for chapter after
chapter is exactly the kind of question this pipeline shouldn't be asking
twice, so the answer is written to that project's project.json the first time
it's given and pre-selected from then on.

One file, not one per setting: everything a project remembers lives in its
project.json, so "what has this project chosen?" is one file to open and one
file to copy when a project moves.

Precedence, everywhere both exist: an explicit answer for this run (a CLI
flag, or the wizard's checklist) beats the project's remembered choice,
which beats config.json's global defaults. Nothing here ever writes
config.json - a per-project preference must not quietly redefine what every
other project does."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Set

from remanga.config import CropperConfig, RemangaConfig
from remanga.paths import get_pipeline_path, load_project_metadata, save_project_metadata
from remanga.settings.vision import package_switch_names

PACKAGE_FORMATS_KEY = "package_formats"
WIPE_KEEP_KEY = "wipe_keep"
PIPELINE_KEY = "pipeline"

# What a user types (or the wizard sends) to mean "none of them" - an empty
# selection is a real answer for both settings: build nothing extra, or keep
# nothing at all.
_NOTHING = ("none", "nothing")


def _stored_list(project_name: str, key: str) -> Optional[List[str]]:
    """The remembered list, or None when this project has never answered.
    None and [] are different answers here - "never chosen" falls back to
    config.json, "chose nothing" is an empty selection the user meant."""
    value = load_project_metadata(project_name).get(key)
    if not isinstance(value, list):
        return None
    return [str(item) for item in value]


# --- packaging formats -----------------------------------------------------


def parse_package_formats(raw: Optional[str]) -> Optional[List[str]]:
    """`--formats` (or the wizard's checklist) as a validated list of switch
    names. None stays None ("not answered this run"); 'none' becomes []."""
    if raw is None:
        return None
    text = raw.strip()
    if text.lower() in _NOTHING:
        return []
    valid = package_switch_names()
    names, unknown = [], []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if token not in valid:
            unknown.append(token)
        elif token not in names:
            names.append(token)
    if unknown:
        raise ValueError(
            f"Unknown package format(s): {', '.join(unknown)}. Valid formats: {', '.join(valid)}."
        )
    return names


def remembered_package_formats(project_name: str) -> Optional[List[str]]:
    return _stored_list(project_name, PACKAGE_FORMATS_KEY)


def remember_package_formats(project_name: str, formats: Sequence[str]) -> None:
    save_project_metadata(project_name, {PACKAGE_FORMATS_KEY: list(formats)})


def active_package_formats(config: RemangaConfig, project_name: str,
                           formats: Optional[Sequence[str]] = None) -> List[str]:
    """Which formats are actually on for this project right now, applying the
    full precedence: this run's answer, else the project's memory, else
    config.json's switches."""
    if formats is not None:
        return list(formats)
    remembered = remembered_package_formats(project_name)
    if remembered is not None:
        return remembered
    package = config.cropper.package
    return [name for name in package_switch_names() if getattr(package, name)]


def cropper_config_for(config: RemangaConfig, project_name: str,
                       formats: Optional[Sequence[str]] = None) -> CropperConfig:
    """A CropperConfig whose packaging switches reflect this project's active
    formats, leaving every other cropper setting (padding, gutter snapping,
    trimming, the size cap) exactly as configured.

    Returned as a copy: the live config object is shared by everything else
    in the process, and a project-scoped override must not leak into it."""
    active = set(active_package_formats(config, project_name, formats))
    cropper = config.cropper.model_copy(deep=True)
    for name in package_switch_names():
        setattr(cropper.package, name, name in active)
    return cropper


# --- wipe keep-list --------------------------------------------------------


def remembered_wipe_keep(project_name: str) -> Optional[Set[str]]:
    remembered = _stored_list(project_name, WIPE_KEEP_KEY)
    return set(remembered) if remembered is not None else None


def remember_wipe_keep(project_name: str, keep_names: Iterable[str]) -> None:
    save_project_metadata(project_name, {WIPE_KEEP_KEY: sorted(keep_names)})


# --- the project's pipeline ------------------------------------------------


def remembered_pipeline(project_name: str) -> Optional[List[str]]:
    """This project's ordered pipeline step names, or None if it has never
    chosen - in which case remanga.pipeline falls back to DEFAULT_STEPS.

    Lives here, in project.json, next to the project's other remembered
    answers. It used to be a pipeline.json of its own alongside it; a project
    that still has one is read from it (see remanga.pipeline.load_pipeline)
    until the next save moves it in here."""
    return _stored_list(project_name, PIPELINE_KEY)


def remember_pipeline(project_name: str, steps: Sequence[str]) -> None:
    """Saves the pipeline, and retires a legacy pipeline.json if this project
    still had one - leaving it in place would leave a file that looks like
    the pipeline, reads like the pipeline, and is no longer the pipeline."""
    save_project_metadata(project_name, {PIPELINE_KEY: list(steps)})
    legacy = get_pipeline_path(project_name)
    if legacy.exists():
        legacy.unlink()
