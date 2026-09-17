"""How page narration shows up in `status`: whether the pages upload is built
and whether a reply is pasted."""

from __future__ import annotations

from typing import Any

from remanga.extensions.spec import StatusHooks, StatusRow


def _facts(project: str, chapter: str) -> dict[str, Any]:
    from remanga.extensions.page_narration.paths import get_reply_path
    from remanga.extensions.page_narration.upload import upload_files
    from remanga.json_io import has_real_json_content

    return {
        "page_upload_built": bool(upload_files(project, chapter)),
        "page_reply_exist": has_real_json_content(get_reply_path(project, chapter)),
    }


def hooks() -> StatusHooks:
    from remanga.status.badges import done, off

    return StatusHooks(
        facts=_facts,
        rows=(
            StatusRow("   2d. Page Mode Upload   ",
                      lambda st: done("Built (page-upload)") if st["page_upload_built"] else off("not built"),
                      after="llm_reply", key="page_upload"),
            StatusRow("   2e. Page Mode Reply    ",
                      lambda st: done("Pasted (page_narration.json)") if st["page_reply_exist"] else off("not pasted"),
                      after="page_upload", key="page_reply"),
        ),
    )
