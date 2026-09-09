"""The settings rows a command offers from inside itself.

Lifted out of the command catalog so the catalog stays a catalog. These are
pointers into definitions that already exist - remanga.settings.sections for
a whole settings area, remanga.settings.assets for one shared file - never
reimplementations, which is what stops a row here from describing a screen
differently than the settings menu does.
"""

from __future__ import annotations

from remanga.commands.spec import SetupAction
from remanga.config.tts import TTS_ENGINE_SPECS
from remanga.settings.assets import ASSET_BY_KEY, asset_relevant, asset_status, edit_asset
from remanga.settings.sections import SECTION_BY_KEY

# --- what each command runs on --------------------------------------------
#
# A command's setup rows are the settings it reads, offered from the command
# itself: you notice the wrong voice or the wrong resolution at the moment you
# go to synthesize or render, not while walking through `setup-config`.
#
# Both builders below take the row's title, its current-value line and its
# editor from the definition that already exists - remanga.settings.sections
# for a whole settings area, remanga.settings.assets for one shared file - so
# a row here can't describe a screen differently from the settings menu, or go
# stale when that screen changes. Nothing is reimplemented; these are pointers.


def section_setup(key: str, detail: str = "") -> SetupAction:
    """A setup row for one settings area (remanga.settings.sections). `detail`
    overrides the section's own only where a command wants to say why *it*
    cares about that setting."""
    section = SECTION_BY_KEY[key]
    return SetupAction(
        section.title, describe=section.describe, run=section.run,
        detail=detail or section.detail,
    )


def asset_setup(key: str, label: str, detail: str) -> SetupAction:
    """A setup row for one shared asset (remanga.settings.assets), taking its
    current-value line, its editor and its "does this engine even use it" test
    from that asset's own spec.

    Per-asset rather than the whole Assets screen on purpose: `mix` cares
    about the BGM and nothing else, and offering it every other shared file
    would be rows of noise around the one that matters."""
    spec = ASSET_BY_KEY[key]
    return SetupAction(
        label,
        describe=lambda config: asset_status(config, spec)[2],
        run=lambda config: edit_asset(config, spec),
        detail=detail,
        relevant=lambda config: asset_relevant(config, spec),
    )


TTS_SETUP: tuple[SetupAction, ...] = (
    section_setup("engine", "which model synthesizes the narration voice - "
                   + ", ".join(spec.display_name for spec in TTS_ENGINE_SPECS)),
    section_setup("voice", "which of the engine's built-in voices reads this chapter - "
                   "a name from its own catalogue, not a clip to clone"),
    section_setup("language", "passed straight through to the engine"),
    section_setup("pacing", "how fast this chapter reads, and the gap held after each panel"),
    section_setup("voicechain", "thickness and presence on the narration itself"),
)

BGM_SETUP: tuple[SetupAction, ...] = (
    asset_setup("bgm", "Background music", "the music bed mixed under the narration"),
    section_setup("levels", "how loud the narration sits over the music, and whether the "
                   "master is loudness-normalized"),
)

VIDEO_SETUP: tuple[SetupAction, ...] = (
    section_setup("resolution", "the frame size every chapter is rendered at"),
    section_setup("background", "what fills the frame around each panel"),
    section_setup("hardware", "GPU encoding when it's available, CPU when it isn't"),
    section_setup("framing", "how each panel sits inside that frame"),
)

# Cropping is where a bad page turns into bad panels, and every pass here is
# normally right and occasionally wrong on a splash page or a spread - so the
# toggles belong next to the command that runs them, not three menus away.
CROP_SETUP: tuple[SetupAction, ...] = (
    section_setup("detection", "which cleanup passes run over each page"),
    section_setup("vision", "what a cropped chapter gets packaged into for an LLM upload"),
)
