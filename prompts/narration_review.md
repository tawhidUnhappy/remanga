# Fixing a chapter's narration

You wrote the narration for this chapter from `prompts/narration.md`. Someone has since gone through
it panel by panel against the art and flagged the lines that are wrong. Fix exactly those, and leave
everything else exactly as it is.

## What you are given

1. The chapter's current `narration.json` - the reply you gave, pasted into a file. Its `narration`
   section has one entry per panel, and its `memory` section is the story so far.
1. `narration_review.json` - what was flagged:

```json
{
  "chapter": "2.2",
  "round": 1,
  "approved": false,
  "general_note": "several lines invent names the chapter never gives",
  "flagged_count": 2,
  "total_panels": 60,
  "flagged_panels": [
    {
      "panel_id": "2.2_002_01",
      "text_at_flag": "the line as it was when it was flagged",
      "issue": "what is wrong with it, in the reviewer's words",
      "tag": "wrong"
    }
  ]
}
```

1. The chapter's panel PDF, if it is still in the conversation. If fixing a flag needs a panel you
   cannot see, ask for that one panel rather than guessing what is in it.

## How to fix

- **Only the flagged panels change.** An unflagged panel's text comes back exactly as it was, to the
  character. The reviewer read the rest and was happy with it.
- **`issue` is the instruction.** If it says a name is invented, take the name out; if it says a line
  of dialogue is missing, put that line in; if it says the panel is described rather than told, tell
  it. Do not fix anything else you notice in that panel while you are there unless it is part of the
  same mistake.
- **`general_note`, when there is one, applies to the whole chapter** - but it still only licenses
  changes to the flagged panels, plus whatever the note names explicitly.
- **`tag`** is the reviewer's shorthand for the kind of mistake. Take it as a hint, never over
  `issue`.
- Everything in `prompts/narration.md` still holds for every line you touch: reported speech, no
  quotation marks, no `?` or `!` or `...`, no contractions, one calm narrator, every panel told with
  all of its dialogue.
- **Update `memory` if a fix changes it** - a name that was wrong, an event that did not happen the
  way it was told. Otherwise give the memory section back unchanged.

## Reply

Exactly one ```json code block and nothing else, in the same shape as before: `narration` first
(every panel of the chapter, in order, fixed ones and untouched ones alike), `memory` last. It
replaces `narration.json` wholesale, so a panel left out is a panel lost.
