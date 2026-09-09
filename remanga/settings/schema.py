"""Every config field, described from the models themselves.

The settings menu has always been hand-written screens: good ones, because a
screen can group settings by the question being asked rather than by which
model they live in, and can explain a trade-off in a sentence. But a
hand-written screen only covers what somebody remembered to write, and an
audit found 96 config fields with 24 of them reachable. The other 72 were
editable only by opening config.json in a text editor - which is not a
setting anyone finds, and is exactly how a project ends up mis-tuned in a way
nobody can explain.

So this module derives the full list from the pydantic models instead. A
field added anywhere under RemangaConfig shows up in the browser
(settings/browser.py) with no extra work: its type decides the editor, its
validators supply the bounds, its default is the reset value. There is
nothing to keep in sync, which is the only way a "you can configure
everything here" claim stays true after the next feature.

The curated screens stay, and stay first. This is the floor, not the
replacement: someone tuning the voice-vs-music balance should get the screen
that explains what loudness normalization does to it, not a flat list of
every float in the program."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from remanga.config import RemangaConfig

# Fields nothing good comes of editing from a menu. Not hidden because they
# are dangerous - config.json still holds them - but because putting a Hugging
# Face repo id or a model directory in the same list as "video resolution"
# makes the list worse at its job. Matched on the LAST path segment.
_INTERNAL_SUFFIXES = frozenset({
    "hf_repo_id", "model_dir", "cfg_path", "magi_repo_id", "magi_model_dir",
    "hf_token_path",
})


@dataclass(frozen=True)
class FieldSpec:
    """One editable config field, and everything a generic editor needs."""

    dotted: str                 # "audio.bgm_volume_db"
    section: str                # "audio"
    name: str                   # "bgm_volume_db"
    kind: str                   # "bool" | "int" | "float" | "str" | "choice"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """"bgm_volume_db" -> "Bgm volume db". Derived rather than stored:
        a hand-written label is one more thing to fall out of date, and a
        field whose name does not read clearly is better renamed than
        papered over here."""
        return self.name.replace("_", " ").capitalize()

    @property
    def bounds_hint(self) -> str:
        if self.minimum is None and self.maximum is None:
            return ""
        lo = "" if self.minimum is None else f"{self.minimum:g}"
        hi = "" if self.maximum is None else f"{self.maximum:g}"
        return f"{lo}..{hi}"


def _numeric_bounds(field: Any) -> tuple[float | None, float | None]:
    """Bounds from the field's own validators, so a menu cannot offer a value
    the model would then reject."""
    lo = hi = None
    for meta in getattr(field, "metadata", ()) or ():
        for attr, setter in (("ge", "lo"), ("gt", "lo"), ("le", "hi"), ("lt", "hi")):
            value = getattr(meta, attr, None)
            if value is not None:
                if setter == "lo":
                    lo = float(value)
                else:
                    hi = float(value)
    return lo, hi


def _kind_of(annotation: Any) -> str:
    """The editor a field wants. Optionals are unwrapped to their real type -
    `str | None` is still a string to a person typing one in."""
    if get_origin(annotation) is not None:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            annotation = args[0]
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    return "str"


def _walk(model: BaseModel, prefix: str, section: str) -> list[FieldSpec]:
    out: list[FieldSpec] = []
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            out += _walk(value, f"{prefix}{name}.", section or name)
            continue
        if name in _INTERNAL_SUFFIXES:
            continue
        lo, hi = _numeric_bounds(field)
        out.append(FieldSpec(
            dotted=f"{prefix}{name}", section=section or "general", name=name,
            kind=_kind_of(field.annotation), default=field.default,
            minimum=lo, maximum=hi,
        ))
    return out


def all_fields(config: RemangaConfig | None = None) -> list[FieldSpec]:
    """Every editable field under RemangaConfig, in declaration order."""
    return _walk(config or RemangaConfig(), "", "")


def fields_by_section(config: RemangaConfig | None = None) -> dict[str, list[FieldSpec]]:
    grouped: dict[str, list[FieldSpec]] = {}
    for spec in all_fields(config):
        grouped.setdefault(spec.section, []).append(spec)
    return grouped
