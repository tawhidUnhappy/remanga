"""The panels/ vs narration.json cross-check.

Cheap by design - a directory listing and one JSON read, no ffprobe - so
the wizard can run it on every project selection rather than only during an
explicit `verify`."""

from __future__ import annotations

from typing import List, Optional

from remanga.json_io import has_real_json_content, read_json
from remanga.paths import get_chapter_dir


def check_panel_narration_mismatch(project_name: str, chapter_num: str) -> Optional[str]:
    """Fast, cheap cross-check between panels/ and narration.json's entries -
    no ffprobe/media decode, just directory listing + one JSON read, so it's
    safe to run automatically and often (the wizard runs this the moment a
    project is selected, not just via the `verify` command). Catches the
    exact footgun the remanga-ops skill calls out: narration.json's
    panel_id MUST equal the stem of a file in panels/ (render.py globs
    panels/*.png|*.jpg and keys off .stem) - a mismatch here usually means a
    re-crop happened after narration was written (or vice versa), silently
    leaving some panels unnarrated or some narration entries pointing at
    panels that no longer exist. Returns a one-line description if
    something's off, None if narration.json doesn't exist yet or everything
    lines up."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    narration_path = chapter_dir / "narration.json"
    if not has_real_json_content(narration_path):
        return None

    panels_dir = chapter_dir / "panels"
    panel_stems = {p.stem for p in panels_dir.iterdir() if p.is_file()} if panels_dir.exists() else set()

    narration = read_json(narration_path).get("narration", [])
    narration_ids = [e.get("panel_id") for e in narration]

    if len(narration_ids) == len(panel_stems) and set(narration_ids) == panel_stems:
        return None

    missing_panels = [pid for pid in narration_ids if pid not in panel_stems]
    extra_panels = sorted(panel_stems - set(narration_ids))
    parts = [f"{len(narration_ids)} narration entries vs {len(panel_stems)} panel file(s)"]
    if missing_panels:
        parts.append(
            f"{len(missing_panels)} narrated panel_id(s) with no matching panel file: "
            f"{', '.join(missing_panels[:5])}{' ...' if len(missing_panels) > 5 else ''}"
        )
    if extra_panels:
        parts.append(
            f"{len(extra_panels)} panel file(s) with no narration entry: "
            f"{', '.join(extra_panels[:5])}{' ...' if len(extra_panels) > 5 else ''}"
        )
    return "; ".join(parts)


def project_panel_narration_mismatches(project_name: str) -> List[tuple]:
    """Every chapter of this project with a panel/narration mismatch right
    now, as (chapter_num, issue) pairs - see check_panel_narration_mismatch.
    Cheap enough to call on every project selection, not just an explicit
    `verify` run."""
    from remanga.full_recap import discover_chapters, chapter_sort_key

    results = []
    for chapter_num in sorted(discover_chapters(project_name), key=chapter_sort_key):
        issue = check_panel_narration_mismatch(project_name, chapter_num)
        if issue:
            results.append((chapter_num, issue))
    return results


