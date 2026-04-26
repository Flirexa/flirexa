"""
VPN Management Studio — Business Invariant Validator

Checks that the system's runtime state is consistent with its data-layer state.
Detects "financial holes" and silent access violations before they become support tickets.

Invariants checked
------------------
INV-1  subscription.active  → client.enabled = True
INV-2  subscription.expired → client.enabled = False
INV-5  payment.completed    → subscription exists and is active
INV-6  traffic_exceeded / expired client → enabled = False
INV-7  proxy client         → bandwidth_limit = NULL (no TC support for proxy)
INV-8  bandwidth_limit in DB → TC class actually applied on server interface
INV-9  WG server drift_detected → reconcile peers (enabled↔live, ghost peers removed)
INV-10 proxy server config  → reflects DB enabled clients (TUIC users, Hy2 auth.password)
INV-11 worker heartbeat     → not stale (threshold: 15 min)

Usage
-----
    from src.modules.business_validator import BusinessValidator
    with SessionLocal() as db:
        bv = BusinessValidator(db)
        report = bv.run_all(auto_fix=True)
        if report.violations:
            logger.error(f"Business invariants violated: {len(report.violations)}")
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..database.connection import SessionLocal
from ..database.models import (
    AuditAction,
    AuditLog,
    Client,
    ClientStatus,
    Payment,
    PaymentStatus,
    Server,
    ServerStatus,
    Subscription,
    SubscriptionStatus,
    SystemConfig,
)
from ..modules.subscription.subscription_models import ClientPortalPayment, ClientPortalSubscription


# ─── result types ────────────────────────────────────────────────────────────

@dataclass
class Violation:
    invariant: str          # e.g. "INV-1"
    entity: str             # e.g. "client"
    entity_id: int
    description: str
    severity: str = "error"  # "warning" | "error" | "critical"
    fixed: bool = False


@dataclass
class ValidationReport:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    violations: List[Violation] = field(default_factory=list)
    checked: int = 0
    auto_fixed: int = 0
    errors_during_check: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len([v for v in self.violations if not v.fixed]) == 0

    def summary(self) -> str:
        elapsed = ""
        if self.finished_at:
            elapsed = f" in {(self.finished_at - self.started_at).total_seconds():.1f}s"
        fixed_note = f", auto-fixed {self.auto_fixed}" if self.auto_fixed else ""
        return (
            f"BusinessValidator: checked {self.checked} entities{elapsed} — "
            f"{len(self.violations)} violations{fixed_note}"
        )


# ─── main class ──────────────────────────────────────────────────────────────

class BusinessValidator:
    """
    Validates business invariants and optionally auto-fixes them.

    Pass auto_fix=True to repair violations automatically.
    All actions are logged to audit_logs with user_type='system'.
    """

    def __init__(self, db: Session):
        self.db = db
        self._report = ValidationReport()

    # ── public API ───────────────────────────────────────────────────────────

    def run_all(self, auto_fix: bool = False) -> ValidationReport:
        """Run every invariant check and return a consolidated report."""
        logger.info("[BV] Starting full business invariant validation (auto_fix=%s)", auto_fix)

        checks = [
            self._check_inv1_active_sub_client_enabled,
            self._check_inv2_expired_sub_client_disabled,
            self._check_inv5_payment_completed_has_active_sub,
            self._check_inv6_status_matches_enabled,
            self._check_inv7_proxy_no_bandwidth,
            self._check_financial_holes,
            self._check_inv8_bandwidth_tc_applied,
            self._check_inv9_wg_peer_exists,
            self._check_inv10_proxy_config_drift,
            self._check_inv11_worker_stale,
        ]

        for check in checks:
            try:
                check(auto_fix=auto_fix)
            except Exception as exc:
                msg = f"Check {check.__name__} raised: {exc}"
                logger.error("[BV] %s", msg)
                self._report.errors_during_check.append(msg)

        self._report.finished_at = datetime.now(timezone.utc)

        # Cache deep-check results in DB for /health/full
        try:
            self._cache_deep_check_results()
        except Exception as exc:
            logger.debug("[BV] cache_deep_check_results failed: %s", exc)

        if self._report.violations:
            logger.error(
                "[BV] %s — %d unfixed violations",
                self._report.summary(),
                len([v for v in self._report.violations if not v.fixed]),
            )
        else:
            logger.info("[BV] %s — all OK", self._report.summary())

        return self._report

    def check_after_payment(self, payment_invoice_id: str, auto_fix: bool = True) -> ValidationReport:
        """Run targeted checks after a payment completes (call from payment pipeline)."""
        logger.debug("[BV] Post-payment check for invoice %s", payment_invoice_id)
        self._check_inv5_payment_completed_has_active_sub(auto_fix=auto_fix, invoice_id=payment_invoice_id)
        self._report.finished_at = datetime.now(timezone.utc)
        return self._report

    def check_after_expiry(self, client_id: int, auto_fix: bool = True) -> ValidationReport:
        """Run targeted checks after a client expires (call from timer_manager)."""
        logger.debug("[BV] Post-expiry check for client_id=%d", client_id)
        self._check_inv2_expired_sub_client_disabled(auto_fix=auto_fix, client_id=client_id)
        self._check_inv6_status_matches_enabled(auto_fix=auto_fix, client_id=client_id)
        self._report.finished_at = datetime.now(timezone.utc)
        return self._report

    # ── INV-1: active subscription → client enabled ──────────────────────────

    def _check_inv1_active_sub_client_enabled(
        self, auto_fix: bool = False, user_id: Optional[int] = None
    ):
        """
        Every user with an active subscription must have at least one enabled client.
        """
        now = datetime.now(timezone.utc)

        q = self.db.query(ClientPortalSubscription).filter(
            ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPortalSubscription.end_date > now,
        )
        if user_id is not None:
            q = q.filter(ClientPortalSubscription.user_id == user_id)

        active_subs = q.all()
        self._report.checked += len(active_subs)

        for sub in active_subs:
            # Check if this user has any enabled client
            has_enabled = (
                self.db.query(Client)
                .join(Client.server)
                .filter(
                    Client.telegram_user_id == sub.user_id,
                    Client.enabled == True,
                )
                .first()
            )
            if has_enabled:
                continue

            # No enabled client for active subscriber
            v = Violation(
                invariant="INV-1",
                entity="subscription",
                entity_id=sub.id,
                description=(
                    f"User {sub.user_id} has active subscription (tier={sub.tier}, "
                    f"ends={sub.end_date.date()}) but no enabled WG/proxy client"
                ),
                severity="error",
            )
            self._record_violation(v)

            if auto_fix:
                fixed = self._fix_enable_client_for_user(sub.user_id, sub)
                v.fixed = fixed

    # ── INV-2: expired subscription → client disabled ────────────────────────

    def _check_inv2_expired_sub_client_disabled(
        self, auto_fix: bool = False, client_id: Optional[int] = None
    ):
        """
        Clients whose subscription has expired (or are in expired/traffic_exceeded status)
        must have enabled=False.
        """
        now = datetime.now(timezone.utc)

        q = self.db.query(Client).filter(
            Client.enabled == True,
            Client.status.in_([ClientStatus.EXPIRED, ClientStatus.TRAFFIC_EXCEEDED]),
        )
        if client_id is not None:
            q = q.filter(Client.id == client_id)

        bad_clients = q.all()
        self._report.checked += len(bad_clients)

        for client in bad_clients:
            v = Violation(
                invariant="INV-2",
                entity="client",
                entity_id=client.id,
                description=(
                    f"Client '{client.name}' (id={client.id}) has status={client.status.value} "
                    f"but enabled=True — access not revoked"
                ),
                severity="critical",
            )
            self._record_violation(v)

            if auto_fix:
                try:
                    client.enabled = False
                    self.db.commit()
                    v.fixed = True
                    self._report.auto_fixed += 1
                    logger.warning(
                        "[BV] INV-2 auto-fix: disabled client %d '%s' (status=%s)",
                        client.id, client.name, client.status.value,
                    )
                    self._audit(
                        AuditAction.CLIENT_DISABLE,
                        "client", client.id, client.name,
                        {"reason": "business_validator_inv2", "status": client.status.value},
                    )
                except Exception as exc:
                    logger.error("[BV] INV-2 auto-fix failed for client %d: %s", client.id, exc)

        # Also check clients with expired expiry_date but still enabled
        q2 = self.db.query(Client).filter(
            Client.enabled == True,
            Client.expiry_date.isnot(None),
            Client.expiry_date < now,
        )
        if client_id is not None:
            q2 = q2.filter(Client.id == client_id)

        for client in q2.all():
            self._report.checked += 1
            v = Violation(
                invariant="INV-2",
                entity="client",
                entity_id=client.id,
                description=(
                    f"Client '{client.name}' (id={client.id}) expiry_date={client.expiry_date} "
                    f"is in the past but enabled=True"
                ),
                severity="critical",
            )
            self._record_violation(v)

            if auto_fix:
                try:
                    client.enabled = False
                    client.status = ClientStatus.EXPIRED
                    self.db.commit()
                    v.fixed = True
                    self._report.auto_fixed += 1
                    logger.warning(
                        "[BV] INV-2 auto-fix: expired client %d '%s'", client.id, client.name
                    )
                    self._audit(
                        AuditAction.CLIENT_DISABLE,
                        "client", client.id, client.name,
                        {"reason": "business_validator_expired_date"},
                    )
                except Exception as exc:
                    logger.error("[BV] INV-2 auto-fix failed for client %d: %s", client.id, exc)

    # ── INV-5: completed payment → active subscription ───────────────────────

    def _check_inv5_payment_completed_has_active_sub(
        self, auto_fix: bool = False, invoice_id: Optional[str] = None
    ):
        """
        Every completed payment must link to an active subscription.
        If not, flag as inconsistent and log CRITICAL.
        """
        q = self.db.query(ClientPortalPayment).filter(
            ClientPortalPayment.status == "completed"
        )
        if invoice_id is not None:
            q = q.filter(ClientPortalPayment.invoice_id == invoice_id)
        else:
            # Limit scan to recent payments to avoid scanning all history
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            q = q.filter(ClientPortalPayment.completed_at >= cutoff)

        payments = q.all()
        self._report.checked += len(payments)

        for payment in payments:
            # Find linked subscription for this user
            active_sub = (
                self.db.query(ClientPortalSubscription)
                .filter(
                    ClientPortalSubscription.user_id == payment.user_id,
                    ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
                )
                .first()
            )
            if active_sub:
                continue

            v = Violation(
                invariant="INV-5",
                entity="payment",
                entity_id=payment.id,
                description=(
                    f"Payment {payment.invoice_id} (user_id={payment.user_id}, "
                    f"amount=${payment.amount_usd}, completed_at={payment.completed_at}) "
                    f"is COMPLETED but user has no active subscription — POTENTIAL MONEY LOSS"
                ),
                severity="critical",
            )
            self._record_violation(v)
            logger.critical(
                "[BV] INV-5 CRITICAL: payment %s completed but no active sub for user %d",
                payment.invoice_id, payment.user_id,
            )

            if auto_fix:
                fixed = self._fix_create_sub_for_payment(payment)
                v.fixed = fixed

    # ── INV-6: status matches enabled flag ───────────────────────────────────

    def _check_inv6_status_matches_enabled(
        self, auto_fix: bool = False, client_id: Optional[int] = None
    ):
        """
        enabled=True  ↔ status must be ACTIVE or PENDING
        enabled=False ↔ status must be DISABLED / EXPIRED / TRAFFIC_EXCEEDED
        """
        good_enabled = {ClientStatus.ACTIVE, ClientStatus.PENDING}
        good_disabled = {ClientStatus.DISABLED, ClientStatus.EXPIRED, ClientStatus.TRAFFIC_EXCEEDED}

        q = self.db.query(Client)
        if client_id is not None:
            q = q.filter(Client.id == client_id)

        for client in q.all():
            self._report.checked += 1
            if client.enabled and client.status not in good_enabled:
                v = Violation(
                    invariant="INV-6",
                    entity="client",
                    entity_id=client.id,
                    description=(
                        f"Client '{client.name}': enabled=True but status={client.status.value} "
                        f"(expected: {[s.value for s in good_enabled]})"
                    ),
                    severity="error",
                )
                self._record_violation(v)
                if auto_fix:
                    try:
                        client.status = ClientStatus.ACTIVE
                        self.db.commit()
                        v.fixed = True
                        self._report.auto_fixed += 1
                    except Exception as exc:
                        logger.error("[BV] INV-6 fix failed for client %d: %s", client.id, exc)

            elif not client.enabled and client.status not in good_disabled:
                v = Violation(
                    invariant="INV-6",
                    entity="client",
                    entity_id=client.id,
                    description=(
                        f"Client '{client.name}': enabled=False but status={client.status.value} "
                        f"(expected: {[s.value for s in good_disabled]})"
                    ),
                    severity="warning",
                )
                self._record_violation(v)
                if auto_fix:
                    try:
                        client.status = ClientStatus.DISABLED
                        self.db.commit()
                        v.fixed = True
                        self._report.auto_fixed += 1
                    except Exception as exc:
                        logger.error("[BV] INV-6 fix failed for client %d: %s", client.id, exc)

    # ── INV-7: proxy clients must have no bandwidth_limit ────────────────────

    def _check_inv7_proxy_no_bandwidth(self, auto_fix: bool = False, **_):
        """
        Proxy clients cannot have bandwidth_limit set — TC is not supported for them.
        If set, clear the field and warn.
        """
        bad = (
            self.db.query(Client)
            .filter(
                Client.public_key.is_(None),
                Client.bandwidth_limit.isnot(None),
            )
            .all()
        )
        self._report.checked += len(bad)

        for client in bad:
            v = Violation(
                invariant="INV-7",
                entity="client",
                entity_id=client.id,
                description=(
                    f"Proxy client '{client.name}' has bandwidth_limit={client.bandwidth_limit} Mbps "
                    f"but TC is not supported for proxy — UI would show fake limit"
                ),
                severity="warning",
            )
            self._record_violation(v)
            if auto_fix:
                try:
                    client.bandwidth_limit = None
                    self.db.commit()
                    v.fixed = True
                    self._report.auto_fixed += 1
                    logger.warning(
                        "[BV] INV-7 auto-fix: cleared bandwidth_limit on proxy client %d '%s'",
                        client.id, client.name,
                    )
                except Exception as exc:
                    logger.error("[BV] INV-7 fix failed for client %d: %s", client.id, exc)

    # ── Financial holes ───────────────────────────────────────────────────────

    def _check_financial_holes(self, auto_fix: bool = False, **_):
        """
        Detect:
        - Users with active subscription but ALL clients disabled
        - Clients with traffic exceeded but not marked as such
        - Pending payments older than 48h (likely orphaned)
        """
        from datetime import timedelta
        now = datetime.now(timezone.utc)

        # --- Pending payments stuck > 48h
        stale_pending = (
            self.db.query(ClientPortalPayment)
            .filter(
                ClientPortalPayment.status == "pending",
                ClientPortalPayment.created_at < now - timedelta(hours=48),
            )
            .all()
        )
        self._report.checked += len(stale_pending)
        for p in stale_pending:
            v = Violation(
                invariant="FIN-1",
                entity="payment",
                entity_id=p.id,
                description=(
                    f"Payment {p.invoice_id} (user_id={p.user_id}, ${p.amount_usd}) "
                    f"has been pending for {(now - p.created_at).days}d — "
                    f"orphaned or webhook not received"
                ),
                severity="warning",
            )
            self._record_violation(v)

        # --- Clients with traffic_limit exceeded but still enabled
        over_traffic = (
            self.db.query(Client)
            .filter(
                Client.enabled == True,
                Client.traffic_limit_mb.isnot(None),
                Client.traffic_limit_mb > 0,
            )
            .all()
        )
        self._report.checked += len(over_traffic)
        for client in over_traffic:
            used_mb = (client.traffic_used_rx + client.traffic_used_tx) / (1024 * 1024)
            if used_mb > client.traffic_limit_mb:
                v = Violation(
                    invariant="FIN-2",
                    entity="client",
                    entity_id=client.id,
                    description=(
                        f"Client '{client.name}' (id={client.id}) used {used_mb:.0f} MB "
                        f"but limit is {client.traffic_limit_mb} MB — still enabled (traffic leak)"
                    ),
                    severity="critical",
                )
                self._record_violation(v)
                logger.critical(
                    "[BV] FIN-2: client %d '%s' over traffic limit (%.0f/%.0f MB) but enabled",
                    client.id, client.name, used_mb, client.traffic_limit_mb,
                )
                if auto_fix:
                    try:
                        client.enabled = False
                        client.status = ClientStatus.TRAFFIC_EXCEEDED
                        self.db.commit()
                        v.fixed = True
                        self._report.auto_fixed += 1
                        logger.warning(
                            "[BV] FIN-2 auto-fix: disabled client %d '%s'", client.id, client.name
                        )
                        self._audit(
                            AuditAction.CLIENT_DISABLE, "client", client.id, client.name,
                            {"reason": "business_validator_traffic_exceeded"},
                        )
                    except Exception as exc:
                        logger.error("[BV] FIN-2 fix failed for client %d: %s", client.id, exc)

    # ── INV-8: TC bandwidth rules actually applied ────────────────────────────

    def _check_inv8_bandwidth_tc_applied(self, auto_fix: bool = False, **_):
        """
        INV-8: client.bandwidth_limit is set in DB but the TC class is missing or
        has a wrong rate on the actual server interface.
        Checks local and SSH servers; agent servers are skipped.
        """
        from ..core.traffic_manager import TrafficManager

        servers = (
            self.db.query(Server)
            .join(Client, Client.server_id == Server.id)
            .filter(
                Client.bandwidth_limit.isnot(None),
                Client.bandwidth_limit > 0,
                Client.public_key.isnot(None),
                Client.enabled == True,
            )
            .distinct()
            .all()
        )

        for server in servers:
            if getattr(server, "server_category", None) == "proxy":
                continue
            try:
                tm = TrafficManager(self.db)
                result = tm.verify_bandwidth_applied(server.id)
            except Exception as exc:
                logger.error("[BV] INV-8 TC check failed for server %d: %s", server.id, exc)
                self._report.errors_during_check.append(f"INV-8 server {server.id}: {exc}")
                continue

            if result.get("skipped") or result.get("error"):
                continue

            for mm in result.get("mismatches", []):
                self._report.checked += 1
                v = Violation(
                    invariant="INV-8",
                    entity="client",
                    entity_id=mm["client_id"],
                    description=(
                        f"Client '{mm['name']}' (id={mm['client_id']}) "
                        f"bandwidth_limit={mm['expected_mbps']}Mbps in DB but "
                        f"TC rule is {mm.get('reason', 'missing')} on server '{server.name}'"
                    ),
                    severity="error",
                )
                self._record_violation(v)

                if auto_fix:
                    try:
                        tm.set_bandwidth_limit(mm["client_id"], mm["expected_mbps"])
                        v.fixed = True
                        self._report.auto_fixed += 1
                        logger.warning(
                            "[BV] INV-8 [AUTO-FIX] client_id=%d name='%s' action=reapply_tc mbps=%d",
                            mm["client_id"], mm["name"], mm["expected_mbps"],
                        )
                        self._audit(
                            AuditAction.SYSTEM_START, "client", mm["client_id"], mm["name"],
                            {"invariant": "INV-8", "action": "reapply_tc",
                             "mbps": mm["expected_mbps"]},
                        )
                    except Exception as exc:
                        logger.error("[BV] INV-8 auto-fix failed for client %d: %s",
                                     mm["client_id"], exc)

    # ── INV-9: WG peer presence matches DB enabled flag ───────────────────────

    def _check_inv9_wg_peer_exists(self, auto_fix: bool = False, **_):
        """
        INV-9: WG peer state on the live interface must match the DB enabled flag.
          - enabled=True but peer absent → re-add (missing peer)
          - enabled=False but peer present → remove (ghost peer / access leak)

        Delegates to state_reconciler to get live WG state for drifted servers.
        Non-drifted servers are assumed consistent (reconciler runs every 5 min).
        """
        from ..modules.state_reconciler import reconcile_server as _reconcile

        drifted_servers = (
            self.db.query(Server)
            .filter(
                Server.drift_detected == True,
                Server.lifecycle_status == "online",
            )
            .all()
        )
        vpn_drifted = [s for s in drifted_servers
                       if getattr(s, "server_category", None) != "proxy"]

        if not vpn_drifted:
            return  # reconciler keeps non-drifted servers clean

        for server in vpn_drifted:
            enabled_count = (
                self.db.query(Client)
                .filter(
                    Client.server_id == server.id,
                    Client.enabled == True,
                    Client.public_key.isnot(None),
                )
                .count()
            )
            if enabled_count == 0:
                continue

            self._report.checked += 1
            v = Violation(
                invariant="INV-9",
                entity="server",
                entity_id=server.id,
                description=(
                    f"Server '{server.name}' has drift_detected=True with "
                    f"{enabled_count} enabled WG client(s) — peer state may not match DB. "
                    f"Details: {server.drift_details or 'unknown'}"
                ),
                severity="error",
            )
            self._record_violation(v)

            if auto_fix:
                try:
                    result = _reconcile(server, self.db)
                    self.db.commit()
                    reconciled = result.get("reconciled", [])
                    ghost_removed = [r for r in reconciled if r.startswith("GHOST_REMOVED:")]
                    re_added = [r for r in reconciled if not r.startswith("GHOST_REMOVED:")]
                    if not result.get("drift_detected") or reconciled:
                        v.fixed = True
                        self._report.auto_fixed += 1
                    for action in ghost_removed:
                        logger.warning(
                            "[BV] INV-9 [AUTO-FIX] server=%s action=remove_ghost_peer peer=%s",
                            server.name, action,
                        )
                    for action in re_added:
                        logger.warning(
                            "[BV] INV-9 [AUTO-FIX] server=%s action=re_add_peer peer=%s",
                            server.name, action,
                        )
                except Exception as exc:
                    logger.error("[BV] INV-9 auto-fix (reconcile) failed for server %d: %s",
                                 server.id, exc)

    # ── INV-10: Proxy config matches DB enabled clients ───────────────────────

    def _check_inv10_proxy_config_drift(self, auto_fix: bool = False, **_):
        """
        INV-10: The live proxy server config must reflect DB enabled clients.
          - TUIC: 'users' dict (uuid→password) must match enabled clients
          - Hysteria2: uses shared auth password; checks if service is running
        Drift auto-fix: regenerate config and restart service.
        """
        proxy_servers = (
            self.db.query(Server)
            .filter(
                Server.server_category == "proxy",
                Server.lifecycle_status == "online",
            )
            .all()
        )

        for server in proxy_servers:
            try:
                self._check_proxy_server_config(server, auto_fix=auto_fix)
            except Exception as exc:
                logger.error("[BV] INV-10 proxy check failed for server %d: %s",
                             server.id, exc)
                self._report.errors_during_check.append(
                    f"INV-10 server {server.id}: {exc}"
                )

    def _check_proxy_server_config(self, server: Server, auto_fix: bool = False):
        """Check one proxy server config vs DB state."""
        from ..core.proxy_base import ProxyBaseManager

        server_type = getattr(server, "server_type", "")
        config_path = getattr(server, "proxy_config_path", None)
        if not config_path:
            return  # no config path configured — skip

        mgr = ProxyBaseManager(
            config_path=config_path,
            service_name=getattr(server, "proxy_service_name", None) or "proxy-server",
            ssh_host=server.ssh_host,
            ssh_port=server.ssh_port or 22,
            ssh_user=server.ssh_user or "root",
            ssh_password=server.ssh_password,
            ssh_private_key=server.ssh_private_key,
        )

        try:
            config_raw = mgr._read_file(config_path)
        except Exception as exc:
            logger.warning("[BV] INV-10 could not read config for server %d: %s",
                           server.id, exc)
            return
        finally:
            try:
                mgr.close()
            except Exception:
                pass

        if not config_raw:
            self._report.checked += 1
            v = Violation(
                invariant="INV-10",
                entity="server",
                entity_id=server.id,
                description=(
                    f"Proxy server '{server.name}' config file is missing or empty: {config_path}"
                ),
                severity="error",
            )
            self._record_violation(v)
            if auto_fix:
                self._fix_proxy_config(server, v)
            return

        if server_type == "tuic":
            self._check_tuic_config(server, config_raw, auto_fix)
        elif server_type == "hysteria2":
            self._check_hysteria2_config(server, config_raw, auto_fix)

    def _check_tuic_config(self, server: Server, config_raw: str, auto_fix: bool):
        """Verify TUIC config users dict matches DB enabled clients."""
        import json as _json

        try:
            cfg = _json.loads(config_raw)
        except Exception as exc:
            logger.warning("[BV] INV-10 TUIC config JSON parse error for server %d: %s",
                           server.id, exc)
            return

        live_uuids: set = set(cfg.get("users", {}).keys())

        db_clients = (
            self.db.query(Client)
            .filter(
                Client.server_id == server.id,
                Client.public_key.is_(None),
            )
            .all()
        )
        enabled_uuids = {
            c.proxy_uuid for c in db_clients
            if c.enabled and c.proxy_uuid
        }
        disabled_uuids = {
            c.proxy_uuid for c in db_clients
            if not c.enabled and c.proxy_uuid
        }

        self._report.checked += 1

        # Enabled in DB but missing from config
        missing = enabled_uuids - live_uuids
        # Disabled in DB but present in config (access leak)
        ghost = disabled_uuids & live_uuids

        if missing:
            v = Violation(
                invariant="INV-10",
                entity="server",
                entity_id=server.id,
                description=(
                    f"TUIC server '{server.name}': {len(missing)} enabled client(s) "
                    f"missing from config {server.proxy_config_path} — access not granted"
                ),
                severity="error",
            )
            self._record_violation(v)
            if auto_fix:
                self._fix_proxy_config(server, v)
            return  # auto-fix will rebuild whole config

        if ghost:
            v = Violation(
                invariant="INV-10",
                entity="server",
                entity_id=server.id,
                description=(
                    f"TUIC server '{server.name}': {len(ghost)} disabled client(s) "
                    f"still present in config (access leak) — config not regenerated"
                ),
                severity="critical",
            )
            self._record_violation(v)
            logger.critical(
                "[BV] INV-10 CRITICAL: TUIC server %d '%s' — %d ghost user(s) in config",
                server.id, server.name, len(ghost),
            )
            if auto_fix:
                self._fix_proxy_config(server, v)

    def _check_hysteria2_config(self, server: Server, config_raw: str, auto_fix: bool):
        """Verify Hysteria2 config auth password matches DB."""
        try:
            import yaml as _yaml
            cfg = _yaml.safe_load(config_raw)
        except Exception as exc:
            logger.warning("[BV] INV-10 Hysteria2 config YAML parse error for server %d: %s",
                           server.id, exc)
            return

        self._report.checked += 1
        live_password = (cfg or {}).get("auth", {}).get("password", "")
        db_password = getattr(server, "proxy_auth_password", None) or ""

        if db_password and live_password != db_password:
            v = Violation(
                invariant="INV-10",
                entity="server",
                entity_id=server.id,
                description=(
                    f"Hysteria2 server '{server.name}': auth.password in config "
                    f"does not match proxy_auth_password in DB — clients may be locked out"
                ),
                severity="error",
            )
            self._record_violation(v)
            if auto_fix:
                self._fix_proxy_config(server, v)

    def _fix_proxy_config(self, server: Server, v: Violation):
        """Regenerate proxy config from DB and restart service."""
        try:
            from ..core.client_manager import ClientManager
            cm = ClientManager(self.db)
            ok = cm._apply_proxy_config(server)
            if ok:
                v.fixed = True
                self._report.auto_fixed += 1
                logger.warning(
                    "[BV] INV-10 [AUTO-FIX] server_id=%d name='%s' action=regenerate_proxy_config",
                    server.id, server.name,
                )
                self._audit(
                    AuditAction.SYSTEM_START, "server", server.id, server.name,
                    {"invariant": "INV-10", "action": "regenerate_proxy_config"},
                )
            else:
                logger.error("[BV] INV-10 auto-fix: apply_proxy_config returned False "
                             "for server %d '%s'", server.id, server.name)
        except Exception as exc:
            logger.error("[BV] INV-10 auto-fix failed for server %d: %s",
                         server.id, exc)

    # ── INV-11: Worker heartbeat freshness ───────────────────────────────────

    def _check_inv11_worker_stale(self, auto_fix: bool = False, **_):
        """
        INV-11: Worker heartbeat must be newer than WORKER_STALE_MINUTES.
        A stale worker means scheduled tasks (expiry, BV, fail-safe refresh)
        are not running — system in degraded state.
        """
        WORKER_STALE_MINUTES = 15

        row = (
            self.db.query(SystemConfig)
            .filter(SystemConfig.key == "worker_last_heartbeat")
            .first()
        )
        self._report.checked += 1

        if not row or not row.value:
            v = Violation(
                invariant="INV-11",
                entity="system",
                entity_id=0,
                description="Worker heartbeat key missing — worker may never have started",
                severity="warning",
            )
            self._record_violation(v)
            return

        try:
            last_beat = datetime.fromisoformat(row.value)
            if last_beat.tzinfo is None:
                last_beat = last_beat.replace(tzinfo=timezone.utc)
        except Exception:
            return

        age_min = (datetime.now(timezone.utc) - last_beat).total_seconds() / 60
        if age_min > WORKER_STALE_MINUTES:
            v = Violation(
                invariant="INV-11",
                entity="system",
                entity_id=0,
                description=(
                    f"Worker heartbeat is {age_min:.0f} min old (threshold: {WORKER_STALE_MINUTES} min) "
                    f"— background tasks may be stopped. Last beat: {row.value}"
                ),
                severity="critical",
            )
            self._record_violation(v)
            logger.critical(
                "[BV] INV-11 CRITICAL: worker heartbeat stale by %.0f min (last: %s)",
                age_min, row.value,
            )
            # No auto-fix possible for a dead worker from within the BV

    # ── Deep-check result caching ─────────────────────────────────────────────

    def _cache_deep_check_results(self):
        """
        Store deep-check counters in SystemConfig so /health/full can read them
        without re-running expensive WG/SSH checks inline.
        """
        import json as _json

        bw_mismatches = sum(
            1 for v in self._report.violations if v.invariant == "INV-8"
        )
        # INV-9 violations are per-server; count distinct server IDs
        peer_drift_servers = sum(
            1 for v in self._report.violations if v.invariant == "INV-9"
        )
        proxy_drift = sum(
            1 for v in self._report.violations if v.invariant == "INV-10"
        )
        worker_stale = any(v.invariant == "INV-11" for v in self._report.violations)

        def _upsert(key: str, value: str):
            row = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if row:
                row.value = value
            else:
                self.db.add(SystemConfig(key=key, value=value, value_type="string",
                                         description="bv deep-check cache"))

        _upsert("bv_bandwidth_mismatches", str(bw_mismatches))
        _upsert("bv_peer_drift_servers", str(peer_drift_servers))
        _upsert("bv_proxy_config_drift", str(proxy_drift))
        _upsert("bv_worker_stale", "true" if worker_stale else "false")
        _upsert("bv_last_deep_check", datetime.now(timezone.utc).isoformat())
        self.db.commit()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _record_violation(self, v: Violation):
        """Log and record a violation into the report."""
        log_fn = logger.critical if v.severity == "critical" else (
            logger.error if v.severity == "error" else logger.warning
        )
        log_fn("[BV] %s [%s]: %s", v.invariant, v.severity.upper(), v.description)

        self._report.violations.append(v)

        # Write to audit_logs so it's visible in the Admin Panel
        try:
            self._audit(
                AuditAction.SYSTEM_START,  # closest generic action — future: add INVARIANT_VIOLATION
                v.entity, v.entity_id, None,
                {
                    "invariant": v.invariant,
                    "severity": v.severity,
                    "description": v.description,
                    "source": "business_validator",
                },
            )
        except Exception:
            pass  # never crash the check because of audit write failure

    def _audit(
        self,
        action: AuditAction,
        target_type: str,
        target_id: int,
        target_name: Optional[str],
        details: dict,
    ):
        try:
            entry = AuditLog(
                user_id=None,
                user_type="system",
                action=action,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                details=details,
            )
            self.db.add(entry)
            self.db.commit()
        except Exception as exc:
            logger.debug("[BV] audit write failed: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass

    def _fix_enable_client_for_user(
        self, user_id: int, sub: ClientPortalSubscription
    ) -> bool:
        """Try to find a disabled client for the user and re-enable it."""
        client = (
            self.db.query(Client)
            .filter(Client.telegram_user_id == user_id)
            .order_by(Client.id.desc())
            .first()
        )
        if not client:
            logger.error(
                "[BV] INV-1 auto-fix: no client found for user %d — cannot re-enable", user_id
            )
            return False
        try:
            client.enabled = True
            if client.status in (ClientStatus.EXPIRED, ClientStatus.DISABLED):
                client.status = ClientStatus.ACTIVE
            self.db.commit()
            self._report.auto_fixed += 1
            logger.warning(
                "[BV] INV-1 auto-fix: re-enabled client %d '%s' for user %d",
                client.id, client.name, user_id,
            )
            self._audit(
                AuditAction.CLIENT_ENABLE, "client", client.id, client.name,
                {"reason": "business_validator_inv1", "sub_id": sub.id},
            )
            return True
        except Exception as exc:
            logger.error("[BV] INV-1 auto-fix failed for user %d: %s", user_id, exc)
            return False

    def _fix_create_sub_for_payment(self, payment: ClientPortalPayment) -> bool:
        """Re-run subscription creation for a payment that has no linked sub."""
        try:
            from .subscription.subscription_manager import SubscriptionManager
            mgr = SubscriptionManager(self.db)
            mgr.apply_subscription_limits(payment.user_id, reset_traffic=False)
            self._report.auto_fixed += 1
            logger.warning(
                "[BV] INV-5 auto-fix: re-applied subscription limits for user %d (payment %s)",
                payment.user_id, payment.invoice_id,
            )
            return True
        except Exception as exc:
            logger.error(
                "[BV] INV-5 auto-fix failed for payment %s: %s", payment.invoice_id, exc
            )
            return False


# ─── standalone runner (for worker / cron) ───────────────────────────────────

def run_validation(auto_fix: bool = True) -> ValidationReport:
    """Entry point for periodic worker execution."""
    try:
        db = SessionLocal()
        try:
            bv = BusinessValidator(db)
            return bv.run_all(auto_fix=auto_fix)
        finally:
            db.close()
    except Exception as exc:
        logger.error("[BV] run_validation failed with unhandled exception: %s", exc)
        report = ValidationReport()
        report.errors_during_check.append(str(exc))
        report.finished_at = datetime.now(timezone.utc)
        return report
