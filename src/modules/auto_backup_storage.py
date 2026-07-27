"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `auto_backup` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "auto_backup"
_UPGRADE_HINT = (
    "This component requires the auto_backup commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


import os
from pathlib import Path

def get_storage_config(manager) -> dict[str, str]:
    return {
        "backup_storage_type": "local",
        "backup_path": os.getenv(
            "VMS_BACKUP_DIR", str(Path(__file__).resolve().parents[2] / "backups")
        ),
    }

def get_backup_dir(manager) -> str:
    return get_storage_config(manager)["backup_path"]

def is_path_mounted(path: str) -> bool:
    return False

def ensure_storage_ready(manager) -> dict:
    target = get_backup_dir(manager)
    try:
        os.makedirs(target, exist_ok=True)
        return {"target": target, "storage_type": "local", "ready": True, "auto_mounted": False, "error": None}
    except OSError as exc:
        return {"target": target, "storage_type": "local", "ready": False, "auto_mounted": False, "error": str(exc)}

def mount_network_storage(config: dict) -> None:
    raise RuntimeError(_UPGRADE_HINT)

def run_mount_command(command: list[str]) -> None:
    raise RuntimeError(_UPGRADE_HINT)
