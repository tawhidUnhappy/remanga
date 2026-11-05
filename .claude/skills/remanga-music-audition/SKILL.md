---
name: remanga-music-audition
description: Choose a project's background music by hearing and measuring candidates the way a chapter mixes them - a stretch of the chapter's real narration over each track at the configured level, in one labelled video, with what an ear would judge measured (sung words, drum-like attacks, energy in the speech band, loudness range). Use when picking, changing or comparing background music, or when asked which track fits a manga.
---

# Picking background music

The music sits `audio.bgm_below_voice_lu` under the voice, measured by its loud parts over the whole
chapter (`remanga/audio/mix.py:music_gain_db`), looped with `bgm_loop_gap_s` between passes. A track
is judged there, under narration - not on its own, where a busy track can sound best.

```bash
PYTHONPATH=. .venv/bin/python .claude/skills/remanga-music-audition/music_audition.py \
    PROJECT CHAPTER OUT_DIR TRACK [TRACK ...] [--seconds 50] [--start 0]
```

It needs a chapter whose narration has been made (its takes), and the GPU free for whisper. Put the
current track first as the baseline. OUT_DIR gets one mp3 per track (narration + music, at the
Volume target), `ALL-in-a-row.mp4` (a card naming each), `scores.json` and `what-they-say.txt`.

## What the numbers say

- **words**: what whisper hears in the track alone (confident words only). A bed with sung words
  competes with the narrator for attention - want 0.
- **onsets/s**: sharp attacks a second. Drums and plucked notes tick across the speech rhythm; a calm
  bed has few.
- **speech band %**: the share of the track's energy between 1 and 4 kHz, where consonants - and so
  understanding - live. Lower masks fewer words at the same level.
- **LRA**: EBU loudness range. The level is set by the loud parts, so a very wide range leaves the
  quiet parts inaudible under the voice.
- **centroid**: the spectral centroid; lower sounds warmer and darker.

Match the mood too, which no number gives: read the story so far and say why a track fits it.

## Copyright

YouTube's Content ID claims recognisable recordings - theme songs, chart songs and their covers or
instrumentals - whatever the level under the voice. Prefer music made for the project (a local
generator; check its licence covers its output) or tracks published as free to use, and keep where
each came from beside it.

## Using the choice

Copy the track into `global/bgm/`, set Background music in the Settings (`audio.bgm_path`), and make
the videos again: the narration takes are reused from the store, so only the mix and the encode are
redone. A long video gets one music bed across its chapters.
