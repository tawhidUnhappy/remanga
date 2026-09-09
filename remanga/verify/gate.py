"""The hard stop between "something is inconsistent" and "render it anyway".

remanga already cross-checks panels/ against narration.json
(verify/panels.py) and the wizard shows the result when a project is
selected. That is a NOTICE, and a notice is easy to walk past - it appears
once, several minutes before the step it actually matters to, and the run
that follows produces a finished video with silent panels or missing art in
it. The failure is invisible until someone watches the whole thing.

So the same check is enforced here, at the point of use, by the three stages
that turn panels and narration into output. Placed in the engines rather
than in pipeline.py's step list because full-recap does not go through those
steps: a guard that only covered the wizard's per-chapter path would leave
the whole-project compile - the long, unattended one, where a bad chapter
costs the most - unprotected.

What it refuses to do:

  - narrate a panel_id with no panel image behind it (silence over nothing,
    or a crash at frame-pairing time)
  - leave a cropped panel with no narration entry (a panel that appears in
    the video with no voice over it)

Either direction fails, because either produces a video that is quietly
worse than it looks - which is exactly the class of problem nobody catches
before publishing."""

from __future__ import annotations

from remanga.verify.panels import check_panel_narration_mismatch


class PanelNarrationMismatch(RuntimeError):
    """Raised instead of producing output that would be silently degraded."""


def ensure_panels_match_narration(project_name: str, chapter_num: str, *, stage: str) -> None:
    """Refuses to continue when panels/ and narration.json disagree.

    `stage` names the step being blocked, so the message says what did not
    happen rather than only what is wrong.

    Silent when narration.json does not exist yet: that is a chapter which
    has not reached narration, not a broken one, and the steps that need it
    fail with their own clearer error."""
    issue = check_panel_narration_mismatch(project_name, chapter_num)
    if not issue:
        return

    raise PanelNarrationMismatch(
        f"Chapter {chapter_num}: panels and narration do not match, so {stage} was stopped "
        f"before it could produce a degraded result.\n"
        f"  {issue}\n"
        f"\n"
        f"Every panel image needs a narration entry and every narration entry needs a panel "
        f"image - narration.json's panel_id must equal the panel file's name without its "
        f"extension. A mismatch almost always means panels were re-cropped after narration "
        f"was written, or narration was written against an older crop.\n"
        f"\n"
        f"Fix it by either:\n"
        f"  - re-writing narration for the panels that exist now "
        f"(`remanga create-narration --project {project_name} --chapter {chapter_num}`), or\n"
        f"  - restoring the crop that narration was written for "
        f"(`remanga restart --project {project_name} --chapter {chapter_num}`),\n"
        f"then running this step again. `remanga verify --project {project_name}` lists every "
        f"affected chapter."
    )
