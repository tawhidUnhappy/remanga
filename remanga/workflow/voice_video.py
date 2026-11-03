"""Voice samples as one video to watch through: each sample plays under a card
naming it - its number, name, what it is and its file - with the whole set
listed beside it (user, 2026-10-27: an mp3 of them all in a row meant
matching timestamps to names by hand; "make a video that shows the speaker
or the file name, that way it will be more efficient").

Each sample is brought to the same loudness for the video only (the files
beside it stay as the engine made them), so no voice wins for being louder."""

from __future__ import annotations

import shutil
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from remanga.audio.master import write_master
from remanga.ffmpeg_io import run_ffmpeg
from remanga.paths import REPO_ROOT

W, H = 1280, 720
GAP_SECONDS = 2.0
LOUDNESS_LUFS = -14.0
ANTON = REPO_ROOT / "assets" / "fonts" / "Anton-Regular.ttf"
BACKGROUND, YELLOW, GREY, WHITE = (18, 18, 22), (255, 230, 0), (120, 120, 130), (235, 235, 240)


def _seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def _card(title: str, samples: list[tuple[str, str, Path]], index: int) -> Image.Image:
    name, what, wav = samples[index]
    image = Image.new("RGB", (W, H), BACKGROUND)
    draw = ImageDraw.Draw(image)
    small, middle = ImageFont.load_default(size=22), ImageFont.load_default(size=30)
    draw.text((48, 36), title, font=small, fill=GREY)
    draw.text((48, 70), f"voice {index + 1} of {len(samples)}", font=small, fill=GREY)
    draw.text((48, 170), f"#{index + 1}", font=ImageFont.truetype(str(ANTON), 72), fill=YELLOW)
    size = 110  # the name shrinks until it fits left of the list
    while size > 40 and draw.textbbox((48, 0), name, font=ImageFont.truetype(str(ANTON), size))[2] > 830:
        size -= 4
    draw.text((48, 250 + (110 - size) // 2), name, font=ImageFont.truetype(str(ANTON), size), fill=WHITE)
    draw.text((52, 400), what[:60], font=middle, fill=WHITE)
    draw.text((52, 450), f"file: {wav.name}", font=small, fill=GREY)
    row = max(20, min(48, (H - 120) // len(samples)))
    listed = ImageFont.load_default(size=max(12, min(24, row - 10)))
    draw.line((860, 60, 860, H - 60), fill=(50, 50, 58), width=2)
    for n, (other, _, _) in enumerate(samples):
        y = 70 + n * row
        if n == index:
            draw.rounded_rectangle((875, y - 6, W - 30, y + row - 14), 6, fill=(60, 55, 10))
        draw.text((890, y), f"{n + 1:>2}  {other}", font=listed, fill=YELLOW if n == index else GREY)
    return image


def labelled_video(samples: list[tuple[str, str, Path]], title: str, out: Path, sample_rate: int) -> Path:
    """`samples` = (name, what it is, wav) in the order to play them; the
    video goes to `out`. Each card is on screen exactly as long as its
    sample plus the gap after it: looped stills joined by the concat filter
    (the concat demuxer cut the last card short, or ran it long)."""
    with tempfile.TemporaryDirectory(prefix="voices-video-") as tmp:
        work = Path(tmp)
        gap = work / "gap.wav"
        run_ffmpeg(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono", "-t", f"{GAP_SECONDS}",
                    "-c:a", "pcm_s16le", str(gap)], check=True, capture=True)
        cmd = ["ffmpeg", "-y"]
        listing = []
        for index, (_, _, wav) in enumerate(samples):
            level = work / f"level_{index:02d}.wav"
            raw = work / f"raw_{index:02d}.wav"
            shutil.copy2(wav, raw)
            write_master(raw, level, sample_rate, target_lufs=LOUDNESS_LUFS)
            run_ffmpeg(["ffmpeg", "-y", "-i", str(level), "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
                        str(work / f"even_{index:02d}.wav")], check=True, capture=True)
            listing += [f"file '{work / f'even_{index:02d}.wav'}'", f"file '{gap}'"]
            card = work / f"card_{index:02d}.png"
            _card(title, samples, index).save(card)
            cmd += ["-loop", "1", "-framerate", "24", "-t", f"{_seconds(level) + GAP_SECONDS:.3f}", "-i", str(card)]
        concat = work / "sound.txt"
        concat.write_text("\n".join(listing) + "\n", encoding="utf-8")
        sound = work / "sound.wav"
        run_ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(sound)],
                   check=True, capture=True)
        n = len(samples)
        out.parent.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(out.stem + ".part.mp4")
        cmd += ["-i", str(sound), "-filter_complex",
                "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]",
                "-map", "[v]", "-map", f"{n}:a", "-c:v", "libx264", "-tune", "stillimage", "-crf", "20", "-r", "24",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(partial)]
        run_ffmpeg(cmd, check=True, capture=True)
        partial.replace(out)
    return out
