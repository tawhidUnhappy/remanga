// The categories a flagged panel can be filed under.
//
// They exist for the fix pass rather than for this screen: the LLM reading
// narration_review.json (with prompts/narration_review.md) is told what KIND
// of thing went wrong, which is what turns "this line is off" into a
// correction it can actually make. Every one of them names a rule from
// prompts/narration.md - so a new rule there wants an entry here.

export const TAGS = [
  ["", "No specific category"],
  ["wrong_detail", "Wrong/invented detail (doesn't match the art)"],
  ["wrong_speaker", "Wrong speaker attribution"],
  ["dropped_content", "Dropped bubble/thought/caption/action"],
  ["gist_only", "Only the gist of what was said survived"],
  ["quoted_dialogue", "Quoted/direct speech instead of reported"],
  ["register_break", "Register slipped (?, !, ..., contraction, narrator commentary)"],
  ["tts_unsafe_typography", "Lettering the voice misreads (w-what, SHUT UP, A rank)"],
  ["disconnected", "Doesn't follow on / scene change unmarked"],
  ["content_shift", "Text describes a different panel (images went out of order)"],
  ["empty_text", "Left blank - should have real narration"],
  ["spoiler", "Spoiler / name used too early"],
  ["too_explicit", "Suggestive or graphic material told too bluntly"],
  ["entry_length", "Cut short / padded for what the panel holds"],
  ["continuity", "Contradicts memory.json continuity"],
  ["other", "Other"],
];

export function tagOptionsHtml(selected) {
  return TAGS.map(([value, label]) =>
    `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
}
