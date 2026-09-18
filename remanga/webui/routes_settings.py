"""The panel marker's settings routes: the action bar's switches and scope,
and the Shortcuts menu.

Mounted on the app by routes.py. Both describe how someone works rather than
anything about today's manga, so both are written into config.json as well as
into this session - see settings_store.py."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from remanga.config import MarkerConfig, ShortcutsConfig
from remanga.webui.marker_session import MarkerSession
from remanga.webui.settings_store import persist_marker_settings, persist_shortcuts


def register_settings_routes(app: Flask, session: MarkerSession, config: MarkerConfig) -> None:
    """Adds the shortcuts and marker-settings routes to `app`."""

    @app.get("/api/shortcuts")
    def get_shortcuts():
        return jsonify({
            "shortcuts": config.shortcuts.model_dump(),
            "defaults": ShortcutsConfig().model_dump(),
        })

    @app.post("/api/shortcuts")
    def post_shortcuts():
        try:
            updated = ShortcutsConfig.model_validate(request.get_json(force=True) or {})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        config.shortcuts = updated
        persist_shortcuts(updated.model_dump())
        return jsonify({"ok": True, "shortcuts": updated.model_dump()})

    @app.post("/api/settings")
    def post_settings():
        """The action bar's scope and switches. Applied to this session AND written
        into config.json, because they describe how someone works rather
        than anything about today's manga - see
        settings_store.persist_marker_settings."""
        if session.read_only:
            return jsonify({"ok": False, "error": "This session is read-only"}), 403
        body = request.get_json(silent=True) or {}
        saved: dict[str, Any] = {}

        if "auto_save" in body:
            session.set_auto_save(bool(body["auto_save"]))
            config.auto_save = session.auto_save
            saved["auto_save"] = session.auto_save
        if "auto_order" in body:
            session.set_auto_order(bool(body["auto_order"]))
            config.auto_order = session.auto_order
            saved["auto_order"] = session.auto_order
        if "scope" in body:
            scope = str(body["scope"])
            if scope not in ("page", "chapter", "range", "all"):
                return jsonify({"ok": False, "error": f"Unknown scope {scope!r}"}), 400
            config.auto_detect_scope = scope
            saved["auto_detect_scope"] = scope

        if saved:
            persist_marker_settings(saved)
        return jsonify({"ok": True, **session.detection_status()})
