import json

import pytest
from fastapi import HTTPException

from src.api.middleware.auth import require_permission
from src.api.routes.portal_users import (
    AdminReplyRequest,
    reply_to_ticket,
    router as portal_users_router,
    support_router,
)
from src.database.models import AdminUser, AuditLog
from src.modules.subscription.subscription_models import ClientUser, SupportMessage


@pytest.mark.asyncio
async def test_support_permission_does_not_grant_client_crud(db_session):
    manager = AdminUser(
        username="support_manager",
        password_hash="not-used-in-this-test",
        role="manager",
        is_superadmin=False,
        is_active=True,
        permissions=json.dumps(["support"]),
    )
    db_session.add(manager)
    db_session.commit()

    payload = {
        "user_id": manager.id,
        "username": manager.username,
        "role": "manager",
        "is_superadmin": False,
    }

    assert await require_permission("support")(payload=payload, db=db_session) == payload
    with pytest.raises(HTTPException) as exc:
        await require_permission("clients")(payload=payload, db=db_session)
    assert exc.value.status_code == 403


def test_support_routes_are_isolated_from_portal_user_crud():
    support_paths = {route.path for route in support_router.routes}
    client_paths = {route.path for route in portal_users_router.routes}

    assert "/support-messages" in support_paths
    assert "/support-messages/{ticket_id}/reply" in support_paths
    assert not any(path.startswith("/support-messages") for path in client_paths)


def test_support_reply_is_attributed_to_exact_manager(db_session):
    manager = AdminUser(
        username="agent_alex",
        password_hash="not-used-in-this-test",
        role="manager",
        is_superadmin=False,
        is_active=True,
        permissions=json.dumps(["support"]),
    )
    customer = ClientUser(
        email="customer@example.test",
        username="customer_demo",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    db_session.add_all([manager, customer])
    db_session.flush()
    ticket = SupportMessage(
        user_id=customer.id,
        subject="Connection help",
        message="Please help with my device.",
        direction="user",
        status="open",
        is_read=False,
    )
    db_session.add(ticket)
    db_session.commit()

    result = reply_to_ticket(
        ticket.id,
        AdminReplyRequest(message="We are checking this for you."),
        current_admin={
            "user_id": manager.id,
            "username": manager.username,
            "role": "manager",
            "is_superadmin": False,
        },
        db=db_session,
    )

    assert result["status"] == "sent"
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_type == "support_ticket")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.user_id == manager.id
    assert audit.target_id == ticket.id
    assert audit.details["action"] == "support_reply"
    assert audit.details["reply_id"] == result["id"]
