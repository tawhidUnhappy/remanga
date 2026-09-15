"""The LLM crop extension's manifest: everything it plugs into remanga.

Declarative on purpose - every factory imports what it needs only when a
registry calls it (see remanga.extensions.spec)."""

from __future__ import annotations

from remanga.extensions.spec import Extension, Placed


def _commands():
    from remanga.commands.catalog.llm_crop import LLM_CROP_CHAPTER_COMMANDS, LLM_CROP_PROJECT_COMMANDS

    crop_grid, llm_crop = LLM_CROP_CHAPTER_COMMANDS
    crop_grid_all, llm_crop_all = LLM_CROP_PROJECT_COMMANDS
    return (
        # Right after the Panel Marker's commands, which these replace.
        Placed(crop_grid, after="mark"),
        Placed(llm_crop, after="crop-grid"),
        Placed(crop_grid_all, after="view-marks"),
        Placed(llm_crop_all, after="crop-grid-all"),
    )


def _steps():
    from remanga.extensions.llm_crop.steps import LLM_CROP_STEP

    return (Placed(LLM_CROP_STEP, after="mark"),)


def _settings():
    from remanga.settings.llm_crop import configure_llm_crop, llm_crop_summary
    from remanga.settings.section_spec import Section

    section = Section(
        "llm_crop", "LLM crop (Gemini)", llm_crop_summary, configure_llm_crop,
        detail="what crop-grid builds for Gemini, how readily it groups panels, and how its crops are cut",
    )
    return (Placed(section, after="detection"),)


EXTENSION = Extension(
    name="llm_crop",
    title="LLM crop (Gemini)",
    description="Crop chapters with Gemini from gridded pages - bubbles kept with their panel, "
                "groups of panels, neighbours painted out",
    commands=_commands,
    steps=_steps,
    settings=_settings,
    generated_kinds=("grid_pages", "grid_zip", "grid_pdf", "llm_crop"),
    source_files=("llm_crops.json",),
    alternative_steps=("llm-crop",),
)
