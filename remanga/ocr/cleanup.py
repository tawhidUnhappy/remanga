"""Turns a document-OCR model's output into plain panel text.

These models are trained to parse document *pages*, and a manga panel is not
one. Two habits come from that, and neither is fixable by prompting - measured
on real panels with LightOnOCR-2, an explicit "plain text only, no LaTeX, no
description" instruction changed nothing about the LaTeX and made the
descriptions worse. The examples below are its output; DeepSeek-OCR-2 is a
document model too, so the same shapes are expected and the same stripping
applies:

  - **LaTeX.** Sound effects come back wrapped as maths, because on a document
    page that is usually what a small isolated glyph cluster is:
    `$\\frac{2}{7} \\text{Gulp...}$` for a bubble that just says "Gulp...".
  - **Image descriptions.** A panel with little or no text gets described
    instead of transcribed - "*Note: The image contains a black-and-white line
    drawing of a person..." - sometimes with a `![image](image_1.png)` tag.

Both are noise in the Narration Writer's text box, and both are recognizable
enough to strip without touching real dialogue. This is deliberately
conservative: anything it cannot confidently identify as scaffolding is left
alone, because a wrong strip silently loses words a human then has to notice
are missing."""

from __future__ import annotations

import re

# ![alt](path) - markdown image tags the model emits for the artwork itself.
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

# A descriptive aside about the artwork rather than text read off it. Anchored
# to the "Note:" opener the model actually uses, and required to mention the
# image, so a bubble that genuinely starts with "Note:" survives.
_DESCRIPTION_RE = re.compile(
    r"^\s*\*?\s*Note:\s*The image\b.*?(?:\n\s*\n|\Z)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

# \frac{...}{...} - never meaningful for a speech bubble; the model uses it to
# render stacked or stylized lettering.
_FRAC_RE = re.compile(r"\\d?frac\s*\{[^{}]*\}\s*\{[^{}]*\}")
# \text{...}, \mathrm{...} etc - the wrapper is scaffolding, the content is the
# actual word, so this unwraps rather than deletes.
_TEXT_WRAP_RE = re.compile(r"\\(?:text|mathrm|mathit|mathbf|textbf|textit)\s*\{([^{}]*)\}")
# Any remaining single LaTeX command.
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\s*")
_BLANK_RUN_RE = re.compile(r"\n{3,}")

# DeepSeek-OCR-2 answers a picture-only panel with a sentence ABOUT the panel,
# in Chinese, rather than with nothing: "（图中无可辨识的文字）" - "(no
# recognizable text in the image)". It is a status message, not a reading, and
# left alone it lands in the Narration Writer's text box as if the panel said
# it. Matched narrowly - fullwidth parentheses wrapping a CJK phrase that
# contains 无 ("no/none") or 未 ("not yet") - so a panel that genuinely shows
# a Japanese line survives.
_CJK_NO_TEXT_RE = re.compile(r"^\s*[（(][^)）]*[无未][^)）]*[)）]\s*$", re.MULTILINE)


def _strip_latex(text: str) -> str:
    """Unwraps `$...$` / `$$...$$` spans, keeping whatever words were inside."""

    def unwrap(match: re.Match) -> str:
        inner = match.group(1)
        inner = _FRAC_RE.sub(" ", inner)
        inner = _TEXT_WRAP_RE.sub(r"\1", inner)
        inner = _LATEX_CMD_RE.sub(" ", inner)
        inner = inner.replace("{", " ").replace("}", " ")
        return re.sub(r"\s+", " ", inner).strip()

    text = re.sub(r"\$\$(.+?)\$\$", unwrap, text, flags=re.DOTALL)
    return re.sub(r"\$(.+?)\$", unwrap, text, flags=re.DOTALL)


def clean_ocr_text(text: str) -> str:
    """Panel text as a human would have typed it, from one raw OCR response."""
    if not text:
        return ""

    text = _CJK_NO_TEXT_RE.sub("", text)
    text = _MD_IMAGE_RE.sub("", text)
    text = _DESCRIPTION_RE.sub("", text)
    text = _strip_latex(text)

    # Per line so the blank-line structure between bubbles survives.
    #
    # Note what is NOT done here: punctuation-only lines are kept. It is
    # tempting to drop them as stripping residue, but "..." is a real manga
    # bubble - a silent beat - and unwrapping already empties the lines that
    # held nothing but LaTeX, so the rule would cost real text to solve a
    # problem that no longer exists.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return _BLANK_RUN_RE.sub("\n\n", "\n".join(lines)).strip()
