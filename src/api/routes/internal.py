"""
VPN Management Studio Internal API — endpoints for client portal inter-service communication.
Protected by SERVICE_API_TOKEN header.
"""

import os
import io
import re
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

import qrcode

from ...database.connection import get_db
from ...database.models import Client, Server
from ...core.management import ManagementCore

router = APIRouter()

SERVICE_API_TOKEN = os.getenv("SERVICE_API_TOKEN", "")


def _safe_filename(name: str) -> str:
    """Sanitize name for Content-Disposition header (ASCII-safe)."""
    return re.sub(r'[^\w\-.]', '_', name) or "client"


def verify_service_token(x_service_token: str = Header(...)):
    """Verify internal service token"""
    if not SERVICE_API_TOKEN:
        raise HTTPException(status_code=503, detail="SERVICE_API_TOKEN not configured")
    if not secrets.compare_digest((x_service_token or "").strip(), SERVICE_API_TOKEN.strip()):
        raise HTTPException(status_code=403, detail="Invalid service token")


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

class CreateClientRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    server_id: Optional[int] = None
    bandwidth_limit: Optional[int] = None
    traffic_limit_mb: Optional[int] = None
    expiry_days: Optional[int] = None


class CreateClientResponse(BaseModel):
    id: int
    name: str
    ipv4: Optional[str] = None
    server_id: int
    server_type: Optional[str] = None


class ClientInfoResponse(BaseModel):
    id: int
    name: str
    ipv4: Optional[str] = None
    status: str
    enabled: bool
    server_id: int
    server_name: Optional[str] = None
    server_type: Optional[str] = None
    bandwidth_limit: Optional[int] = None
    traffic_used_rx: int = 0
    traffic_used_tx: int = 0
    expiry_date: Optional[str] = None


class UpdateLimitsRequest(BaseModel):
    bandwidth_limit: Optional[int] = None
    traffic_limit_mb: Optional[int] = None
    expiry_date: Optional[str] = None
    enabled: Optional[bool] = None
    status: Optional[str] = None
    reset_traffic: bool = False  # If True, reset WG traffic counter (call after subscription renewal)


class DefaultServerResponse(BaseModel):
    id: int
    name: str


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/clients", response_model=CreateClientResponse)
async def create_client(
    data: CreateClientRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_service_token),
):
    """Create a WireGuard client (called by client portal after payment)"""
    # License enforcement: internal endpoint must respect client limits just like the admin API.
    # Without this check an attacker with SERVICE_API_TOKEN could bypass the license limit.
    try:
        from sqlalchemy import text as _sql_text
        from ...modules.license.manager import get_license_manager
        db.execute(_sql_text("SELECT pg_advisory_xact_lock(1000001)"))
        mgr = get_license_manager()
        info = mgr.get_license_info()
        current_count = db.query(Client).count()
        if not info.can_add_client(current_count):
            raise HTTPException(
                status_code=403,
                detail=f"License limit reached: {current_count}/{info.max_clients} clients."
            )
    except HTTPException:
        raise
    except Exception as _lic_err:
        from loguru import logger
        logger.error(f"License check failed in internal client creation: {_lic_err}")
        raise HTTPException(status_code=503, detail="License verification unavailable")

    core = ManagementCore(db)
    client = core.create_client(
        name=data.name,
        server_id=data.server_id,
        bandwidth_limit=data.bandwidth_limit,
        traffic_limit_mb=data.traffic_limit_mb,
        expiry_days=data.expiry_days,
    )
    if not client:
        raise HTTPException(status_code=500, detail="Failed to create client")

    return CreateClientResponse(
        id=client.id,
        name=client.name,
        ipv4=client.ipv4,
        server_id=client.server_id,
        server_type=getattr(client.server, "server_type", None) if getattr(client, "server", None) else None,
    )


@router.get("/clients/by-ids", response_model=List[ClientInfoResponse])
async def get_clients_by_ids(
    ids: str = Query(..., description="Comma-separated client IDs"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_service_token),
):
    """Get clients by list of IDs (for portal user's devices)"""
    try:
        client_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid IDs format")

    if not client_ids:
        return []

    clients = db.query(Client).filter(Client.id.in_(client_ids)).all()

    return [
        ClientInfoResponse(
            id=c.id,
            name=c.name,
            ipv4=c.ipv4,
            status=c.status.value if hasattr(c.status, 'value') else str(c.status),
            enabled=c.enabled,
            server_id=c.server_id,
            server_name=c.server.name if c.server else None,
            server_type=getattr(c.server, "server_type", None) if c.server else None,
            bandwidth_limit=c.bandwidth_limit,
            traffic_used_rx=c.traffic_used_rx or 0,
            traffic_used_tx=c.traffic_used_tx or 0,
            expiry_date=c.expiry_date.isoformat() if c.expiry_date else None,
        )
        for c in clients
    ]


@router.get("/clients/{client_id}/config")
async def get_client_config(
    client_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_service_token),
):
    """Get configuration payload for a client."""
    core = ManagementCore(db)
    client = core.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    server_type = (getattr(client.server, "server_type", "") or "").lower() if client.server else ""
    if server_type in {"hysteria2", "tuic"}:
        access = core.clients.get_proxy_client_access(client_id)
        if not access:
            raise HTTPException(status_code=500, detail="Failed to generate proxy config")
        return {
            "client_name": client.name,
            "protocol": access.get("protocol"),
            "category": access.get("category"),
            "uri": access.get("uri"),
            "config": access.get("config"),
            "config_text": access.get("config_yaml") or access.get("config_json") or access.get("config"),
        }

    config = core.get_client_config(client_id)
    if not config:
        raise HTTPException(status_code=500, detail="Failed to generate config")

    return {"config": config, "config_text": config, "client_name": client.name, "protocol": "wireguard", "category": "vpn"}


@router.get("/clients/{client_id}/qrcode")
async def get_client_qrcode(
    client_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_service_token),
):
    """Get QR code image for client configuration."""
    core = ManagementCore(db)
    client = core.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    server_type = (getattr(client.server, "server_type", "") or "").lower() if client.server else ""
    if server_type in {"hysteria2", "tuic"}:
        access = core.clients.get_proxy_client_access(client_id)
        qr_payload = access.get("uri") if access else None
        if not qr_payload:
            raise HTTPException(status_code=500, detail="Failed to generate proxy QR code")
    else:
        qr_payload = core.get_client_config(client_id)
        if not qr_payload:
            raise HTTPException(status_code=500, detail="Failed to generate config")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)

    return Response(
        content=bio.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=" + _safe_filename(client.name) + "-qr.png"},
    )


@router.put("/clients/{client_id}/limits")
async def update_client_limits(
    client_id: int,
    data: UpdateLimitsRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_service_token),
):
    """Update bandwidth/traffic/expiry limits on a WG client"""
    from datetime import datetime, timezone

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if data.bandwidth_limit is not None:
        client.bandwidth_limit = data.bandwidth_limit
    if data.traffic_limit_mb is not None:
        client.traffic_limit_mb = data.traffic_limit_mb
    if data.reset_traffic:
        # Reset traffic counter: save current WG counters as new baseline so usage starts from 0
        core = ManagementCore(db)
        core.reset_traffic_counter(client_id)
    if data.expiry_date is not None:
        expiry = datetime.fromisoformat(data.expiry_date)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        client.expiry_date = expiry

    # enabled/status: route through ClientManager so WG peer state is kept in sync
    if data.enabled is not None:
        db.commit()  # flush limit changes first so enable_client sees fresh state
        core = ManagementCore(db)
        if data.enabled:
            try:
                core.clients.enable_client(client_id)
            except Exception as e:
                from loguru import logger
                logger.warning(f"internal update_client_limits: enable_client failed for {client_id}: {e}")
                client.enabled = True
                if data.status is not None:
                    client.status = data.status
                db.commit()
            return {"status": "ok", "client_id": client_id}
        else:
            try:
                core.clients.disable_client(client_id)
            except Exception as e:
                from loguru import logger
                logger.warning(f"internal update_client_limits: disable_client failed for {client_id}: {e}")
                client.enabled = False
                if data.status is not None:
                    client.status = data.status
                db.commit()
            return {"status": "ok", "client_id": client_id}

    if data.status is not None:
        client.status = data.status

    db.commit()
    return {"status": "ok", "client_id": client_id}


@router.delete("/clients/{client_id}")
async def delete_client_internal(
    client_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_service_token),
):
    """Delete a WireGuard client via internal API"""
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not core.delete_client(client_id):
        raise HTTPException(status_code=500, detail="Failed to delete client")

    return {"status": "ok", "message": f"Client '{client.name}' deleted"}


@router.get("/servers/default", response_model=DefaultServerResponse)
async def get_default_server(
    db: Session = Depends(get_db),
    _: str = Depends(verify_service_token),
):
    """Get the default server for auto-creating clients"""
    core = ManagementCore(db)
    server = core.servers.get_default_server()
    if not server:
        raise HTTPException(status_code=404, detail="No servers configured")

    return DefaultServerResponse(id=server.id, name=server.name)
