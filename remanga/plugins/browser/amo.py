"""Signing the remanga helper so Firefox keeps it installed - like any other
extension, through restarts - instead of as a temporary add-on.

Firefox installs only extensions Mozilla has signed. Mozilla signs a private
("unlisted") one automatically and for free: it is never listed on
addons.mozilla.org and nobody else can find it. That takes your own
addons.mozilla.org API key - see `./run.sh helper`.

The key lives in global/browser-helper/amo-api-key.json (global/ is never
committed): {"issuer": "user:12345:67", "secret": "..."}, or in the
AMO_JWT_ISSUER / AMO_JWT_SECRET environment variables. Signed files are kept
beside it, one per helper version."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
import zipfile
from pathlib import Path

import requests

from remanga.console import console, escape as _esc
from remanga.paths.roots import GLOBAL_DIR

API = "https://addons.mozilla.org/api/v5"
KEY_PAGE = "https://addons.mozilla.org/en-US/developers/addon/api/key/"
HELPER_DIR = GLOBAL_DIR / "browser-helper"
KEY_PATH = HELPER_DIR / "amo-api-key.json"


class SigningError(RuntimeError):
    pass


def api_key() -> tuple[str, str] | None:
    issuer, secret = os.environ.get("AMO_JWT_ISSUER", ""), os.environ.get("AMO_JWT_SECRET", "")
    if not (issuer and secret) and KEY_PATH.exists():
        data = json.loads(KEY_PATH.read_text(encoding="utf-8"))
        issuer, secret = str(data.get("issuer", "")).strip(), str(data.get("secret", "")).strip()
    return (issuer, secret) if issuer and secret else None


def signed_path(version: str) -> Path:
    return HELPER_DIR / f"remanga-helper-{version}.xpi"


def is_signed(path: Path) -> bool:
    """A Mozilla-signed extension carries its signature in META-INF/."""
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.startswith("META-INF/") for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _token(issuer: str, secret: str) -> str:
    """The JWT addons.mozilla.org asks for: HS256, at most 5 minutes long."""
    now = int(time.time())
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps({"iss": issuer, "jti": uuid.uuid4().hex, "iat": now, "exp": now + 240}).encode())
    signature = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(signature)}"


def _check(response: requests.Response, doing: str) -> dict:
    if response.status_code >= 400:
        raise SigningError(f"addons.mozilla.org refused {doing} ({response.status_code}): {response.text[:600]}")
    return response.json() if response.content else {}


def _validation_errors(validation: dict) -> list[str]:
    return [f"{m.get('message', '')} {m.get('file') or ''}".strip()
            for m in (validation or {}).get("messages", []) if m.get("type") == "error"]


def sign(xpi: Path, guid: str, version: str) -> Path:
    """Uploads the helper as an unlisted version, waits for Mozilla to check
    and sign it (usually a few minutes) and keeps the signed file."""
    key = api_key()
    if not key:
        raise SigningError(f"No addons.mozilla.org API key - see `./run.sh helper` (key file: {KEY_PATH}).")
    session = requests.Session()

    def auth() -> dict[str, str]:
        return {"Authorization": f"JWT {_token(*key)}"}

    def call(method: str, url: str, **kwargs) -> requests.Response:
        """addons.mozilla.org answers 502/503 now and then; such a request is
        tried again after a pause (a creation is first checked for, since a
        502 can come back from one that went through)."""
        for attempt in range(4):
            response = session.request(method, url, headers=auth(), timeout=120, **kwargs)
            if response.status_code < 500:
                return response
            time.sleep(15 * (attempt + 1))
            if method == "POST" and version_exists():
                return response
        return response

    detail_url = f"{API}/addons/addon/{guid}/versions/v{version}/"

    def version_exists() -> bool:
        return session.get(detail_url, headers=auth(), timeout=60).status_code == 200

    if version_exists():
        console.print(f"[cyan]remanga helper {version} is already with Mozilla - waiting for its signature...[/]")
    else:
        console.print(f"[cyan]Sending remanga helper {version} to Mozilla to be signed (unlisted - private)...[/]")
        with xpi.open("rb") as handle:
            upload = _check(call("POST", f"{API}/addons/upload/", data={"channel": "unlisted"},
                                 files={"upload": (xpi.name, handle, "application/x-xpinstall")}), "the upload")
        upload_id = upload["uuid"]
        for _ in range(120):
            if upload.get("processed"):
                break
            time.sleep(5)
            upload = _check(call("GET", f"{API}/addons/upload/{upload_id}/"), "the check")
        if not upload.get("processed"):
            raise SigningError("Mozilla's check of the upload didn't finish in 10 minutes - try again later.")
        if not upload.get("valid"):
            problems = _validation_errors(upload.get("validation"))
            raise SigningError("Mozilla's check found problems:\n  " + "\n  ".join(problems))
        console.print("[green]Mozilla's check passed.[/] Asking for the signature...")
        exists = call("GET", f"{API}/addons/addon/{guid}/").status_code == 200
        if exists:
            created = call("POST", f"{API}/addons/addon/{guid}/versions/", json={"upload": upload_id})
        else:
            # The first time: the add-on itself is made on your account.
            created = call("POST", f"{API}/addons/addon/", json={"version": {"upload": upload_id}})
        if not version_exists():
            _check(created, "the new version")

    for _ in range(360):
        file = (_check(call("GET", detail_url), "the version") or {}).get("file") or {}
        if file.get("status") == "public" and file.get("url"):
            break
        if file.get("status") == "disabled":
            raise SigningError("Mozilla rejected this version - see your add-on on addons.mozilla.org/developers.")
        time.sleep(5)
    else:
        raise SigningError("Signing didn't finish in 30 minutes - run `./run.sh helper --install` again later.")

    target = signed_path(version)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".partial")
    partial.write_bytes(_check_bytes(call("GET", file["url"])))
    if not is_signed(partial):
        partial.unlink(missing_ok=True)
        raise SigningError("The file Mozilla sent back isn't signed.")
    partial.replace(target)
    console.print(f"[bold green]✓ Signed:[/] {_esc(str(target))}")
    return target


def _check_bytes(response: requests.Response) -> bytes:
    if response.status_code >= 400:
        raise SigningError(f"Downloading the signed file failed ({response.status_code}).")
    return response.content
