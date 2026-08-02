"""Read-only integrity audit for per-server VPN client addresses.

Cross-server address reuse is valid because each WireGuard interface has its
own namespace. Only collisions and metadata drift *within the same server* are
reported. Repair is intentionally not automatic: changing an address also
requires replacing the customer's live peer/config, so silent DB rewrites
would create a larger outage than the anomaly they try to fix.
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.database.models import Client, Server


def audit_server_client_addresses(
    db: Session,
    server_id: int,
    address_pool: Optional[str] = None,
) -> Dict[str, Any]:
    server = db.query(Server).filter(Server.id == server_id).first()
    pool_text = address_pool or (server.address_pool_ipv4 if server else None)
    issues: List[Dict[str, Any]] = []

    try:
        network = ipaddress.IPv4Network(pool_text or "", strict=False)
    except ValueError:
        network = None
        issues.append({"code": "invalid_pool", "value": pool_text})

    rows = (
        db.query(Client.id, Client.name, Client.ip_index, Client.ipv4)
        .filter(Client.server_id == server_id)
        .order_by(Client.id)
        .all()
    )
    by_ipv4: Dict[str, List[int]] = defaultdict(list)
    by_index: Dict[int, List[int]] = defaultdict(list)

    for row in rows:
        if row.ip_index is not None:
            by_index[int(row.ip_index)].append(row.id)

        raw = (row.ipv4 or "").split("/", 1)[0].strip()
        if not raw:
            issues.append({"code": "missing_ipv4", "client_ids": [row.id]})
            continue
        try:
            addr = ipaddress.IPv4Address(raw)
        except ipaddress.AddressValueError:
            issues.append({"code": "invalid_ipv4", "client_ids": [row.id], "value": row.ipv4})
            continue

        canonical = str(addr)
        by_ipv4[canonical].append(row.id)
        if network is not None:
            if addr not in network:
                issues.append({"code": "ipv4_outside_pool", "client_ids": [row.id], "value": canonical})
            else:
                expected = int(addr) - int(network.network_address)
                if row.ip_index != expected:
                    issues.append({
                        "code": "ip_index_mismatch",
                        "client_ids": [row.id],
                        "ipv4": canonical,
                        "stored": row.ip_index,
                        "expected": expected,
                    })

    for ipv4, client_ids in by_ipv4.items():
        if len(client_ids) > 1:
            issues.append({"code": "duplicate_ipv4", "ipv4": ipv4, "client_ids": client_ids})
    for ip_index, client_ids in by_index.items():
        if len(client_ids) > 1:
            issues.append({"code": "duplicate_ip_index", "ip_index": ip_index, "client_ids": client_ids})

    return {
        "server_id": server_id,
        "server_name": (server.display_name or server.name) if server else None,
        "address_pool_ipv4": pool_text,
        "clients_checked": len(rows),
        "healthy": not issues,
        "issues": issues,
    }


def audit_all_client_addresses(db: Session, server_id: Optional[int] = None) -> Dict[str, Any]:
    query = db.query(Server).filter(Server.server_category != "proxy")
    if server_id is not None:
        query = query.filter(Server.id == server_id)
    reports = [audit_server_client_addresses(db, server.id) for server in query.order_by(Server.id).all()]
    issue_count = sum(len(report["issues"]) for report in reports)
    return {
        "success": issue_count == 0,
        "action": "clients_audit_addresses",
        "servers_checked": len(reports),
        "clients_checked": sum(report["clients_checked"] for report in reports),
        "issue_count": issue_count,
        "servers": reports,
    }
