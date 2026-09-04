"""The "what to generate / what to zip for upload" checklist.

Nine independent yes/no switches (see config.PackageConfig), and this
screen is generated from that model - label, one-line explanation and
example output path all come from each field's own metadata. Before, the
same nine switches were spelled out three times: once in the model, once as
a hand-written question per switch, and once more in a summary line that
enumerated them all by hand. Adding a tenth format used to mean editing
three lists; now it means adding one field."""

from __future__ import annotations

from typing import List

from remanga.config import PackageConfig, RemangaConfig
from remanga.console import console
from remanga.tui import Choice, ask_number, is_cancel, multiselect

# Switches whose "on" state only means "split the parts", so the size cap
# question is worth asking. Derived by name suffix rather than listed, so a
# future `*_splite` format is covered automatically.
_SPLIT_SUFFIXES = ("_splite", "_splites")


def _boolean_fields() -> List[str]:
    return [
        name for name, field in PackageConfig.model_fields.items()
        if field.annotation is bool
    ]


def is_split_switch(name: str) -> bool:
    return name.endswith(_SPLIT_SUFFIXES)


def package_choices(config: RemangaConfig) -> List[Choice]:
    """One Choice per switch, pre-checked to its current value, with the
    field's own description as the fine print and its example output as the
    hint. `sheets_folders` gets the live panels-per-folder count folded into
    its hint - a number that's already in config.json and would otherwise be
    something the user has to go look up."""
    package = config.cropper.package
    rows: List[Choice] = []
    for name in _boolean_fields():
        field = PackageConfig.model_fields[name]
        extra = field.json_schema_extra or {}
        produces = str(extra.get("produces", ""))
        if name == "sheets_folders":
            produces += f" ({config.cropper.panels_per_folder} panels each)"
        rows.append(Choice(
            label=field.title or name,
            hint=produces,
            detail=field.description or "",
            value=name,
            checked=bool(getattr(package, name)),
        ))
    return rows


def package_summary(package: PackageConfig) -> str:
    """The active formats as one line, e.g. "sheets, panels_zip (split at
    50MB)". Built from whatever is on, so it can't fall out of step with the
    switches themselves."""
    active = [name for name in _boolean_fields() if getattr(package, name)]
    if not active:
        return "panels only"
    line = ", ".join(active)
    if any(is_split_switch(name) for name in active):
        line += f" (split at {package.max_mb:g}MB)"
    return line


def configure_vision_outputs(config: RemangaConfig) -> None:
    """Edits every packaging switch at once as a checklist, then asks for the
    size cap only when a split format is actually on. Saves config.json
    itself, like every other configure_* helper here."""
    package = config.cropper.package
    picked = multiselect(
        "What to generate / zip for upload",
        package_choices(config),
        note=("panels/ is always produced - everything here is optional, losslessly "
              "re-encoded, and never touches panels/ itself"),
    )
    if is_cancel(picked):
        return

    for name in _boolean_fields():
        setattr(package, name, name in picked)

    if any(is_split_switch(name) for name in picked):
        package.max_mb = ask_number(
            "Size cap per part, in MB", default=package.max_mb, minimum=1, maximum=2000,
            note="each part is kept at or under this by splitting on image/page boundaries",
        )

    config.save()
    console.print(f"[bold green]✓ Vision outputs:[/] {package_summary(package)}")
