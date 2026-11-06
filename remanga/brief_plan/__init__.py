"""The brief: a reference typed in words ("isaki, villain, yandere white hair
waifu") becomes, through an LLM, a manga on MangaDex, the chapters to take and a
narrator voice for Drama 3. prompts/brief.md is the contract; reply.py checks
the reply."""

from remanga.brief_plan.reply import (
    BRIEF_REPLY_NAME,
    BriefPlan,
    BriefReplyError,
    Candidate,
    VoicePlan,
    read_brief_reply,
)

__all__ = ["BRIEF_REPLY_NAME", "BriefPlan", "BriefReplyError", "Candidate", "VoicePlan", "read_brief_reply"]
