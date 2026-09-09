"""Help strings derived from the registries they describe.

Each of these is built from the real list at import time rather than typed
out, so a command's --help can never end up describing a different set of
steps, keep-files or restart modes than the code actually uses."""

from __future__ import annotations

from remanga.commands.selection import DEFAULT_WIPE_KEEP
from remanga.pipeline import DEFAULT_STEPS, STEP_REGISTRY
from remanga.reset import PROJECT_KEEP, RESTART_MODES

# Every step that exists, and - separately - the ones a project that has
# never chosen actually runs. Not the same list (see Step.default), and a
# --help that conflated them would promise a default order no project has.
STEP_NAMES = ", ".join(step.name for step in STEP_REGISTRY)
DEFAULT_STEP_NAMES = ", ".join(DEFAULT_STEPS)
# The project-root metadata files a whole-project wipe keeps, named from the
# keep-list itself rather than retyped, so --regenerate-all's help can't end
# up describing a different set than reset.wipe_project actually preserves.
PROJECT_KEEP_FILES = ", ".join(name for name in PROJECT_KEEP if name.endswith(".json"))
RESTART_MODE_HELP = ". ".join(f"{mode.name}: {mode.summary}" for mode in RESTART_MODES)
DEFAULT_KEEP_TEXT = ", ".join(sorted(DEFAULT_WIPE_KEEP))
