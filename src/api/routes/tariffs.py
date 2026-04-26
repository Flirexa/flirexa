"""
VPN Management Studio Admin - Tariff Management API
CRUD for subscription plans (SubscriptionPlan model)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from src.database.connection import get_db
from src.modules.subscription.subscription_models import (
    SubscriptionPlan, ClientPortalSubscription, SubscriptionStatus
)
from src.modules.subscription.subscription_manager import SubscriptionManager

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

class TariffCreate(BaseModel):
    tier: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    max_devices: int = Field(1, ge=1, le=100)
    traffic_limit_gb: Optional[int] = Field(None, ge=0)
    bandwidth_limit_mbps: Optional[int] = Field(None, ge=0)
    price_monthly_usd: float = Field(..., ge=0)
    price_quarterly_usd: Optional[float] = Field(None, ge=0)
    price_yearly_usd: Optional[float] = Field(None, ge=0)
    is_active: bool = True
    is_visible: bool = True
    display_order: int = 0
    # Corporate VPN: max number of corporate networks (0 = feature disabled)
    corp_networks: int = Field(0, ge=0)
    corp_sites: int = Field(0, ge=0)


class TariffUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    max_devices: Optional[int] = Field(None, ge=1, le=100)
    traffic_limit_gb: Optional[int] = Field(None, ge=0)
    bandwidth_limit_mbps: Optional[int] = Field(None, ge=0)
    price_monthly_usd: Optional[float] = Field(None, ge=0)
    price_quarterly_usd: Optional[float] = Field(None, ge=0)
    price_yearly_usd: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
    is_visible: Optional[bool] = None
    display_order: Optional[int] = None
    corp_networks: Optional[int] = Field(None, ge=0)
    corp_sites: Optional[int] = Field(None, ge=0)


class TariffResponse(BaseModel):
    id: int
    tier: str
    name: str
    description: Optional[str] = None
    max_devices: int
    traffic_limit_gb: Optional[int] = None
    bandwidth_limit_mbps: Optional[int] = None
    price_monthly_usd: float
    price_quarterly_usd: Optional[float] = None
    price_yearly_usd: Optional[float] = None
    is_active: bool
    is_visible: bool
    display_order: int
    corp_networks: int = 0
    corp_sites: int = 0

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_features(cls, obj):
        """Build response extracting corp_networks from the features JSON dict."""
        d = {
            "id": obj.id, "tier": obj.tier, "name": obj.name,
            "description": obj.description, "max_devices": obj.max_devices,
            "traffic_limit_gb": obj.traffic_limit_gb,
            "bandwidth_limit_mbps": obj.bandwidth_limit_mbps,
            "price_monthly_usd": obj.price_monthly_usd,
            "price_quarterly_usd": obj.price_quarterly_usd,
            "price_yearly_usd": obj.price_yearly_usd,
            "is_active": obj.is_active, "is_visible": obj.is_visible,
            "display_order": obj.display_order,
            "corp_networks": int((obj.features or {}).get("corp_networks", 0)),
            "corp_sites": int((obj.features or {}).get("corp_sites", 0)),
        }
        return cls(**d)


class ReorderItem(BaseModel):
    id: int
    display_order: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem]


# ═══════════════════════════════════════════════════════════════════════════
# CRUD ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_tariffs(
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """List all tariffs"""
    query = db.query(SubscriptionPlan)
    if active_only:
        query = query.filter(SubscriptionPlan.is_active == True)
    tariffs = query.order_by(SubscriptionPlan.display_order, SubscriptionPlan.id).all()
    return [TariffResponse.from_orm_with_features(t) for t in tariffs]


@router.post("/reorder")
async def reorder_tariffs(data: ReorderRequest, db: Session = Depends(get_db)):
    """Update display order for tariffs"""
    for item in data.items:
        tariff = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == item.id).first()
        if tariff:
            tariff.display_order = item.display_order

    db.commit()
    return {"status": "ok", "message": f"Reordered {len(data.items)} tariffs"}


@router.get("/{tariff_id}")
async def get_tariff(tariff_id: int, db: Session = Depends(get_db)):
    """Get tariff by ID"""
    tariff = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == tariff_id).first()
    if not tariff:
        raise HTTPException(status_code=404, detail="Tariff not found")
    return TariffResponse.from_orm_with_features(tariff)


@router.post("", status_code=201)
async def create_tariff(data: TariffCreate, db: Session = Depends(get_db)):
    """Create a new tariff"""
    # Check tier uniqueness
    existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.tier == data.tier).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Tariff with tier '{data.tier}' already exists")

    features = None
    if data.corp_networks > 0 or data.corp_sites > 0:
        features = {
            "corp_networks": data.corp_networks,
            "corp_sites": data.corp_sites,
        }

    tariff = SubscriptionPlan(
        tier=data.tier,
        name=data.name,
        description=data.description,
        max_devices=data.max_devices,
        traffic_limit_gb=data.traffic_limit_gb,
        bandwidth_limit_mbps=data.bandwidth_limit_mbps,
        price_monthly_usd=data.price_monthly_usd,
        price_quarterly_usd=data.price_quarterly_usd,
        price_yearly_usd=data.price_yearly_usd,
        is_active=data.is_active,
        is_visible=data.is_visible,
        display_order=data.display_order,
        features=features,
    )

    db.add(tariff)
    db.commit()
    db.refresh(tariff)

    logger.info(f"Created tariff: {tariff.tier} ({tariff.name}) - ${tariff.price_monthly_usd}/mo")
    return TariffResponse.from_orm_with_features(tariff)


@router.put("/{tariff_id}")
async def update_tariff(tariff_id: int, data: TariffUpdate, db: Session = Depends(get_db)):
    """Update a tariff"""
    tariff = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == tariff_id).first()
    if not tariff:
        raise HTTPException(status_code=404, detail="Tariff not found")

    update_data = data.model_dump(exclude_unset=True)
    # Handle corp_networks separately — stored in features JSON, not a direct column
    corp_networks = update_data.pop("corp_networks", None)
    corp_sites = update_data.pop("corp_sites", None)
    for field, value in update_data.items():
        setattr(tariff, field, value)
    if corp_networks is not None or corp_sites is not None:
        current_features = dict(tariff.features or {})
        if corp_networks is not None:
            current_features["corp_networks"] = corp_networks
        if corp_sites is not None:
            current_features["corp_sites"] = corp_sites
        if not current_features.get("corp_networks", 0) and not current_features.get("corp_sites", 0):
            tariff.features = None
        else:
            tariff.features = current_features

    db.commit()
    db.refresh(tariff)

    logger.info(f"Updated tariff #{tariff_id}: {tariff.tier}")
    return TariffResponse.from_orm_with_features(tariff)


@router.delete("/{tariff_id}")
async def delete_tariff(tariff_id: int, db: Session = Depends(get_db)):
    """Soft-delete a tariff (set is_active=False)"""
    tariff = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == tariff_id).first()
    if not tariff:
        raise HTTPException(status_code=404, detail="Tariff not found")

    # Check for active subscriptions using this tier
    active_subs_count = db.query(ClientPortalSubscription).filter(
        ClientPortalSubscription.tier == tariff.tier,
        ClientPortalSubscription.status == SubscriptionStatus.ACTIVE,
    ).count()

    tariff.is_active = False
    tariff.is_visible = False
    db.commit()

    warning = None
    if active_subs_count > 0:
        warning = f"{active_subs_count} active subscription(s) still use this tier"

    logger.info(f"Deleted (soft) tariff #{tariff_id}: {tariff.tier}")
    response = {"status": "ok", "message": f"Tariff '{tariff.name}' deactivated"}
    if warning:
        response["warning"] = warning
    return response


# ═══════════════════════════════════════════════════════════════════════════
# SIMULATE PAYMENT (TEST MODE)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/simulate-payment/{invoice_id}")
async def simulate_payment(invoice_id: str, db: Session = Depends(get_db)):
    """
    Test mode: simulate successful payment without actual crypto.
    Triggers full payment flow: subscription upgrade + WG limits.
    """
    manager = SubscriptionManager(db)
    payment = manager.get_payment_by_invoice(invoice_id)

    if not payment:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if payment.status == "completed":
        raise HTTPException(status_code=400, detail="Payment already completed")

    success = manager.complete_payment(invoice_id, tx_hash="SIMULATED")

    return {
        "status": "ok",
        "message": "Payment simulated successfully",
        "success": success,
        "user_id": payment.user_id,
        "tier": payment.subscription_tier,
        "amount_usd": payment.amount_usd,
    }
