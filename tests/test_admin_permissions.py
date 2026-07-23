import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.middleware.auth import require_permission, require_superadmin


class _Query:
    def __init__(self, admin=None, error=None):
        self._admin = admin
        self._error = error

    def filter(self, *_args):
        return self

    def first(self):
        if self._error:
            raise self._error
        return self._admin


class _DB:
    def __init__(self, admin=None, error=None):
        self._admin = admin
        self._error = error

    def query(self, *_args):
        return _Query(self._admin, self._error)


def _admin(*, role="owner", is_superadmin=False, permissions=None, is_active=True):
    return SimpleNamespace(
        role=role,
        is_superadmin=is_superadmin,
        permissions=json.dumps(permissions or []),
        is_active=is_active,
    )


@pytest.mark.asyncio
async def test_owner_passes_superadmin_gate_without_legacy_flag():
    payload = {"user_id": 1, "role": "owner", "is_superadmin": False}
    assert await require_superadmin(payload=payload, db=_DB(_admin())) == payload


@pytest.mark.asyncio
async def test_full_admin_bypasses_scoped_permission_gate():
    payload = {"user_id": 1, "role": "admin", "is_superadmin": False}
    dep = require_permission("servers")
    assert await dep(payload=payload, db=_DB(_admin(role="admin"))) == payload


@pytest.mark.asyncio
async def test_manager_needs_the_requested_permission():
    payload = {"user_id": 2, "role": "manager", "is_superadmin": False}
    dep = require_permission("servers")

    assert await dep(
        payload=payload,
        db=_DB(_admin(role="manager", permissions=["servers"])),
    ) == payload

    with pytest.raises(HTTPException) as exc:
        await dep(
            payload=payload,
            db=_DB(_admin(role="manager", permissions=["clients"])),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_schema_drift_falls_back_only_for_unscoped_token_roles():
    error = RuntimeError("legacy schema")
    dep = require_permission("servers")

    owner = {"user_id": 1, "role": "owner", "is_superadmin": False}
    assert await dep(payload=owner, db=_DB(error=error)) == owner

    manager = {"user_id": 2, "role": "manager", "is_superadmin": False}
    with pytest.raises(HTTPException) as exc:
        await dep(payload=manager, db=_DB(error=error))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_inactive_owner_is_rejected_immediately():
    payload = {"user_id": 1, "role": "owner", "is_superadmin": True}
    with pytest.raises(HTTPException) as exc:
        await require_superadmin(
            payload=payload,
            db=_DB(_admin(is_superadmin=True, is_active=False)),
        )
    assert exc.value.status_code == 401
