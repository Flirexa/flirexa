"""Public, time-limited config-share endpoints (1.5.67+).

The operator generates a share link via POST /api/v1/clients/{id}/share-link
(admin-auth required). That returns a URL of the form `/share/<token>` which
the operator hands to the customer. The customer downloads the .conf with no
panel login — token validates server-side, expires after 10 minutes by
default, and records first download for audit.

This router is mounted WITHOUT admin_auth_dep so the customer-facing GET
works without a session. The middleware in `main.py` already lets non-API
paths through, so `/share/<token>` reaches us directly.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from loguru import logger

from ...database.connection import get_db
from ...database.models import Client, ClientShareToken


router = APIRouter()


def _build_config(client: Client, db: Session) -> str:
    """Reuse the existing in-tree config builder used by /clients/{id}/config.

    Importing lazily so we don't pull the whole client manager at module
    load time when only the public share path is hit.
    """
    from ...core.management import ManagementCore
    core = ManagementCore(db)
    cfg = core.get_client_config(client.id)
    if not cfg:
        raise HTTPException(status_code=500, detail="Failed to render client config")
    return cfg


@router.get("/share/{token}")
def download_shared_config(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public — no auth. Downloads the WireGuard .conf for a previously-issued
    share token. Records first-use timestamp for audit, then keeps serving
    the same file until expiry (so a customer who hits the link, briefly
    loses connectivity, and retries gets the same file rather than a 404)."""
    if not token or len(token) > 64:
        raise HTTPException(status_code=404, detail="Not found")

    row = db.query(ClientShareToken).filter(ClientShareToken.token == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="Link not found or expired")

    now = datetime.now(timezone.utc)
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now >= expires_at:
        # Don't delete the row — the operator may want to see it expired
        # in audit. Worker / next access will purge eventually.
        raise HTTPException(status_code=410, detail="Link has expired")

    client = db.query(Client).filter(Client.id == row.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client no longer exists")

    # Record first download. Subsequent hits within the TTL are still allowed
    # (idempotent within the window) but only the first IP is recorded.
    if row.used_at is None:
        row.used_at = now
        try:
            row.download_ip = (request.client.host if request.client else None) or None
        except Exception:
            pass
        try:
            db.commit()
        except Exception:
            db.rollback()

    cfg = _build_config(client, db)
    safe_name = "".join(c for c in (client.name or "client") if c.isalnum() or c in "-_")[:48] or "client"
    filename = f"{safe_name}.conf"

    logger.info(
        "Shared config downloaded: client_id={} token={}… ip={}",
        client.id, token[:8], row.download_ip or "?",
    )
    return Response(
        content=cfg,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, max-age=0",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
