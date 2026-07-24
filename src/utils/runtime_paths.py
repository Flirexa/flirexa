from __future__ import annotations

import os
from pathlib import Path


def get_install_root(default: str = "/opt/vpnmanager") -> Path:
    root = Path(os.getenv("INSTALL_DIR", default))
    if root.exists():
        return root
    return Path(__file__).resolve().parents[2]


def get_current_link(install_root: Path | None = None) -> Path:
    root = install_root or get_install_root()
    return root / "current"


def get_runtime_root(install_root: Path | None = None) -> Path:
    root = install_root or get_install_root()
    current = get_current_link(root)
    if current.exists():
        return current
    return root


def get_shared_root(install_root: Path | None = None) -> Path:
    root = install_root or get_install_root()
    return root / "shared"


def get_releases_root(install_root: Path | None = None) -> Path:
    root = install_root or get_install_root()
    return root / "releases"


def get_version_file(install_root: Path | None = None) -> Path:
    runtime_root = get_runtime_root(install_root)
    runtime_version = runtime_root / "VERSION"
    if runtime_version.exists():
        return runtime_version
    root = install_root or get_install_root()
    return root / "VERSION"


def get_app_version(default: str = "0.0.0") -> str:
    """Return the explicit APP_VERSION override or the runtime VERSION file."""
    override = os.getenv("APP_VERSION", "").strip()
    if override:
        return override
    try:
        value = get_version_file().read_text(encoding="utf-8").strip()
        return value or default
    except OSError:
        return default
