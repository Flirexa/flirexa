"""
prometheus-metrics — community plugin example.

Exposes runtime metrics about the Flirexa install at:

    GET /metrics            (no auth — protect with reverse proxy or firewall)

Metrics emitted (Prometheus exposition format):

    flirexa_clients_total{status="active|disabled|expired"}
    flirexa_servers_total
    flirexa_traffic_bytes_total{direction="up|down"}
    flirexa_payments_total{provider="...",status="..."}
    flirexa_uptime_seconds

Configuration (env vars):

    METRICS_AUTH_TOKEN     If set, /metrics requires `Authorization: Bearer <token>`
    METRICS_BIND           Default ":metrics" path. Override to e.g. "/internal/metrics"

This is also the **canonical reference** for community-plugin authoring. Copy
the directory to start your own; nothing in here is Flirexa-internal.
"""

from __future__ import annotations

import os
import time
from typing import Iterable

from fastapi import APIRouter, Header, HTTPException, Response

from src.modules.plugin_loader import Plugin


# ── State shared across requests ──────────────────────────────────────────────

_started_at = time.time()


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_auth(authorization: str | None) -> None:
    """If METRICS_AUTH_TOKEN is set, enforce it. Otherwise the endpoint is open
    on the assumption a reverse proxy / firewall is in front of it."""
    expected = os.getenv("METRICS_AUTH_TOKEN", "").strip()
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "metrics: missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(401, "metrics: bad token")


# ── Metric helpers ────────────────────────────────────────────────────────────

def _line(name: str, value: float, **labels: str) -> str:
    """Format a single Prometheus exposition line."""
    if labels:
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f"{name}{{{label_str}}} {value}"
    return f"{name} {value}"


def _emit_counter(name: str, help_text: str, samples: Iterable[tuple[dict, float]]) -> str:
    out = [f"# HELP {name} {help_text}", f"# TYPE {name} counter"]
    for labels, value in samples:
        out.append(_line(name, value, **labels))
    return "\n".join(out)


def _emit_gauge(name: str, help_text: str, samples: Iterable[tuple[dict, float]]) -> str:
    out = [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
    for labels, value in samples:
        out.append(_line(name, value, **labels))
    return "\n".join(out)


# ── Metric collection ────────────────────────────────────────────────────────

def _collect_clients() -> Iterable[tuple[dict, float]]:
    try:
        from src.database.connection import SessionLocal
        from src.database.models import Client, ClientStatus
        with SessionLocal() as db:
            for status in ClientStatus:
                count = db.query(Client).filter(Client.status == status).count()
                yield {"status": status.value}, float(count)
    except Exception:
        # Don't crash /metrics if the DB hiccups — emit nothing for this metric.
        return


def _collect_servers() -> float:
    try:
        from src.database.connection import SessionLocal
        from src.database.models import Server
        with SessionLocal() as db:
            return float(db.query(Server).count())
    except Exception:
        return 0.0


def _collect_traffic() -> Iterable[tuple[dict, float]]:
    try:
        from src.database.connection import SessionLocal
        from src.database.models import Client
        with SessionLocal() as db:
            up = db.query(Client).with_entities(Client.traffic_up_bytes).all()
            down = db.query(Client).with_entities(Client.traffic_down_bytes).all()
            yield {"direction": "up"}, float(sum(x[0] or 0 for x in up))
            yield {"direction": "down"}, float(sum(x[0] or 0 for x in down))
    except Exception:
        return


# ── Routes ────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics(authorization: str | None = Header(default=None)):
    _check_auth(authorization)

    blocks: list[str] = [
        _emit_gauge(
            "flirexa_uptime_seconds",
            "Seconds since the API process started.",
            [({}, time.time() - _started_at)],
        ),
        _emit_gauge(
            "flirexa_clients_total",
            "Total VPN clients by status.",
            list(_collect_clients()),
        ),
        _emit_gauge(
            "flirexa_servers_total",
            "Total VPN servers configured.",
            [({}, _collect_servers())],
        ),
        _emit_counter(
            "flirexa_traffic_bytes_total",
            "Cumulative VPN traffic in bytes by direction.",
            list(_collect_traffic()),
        ),
    ]
    body = "\n\n".join(blocks) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")


@router.get("/api/v1/plugins/prometheus-metrics/status")
async def status():
    return {
        "plugin": "prometheus-metrics",
        "version": "1.0.0",
        "active": True,
        "endpoint": "/metrics",
        "auth_enabled": bool(os.getenv("METRICS_AUTH_TOKEN", "").strip()),
    }


# ── Plugin definition ────────────────────────────────────────────────────────


class PrometheusMetricsPlugin(Plugin):
    def get_router(self):
        return router

    def on_load(self):
        from loguru import logger
        logger.info("prometheus-metrics plugin loaded — /metrics available")


_MANIFEST = {
    "name": "prometheus-metrics",
    "version": "1.0.0",
    "display_name": "Prometheus Metrics Exporter",
    "requires_license_feature": "community",
}

PLUGIN = PrometheusMetricsPlugin(_MANIFEST)
