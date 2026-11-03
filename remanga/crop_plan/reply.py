"""An LLM's crop reply - JSON, pasted into chapters/chapter_N/crop_reply.txt -
checked against the crop PDF it answers, and the fix request written when it
does not check out, to paste back into the same chat (the narration's round
trip).

Two kinds of trouble, told apart: a reply the LLM got wrong (a box number the
page does not have, a line it garbled) gets a fix request; a reply pasted into
the wrong place (another chapter's, or one written for an older crop PDF) is
the user's to sort out, and asking the LLM to fix it would only muddle it."""

from __future__ import annotations

from pathlib import Path

from remanga.crop_plan.grammar import Plan

REPLY_NAME = "crop_reply.txt"
FIX_REQUEST_NAME = "crop_fix_request.md"


class CropReplyError(ValueError):
    """A reply that was not used - nothing changed. `fix_request` is the file
    to paste back to the LLM, when it is the LLM's to fix."""

    def __init__(self, message: str, errors: list[str], fix_request: Path | None = None):
        super().__init__(message)
        self.errors = errors
        self.fix_request = fix_request


def misplaced(plan: Plan, chapter: str, record: dict) -> str | None:
    """Why this reply does not belong to this chapter's crop PDF, if it does not."""
    if plan.chapter is not None and plan.chapter != str(chapter):
        return (f"This reply is chapter {plan.chapter}'s, not chapter {chapter}'s - it was pasted into the wrong "
                f"chapter's {REPLY_NAME}.")
    if plan.marks_id is not None and plan.marks_id != record["id"]:
        return (f"This reply answers another crop PDF of chapter {chapter} (marks {plan.marks_id}); the one made "
                f"last is marks {record['id']}. Paste the reply to that one, or send it to the LLM. If this reply "
                f"does answer it, change its first line to: chapter {chapter} marks {record['id']}")
    return None


def shape_problems(plan: Plan, record: dict) -> list[str]:
    """Lines of the wrong kind for the chapter's layout."""
    if record["layout"] == "long_strip" and plan.pages:
        return [f"{plan.pages[0].at()}: this chapter is a long strip - its reply is \"edits\" to the cuts "
                f"(split/join/move/drop/add with rows), not pages"]
    if record["layout"] != "long_strip" and plan.edits:
        return [f"{plan.edits[0].at()}: this chapter is printed pages - its reply is \"pages\", an entry a page, "
                f"not strip edits"]
    return []


def header_warnings(plan: Plan, chapter: str, record: dict) -> list[str]:
    if plan.chapter is None:
        return [f"the reply names no chapter - read as chapter {chapter}'s, against the crop PDF made last"]
    if plan.marks_id is None:
        return ["the reply has no marks id - read against the crop PDF made last"]
    return []


def fix_request_text(chapter: str, errors: list[str], layout: str) -> str:
    whole = ('"chapter", "marks" and every edit' if layout == "long_strip"
             else '"chapter", "marks" and an entry for every page')
    return "\n".join([
        f"# Fix request: chapter {chapter}'s crop reply", "",
        "remanga could not use your reply - these need fixing:", "",
        *[f"- {error}" for error in errors], "",
        f"Fix only these, checked against the pages, and reply with the whole plan again - {whole} - as one "
        f"```json block, nothing before or after it.", ""])
