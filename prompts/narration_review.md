# Narration Fix-Pass Prompt (Human Review Round)

## Role & Mission
You already wrote a narration script for this chapter using `prompts/narration.md`. A human has
now reviewed that script panel-by-panel against the actual manga art and flagged specific lines
that are wrong, plus optionally an overall note about the chapter. Your job this round is
narrower than the original scriptwriting pass: **fix exactly what was flagged, leave everything
else untouched, and record what kind of mistake this was so it generalizes to future chapters and
other manga** — not just this one.

You'll be given, alongside this prompt:
1. This chapter's current `narration.json` (the script you're correcting).
2. `narration_review.json` — the human's flagged panels and general note (schema below).
3. The current `memory.json` — story continuity for this project, unchanged by this prompt except
   as `prompts/narration.md` already directs.
4. `narration_lessons.json` — a running, cross-manga log of generalized mistakes and how to avoid
   them (schema below). May be empty/placeholder on the very first review round ever.

The original panel images/PDF/zip for this chapter are **not** necessarily re-attached this round
— you already analyzed them once. If a flagged issue genuinely requires re-examining a panel's art
and the images aren't in this conversation, say so and ask for that specific panel image rather
than guessing at a fix.

---

## Input Schema: `narration_review.json`
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
      "issue": "The human's description of what's wrong with this panel's line.",
      "tag": "wrong_speaker"
    }
  ]
}
```
`tag` is one of: `wrong_detail`, `wrong_speaker`, `dropped_content`, `flattened_dialogue`,
`tts_unsafe_typography`, `empty_text`, `spoiler`, `punctuation`, `word_budget`, `continuity`,
`other`, or empty.
`flattened_dialogue` means a panel's line was paraphrased into third-person summary when the
character's actual words should have been quoted instead (Rule 5 of `prompts/narration.md`) —
fix it by rewriting the line to work the real quote in, not by rephrasing the paraphrase.
`tts_unsafe_typography` means a `text` value still has manga lettering's stutter-hyphen or
ellipsis typography in it ("w-what", "I...was") — **never valid** per Rule 5 of
`prompts/narration.md`; fix it by normalizing that one line (keep the stammer/trailing-off as
a narration-frame verb, e.g. "he stammers", per that rule's examples) without touching
anything else about the wording. If more than one or two panels this chapter got flagged with
this tag, say so explicitly in the generalized lesson (Block 3 below) — it means the pattern
needs reinforcing, not just this line fixing.
`empty_text` means a panel was left with `"text": ""` — **never valid** per Rule 4 of
`prompts/narration.md`; every panel that reaches this pipeline already passed human
panel-relevance filtering during marking, so describe what the panel actually shows instead
of leaving it blank, even for a silent/reaction beat. Treat `tag` as a hint about *what kind*
of mistake
this is — useful for writing a good generalized lesson (see Block 3 below) — not as the whole
instruction; always read `issue` for the actual specifics.

`text_at_flag` may not exactly match this panel's current text in `narration.json` if a prior
round already partially addressed it — trust the current `narration.json` as the panel's present
state, and `issue`/`tag` as what's still believed wrong with it.

---

## Process
1. **Fix only flagged panels.** For each entry in `flagged_panels`, re-examine that panel against
   Rule 2 (objective visual grounding), Rule 3 (prosody/punctuation), Rule 4 (word budget), Rule 5
   (show-and-synthesize), Rule 7 (complete dialogue/action coverage), and whichever Golden Rule the
   `issue` text and `tag` point to in `prompts/narration.md`, and rewrite that panel's `text` to
   actually fix the described problem. Do not rewrite a flagged panel's line more than the issue
   calls for — fix the specific thing, don't rephrase what wasn't flagged as wrong.
2. **Leave every unflagged panel exactly as it was.** This is not a chance to re-polish the whole
   script — a panel not present in `flagged_panels` is left character-for-character unchanged.
3. **Apply `general_note`, if present**, as a chapter-wide instruction (e.g. "punctuation is
   overused in the back half") — it may mean touching panels beyond `flagged_panels` if the note
   genuinely describes a pattern across the chapter; if so, note in your reply which additional
   panels you touched and why.
4. **Re-run Rule 9's full-script verification pass** (from `prompts/narration.md`) over the whole
   updated script, not just the fixed panels — a fix to one panel can create a new gap or
   contradiction with its neighbors.
5. **Write the generalized lesson(s)** for `narration_lessons.json` — see Block 3 below. This is
   the step most likely to be skipped under time pressure; it is not optional.

---

## Block 3 Is the Point of This Prompt: Generalize, Don't Log the Incident
The single most important output of a review round isn't the fixed panel — it's making sure the
**same class of mistake** doesn't recur on a later chapter, or a completely different manga. That
means every lesson you write must be phrased as a **general narration-writing principle**, never
as a note about this specific chapter, character, or series.

- ❌ **Too specific (do not write this):** *"Panel 01_003_02 in chapter 1 had Lloyd's line
  attributed to the wrong character."*
- ✅ **Correctly generalized:** *"When two characters are close together in a panel and only one
  speech bubble tail is visible, trace the tail to its source before attributing the line — don't
  default to the more prominent/foregrounded character."*

- ❌ **Too specific:** *"Chapter 3's ellipses were overused on the fight scene panels."*
- ✅ **Correctly generalized:** *"A run of consecutive action panels tends to accumulate `...` even
  when only the first one or two panels are actually hesitant — check each panel's ellipsis against
  Rule 3 individually rather than carrying the previous panel's punctuation tone forward."*

For each flagged panel (and anything `general_note` caught), ask: *"What would have prevented this,
phrased so it still makes sense on a manga with different characters, different art, a different
genre?"* That sentence is the lesson. If an issue is truly one-off and doesn't generalize (e.g. a
factual typo), it's fine to skip logging it — don't force a lesson that doesn't teach anything
reusable.

**Read the existing `narration_lessons.json` first** and don't duplicate a lesson that's already
there in substance, even if this round's wording would differ slightly — if this mistake is a
specific instance of an existing lesson, skip adding a near-duplicate. Only append lessons that are
genuinely new generalizations. Keep the list itself reasonably tidy — if two existing lessons could
be merged into one clearer principle, merging them is welcome, but never delete a lesson just
because it wasn't relevant this round.

### Schema: `narration_lessons.json`
```json
{
  "lessons": [
    "One generalized, manga-agnostic sentence per lesson, phrased as a standing rule to check against on every future chapter."
  ]
}
```
Plain array of strings, nothing else. Append new entries to the end; never renumber, remove, or
rewrite an existing entry except to merge near-duplicates as described above.

**This file is consulted going forward on every chapter this pipeline narrates, for any project** —
`prompts/narration.md` treats it as a standing checklist alongside the Golden Rules. Writing a
sharp, genuinely general lesson here is the mechanism that makes review rounds worth doing at all;
a lesson too specific to reuse is functionally the same as not writing one.

---

## Output Schema Requirements — Read Carefully, This Gets Parsed by Code
Exactly the same hard requirement as `prompts/narration.md`: **your entire response must be
exactly three fenced ` ```json ` code blocks, back to back, and nothing else** — no greeting, no
commentary, no text between blocks, nothing after the third block. Standard JSON only:
double-quoted keys/strings, no trailing commas, no comments.

### Block 1: `narration.json`
Save to: `projects/<project_name>/chapters/chapter_<num>/narration.json`
Same schema as `prompts/narration.md` Section 4, Block 1 (`chapter`, `total_panels`, `narration[]`
of `{panel_id, text}`) — the **complete** script, fixed panels updated, everything else unchanged,
`total_panels` recounted to match `narration.length`.

### Block 2: `memory.json`
Save to: `projects/<project_name>/memory.json`
Same schema as `prompts/narration.md` Section 4, Block 2. Update it only if a flagged fix actually
changes what happened in the chapter (e.g. a corrected speaker changes a relationship fact) —
otherwise carry it forward unchanged, same rule as any other pass: never discard existing content.

### Block 3: `narration_lessons.json`
Save to: `global/narration_lessons.json`
The schema above — the existing list plus any new, genuinely generalized lesson(s) from this round.
If this round produced no lesson worth generalizing, output the list **unchanged** (don't pad it
with something trivial just to have written something).
