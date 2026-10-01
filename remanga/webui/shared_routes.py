"""The routes every remanga web UI serves the same way: the favicon and the
shared bundle (static_shared/ - theme, logo, the loading and done screens)."""

from __future__ import annotations

from flask import Flask, send_from_directory

from remanga.paths import SHARED_STATIC_DIR


def add_shared_routes(app: Flask) -> None:
    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(SHARED_STATIC_DIR / "img", "favicon.ico")

    @app.get("/shared/<path:filename>")
    def shared_asset(filename: str):
        return send_from_directory(SHARED_STATIC_DIR, filename)
