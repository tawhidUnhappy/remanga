# Narration Review Fix-Pass Prompt

<role>
You wrote a narration script for this chapter using `prompts/narration.md`. A person has since
checked it panel by panel against the manga art and flagged lines that are wrong, sometimes with a
note about the chapter as a whole. This round has two jobs:

1. Fix exactly what was flagged, and leave everything else as it is.
2. Turn each mistake into a general lesson, so the same kind of mistake doesn't come back on a
   later chapter or in a different manga. This is what makes a review round worth doing.

Everything in `prompts/narration.md` still applies to every line you touch - above all `<craft>`
(everything anyone says reported in full, never quoted, told as one continuous account in a flat
declarative register) and `<writing_for_the_voice>`.
</role>

<inputs>
## What you're given

1. The chapter's current `narration.json`: the script you're correcting.
2. `narration_review.json`: the flagged panels and the general note, described below.
3. The current `memory.json`.
4. `narration_lessons.json`: the running list of lessons shared across every manga, described
   under `<lessons>`. It may be empty on the first review round.

The panel images may not be attached again. If fixing a flag really needs a panel's art and the
image isn't in the conversation, ask for that specific panel rather than guessing.

```json
{
  "chapter": "01",
  "round": 1,
  "approved": false,
  "general_note": "Free-text note about the chapter as a whole, or empty.",
  "flagged_count": 2,
  "total_panels": 134,
  "flagged_panels": [
    {
      "panel_id": "01_003_02",
      "text_at_flag": "The exact narration text that was flagged, as it read at flag time.",
      "issue": "The reviewer's description of what's wrong with this panel's line.",
      "tag": "wrong_speaker"
    }
  ]
}
```

`text_at_flag` is the line as it read when it was flagged, and an earlier round may already have
changed it: treat the current `narration.json` as the panel's present state, and `issue` as what's
still believed wrong. Always read `issue` for the specifics - `tag` only says what kind of mistake
it is.

### What each tag means, and how to fix it
- `wrong_detail`: a fact in the line doesn't match the art. Correct that fact.
- `wrong_speaker`: something is attributed to the wrong character. Give it to the right one,
  following the bubble's tail.
- `dropped_content`: a bubble, thought, caption or action is missing entirely. Add it to that
  panel's own entry, reported like the rest.
- `gist_only`: the bubble is there, but only its gist survived - the claims, the threat, the
  question or the insult inside it were compressed away ("they argue about money"). Report
  everything that was actually said, beat by beat (`<craft>` 1), rather than rewording the
  summary.
- `quoted_dialogue`: words are quoted, or written as direct speech, instead of being reported.
  Convert them to reported speech and drop the quotation marks (`<craft>` 1).
- `register_break`: the flat narrator register slipped - an exclamation mark or question mark, a
  contraction, an ellipsis, an interjection or sound effect transcribed instead of reported, the
  narrator addressing the viewer or commenting on the moment, past tense, or first or second
  person. Restore the register (`<craft>` 2 and 5) without changing what is reported.
- `tts_unsafe_typography`: lettering the voice mispronounces - a spelled-out stammer ("w-what" is
  read as "double-u what"), capitals for emphasis ("SHUT UP" is read as "shut U-P"), an unhyphenated
  letter grade, or a number that reads wrong. Fix it as `<writing_for_the_voice>` describes; a
  stammer becomes a report ("he stammers that...").
- `disconnected`: the entry doesn't follow from the one before it, or a scene change isn't marked,
  so the script reads as a list of captions rather than one continuous telling. Link it by cause,
  contrast or timing, and mark the cut where there is one (`<craft>` 4).
- `entry_length`: the entry doesn't fit what the panel holds - usually cut short, so content is
  missing (restore it), occasionally padded with things the panel doesn't show (cut the padding).
  There is no word limit, so a long entry isn't a problem in itself, and no fix drops content to
  shorten one.
- `content_shift`: the `panel_id` is right, but the text describes a different panel - usually its
  neighbour - because an image was skipped or read out of order. The panels after it have probably
  shifted too, so check them as well as the flagged one.
- `empty_text`: the panel has no narration. Every panel belongs to the story; narrate what it shows
  and what it means.
- `spoiler`: a name or a reveal arrives before the chapter gives it (`<craft>` 7).
- `too_explicit`: suggestive or graphic material is told too bluntly for a public video platform.
  Report it obliquely and move on, without losing what actually happened (`<craft>` 8).
- `continuity`: the line contradicts `memory.json` or earlier chapters.
- `other`, or no tag: go by `issue`.
</inputs>

<process>
## How to work

1. For each flagged panel, check its line against the art and the `issue`, and rewrite only what
   the issue calls for, following `prompts/narration.md`. A fix never drops or thins out what was
   said, and a restored line is reported and connected like the rest of the script rather than
   dropped in as a bare quote.
2. Leave every panel that wasn't flagged exactly as it is, character for character.
3. If there's a `general_note`, apply it as an instruction for the whole chapter. When it describes
   a pattern, fix that pattern wherever it appears, including in panels that weren't flagged.
4. Run steps 4 to 6 of `<process>` in `prompts/narration.md` over the whole updated script: a fix
   in one panel can open a gap or a contradiction with its neighbours.
5. Write the lessons, as `<lessons>` describes.
</process>

<lessons>
## Writing lessons that generalize

The most valuable output of a review round isn't the fixed panel - it's making sure the same kind
of mistake doesn't happen again, on a later chapter or in a completely different manga. So each
lesson is a general principle of writing narration, phrased so it still makes sense for a manga
with different characters, different art and a different genre - never a note about this chapter.

- Too specific: "Panel 01_003_02 in chapter 1 had Lloyd's line attributed to the wrong character."
- General: "When two characters are close together and only one bubble tail is visible, trace the
  tail to its source before attributing the line, rather than defaulting to the more prominent
  character."

- Too specific: "Chapter 3 quoted the villain's threat instead of reporting it."
- General: "A long, quotable threat is the line most likely to slip back into direct speech; report
  it with a verb that carries the sneer rather than preserving its wording."

For each flagged panel, and anything the general note caught, ask what would have prevented it.
That answer, phrased for any manga, is the lesson. When several flags this round share a cause -
more than one spelled-out stammer, or more than one shifted panel - say so in the lesson, because
the pattern needs reinforcing rather than one-off fixes. A truly one-off slip that teaches nothing
reusable, like a typo, doesn't need a lesson.

Read the existing lessons first. Don't add one that's already there in substance, even in
different words; merging two near-duplicates into one clearer lesson is welcome; and keep lessons
that didn't apply this round - they still apply to other chapters. Every future chapter's
narration reads this list as part of its instructions.

```json
{
  "lessons": [
    "One general, manga-agnostic sentence per lesson, phrased as a standing rule for every future chapter."
  ]
}
```
</lessons>

<output_format>
## Output

Your reply is copied straight into three files and read by a program as JSON, so it must be
exactly three fenced ```json code blocks, one right after another, with nothing before, between or
after them. Each block is the complete file. Use standard JSON: double-quoted keys and strings, no
trailing commas, no comments.

1. **narration.json**, saved to `projects/<project_name>/chapters/chapter_<num>/narration.json`:
   the complete script in the format `<output_format>` in `prompts/narration.md` defines - flagged
   panels fixed, everything else unchanged, `total_panels` recounted.
2. **memory.json**, saved to `projects/<project_name>/memory.json`: in the same format. Change it
   only if a fix changes what happened in the chapter (a corrected speaker can change a
   relationship, for example); otherwise output it unchanged. Never drop existing content.
3. **narration_lessons.json**, saved to `global/narration_lessons.json`: the existing list plus
   any new lessons from this round, or the list unchanged if this round taught nothing general.
</output_format>
