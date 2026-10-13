"""The routes every remanga web UI serves the same way: the favicon and the
shared bundle (static_shared/ - theme, logo, the loading and done screens),
plus the guard every UI runs before each request.

The guard: the UIs listen on this computer only, but a website open in another
tab could still send them requests (cross-site requests) or reach them through
a domain that points at 127.0.0.1 (DNS rebinding). So a request must name the
computer by address or as localhost, and a change (POST, PUT, DELETE) must come
from the UI's own page. Every answer also forbids framing and type sniffing."""

from __future__ import annotations

import ipaddress

from flask import Flask, abort, request, send_from_directory

from remanga.paths import SHARED_STATIC_DIR

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _host_ok(host: str) -> bool:
    """localhost or an IP address (a domain name could be rebound to this computer)."""
    name = host.rsplit(":", 1)[0] if not host.startswith("[") else host[1:host.find("]")]
    if name.lower() == "localhost":
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def add_guard(app: Flask) -> None:
    @app.before_request
    def only_this_page():
        if not _host_ok(request.host):
            abort(403)
        if request.method in _SAFE_METHODS:
            return None
        origin = request.headers.get("Origin")
        if origin is not None and origin.rstrip("/") != request.host_url.rstrip("/"):
            abort(403)
        if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            abort(403)
        return None

    @app.after_request
    def headers(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


def add_shared_routes(app: Flask) -> None:
    add_guard(app)

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(SHARED_STATIC_DIR / "img", "favicon.ico")

    @app.get("/shared/<path:filename>")
    def shared_asset(filename: str):
        return send_from_directory(SHARED_STATIC_DIR, filename)
