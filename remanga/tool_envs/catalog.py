"""The tool environments - every "tool" plug-in (remanga/plugins/): each
engine or model that runs in its own isolated venv registers its ToolSpec in
its plug-in folder.

bootstrap.sh, `remanga setup` and a tool's own first use all provision from
this list, so none of them can drift from the others."""

from __future__ import annotations

from remanga.tool_envs.spec import ToolSpec


def tools() -> tuple[ToolSpec, ...]:
    from remanga import plugins

    return tuple(plugins.items("tool"))


def tool_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in tools())


def tool_spec(name: str) -> ToolSpec | None:
    """The entry for `name`, or None if no tool is called that."""
    from remanga import plugins

    return plugins.find("tool", name)
