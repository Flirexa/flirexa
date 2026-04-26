"""
VPN Management Studio Promo Codes API
Admin management of promotional codes (percent discounts and free days)
"""

import random
import string
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from loguru import logger

from ...database.connection import get_db
from ...modules.subscription.subscription_models import PromoCode

router = APIRouter()


# ============================================================================
# SCHEMAS
# ============================================================================

class PromoCodeCreate(BaseModel):
    code: Optional[str] = Field(None, description="Leave empty to auto-generate an 8-char code")
    discount_type: str = Field(..., description="'percent' or 'days'")
    discount_value: float = Field(..., gt=0, description="e.g. 20 for 20% or 7 for 7 free days")
    max_uses: Optional[int] = Field(None, ge=1, description="Max redemptions; None = unlimited")
    applies_to_tier: Optional[str] = Field(None, description="Restrict to a specific tier; None = all tiers")
    min_duration_days: Optional[int] = Field(None, ge=1, description="Minimum subscription duration to qualify")
    expires_at: Optional[datetime] = Field(None, description="UTC expiry datetime; None = never expires")

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, v):
        if v not in ("percent", "days"):
            raise ValueError("discount_type must be 'percent' or 'days'")
        return v

    @field_validator("discount_value")
    @classmethod
    def validate_discount_value(cls, v, info):
        discount_type = info.data.get("discount_type")
        if discount_type == "percent" and v > 100:
            raise ValueError("Percent discount cannot exceed 100")
        return v


class PromoCodeUpdate(BaseModel):
    is_active: Optional[bool] = None
    max_uses: Optional[int] = Field(None, ge=0)
    expires_at: Optional[datetime] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = Field(None, gt=0)
    applies_to_tier: Optional[str] = None


class PromoCodeValidateRequest(BaseModel):
    code: str = Field(..., min_length=1)
    tier: str = Field(..., min_length=1)
    duration_days: int = Field(..., ge=1)


class PromoCodeSummary(BaseModel):
    id: int
    code: str
    discount_type: str
    discount_value: float
    max_uses: Optional[int]
    used_count: int
    applies_to_tier: Optional[str]
    min_duration_days: Optional[int]
    is_active: bool
    expires_at: Optional[str]
    created_by: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class PromoCodeStats(BaseModel):
    total_codes: int = 0
    active_codes: int = 0
    total_uses: int = 0
    top_used: List[dict] = []


# ============================================================================
# HELPERS
# ============================================================================

def _dt_str(dt) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _generate_code(length: int = 8) -> str:
    """Generate a random uppercase alphanumeric code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def _serialize_promo_code(promo: PromoCode) -> dict:
    return {
        "id": promo.id,
        "code": promo.code,
        "discount_type": promo.discount_type,
        "discount_value": promo.discount_value,
        "max_uses": promo.max_uses,
        "used_count": promo.used_count,
        "applies_to_tier": promo.applies_to_tier,
        "min_duration_days": promo.min_duration_days,
        "is_active": promo.is_active,
        "expires_at": _dt_str(promo.expires_at),
        "created_by": promo.created_by,
        "created_at": _dt_str(promo.created_at),
        "updated_at": _dt_str(promo.updated_at),
    }


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("")
async def list_promo_codes(
    search: Optional[str] = Query(None, description="Search by code (partial match)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List promo codes with optional search and pagination"""
    query = db.query(PromoCode)

    if search:
        pattern = f"%{search.upper()}%"
        query = query.filter(PromoCode.code.ilike(pattern))

    if is_active is not None:
        query = query.filter(PromoCode.is_active == is_active)

    total = query.count()
    promos = query.order_by(PromoCode.id.desc()).offset(offset).limit(limit).all()

    items = [_serialize_promo_code(p) for p in promos]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/stats", response_model=PromoCodeStats)
async def get_promo_code_stats(db: Session = Depends(get_db)):
    """Stats: total codes, active codes, total uses, top used codes"""
    total_codes = db.query(func.count(PromoCode.id)).scalar() or 0

    now = datetime.now(timezone.utc)
    active_codes = db.query(func.count(PromoCode.id)).filter(
        PromoCode.is_active == True
    ).scalar() or 0

    total_uses = db.query(func.sum(PromoCode.used_count)).scalar() or 0

    top_used_rows = (
        db.query(PromoCode)
        .filter(PromoCode.used_count > 0)
        .order_by(PromoCode.used_count.desc())
        .limit(5)
        .all()
    )
    top_used = [
        {
            "id": p.id,
            "code": p.code,
            "used_count": p.used_count,
            "discount_type": p.discount_type,
            "discount_value": p.discount_value,
        }
        for p in top_used_rows
    ]

    return {
        "total_codes": total_codes,
        "active_codes": active_codes,
        "total_uses": int(total_uses),
        "top_used": top_used,
    }


@router.post("", status_code=201)
async def create_promo_code(data: PromoCodeCreate, db: Session = Depends(get_db)):
    """Create a new promo code. Code is uppercased; auto-generated if not provided."""
    if data.code:
        code = data.code.strip().upper()
        if not code:
            raise HTTPException(status_code=400, detail="Code cannot be blank")
    else:
        # Auto-generate, avoid collisions
        for _ in range(10):
            code = _generate_code(8)
            if not db.query(PromoCode).filter(PromoCode.code == code).first():
                break
        else:
            raise HTTPException(status_code=500, detail="Failed to generate a unique promo code")

    existing = db.query(PromoCode).filter(PromoCode.code == code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Promo code '{code}' already exists")

    promo = PromoCode(
        code=code,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        max_uses=data.max_uses,
        used_count=0,
        applies_to_tier=data.applies_to_tier,
        min_duration_days=data.min_duration_days,
        is_active=True,
        expires_at=data.expires_at,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)

    logger.info(
        f"Admin created promo code '{code}': "
        f"{data.discount_type}={data.discount_value}, "
        f"max_uses={data.max_uses}, tier={data.applies_to_tier}"
    )
    return _serialize_promo_code(promo)


@router.put("/{code_id}")
async def update_promo_code(code_id: int, data: PromoCodeUpdate, db: Session = Depends(get_db)):
    """Update a promo code (is_active, max_uses, expires_at, discount_value)"""
    promo = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")

    if data.is_active is not None:
        promo.is_active = data.is_active
    if data.max_uses is not None:
        promo.max_uses = data.max_uses if data.max_uses > 0 else None
    if data.expires_at is not None:
        promo.expires_at = data.expires_at
    if data.discount_type is not None:
        promo.discount_type = data.discount_type
    if data.discount_value is not None:
        promo.discount_value = data.discount_value
    if data.applies_to_tier is not None:
        promo.applies_to_tier = data.applies_to_tier if data.applies_to_tier else None

    db.commit()
    db.refresh(promo)

    logger.info(f"Admin updated promo code '{promo.code}' (id={code_id})")
    return _serialize_promo_code(promo)


@router.delete("/{code_id}")
async def delete_promo_code(code_id: int, db: Session = Depends(get_db)):
    """Delete a promo code"""
    promo = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")

    code = promo.code
    db.delete(promo)
    db.commit()

    logger.info(f"Admin deleted promo code '{code}' (id={code_id})")
    return {"message": f"Promo code '{code}' deleted"}


@router.post("/validate")
async def validate_promo_code(data: PromoCodeValidateRequest, db: Session = Depends(get_db)):
    """
    Validate a promo code for use.

    Checks:
    - Code exists
    - is_active
    - not expired (expires_at)
    - usage limit not reached (max_uses)
    - tier restriction (applies_to_tier)
    - minimum duration (min_duration_days)
    """
    code = data.code.strip().upper()

    promo = db.query(PromoCode).filter(PromoCode.code == code).first()
    if not promo:
        return {
            "valid": False,
            "discount_type": None,
            "discount_value": None,
            "error": "Promo code not found",
        }

    # Check is_active
    if not promo.is_active:
        return {
            "valid": False,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "error": "Promo code is inactive",
        }

    # Check expiry
    if promo.expires_at:
        exp = promo.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= exp:
            return {
                "valid": False,
                "discount_type": promo.discount_type,
                "discount_value": promo.discount_value,
                "error": "Promo code has expired",
            }

    # Check usage limit
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        return {
            "valid": False,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "error": "Promo code usage limit has been reached",
        }

    # Check tier restriction
    if promo.applies_to_tier and promo.applies_to_tier != data.tier:
        return {
            "valid": False,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "error": f"Promo code is only valid for the '{promo.applies_to_tier}' tier",
        }

    # Check minimum duration
    if promo.min_duration_days is not None and data.duration_days < promo.min_duration_days:
        return {
            "valid": False,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "error": f"Promo code requires a minimum subscription of {promo.min_duration_days} days",
        }

    logger.info(
        f"Promo code '{code}' validated for tier='{data.tier}', duration={data.duration_days} days"
    )
    return {
        "valid": True,
        "discount_type": promo.discount_type,
        "discount_value": promo.discount_value,
        "error": None,
    }
