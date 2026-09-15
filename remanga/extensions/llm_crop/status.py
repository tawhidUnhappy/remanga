"""How LLM crop shows up in `status` and in the chapter lists: two rows after
the pages zip, and two summary stages below "Crops JSON Ready"."""

from __future__ import annotations

from typing import Any

from remanga.extensions.spec import StatusHooks, StatusRow, SummaryStage


def _facts(project: str, chapter: str) -> dict[str, Any]:
    """Disk-only, like the core facts: any grid upload on disk counts as
    built (which formats a project builds is config, and status reads none),
    and a reply counts once it's more than the empty placeholder."""
    from remanga.extensions.llm_crop.paths import (
        get_grid_pages_dir,
        get_grid_pdf_dir,
        get_grid_zip_dir,
        get_llm_crops_path,
    )
    from remanga.json_io import has_real_json_content

    pdf_dir = get_grid_pdf_dir(project, chapter, create=False)
    return {
        "crop_grid_built": (
            any(get_grid_zip_dir(project, chapter, create=False).glob("grid_*.zip"))
            or any(pdf_dir.glob("grid_*.pdf")) or any(pdf_dir.glob("grid_*.zip"))
            or any(get_grid_pages_dir(project, chapter, create=False).glob("*.png"))
        ),
        "llm_reply_exist": has_real_json_content(get_llm_crops_path(project, chapter)),
    }


def hooks() -> StatusHooks:
    from remanga.status.badges import done, off

    return StatusHooks(
        facts=_facts,
        rows=(
            StatusRow("   2b. Gemini Crop Grid   ",
                      lambda st: done("Built (crop-grid)") if st["crop_grid_built"] else off("not built"),
                      after="pages_zip", key="crop_grid"),
            StatusRow("   2c. Gemini Crop Reply  ",
                      lambda st: done("Pasted (llm_crops.json)") if st["llm_reply_exist"] else off("not pasted"),
                      after="crop_grid", key="llm_reply"),
        ),
        summaries=(
            SummaryStage("llm_reply", lambda st: "Gemini Crops Pasted (run llm-crop)" if st["llm_reply_exist"]
                         else None, after="crops_json"),
            SummaryStage("crop_grid", lambda st: "Crop Grid Ready (awaiting Gemini)" if st["crop_grid_built"]
                         else None, after="llm_reply"),
        ),
    )
