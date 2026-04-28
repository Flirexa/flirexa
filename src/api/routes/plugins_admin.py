"""Admin routes for installing and managing user-supplied plugins.

These endpoints let an operator install a plugin tarball from any HTTPS URL,
verify its integrity by SHA-256, and remove it later. Plugins shipped with
Flirexa itself (declared in `_CORE_PLUGINS`) are protected from removal here.

Security stance: the plugin model is "you trust the URL you paste". A plugin
runs as full Python code with the same permissions as the API process, so
operators must vet the source. The endpoint logs every install action with
the admin user, the URL, and the verified SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from ..middleware.auth import get_current_admin


router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


# Plugins shipped with the install — never removable via this API.
_CORE_PLUGINS: set[str] = {
    "_example",
    "auto-backup",
    "client-tg-bot",
    "corporate-vpn",
    "extra-protocols",
    "manager-rbac",
    "multi-server",
    "payments",
    "promo-codes",
    "prometheus-metrics",
    "traffic-rules",
    "white-label-basic",
}

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_MAX_TARBALL_BYTES = 25 * 1024 * 1024  # 25 MB hard cap on download
_DOWNLOAD_TIMEOUT_SEC = 60


def _plugins_root() -> Path:
    return Path(__file__).resolve().parents[3] / "plugins"


def _user_installed_index() -> Path:
    return _plugins_root() / ".user_installed.json"


def _read_user_index() -> dict[str, dict]:
    path = _user_installed_index()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_user_index(index: dict[str, dict]) -> None:
    path = _user_installed_index()
    path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")


# ── schemas ──────────────────────────────────────────────────────────────────

class InstallRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")


class InstalledPlugin(BaseModel):
    name: str
    version: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    requires_license_feature: Optional[str] = None
    is_core: bool = False
    user_installed_at: Optional[str] = None
    user_installed_from: Optional[str] = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _validate_url(url: str) -> None:
    if not url.startswith("https://"):
        raise HTTPException(400, "Plugin URL must be https://")
    if not (url.endswith(".tar.gz") or url.endswith(".tgz")):
        raise HTTPException(400, "Plugin URL must end with .tar.gz or .tgz")


def _download_tarball(url: str, expected_sha: str) -> bytes:
    """Download tarball with size cap, verify SHA-256, return bytes."""
    try:
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT_SEC, follow_redirects=True) as cli:
            with cli.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(400, f"Plugin URL returned HTTP {resp.status_code}")
                hasher = hashlib.sha256()
                buf = bytearray()
                for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                    buf.extend(chunk)
                    hasher.update(chunk)
                    if len(buf) > _MAX_TARBALL_BYTES:
                        raise HTTPException(
                            400,
                            f"Plugin tarball exceeds {_MAX_TARBALL_BYTES // (1024 * 1024)} MB limit",
                        )
    except httpx.HTTPError as exc:
        raise HTTPException(400, f"Download failed: {exc}")

    digest = hasher.hexdigest()
    if digest.lower() != expected_sha.lower():
        raise HTTPException(
            400,
            f"SHA-256 mismatch: tarball is {digest}, manifest declared {expected_sha}",
        )
    return bytes(buf)


def _safe_extract(tar_bytes: bytes, dest: Path) -> Path:
    """Extract tarball into dest, refusing path-traversal entries.

    Returns the path of the single top-level directory inside the tarball.
    Plugin tarballs MUST contain exactly one top-level directory whose name
    matches the manifest's `name`.
    """
    import io
    dest.mkdir(parents=True, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise HTTPException(400, "Plugin tarball is empty")

        # Ensure no path traversal — every member path must stay inside dest
        top_levels: set[str] = set()
        for m in members:
            if m.name.startswith("/") or ".." in Path(m.name).parts:
                raise HTTPException(400, f"Plugin tarball contains unsafe path: {m.name}")
            top = Path(m.name).parts[0] if Path(m.name).parts else ""
            if top:
                top_levels.add(top)

        if len(top_levels) != 1:
            raise HTTPException(
                400,
                f"Plugin tarball must contain exactly one top-level directory, got {len(top_levels)}",
            )

        # Python 3.12+ filter for safe extraction; fall back to plain extract on older
        try:
            tar.extractall(path=dest, filter="data")
        except TypeError:
            tar.extractall(path=dest)  # noqa: S202 — manual member check above

        return dest / next(iter(top_levels))


def _read_manifest(plugin_dir: Path) -> dict:
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(400, "Plugin tarball missing manifest.json at top level")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"manifest.json is not valid JSON: {exc}")
    if not isinstance(manifest, dict):
        raise HTTPException(400, "manifest.json must be a JSON object")
    name = manifest.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise HTTPException(
            400,
            "manifest.json `name` must match ^[a-z][a-z0-9-]{1,39}$",
        )
    return manifest


# ── endpoints ────────────────────────────────────────────────────────────────


@router.get("/installed", response_model=list[InstalledPlugin])
async def list_installed(_admin=Depends(get_current_admin)):
    """List every plugin directory under plugins/ with its manifest data."""
    user_index = _read_user_index()
    out: list[InstalledPlugin] = []

    for child in sorted(_plugins_root().iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name.startswith("__"):
            continue

        manifest_path = child / "manifest.json"
        manifest: dict = {}
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                manifest = {}

        is_core = child.name in _CORE_PLUGINS
        user_meta = user_index.get(child.name, {})

        out.append(InstalledPlugin(
            name=child.name,
            version=manifest.get("version"),
            display_name=manifest.get("display_name"),
            description=manifest.get("description"),
            requires_license_feature=manifest.get("requires_license_feature"),
            is_core=is_core,
            user_installed_at=user_meta.get("installed_at"),
            user_installed_from=user_meta.get("source_url"),
        ))

    return out


@router.post("/install", status_code=201)
async def install_plugin(
    body: InstallRequest,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """Download a plugin tarball, verify SHA-256, install into plugins/<name>/.

    The API process must be restarted to actually mount the plugin's routes;
    until then it sits on disk but is not loaded. The response includes a
    `restart_required: true` field so the UI can prompt the operator.
    """
    _validate_url(body.url)
    tar_bytes = _download_tarball(body.url, body.sha256)

    with tempfile.TemporaryDirectory(prefix="flirexa-plugin-") as tmp:
        tmp_dir = Path(tmp)
        extracted_root = _safe_extract(tar_bytes, tmp_dir)
        manifest = _read_manifest(extracted_root)

        plugin_name = manifest["name"]

        if extracted_root.name != plugin_name:
            raise HTTPException(
                400,
                f"Tarball top directory ({extracted_root.name!r}) does not match "
                f"manifest name ({plugin_name!r})",
            )

        target = _plugins_root() / plugin_name
        if target.exists():
            raise HTTPException(409, f"Plugin {plugin_name!r} is already installed")

        # Atomic move: temp → plugins/<name>
        shutil.move(str(extracted_root), str(target))

    # Record in user-installed index
    index = _read_user_index()
    index[plugin_name] = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "installed_by": admin.get("username", "unknown"),
        "source_url": body.url,
        "sha256": body.sha256.lower(),
        "manifest": {
            "name": manifest.get("name"),
            "version": manifest.get("version"),
            "display_name": manifest.get("display_name"),
            "requires_license_feature": manifest.get("requires_license_feature"),
        },
    }
    _write_user_index(index)

    logger.info(
        "Plugin installed: name=%s url=%s sha256=%s by=%s",
        plugin_name, body.url, body.sha256.lower(), admin.get("username", "?"),
    )

    return {
        "ok": True,
        "name": plugin_name,
        "version": manifest.get("version"),
        "display_name": manifest.get("display_name"),
        "restart_required": True,
        "message": (
            "Plugin installed on disk. Restart the API "
            "(`systemctl restart vpnmanager-api`) to load it."
        ),
    }


@router.delete("/{name}", status_code=200)
async def uninstall_plugin(
    name: str,
    admin: dict = Depends(get_current_admin),
):
    """Remove a user-installed plugin from disk. Core plugins are protected."""
    if not _NAME_RE.match(name):
        raise HTTPException(400, f"Invalid plugin name: {name!r}")

    if name in _CORE_PLUGINS:
        raise HTTPException(
            403,
            f"{name!r} is a core plugin and cannot be removed via this API. "
            "Manage it through your license / subscription instead.",
        )

    target = _plugins_root() / name
    if not target.is_dir():
        raise HTTPException(404, f"Plugin {name!r} is not installed")

    shutil.rmtree(target)

    index = _read_user_index()
    index.pop(name, None)
    _write_user_index(index)

    logger.info(
        "Plugin uninstalled: name=%s by=%s",
        name, admin.get("username", "?"),
    )

    return {
        "ok": True,
        "name": name,
        "restart_required": True,
        "message": (
            "Plugin removed from disk. Restart the API "
            "(`systemctl restart vpnmanager-api`) so its routes go away."
        ),
    }
