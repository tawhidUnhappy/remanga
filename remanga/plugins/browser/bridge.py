"""The line between remanga and the helper extension in your Firefox: a small
HTTP server on 127.0.0.1 that hands the helper one job at a time and takes
back its pages and results. The helper asks (it polls); remanga never reaches
into the browser.

Who may talk to whom:
- Only this copy's helper is answered. remanga and the helper share a secret
  key (global/browser-helper/pairing-key, built into the helper's file and
  never committed): every helper request carries a fresh nonce and an HMAC
  of it, and every job handed out is signed over that nonce - so neither
  another program on this computer nor a web page can pose as either side,
  and a nonce is never accepted twice.
- A web page can't reach it at all: a request from an http(s) Origin, a CORS
  preflight, or one addressed to any Host but 127.0.0.1/localhost (DNS
  rebinding: a site pointing its own name at 127.0.0.1) is refused.
- A helper without the key (one from before pairing, or another copy's) is
  only noted - its version, so remanga can update it - and may receive only a
  "reload" job.
- One job can't send more than MAX_PAGES pages or MAX_JOB_BYTES in all."""

from __future__ import annotations

import collections
import hashlib
import hmac
import itertools
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from remanga.paths.roots import GLOBAL_DIR

PORT = 47615  # also in extension/background.js
HELPER_VERSION = "0.9.0"  # extension/manifest.json's version, which this code expects
MAX_PAGE_BYTES = 200 * 1024 * 1024
MAX_PAGES = 3000
MAX_JOB_BYTES = 4 * 1024 * 1024 * 1024
KEY_PATH = GLOBAL_DIR / "browser-helper" / "pairing-key"


def pairing_key(path: Path | None = None) -> str:
    """This copy's secret shared with its helper - made the first time,
    readable only by you."""
    path = path or KEY_PATH
    if path.exists() and len(path.read_text(encoding="utf-8").strip()) == 64:
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")
    path.chmod(0o600)
    return key


def proof(key: str, *parts: str) -> str:
    """HMAC-SHA256 of the parts, one per line - extension/background.js makes the same."""
    return hmac.new(key.encode(), "\n".join(parts).encode(), hashlib.sha256).hexdigest()


class HelperError(RuntimeError):
    """The helper ran a job and it failed (a page it couldn't read, a site that changed)."""


@dataclass
class Job:
    kind: str
    payload: dict[str, Any]
    id: str = ""
    pages: dict[int, tuple[str, bytes, str]] = field(default_factory=dict)  # index -> (type, bytes, url)
    total: int = 0
    bytes: int = 0
    result: dict[str, Any] | None = None
    cancelled: bool = False
    done: threading.Event = field(default_factory=threading.Event)

    def as_message(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, **self.payload}


class Bridge:
    """Context manager: the server runs for the duration of a download."""

    def __init__(self, port: int | None = None):
        self.port = port or PORT
        self.lock = threading.Lock()
        self.pending: Job | None = None  # waiting for the helper to take it
        self.current: Job | None = None  # taken, running
        self.helper_seen = 0.0
        self.helper_version = ""
        self.helper_install = ""  # "development" (about:debugging) or "normal" (a signed install)
        self.helper_paired = False  # its requests carry this copy's key
        self.key = pairing_key()
        self.nonces: collections.deque[str] = collections.deque(maxlen=5000)
        self.nonce_set: set[str] = set()
        self.status: tuple[str, str] = ("", "")
        self.ids = itertools.count(1)
        self.server: ThreadingHTTPServer | None = None

    def __enter__(self) -> Bridge:
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), _handler(self))
        except OSError as error:
            raise RuntimeError(f"Port {self.port} on this computer is taken - is another remanga download "
                               f"running? ({error})") from error
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="remanga-bridge", daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        with self.lock:
            for job in (self.pending, self.current):
                if job:
                    job.cancelled = True
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    # ---- remanga's side

    def connected(self) -> bool:
        return time.time() - self.helper_seen < 12

    def wait_for_helper(self, timeout: float | None, on_wait=None) -> bool:
        """True once the helper has asked for work; `on_wait` runs once if it
        hasn't within a few seconds (to say how to load it)."""
        start = time.time()
        told = False
        while not self.connected():
            if not told and time.time() - start > 6:
                told = True
                if on_wait:
                    on_wait()
            if timeout is not None and time.time() - start > timeout:
                return False
            time.sleep(0.5)
        return True

    def ready(self) -> bool:
        """The helper asking is this remanga's version and has this copy's key."""
        return self.connected() and self.helper_version == HELPER_VERSION and self.helper_paired

    def wait_for_version(self, version: str, timeout: float | None) -> bool:
        """True once the helper asking for work is `version`, paired with this copy."""
        start = time.time()
        while not (self.connected() and self.helper_version == version and self.helper_paired):
            if timeout is not None and time.time() - start > timeout:
                return False
            time.sleep(0.5)
        return True

    def run(self, kind: str, payload: dict[str, Any], on_status=None, timeout: float | None = None) -> Job:
        """Gives the helper one job and waits for it to finish. A check you
        are solving in Firefox can take as long as it takes; `timeout` counts
        only time the helper spends otherwise."""
        job = Job(kind, payload, id=f"{kind}-{next(self.ids)}")
        with self.lock:
            self.pending = job
        last = ("", "")
        busy = 0.0
        tick = time.time()
        try:
            while not job.done.wait(0.5):
                now = time.time()
                if self.status != last:
                    last = self.status
                    if on_status:
                        on_status(*last)
                if last[0] != "challenge":
                    busy += now - tick
                tick = now
                if not self.connected() and self.current is job:
                    raise HelperError("Firefox stopped answering (closed, or the helper was removed).")
                if timeout is not None and busy > timeout:
                    raise HelperError(f"The helper took over {int(timeout)} s on {payload.get('url', kind)}.")
        except BaseException:
            job.cancelled = True
            raise
        finally:
            with self.lock:
                if self.pending is job:
                    self.pending = None
                if self.current is job:
                    self.current = None
                self.status = ("", "")
        if not job.result or not job.result.get("ok"):
            raise HelperError((job.result or {}).get("error") or "the helper gave no result")
        return job

    # ---- the helper's side (called from the server's threads)

    def take_job(self, paired: bool) -> dict[str, Any] | None:
        with self.lock:
            if not self.pending or (not paired and self.pending.kind != "reload"):
                return None
            job, self.pending = self.pending, None
            self.current = job
            return job.as_message()

    def fresh_nonce(self, nonce: str) -> bool:
        """A nonce seen before is a replayed request."""
        with self.lock:
            if not (16 <= len(nonce) <= 128) or nonce in self.nonce_set:
                return False
            if len(self.nonces) == self.nonces.maxlen:
                self.nonce_set.discard(self.nonces[0])
            self.nonces.append(nonce)
            self.nonce_set.add(nonce)
            return True

    def job_named(self, job_id: str) -> Job | None:
        with self.lock:
            return self.current if self.current and self.current.id == job_id else None


def _handler(bridge: Bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            pass

        def _answer(self, code: int, body: dict[str, Any], nonce: str = "") -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if nonce:
                # remanga's own word: the helper acts on nothing without it.
                self.send_header("X-Remanga-Proof", proof(bridge.key, "bridge", nonce, data.decode()))
            self.end_headers()
            self.wfile.write(data)

        def _refuse(self) -> None:
            self._answer(403, {"error": "only this copy's remanga helper"})

        def _check(self) -> str | None:
            """None for a request to refuse; "" for a helper without the key
            (noted, nothing more); its nonce for this copy's paired helper."""
            origin = self.headers.get("Origin", "")
            allowed_hosts = {f"127.0.0.1:{bridge.port}", f"localhost:{bridge.port}"}
            if (self.headers.get("Host", "") not in allowed_hosts or not self.headers.get("X-Remanga-Helper")
                    or origin.startswith(("http:", "https:"))):
                self._refuse()
                return None
            nonce = self.headers.get("X-Remanga-Nonce", "")
            given = self.headers.get("X-Remanga-Proof", "")
            paired = bool(given) and hmac.compare_digest(
                given, proof(bridge.key, "helper", nonce, self.command, self.path))
            if paired and not bridge.fresh_nonce(nonce):
                self._refuse()
                return None
            bridge.helper_seen = time.time()
            bridge.helper_version = self.headers.get("X-Remanga-Helper", "")[:32]
            bridge.helper_install = self.headers.get("X-Remanga-Install", "")[:32]
            bridge.helper_paired = paired
            return nonce if paired else ""

        def _body(self, limit: int) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            if length > limit:
                raise ValueError("too large")
            return self.rfile.read(length)

        def do_OPTIONS(self) -> None:  # a web page's CORS preflight: never approved
            self._answer(403, {"error": "only the remanga helper extension"})

        def do_GET(self) -> None:
            nonce = self._check()
            if nonce is None:
                return
            path = urlparse(self.path).path
            if path == "/remanga/job":
                job = bridge.take_job(paired=bool(nonce))
                if not nonce:
                    # Unpaired: only told to reload (from the file remanga just made).
                    self._answer(200, {"job": job, "unpaired": True})
                else:
                    self._answer(200, {"job": job}, nonce)
            elif path == "/remanga/alive":
                self._answer(200, {"ok": True})
            else:
                self._answer(404, {"error": "unknown"})

        def do_POST(self) -> None:
            nonce = self._check()
            if nonce is None:
                return
            parsed = urlparse(self.path)
            if not nonce and parsed.path != "/remanga/result":
                self._refuse()
                return
            try:
                if parsed.path == "/remanga/page":
                    self._page(parse_qs(parsed.query))
                    return
                message = json.loads(self._body(4 * 1024 * 1024) or b"{}")
            except (ValueError, json.JSONDecodeError) as error:
                self._answer(400, {"error": str(error)[:200]})
                return
            job = bridge.job_named(str(message.get("job", "")))
            if job is None or (not nonce and job.kind != "reload"):
                self._answer(200, {"cancel": True})
                return
            if parsed.path == "/remanga/status":
                bridge.status = (str(message.get("state", ""))[:40], str(message.get("message", ""))[:300])
                self._answer(200, {"cancel": job.cancelled})
            elif parsed.path == "/remanga/result":
                job.result = message
                job.done.set()
                self._answer(200, {"ok": True})
            else:
                self._answer(404, {"error": "unknown"})

        def _page(self, query: dict[str, list[str]]) -> None:
            job = bridge.job_named(query.get("job", [""])[0])
            if job is None or job.cancelled:
                self._answer(200, {"cancel": True})
                return
            index = int(query.get("index", ["0"])[0])
            total = int(query.get("total", ["0"])[0])
            if not (1 <= index <= total <= MAX_PAGES):
                raise ValueError(f"page {index} of {total}: out of range")
            content = self._body(MAX_PAGE_BYTES)
            job.bytes += len(content)
            if job.bytes > MAX_JOB_BYTES:
                job.cancelled = True
                raise ValueError("this job sent more than remanga takes")
            job.total = total
            job.pages[index] = (query.get("type", [""])[0][:100], content, query.get("url", [""])[0][:2000])
            bridge.status = ("page", f"{index}/{job.total}")
            self._answer(200, {"ok": True})

    return Handler
