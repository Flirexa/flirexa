"""
VPN Management Studio API - Agent Management Routes
Install and manage agents on remote servers
"""

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database.connection import get_db
from ...core.management import ManagementCore
from ..middleware.license_gate import require_license_feature


router = APIRouter()

# Multi-server agent operations are gated by the `multi_server` feature.
# Read-only status check stays ungated so FREE admins can introspect any
# servers they may have inherited from a prior paid install.
_multi_server_gate = Depends(require_license_feature("multi_server"))


# ============================================================================
# SCHEMAS
# ============================================================================

class AgentInstall(BaseModel):
    """Schema for agent installation"""
    agent_code_path: str = str(Path(__file__).parent.parent.parent.parent / "agent.py")
    port: int = 8001


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/{server_id}/install", dependencies=[_multi_server_gate])
async def install_agent(
    server_id: int,
    data: AgentInstall,
    db: Session = Depends(get_db)
):
    """
    Install agent on remote server using SSH bootstrap

    This uses SSH to:
    1. Upload agent.py
    2. Install dependencies (fastapi, uvicorn)
    3. Create systemd service
    4. Start agent

    After installation, server switches to agent mode (HTTP API)
    """
    core = ManagementCore(db)
    server = core.get_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not server.ssh_host:
        raise HTTPException(
            status_code=400,
            detail="Cannot install agent on local server"
        )

    result = core.servers.install_agent(
        server_id=server_id,
        agent_code_path=data.agent_code_path,
        port=data.port
    )

    if not result.get("success"):
        error_msg = result.get("error", "Agent installation failed")
        raise HTTPException(status_code=500, detail=error_msg)

    # Refresh server data from DB
    server = core.get_server(server_id)

    return {
        "success": True,
        "message": f"Agent installed on {server.name}",
        "agent_url": server.agent_url,
        "mode": server.agent_mode,
        "port": result.get("port"),
        "port_accessible": result.get("port_accessible", True),
        "details": result.get("message", "")
    }


@router.post("/{server_id}/uninstall", dependencies=[_multi_server_gate])
async def uninstall_agent(
    server_id: int,
    db: Session = Depends(get_db)
):
    """
    Uninstall agent from remote server

    Switches server back to SSH mode
    """
    core = ManagementCore(db)
    server = core.get_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    success = core.servers.uninstall_agent(server_id)

    if not success:
        raise HTTPException(status_code=500, detail="Agent uninstall failed")

    return {
        "success": True,
        "message": f"Agent uninstalled from {server.name}",
        "mode": "ssh"
    }


@router.post("/{server_id}/switch-mode", dependencies=[_multi_server_gate])
async def switch_mode(
    server_id: int,
    mode: str,
    db: Session = Depends(get_db)
):
    """
    Switch server between agent and SSH mode

    Args:
        mode: "agent" or "ssh"
    """
    if mode not in ["agent", "ssh"]:
        raise HTTPException(
            status_code=400,
            detail="Mode must be 'agent' or 'ssh'"
        )

    core = ManagementCore(db)
    server = core.get_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if mode == "agent":
        success = core.servers.switch_to_agent_mode(server_id)
    else:
        success = core.servers.switch_to_ssh_mode(server_id)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to switch to {mode} mode")

    return {
        "success": True,
        "message": f"Switched {server.name} to {mode} mode",
        "mode": mode
    }


@router.get("/{server_id}/status")
async def get_agent_status(
    server_id: int,
    db: Session = Depends(get_db)
):
    """
    Get agent status for server

    Returns:
        - mode: "agent" or "ssh"
        - agent_url: Agent API URL (if agent mode)
        - health: Agent health status (if agent mode)
    """
    core = ManagementCore(db)
    server = core.get_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    response = {
        "server_id": server.id,
        "server_name": server.name,
        "mode": server.agent_mode or "ssh",
        "agent_url": server.agent_url,
        "is_remote": server.ssh_host is not None
    }

    # Check agent health if in agent mode
    if server.agent_mode == "agent" and server.agent_url and server.agent_api_key:
        from ...core.agent_client import AgentClient

        try:
            client = AgentClient(server.agent_url, server.agent_api_key, timeout=5)
            health = client.health_check()
            response["agent_healthy"] = health
            client.close()
        except Exception:
            response["agent_healthy"] = False

    return response
