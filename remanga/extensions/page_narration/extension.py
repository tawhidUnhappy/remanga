"""The page narration extension's manifest: everything it plugs into remanga.

Page mode skips cropping: the chapter's pages go to the LLM whole, it writes
one narration entry per page that covers every panel on it, and each story
page becomes that page's one panel - so TTS, mix, render and every check
downstream run exactly as they do for cropped panels."""

from __future__ import annotations

from remanga.extensions.spec import Extension, Placed


def _commands():
    from remanga.extensions.page_narration.commands import PAGE_NARRATION, PAGE_UPLOAD, PAGE_UPLOAD_ALL

    return (
        Placed(PAGE_UPLOAD, after="package"),
        Placed(PAGE_NARRATION, after="narration-init"),
        Placed(PAGE_UPLOAD_ALL, after="package-all"),
    )


def _steps():
    from remanga.extensions.page_narration.steps import PAGE_NARRATION_STEP

    return (Placed(PAGE_NARRATION_STEP, after="narration"),)


def _settings():
    from remanga.extensions.page_narration.settings import configure_page_narration, page_narration_summary
    from remanga.settings.section_spec import Section

    section = Section(
        "page_narration", "Page narration", page_narration_summary, configure_page_narration,
        detail="page mode: which pages uploads page-upload builds, and their size cap",
    )
    return (Placed(section, after="llm_crop"),)


def _config_model():
    from remanga.extensions.page_narration.config import PageNarrationConfig

    return PageNarrationConfig


def _status():
    from remanga.extensions.page_narration.status import hooks

    return hooks()


EXTENSION = Extension(
    name="page_narration",
    title="Page narration",
    description="Narrate whole pages instead of cropped panels - no marking or cropping, each page shown "
                "whole and narrated panel by panel",
    commands=_commands,
    steps=_steps,
    settings=_settings,
    config_model=_config_model,
    status=_status,
    generated_kinds=("page_upload",),
    source_files=("page_narration.json",),
    alternative_steps=("page-narration",),
)
