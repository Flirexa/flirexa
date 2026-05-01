"""
VPN Management Studio API - Client Routes
CRUD operations for WireGuard clients
"""

from typing import Optional, List, Dict
from datetime import datetime, timezone
import re
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import io
import qrcode
import httpx
from loguru import logger

from ...database.connection import get_db
from ...database.models import Client, Server, ClientStatus
from ...core.management import ManagementCore


router = APIRouter()


def _safe_filename(name: str) -> str:
    """Sanitize name for Content-Disposition header (ASCII-safe)."""
    return re.sub(r'[^a-zA-Z0-9_\-.]', '_', name) or "client"


# ============================================================================
# SCHEMAS
# ============================================================================

class ClientCreate(BaseModel):
    """Schema for creating a new client"""
    name: str = Field(..., min_length=1, max_length=100, description="Client name")
    server_id: Optional[int] = Field(None, description="Server ID (uses default if not specified)")
    bandwidth_limit: Optional[int] = Field(None, ge=0, description="Speed limit in Mbps")
    traffic_limit_mb: Optional[int] = Field(None, ge=0, description="Traffic limit in MB")
    expiry_days: Optional[int] = Field(None, ge=0, description="Days until expiry")
    peer_visibility: bool = Field(False, description="Allow same-user devices to see each other's VPN IP")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "MyPhone",
                "bandwidth_limit": 50,
                "traffic_limit_mb": 10240,
                "expiry_days": 30
            }
        }


class ClientUpdate(BaseModel):
    """Schema for updating a client"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    bandwidth_limit: Optional[int] = Field(None, ge=0)
    traffic_limit_mb: Optional[int] = Field(None, ge=0)


class ClientResponse(BaseModel):
    """Schema for client response"""
    id: int
    name: str
    ipv4: Optional[str] = None   # None for proxy clients
    ipv6: Optional[str] = None
    enabled: bool
    status: str
    server_id: int
    bandwidth_limit: Optional[int]
    traffic_limit_mb: Optional[int]
    traffic_used_rx: int = 0
    traffic_used_tx: int = 0
    expiry_date: Optional[datetime]
    created_at: datetime
    last_handshake: Optional[datetime] = None
    # Proxy fields (populated for hysteria2/tuic clients)
    proxy_uuid: Optional[str] = None
    is_proxy_client: bool = False

    class Config:
        from_attributes = True


class ClientDetailResponse(BaseModel):
    """Detailed client response with traffic and expiry info"""
    id: int
    name: str
    ipv4: Optional[str] = None   # None for proxy clients (no VPN IP)
    ipv6: Optional[str] = None
    enabled: bool
    status: str
    server_id: int
    server_name: Optional[str]
    bandwidth_limit: Optional[int]
    traffic: dict
    expiry: Optional[dict]
    last_handshake: Optional[str]
    created_at: Optional[str]


class TrafficLimitRequest(BaseModel):
    """Request for setting traffic limit"""
    limit_mb: int = Field(..., ge=0, description="Traffic limit in MB (0 to remove)")
    duration_days: int = Field(0, ge=0, description="Days until limit expires")
    sync_with_expiry: bool = Field(False, description="Sync with client expiry date")


class BandwidthRequest(BaseModel):
    """Request for setting bandwidth limit"""
    limit_mbps: int = Field(..., ge=0, description="Speed limit in Mbps (0 to remove)")


class ExpiryRequest(BaseModel):
    """Request for setting expiry"""
    days: int = Field(..., ge=0, description="Days until expiry (0 to remove)")
    extend: bool = Field(False, description="Extend from current expiry")


def _enrich_handshakes(clients: list, db: Session):
    """Fetch live WG handshake timestamps and inject into client objects."""
    servers = db.query(Server).filter(Server.is_active == True).all()  # noqa

    # Build pubkey → handshake_timestamp map
    hs_map = {}
    for server in servers:
        server_type = getattr(server, 'server_type', 'wireguard') or 'wireguard'
        is_proxy = getattr(server, 'server_category', 'vpn') == 'proxy' or server_type in ('hysteria2', 'tuic')
        if is_proxy:
            continue

        peers = []
        try:
            if server.ssh_host:
                from ...core.remote_adapter import RemoteServerAdapter
                adapter = RemoteServerAdapter(
                    server=server,
                    interface=server.interface,
                    config_path=server.config_path,
                )
                try:
                    peers = adapter.get_all_peers()
                finally:
                    adapter.close()
            elif server_type == 'amneziawg':
                from ...core.amneziawg import AmneziaWGManager
                mgr = AmneziaWGManager(interface=server.interface, config_path=server.config_path)
                peers = mgr.get_all_peers()
            else:
                from ...core.wireguard import WireGuardManager
                mgr = WireGuardManager(interface=server.interface, config_path=server.config_path)
                peers = mgr.get_all_peers()
        except Exception as e:
            logger.debug(f"Handshake fetch failed for server {server.name}: {e}")

        for peer in peers:
            hs = getattr(peer, 'latest_handshake', None)
            if hs and isinstance(hs, (int, float)) and hs > 0:
                hs_map[peer.public_key] = datetime.fromtimestamp(hs, tz=timezone.utc)
            elif hs and isinstance(hs, datetime):
                hs_map[peer.public_key] = hs if hs.tzinfo else hs.replace(tzinfo=timezone.utc)

    # Inject into client objects (transient, not saved to DB)
    for client in clients:
        hs = hs_map.get(client.public_key)
        if hs:
            client.last_handshake = hs


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("")
async def list_clients(
    server_id: Optional[int] = Query(None, description="Filter by server ID"),
    enabled_only: bool = Query(False, description="Only show enabled clients"),
    limit: int = Query(500, ge=1, le=500, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: Session = Depends(get_db)
):
    """
    Get list of all clients with pagination

    - **server_id**: Optional filter by server
    - **enabled_only**: Only return enabled clients
    - **limit**: Max items per page (1-500, default 50)
    - **offset**: Items to skip (default 0)
    """
    query = db.query(Client)

    if server_id is not None:
        query = query.filter(Client.server_id == server_id)

    if enabled_only:
        query = query.filter(Client.enabled == True)

    total = query.count()
    clients = query.order_by(Client.name).offset(offset).limit(limit).all()

    # Enrich with live WireGuard handshake data
    try:
        _enrich_handshakes(clients, db)
    except Exception as e:
        logger.warning(f"Failed to enrich handshakes: {e}")

    return {"total": total, "limit": limit, "offset": offset, "items": clients}


# ============================================================================
# MAP DATA (GeoIP) — must be before /{client_id} routes
# ============================================================================

_geo_cache: Dict[str, dict] = {}
_GEO_CACHE_TTL = 3600  # 1 hour


def _get_cached_geo(ip: str) -> Optional[dict]:
    entry = _geo_cache.get(ip)
    if entry and (time.time() - entry.get("_ts", 0)) < _GEO_CACHE_TTL:
        return entry
    return None


async def _batch_geoip(ips: List[str]) -> Dict[str, dict]:
    # Prevent unbounded cache growth
    if len(_geo_cache) > 10000:
        _geo_cache.clear()

    uncached = [ip for ip in ips if not _get_cached_geo(ip)]
    if uncached:
        batch_payload = [
            {"query": ip, "fields": "status,country,countryCode,city,lat,lon,query"}
            for ip in uncached[:100]
        ]
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.post(
                    "http://ip-api.com/batch?fields=status,country,countryCode,city,lat,lon,query",
                    json=batch_payload
                )
                if resp.status_code == 200:
                    for item in resp.json():
                        if item.get("status") == "success":
                            ip = item["query"]
                            _geo_cache[ip] = {
                                "lat": item["lat"],
                                "lon": item["lon"],
                                "country": item["country"],
                                "country_code": item.get("countryCode", ""),
                                "city": item.get("city", ""),
                                "_ts": time.time(),
                            }
        except Exception as e:
            logger.warning(f"GeoIP batch lookup failed: {e}")

    result = {}
    for ip in ips:
        cached = _get_cached_geo(ip)
        if cached:
            result[ip] = cached
    return result


def _format_bytes_short(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


@router.get("/map-data")
async def get_map_data(db: Session = Depends(get_db)):
    """Get geolocation data for all servers and connected clients."""
    core = ManagementCore(db)
    servers = db.query(Server).all()

    server_list = []
    client_list = []
    all_ips = set()
    server_names = {}

    for server in servers:
        server_ip = server.endpoint.split(":")[0] if server.endpoint else None
        if server_ip:
            all_ips.add(server_ip)
            server_names[server.id] = {"name": server.name, "ip": server_ip}

        # Proxy servers (Hysteria2, TUIC) have no WireGuard peers — skip peer fetch
        _is_proxy = getattr(server, 'server_category', 'vpn') == 'proxy' or \
                    getattr(server, 'server_type', 'wireguard') in ('hysteria2', 'tuic')
        peers = []
        if not _is_proxy:
            try:
                if server.ssh_host:
                    from ...core.remote_adapter import RemoteServerAdapter
                    adapter = RemoteServerAdapter(
                        server=server,
                        interface=server.interface,
                        config_path=server.config_path
                    )
                    try:
                        peers = adapter.get_all_peers()
                    finally:
                        adapter.close()
                elif getattr(server, 'server_type', 'wireguard') == 'amneziawg':
                    from ...core.amneziawg import AmneziaWGManager
                    wg = AmneziaWGManager(interface=server.interface, config_path=server.config_path)
                    peers = wg.get_all_peers()
                else:
                    from ...core.wireguard import WireGuardManager
                    wg = WireGuardManager(interface=server.interface, config_path=server.config_path)
                    peers = wg.get_all_peers()
            except Exception as e:
                logger.warning(f"Failed to get peers for server {server.name}: {e}")
                peers = []

        peer_endpoints = {}
        for peer in peers:
            endpoint = getattr(peer, "endpoint", None)
            if endpoint and endpoint != "(none)":
                peer_ip = endpoint.rsplit(":", 1)[0] if ":" in endpoint else endpoint
                peer_endpoints[peer.public_key] = {
                    "ip": peer_ip,
                    "handshake": getattr(peer, "latest_handshake", None),
                }
                all_ips.add(peer_ip)

        clients = db.query(Client).filter(Client.server_id == server.id).all()
        for client in clients:
            peer_data = peer_endpoints.get(client.public_key)
            if peer_data:
                hs = peer_data.get("handshake")
                is_active = False
                hs_iso = None
                if hs:
                    if isinstance(hs, (int, float)) and hs > 0:
                        hs_dt = datetime.fromtimestamp(hs, tz=timezone.utc)
                        is_active = (datetime.now(timezone.utc) - hs_dt).total_seconds() < 180
                        hs_iso = hs_dt.isoformat()
                    elif isinstance(hs, datetime):
                        hs_tz = hs.replace(tzinfo=timezone.utc) if hs.tzinfo is None else hs
                        is_active = (datetime.now(timezone.utc) - hs_tz).total_seconds() < 180
                        hs_iso = hs.isoformat()

                traffic_total = (client.traffic_used_rx or 0) + (client.traffic_used_tx or 0)
                client_list.append({
                    "name": client.name,
                    "server": server.name,
                    "ip": peer_data["ip"],
                    "traffic_total": traffic_total,
                    "traffic_formatted": _format_bytes_short(traffic_total),
                    "last_handshake": hs_iso,
                    "active": is_active,
                })

    geo_data = await _batch_geoip(list(all_ips))

    for server in servers:
        info = server_names.get(server.id)
        if not info:
            continue
        geo = geo_data.get(info["ip"], {})
        client_count = sum(1 for c in client_list if c.get("server") == server.name)
        server_list.append({
            "name": server.name,
            "ip": info["ip"],
            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "country": geo.get("country", ""),
            "city": geo.get("city", ""),
            "clients_count": client_count,
        })

    for client in client_list:
        geo = geo_data.get(client["ip"], {})
        client["lat"] = geo.get("lat")
        client["lon"] = geo.get("lon")
        client["country"] = geo.get("country", "")
        client["city"] = geo.get("city", "")

    client_list = [c for c in client_list if c.get("lat") is not None]

    return {"servers": server_list, "clients": client_list}


# ============================================================================
# CLIENT CRUD
# ============================================================================

@router.post("", response_model=ClientDetailResponse, status_code=201)
async def create_client(
    client_data: ClientCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new WireGuard client

    Returns the created client with full details including config
    """
    # License enforcement: check client limit.
    # Advisory lock ensures only one transaction passes the check-then-act at a time,
    # preventing a race condition where two concurrent requests both see count=N and
    # both create a client, exceeding the license limit.
    try:
        from sqlalchemy import text as _sql_text
        from ...modules.license.manager import get_license_manager
        try:
            db.execute(_sql_text("SELECT pg_advisory_xact_lock(1000001)"))
        except Exception:
            pass  # SQLite in tests / non-PG engines — skip advisory lock
        mgr = get_license_manager()
        info = mgr.get_license_info()
        current_count = db.query(Client).count()
        if not info.can_add_client(current_count):
            raise HTTPException(
                status_code=403,
                detail=f"License limit reached: {current_count}/{info.max_clients} clients. Upgrade your license."
            )
    except HTTPException:
        raise
    except Exception as _lic_err:
        from loguru import logger
        logger.error(f"License check failed during client creation: {_lic_err}")
        raise HTTPException(status_code=503, detail="License verification unavailable")

    core = ManagementCore(db)

    # Check if name already exists
    if core.clients.client_exists(client_data.name, client_data.server_id):
        raise HTTPException(
            status_code=400,
            detail=f"Client '{client_data.name}' already exists"
        )

    # Enforce server-level peer_visibility support
    if client_data.peer_visibility:
        resolved_server_id = client_data.server_id
        if resolved_server_id is None:
            default_srv = core.servers.get_default_server()
            if default_srv:
                resolved_server_id = default_srv.id
        if resolved_server_id is not None:
            srv = db.query(Server).filter(Server.id == resolved_server_id).first()
            if srv and not getattr(srv, 'supports_peer_visibility', True):
                raise HTTPException(
                    status_code=400,
                    detail=f"Server '{srv.name}' does not support peer visibility. "
                           f"Disable peer_visibility or choose a different server."
                )

    client = core.create_client(
        name=client_data.name,
        server_id=client_data.server_id,
        bandwidth_limit=client_data.bandwidth_limit,
        traffic_limit_mb=client_data.traffic_limit_mb,
        expiry_days=client_data.expiry_days,
        peer_visibility=client_data.peer_visibility,
    )

    if not client:
        raise HTTPException(
            status_code=500,
            detail="Failed to create client"
        )

    return core.get_client_full_info(client.id)


@router.get("/{client_id}", response_model=ClientDetailResponse)
async def get_client(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific client
    """
    core = ManagementCore(db)
    info = core.get_client_full_info(client_id)

    if not info:
        raise HTTPException(status_code=404, detail="Client not found")

    return info


@router.put("/{client_id}", response_model=ClientDetailResponse)
async def update_client(
    client_id: int,
    client_data: ClientUpdate,
    db: Session = Depends(get_db)
):
    """
    Update client properties
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    update_data = client_data.model_dump(exclude_unset=True)

    if update_data:
        core.clients.update_client(client_id, **update_data)

    return core.get_client_full_info(client_id)


@router.get("/{client_id}/delete-preview")
async def delete_client_preview(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Preview what will happen when deleting a client.
    Shows connected portal user, subscription status, traffic data.
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Check if client is linked to a portal user
    portal_info = None
    try:
        from ...modules.subscription.subscription_models import ClientUser
        portal_user = db.query(ClientUser).filter(
            ClientUser.id.in_(
                db.query(ClientUser.id).filter(
                    ClientUser.wireguard_clients.any(id=client_id)
                )
            )
        ).first()
        if portal_user:
            portal_info = {"username": portal_user.username, "user_id": portal_user.id}
    except Exception:
        pass

    return {
        "client_name": client.name,
        "client_id": client_id,
        "server_name": client.server.name if client.server else None,
        "enabled": client.enabled,
        "ipv4": client.ipv4,
        "has_portal_user": portal_info is not None,
        "portal_user": portal_info,
        "warning": f"This will permanently delete client '{client.name}' and remove the WireGuard peer.",
    }


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a client
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not core.delete_client(client_id):
        raise HTTPException(status_code=500, detail="Failed to delete client")

    return {"message": f"Client '{client.name}' deleted successfully"}


@router.post("/{client_id}/enable")
async def enable_client(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Enable a disabled client
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not core.enable_client(client_id):
        raise HTTPException(status_code=500, detail="Failed to enable client")

    return {"message": f"Client '{client.name}' enabled", "enabled": True}


@router.post("/{client_id}/disable")
async def disable_client(
    client_id: int,
    reason: Optional[str] = Query(None, description="Reason for disabling"),
    db: Session = Depends(get_db)
):
    """
    Disable a client
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not core.disable_client(client_id, reason):
        raise HTTPException(status_code=500, detail="Failed to disable client")

    return {"message": f"Client '{client.name}' disabled", "enabled": False}


@router.post("/{client_id}/reset-traffic")
async def reset_client_traffic(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Reset traffic counter for a client
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not core.reset_traffic_counter(client_id):
        raise HTTPException(status_code=500, detail="Failed to reset traffic")

    return {"message": f"Traffic counter reset for '{client.name}'"}


@router.get("/{client_id}/stats")
async def get_client_stats(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Get traffic and connection statistics for a client
    """
    core = ManagementCore(db)
    info = core.get_client_full_info(client_id)

    if not info:
        raise HTTPException(status_code=404, detail="Client not found")

    return {
        "client_id": client_id,
        "name": info["name"],
        "traffic": info["traffic"],
        "expiry": info["expiry"],
        "last_handshake": info["last_handshake"],
    }


@router.get("/{client_id}/config")
async def get_client_config(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Get client configuration file content (WireGuard / AmneziaWG / proxy URI+config)
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    server = client.server
    server_type = getattr(server, 'server_type', 'wireguard') if server else 'wireguard'
    server_category = getattr(server, 'server_category', 'vpn') if server else 'vpn'

    # Proxy clients: return rich dict with URI + config
    if server_category == 'proxy' or server_type in ('hysteria2', 'tuic'):
        access = core.clients.get_proxy_client_access(client_id)
        if not access:
            raise HTTPException(status_code=500, detail="Failed to generate proxy config")
        return {
            "protocol": server_type,
            "category": "proxy",
            "uri": access.get("uri"),
            "config": access.get("config"),
            "config_text": access.get("config_yaml") or access.get("config_json"),
        }

    config = core.get_client_config(client_id)
    if not config:
        raise HTTPException(status_code=500, detail="Failed to generate config")

    return {"config": config, "protocol": server_type, "category": "vpn"}


@router.get("/{client_id}/config/download")
async def download_client_config(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Download configuration file.
    - WireGuard / AmneziaWG → .conf file
    - Proxy (Hysteria2 / TUIC) → JSON/YAML config file
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    server = client.server
    server_type = getattr(server, 'server_type', 'wireguard') if server else 'wireguard'
    server_category = getattr(server, 'server_category', 'vpn') if server else 'vpn'

    if server_category == 'proxy' or server_type in ('hysteria2', 'tuic'):
        access = core.clients.get_proxy_client_access(client_id)
        if not access:
            raise HTTPException(status_code=500, detail="Failed to generate proxy config")
        # Return the text config (YAML for Hysteria2, JSON for TUIC)
        config_text = access.get("config_yaml") or access.get("config_json") or ""
        ext = "yaml" if server_type == "hysteria2" else "json"
        return Response(
            content=config_text,
            media_type="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=" + _safe_filename(client.name) + f".{ext}"
            }
        )

    config = core.get_client_config(client_id)
    if not config:
        raise HTTPException(status_code=500, detail="Failed to generate config")

    return Response(
        content=config,
        media_type="text/plain",
        headers={
            "Content-Disposition": "attachment; filename=" + _safe_filename(client.name) + ".conf"
        }
    )


@router.get("/{client_id}/qrcode")
async def get_client_qrcode(
    client_id: int,
    format: str = "conf",
    db: Session = Depends(get_db),
):
    """
    QR code image for a client configuration.

    Formats:
    - `format=conf` (default) — plain `[Interface]/[Peer]` text. Imports into
      WireGuard, AmneziaWG (the lite app), and AmneziaVPN's "Import as
      WireGuard config" flow.
    - `format=amneziavpn` — `vpn://<qCompress(JSON)>` share URL accepted by
      AmneziaVPN's "Scan QR" flow. Required for AmneziaWG servers when the
      user is on the full AmneziaVPN app.
    - Proxy servers (Hysteria2/TUIC) ignore this parameter and always return
      their protocol URI.
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    server = client.server
    server_type = getattr(server, 'server_type', 'wireguard') if server else 'wireguard'
    server_category = getattr(server, 'server_category', 'vpn') if server else 'vpn'

    if server_category == 'proxy' or server_type in ('hysteria2', 'tuic'):
        access = core.clients.get_proxy_client_access(client_id)
        if not access or not access.get("uri"):
            raise HTTPException(status_code=500, detail="Failed to generate proxy URI")
        qr_data = access["uri"]
    elif server_type == 'amneziawg' and format == 'amneziavpn':
        qr_data = core.clients.get_amneziavpn_share_url(client_id)
        if not qr_data:
            raise HTTPException(status_code=500, detail="Failed to generate AmneziaVPN share URL")
    else:
        qr_data = core.get_client_config(client_id)
        if not qr_data:
            raise HTTPException(status_code=500, detail="Failed to generate config")

    # Generate QR code
    qr = qrcode.QRCode(
        # version=None lets the library auto-pick a QR version big enough
        # for the payload. version=1 fits ~25 chars at L correction —
        # AmneziaVPN share URLs and even plain wg-quick configs are larger.
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)

    return Response(
        content=bio.getvalue(),
        media_type="image/png",
        headers={
            "Content-Disposition": "inline; filename=" + _safe_filename(client.name) + "-qr.png"
        }
    )


@router.post("/{client_id}/traffic-limit")
async def set_traffic_limit(
    client_id: int,
    request: TrafficLimitRequest,
    db: Session = Depends(get_db)
):
    """
    Set traffic limit for a client
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if client.is_proxy_client:
        raise HTTPException(status_code=400, detail="Traffic limits are not supported for proxy clients")

    if not core.set_traffic_limit(
        client_id,
        request.limit_mb,
        request.duration_days,
        request.sync_with_expiry
    ):
        raise HTTPException(status_code=500, detail="Failed to set traffic limit")

    return {
        "message": f"Traffic limit set for '{client.name}'",
        "limit_mb": request.limit_mb if request.limit_mb > 0 else None
    }


@router.post("/{client_id}/bandwidth-limit")
async def set_bandwidth_limit(
    client_id: int,
    request: BandwidthRequest,
    db: Session = Depends(get_db)
):
    """
    Set bandwidth (speed) limit for a client
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if client.is_proxy_client:
        raise HTTPException(status_code=400, detail="Bandwidth limits are not supported for proxy clients")

    if not core.set_bandwidth_limit(client_id, request.limit_mbps):
        raise HTTPException(status_code=500, detail="Failed to set bandwidth limit")

    return {
        "message": f"Bandwidth limit set for '{client.name}'",
        "bandwidth_mbps": request.limit_mbps if request.limit_mbps > 0 else None
    }


@router.post("/{client_id}/expiry")
async def set_client_expiry(
    client_id: int,
    request: ExpiryRequest,
    db: Session = Depends(get_db)
):
    """
    Set expiry timer for a client
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if request.extend:
        success = core.extend_expiry(client_id, request.days)
    else:
        success = core.set_expiry(client_id, request.days)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to set expiry")

    expiry_info = core.get_expiry_info(client_id)

    return {
        "message": f"Expiry set for '{client.name}'",
        "expiry": expiry_info
    }


@router.get("/{client_id}/peer-devices")
async def get_peer_devices(
    client_id: int,
    db: Session = Depends(get_db)
):
    """
    Get other devices belonging to the same Telegram user as this client.
    Used for peer_visibility feature — shows user's own VPN IPs across devices.
    Returns an empty list if client has no telegram_user_id.
    """
    core = ManagementCore(db)
    client = core.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    devices = core.clients.get_peer_devices(client_id)
    return {
        "client_id": client_id,
        "peer_visibility": getattr(client, 'peer_visibility', False),
        "devices": devices,
        "count": len(devices),
    }
