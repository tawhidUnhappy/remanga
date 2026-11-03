"""A chapter's versions: every video made of it, kept, with what made it.

`versions/chapter_<N>.json` in the project lists them - when, what it was
made with (engine, voice, music...), and the store objects (store/objects.py)
it is made of: one take and one word timing per batch, the chapter's
audio_timing.json, and the finished video. One of them is current: the one
in the chapter's own folders (audio/, subtitles/, video/), which are only
ever a view of the store, rebuilt from it.

What is kept is what is slow to make (user's choice, 2026-10-25: "keep
expensive, drop cheap"): every version's takes, word timings and finished
video. The mixed master (~180 MB, ~30 s to make) is kept for the current
version only, and made again when an older one is made current.

Also here: TakeCache, which narration asks before it synthesizes a take
(audio/takes.py) and gives every checked take to afterwards; and the video's
key, which render asks before it renders (workflow/video.py)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from remanga.json_io import read_json_or, write_json
from remanga.paths import (
    get_audio_dir,
    get_audio_timing_path,
    get_final_video_path,
    get_panels_dir,
    get_project_dir,
    get_subtitles_dir,
)
from remanga.store.objects import Store, file_sha256, link_or_copy, recipe_key

# Bumped when how a kind is made changes, so an object made the old way is
# not taken for the new one.
TAKE_VERSION = 1
WORDS_VERSION = 1
VIDEO_VERSION = 1


def take_key(source_sha256: str, sample_rate: int, fresh: str | None = None) -> str:
    """A take: its text and the voice reading it (audio/takes.py:source_key -
    engine, voice, seed... all of narration_identity) at this sample rate.
    `fresh`: the id of a run made fresh on purpose (workflow/video.py:
    make_video), whose takes are kept as their own, beside any made before."""
    recipe = {"source": source_sha256, "sample_rate": sample_rate, "v": TAKE_VERSION}
    if fresh:
        recipe["fresh"] = fresh
    return recipe_key("take", recipe)


def words_key(take: str, subtitles_config) -> str:
    """A take's word timings: the take and the whisper that read them."""
    return recipe_key("words", {"take": take, "model": subtitles_config.hf_repo_id,
                                "language": subtitles_config.language, "v": WORDS_VERSION})


class TakeCache:
    """The store, as narration sees it: a take asked for again - same text,
    same voice - is put back with its word timings instead of synthesized and
    transcribed; every take that passed its checks is kept."""

    def __init__(self, project: str, chapter: str, audio_config, subtitles_config,
                 fresh: str | None = None) -> None:
        self.store = Store(project)
        # A fresh run reuses nothing, and keeps what it makes as its own.
        self.fresh = fresh
        self.audio_dir = get_audio_dir(project, chapter)
        self.subs_dir = get_subtitles_dir(project, chapter)
        self.sample_rate = audio_config.sample_rate
        self.subtitles_config = subtitles_config
        self.from_store: set[str] = set()

    def has(self, source_sha256: str) -> bool:
        """Whether this exact take, with its word timings, is in the store."""
        if self.fresh:
            return False
        take = take_key(source_sha256, self.sample_rate)
        return bool(self.store.find("take", take) and self.store.find("words", words_key(take, self.subtitles_config)))

    def restore(self, name: str, source_sha256: str) -> bool:
        """Batch `name`'s take and word timings back from the store, if this
        exact take was made before. Both or neither."""
        if self.fresh:
            return False
        take = take_key(source_sha256, self.sample_rate)
        words = words_key(take, self.subtitles_config)
        if not (self.store.find("take", take) and self.store.find("words", words)):
            return False
        if not (self.store.place("take", take, "take.wav", self.audio_dir / f"{name}.wav")
                and self.store.place("words", words, "words.json", self.subs_dir / f"{name}.json")):
            return False   # damaged: set aside, made again
        self.from_store.add(name)
        return True

    def keep(self, name: str, source_sha256: str, about: dict[str, Any]) -> None:
        """Batch `name`'s take and word timings, as they stand after every
        check, into the store."""
        take = take_key(source_sha256, self.sample_rate, self.fresh)
        self.store.put("take", take, {"take.wav": self.audio_dir / f"{name}.wav"},
                       {"source": source_sha256, "sample_rate": self.sample_rate}, about)
        self.store.put("words", words_key(take, self.subtitles_config),
                       {"words.json": self.subs_dir / f"{name}.json"}, {"take": take}, about)


def video_recipe(project: str, chapter: str, config) -> dict[str, Any]:
    """Everything a chapter's finished video depends on: the narration (its
    audio_timing.json, which names every take by text and voice), the music
    file and the sound settings, the video settings, the panels, the intro."""
    from remanga.audio.master import BED_VERSION
    from remanga.audio.mix import MUSIC_MEASURE
    from remanga.video.intro import intro_identity

    audio = config.audio
    bgm = Path(audio.bgm_path).expanduser() if audio.bgm_enabled and audio.bgm_path else None
    bgm_id = None
    if bgm and bgm.is_file():
        stat = bgm.stat()
        bgm_id = {"name": bgm.name, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    panels_dir = get_panels_dir(project, chapter, create=False)
    panels = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                    for p in panels_dir.glob("*") if p.is_file()) if panels_dir.is_dir() else []
    timing = get_audio_timing_path(project, chapter, create=False)
    return {
        "timing": file_sha256(timing) if timing.is_file() else None,
        "bgm": bgm_id,
        "sound": {"volume_lufs": audio.volume_lufs, "below_voice_lu": audio.bgm_below_voice_lu,
                  "loop_gap_s": audio.bgm_loop_gap_s,
                  "sample_rate": audio.sample_rate, "music_measure": MUSIC_MEASURE, "bed": BED_VERSION},
        "video": config.video.model_dump(),
        "panels": panels,
        "intro": intro_identity(config.video),
        "v": VIDEO_VERSION,
    }


def video_key(project: str, chapter: str, config) -> str:
    return recipe_key("video", video_recipe(project, chapter, config))


# --- the versions themselves -----------------------------------------------

def _versions_path(project: str, chapter: str) -> Path:
    return get_project_dir(project) / "versions" / f"chapter_{chapter}.json"


def load(project: str, chapter: str) -> dict[str, Any]:
    return read_json_or(_versions_path(project, chapter), None) or {"current": None, "versions": []}


def _save(project: str, chapter: str, data: dict[str, Any]) -> None:
    write_json(_versions_path(project, chapter), data)


@dataclass
class Version:
    id: int
    made: str
    label: str
    current: bool
    size: int
    takes: int
    objects: list[tuple[str, str]]


def _voice_of(identity: dict[str, Any] | None, config) -> tuple[str, str]:
    """(engine's name, voice's name) of the narration as it was MADE - its
    audio_timing.json's voice - not of the settings now, which may be
    another voice by the time an older narration is mixed again."""
    from remanga import plugins

    tts = config.tts
    if not identity or identity.get("engine") not in {e.name for e in plugins.items("tts")}:
        return tts.spec.display_name, tts.voice_label
    engine = plugins.get("tts", identity["engine"])
    model = plugins.resolve(engine.config)
    try:
        block = model(**{k: v for k, v in identity.items() if k in model.model_fields})
        return engine.display_name, block.voice_label
    except Exception:
        return engine.display_name, str(identity.get("voice", "?"))


def describe(config, project: str | None = None, chapter: str | None = None) -> tuple[str, dict[str, Any]]:
    """A version's label, and what it records it was made with: the
    narration's voice as it was made (the chapter's audio_timing.json), the
    sound and video settings now."""
    audio, video = config.audio, config.video
    identity = None
    if project is not None:
        timing = read_json_or(get_audio_timing_path(project, chapter, create=False), {}) or {}
        identity = timing.get("voice")
    engine_name, voice_name = _voice_of(identity, config)
    music = Path(audio.bgm_path).name if audio.bgm_enabled and audio.bgm_path else "no music"
    about = {"engine": engine_name, "voice": voice_name, "identity": identity or config.tts.identity(),
             "music": music, "music_lu": audio.bgm_below_voice_lu, "volume_lufs": audio.volume_lufs,
             "video": f"{video.width}x{video.height}"}
    music_part = f"{music}, {audio.bgm_below_voice_lu:g} LU" if audio.bgm_enabled and audio.bgm_path else music
    return f"{engine_name} · {voice_name} · {music_part} · {video.width}x{video.height}", about


def _timing_batches(project: str, chapter: str) -> list[dict[str, Any]]:
    timing = read_json_or(get_audio_timing_path(project, chapter, create=False), {}) or {}
    return [b for b in timing.get("batches", []) if isinstance(b, dict) and b.get("name")]


def record(project: str, chapter: str, config, video_object: str, label: str | None = None,
           about: dict[str, Any] | None = None, fresh: str | None = None) -> int:
    """The chapter's folders as they stand - its narration and its video,
    already in the store - recorded as a version, and made current. A video
    already recorded is that version, made current again, not a second one."""
    store = Store(project)
    data = load(project, chapter)
    for version in data["versions"]:
        if version["video"] == video_object:
            data["current"] = version["id"]
            _save(project, chapter, data)
            return version["id"]
    timing_path = get_audio_timing_path(project, chapter, create=False)
    timing = recipe_key("timing", {"sha256": file_sha256(timing_path)})
    store.put("timing", timing, {"audio_timing.json": timing_path}, {"chapter": chapter})
    sample_rate = config.audio.sample_rate
    takes = []
    for batch in _timing_batches(project, chapter):
        take = take_key(batch["source_sha256"], sample_rate, fresh)
        takes.append({"name": batch["name"], "take": take, "words": words_key(take, config.subtitles)})
    default_label, default_about = describe(config, project, chapter)
    if fresh:   # first, so a narrow table never cuts it off
        default_label = "made fresh · " + default_label
    number = max((v["id"] for v in data["versions"]), default=0) + 1
    data["versions"].append({"id": number, "made": time.strftime("%Y-%m-%d %H:%M"),
                             "label": label or default_label, "about": about or default_about,
                             "takes": takes, "timing": timing, "video": video_object})
    data["current"] = number
    _save(project, chapter, data)
    return number


def adopt(project: str, chapter: str, config) -> int | None:
    """What a chapter's folders hold from before versions existed - its takes,
    word timings, audio_timing.json and video - kept as a version before a run
    clears them, so nothing made then is lost. Nothing to do when the folders
    are empty, or already hold the current version."""
    video = get_final_video_path(project, chapter, create=False)
    timing = get_audio_timing_path(project, chapter, create=False)
    if not video.is_file() or not timing.is_file():
        return None
    store = Store(project)
    data = load(project, chapter)
    current = next((v for v in data["versions"] if v["id"] == data["current"]), None)
    if current:
        folder = store.find("video", current["video"])
        if folder and (folder / "recap.mp4").samefile(video):
            return None
    audio_dir, subs_dir = get_audio_dir(project, chapter), get_subtitles_dir(project, chapter)
    stored_takes = []
    for batch in _timing_batches(project, chapter):
        wav, words = audio_dir / f"{batch['name']}.wav", subs_dir / f"{batch['name']}.json"
        if not (wav.is_file() and words.is_file()):
            return None   # not a whole narration: nothing that could be a version
        take = take_key(batch["source_sha256"], config.audio.sample_rate)
        store.put("take", take, {"take.wav": wav}, {"source": batch["source_sha256"]}, {"adopted": True})
        store.put("words", words_key(take, config.subtitles), {"words.json": words}, {"take": take},
                  {"adopted": True})
        stored_takes.append(take)
    key = recipe_key("video", {"adopted_sha256": file_sha256(video)})
    store.put("video", key, {"recap.mp4": video}, {"adopted": True})
    voice = (read_json_or(timing, {}) or {}).get("voice") or {}
    label = f"made before versions · {voice.get('engine', '?')} {voice.get('voice', '')}".strip()
    return record(project, chapter, config, key, label=label, about={"adopted": True, "voice": voice})


def versions(project: str, chapter: str) -> list[Version]:
    store, data = Store(project), load(project, chapter)
    out = []
    for v in data["versions"]:
        size = store.size("video", v["video"]) + sum(store.size("take", t["take"]) for t in v["takes"])
        objects = [("video", v["video"]), ("timing", v["timing"]),
                   *[(k, t[k]) for t in v["takes"] for k in ("take", "words")]]
        out.append(Version(v["id"], v["made"], v["label"], v["id"] == data["current"], size, len(v["takes"]),
                           objects))
    return out


def make_current(project: str, chapter: str, number: int) -> Path:
    """Version `number` back in the chapter's folders - its takes, word
    timings, audio_timing.json and video, from the store, nothing made again;
    the mix and the picture of whatever was there go (they belong to another
    version, and are made again when needed). The video's path."""
    from remanga.audio.manifest import write_audio_manifest
    from remanga.subtitles.manifest import write_subtitle_manifest
    from remanga.workflow.cleanup import drop_audio_and_video

    store, data = Store(project), load(project, chapter)
    version = next((v for v in data["versions"] if v["id"] == number), None)
    if version is None:
        raise KeyError(f"Chapter {chapter} has no version {number}.")
    missing = [t["name"] for t in version["takes"]
               if not (store.find("take", t["take"]) and store.find("words", t["words"]))]
    if missing or not store.find("timing", version["timing"]) or not store.find("video", version["video"]):
        raise FileNotFoundError(f"Version {number} of chapter {chapter} is not whole in the store "
                                f"({', '.join(missing) or 'its timing or video'} missing).")
    drop_audio_and_video(project, chapter)
    audio_dir, subs_dir = get_audio_dir(project, chapter), get_subtitles_dir(project, chapter)
    for t in version["takes"]:
        store.place("take", t["take"], "take.wav", audio_dir / f"{t['name']}.wav")
        store.place("words", t["words"], "words.json", subs_dir / f"{t['name']}.json")
    store.place("timing", version["timing"], "audio_timing.json", get_audio_timing_path(project, chapter))
    video = get_final_video_path(project, chapter)
    store.place("video", version["video"], "recap.mp4", video)
    write_audio_manifest(audio_dir, chapter, sorted(f"{t['name']}.wav" for t in version["takes"]))
    write_subtitle_manifest(subs_dir, chapter, sorted(f"{t['name']}.json" for t in version["takes"]))
    data["current"] = number
    _save(project, chapter, data)
    return video


def delete(project: str, chapter: str, number: int) -> int:
    """Version `number` deleted, with every object no other version of the
    project uses. The current version can't be: make another current first.
    Bytes freed."""
    data = load(project, chapter)
    if data["current"] == number:
        raise ValueError(f"Version {number} is the one in use - make another version current first.")
    gone = next((v for v in data["versions"] if v["id"] == number), None)
    if gone is None:
        raise KeyError(f"Chapter {chapter} has no version {number}.")
    data["versions"] = [v for v in data["versions"] if v["id"] != number]
    _save(project, chapter, data)
    still = _used(project)
    store, freed = Store(project), 0
    for kind, key in [("video", gone["video"]), ("timing", gone["timing"]),
                      *[(k, t[k]) for t in gone["takes"] for k in ("take", "words")]]:
        if (kind, key) not in still:
            freed += store.size(kind, key)
            store.remove(kind, key)
    return freed


def _used(project: str) -> set[tuple[str, str]]:
    """Every object some version of some chapter of the project uses."""
    used: set[tuple[str, str]] = set()
    folder = get_project_dir(project) / "versions"
    for path in folder.glob("chapter_*.json") if folder.is_dir() else []:
        for v in (json.loads(path.read_text(encoding="utf-8")).get("versions") or []):
            used |= {("video", v["video"]), ("timing", v["timing"])}
            used |= {(k, t[k]) for t in v["takes"] for k in ("take", "words")}
    return used


def keep_long(project: str, path: Path, about: dict[str, Any]) -> str:
    """A long video (workflow/long_video.py) into the store, by its own
    SHA-256 - before a new one of the same chapters replaces it, and after
    it is made, so the file in video/long/ is the store's, read-only. Its key."""
    key = recipe_key("long", {"sha256": file_sha256(path)})
    Store(project).put("long", key, {"long.mp4": path}, {"file": path.name}, about)
    link_or_copy(Store(project).find("long", key) / "long.mp4", path)
    return key


def check(project: str, version: Version) -> str:
    """Every file of a version read and checked against its SHA-256: "ok",
    or what is wrong. A damaged object is set aside (objects.Store.set_aside),
    never deleted."""
    store = Store(project)
    missing = [kind for kind, key in version.objects if store.find(kind, key) is None]
    if missing:
        return f"missing: {', '.join(sorted(set(missing)))}"
    damaged = [kind for kind, key in version.objects if not store.verify(kind, key)]
    for kind, key in version.objects:
        if kind in damaged:
            store.set_aside(kind, key)
    return f"damaged: {', '.join(sorted(set(damaged)))} (set aside in store/damaged)" if damaged else "ok"


@dataclass
class FreshComparison:
    """How the takes of a run made fresh compare with the ones made before
    with the same text and voice."""
    compared: int = 0
    identical: int = 0      # byte for byte
    same_reading: int = 0   # same length and the same words at the same moments
    drift: float = 0.0      # 95% of the words are this close to their time then, in seconds

    def line(self) -> str:
        if not self.compared:
            return "Made fresh - nothing made before to compare it with."
        if self.identical == self.compared:
            return (f"Made fresh: {self.compared} of {self.compared} take(s) byte for byte the ones made before "
                    f"- the store gives back exactly what making it again gives.")
        if self.same_reading == self.compared:
            return (f"Made fresh: {self.compared} of {self.compared} take(s) read the same as before - the same "
                    f"words at the same moments (95% within {self.drift:.2f} s); {self.identical} byte for byte (a "
                    f"model on a GPU never repeats its arithmetic exactly). Both are kept.")
        return (f"Made fresh: {self.same_reading} of {self.compared} take(s) read the same as before; the rest "
                f"came out a different reading this time. Both are kept (Versions).")


SAME_LENGTH = 0.01      # of the take's length
SAME_MOMENT_S = 0.15    # a word this close to its time before is at the same moment


def _words(store: Store, key: str) -> list[tuple[str, float]]:
    folder = store.find("words", key)
    if folder is None:
        return []
    doc = json.loads((folder / "words.json").read_text(encoding="utf-8"))
    return [("".join(ch for ch in str(w.get("word", "")).lower() if ch.isalnum()), float(w.get("start", 0)))
            for w in doc.get("words", [])]


def compare_fresh(project: str, chapter: str, config) -> FreshComparison:
    """After a run made fresh: its takes against the ones made before with
    the same text and voice - byte for byte, and as a reading (length,
    words, the moment of each word, from their word timings)."""
    store, out = Store(project), FreshComparison()
    data = load(project, chapter)
    current = next((v for v in data["versions"] if v["id"] == data["current"]), None)
    timing = read_json_or(get_audio_timing_path(project, chapter, create=False), {}) or {}
    sources = {b["name"]: b["source_sha256"] for b in timing.get("batches", []) if isinstance(b, dict)}
    for t in (current or {}).get("takes", []):
        old_take = take_key(sources.get(t["name"], ""), config.audio.sample_rate)
        before, now = store.record("take", old_take), store.record("take", t["take"])
        if not (before and now):
            continue
        out.compared += 1
        if before["files"]["take.wav"]["sha256"] == now["files"]["take.wav"]["sha256"]:
            out.identical += 1
            out.same_reading += 1
            continue
        size_then, size_now = before["files"]["take.wav"]["size"], now["files"]["take.wav"]["size"]
        then, words_now = _words(store, words_key(old_take, config.subtitles)), _words(store, t["words"])
        same_words = bool(then) and [w for w, _ in then] == [w for w, _ in words_now]
        # The 95th percentile, not the largest: whisper's own timing of one
        # word in a few hundred wanders (one by 0.4 s, measured, on a take
        # otherwise the same to the sample count).
        gaps = sorted(abs(a - b) for (_, a), (_, b) in zip(then, words_now, strict=False))
        drift = gaps[int(len(gaps) * 0.95)] if gaps else 0.0
        if abs(size_then - size_now) <= SAME_LENGTH * size_then and same_words and drift <= SAME_MOMENT_S:
            out.same_reading += 1
            out.drift = max(out.drift, drift)
    return out
