"""
Admin Accounts Management API
Manages admin panel accounts: administrators (full access) and managers (scoped permissions).
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import AdminUser
from src.modules.subscription.subscription_models import ClientUser
from src.api.middleware.auth import hash_password
from src.api.middleware.license_gate import require_license_feature

# Manager / RBAC support is an Enterprise-tier feature. The single existing
# admin account flow stays in core (admin_auth router), so FREE installs
# can still log in and operate. This router is for *additional* admin /
# manager accounts and per-permission scoping — that's the paid surface.
router = APIRouter(dependencies=[Depends(require_license_feature("manager_rbac"))])

# Available permissions for manager role
AVAILABLE_PERMISSIONS = [
    "clients",   # Manage VPN clients
    "servers",   # Manage servers
    "payments",  # View/manage payments
    "support",   # Handle support tickets
    "stats",     # View statistics & reports
    "bots",      # Manage Telegram bots
    "settings",  # Change system settings
    "updates",   # Manage updates
    "backup",    # Backup & restore
    "logs",      # Audit logs & app logs
]


class CreateAdminAccountRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    role: str = Field(default="admin")  # "admin" | "manager"
    permissions: Optional[List[str]] = None  # only for manager role


class UpdateAdminAccountRequest(BaseModel):
    password: Optional[str] = Field(None, min_length=6, max_length=100)
    is_active: Optional[bool] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None


def _serialize_permissions(perms: Optional[List[str]]) -> Optional[str]:
    if perms is None:
        return None
    valid = [p for p in perms if p in AVAILABLE_PERMISSIONS]
    return json.dumps(valid)


def _deserialize_permissions(raw: Optional[str]) -> Optional[List[str]]:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _account_dict(admin: AdminUser) -> dict:
    return {
        "id": admin.id,
        "username": admin.username,
        "is_active": getattr(admin, "is_active", True),
        "role": admin.role,
        "is_superadmin": admin.is_superadmin,
        "permissions": _deserialize_permissions(admin.permissions),
        "created_at": admin.created_at.isoformat() if admin.created_at else None,
        "last_login": admin.last_login.isoformat() if admin.last_login else None,
    }


@router.get("/permissions")
async def list_permissions():
    """List all available permissions for manager role"""
    return {"permissions": AVAILABLE_PERMISSIONS}


@router.get("")
async def list_admin_accounts(db: Session = Depends(get_db)):
    """List all admin panel accounts (admins + managers)"""
    users = db.query(AdminUser).order_by(AdminUser.created_at).all()
    return [_account_dict(u) for u in users]


@router.post("", status_code=201)
async def create_admin_account(data: CreateAdminAccountRequest, db: Session = Depends(get_db)):
    """Create a new admin or manager account"""
    if data.role not in ("admin", "manager"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'manager'")

    if db.query(AdminUser).filter(AdminUser.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")

    # Also create a ClientUser so the account can log into client portal if needed
    existing_client = db.query(ClientUser).filter(ClientUser.email == data.email).first()

    pw_hash = hash_password(data.password)
    is_superadmin = data.role == "admin"
    permissions_json = _serialize_permissions(data.permissions) if data.role == "manager" else None

    admin_user = AdminUser(
        username=data.username,
        password_hash=pw_hash,
        is_superadmin=is_superadmin,
        is_active=True,
        role=data.role,
        permissions=permissions_json,
    )
    db.add(admin_user)

    if not existing_client:
        client_user = ClientUser(
            email=data.email,
            username=data.username,
            password_hash=pw_hash,
            role="admin",
            email_verified=True,
            is_active=True,
        )
        db.add(client_user)

    db.commit()
    db.refresh(admin_user)

    return _account_dict(admin_user)


@router.get("/{account_id}")
async def get_admin_account(account_id: int, db: Session = Depends(get_db)):
    """Get admin account details"""
    admin = db.query(AdminUser).filter(AdminUser.id == account_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Account not found")
    return _account_dict(admin)


@router.put("/{account_id}")
async def update_admin_account(
    account_id: int, data: UpdateAdminAccountRequest, db: Session = Depends(get_db)
):
    """Update admin account"""
    admin = db.query(AdminUser).filter(AdminUser.id == account_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Account not found")

    if data.password is not None:
        pw_hash = hash_password(data.password)
        admin.password_hash = pw_hash
        # Sync to linked ClientUser if exists
        client = db.query(ClientUser).filter(ClientUser.username == admin.username).first()
        if client:
            client.password_hash = pw_hash

    if data.is_active is not None:
        admin.is_active = data.is_active
        client = db.query(ClientUser).filter(ClientUser.username == admin.username).first()
        if client:
            client.is_active = data.is_active

    if data.role is not None:
        if data.role not in ("admin", "manager"):
            raise HTTPException(status_code=400, detail="role must be 'admin' or 'manager'")
        admin.role = data.role
        admin.is_superadmin = data.role == "admin"
        if data.role == "admin":
            admin.permissions = None  # admins have no restriction

    if data.permissions is not None and admin.role == "manager":
        admin.permissions = _serialize_permissions(data.permissions)

    db.commit()
    return _account_dict(admin)


@router.delete("/{account_id}")
async def delete_admin_account(account_id: int, db: Session = Depends(get_db)):
    """Delete admin account"""
    admin = db.query(AdminUser).filter(AdminUser.id == account_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Account not found")

    # Remove linked ClientUser if exists
    client = db.query(ClientUser).filter(ClientUser.username == admin.username).first()
    if client:
        db.delete(client)

    db.delete(admin)
    db.commit()
    return {"status": "deleted"}
