"""Audio settings: pauses, background music, loudness - see remanga/audio/mix.py."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from remanga.config.base import ConfigModel


class AudioConfig(ConfigModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    # Silence after each panel's narration before the next panel's. Not 0: clips
    # come back trimmed tight to the speech, and butted together the sentences
    # run into each other; a narrator reading aloud takes 300-600ms.
    pause_between_panels_ms: int = Field(350, validation_alias=AliasChoices("pause_between_panels_ms",
                                                                            "pause_between_pages_ms"))
    # The longest pause allowed inside a take, in ms (0 = keep the engine's
    # natural pauses): every longer silence is cut down to it as the take
    # comes back, before it is timed - audio/gaps.py. Changing it remakes
    # the takes.
    max_gap_ms: int = 0
    # Narrate several panels in one generation instead of one each. A panel
    # synthesized alone is a take of its own - Qwen reads it with no idea what
    # came before, so the tone resets every panel, which is audible in a way
    # no amount of trimming the joins can fix. On by default since it proved
    # itself (2026-10-04); the per-panel path is unchanged underneath it.
    batch_narration: bool = True
    # About how long one of those generations should be, capped by the
    # synthesizer's max_take_seconds - five minutes, or for a cloned voice
    # audio/batching.py:CLONE_MAX_TAKE_SECONDS, which is why the default is a
    # minute: a cloned voice measurably drifts away from its reference as a
    # take goes on (see that constant for the numbers), and a minute is where
    # it still measures as the reference. Longer means fewer seams to hear,
    # a voice less like the one asked for, and more audio to make again when
    # one line changes.
    # The default is the whole chapter (999 = ui/screens/settings_sound.py:
    # WHOLE_CHAPTER): Kokoro, the default engine, reads it as ONE take with no
    # joins between takes at all, and every other engine is held to its own
    # max_take_seconds anyway.
    batch_target_minutes: float = 999.0
    # Background music: off until a file is chosen.
    bgm_enabled: bool = False
    bgm_path: str = ""
    # How far the music sits under the narration, in loudness units (LU). Both
    # are measured at mix time and the music's gain is set to match, so every
    # track sits at the same level however loud its file is mastered - a fixed
    # dB gain left one track 6 LU louder than another. 14 keeps the music
    # present enough to carry energy while every word stays clear; 18+ is a
    # quiet bed, under 12 starts to mask consonants on phone speakers.
    bgm_below_voice_lu: float = 14.0
    # The level last typed in as "Custom..." (Settings - Music level), kept so
    # it is offered again next time beside the presets, whichever level is in
    # use. None until one has been typed.
    bgm_custom_lu: float | None = None
    # The voice chain (audio/voice_chain.py), over the narration before the
    # music goes under it. Re-mixes only - nothing is narrated again.
    # Compressor: "off", "gentle", "medium" or "strong" - evens the loud and
    # quiet parts so the voice sounds thick and close to the mic.
    voice_compressor: str = "medium"
    # A low shelf at 150 Hz, in dB (0 = off): the deep radio-narrator chest.
    voice_bass_boost_db: float = 3.0
    # A peaking boost at 4 kHz, in dB (0 = off): the edge that makes a voice
    # cut through - the "powerful" half of a broadcast sound.
    voice_presence_db: float = 0.0
    # "off", "close" or "studio": the voice as a real mic records it - mic
    # EQ and drive, room tone, and for studio a small room around it
    # (audio/microphone.py). TTS with none of that sounds generated.
    voice_microphone: str = "off"
    # "off", "light" or "strong": the narrator's breath on an unprotected
    # mic - pops of air on hard word onsets, quick inhales in the pauses
    # (audio/breath.py).
    voice_breath: str = "off"
    # "off" or "phone": recorded on a phone - hiss that rides with the voice,
    # then a voice codec (audio/phone.py).
    voice_recording: str = "off"
    # Noise made from the voice itself (its own spectral envelope), this many
    # dB under it, 0 = off: felt rather than heard (audio/blend.py).
    voice_blended_noise_db: float = 0.0
    # A peak limiter on the finished mix, so the loudness pass can bring it up
    # without a peak clipping. Off, a mix whose peaks would clip is held
    # quieter than the target instead.
    voice_limiter: bool = True
    # Normalize the finished mix to `loudness_target_lufs` (two-pass, linear -
    # the level changes, the dynamics don't).
    enable_loudnorm: bool = True
    # -14 LUFS is what YouTube normalizes to: a quieter video is not turned up
    # and sounds weaker next to others.
    loudness_target_lufs: float = -14.0
