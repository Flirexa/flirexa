from datetime import datetime, timezone

from src.api import scheduler
from src.modules.subscription.subscription_models import (
    ClientPortalSubscription,
    ClientUser,
)


def test_notification_marker_uses_new_json_value_and_persists(db_session):
    user = ClientUser(
        username="notification-dedup",
        email="notification-dedup@example.test",
        password_hash="test-only",
    )
    db_session.add(user)
    db_session.flush()
    subscription = ClientPortalSubscription(
        user_id=user.id,
        tier="basic",
        notification_sent_at={"7day": "2026-07-20T00:00:00+00:00"},
    )
    db_session.add(subscription)
    db_session.commit()

    original = subscription.notification_sent_at
    updated = scheduler._add_notification_marker(
        original, "3day", datetime(2026, 7, 30, tzinfo=timezone.utc)
    )
    assert updated is not original
    assert "3day" not in original

    subscription.notification_sent_at = updated
    subscription_id = subscription.id
    db_session.commit()
    db_session.expunge_all()

    reloaded = db_session.get(ClientPortalSubscription, subscription_id)
    assert set(reloaded.notification_sent_at) == {"7day", "3day"}
