"""The crop plan: the JSON that says how a chapter's pages are cut into
panels - written by an LLM from the crop PDF (prompts/crop.md, pasted into
chapters/chapter_N/crop_reply.txt), or by Claude after looking at the pages
(.claude/skills/remanga-long-recap/crop.py). One format, read and applied
here for both.

The machine proposes first - MAGI v3 on printed pages, the gutter detector on
a long strip - and the plan corrects it: a page's panels by the numbers of the
boxes drawn on it (3, "2+3"), the labels of the figures and bubbles found
crossing them (F1, B1) or a measured box where nothing drawn fits, a strip's
cuts by their rows. LLMs read pages well and measure them badly (frames taken
from the page margin, panels back as thin strips, two panels as one), so
reusing what the machine drew is the point.

    grammar.py    reading a plan (JSON; the older plain lines too)
    pages.py      page entries applied to crops.json
    strip.py      a long strip's panels now, and edits applied to them
    found.py      what the detector saw besides the panels: figures, bubbles
    breakouts.py  the figures and bubbles that cross a box, as hints
    sheets.py     the pages and the strip drawn with their boxes, hints, grid and ruler
    handoff.py    the crop PDF's text page and its record of what it draws
    reply.py      a pasted reply checked against that record; the fix request
    report.py     cut panels that do not match their marks"""

from remanga.crop_plan.grammar import PageLine, Panel, Plan, StripEdit, plan_text, read_plan, read_reply
from remanga.crop_plan.pages import PagesOutcome, apply_page_lines, page_boxes, page_record
from remanga.crop_plan.reply import FIX_REQUEST_NAME, REPLY_NAME, CropReplyError
from remanga.crop_plan.report import cut_report
from remanga.crop_plan.strip import StripNow, StripOutcome, apply_edits, cuts_of, strip_now

__all__ = [
    "FIX_REQUEST_NAME",
    "REPLY_NAME",
    "CropReplyError",
    "PageLine",
    "PagesOutcome",
    "Panel",
    "Plan",
    "StripEdit",
    "StripNow",
    "StripOutcome",
    "apply_edits",
    "apply_page_lines",
    "cut_report",
    "cuts_of",
    "page_boxes",
    "page_record",
    "plan_text",
    "read_plan",
    "read_reply",
    "strip_now",
]
