---
name: remanga-voice-design
description: Design a new narrator voice for Fish Audio Drama 3 - candidate voices described in words (each with a seed), every one read the way a chapter is read, measured (pitch, how much it moves, pace, pauses, words heard, hums), ranked against target ranges and played in one labelled video; the winner is then added to DRAMA_VOICES. Use when asked for a new, different or better narrator voice, or to compare described voices.
---

# Designing a Drama 3 narrator

Drama 3 has no named voices: a cue in brackets describes one (`[rich, warm young male narrator, smooth
with clear diction, gentle storytelling]`), and the seed picks which speaker of that description you
get. remanga reads every take from a voice file made once from cue + seed
(`remanga/plugins/drama3/scripts/drama3_worker.py`), so the voice stays the same from page to page. A
voice is a `DramaVoice(name, label, cue, use)` in `remanga/plugins/drama3/config.py`; the cue must stay
word for word once chosen - with the seed, it is what the voice file was made from.

## Audition

```bash
PYTHONPATH=. .venv/bin/python .claude/skills/remanga-voice-design/audition.py CANDIDATES.json TEXT.txt OUT_DIR
```

- `CANDIDATES.json`: `[{"name", "cue", "seed", "what"}, ...]`, in the order to play them. A name already
  in `DRAMA_VOICES` reads in that voice - put the current narrator first as the baseline. Two or three
  seeds of the best descriptions are worth a slot each: one description gives quite different speakers.
- `TEXT.txt`: about 100 words of narration in the project's own style - reported speech, names, a
  question, an exclamation and a trailing-off - so pauses and pitch movement have something to show.
- Writes `OUT_DIR/N-name-seedS.mp3` (-14 LUFS by one measured gain), `ALL-in-a-row.mp4` (one card per
  voice naming it, with its numbers), `what-they-say.txt` (ranked) and `scores.json`; takes and word
  timings stay in `OUT_DIR/_work`, so a second run only measures again.
- It loads Drama 3 once for every candidate (each new voice first reads a reference line to make its
  voice file), then faster-whisper once. About 1.5 minutes a candidate on a 12 GB card. It needs the
  GPU to itself: run it when no render or MAGI run is going. `config.json` is read, never saved.

## Reading the numbers

- **pitch_hz** (median F0) and **movement_st** (5th-95th percentile span, semitones): a narrator that
  never moves sounds flat; one that swings far sounds like it is acting.
- **syllables_per_s** over the reading, pauses included: the pace a listener feels.
- **pause_ms**: the median of the gaps of 250 ms or more between words. A voice that only ever pauses
  ~300 ms sounds rushed beside one whose pauses vary from 0.3 to 1 s.
- **heard_pct**: how much of the script whisper heard, in order. Names the model has never seen are
  misheard by every voice alike (an invented name comes back spelled another way), so compare
  candidates with each other; a voice that drops or adds words is the real failure.
- **hums**: voice where whisper heard no word (`remanga/audio/hums.py`).
- **distance**: how far outside the target ranges, each range's width counting 1; missing words and
  hums count extra. Defaults (`TARGETS` in audition.py): 95-118 Hz, 7.8-12.5 semitones, 4.35-5.06
  syllables a second, 465-715 ms pauses - a calm recap narrator measured on recap channels. Pass
  other targets as a JSON object in the 4th argument.

The distance does not see how much the pauses vary - a voice whose every pause is ~300 ms ranks
well yet sounds rushed beside one that pauses 0.3 to 1 s. Read `longest_pause_ms` and the gaps in
`_work/*.words.json` for the top few. The numbers rank; a person listening decides: present the
labelled video, not just the table.

## Using the winner

1. Add it to `DRAMA_VOICES` with its cue word for word and a comment saying how it was chosen.
2. Set `tts.drama3.voice` (and `seed`) in the Settings - or `config.json` - for the projects that use it.
3. Check it over a whole chapter, not just the sample: after the first render, the per-take median
   pitch should stay within a few Hz (a voice file holds it; the model's own voice drifts from take to
   take), and every take should align (verify.py).
