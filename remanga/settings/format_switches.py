"""A set of upload-format switches on a config model - asked as a checklist,
passed as `--formats`, and saved to the project either way.

The LLM crop grid formats and the page-narration page formats are both a
handful of bool fields on their extension's config model, each field carrying
its own menu text (`title`, `description`, `json_schema_extra["produces"]` and
a `group`). Everything a command needs to offer them is the same: the
checklist rows, the `--formats` parameter with its wizard screen, validating
what was typed, and switching exactly those on for the project. One
definition, so the two can't drift into asking differently.

set_field/get_field are imported where they are used, for the reason
remanga.extensions.llm_crop.settings gives: this module can be loaded while
the settings package is still building itself."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from remanga.console import console
from remanga.tui import Choice, is_cancel, multiselect


@dataclass(frozen=True)
class FormatSwitches:
    """`model`'s bool fields whose `group` is in `groups`, living at the
    dotted config path `prefix`. `what` names them in messages ("grid"), and
    `settings_name` says where else they can be changed."""

    model: type[BaseModel]
    prefix: str
    groups: tuple[str, ...]
    what: str
    settings_name: str

    def names(self) -> list[str]:
        """Every switch, in model order."""
        return [name for name, field in self.model.model_fields.items()
                if (field.json_schema_extra or {}).get("group") in self.groups]

    def section(self, config: Any) -> Any:
        from remanga.settings.fields import get_field

        return get_field(config, self.prefix)

    def active(self, section: Any) -> list[str]:
        return [name for name in self.names() if getattr(section, name)]

    def rows(self, section: Any) -> list[Choice]:
        """One checklist row per switch, checked as `section` has it."""
        rows = []
        for name in self.names():
            field = self.model.model_fields[name]
            rows.append(Choice(
                label=field.title or name,
                hint=str((field.json_schema_extra or {}).get("produces", "")),
                detail=field.description or "",
                value=name,
                checked=bool(getattr(section, name)),
            ))
        return rows

    def parse(self, raw: str | None) -> list[str] | None:
        """`--formats` (or the checklist's answer) as a validated list. None
        stays None - not answered this run, so the project's switches are
        used as they are."""
        if raw is None:
            return None
        valid = self.names()
        names = list(dict.fromkeys(token.strip() for token in raw.split(",") if token.strip()))
        unknown = [name for name in names if name not in valid]
        if unknown:
            raise ValueError(f"Unknown {self.what} format(s): {', '.join(unknown)}. "
                             f"Valid formats: {', '.join(valid)}.")
        if not names:
            raise ValueError(f"Pick at least one {self.what} format: {', '.join(valid)}.")
        return names

    def apply(self, config: Any, formats: list[str] | None) -> None:
        """Switches exactly `formats` on and saves - to the project's
        project.json when `config` is scoped to one, where the settings
        screen saves them too - so later chapters and the pipeline step
        build the same set without asking. None changes nothing."""
        if formats is None or self.active(self.section(config)) == formats:
            return
        from remanga.settings.fields import set_field

        for name in self.names():
            set_field(config, f"{self.prefix}.{name}", name in formats, save=False)
        config.save()
        console.print(f"[dim]{self.what.capitalize()} formats: {', '.join(formats)} - remembered for this "
                      f"project.[/]")

    def param(self, prompt: str, *, skip: Callable[[Any, dict[str, Any]], bool] | None = None,
              step: str = "") -> Any:
        """The `--formats` parameter: a checklist in the wizard, opened on
        what the project builds now. `skip(session, values)` returning True
        leaves it unasked (None), for a command that won't build anything
        this run. `step` names the pipeline step that reuses the choice."""
        from remanga.commands.spec import Param

        def prompter(param: Any, session: Any, values: dict[str, Any]) -> Any:
            if skip is not None and skip(session, values):
                return None
            section = self.section(session.config)
            picked = multiselect(
                param.label, self.rows(section), allow_empty=False,
                note=f"remembered for this project · PDFs and split parts are capped at "
                     f"{section.max_mb:g}MB (change it in {self.settings_name})",
            )
            return picked if is_cancel(picked) else ",".join(picked)

        reuse = f"later runs (and the pipeline's {step} step)" if step else "later runs"
        return Param(
            "formats", ["--formats"], required=False, default=None, prompt=prompt, prompter=prompter,
            help=f"Comma-separated {self.what} formats to build - any of: {', '.join(self.names())}. "
                 f"The wizard offers this as a checklist. Whatever you pick is saved for the project, so "
                 f"{reuse} build the same thing. Left unset: what the project builds now "
                 f"({self.settings_name}).",
        )
