"""Kokoro-82M's built-in voices, and how good each one is.

Kokoro does not clone: it ships a fixed set of named voices, so "the
narrator's voice" is a name from this list rather than a WAV file on disk.
That is the whole reason the reference-clip asset and its transcript are
gone from the settings screens - there is no clip to point at any more.

The grades are Kokoro's own published ones (its VOICES.md), which report
how much training data each voice had and how well it turned out. They are
listed here because the spread is wide enough to matter: the best voice is
graded A and several are graded D or F, and picking blind is how you end up
narrating a whole chapter in one of the bad ones. The settings picker shows
the grade next to every voice for exactly that reason."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KokoroVoice:
    name: str
    label: str
    grade: str
    accent: str


# American English first (lang_code "a"), then British ("b"), each ordered
# best-graded first so the picker reads top-down as "most to least
# recommended" rather than alphabetically.
KOKORO_VOICES: tuple[KokoroVoice, ...] = (
    KokoroVoice("af_heart", "Heart (female)", "A", "american"),
    KokoroVoice("af_bella", "Bella (female)", "A-", "american"),
    KokoroVoice("af_nicole", "Nicole (female)", "B-", "american"),
    KokoroVoice("am_fenrir", "Fenrir (male)", "C+", "american"),
    KokoroVoice("am_michael", "Michael (male)", "C+", "american"),
    KokoroVoice("am_puck", "Puck (male)", "C+", "american"),
    KokoroVoice("af_aoede", "Aoede (female)", "C+", "american"),
    KokoroVoice("af_kore", "Kore (female)", "C+", "american"),
    KokoroVoice("af_sarah", "Sarah (female)", "C+", "american"),
    KokoroVoice("af_nova", "Nova (female)", "C", "american"),
    KokoroVoice("af_sky", "Sky (female)", "C-", "american"),
    KokoroVoice("af_alloy", "Alloy (female)", "C", "american"),
    KokoroVoice("af_jessica", "Jessica (female)", "D", "american"),
    KokoroVoice("af_river", "River (female)", "D", "american"),
    KokoroVoice("am_echo", "Echo (male)", "D", "american"),
    KokoroVoice("am_eric", "Eric (male)", "D", "american"),
    KokoroVoice("am_liam", "Liam (male)", "D", "american"),
    KokoroVoice("am_onyx", "Onyx (male)", "D", "american"),
    KokoroVoice("am_adam", "Adam (male)", "F+", "american"),
    KokoroVoice("am_santa", "Santa (male)", "D-", "american"),
    KokoroVoice("bf_emma", "Emma (female)", "B-", "british"),
    KokoroVoice("bm_fable", "Fable (male)", "C", "british"),
    KokoroVoice("bm_george", "George (male)", "C", "british"),
    KokoroVoice("bf_isabella", "Isabella (female)", "C", "british"),
    KokoroVoice("bm_lewis", "Lewis (male)", "D+", "british"),
    KokoroVoice("bf_alice", "Alice (female)", "D", "british"),
    KokoroVoice("bm_daniel", "Daniel (male)", "D", "british"),
    KokoroVoice("bf_lily", "Lily (female)", "D", "british"),
)

VOICE_BY_NAME = {v.name: v for v in KOKORO_VOICES}

# Kokoro's highest-graded voice (A). The default narrator for that reason
# alone - nothing else it ships is graded above A-, and the drop to the best
# male voice (am_fenrir, C+) is three whole grades. If you want a male
# narrator, am_fenrir is the one to set; it is a real quality trade, not a
# coin flip, which is why it isn't silently the default.
DEFAULT_VOICE = "af_heart"

# Kokoro takes the accent as a one-character "lang_code" rather than reading
# it off the voice name, and mismatching them produces a voice speaking with
# the wrong accent's phonemes instead of an error. Derived from the voice so
# the two can never disagree - see KokoroConfig.lang_code.
ACCENT_LANG_CODE = {"american": "a", "british": "b"}


def voice_spec(name: str) -> KokoroVoice:
    """The voice named, falling back to the default for anything
    unrecognized - config.json is hand-editable, and a typo there should
    narrate in the default voice rather than crash mid-chapter."""
    return VOICE_BY_NAME.get((name or "").strip(), VOICE_BY_NAME[DEFAULT_VOICE])


def lang_code_for(voice: str) -> str:
    """Kokoro's one-character language/accent code for a voice name."""
    return ACCENT_LANG_CODE.get(voice_spec(voice).accent, "a")
