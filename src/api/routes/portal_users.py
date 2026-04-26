"""
VPN Management Studio Portal Users API
Admin management of client portal users, subscriptions, payments, revenue
"""

from typing import Optional, List
from datetime import datetime, timedelta, timezone
import io
import csv
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from loguru import logger

from ...database.connection import get_db
from ...database.models import Client, Server, ClientStatus
from ...modules.subscription.subscription_models import (
    ClientUser, ClientPortalSubscription, ClientPortalPayment,
    SubscriptionPlan, SubscriptionStatus, ClientUserClients,
    SupportMessage
)
from ...modules.subscription.subscription_manager import SubscriptionManager

router = APIRouter()


# ============================================================================
# SCHEMAS
# ============================================================================

class PortalUserSummary(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_banned: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    tier: Optional[str] = None
    subscription_status: Optional[str] = None
    expiry_date: Optional[str] = None
    devices_count: int = 0

    class Config:
        from_attributes = True


class PortalUserDetail(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    telegram_id: Optional[str] = None
    language: Optional[str] = None
    email_verified: bool = False
    is_active: bool
    is_banned: bool
    ban_reason: Optional[str] = None
    created_at: Optional[str] = None
    last_login: Optional[str] = None

    subscription: Optional[dict] = None
    devices: List[dict] = []
    payments: List[dict] = []


class CreateAccountRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    username: str = Field(..., min_length=3, max_length=50)
    full_name: Optional[str] = None
    tier: str = Field("free", min_length=1)
    duration_days: int = Field(30, ge=1, le=3650)


class UserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    is_banned: Optional[bool] = None
    ban_reason: Optional[str] = None


class GrantSubscriptionRequest(BaseModel):
    tier: str = Field(..., min_length=1)
    duration_days: int = Field(30, ge=1, le=3650)


class ExtendSubscriptionRequest(BaseModel):
    days: int = Field(..., ge=1, le=3650)


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class BroadcastRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    tier: Optional[str] = None  # None = all users
    only_active: bool = True


class PaymentListItem(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    email: Optional[str] = None
    invoice_id: str
    amount_usd: float
    payment_method: Optional[str] = None
    status: str
    subscription_tier: Optional[str] = None
    duration_days: Optional[int] = None
    provider_name: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class RevenueStats(BaseModel):
    total_revenue: float = 0
    total_payments: int = 0
    completed_payments: int = 0
    pending_payments: int = 0
    revenue_30d: float = 0
    revenue_7d: float = 0
    by_method: dict = {}
    by_tier: dict = {}
    active_subscriptions: int = 0
    total_users: int = 0


# ============================================================================
# HELPERS
# ============================================================================

def _dt_str(dt) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _serialize_user_summary(user: ClientUser, db: Session, devices_count: int = None) -> dict:
    sub = user.subscription
    if devices_count is None:
        devices_count = db.query(ClientUserClients).filter(
            ClientUserClients.client_user_id == user.id
        ).count()

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_banned": user.is_banned,
        "created_at": _dt_str(user.created_at),
        "last_login": _dt_str(user.last_login),
        "tier": sub.tier if sub else None,
        "subscription_status": sub.status.value if sub else None,
        "expiry_date": _dt_str(sub.expiry_date) if sub else None,
        "devices_count": devices_count,
    }


def _serialize_subscription(sub: ClientPortalSubscription) -> dict:
    if not sub:
        return None
    return {
        "id": sub.id,
        "tier": sub.tier,
        "status": sub.status.value,
        "max_devices": sub.max_devices,
        "traffic_limit_gb": sub.traffic_limit_gb,
        "traffic_used_gb": round(sub.traffic_used_total_gb, 2),
        "bandwidth_limit_mbps": sub.bandwidth_limit_mbps,
        "price_monthly_usd": sub.price_monthly_usd,
        "expiry_date": _dt_str(sub.expiry_date),
        "days_remaining": sub.days_remaining,
        "auto_renew": sub.auto_renew,
        "start_date": _dt_str(sub.start_date),
        "last_renewal": _dt_str(sub.last_renewal),
    }


def _serialize_payment(payment: ClientPortalPayment) -> dict:
    return {
        "id": payment.id,
        "user_id": payment.user_id,
        "invoice_id": payment.invoice_id,
        "amount_usd": payment.amount_usd,
        "payment_method": payment.payment_method.value if payment.payment_method else None,
        "status": payment.status,
        "subscription_tier": payment.subscription_tier,
        "duration_days": payment.duration_days,
        "provider_name": payment.provider_name,
        "created_at": _dt_str(payment.created_at),
        "completed_at": _dt_str(payment.completed_at),
    }


def _disable_user_wg_clients(user_id: int, db: Session, reason: str = "disabled") -> int:
    """Disable all WG clients linked to a portal user. Returns count."""
    from ...database.models import ClientStatus
    from ...core.management import ManagementCore
    links = db.query(ClientUserClients).filter(ClientUserClients.client_user_id == user_id).all()
    if not links:
        return 0
    client_ids = [l.client_id for l in links]
    wg_clients = db.query(Client).filter(Client.id.in_(client_ids), Client.enabled == True).all()
    core = ManagementCore(db)
    for c in wg_clients:
        # disable_client() removes WG peer and updates DB state atomically
        try:
            core.clients.disable_client(c.id)
        except Exception as e:
            logger.warning(f"Failed to disable WG peer for client {c.name}: {e}")
            # Fallback: update DB only
            c.enabled = False
            c.status = ClientStatus.DISABLED
    return len(wg_clients)


def _enable_user_wg_clients(user_id: int, db: Session) -> int:
    """Re-enable all WG clients linked to a portal user. Returns count."""
    from ...database.models import ClientStatus
    from ...core.management import ManagementCore
    links = db.query(ClientUserClients).filter(ClientUserClients.client_user_id == user_id).all()
    if not links:
        return 0
    client_ids = [l.client_id for l in links]
    wg_clients = db.query(Client).filter(Client.id.in_(client_ids), Client.enabled == False).all()
    core = ManagementCore(db)
    for c in wg_clients:
        # enable_client() adds WG peer and updates DB state atomically
        try:
            core.clients.enable_client(c.id)
        except Exception as e:
            logger.warning(f"Failed to enable WG peer for client {c.name}: {e}")
            # Fallback: update DB only
            c.enabled = True
            c.status = ClientStatus.ACTIVE
    return len(wg_clients)


# ============================================================================
# PHASE 1: USER MANAGEMENT
# ============================================================================

@router.get("")
async def list_portal_users(
    search: Optional[str] = Query(None, description="Search by username/email"),
    tier: Optional[str] = Query(None, description="Filter by subscription tier"),
    status: Optional[str] = Query(None, description="Filter: active, banned, inactive"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List portal users with search, filter, pagination"""
    query = db.query(ClientUser)

    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(
            ClientUser.username.ilike(pattern),
            ClientUser.email.ilike(pattern),
            ClientUser.full_name.ilike(pattern),
        ))

    if status == "active":
        query = query.filter(ClientUser.is_active == True, ClientUser.is_banned == False)
    elif status == "banned":
        query = query.filter(ClientUser.is_banned == True)
    elif status == "inactive":
        query = query.filter(ClientUser.is_active == False)

    if tier:
        query = query.join(ClientPortalSubscription).filter(func.lower(ClientPortalSubscription.tier) == tier.lower())

    total = query.count()
    users = query.order_by(ClientUser.id.desc()).offset(offset).limit(limit).all()

    # Batch device counts to avoid N+1 queries
    user_ids = [u.id for u in users]
    if user_ids:
        from sqlalchemy import func as sa_func
        device_counts = dict(
            db.query(
                ClientUserClients.client_user_id,
                sa_func.count(ClientUserClients.id),
            ).filter(ClientUserClients.client_user_id.in_(user_ids))
            .group_by(ClientUserClients.client_user_id).all()
        )
    else:
        device_counts = {}

    items = [_serialize_user_summary(u, db, device_counts.get(u.id, 0)) for u in users]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/tiers")
async def get_available_tiers(db: Session = Depends(get_db)):
    """Get available subscription tiers for filter dropdown"""
    plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).order_by(SubscriptionPlan.display_order).all()
    return [{"tier": p.tier, "name": p.name} for p in plans]


@router.post("/create-account")
async def create_account(req: CreateAccountRequest, db: Session = Depends(get_db)):
    """Admin: create a new portal user account with specified subscription tier"""
    mgr = SubscriptionManager(db)

    # Create user
    user, error = mgr.create_user(
        email=req.email,
        password=req.password,
        username=req.username,
        full_name=req.full_name,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    # If tier != free, upgrade the subscription
    if req.tier.lower() != "free":
        # Validate the tier exists BEFORE deleting the free subscription
        plan = mgr.get_plan_by_tier(req.tier)
        if not plan:
            raise HTTPException(status_code=400, detail=f"Plan not found for tier: {req.tier}")
        # Replace the default free subscription with the requested tier
        sub = mgr.get_subscription(user.id)
        if sub:
            db.delete(sub)
            db.commit()
        try:
            mgr.create_subscription(user.id, req.tier, req.duration_days)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Mark email as verified (admin-created accounts don't need verification)
    user.email_verified = True
    db.commit()

    sub = mgr.get_subscription(user.id)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "tier": sub.tier if sub else "free",
        "expiry_date": str(sub.expiry_date) if sub and sub.expiry_date else None,
        "message": f"Account created: {user.username} ({req.tier})"
    }


@router.get("/stats/revenue", response_model=RevenueStats)
async def get_revenue_stats(db: Session = Depends(get_db)):
    """Revenue and subscription statistics"""
    now = datetime.now(timezone.utc)

    # Total payments
    total_payments = db.query(func.count(ClientPortalPayment.id)).scalar() or 0
    completed_payments = db.query(func.count(ClientPortalPayment.id)).filter(
        ClientPortalPayment.status == "completed"
    ).scalar() or 0
    pending_payments = db.query(func.count(ClientPortalPayment.id)).filter(
        ClientPortalPayment.status == "pending"
    ).scalar() or 0

    # Revenue
    total_revenue = db.query(func.sum(ClientPortalPayment.amount_usd)).filter(
        ClientPortalPayment.status == "completed"
    ).scalar() or 0

    from datetime import timedelta
    revenue_30d = db.query(func.sum(ClientPortalPayment.amount_usd)).filter(
        ClientPortalPayment.status == "completed",
        ClientPortalPayment.completed_at >= now - timedelta(days=30)
    ).scalar() or 0

    revenue_7d = db.query(func.sum(ClientPortalPayment.amount_usd)).filter(
        ClientPortalPayment.status == "completed",
        ClientPortalPayment.completed_at >= now - timedelta(days=7)
    ).scalar() or 0

    # By method
    method_rows = db.query(
        ClientPortalPayment.payment_method,
        func.sum(ClientPortalPayment.amount_usd)
    ).filter(
        ClientPortalPayment.status == "completed"
    ).group_by(ClientPortalPayment.payment_method).all()
    by_method = {str(r[0].value) if r[0] else "unknown": round(r[1] or 0, 2) for r in method_rows}

    # By tier
    tier_rows = db.query(
        ClientPortalPayment.subscription_tier,
        func.sum(ClientPortalPayment.amount_usd)
    ).filter(
        ClientPortalPayment.status == "completed"
    ).group_by(ClientPortalPayment.subscription_tier).all()
    by_tier = {str(r[0] or "unknown"): round(r[1] or 0, 2) for r in tier_rows}

    # Active subscriptions
    active_subs = db.query(func.count(ClientPortalSubscription.id)).filter(
        ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
        ClientPortalSubscription.tier != "free"
    ).scalar() or 0

    total_users = db.query(func.count(ClientUser.id)).scalar() or 0

    return {
        "total_revenue": round(total_revenue, 2),
        "total_payments": total_payments,
        "completed_payments": completed_payments,
        "pending_payments": pending_payments,
        "revenue_30d": round(revenue_30d, 2),
        "revenue_7d": round(revenue_7d, 2),
        "by_method": by_method,
        "by_tier": by_tier,
        "active_subscriptions": active_subs,
        "total_users": total_users,
    }


@router.get("/payments")
async def list_all_payments(
    status: Optional[str] = Query(None, description="Filter by status"),
    user_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List all payments with filters"""
    query = db.query(ClientPortalPayment)

    if status:
        query = query.filter(ClientPortalPayment.status == status)
    if user_id:
        query = query.filter(ClientPortalPayment.user_id == user_id)

    total = query.count()
    payments = query.order_by(ClientPortalPayment.created_at.desc()).offset(offset).limit(limit).all()

    # Batch-load users to avoid N+1
    user_ids = list(set(p.user_id for p in payments))
    if user_ids:
        users_map = {u.id: u for u in db.query(ClientUser).filter(ClientUser.id.in_(user_ids)).all()}
    else:
        users_map = {}

    items = []
    for p in payments:
        data = _serialize_payment(p)
        user = users_map.get(p.user_id)
        data["username"] = user.username if user else None
        data["email"] = user.email if user else None
        items.append(data)

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/payments/{payment_id}/confirm")
async def confirm_payment(payment_id: int, db: Session = Depends(get_db)):
    """Manually confirm a pending payment"""
    payment = db.query(ClientPortalPayment).filter(ClientPortalPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status == "completed":
        return {"message": "Payment already completed"}

    mgr = SubscriptionManager(db)
    success = mgr.complete_payment(payment.invoice_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to complete payment")

    logger.info(f"Admin confirmed payment {payment.invoice_id} for user {payment.user_id}")
    return {"message": "Payment confirmed", "invoice_id": payment.invoice_id}


@router.post("/payments/{payment_id}/reject")
async def reject_payment(payment_id: int, db: Session = Depends(get_db)):
    """Reject a pending payment"""
    payment = db.query(ClientPortalPayment).filter(ClientPortalPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot reject a completed payment")

    payment.status = "rejected"
    db.commit()

    logger.info(f"Admin rejected payment {payment.invoice_id} for user {payment.user_id}")
    return {"message": "Payment rejected", "invoice_id": payment.invoice_id}


@router.delete("/payments/{payment_id}")
async def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    """Delete a payment record"""
    payment = db.query(ClientPortalPayment).filter(ClientPortalPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    invoice_id = payment.invoice_id
    db.delete(payment)
    db.commit()

    logger.info(f"Admin deleted payment {invoice_id}")
    return {"message": "Payment deleted"}


# ============================================================================
# STATIC ROUTES (must be BEFORE /{user_id} to avoid route conflict)
# ============================================================================

# --- CSV EXPORT ---

@router.get("/export/users")
async def export_users_csv(
    search: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Export portal users as CSV (with same filters as list)"""
    query = db.query(ClientUser)

    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(
            ClientUser.username.ilike(pattern),
            ClientUser.email.ilike(pattern),
        ))
    if status == "active":
        query = query.filter(ClientUser.is_active == True, ClientUser.is_banned == False)
    elif status == "banned":
        query = query.filter(ClientUser.is_banned == True)
    elif status == "inactive":
        query = query.filter(ClientUser.is_active == False)
    if tier:
        query = query.join(ClientPortalSubscription).filter(func.lower(ClientPortalSubscription.tier) == tier.lower())

    users = query.order_by(ClientUser.id).yield_per(100)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Username", "Email", "Full Name", "Active", "Banned", "Tier", "Status", "Expiry", "Devices", "Referral Code", "Referred By", "Created"])

    for u in users:
        sub = u.subscription
        devices = db.query(ClientUserClients).filter(ClientUserClients.client_user_id == u.id).count()
        referred_by = None
        if u.referred_by_id:
            ref = db.query(ClientUser).filter(ClientUser.id == u.referred_by_id).first()
            referred_by = ref.username if ref else str(u.referred_by_id)
        writer.writerow([
            u.id, u.username, u.email, u.full_name or "",
            u.is_active, u.is_banned,
            sub.tier if sub else "", sub.status.value if sub else "",
            _dt_str(sub.expiry_date) if sub else "",
            devices, u.referral_code or "", referred_by or "",
            _dt_str(u.created_at),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=portal_users.csv"}
    )


@router.get("/export/payments")
async def export_payments_csv(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Export payments as CSV"""
    query = db.query(ClientPortalPayment)
    if status:
        query = query.filter(ClientPortalPayment.status == status)

    payments = query.order_by(ClientPortalPayment.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Invoice", "Username", "Email", "Amount USD", "Method", "Status", "Tier", "Duration Days", "Provider", "Created", "Completed"])

    for p in payments:
        user = db.query(ClientUser).filter(ClientUser.id == p.user_id).first()
        writer.writerow([
            p.id, p.invoice_id,
            user.username if user else "", user.email if user else "",
            p.amount_usd, p.payment_method.value if p.payment_method else "",
            p.status, p.subscription_tier or "", p.duration_days or "",
            p.provider_name or "", _dt_str(p.created_at), _dt_str(p.completed_at),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments.csv"}
    )


# --- DASHBOARD STATS ---

@router.get("/stats/dashboard")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Extended stats for admin dashboard"""
    now = datetime.now(timezone.utc)

    new_users_7d = db.query(func.count(ClientUser.id)).filter(
        ClientUser.created_at >= now - timedelta(days=7)
    ).scalar() or 0

    new_users_30d = db.query(func.count(ClientUser.id)).filter(
        ClientUser.created_at >= now - timedelta(days=30)
    ).scalar() or 0

    total_users = db.query(func.count(ClientUser.id)).scalar() or 0

    paid_users = db.query(func.count(ClientPortalSubscription.id)).filter(
        ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
        ClientPortalSubscription.tier != "free"
    ).scalar() or 0

    free_users = total_users - paid_users
    conversion_rate = round((paid_users / total_users * 100), 1) if total_users > 0 else 0

    total_referrals = db.query(func.count(ClientUser.id)).filter(
        ClientUser.referred_by_id.isnot(None)
    ).scalar() or 0

    from sqlalchemy.orm import aliased
    Referrer = aliased(ClientUser)
    top_referrers_data = db.query(
        Referrer.username,
        func.count(ClientUser.id).label("cnt")
    ).join(
        Referrer, ClientUser.referred_by_id == Referrer.id
    ).group_by(Referrer.username).order_by(func.count(ClientUser.id).desc()).limit(5).all()

    from ...modules.subscription.subscription_models import PromoCode
    total_promo_uses = db.query(func.sum(PromoCode.used_count)).scalar() or 0
    active_promos = db.query(func.count(PromoCode.id)).filter(PromoCode.is_active == True).scalar() or 0

    return {
        "new_users_7d": new_users_7d,
        "new_users_30d": new_users_30d,
        "total_users": total_users,
        "paid_users": paid_users,
        "free_users": free_users,
        "conversion_rate": conversion_rate,
        "total_referrals": total_referrals,
        "top_referrers": [{"username": r[0], "count": r[1]} for r in top_referrers_data],
        "total_promo_uses": int(total_promo_uses),
        "active_promos": active_promos,
    }


# --- CHARTS DATA ---

@router.get("/stats/charts")
async def get_chart_data(db: Session = Depends(get_db)):
    """Time-series and distribution data for dashboard charts"""
    now = datetime.now(timezone.utc)

    # Revenue by day — last 30 days
    revenue_trend = []
    for i in range(29, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        amount = db.query(func.sum(ClientPortalPayment.amount_usd)).filter(
            ClientPortalPayment.status == "completed",
            ClientPortalPayment.completed_at >= day_start,
            ClientPortalPayment.completed_at <  day_end,
        ).scalar() or 0
        revenue_trend.append({"date": day_start.strftime("%b %d"), "amount": round(float(amount), 2)})

    # New users by day — last 30 days
    user_trend = []
    for i in range(29, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        cnt = db.query(func.count(ClientUser.id)).filter(
            ClientUser.created_at >= day_start,
            ClientUser.created_at <  day_end,
        ).scalar() or 0
        user_trend.append({"date": day_start.strftime("%b %d"), "count": cnt})

    # Subscription distribution by tier
    tier_rows = db.query(
        ClientPortalSubscription.tier,
        func.count(ClientPortalSubscription.id)
    ).filter(
        ClientPortalSubscription.status == SubscriptionStatus.ACTIVE
    ).group_by(ClientPortalSubscription.tier).all()
    sub_distribution = {row[0] or "free": row[1] for row in tier_rows}

    # Payment method distribution
    method_rows = db.query(
        ClientPortalPayment.payment_method,
        func.count(ClientPortalPayment.id)
    ).filter(
        ClientPortalPayment.status == "completed"
    ).group_by(ClientPortalPayment.payment_method).all()
    payment_methods = {str(row[0].value) if row[0] else "unknown": row[1] for row in method_rows}

    return {
        "revenue_trend": revenue_trend,
        "user_trend": user_trend,
        "sub_distribution": sub_distribution,
        "payment_methods": payment_methods,
    }


# --- BROADCAST ---

@router.post("/broadcast")
async def broadcast_message(data: BroadcastRequest, db: Session = Depends(get_db)):
    """Send a Telegram message to all (or filtered) portal users"""
    query = db.query(ClientUser).filter(ClientUser.telegram_id.isnot(None))
    if data.only_active:
        query = query.filter(ClientUser.is_active == True, ClientUser.is_banned == False)
    if data.tier:
        query = query.join(ClientPortalSubscription).filter(func.lower(ClientPortalSubscription.tier) == data.tier.lower())

    users = query.all()
    if not users:
        raise HTTPException(status_code=404, detail="No users matching criteria")

    from ...modules.notifications import NotificationService
    notif = NotificationService(db)

    sent = 0
    failed = 0
    for user in users:
        ok = notif.notify_user(user.id, data.message)
        if ok:
            sent += 1
        else:
            failed += 1

    return {"ok": True, "sent": sent, "failed": failed, "total": len(users)}


# --- SUPPORT MESSAGES (Admin side) ---

@router.get("/support-messages")
async def list_support_messages(
    status: Optional[str] = Query(None, description="Filter by status: open, answered, closed"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all support tickets (root messages only)"""
    from ...modules.subscription.subscription_models import SupportMessage

    query = db.query(SupportMessage).filter(SupportMessage.parent_id == None)

    if status:
        query = query.filter(SupportMessage.status == status)

    if search:
        query = query.join(ClientUser).filter(
            or_(
                SupportMessage.subject.ilike(f"%{search}%"),
                SupportMessage.message.ilike(f"%{search}%"),
                ClientUser.username.ilike(f"%{search}%"),
                ClientUser.email.ilike(f"%{search}%"),
            )
        )

    total = query.count()
    tickets = query.order_by(SupportMessage.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    result = []
    for t in tickets:
        user = db.get(ClientUser, t.user_id)
        reply_count = db.query(SupportMessage).filter(SupportMessage.parent_id == t.id).count()
        unread_count = db.query(SupportMessage).filter(
            SupportMessage.parent_id == t.id,
            SupportMessage.direction == "user",
            SupportMessage.is_read == False,
        ).count()
        if t.direction == "user" and not t.is_read:
            unread_count += 1

        result.append({
            "id": t.id,
            "user_id": t.user_id,
            "username": user.username if user else "deleted",
            "email": user.email if user else "",
            "subject": t.subject,
            "message": t.message,
            "status": t.status,
            "reply_count": reply_count,
            "unread_count": unread_count,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return {"items": result, "total": total, "page": page, "per_page": per_page}


@router.get("/support-messages/unread-count")
async def get_support_unread_total(db: Session = Depends(get_db)):
    """Get total unread support messages for admin badge"""
    from ...modules.subscription.subscription_models import SupportMessage

    count = db.query(SupportMessage).filter(
        SupportMessage.direction == "user",
        SupportMessage.is_read == False,
    ).count()

    return {"unread": count}


@router.get("/support-messages/{ticket_id}")
async def get_support_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Get a support ticket with all replies"""
    from ...modules.subscription.subscription_models import SupportMessage

    ticket = db.query(SupportMessage).filter(
        SupportMessage.id == ticket_id,
        SupportMessage.parent_id == None,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    user = db.get(ClientUser, ticket.user_id)
    replies = db.query(SupportMessage).filter(
        SupportMessage.parent_id == ticket.id
    ).order_by(SupportMessage.created_at.asc()).all()

    if not ticket.is_read and ticket.direction == "user":
        ticket.is_read = True
    for r in replies:
        if r.direction == "user" and not r.is_read:
            r.is_read = True
    db.commit()

    return {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "username": user.username if user else "deleted",
        "email": user.email if user else "",
        "telegram_id": user.telegram_id if user else None,
        "subject": ticket.subject,
        "message": ticket.message,
        "status": ticket.status,
        "direction": ticket.direction,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "replies": [{
            "id": r.id,
            "message": r.message,
            "direction": r.direction,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in replies],
    }


class AdminReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


@router.post("/support-messages/{ticket_id}/reply")
async def reply_to_ticket(ticket_id: int, data: AdminReplyRequest, db: Session = Depends(get_db)):
    """Admin replies to a support ticket"""
    from ...modules.subscription.subscription_models import SupportMessage

    ticket = db.query(SupportMessage).filter(
        SupportMessage.id == ticket_id,
        SupportMessage.parent_id == None,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    reply = SupportMessage(
        user_id=ticket.user_id,
        subject=ticket.subject,
        message=data.message,
        direction="admin",
        parent_id=ticket.id,
        is_read=False,
    )
    db.add(reply)
    ticket.status = "answered"
    db.commit()

    try:
        user = db.get(ClientUser, ticket.user_id)
        if user and user.telegram_id:
            from ...modules.notifications import NotificationService
            notif = NotificationService(db)
            notif.notify_user(ticket.user_id, f"📬 Support reply\nRe: {ticket.subject}\n\n{data.message[:500]}")
    except Exception as e:
        logger.warning(f"Failed to notify user about support reply: {e}")

    return {"id": reply.id, "status": "sent"}


@router.post("/support-messages/{ticket_id}/close")
async def close_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Close a support ticket"""
    from ...modules.subscription.subscription_models import SupportMessage

    ticket = db.query(SupportMessage).filter(
        SupportMessage.id == ticket_id,
        SupportMessage.parent_id == None,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = "closed"
    db.commit()
    return {"ok": True, "status": "closed"}


@router.post("/support-messages/{ticket_id}/reopen")
async def reopen_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Reopen a closed support ticket"""
    from ...modules.subscription.subscription_models import SupportMessage

    ticket = db.query(SupportMessage).filter(
        SupportMessage.id == ticket_id,
        SupportMessage.parent_id == None,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = "open"
    db.commit()
    return {"ok": True, "status": "open"}


@router.delete("/support-messages/{ticket_id}")
async def delete_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Delete a support ticket and all its replies"""
    from ...modules.subscription.subscription_models import SupportMessage

    ticket = db.query(SupportMessage).filter(
        SupportMessage.id == ticket_id,
        SupportMessage.parent_id == None,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    db.query(SupportMessage).filter(SupportMessage.parent_id == ticket_id).delete()
    db.delete(ticket)
    db.commit()
    return {"ok": True}


# ============================================================================
# USER-SPECIFIC ROUTES (/{user_id} catch-all - must be LAST)
# ============================================================================

@router.get("/{user_id}")
async def get_portal_user(user_id: int, db: Session = Depends(get_db)):
    """Get detailed info about a portal user"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Subscription
    sub_data = _serialize_subscription(user.subscription)

    # Devices (WG clients)
    links = db.query(ClientUserClients).filter(ClientUserClients.client_user_id == user_id).all()
    devices = []
    if links:
        client_ids = [l.client_id for l in links]
        wg_clients = db.query(Client).filter(Client.id.in_(client_ids)).all()
        # Pre-fetch server names
        server_ids = list(set(c.server_id for c in wg_clients))
        servers = {s.id: s.name for s in db.query(Server).filter(Server.id.in_(server_ids)).all()} if server_ids else {}
        for c in wg_clients:
            devices.append({
                "id": c.id,
                "name": c.name,
                "ipv4": c.ipv4,
                "enabled": c.enabled,
                "server_id": c.server_id,
                "server_name": servers.get(c.server_id, f"Server #{c.server_id}"),
                "bandwidth_limit": c.bandwidth_limit,
                "traffic_rx": c.traffic_used_rx,
                "traffic_tx": c.traffic_used_tx,
                "last_handshake": _dt_str(c.last_handshake) if hasattr(c, 'last_handshake') else None,
            })

    # Payments
    payments = db.query(ClientPortalPayment).filter(
        ClientPortalPayment.user_id == user_id
    ).order_by(ClientPortalPayment.created_at.desc()).limit(20).all()
    payments_data = [_serialize_payment(p) for p in payments]

    # Referral info
    referred_by_username = None
    if user.referred_by_id:
        referrer = db.query(ClientUser).filter(ClientUser.id == user.referred_by_id).first()
        referred_by_username = referrer.username if referrer else None
    referral_count = db.query(ClientUser).filter(ClientUser.referred_by_id == user.id).count()

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "telegram_id": user.telegram_id,
        "language": user.language,
        "email_verified": user.email_verified,
        "is_active": user.is_active,
        "is_banned": user.is_banned,
        "ban_reason": user.ban_reason,
        "created_at": _dt_str(user.created_at),
        "last_login": _dt_str(user.last_login),
        "referral_code": user.referral_code,
        "referred_by_username": referred_by_username,
        "referral_count": referral_count,
        "subscription": sub_data,
        "devices": devices,
        "payments": payments_data,
    }


@router.put("/{user_id}")
async def update_portal_user(user_id: int, data: UserUpdateRequest, db: Session = Depends(get_db)):
    """Ban/unban or activate/deactivate a portal user"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    was_banned = user.is_banned
    was_active = user.is_active

    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_banned is not None:
        user.is_banned = data.is_banned
        if data.is_banned:
            user.ban_reason = data.ban_reason
        else:
            user.ban_reason = None

    # Determine if user is now restricted (banned or inactive)
    now_restricted = user.is_banned or not user.is_active
    was_restricted = was_banned or not was_active

    disabled_count = 0
    enabled_count = 0

    if now_restricted and not was_restricted:
        # User just got banned/deactivated → disable WG clients
        disabled_count = _disable_user_wg_clients(user.id, db, reason="BANNED" if user.is_banned else "DISABLED")
    elif not now_restricted and was_restricted:
        # User just got unbanned/activated → re-enable if subscription is active
        sub = user.subscription
        if sub and sub.status == SubscriptionStatus.ACTIVE:
            enabled_count = _enable_user_wg_clients(user.id, db)

    db.commit()
    logger.info(f"Updated portal user {user.username}: active={user.is_active}, banned={user.is_banned}, wg_disabled={disabled_count}, wg_enabled={enabled_count}")
    return {"message": "User updated", "id": user.id}


# ============================================================================
# PHASE 2: SUBSCRIPTION MANAGEMENT
# ============================================================================

@router.post("/{user_id}/grant-subscription")
async def grant_subscription(user_id: int, data: GrantSubscriptionRequest, db: Session = Depends(get_db)):
    """Grant or upgrade subscription for a user"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_banned:
        raise HTTPException(status_code=400, detail="Cannot grant subscription to a banned user. Unban first.")

    mgr = SubscriptionManager(db)

    existing = mgr.get_subscription(user_id)
    if existing:
        sub, err = mgr.upgrade_subscription(user_id, data.tier, data.duration_days)
        if err:
            raise HTTPException(status_code=400, detail=err)
        action = "upgraded"
    else:
        sub = mgr.create_subscription(user_id, data.tier, data.duration_days)
        action = "created"

    # Apply WG limits
    mgr.apply_subscription_limits(user_id)

    # Auto-create WG client if user has none
    auto_created = False
    existing_clients = mgr.get_user_wireguard_clients(user_id)
    if not existing_clients and data.tier != "free":
        try:
            wg_client = mgr.auto_create_wireguard_client(user_id)
            if wg_client:
                auto_created = True
                logger.info(f"Auto-created WG client for user {user.username} on grant")
        except Exception as e:
            logger.error(f"Failed to auto-create WG client for user {user.username}: {e}")

    logger.info(f"Admin {action} subscription for user {user.username}: {data.tier} for {data.duration_days} days")
    return {"message": f"Subscription {action}" + (" (device auto-created)" if auto_created else ""), "subscription": _serialize_subscription(sub)}


@router.post("/{user_id}/extend-subscription")
async def extend_subscription(user_id: int, data: ExtendSubscriptionRequest, db: Session = Depends(get_db)):
    """Extend user's subscription by N days"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    mgr = SubscriptionManager(db)
    sub, err = mgr.renew_subscription(user_id, data.days)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Apply WG limits
    mgr.apply_subscription_limits(user_id)

    logger.info(f"Admin extended subscription for user {user.username} by {data.days} days")
    return {"message": f"Subscription extended by {data.days} days", "subscription": _serialize_subscription(sub)}


@router.post("/{user_id}/cancel-subscription")
async def cancel_subscription(user_id: int, db: Session = Depends(get_db)):
    """Cancel user's subscription"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    mgr = SubscriptionManager(db)
    success = mgr.cancel_subscription(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="No subscription found")

    # Downgrade WG limits to free and disable clients
    mgr.apply_subscription_limits(user_id)
    disabled = _disable_user_wg_clients(user_id, db, reason="SUBSCRIPTION_CANCELLED")
    db.commit()

    logger.info(f"Admin cancelled subscription for user {user.username}, disabled {disabled} WG clients")
    return {"message": "Subscription cancelled"}


# ============================================================================
# PHASE 3: RESET TRAFFIC & DELETE USER
# ============================================================================

@router.post("/{user_id}/reset-traffic")
async def reset_user_traffic(user_id: int, db: Session = Depends(get_db)):
    """Reset traffic counters for a portal user's subscription"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sub = user.subscription
    if not sub:
        raise HTTPException(status_code=400, detail="No subscription found")

    sub.traffic_used_rx = 0
    sub.traffic_used_tx = 0

    # Also reset traffic on linked WG clients
    links = db.query(ClientUserClients).filter(ClientUserClients.client_user_id == user_id).all()
    if links:
        client_ids = [l.client_id for l in links]
        wg_clients = db.query(Client).filter(Client.id.in_(client_ids)).all()
        for c in wg_clients:
            c.traffic_used_rx = 0
            c.traffic_used_tx = 0
            c.traffic_baseline_rx = 0
            c.traffic_baseline_tx = 0
            # Re-enable if was disabled due to traffic exceeded
            if c.status == ClientStatus.TRAFFIC_EXCEEDED:
                # enable_client() re-adds WG peer and updates DB state atomically
                try:
                    from ...core.management import ManagementCore
                    core = ManagementCore(db)
                    core.clients.enable_client(c.id)
                except Exception as e:
                    logger.warning(f"Failed to re-enable WG peer for {c.name} on traffic reset: {e}")
                    c.enabled = True
                    c.status = ClientStatus.ACTIVE

    db.commit()
    logger.info(f"Admin reset traffic for user {user.username}")
    return {"message": "Traffic reset"}


@router.delete("/{user_id}")
async def delete_portal_user(user_id: int, db: Session = Depends(get_db)):
    """Delete a portal user and unlink their WG clients"""
    user = db.query(ClientUser).filter(ClientUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    username = user.username

    # Disable and unlink WG clients (don't delete WG clients, but disable them)
    links = db.query(ClientUserClients).filter(ClientUserClients.client_user_id == user_id).all()
    if links:
        client_ids = [l.client_id for l in links]
        wg_clients = db.query(Client).filter(Client.id.in_(client_ids), Client.enabled == True).all()
        from ...core.management import ManagementCore
        core = ManagementCore(db)
        for c in wg_clients:
            # disable_client() removes WG peer and updates DB state atomically
            try:
                core.clients.disable_client(c.id)
            except Exception as e:
                logger.warning(f"Failed to disable WG peer for {c.name} on user delete: {e}")
                c.enabled = False
                c.status = ClientStatus.DISABLED
        db.query(ClientUserClients).filter(ClientUserClients.client_user_id == user_id).delete()

    # Delete support messages
    db.query(SupportMessage).filter(SupportMessage.user_id == user_id).delete()

    # Delete payments (FK constraint requires this before user deletion)
    db.query(ClientPortalPayment).filter(ClientPortalPayment.user_id == user_id).delete()

    # Delete subscription
    db.query(ClientPortalSubscription).filter(ClientPortalSubscription.user_id == user_id).delete()

    # Delete user
    db.delete(user)
    db.commit()

    logger.info(f"Admin deleted portal user {username} (id={user_id}), WG clients disabled")
    return {"message": f"User {username} deleted"}
