"""
Corporate site-to-site WireGuard VPN — API routes.

portal_router  →  /client-portal/corporate/...   (portal JWT auth)
admin_router   →  /api/v1/corporate/...           (admin JWT auth)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.modules.corporate.manager import CorporateManager
from src.modules.corporate.models import CorporateNetwork, CorporateNetworkSite
from src.api.routes.client_portal import get_current_user
from src.api.middleware.auth import get_current_admin
from src.api.middleware.license_gate import require_license_feature

logger = logging.getLogger(__name__)

# Corporate VPN is an Enterprise-tier feature. Both portal and admin routers
# are gated at the router level so any new endpoint inherits the check.
_corporate_gate = Depends(require_license_feature("corporate_vpn"))

portal_router = APIRouter(dependencies=[_corporate_gate])
admin_router = APIRouter(dependencies=[_corporate_gate])


# ── Pydantic request schemas ──────────────────────────────────────────────────

class CreateNetworkRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class CreateSiteRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="Auto-generated if omitted")
    local_subnets: Optional[List[str]] = Field(None, description="CIDR list, e.g. ['192.168.1.0/24']")
    endpoint: Optional[str] = Field(None, description="Public endpoint, e.g. '1.2.3.4:51820'")
    listen_port: Optional[int] = Field(None, ge=1, le=65535, description="Auto-assigned if omitted")
    is_relay: bool = Field(False, description="Designate this site as a relay/hub node")
    routing_mode: str = Field("auto", description="auto | direct | via_relay")


class UpdateSiteRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    local_subnets: Optional[List[str]] = None
    endpoint: Optional[str] = None
    listen_port: Optional[int] = Field(None, ge=1, le=65535)
    is_relay: Optional[bool] = None
    routing_mode: Optional[str] = Field(None, description="auto | direct | via_relay")


class SetRelayRequest(BaseModel):
    is_relay: bool


class AdminUpdateNetworkRequest(BaseModel):
    status: Optional[str] = Field(None, description="active | suspended | expired")
    notes: Optional[str] = None


class AdminUpdateSiteRequest(BaseModel):
    status: Optional[str] = Field(None, description="active | disabled")


# ── Response serialisers ───────────────────────────────────────────────────────

def _site_out(site: CorporateNetworkSite) -> dict:
    return {
        "id": site.id,
        "name": site.name,
        "public_key": site.public_key,
        "vpn_ip": site.vpn_ip,
        "local_subnets": site.get_local_subnets(),
        "endpoint": site.endpoint,
        "listen_port": site.listen_port,
        "suggested_interface": f"wg-corp-{site.id:02d}",
        "status": site.status,
        "is_relay": getattr(site, "is_relay", False),
        "routing_mode": getattr(site, "routing_mode", "auto") or "auto",
        "config_downloaded_at": (
            site.config_downloaded_at.isoformat() if site.config_downloaded_at else None
        ),
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
    }


def _network_out(
    network: CorporateNetwork,
    include_sites: bool = True,
    include_health: bool = False,
) -> dict:
    from src.modules.corporate import diagnostics as _diag
    active_sites = [s for s in network.sites if s.status == "active"]
    d = {
        "id": network.id,
        "name": network.name,
        "vpn_subnet": network.vpn_subnet,
        "status": network.status,
        "subscription_tier": network.subscription_tier,
        "expires_at": network.expires_at.isoformat() if network.expires_at else None,
        "notes": network.notes,
        "site_count": len(network.sites),
        "active_site_count": len(active_sites),
        "created_at": network.created_at.isoformat(),
        "updated_at": network.updated_at.isoformat(),
    }
    if include_health:
        d["health"] = _diag.quick_network_health(network)
    if include_sites:
        d["sites"] = [_site_out(s) for s in network.sites]
    return d


def _event_out(ev) -> dict:
    return {
        "id": ev.id,
        "network_id": ev.network_id,
        "site_id": ev.site_id,
        "site_name": ev.site_name,
        "event_type": ev.event_type,
        "description": ev.description,
        "severity": ev.severity,
        "created_at": ev.created_at.isoformat(),
    }


def _get_site_or_404(network: CorporateNetwork, site_id: int) -> CorporateNetworkSite:
    site = next((s for s in network.sites if s.id == site_id), None)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


# ═════════════════════════════════════════════════════════════════════════════
# CLIENT PORTAL ROUTES  (prefix: /client-portal/corporate)
# ═════════════════════════════════════════════════════════════════════════════

@portal_router.get("/networks", summary="List user's corporate VPN networks")
async def list_networks(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    networks = mgr.get_user_networks(user_id)
    return [_network_out(n, include_health=True) for n in networks]


@portal_router.post("/networks", status_code=201, summary="Create a corporate VPN network")
async def create_network(
    body: CreateNetworkRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    try:
        network = mgr.create_network(user_id=user_id, name=body.name)
        db.commit()
        db.refresh(network)
        return _network_out(network)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Network creation failed due to a concurrent request. Please try again.")


@portal_router.get("/networks/{network_id}", summary="Get network details")
async def get_network(
    network_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return _network_out(network)


@portal_router.delete("/networks/{network_id}", status_code=204, summary="Delete network and all its sites")
async def delete_network(
    network_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    mgr.delete_network(network)
    db.commit()


@portal_router.post("/networks/{network_id}/sites", status_code=201, summary="Add a site to a network")
async def add_site(
    network_id: int,
    body: CreateSiteRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    if network.status != "active":
        raise HTTPException(status_code=403, detail="Network is not active")
    try:
        site = mgr.add_site(
            network=network,
            name=body.name,
            local_subnets=body.local_subnets,
            endpoint=body.endpoint,
            listen_port=body.listen_port,
            is_relay=body.is_relay,
            routing_mode=body.routing_mode,
        )
        db.commit()
        db.refresh(site)
        return _site_out(site)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Site creation failed due to a concurrent request. Please try again.")


@portal_router.patch("/networks/{network_id}/sites/{site_id}", summary="Update site configuration")
async def update_site(
    network_id: int,
    site_id: int,
    body: UpdateSiteRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    site = _get_site_or_404(network, site_id)
    try:
        mgr.update_site(
            site,
            name=body.name,
            local_subnets=body.local_subnets,
            endpoint=body.endpoint,
            listen_port=body.listen_port,
            is_relay=body.is_relay,
            routing_mode=body.routing_mode,
        )
        db.commit()
        db.refresh(site)
        return _site_out(site)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@portal_router.get(
    "/networks/{network_id}/sites/{site_id}/config",
    response_class=PlainTextResponse,
    summary="Download WireGuard config for a site",
)
async def download_site_config(
    network_id: int,
    site_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    site = _get_site_or_404(network, site_id)

    config = mgr.generate_site_config(site)
    mgr.mark_config_downloaded(site)
    db.commit()

    net_slug = network.name.lower().replace(" ", "-")
    site_slug = site.name.lower().replace(" ", "-")
    filename = f"corp-{net_slug}-{site_slug}.conf"
    return PlainTextResponse(
        content=config,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@portal_router.post(
    "/networks/{network_id}/sites/{site_id}/regenerate-keys",
    summary="Regenerate WireGuard key pair for a site",
)
async def regenerate_site_keys(
    network_id: int,
    site_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    site = _get_site_or_404(network, site_id)

    mgr.regenerate_site_keys(site)
    db.commit()
    db.refresh(site)
    return {
        "message": "Keys regenerated successfully. Re-download configs for ALL sites in this network.",
        "public_key": site.public_key,
    }


@portal_router.delete(
    "/networks/{network_id}/sites/{site_id}",
    status_code=204,
    summary="Delete a site",
)
async def delete_site(
    network_id: int,
    site_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    site = _get_site_or_404(network, site_id)
    mgr.delete_site(site)
    db.commit()


@portal_router.get("/networks/{network_id}/health", summary="Quick network health (no DNS)")
async def get_network_health(
    network_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return mgr.get_quick_health(network)


@portal_router.get("/networks/{network_id}/diagnostics", summary="Run full network diagnostics")
async def run_diagnostics(
    network_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    result = mgr.run_full_diagnostics(network)
    db.commit()
    return result


@portal_router.get("/networks/{network_id}/relay", summary="Get relay topology for the network")
async def get_relay_topology(
    network_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return mgr.get_relay_topology(network)


@portal_router.patch(
    "/networks/{network_id}/sites/{site_id}/relay",
    summary="Set or unset relay role for a site",
)
async def set_site_relay(
    network_id: int,
    site_id: int,
    body: SetRelayRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    if network.status != "active":
        raise HTTPException(status_code=403, detail="Network is not active")
    site = _get_site_or_404(network, site_id)
    try:
        mgr.set_site_relay_status(site, body.is_relay)
        db.commit()
        db.refresh(site)
        return _site_out(site)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@portal_router.get("/networks/{network_id}/events", summary="Get network event log")
async def get_events(
    network_id: int,
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id, user_id=user_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    events = mgr.get_event_log(network_id, limit=limit)
    return [_event_out(e) for e in events]


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES  (prefix: /api/v1/corporate)
# ═════════════════════════════════════════════════════════════════════════════

@admin_router.get("/networks", summary="List all corporate VPN networks")
async def admin_list_networks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    networks = mgr.get_all_networks(skip=skip, limit=limit, status=status, user_id=user_id)
    return [_network_out(n, include_health=True) for n in networks]


@admin_router.get("/networks/{network_id}", summary="Get network details (admin)")
async def admin_get_network(
    network_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    return _network_out(network)


@admin_router.patch("/networks/{network_id}", summary="Update network status / notes")
async def admin_update_network(
    network_id: int,
    body: AdminUpdateNetworkRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")

    if body.status:
        valid = {"active", "suspended", "expired"}
        if body.status not in valid:
            raise HTTPException(status_code=400, detail=f"status must be one of: {valid}")
        mgr.set_network_status(network, body.status)

    if body.notes is not None:
        network.notes = body.notes

    db.commit()
    return _network_out(network)


@admin_router.patch("/networks/{network_id}/sites/{site_id}", summary="Update site status")
async def admin_update_site(
    network_id: int,
    site_id: int,
    body: AdminUpdateSiteRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    site = _get_site_or_404(network, site_id)

    if body.status:
        valid = {"active", "disabled"}
        if body.status not in valid:
            raise HTTPException(status_code=400, detail=f"status must be one of: {valid}")
        mgr.set_site_status(site, body.status)

    db.commit()
    return _site_out(site)


@admin_router.post(
    "/networks/{network_id}/sites/{site_id}/regenerate-keys",
    summary="Regenerate site keys (admin)",
)
async def admin_regenerate_keys(
    network_id: int,
    site_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    site = _get_site_or_404(network, site_id)
    mgr.regenerate_site_keys(site)
    db.commit()
    return {"message": "Keys regenerated", "public_key": site.public_key}


@admin_router.get(
    "/networks/{network_id}/sites/{site_id}/config",
    response_class=PlainTextResponse,
    summary="Download site config (admin)",
)
async def admin_download_config(
    network_id: int,
    site_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    site = _get_site_or_404(network, site_id)
    config = mgr.generate_site_config(site)
    net_slug = network.name.lower().replace(" ", "-")
    site_slug = site.name.lower().replace(" ", "-")
    return PlainTextResponse(
        content=config,
        headers={
            "Content-Disposition": f'attachment; filename="admin-{net_slug}-{site_slug}.conf"'
        },
    )


@admin_router.get("/networks/{network_id}/diagnostics", summary="Run full diagnostics (admin)")
async def admin_run_diagnostics(
    network_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    result = mgr.run_full_diagnostics(network)
    db.commit()
    return result


@admin_router.get("/networks/{network_id}/events", summary="Get event log (admin)")
async def admin_get_events(
    network_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin),
):
    mgr = CorporateManager(db)
    network = mgr.get_network(network_id)
    if not network:
        raise HTTPException(status_code=404, detail="Network not found")
    events = mgr.get_event_log(network_id, limit=limit)
    return [_event_out(e) for e in events]
