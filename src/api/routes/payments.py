"""
VPN Management Studio API - Payment Routes
Payment management (stub implementation)
"""

from typing import Optional, List
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database.connection import get_db
from ...database.models import Payment, PaymentStatus, Plan


router = APIRouter()


# ============================================================================
# SCHEMAS
# ============================================================================

class PlanResponse(BaseModel):
    """Subscription plan response"""
    id: int
    name: str
    duration_days: int
    traffic_limit_gb: Optional[int]
    bandwidth_limit_mbps: Optional[int]
    max_devices: int
    price_usd: int
    price_rub: int
    is_active: bool
    description: Optional[str]

    class Config:
        from_attributes = True


class PlanCreate(BaseModel):
    """Create subscription plan"""
    name: str = Field(..., min_length=1, max_length=100)
    duration_days: int = Field(..., ge=1)
    traffic_limit_gb: Optional[int] = Field(None, ge=0)
    bandwidth_limit_mbps: Optional[int] = Field(None, ge=0)
    max_devices: int = Field(1, ge=1)
    price_usd: int = Field(0, ge=0, description="Price in cents")
    price_rub: int = Field(0, ge=0, description="Price in kopecks")
    description: Optional[str] = None


class PaymentResponse(BaseModel):
    """Payment response"""
    id: int
    telegram_user_id: Optional[int]
    amount: int
    currency: str
    provider: str
    status: str
    wallet_address: Optional[str]
    tx_hash: Optional[str]
    created_at: datetime
    expires_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    """Create payment invoice"""
    telegram_user_id: Optional[int] = None
    amount: int = Field(..., gt=0, description="Amount in smallest units")
    currency: str = Field(..., description="Currency code (USD, RUB, BTC, etc.)")
    provider: str = Field("mock", description="Payment provider")
    plan_id: Optional[int] = None


class InvoiceResponse(BaseModel):
    """Invoice response"""
    id: int
    amount: int
    currency: str
    provider: str
    status: str
    wallet_address: Optional[str]
    qr_code: Optional[str]
    expires_at: Optional[datetime]


# ============================================================================
# PLAN ENDPOINTS
# ============================================================================

@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(
    active_only: bool = Query(True),
    db: Session = Depends(get_db)
):
    """
    Get available subscription plans
    """
    query = db.query(Plan)
    if active_only:
        query = query.filter(Plan.is_active == True)
    return query.all()


@router.post("/plans", response_model=PlanResponse, status_code=201)
async def create_plan(
    plan_data: PlanCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new subscription plan
    """
    # Check if plan with same name exists
    existing = db.query(Plan).filter(Plan.name == plan_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Plan with this name already exists")

    plan = Plan(
        name=plan_data.name,
        duration_days=plan_data.duration_days,
        traffic_limit_gb=plan_data.traffic_limit_gb,
        bandwidth_limit_mbps=plan_data.bandwidth_limit_mbps,
        max_devices=plan_data.max_devices,
        price_usd=plan_data.price_usd,
        price_rub=plan_data.price_rub,
        description=plan_data.description,
        is_active=True,
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)

    return plan


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Get plan details
    """
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a subscription plan (sets inactive)
    """
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan.is_active = False
    db.commit()

    return {"message": f"Plan '{plan.name}' deactivated"}


# ============================================================================
# PAYMENT ENDPOINTS
# ============================================================================

@router.get("", response_model=List[PaymentResponse])
async def list_payments(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    Get list of payments
    """
    query = db.query(Payment)

    if status:
        try:
            status_enum = PaymentStatus(status)
            query = query.filter(Payment.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    return query.order_by(Payment.created_at.desc()).limit(limit).all()


@router.post("/invoice", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    invoice_data: InvoiceCreate,
    db: Session = Depends(get_db)
):
    """
    Create a payment invoice (stub - mock provider only)
    """
    # Create payment record
    payment = Payment(
        telegram_user_id=invoice_data.telegram_user_id,
        amount=invoice_data.amount,
        currency=invoice_data.currency,
        provider=invoice_data.provider,
        status=PaymentStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    db.add(payment)
    db.flush()  # Ensure payment.id is assigned before using it

    # Mock provider - generate fake wallet address
    if invoice_data.provider == "mock":
        payment.wallet_address = f"mock_wallet_{payment.id}"

    db.commit()
    db.refresh(payment)

    return InvoiceResponse(
        id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        provider=payment.provider,
        status=payment.status.value,
        wallet_address=payment.wallet_address,
        qr_code=None,  # Would generate QR code here
        expires_at=payment.expires_at,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    db: Session = Depends(get_db)
):
    """
    Get payment details
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.post("/{payment_id}/check")
async def check_payment(
    payment_id: int,
    db: Session = Depends(get_db)
):
    """
    Check payment status (stub - always returns pending for mock)
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # For mock provider, payment stays pending until manually confirmed
    return {
        "payment_id": payment.id,
        "status": payment.status.value,
        "is_completed": payment.status == PaymentStatus.COMPLETED,
    }


@router.post("/{payment_id}/confirm")
async def confirm_payment(
    payment_id: int,
    tx_hash: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Manually confirm a payment (for mock/testing)
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status == PaymentStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Payment already completed")

    payment.status = PaymentStatus.COMPLETED
    payment.completed_at = datetime.now(timezone.utc)
    payment.tx_hash = tx_hash or f"mock_tx_{payment_id}"

    db.commit()

    return {
        "payment_id": payment.id,
        "status": "completed",
        "tx_hash": payment.tx_hash,
    }


@router.post("/{payment_id}/cancel")
async def cancel_payment(
    payment_id: int,
    db: Session = Depends(get_db)
):
    """
    Cancel a pending payment
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Can only cancel pending payments")

    payment.status = PaymentStatus.FAILED
    db.commit()

    return {"payment_id": payment.id, "status": "cancelled"}


# ============================================================================
# WEBHOOK ENDPOINT (STUB)
# ============================================================================

@router.post("/webhook/{provider}")
async def payment_webhook(
    provider: str,
    db: Session = Depends(get_db)
):
    """
    Payment provider webhook endpoint (stub)

    This would handle callbacks from payment providers
    like crypto payment processors
    """
    # Stub implementation
    return {"received": True, "provider": provider}
