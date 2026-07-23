"""
Tests for the Segments CRUD router (Task 3).

Uses the same TestClient + dependency-override harness as test_migrate_clients.py:
  - in-memory SQLite with StaticPool (same engine/session shared between test and app)
  - create_app(debug=True) factory
  - get_db overridden so the route and the test see the same data
  - get_current_admin overridden with a synthetic admin dict
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import create_app
from src.api.routes.system import get_db
from src.api.middleware.auth import get_current_admin
from src.database.models import AdminUser, Base, ClientSegment


@pytest.fixture(scope="module")
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    db = TestSession()
    db.add(AdminUser(
        id=1,
        username="testadmin",
        password_hash="not-used-by-overridden-auth",
        is_superadmin=True,
        is_active=True,
        role="owner",
    ))
    db.commit()
    db.close()

    app = create_app(debug=True)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = lambda: {
        "user_id": 1,
        "username": "testadmin",
        "is_superadmin": True,
    }

    with TestClient(app) as c:
        # also expose the session factory so tests can inspect the DB directly
        c._test_session_factory = TestSession
        yield c


def test_create_list_update_delete(client):
    # CREATE
    r = client.post("/api/v1/segments", json={"name": "VIP", "bandwidth_limit": 100})
    assert r.status_code == 201, r.text
    data = r.json()
    sid = data["id"]
    assert data["name"] == "VIP"
    assert data["bandwidth_limit"] == 100
    assert data["member_count"] == 0

    # LIST — first entry should be the one we just created
    r2 = client.get("/api/v1/segments")
    assert r2.status_code == 200, r2.text
    names = [s["name"] for s in r2.json()]
    assert "VIP" in names

    # UPDATE
    r3 = client.put(f"/api/v1/segments/{sid}", json={"notes": "n"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["notes"] == "n"

    # DELETE
    r4 = client.delete(f"/api/v1/segments/{sid}")
    assert r4.status_code == 200, r4.text

    # Verify row is gone via DB session
    db = client._test_session_factory()
    try:
        assert db.get(ClientSegment, sid) is None
    finally:
        db.close()


def test_duplicate_name_returns_409(client):
    client.post("/api/v1/segments", json={"name": "DUPE"})
    r = client.post("/api/v1/segments", json={"name": "DUPE"})
    assert r.status_code == 409, r.text
    # cleanup
    segs = client.get("/api/v1/segments").json()
    for s in segs:
        if s["name"] == "DUPE":
            client.delete(f"/api/v1/segments/{s['id']}")


def test_get_nonexistent_returns_404(client):
    r = client.put("/api/v1/segments/999999", json={"notes": "x"})
    assert r.status_code == 404, r.text

    r2 = client.delete("/api/v1/segments/999999")
    assert r2.status_code == 404, r2.text
