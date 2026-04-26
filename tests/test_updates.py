"""
Tests for the update mechanism:
- Manifest signature verification
- Version comparison
- Update checker (no update / update available / error)
- UpdateManager state transitions
- API endpoints (status / check / history / apply guard / rollback guard)
- Update channel setting
- SHA-256 checksum verification
- Manifest field validation
"""

import asyncio
import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Helpers: generate real RSA key pair for tests
# ============================================================================

def _make_key_pair():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub, key


def _sign(manifest_data: dict, private_key) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    payload_dict = {k: v for k, v in manifest_data.items() if k != "signature"}
    payload_json = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True)
    payload_b64  = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
    sig_bytes = private_key.sign(
        payload_b64.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()


def _make_manifest(version="1.1.0", channel="stable", private_key=None) -> dict:
    m = {
        "schema_version":            1,
        "version":                   version,
        "published_at":              "2026-04-01T00:00:00+00:00",
        "release_date":              "2026-04-01T00:00:00+00:00",
        "channel":                   channel,
        "update_type":               "minor",
        "release_notes":             "Bug fixes",
        "changelog":                 "Bug fixes",
        "package_url":               f"https://example.com/updates/packages/vpn-manager-v{version}.tar.gz",
        "sha256":                    "a" * 64,
        "package_sha256":            "a" * 64,
        "package_size":              12345,
        "min_supported_version":     "1.0.0",
        "minimum_supported_version": "1.0.0",
        "rollback_supported":        True,
        "requires_migration":        False,
        "has_db_migrations":         False,
        "requires_restart":          True,
    }
    if private_key:
        m["signature"] = _sign(m, private_key)
    else:
        m["signature"] = "invalidsignature"
    return m


# ============================================================================
# Version comparison
# ============================================================================

class TestVersionComparison:

    def test_newer_returns_true(self):
        from src.modules.updates.checker import is_newer
        assert is_newer("1.1.0", "1.0.0") is True

    def test_older_returns_false(self):
        from src.modules.updates.checker import is_newer
        assert is_newer("0.9.0", "1.0.0") is False

    def test_same_returns_false(self):
        from src.modules.updates.checker import is_newer
        assert is_newer("1.0.0", "1.0.0") is False

    def test_patch_newer(self):
        from src.modules.updates.checker import is_newer
        assert is_newer("1.0.1", "1.0.0") is True

    def test_major_newer(self):
        from src.modules.updates.checker import is_newer
        assert is_newer("2.0.0", "1.9.9") is True

    def test_malformed_version(self):
        from src.modules.updates.checker import _parse_version
        assert _parse_version("bad") == (0, 0, 0)

    def test_is_compatible(self):
        from src.modules.updates.checker import is_compatible
        manifest = {"min_supported_version": "1.0.0"}
        assert is_compatible(manifest, "1.0.0") is True
        assert is_compatible(manifest, "0.9.0") is False
        assert is_compatible(manifest, "1.5.0") is True


# ============================================================================
# Manifest signature verification
# ============================================================================

class TestManifestVerification:

    def setup_method(self):
        self.priv_pem, self.pub_pem, self.priv_key = _make_key_pair()

    def test_valid_signature_passes(self):
        from src.modules.updates.checker import _verify_manifest_signature
        m = _make_manifest(private_key=self.priv_key)
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(self.pub_pem)
            pub_path = f.name
        try:
            with patch("src.modules.updates.checker._load_pub_key") as mock_load:
                from cryptography.hazmat.primitives import serialization
                mock_load.return_value = serialization.load_pem_public_key(self.pub_pem)
                assert _verify_manifest_signature(m) is True
        finally:
            os.unlink(pub_path)

    def test_invalid_signature_fails(self):
        from src.modules.updates.checker import _verify_manifest_signature
        m = _make_manifest(private_key=self.priv_key)
        m["signature"] = "AAAA"  # corrupt
        with patch("src.modules.updates.checker._load_pub_key") as mock_load:
            from cryptography.hazmat.primitives import serialization
            mock_load.return_value = serialization.load_pem_public_key(self.pub_pem)
            assert _verify_manifest_signature(m) is False

    def test_tampered_manifest_fails(self):
        from src.modules.updates.checker import _verify_manifest_signature
        m = _make_manifest(private_key=self.priv_key)
        m["version"] = "9.9.9"  # tamper after signing
        with patch("src.modules.updates.checker._load_pub_key") as mock_load:
            from cryptography.hazmat.primitives import serialization
            mock_load.return_value = serialization.load_pem_public_key(self.pub_pem)
            assert _verify_manifest_signature(m) is False

    def test_missing_signature_fails(self):
        from src.modules.updates.checker import _verify_manifest_signature
        m = _make_manifest(private_key=self.priv_key)
        del m["signature"]
        with patch("src.modules.updates.checker._load_pub_key") as mock_load:
            from cryptography.hazmat.primitives import serialization
            mock_load.return_value = serialization.load_pem_public_key(self.pub_pem)
            assert _verify_manifest_signature(m) is False

    def test_wrong_key_fails(self):
        from src.modules.updates.checker import _verify_manifest_signature
        m = _make_manifest(private_key=self.priv_key)
        _, wrong_pub_pem, _ = _make_key_pair()  # different key
        with patch("src.modules.updates.checker._load_pub_key") as mock_load:
            from cryptography.hazmat.primitives import serialization
            mock_load.return_value = serialization.load_pem_public_key(wrong_pub_pem)
            assert _verify_manifest_signature(m) is False


class TestUpdateStatusQueryCompatibility:

    def test_updates_route_active_query_casts_status_to_text(self):
        source = Path("src/api/routes/updates.py").read_text(encoding="utf-8")
        assert "cast(UpdateHistory.status, String).in_(" in source

    def test_manager_orphan_cleanup_casts_status_to_text(self):
        source = Path("src/modules/updates/manager.py").read_text(encoding="utf-8")
        assert "cast(UpdateHistory.status, String).in_(" in source


# ============================================================================
# Checksum verification
# ============================================================================

class TestChecksumVerification:

    def test_valid_checksum_passes(self, tmp_path):
        from src.modules.updates.checker import verify_package_checksum
        data = b"fake package content " * 1000
        pkg = tmp_path / "test.tar.gz"
        pkg.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert verify_package_checksum(pkg, expected) is True

    def test_wrong_checksum_fails(self, tmp_path):
        from src.modules.updates.checker import verify_package_checksum
        pkg = tmp_path / "test.tar.gz"
        pkg.write_bytes(b"data")
        assert verify_package_checksum(pkg, "a" * 64) is False


# ============================================================================
# Manifest required fields
# ============================================================================

class TestManifestFields:

    def test_missing_required_field(self):
        from src.modules.updates.checker import REQUIRED_FIELDS
        m = _make_manifest()
        del m["sha256"]
        missing = REQUIRED_FIELDS - set(m.keys())
        assert "sha256" in missing

    def test_all_required_fields_present(self):
        from src.modules.updates.checker import REQUIRED_FIELDS
        m = _make_manifest()
        assert REQUIRED_FIELDS <= set(m.keys())


# ============================================================================
# Fetch manifest (mocked HTTP)
# ============================================================================

class TestFetchManifest:

    def setup_method(self):
        self.priv_pem, self.pub_pem, self.priv_key = _make_key_pair()
        from src.modules.updates import checker
        checker._cache = None   # clear cache

    def _patch_pub_key(self):
        from cryptography.hazmat.primitives import serialization
        return patch(
            "src.modules.updates.checker._load_pub_key",
            return_value=serialization.load_pem_public_key(self.pub_pem),
        )

    @pytest.mark.asyncio
    async def test_fetch_success_returns_manifest(self):
        from src.modules.updates.checker import fetch_manifest, _cache
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        manifest = _make_manifest(private_key=self.priv_key)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = manifest

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with self._patch_pub_key(), patch("httpx.AsyncClient", return_value=mock_client):
            result, err = await fetch_manifest(channel="stable", force=True)

        assert err is None
        assert result["version"] == "1.1.0"

    @pytest.mark.asyncio
    async def test_fetch_404_returns_error(self):
        from src.modules.updates.checker import fetch_manifest
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result, err = await fetch_manifest(channel="stable", force=True)

        assert result is None
        assert "404" in err or "No manifest" in err

    @pytest.mark.asyncio
    async def test_fetch_invalid_signature_returns_error(self):
        from src.modules.updates.checker import fetch_manifest
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        manifest = _make_manifest(private_key=self.priv_key)
        manifest["signature"] = "CORRUPTED"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = manifest

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with self._patch_pub_key(), patch("httpx.AsyncClient", return_value=mock_client):
            result, err = await fetch_manifest(channel="stable", force=True)

        assert result is None
        assert "signature" in err.lower() or "invalid" in err.lower()

    @pytest.mark.asyncio
    async def test_fetch_verifies_raw_manifest_before_normalization(self):
        from src.modules.updates.checker import fetch_manifest
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        raw_manifest = {
            "schema_version": 1,
            "version": "1.2.81",
            "release_date": "2026-03-27T10:47:31.157509+00:00",
            "channel": "test",
            "update_type": "patch",
            "changelog": "legacy-only manifest",
            "package_url": "https://example.com/updates/packages/vpn-manager-v1.2.81.tar.gz",
            "package_sha256": "a" * 64,
            "minimum_supported_version": "1.2.72",
            "rollback_supported": True,
            "has_db_migrations": True,
            "requires_restart": True,
            "signature": "legacy-signature",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = raw_manifest
        mock_resp.content = json.dumps(raw_manifest).encode()

        observed = {}

        def fake_verify(manifest):
            observed["manifest"] = dict(manifest)
            return True

        with patch("httpx.AsyncClient") as mock_cls, \
             patch("src.modules.updates.checker._verify_manifest_signature", side_effect=fake_verify):
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = instance

            result, err = await fetch_manifest(channel="test", force=True)

        assert err is None
        assert observed["manifest"] == raw_manifest
        assert result["published_at"] == raw_manifest["release_date"]
        assert result["release_notes"] == raw_manifest["changelog"]
        assert result["sha256"] == raw_manifest["package_sha256"]

    @pytest.mark.asyncio
    async def test_check_up_to_date(self):
        from src.modules.updates.checker import check_for_update
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        manifest = _make_manifest(version="1.0.0", private_key=self.priv_key)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = manifest

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with self._patch_pub_key(), patch("httpx.AsyncClient", return_value=mock_client):
            result, err = await check_for_update("1.0.0", "stable", force=True)

        assert result is None   # up to date
        assert err is None

    @pytest.mark.asyncio
    async def test_check_update_available(self):
        from src.modules.updates.checker import check_for_update
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        manifest = _make_manifest(version="1.2.0", private_key=self.priv_key)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = manifest

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with self._patch_pub_key(), patch("httpx.AsyncClient", return_value=mock_client):
            result, err = await check_for_update("1.0.0", "stable", force=True)

        assert err is None
        assert result["version"] == "1.2.0"

    @pytest.mark.asyncio
    async def test_check_incompatible_min_version(self):
        from src.modules.updates.checker import check_for_update
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        manifest = _make_manifest(version="2.0.0", private_key=self.priv_key)
        manifest["min_supported_version"] = "1.5.0"
        manifest["minimum_supported_version"] = "1.5.0"
        # Re-sign after modifying
        manifest["signature"] = _sign(manifest, self.priv_key)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = manifest

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with self._patch_pub_key(), patch("httpx.AsyncClient", return_value=mock_client):
            result, err = await check_for_update("1.0.0", "stable", force=True)

        assert result is None
        assert "minimum" in err.lower() or "1.5.0" in err


# ============================================================================
# Manager helpers
# ============================================================================

class TestManagerHelpers:

    def test_get_current_version_reads_file(self, tmp_path):
        from src.modules.updates import manager
        version_file = tmp_path / "VERSION"
        version_file.write_text("1.2.3\n")
        with patch.object(manager, "_VERSION_FILE", version_file):
            assert manager.get_current_version() == "1.2.3"

    def test_get_current_version_missing_returns_default(self, tmp_path):
        from src.modules.updates import manager
        with patch.object(manager, "_VERSION_FILE", tmp_path / "MISSING"):
            assert manager.get_current_version() == "0.0.0"

    def test_get_active_update_id_none_when_empty(self):
        from src.modules.updates import manager
        old = manager._progress.copy()
        manager._progress.clear()
        try:
            assert manager.get_active_update_id() is None
        finally:
            manager._progress.update(old)

    def test_get_active_update_id_finds_in_progress(self):
        from src.modules.updates import manager
        manager._progress[9999] = {"status": "in_progress"}
        try:
            assert manager.get_active_update_id() == 9999
        finally:
            del manager._progress[9999]

    def test_get_progress_returns_none_for_unknown(self):
        from src.modules.updates import manager
        assert manager.get_progress(99999) is None

    def test_validate_extracted_release_accepts_expected_structure(self, tmp_path):
        from src.modules.updates.manager import _validate_extracted_release
        (tmp_path / "VERSION").write_text("1.2.79\n")
        (tmp_path / "requirements.txt").write_text("fastapi\n")
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        (tmp_path / "src").mkdir()
        assert _validate_extracted_release(tmp_path, "1.2.79") is None

    def test_validate_extracted_release_rejects_wrong_version(self, tmp_path):
        from src.modules.updates.manager import _validate_extracted_release
        (tmp_path / "VERSION").write_text("1.2.78\n")
        (tmp_path / "requirements.txt").write_text("fastapi\n")
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        (tmp_path / "src").mkdir()
        err = _validate_extracted_release(tmp_path, "1.2.79")
        assert "VERSION mismatch" in err


# ============================================================================
# API endpoints  (synchronous TestClient, same pattern as test_api.py)
# ============================================================================

@pytest.fixture
def updates_client(db_session):
    """HTTP TestClient with update routes wired up and admin auth bypassed."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.routes import updates as updates_module
    from src.api.middleware.auth import get_current_admin
    from src.database.connection import get_db

    app = FastAPI()
    app.include_router(updates_module.router, prefix="/api/v1/updates")

    def override_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "owner"}

    return TestClient(app)


class TestUpdatesAPI:

    def test_status_returns_current_version(self, updates_client):
        resp = updates_client.get("/api/v1/updates/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_version" in data
        assert "channel" in data

    def test_history_returns_list(self, updates_client):
        resp = updates_client.get("/api/v1/updates/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_apply_blocked_when_in_progress(self, updates_client):
        with patch("src.api.routes.updates.get_active_update_id", return_value=8888):
            resp = updates_client.post("/api/v1/updates/apply")
        assert resp.status_code == 409

    def test_apply_no_update_available(self, updates_client):
        async def _no_update(*a, **kw):
            return None, None
        with patch("src.api.routes.updates.check_for_update", new=_no_update):
            with patch("src.api.routes.updates.get_active_update_id", return_value=None):
                resp = updates_client.post("/api/v1/updates/apply")
        assert resp.status_code == 400
        assert "No update" in resp.json().get("detail", "")

    def test_apply_check_error(self, updates_client):
        async def _error(*a, **kw):
            return None, "Timeout"
        with patch("src.api.routes.updates.check_for_update", new=_error):
            with patch("src.api.routes.updates.get_active_update_id", return_value=None):
                resp = updates_client.post("/api/v1/updates/apply")
        assert resp.status_code == 400

    def test_rollback_blocked_when_in_progress(self, updates_client, db_session):
        from src.database.models import UpdateHistory, UpdateStatus
        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.SUCCESS,
            started_by="admin",
            rollback_available=True,
            backup_path="/tmp/fake_backup",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        with patch("src.api.routes.updates.get_active_update_id", return_value=8887):
            resp = updates_client.post(f"/api/v1/updates/rollback/{rec.id}")
        assert resp.status_code == 409

    def test_rollback_not_found(self, updates_client):
        resp = updates_client.post("/api/v1/updates/rollback/99999")
        assert resp.status_code == 404

    def test_rollback_not_available(self, updates_client, db_session):
        from src.database.models import UpdateHistory, UpdateStatus
        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.SUCCESS,
            started_by="admin",
            rollback_available=False,
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        with patch("src.api.routes.updates.get_active_update_id", return_value=None):
            resp = updates_client.post(f"/api/v1/updates/rollback/{rec.id}")
        assert resp.status_code == 400
        assert "not available" in resp.json().get("detail", "").lower()

    def test_progress_not_found(self, updates_client):
        resp = updates_client.get("/api/v1/updates/progress/99999")
        assert resp.status_code == 404

    def test_channel_get_and_set(self, updates_client):
        resp = updates_client.get("/api/v1/updates/channel")
        assert resp.status_code == 200
        assert resp.json()["channel"] in ("stable", "test")

        resp = updates_client.post("/api/v1/updates/channel", json={"channel": "test"})
        assert resp.status_code == 200
        assert resp.json()["channel"] == "test"

        resp = updates_client.post("/api/v1/updates/channel", json={"channel": "nightly"})
        assert resp.status_code == 400

        updates_client.post("/api/v1/updates/channel", json={"channel": "stable"})

    def test_log_not_found(self, updates_client):
        resp = updates_client.get("/api/v1/updates/log/99999")
        assert resp.status_code == 404

    def test_log_returns_content(self, updates_client, db_session):
        from src.database.models import UpdateHistory, UpdateStatus
        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.SUCCESS,
            started_by="admin",
            log="Step 1\nStep 2\nDone",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        resp = updates_client.get(f"/api/v1/updates/log/{rec.id}")
        assert resp.status_code == 200
        assert "Step 1" in resp.json()["log"]

    def test_apply_blocked_by_db_active_record(self, updates_client, db_session):
        """DB-level guard: APPLYING record in DB blocks new apply even if in-memory is clear."""
        from src.database.models import UpdateHistory, UpdateStatus
        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.APPLYING,
            started_by="admin",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)
        try:
            with patch("src.api.routes.updates.get_active_update_id", return_value=None):
                resp = updates_client.post("/api/v1/updates/apply")
            assert resp.status_code == 409
            assert str(rec.id) in resp.json().get("detail", "")
        finally:
            db_session.delete(rec)
            db_session.commit()

    def test_apply_rejects_downgrade(self, updates_client, db_session):
        """Version guard: cannot apply version that is not newer than current."""
        async def _same_version(*a, **kw):
            return _make_manifest(version="0.9.0"), None

        with patch("src.api.routes.updates.check_for_update", new=_same_version):
            with patch("src.api.routes.updates.get_active_update_id", return_value=None):
                with patch("src.api.routes.updates.get_current_version", return_value="1.0.0"):
                    resp = updates_client.post("/api/v1/updates/apply")
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert "not newer" in detail.lower() or "rejected" in detail.lower()

    def test_rollback_missing_backup_dir_rejected(self, updates_client, db_session):
        """Rollback is rejected if backup directory does not exist on disk."""
        from src.database.models import UpdateHistory, UpdateStatus
        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.SUCCESS,
            started_by="admin",
            rollback_available=True,
            backup_path="/nonexistent/backup/dir",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        with patch("src.api.routes.updates.get_active_update_id", return_value=None):
            resp = updates_client.post(f"/api/v1/updates/rollback/{rec.id}")
        assert resp.status_code == 400
        assert "backup" in resp.json().get("detail", "").lower()

    def test_progress_recovery_from_db(self, updates_client, db_session):
        """Progress endpoint falls back to DB when not in memory (e.g. after restart)."""
        from src.database.models import UpdateHistory, UpdateStatus
        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.SUCCESS,
            started_by="admin",
            log="all done",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        # Ensure record is NOT in memory progress dict
        with patch("src.api.routes.updates.get_progress", return_value=None):
            resp = updates_client.get(f"/api/v1/updates/progress/{rec.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data.get("from_db") is True


# ============================================================================
# Disk space preflight
# ============================================================================

class TestDiskSpacePreflight:

    def test_check_disk_space_returns_none_when_sufficient(self, tmp_path):
        from src.modules.updates.manager import _check_disk_space
        # There is definitely more than 0 MB free in tmp
        result = _check_disk_space(tmp_path, 0)
        assert result is None

    def test_check_disk_space_returns_error_when_insufficient(self, tmp_path):
        from src.modules.updates.manager import _check_disk_space
        import shutil
        real_free = shutil.disk_usage(tmp_path).free // (1024 * 1024)
        # Require way more than available
        result = _check_disk_space(tmp_path, real_free + 99999)
        assert result is not None
        assert "Insufficient" in result

    def test_check_disk_space_tolerates_missing_path(self, tmp_path):
        from src.modules.updates.manager import _check_disk_space
        # Should not raise — returns None on error
        with patch("shutil.disk_usage", side_effect=PermissionError("no access")):
            result = _check_disk_space(tmp_path, 100)
        assert result is None


# ============================================================================
# Orphan cleanup
# ============================================================================

class TestOrphanCleanup:

    def test_cleanup_marks_in_flight_as_failed(self, db_session):
        """cleanup_orphaned_updates() sets APPLYING/DOWNLOADING records to FAILED."""
        from src.database.models import UpdateHistory, UpdateStatus
        from unittest.mock import patch as _patch

        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.APPLYING,
            started_by="admin",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        # Patch at the import source so the function uses our test db_session
        with _patch("src.database.connection.SessionLocal", return_value=db_session):
            db_session.close = lambda: None   # prevent double-close
            from src.modules.updates.manager import cleanup_orphaned_updates
            cleanup_orphaned_updates()

        db_session.expire(rec)
        db_session.refresh(rec)
        assert rec.status == UpdateStatus.FAILED
        assert rec.error_message is not None
        assert "restart" in rec.error_message.lower()

    def test_cleanup_leaves_terminal_records_untouched(self, db_session):
        """cleanup_orphaned_updates() does not modify SUCCESS/FAILED/ROLLED_BACK records."""
        from src.database.models import UpdateHistory, UpdateStatus
        from unittest.mock import patch as _patch

        rec = UpdateHistory(
            from_version="1.0.0", to_version="1.1.0",
            status=UpdateStatus.SUCCESS,
            started_by="admin",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        with _patch("src.database.connection.SessionLocal", return_value=db_session):
            db_session.close = lambda: None
            from src.modules.updates.manager import cleanup_orphaned_updates
            cleanup_orphaned_updates()

        db_session.expire(rec)
        db_session.refresh(rec)
        assert rec.status == UpdateStatus.SUCCESS   # unchanged

    def test_cleanup_marks_post_migration_unknown_state_as_rollback_required(self, db_session, tmp_path):
        from src.database.models import UpdateHistory, UpdateStatus
        from unittest.mock import patch as _patch

        backup_dir = tmp_path / "backup_unknown"
        backup_dir.mkdir()
        (backup_dir / "phase_migration_started").write_text("started")

        rec = UpdateHistory(
            from_version="1.2.78",
            to_version="1.2.79",
            status=UpdateStatus.APPLYING,
            started_by="admin",
            backup_path=str(backup_dir),
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        with _patch("src.database.connection.SessionLocal", return_value=db_session):
            db_session.close = lambda: None
            from src.modules.updates.manager import cleanup_orphaned_updates
            cleanup_orphaned_updates()

        db_session.expire(rec)
        db_session.refresh(rec)
        assert rec.status == UpdateStatus.ROLLBACK_REQUIRED
        assert "interrupted after migration" in (rec.error_message or "")

    @pytest.mark.asyncio
    async def test_progress_marks_stale_applying_record_failed(self, db_session):
        """update_progress marks stale APPLYING records as FAILED when no script is running."""
        from datetime import datetime, timedelta, timezone
        from src.database.models import UpdateHistory, UpdateStatus
        from src.api.routes.updates import update_progress

        rec = UpdateHistory(
            from_version="1.0.0",
            to_version="1.1.0",
            status=UpdateStatus.APPLYING,
            started_by="admin",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=45),
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        result = await update_progress(rec.id, db_session)

        db_session.refresh(rec)
        assert rec.status == UpdateStatus.FAILED
        assert "stale" in (rec.error_message or "").lower()
        assert result["status"] == UpdateStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_progress_reconciles_successful_apply_after_api_restart(self, db_session, tmp_path):
        from src.database.models import UpdateHistory, UpdateStatus
        from src.api.routes.updates import update_progress
        from unittest.mock import patch as _patch

        backup_dir = tmp_path / "backup_success"
        backup_dir.mkdir()
        (backup_dir / "apply.exitcode").write_text("0")
        (backup_dir / "apply.log").write_text("[UPDATE] complete")
        (backup_dir / "phase_health_ok").write_text("ok")

        rec = UpdateHistory(
            from_version="1.2.84",
            to_version="1.2.85",
            status=UpdateStatus.APPLYING,
            started_by="admin",
            backup_path=str(backup_dir),
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        with _patch("src.database.connection.SessionLocal", return_value=db_session):
            db_session.close = lambda: None
            result = await update_progress(rec.id, db_session)

        db_session.refresh(rec)
        assert rec.status == UpdateStatus.SUCCESS
        assert result["status"] == UpdateStatus.SUCCESS.value


# ============================================================================
# Checker error messages
# ============================================================================

class TestCheckerErrorMessages:

    def setup_method(self):
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

    @pytest.mark.asyncio
    async def test_connect_timeout_message(self):
        import httpx
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        with patch("httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))
            mock_cls.return_value = instance

            from src.modules.updates.checker import fetch_manifest
            result, err = await fetch_manifest(force=True)

        assert result is None
        assert err is not None
        assert "timeout" in err.lower() or "connect" in err.lower()

    @pytest.mark.asyncio
    async def test_dns_failure_message(self):
        import httpx
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        with patch("httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(
                side_effect=httpx.ConnectError("Name or service not known")
            )
            mock_cls.return_value = instance

            from src.modules.updates.checker import fetch_manifest
            result, err = await fetch_manifest(force=True)

        assert result is None
        assert err is not None
        assert "dns" in err.lower() or "resolution" in err.lower() or "reach" in err.lower()

    @pytest.mark.asyncio
    async def test_server_500_message(self):
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.content = b"{}"

        with patch("httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = instance

            from src.modules.updates.checker import fetch_manifest
            result, err = await fetch_manifest(force=True)

        assert result is None
        assert "503" in err or "server error" in err.lower() or "later" in err.lower()

    @pytest.mark.asyncio
    async def test_invalid_package_url_scheme_rejected(self):
        """Manifest with ftp:// package_url should be rejected."""
        priv_pem, pub_pem, priv_key = _make_key_pair()
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        manifest = _make_manifest(private_key=priv_key)
        manifest["package_url"] = "ftp://evil.example.com/pkg.tar.gz"
        manifest["signature"] = _sign(manifest, priv_key)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = manifest
        mock_resp.content = json.dumps(manifest).encode()

        from cryptography.hazmat.primitives import serialization
        with patch("httpx.AsyncClient") as mock_cls, \
             patch("src.modules.updates.checker._load_pub_key",
                   return_value=serialization.load_pem_public_key(pub_pem)):
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = instance

            from src.modules.updates.checker import fetch_manifest
            result, err = await fetch_manifest(force=True)

        assert result is None
        assert err is not None
        assert "scheme" in err.lower() or "security" in err.lower()

    @pytest.mark.asyncio
    async def test_oversized_manifest_rejected(self):
        """Manifest response larger than 64KB should be rejected."""
        import src.modules.updates.checker as checker_mod
        checker_mod._cache = None

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"x" * (65 * 1024)   # 65KB
        mock_resp.json.return_value = {}

        with patch("httpx.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = instance

            from src.modules.updates.checker import fetch_manifest
            result, err = await fetch_manifest(force=True)

        assert result is None
        assert err is not None
        assert "large" in err.lower() or "64" in err


class TestUpdateArtifactCleanup:

    def test_cleanup_update_artifacts_trims_old_backups_and_staging(self, db_session, db_engine, monkeypatch, tmp_path):
        from datetime import timedelta
        from src.database.models import UpdateHistory, UpdateStatus
        from src.modules.updates.manager import _cleanup_update_artifacts

        backup_base = tmp_path / "backups" / "update_backups"
        staging_base = tmp_path / "staging"
        backup_base.mkdir(parents=True)
        staging_base.mkdir(parents=True)

        now = datetime.now(timezone.utc)

        keep_dir = backup_base / "pre_keep"
        keep_dir.mkdir()
        (keep_dir / "code.tar.gz").write_text("x")

        old_dir = backup_base / "pre_old"
        old_dir.mkdir()
        (old_dir / "code.tar.gz").write_text("x")

        stale_stage = staging_base / "update_111"
        stale_stage.mkdir()
        active_stage = staging_base / "update_222"
        active_stage.mkdir()

        old_ts = (now - timedelta(days=30)).timestamp()
        os.utime(old_dir, (old_ts, old_ts))
        old_stage_ts = (now - timedelta(hours=48)).timestamp()
        os.utime(stale_stage, (old_stage_ts, old_stage_ts))

        keep = UpdateHistory(
            from_version="1.0.0",
            to_version="1.0.1",
            update_type="patch",
            status=UpdateStatus.SUCCESS,
            backup_path=str(keep_dir),
            rollback_available=True,
            completed_at=now,
        )
        old = UpdateHistory(
            from_version="1.0.1",
            to_version="1.0.2",
            update_type="patch",
            status=UpdateStatus.SUCCESS,
            backup_path=str(old_dir),
            rollback_available=True,
            completed_at=now - timedelta(days=30),
        )
        active = UpdateHistory(
            from_version="1.0.2",
            to_version="1.0.3",
            update_type="patch",
            status=UpdateStatus.APPLYING,
            staging_path=str(active_stage),
            started_at=now,
        )
        db_session.add_all([keep, old, active])
        db_session.commit()

        from sqlalchemy.orm import sessionmaker

        monkeypatch.setattr('src.modules.updates.manager._BACKUP_BASE', backup_base)
        monkeypatch.setattr('src.modules.updates.manager._STAGING_BASE', staging_base)
        monkeypatch.setattr('src.modules.updates.manager._UPDATE_BACKUP_KEEP_COUNT', 1)
        monkeypatch.setattr('src.modules.updates.manager._UPDATE_BACKUP_KEEP_DAYS', 14)
        monkeypatch.setattr('src.modules.updates.manager._MAX_STAGING_AGE_HOURS', 24)
        monkeypatch.setattr('src.database.connection.SessionLocal', sessionmaker(bind=db_engine))

        result = _cleanup_update_artifacts(now=now)

        db_session.refresh(keep)
        db_session.refresh(old)
        db_session.refresh(active)

        assert result["deleted_update_backups"] == 1
        assert result["deleted_staging_dirs"] == 1
        assert keep_dir.exists()
        assert not old_dir.exists()
        assert stale_stage.exists() is False
        assert active_stage.exists() is True
        assert keep.rollback_available is True
        assert old.rollback_available is False
        assert old.backup_path is None

