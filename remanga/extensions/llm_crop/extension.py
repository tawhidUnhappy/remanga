"""The LLM crop extension's manifest: everything it plugs into remanga.

Declarative on purpose - every factory imports what it needs only when a
registry calls it (see remanga.extensions.spec)."""

from __future__ import annotations

from remanga.extensions.spec import Extension, Placed


def _commands():
    from remanga.extensions.llm_crop.commands import AUTO, CROP_GRID, CROP_GRID_ALL, LLM_CROP, LLM_CROP_ALL

    return (
        # Right after the Panel Marker's commands, which these replace.
        Placed(CROP_GRID, after="mark"),
        Placed(LLM_CROP, after="crop-grid"),
        Placed(CROP_GRID_ALL, after="view-marks"),
        Placed(LLM_CROP_ALL, after="crop-grid-all"),
        # First in Run & check: the whole run, hands-off.
        Placed(AUTO, after="remix"),
    )


def _steps():
    from remanga.extensions.llm_crop.steps import LLM_CROP_STEP

    return (Placed(LLM_CROP_STEP, after="mark"),)


def _settings():
    from remanga.extensions.llm_crop.settings import configure_llm_crop, llm_crop_summary
    from remanga.settings.section_spec import Section

    section = Section(
        "llm_crop", "LLM crop (Gemini)", llm_crop_summary, configure_llm_crop,
        detail="what crop-grid builds for Gemini, how readily it groups panels, and how its crops are cut",
    )
    return (Placed(section, after="detection"),)


def _config_model():
    from remanga.extensions.llm_crop.config import LLMCropConfig

    return LLMCropConfig


def _status():
    from remanga.extensions.llm_crop.status import hooks

    return hooks()


EXTENSION = Extension(
    name="llm_crop",
    title="LLM crop (Gemini)",
    description="Crop chapters with Gemini from gridded pages - bubbles kept with their panel, "
                "groups of panels, neighbours painted out",
    commands=_commands,
    steps=_steps,
    settings=_settings,
    config_model=_config_model,
    status=_status,
    generated_kinds=("grid_pages", "grid_zip", "grid_pdf", "llm_crop"),
    source_files=("llm_crops.json",),
    alternative_steps=("llm-crop",),
)
