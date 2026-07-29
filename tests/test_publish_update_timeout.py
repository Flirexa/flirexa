"""Release publisher timeout must be long enough but remain operator-bounded."""

import pytest

from tools import publish_update


def test_upload_timeout_defaults_to_fifteen_minutes(monkeypatch):
    monkeypatch.delenv("UPDATE_UPLOAD_TIMEOUT_SECONDS", raising=False)
    assert publish_update._upload_timeout_seconds() == 900


def test_upload_timeout_accepts_a_bounded_override(monkeypatch):
    monkeypatch.setenv("UPDATE_UPLOAD_TIMEOUT_SECONDS", "1200")
    assert publish_update._upload_timeout_seconds() == 1200


def test_package_upload_uses_the_full_timeout_while_writing(monkeypatch, tmp_path):
    package = tmp_path / "vpn-manager-v9.9.9.tar.gz"
    package.write_bytes(b"release")
    observed = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"version": "9.9.9"}

    def fake_post(*args, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        return Response()

    monkeypatch.setenv("UPDATE_UPLOAD_TIMEOUT_SECONDS", "1200")
    monkeypatch.setattr(publish_update, "ADMIN_TOKEN", "test-token")
    monkeypatch.setattr(publish_update.requests, "post", fake_post)
    publish_update._upload_package(
        "9.9.9", package, "patch", "test", "1.0.0", False, True, True,
    )
    assert observed["timeout"] == 1200


@pytest.mark.parametrize("value", ["fast", "59", "3601"])
def test_upload_timeout_rejects_invalid_or_unbounded_values(monkeypatch, value):
    monkeypatch.setenv("UPDATE_UPLOAD_TIMEOUT_SECONDS", value)
    with pytest.raises(SystemExit):
        publish_update._upload_timeout_seconds()
