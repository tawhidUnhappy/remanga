"""The description template (upload/description.txt) put together from an
LLM's hook and hashtags and the facts remanga knows itself: the manga's link,
its titles and its credits - never written by the LLM, which may misremember
them. {chapter} and {timestamps} stay in it, filled for each video when it is
stamped (workflow/upload.py)."""

from __future__ import annotations

FAIR_USE = ("This video is a recap and commentary made for review and entertainment (fair use). All artwork "
            "belongs to its original creators.")
AI_VOICE = "Narration voice: AI text-to-speech."


def description_text(hook: list[str], hashtags: list[str], manga_url: str, found: dict) -> str:
    english = found.get("english_title") or ""
    original = found.get("title") or ""
    name = english or original
    titles = f"{english} ({original})" if english and original and original != english else name
    people = " · ".join(part for part in (
        f"Story: {', '.join(found['story'])}" if found.get("story") else "",
        f"Art: {', '.join(found['art'])}" if found.get("art") else "") if part)
    blocks = [
        *hook,
        "▶ {chapter}",
        "{timestamps}",
        f"📖 Read the manga: {manga_url}" if manga_url else "",
        "\n".join(line for line in (f"Manga: {titles}" if titles else "", people) if line),
        " ".join(hashtags),
        "\n".join([FAIR_USE, AI_VOICE] + ([f"Support the official release of {name}."] if name else [])),
    ]
    return "\n\n".join(block for block in blocks if block) + "\n"
