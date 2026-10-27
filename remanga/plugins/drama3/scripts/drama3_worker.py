#!/usr/bin/env python3
"""Standalone Fish Audio Drama 3 synthesis worker - runs inside the isolated
`.tools/venv-drama3` environment as a long-lived subprocess, spoken to by
remanga/audio/synth/ over line-delimited JSON on stdin/stdout. Stdlib only, no
dependency on the `remanga` package.

The model itself runs in speech.cpp's `speech worker` (a C++ port on ggml and
Vulkan; setup.py fetches its release), which this script starts and speaks
JSON Lines with (speech.cpp's docs/worker.md, protocol 3). This script turns
that protocol - the audio as base64 PCM chunks, then an `end` - into remanga's:
one request in, one WAV written, one answer out.

Drama 3 has no named voices: it is a voice-cloning model. With `voice_file`
(the default), every take is read from a voice file - made once per
described voice: the reference line read with the voice's cue under its seed
in the model's own voice, then `speech voice` turns that recording into the
file, kept in `--voices_dir` and added to the running worker. The voice is
then fixed - the seed only changes the delivery - and speech.cpp's chunk
joins click in it, so it is read a sentence per request.

Without it, a take is read in the model's own voice (voice "none"): the cue
opens the text and the seed picks the voice. It sounded smoother to the user,
but the narrator changed from page to page (per-take median pitch 79-123 Hz
over a chapter, against 90-107 from a voice file) - "voice don't match" -
and long takes drop whole sentences (a chapter in one take: 73% of its
script), which page takes and audio/retakes.py:retake_mismatches cover.

Protocol (newline-delimited JSON, one message per line):
  Parent -> worker: {"cmd": "synthesize", "text": ..., "voice": name, "cue": "[...]",
                     "voice_file": bool, "voice_seed": n, "seed": n, "output_path": ...}
  Worker -> parent (once ready): {"event": "ready", "device": ...}
  Worker -> parent (per request): {"ok": true, "stop": ...} or {"ok": false, "error": "..."}
  Parent -> worker: {"cmd": "shutdown"}  (or just close stdin)

speech.cpp writes its logs to stderr, which is passed straight through to the
parent's stderr reader.

Headroom: speech.cpp puts the experts of as many layers on the GPU as the
memory free at load holds, beside a fixed allowance for its working buffers -
and on a 12 GB RTX 3060 with NVIDIA's Vulkan driver that allowance is short:
the first request ran the card out of memory (ErrorOutOfDeviceMemory). So
`--headroom_gb` is held on the GPU through the CUDA driver (libcuda, by
ctypes) while the model loads and let go once it is ready: speech.cpp sees
that much less free, keeps fewer layers' experts, and the memory is there
when a request needs it. Measured: 1.5 GiB held -> 11 of 40 layers on the
GPU, a line read at 0.82x real time, peak 11.8 of 12.3 GB; but 2.0 and 2.5
each once failed to load ("cannot reserve the memory of the codec's
decoding"), so a load that runs out is tried again holding a GiB more.
Without libcuda (no NVIDIA driver) nothing is held."""

from __future__ import annotations

import argparse
import array
import base64
import ctypes
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

PROTOCOL = 3

# What every voice's reference recording says: plain narration, about 14
# seconds - long enough for the codec to carry the voice, short enough that
# every chunk's prompt stays small.
REFERENCE_TEXT = ("Chapter one opens on a quiet village at dawn. Alfred walks to the well, where an old woman "
                  "tells him the soldiers came again last night, and that nobody in the village slept.")
# Bumped when how a voice file is made changes, so the old files are not used.
VOICE_FILE_VERSION = 1

# A load that runs out of GPU memory is tried again holding this much more.
LOAD_ATTEMPTS = 3
HEADROOM_STEP_GB = 1.0


# Where a text is cut into requests: after a sentence's closing mark. One
# request per sentence, because speech.cpp cuts a longer text into ~300-byte
# chunks itself and the joins between its chunks CLICK - measured on a page of
# HimeSama ch1 read from a voice file: three clicks, each exactly on a codec
# frame boundary (frames 204, 442, 779 of their request) at the first word of
# a sentence. A request of one sentence starts and ends in the model's own
# silence, so the only joins are these, in a pause. It is also how speech.cpp
# measured the model: one sentence per request, from a voice file. A mark
# followed by a small letter ("Yes... she said") is no end.
SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z0-9\"'(])")


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_END.split(text.strip()) if part.strip()] or [text]


# How much of the silence a sentence ends on is kept. Read a sentence per
# request, each comes back with a tail of its own, and two of them butted
# together left 600-1,000 ms between sentences (Kokoro reading straight
# through pauses ~420 ms): a tail is cut to this, with a short fade, so the
# next sentence comes in after a narrator's pause. The start is left as it
# is - it comes back 20-30 ms long.
TAIL_KEEP_MS = 350
TAIL_FADE_MS = 10
# A 10 ms frame this far under the sentence's loud frames is silence.
SILENCE_UNDER_DB = 40.0


def trim_tail(pcm: bytes, sample_rate: int) -> bytes:
    """16-bit mono `pcm` with the silence after its last sound cut to
    TAIL_KEEP_MS (stdlib only: this runs in the tool's empty venv)."""
    samples = array.array("h", pcm)
    step = sample_rate // 100
    levels = [max((abs(v) for v in samples[i:i + step]), default=0) for i in range(0, len(samples), step)]
    if not levels:
        return pcm
    loud = sorted(levels)[int(len(levels) * 0.9)]
    floor = loud * 10 ** (-SILENCE_UNDER_DB / 20)
    last = max((n for n, level in enumerate(levels) if level > floor), default=len(levels) - 1)
    end = min(len(samples), (last + 1) * step + sample_rate * TAIL_KEEP_MS // 1000)
    kept = samples[:end]
    fade = min(len(kept), sample_rate * TAIL_FADE_MS // 1000)
    for k in range(fade):
        kept[len(kept) - fade + k] = int(kept[len(kept) - fade + k] * (fade - k) / fade)
    return kept.tobytes()


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def read_message(speech: subprocess.Popen) -> dict:
    line = speech.stdout.readline()
    if not line:
        raise RuntimeError(f"speech worker exited (code {speech.poll()})")
    return json.loads(line)


def answer(speech: subprocess.Popen, request_id: str, on_chunk=None) -> dict:
    """Reads up to request `request_id`'s terminal message, handing its audio
    chunks to `on_chunk`."""
    while True:
        msg = read_message(speech)
        if msg.get("id") != request_id:
            continue   # progress or an answer to nothing of ours
        kind = msg.get("type")
        if kind == "chunk":
            if on_chunk:
                on_chunk(base64.b64decode(msg["pcm"]))
        elif kind in ("end", "error", "cancelled"):
            return msg


def failure(msg: dict) -> str | None:
    if msg.get("type") == "end":
        return None
    error = msg.get("error") or {}
    return f"{error.get('code', msg.get('type'))}: {error.get('message', '')}"


class Worker:
    def __init__(self, args) -> None:
        self.args = args
        self.voices_dir = Path(args.voices_dir)
        self.count = 0
        self.added: set[str] = set()
        cmd = [args.speech, "worker", args.model]
        if args.threads > 0:
            cmd += ["--threads", str(args.threads)]
        self.speech = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
                                       text=True, encoding="utf-8", bufsize=1)

    def request(self, line: dict, on_chunk=None) -> dict:
        self.count += 1
        line = {**line, "id": str(self.count)}
        self.speech.stdin.write(json.dumps(line) + "\n")
        self.speech.stdin.flush()
        return answer(self.speech, line["id"], on_chunk)

    def to_wav(self, lines: list[dict], output_path: Path, sample_rate: int) -> dict:
        """Synthesis requests one after another, their audio written end to
        end into one 16-bit mono WAV, as every other engine writes. Returns
        the last request's answer, or the first one that failed."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial = output_path.with_name(output_path.stem + ".part.wav")
        try:
            with wave.open(str(partial), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(sample_rate)
                for line in lines:
                    pieces: list[bytes] = []
                    msg = self.request(line, pieces.append)
                    if failure(msg):
                        return msg
                    out.writeframes(trim_tail(b"".join(pieces), sample_rate) if len(lines) > 1
                                    else b"".join(pieces))
            partial.replace(output_path)
            return msg
        finally:
            partial.unlink(missing_ok=True)

    def voice(self, name: str, cue: str, seed: int, sample_rate: int) -> str:
        """The speech.cpp voice for described voice `name` under `seed`: made
        into a file the first time (see the module docstring), added to the
        worker the first time this run."""
        key = f"{name}-s{seed}-v{VOICE_FILE_VERSION}"
        if key in self.added:
            return key
        path = self.voices_dir / f"{key}.voice.gguf"
        if not path.is_file():
            self.voices_dir.mkdir(parents=True, exist_ok=True)
            recording = self.voices_dir / f"{key}.wav"
            msg = self.to_wav([{"type": "synthesize", "voice": "none", "seed": seed,
                                "text": f"{cue} {REFERENCE_TEXT}" if cue else REFERENCE_TEXT}],
                              recording, sample_rate)
            if failure(msg):
                raise RuntimeError(f"reading the reference line for {name} failed: {failure(msg)}")
            made = subprocess.run([self.args.speech, "voice", self.args.model, str(recording),
                                   "--transcript", REFERENCE_TEXT, str(path)],
                                  capture_output=True, text=True)
            if made.returncode != 0 or not path.is_file():
                raise RuntimeError(f"making the voice file for {name} failed: {made.stderr.strip()[-500:]}")
        msg = self.request({"type": "add_voice", "name": key, "path": str(path)})
        if failure(msg):
            raise RuntimeError(f"adding the voice {name} failed: {failure(msg)}")
        self.added.add(key)
        return key

    def synthesize(self, req: dict, sample_rate: int) -> dict:
        """The text in the model's own voice (one request, the cue first), or
        with `voice_file` a sentence per request (see SENTENCE_END) in the
        voice file of the voice asked for."""
        options = {key: req[key] for key in ("seed", "temperature", "top_p", "top_k", "max_seconds")
                   if req.get(key) is not None}
        cue = req.get("cue", "")
        if req.get("voice_file"):
            voice = self.voice(req["voice"], cue, int(req.get("voice_seed", 1)), sample_rate)
            lines = [{"type": "synthesize", "text": sentence, "voice": voice, **options}
                     for sentence in sentences(req["text"])]
        else:
            lines = [{"type": "synthesize", "voice": "none", **options,
                      "text": f"{cue} {req['text']}" if cue else req["text"]}]
        msg = self.to_wav(lines, Path(req["output_path"]), sample_rate)
        if failure(msg):
            return {"ok": False, "error": failure(msg)}
        # "max_seconds": a chunk ran to its cap and was cut there - the take
        # checks downstream hear that as missing words and say so.
        return {"ok": True, "stop": msg.get("stop"), "seed": msg.get("seed")}


def out_of_memory(error: dict) -> bool:
    """A load that ran short of GPU memory: speech.cpp's out_of_memory, or its
    "cannot reserve the memory of the codec's decoding", which came back under
    another code and so was not tried again (2026-10-27: the whole chapter run
    stopped on the first load, with the card free a minute later)."""
    return error.get("code") == "out_of_memory" or "cannot reserve the memory" in str(error.get("message", ""))


def hold_gpu_memory(gib: float):
    """`gib` GiB taken on the first GPU through the CUDA driver, as a release
    function - or a no-op one when there is no CUDA driver or nothing to
    hold."""
    if gib <= 0:
        return lambda: None
    try:
        cuda = ctypes.CDLL("libcuda.so.1")
        device, context, pointer = ctypes.c_int(), ctypes.c_void_p(), ctypes.c_uint64()
        if (cuda.cuInit(0) or cuda.cuDeviceGet(ctypes.byref(device), 0)
                or cuda.cuCtxCreate_v2(ctypes.byref(context), 0, device)):
            return lambda: None
        size = int(gib * (1 << 30))
        if cuda.cuMemAlloc_v2(ctypes.byref(pointer), ctypes.c_size_t(size)):
            cuda.cuCtxDestroy_v2(context)
            return lambda: None
        # Written to, so it is really taken, and a moment for the driver's
        # free-memory figure - what speech.cpp reads through Vulkan - to see it.
        cuda.cuMemsetD8_v2(pointer, ctypes.c_ubyte(0), ctypes.c_size_t(size))
        cuda.cuCtxSynchronize()
        time.sleep(1.0)
    except OSError:
        return lambda: None

    def release() -> None:
        cuda.cuMemFree_v2(pointer)
        cuda.cuCtxDestroy_v2(context)
    return release


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speech", required=True, help="speech.cpp's executable")
    parser.add_argument("--model", required=True, help="the Drama 3 GGUF file")
    parser.add_argument("--voices_dir", required=True, help="where the voice files are kept")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--headroom_gb", type=float, default=0.0)
    args = parser.parse_args()

    # How much the GPU's free memory moves under it (the desktop, a browser)
    # is not knowable in advance: a load that runs out of memory is tried
    # again holding more, at the cost of a few layers' experts on the CPU.
    for attempt in range(LOAD_ATTEMPTS):
        headroom = args.headroom_gb + attempt * HEADROOM_STEP_GB if args.headroom_gb > 0 else 0.0
        release = hold_gpu_memory(headroom)
        worker = Worker(args)
        try:
            ready = read_message(worker.speech)
        except Exception as e:
            release()
            send({"event": "error", "error": f"Failed to start speech.cpp: {e}"})
            sys.exit(1)
        release()
        error = ready.get("error") or {}
        if ready.get("type") == "ready" or not out_of_memory(error) or headroom <= 0:
            break
        print(f"drama3_worker: the load ran out of GPU memory with {headroom:g} GiB held - trying again "
              f"with more", file=sys.stderr, flush=True)
        worker.speech.wait(timeout=30)
    if ready.get("type") != "ready":
        send({"event": "error", "error": f"Failed to load Drama 3 ({error.get('code', '?')}): "
                                         f"{error.get('message', ready)}"})
        sys.exit(1)
    if ready.get("protocol") != PROTOCOL:
        send({"event": "error", "error": f"speech.cpp speaks worker protocol {ready.get('protocol')}, "
                                         f"this worker protocol {PROTOCOL}"})
        sys.exit(1)
    model = ready.get("model") or {}
    sample_rate = int(model.get("sample_rate") or 44100)
    send({"event": "ready", "device": model.get("device", "?"), "sample_rate": sample_rate})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            send({"ok": False, "error": f"Bad request JSON: {e}"})
            continue

        if req.get("cmd") == "shutdown":
            break

        try:
            send(worker.synthesize(req, sample_rate))
        except Exception as e:
            send({"ok": False, "error": str(e)})
            if worker.speech.poll() is not None:
                break

    try:
        worker.speech.stdin.close()
        worker.speech.wait(timeout=10)
    except Exception:
        worker.speech.kill()


if __name__ == "__main__":
    main()
