"""Stub for the multi-server agent API.

The full set of endpoints (install / uninstall / switch-mode) lives in the
closed-source `flirexa-pro` package and is overlaid by `install.sh` for
subscriptions that grant the `multi_server` license feature.

Open-core ships only the read-only `/status` endpoint so admins on FREE
or Starter installs can still introspect a server's mode (useful when
downgrading from a paid tier — they can see whether an agent is registered
even if they can no longer manage it).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database.connection import get_db
from ...core.management import ManagementCore


router = APIRouter()


_UPGRADE_403 = HTTPException(
    status_code=403,
    detail=(
        "Multi-server orchestration is a paid feature. "
        "Visit https://flirexa.biz/#pricing — Business tier or higher unlocks "
        "agent install, mode switching, and remote uninstall."
    ),
)


@router.post("/{server_id}/install")
async def install_agent_stub(server_id: int):
    raise _UPGRADE_403


@router.post("/{server_id}/uninstall")
async def uninstall_agent_stub(server_id: int):
    raise _UPGRADE_403


@router.post("/{server_id}/switch-mode")
async def switch_mode_stub(server_id: int):
    raise _UPGRADE_403


@router.get("/{server_id}/status")
async def get_agent_status(server_id: int, db: Session = Depends(get_db)):
    """Read-only status — open on FREE so admins can see inherited servers."""
    core = ManagementCore(db)
    server = core.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return {
        "server_id": server.id,
        "server_name": server.name,
        "mode": server.agent_mode or "ssh",
        "agent_url": server.agent_url,
        "is_remote": server.ssh_host is not None,
        "agent_healthy": None,  # cannot probe without the closed-source client
    }
