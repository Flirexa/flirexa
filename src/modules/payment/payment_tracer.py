"""
VPN Management Studio — Payment Pipeline Tracer

Provides structured, end-to-end logging for every payment lifecycle step.

Each payment gets a trace_id ("pay_<invoice_id>_<epoch>") and a pipeline_log
JSON array stored on the ClientPortalPayment row. This lets you reconstruct
exactly what happened at every step, even after the fact.

Steps tracked
-------------
  create     → invoice created, method chosen
  webhook    → provider webhook received
  activate   → complete_payment() called, subscription updated
  sync_wg    → WireGuard/proxy access applied
  invariant  → business invariant post-check

Usage
-----
    from src.modules.payment.payment_tracer import PaymentTracer

    tracer = PaymentTracer(db, payment)
    tracer.step("create", status="ok", detail={"provider": "cryptopay"})
    ...
    tracer.step("activate", status="error", detail={"error": "DB timeout"})
    tracer.mark_inconsistent("activate step failed after 3 retries")
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..subscription.subscription_models import ClientPortalPayment


# ─── tracer ──────────────────────────────────────────────────────────────────

class PaymentTracer:
    """
    Attaches pipeline-step records to a ClientPortalPayment row.
    Thread-safe within a single DB session; commit is the caller's responsibility.
    """

    STEPS = ("create", "webhook", "activate", "sync_wg", "invariant")

    def __init__(self, db: Session, payment: ClientPortalPayment):
        self.db = db
        self.payment = payment
        self._ensure_trace_id()

    # ── public API ────────────────────────────────────────────────────────────

    def step(
        self,
        step_name: str,
        status: str = "ok",
        detail: Optional[dict] = None,
    ):
        """
        Record one pipeline step.

        Parameters
        ----------
        step_name : one of STEPS ("create" | "webhook" | "activate" | "sync_wg" | "invariant")
        status    : "ok" | "error" | "skip" | "warn"
        detail    : arbitrary dict with context (provider, sub_id, error, etc.)
        """
        log_level = logger.error if status == "error" else (
            logger.warning if status == "warn" else logger.debug
        )

        record = {
            "step": step_name,
            "status": status,
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.payment.trace_id,
        }
        if detail:
            record["detail"] = detail

        log_level(
            "[PAY:%s] step=%s status=%s invoice=%s user_id=%s%s",
            self.payment.trace_id,
            step_name,
            status,
            self.payment.invoice_id,
            self.payment.user_id,
            f" detail={detail}" if detail else "",
        )

        # Append to pipeline_log JSON array
        try:
            log_arr = json.loads(self.payment.pipeline_log or "[]")
        except Exception:
            log_arr = []
        log_arr.append(record)
        self.payment.pipeline_log = json.dumps(log_arr)

        # Flush without full commit so caller controls transaction boundary
        try:
            self.db.flush()
        except Exception as exc:
            logger.warning("[PAY:%s] pipeline_log flush failed: %s", self.payment.trace_id, exc)

    def mark_inconsistent(self, reason: str):
        """
        Mark this payment as inconsistent (pipeline broken mid-way).
        Logs CRITICAL and persists pipeline_status='inconsistent'.
        """
        logger.critical(
            "[PAY:%s] INCONSISTENT: invoice=%s user_id=%s — %s",
            self.payment.trace_id,
            self.payment.invoice_id,
            self.payment.user_id,
            reason,
        )
        self.payment.pipeline_status = "inconsistent"
        self.step("__inconsistent__", status="error", detail={"reason": reason})
        try:
            self.db.commit()
        except Exception as exc:
            logger.error("[PAY:%s] mark_inconsistent commit failed: %s", self.payment.trace_id, exc)
            try:
                self.db.rollback()
            except Exception:
                pass

    def get_log(self) -> list:
        """Return parsed pipeline_log array."""
        try:
            return json.loads(self.payment.pipeline_log or "[]")
        except Exception:
            return []

    def is_step_completed(self, step_name: str) -> bool:
        """Return True if the given step completed with status='ok'."""
        for rec in self.get_log():
            if rec.get("step") == step_name and rec.get("status") == "ok":
                return True
        return False

    # ── helpers ───────────────────────────────────────────────────────────────

    def _ensure_trace_id(self):
        if not self.payment.trace_id:
            ts = int(time.time())
            self.payment.trace_id = f"pay_{self.payment.invoice_id[:16]}_{ts}"
            try:
                self.db.flush()
            except Exception:
                pass


# ─── convenience factory ──────────────────────────────────────────────────────

def get_tracer(db: Session, invoice_id: str) -> Optional[PaymentTracer]:
    """
    Look up a payment by invoice_id and return a PaymentTracer for it.
    Returns None if not found.
    """
    payment = (
        db.query(ClientPortalPayment)
        .filter(ClientPortalPayment.invoice_id == invoice_id)
        .first()
    )
    if not payment:
        logger.warning("[PaymentTracer] invoice_id=%s not found", invoice_id)
        return None
    return PaymentTracer(db, payment)
