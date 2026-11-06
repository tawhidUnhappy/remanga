"""The brief - starting a whole job from a few words. `remanga brief "isaki,
villain, yandere white hair waifu"` writes one prompt file (prompts/brief.md
plus the reference and the voices Drama 3 already has) to give an LLM; its JSON
reply, saved as global/brief/brief_reply.txt, is checked here against MangaDex
itself - the manga exists, it has those chapters - and then becomes a new
Drama 3 narrator voice (saved under global/voices, made the active one), a
project for the manga, and its chapters downloaded."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from remanga import sources
from remanga.brief_plan import BRIEF_REPLY_NAME, BriefPlan, BriefReplyError, Candidate, read_brief_reply
from remanga.brief_plan.reply import FIX_REQUEST_NAME, fix_request_text
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.json_io import has_real_json_content, write_json
from remanga.paths import PROMPTS_DIR, get_project_dir
from remanga.paths.roots import GLOBAL_DIR
from remanga.plugins.drama3.config import (
    DRAMA_VOICES,
    DramaVoice,
    all_voices,
    custom_voices,
    save_custom_voice,
)
from remanga.workflow.chapters import select_chapters
from remanga.workflow.download import download
from remanga.workflow.projects import create_project

PROMPT_PATH = PROMPTS_DIR / "brief.md"


def brief_dir() -> Path:
    p = GLOBAL_DIR / "brief"
    p.mkdir(parents=True, exist_ok=True)
    return p


def brief_reply_path() -> Path:
    return brief_dir() / BRIEF_REPLY_NAME


def make_brief_prompt(reference: str) -> Path:
    """global/brief/brief_prompt.md: the instructions, the reference, and the
    narrator voices that exist (names and cues - so the new one is different
    and in the same style)."""
    reference = " ".join(reference.split())
    if not reference:
        raise ValueError('Type what you are after, e.g. remanga brief "isaki, villain, yandere white hair waifu".')
    voices = "\n".join(f"- `{v.name}` - {v.cue or '(no description)'}" for v in all_voices() if v.cue)
    text = (PROMPT_PATH.read_text(encoding="utf-8").rstrip()
            + f"\n\n## Voices that already exist\n\n{voices}\n\n## The reference\n\n{reference}\n")
    out = brief_dir() / "brief_prompt.md"
    out.write_text(text, encoding="utf-8")
    brief_reply_path().touch()
    return out


@dataclass
class Verified:
    candidate: Candidate
    manga_id: str
    english_title: str
    chapters: list[str]                     # the chapters to download, as MangaDex spells them
    notes: list[str] = field(default_factory=list)


def _verify(candidate: Candidate, plan: BriefPlan, config: RemangaConfig) -> Verified:
    """Ask MangaDex itself. Raises ValueError saying why this candidate cannot be used."""
    client = sources.client(sources.source_for(candidate.manga_id), config)
    try:
        info = client.get_manga_info(client.parse_manga_id(candidate.manga_id))
    except Exception as error:
        raise ValueError(f"MangaDex has no manga with id {candidate.manga_id} ({error})") from error
    shown = info["english_title"] or info["title"]
    notes = []
    named = [t for t in (info["english_title"], info["title"]) if t]
    if not any(difflib.SequenceMatcher(None, candidate.title.casefold(), t.casefold()).ratio() >= 0.6
               or candidate.title.casefold() in t.casefold() or t.casefold() in candidate.title.casefold()
               for t in named):
        notes.append(f'the reply called it "{candidate.title}" but that id is "{shown}" - check it is the one '
                     "you meant")
    resolver = client.resolver
    listed = resolver.latest_versions(resolver.list_chapters(client.parse_manga_id(candidate.manga_id)))
    available = [c for c in dict.fromkeys(str(ch.get("attributes", {}).get("chapter") or "") for ch in listed) if c]
    if not available:
        raise ValueError(f'"{shown}" has no chapters in the languages remanga downloads')
    chosen = select_chapters(f"{plan.first}-{plan.last}", available)
    chosen = [c for c in chosen if c in available]
    if not chosen:
        raise ValueError(f'"{shown}" has no chapter between {plan.first} and {plan.last} '
                         f"(it has {min(available, key=float)}-{max(available, key=float)})")
    if plan.first not in available:
        notes.append(f"chapter {plan.first} is not listed; the range starts at chapter {chosen[0]}")
    if plan.last not in available:
        notes.append(f"chapter {plan.last} is not listed; the range ends at chapter {chosen[-1]}")
    return Verified(candidate, client.parse_manga_id(candidate.manga_id), shown, chosen, notes)


@dataclass
class BriefResult:
    project: str
    manga: str
    chapters: list[str]
    voice: DramaVoice
    seed: int
    previous_voice: str
    previous_seed: int
    downloaded: bool
    notes: list[str]
    skipped: list[str]


def apply_brief(raw: str, config: RemangaConfig, *, download_chapters: bool = True) -> BriefResult:
    """The pasted reply, checked, then used. Nothing changes unless a manga on
    MangaDex fits; a reply with mistakes gets a fix request to paste back."""
    fix = brief_dir() / FIX_REQUEST_NAME

    def refuse(message: str, errors: list[str]) -> None:
        fix.write_text(fix_request_text(errors), encoding="utf-8")
        raise BriefReplyError(f"{message}\n" + "\n".join(f"  - {e}" for e in errors)
                              + f"\nPaste {fix} back to the same chat.", errors)

    try:
        plan = read_brief_reply(raw, taken_names={v.name for v in DRAMA_VOICES})
    except BriefReplyError as error:
        refuse(str(error), error.errors)
    saved = {v.name: v for v in custom_voices()}
    old = saved.get(plan.voice.name)
    if old and old.cue != plan.voice.cue:
        refuse("The voice name is taken.", [f'voice.name "{plan.voice.name}" is a voice you already designed, with '
                                            "another description - give this one a new name (its voice file is kept "
                                            "by name, so the name must keep its description)"])

    skipped, verified = [], None
    for candidate in plan.candidates:
        try:
            verified = _verify(candidate, plan, config)
            break
        except ValueError as error:
            skipped.append(f"{candidate.title}: {error}")
            console.print(f"[yellow]✗ {_esc(candidate.title)}:[/] {_esc(str(error))}")
    if verified is None:
        refuse("None of the manga in the reply could be used.", skipped
               + ["give MangaDex ids you have seen on mangadex.org itself, with chapters that exist"])

    # Checked - now change things.
    voice = DramaVoice(plan.voice.name, plan.voice.label, plan.voice.cue, plan.voice.use)
    save_custom_voice(voice, plan.voice.seed, plan.voice.why)
    drama = config.tts.drama3
    previous = (drama.voice, drama.seed)
    config.tts.engine = "drama3"
    drama.voice, drama.seed = voice.name, plan.voice.seed
    config.save()

    project = create_project(f"https://mangadex.org/title/{verified.manga_id}", config)
    write_json(get_project_dir(project) / "brief.json", {
        "manga": verified.english_title, "manga_id": verified.manga_id, "why": verified.candidate.why,
        "chapters": verified.chapters, "voice": {"name": voice.name, "cue": voice.cue, "seed": plan.voice.seed,
                                                 "why": plan.voice.why}, "skipped": skipped})
    if download_chapters:
        download(project, verified.chapters, config)
    return BriefResult(project, verified.english_title, verified.chapters, voice, plan.voice.seed, *previous,
                       download_chapters, [*plan.warnings, *verified.notes], skipped)


def print_brief_result(result: BriefResult) -> None:
    c = result.chapters
    console.print(f"\n[bold green]✓ {_esc(result.manga)}[/] -> project [bold]{_esc(result.project)}[/], "
                  f"chapters {_esc(c[0])}-{_esc(c[-1])} ({len(c)})"
                  + ("" if result.downloaded else " [yellow](not downloaded - run: ./run.sh download -p "
                     f"{_esc(result.project)} -c {_esc(c[0])}-{_esc(c[-1])})[/]"))
    console.print(f"[bold green]✓ Narrator[/] {_esc(result.voice.label)} [dim]({result.voice.name}, seed "
                  f"{result.seed})[/] - now the Drama 3 voice for every project (was {_esc(result.previous_voice)}, "
                  f"seed {result.previous_seed}). [dim]{_esc(result.voice.cue)}[/]")
    for note in result.notes:
        console.print(f"[yellow]· {_esc(note)}[/]")
    console.print("[dim]Listen to it first with: ./run.sh voices[/]")


def read_reply_text(path: str | None) -> str:
    target = Path(path) if path else brief_reply_path()
    if not target.exists() or (not path and not has_real_json_content(target)):
        raise FileNotFoundError(f"No brief reply yet - paste the LLM's reply into {target}")
    return target.read_text(encoding="utf-8")
