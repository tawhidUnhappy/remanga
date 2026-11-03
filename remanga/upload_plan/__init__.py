"""The upload set from an LLM: three titles and thumbnails (A/B/C, for
YouTube's Test & Compare) and one description, the way the narration and the
crop are made - remanga builds the upload PDF (the images it may use, the
story, the manga's facts), the LLM answers it with JSON (prompts/upload.md),
and remanga writes the project's upload/ templates from the reply, lays out
and renders the thumbnails, and stamps them beside every video.

    facts.py        the manga's titles and credits (from its site), and the story
    candidates.py   the images offered: each chapter's largest panels, colour pages
    handoff.py      the PDF's text page, its record, the reply skeleton
    reply.py        the reply read and checked; the fix request
    framing.py      a thumbnail laid out from the reply: crops, labels, badge
    description.py  the description template from the hook and the facts"""

from remanga.upload_plan.reply import FIX_REQUEST_NAME, REPLY_NAME, UploadPlan, UploadReplyError, read_upload_reply

__all__ = ["FIX_REQUEST_NAME", "REPLY_NAME", "UploadPlan", "UploadReplyError", "read_upload_reply"]
