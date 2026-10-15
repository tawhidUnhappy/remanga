"""The line between remanga and the helper extension in your Firefox: a small
HTTP server on 127.0.0.1 that hands the helper one job at a time and takes
back its pages and results. The helper asks (it polls); remanga never reaches
into the browser.

Only the helper is answered: every request must carry its X-Remanga-Helper
header - which a web page can't send to another origin without a CORS
preflight this server never approves - and a request from a web page (an
http(s) Origin) is refused outright."""

from __future__ import annotations

import itertools
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

PORT = 47615  # also in extension/background.js
HELPER_VERSION = "0.6.0"  # extension/manifest.json's version, which this code expects
MAX_PAGE_BYTES = 200 * 1024 * 1024


class HelperError(RuntimeError):
    """The helper ran a job and it failed (a page it couldn't read, a site that changed)."""


@dataclass
class Job:
    kind: str
    payload: dict[str, Any]
    id: str = ""
    pages: dict[int, tuple[str, bytes, str]] = field(default_factory=dict)  # index -> (type, bytes, url)
    total: int = 0
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

    def wait_for_version(self, version: str, timeout: float | None) -> bool:
        """True once the helper asking for work is `version`."""
        start = time.time()
        while not (self.connected() and self.helper_version == version):
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

    def take_job(self) -> dict[str, Any] | None:
        with self.lock:
            job, self.pending = self.pending, None
            if job:
                self.current = job
                return job.as_message()
            return None

    def job_named(self, job_id: str) -> Job | None:
        with self.lock:
            return self.current if self.current and self.current.id == job_id else None


def _handler(bridge: Bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            pass

        def _answer(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _allowed(self) -> bool:
            origin = self.headers.get("Origin", "")
            if not self.headers.get("X-Remanga-Helper") or origin.startswith(("http:", "https:")):
                self._answer(403, {"error": "only the remanga helper extension"})
                return False
            bridge.helper_seen = time.time()
            bridge.helper_version = self.headers.get("X-Remanga-Helper", "")
            bridge.helper_install = self.headers.get("X-Remanga-Install", "")
            return True

        def _body(self, limit: int) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            if length > limit:
                raise ValueError("too large")
            return self.rfile.read(length)

        def do_OPTIONS(self) -> None:  # a web page's CORS preflight: never approved
            self._answer(403, {"error": "only the remanga helper extension"})

        def do_GET(self) -> None:
            if not self._allowed():
                return
            path = urlparse(self.path).path
            if path == "/remanga/job":
                self._answer(200, {"job": bridge.take_job()})
            elif path == "/remanga/alive":
                self._answer(200, {"ok": True})
            else:
                self._answer(404, {"error": "unknown"})

        def do_POST(self) -> None:
            if not self._allowed():
                return
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/remanga/page":
                    self._page(parse_qs(parsed.query))
                    return
                message = json.loads(self._body(4 * 1024 * 1024) or b"{}")
            except (ValueError, json.JSONDecodeError) as error:
                self._answer(400, {"error": str(error)})
                return
            job = bridge.job_named(str(message.get("job", "")))
            if job is None:
                self._answer(200, {"cancel": True})
                return
            if parsed.path == "/remanga/status":
                bridge.status = (str(message.get("state", "")), str(message.get("message", "")))
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
            job.total = int(query.get("total", ["0"])[0])
            content = self._body(MAX_PAGE_BYTES)
            job.pages[index] = (query.get("type", [""])[0], content, query.get("url", [""])[0])
            bridge.status = ("page", f"{index}/{job.total}")
            self._answer(200, {"ok": True})

    return Handler
