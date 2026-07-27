"""Security Phase C contracts for vendor signature trust anchors."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from src.modules.license import online_validator, server_config
from src.modules.updates import checker


SERVER_PAYLOAD_B64 = (
    "eyJwcmltYXJ5IjoiaHR0cHM6Ly9wcmltYXJ5LmludmFsaWQiLCJiYWNrdXAiOi"  # pragma: allowlist secret
    "JodHRwczovL2JhY2t1cC5pbnZhbGlkIiwiaXNzdWVkX2F0IjoiMjAyNi0wNy0yNF"  # pragma: allowlist secret
    "QwMDowMDowMCswMDowMCIsInZlcnNpb24iOjF9"  # pragma: allowlist secret
)
SERVER_SIGNATURE = (
    "g1gaB68JOS1Dl272zHLkgHKZgzXlKK7oO7NIBpRyhHZ_EsZhYlpHkkOpj7B0R0ov"  # pragma: allowlist secret
    "4uKZD7YAAdxKiDULeVGD3j9ko5jjuSTb4RrBE5ot7wmGQdOMpkNZ4E9b17JPxNg"  # pragma: allowlist secret
    "V-yZozjLkv6FZM5xQaaXkNeCEDS1gBfg7dAbU5dJoda3PQWY4px0Pr-w5-NUlTgF"  # pragma: allowlist secret
    "7FVt7kTl3cVN1JDyvIe5OIA9EnobSZYsBkzLCltXVAtRPv8YdqbefxoVrqSCu68Q"  # pragma: allowlist secret
    "WQTdHQKnOWMkGvlFbVcHJdLVK7HjcrJGY2XcPOQe9EzWKAZ7GaIVA6uPafM86rZ"  # pragma: allowlist secret
    "6ftyiTAyZ6Yvp1ilIs7lVS7A"  # pragma: allowlist secret
)
UPDATE_MANIFEST = {
    "schema_version": 1,
    "version": "9.9.9",
    "published_at": "2026-07-24T00:00:00+00:00",
    "channel": "test",
    "update_type": "patch",
    "release_notes": "Phase C fixture",
    "package_url": (
        "https://flirexa.biz/updates/packages/vpn-manager-v9.9.9.tar.gz"
    ),
    "sha256": "0" * 64,
    "min_supported_version": "1.0.0",
    "rollback_supported": True,
    "requires_migration": False,
    "requires_restart": True,
    "signature": (
        "BgEoUyzzFScFxoxpgO58GoZNMi6nHCjRTQIHwsk87vS8J8Xl0CUpKEd8nfO32E"  # pragma: allowlist secret
        "2l6EGCbPB-16YPPgrku4XyCameS_mEFe-Oyo2bh3B9suxDTIkFU9eOwVGPs_Bhz4"  # pragma: allowlist secret
        "rlACpZV-Kt4wKI0qCqDXfJ4tgQ-Zi32-y-nDx1mM1a0TJlekwRy9C0pzCDtmPqn"  # pragma: allowlist secret
        "sczCQ-bYmpfrps2ebYjsnSXdjH38hkq9wAfUzB8JPLltmEmTdmuYQbWGjMB7GSy"  # pragma: allowlist secret
        "gt-gQIDtu86pwAvPAa1AbpcHNHBn9VAY6okPNF12gU2u3iOCp-ch0RFyBUTlr9FN"  # pragma: allowlist secret
        "DkxjwdGW7USHyFek9zTWEOjb-w"  # pragma: allowlist secret
    ),
}

CURRENT_SERVER_FINGERPRINT = (
    "5fed415c26a29d5430beba65f351dc9b051f43ccf0a82479ee735799f2276224"  # pragma: allowlist secret
)
CURRENT_UPDATE_FINGERPRINT = (
    "6dccbde22db8d2bb81e922569b0296f2ece57511ad1add394f1094b0417610dc"  # pragma: allowlist secret
)
RETIRED_SERVER_FINGERPRINT = (
    "ff8aa99ee649b89f9c241b19f3ef432705f8ec313353c468b1db1ce0feb565b7"  # pragma: allowlist secret
)
RETIRED_UPDATE_FINGERPRINT = (
    "331417674815024ba8f9d2fb31256a7f2f7276c48d8183d4567c835dd854763b"  # pragma: allowlist secret
)


def _fingerprint(key) -> str:
    der = key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return sha256(der).hexdigest()


def _file_fingerprint(path: str) -> str:
    return _fingerprint(serialization.load_pem_public_key(Path(path).read_bytes()))


def test_only_current_server_key_is_trusted(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(
        "SERVER_VERIFY_PUBLIC_KEY_PATH",
        str(tmp_path / "attacker-controlled.pem"),
    )

    config_fingerprints = [_fingerprint(key) for key in server_config._load_pub_keys()]
    response_fingerprints = [
        _fingerprint(key) for key in online_validator._load_server_pub_keys()
    ]

    assert config_fingerprints == [CURRENT_SERVER_FINGERPRINT]
    assert response_fingerprints == [CURRENT_SERVER_FINGERPRINT]
    assert RETIRED_SERVER_FINGERPRINT not in config_fingerprints
    assert RETIRED_SERVER_FINGERPRINT not in response_fingerprints


def test_only_current_update_key_is_trusted(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(
        "UPDATE_PUBLIC_KEY_PATH",
        str(tmp_path / "attacker-controlled.pem"),
    )
    monkeypatch.setattr(checker, "_pub_keys_cache", None)

    fingerprints = [_fingerprint(key) for key in checker._load_pub_keys()]

    assert fingerprints == [CURRENT_UPDATE_FINGERPRINT]
    assert RETIRED_UPDATE_FINGERPRINT not in fingerprints


def test_current_server_signature_is_accepted_and_tampering_is_rejected():
    signed = {"payload": SERVER_PAYLOAD_B64, "signature": SERVER_SIGNATURE}

    assert server_config._verify_signed(signed) == {
        "primary": "https://primary.invalid",
        "backup": "https://backup.invalid",
        "issued_at": "2026-07-24T00:00:00+00:00",
        "version": 1,
    }
    assert online_validator._verify_response(
        SERVER_PAYLOAD_B64,
        SERVER_SIGNATURE,
    ) is not None

    tampered_payload = SERVER_PAYLOAD_B64[:-1] + (
        "A" if SERVER_PAYLOAD_B64[-1] != "A" else "B"
    )
    assert server_config._verify_signed(
        {"payload": tampered_payload, "signature": SERVER_SIGNATURE}
    ) is None
    assert online_validator._verify_response(
        tampered_payload,
        SERVER_SIGNATURE,
    ) is None


def test_current_update_signature_is_accepted_and_tampering_is_rejected():
    assert checker._verify_manifest_signature(UPDATE_MANIFEST) is True

    tampered = deepcopy(UPDATE_MANIFEST)
    tampered["version"] = "9.9.8"
    assert checker._verify_manifest_signature(tampered) is False


def test_distributed_public_keys_match_current_pins():
    assert _file_fingerprint("data/update_public.pem") == CURRENT_UPDATE_FINGERPRINT
    # Seller-side signing fixtures and the paid server-response verifier are
    # deliberately absent from the public open-core mirror. The private source
    # and customer-build context must still prove that every distributed copy
    # matches the current Phase-C pins.
    if Path("license_server").is_dir():
        assert _file_fingerprint("server_verify_public.pem") == CURRENT_SERVER_FINGERPRINT
        assert (
            _file_fingerprint("license_server/keys/server_verify_public.pem")
            == CURRENT_SERVER_FINGERPRINT
        )
        assert (
            _file_fingerprint("license_server/keys/update_public.pem")
            == CURRENT_UPDATE_FINGERPRINT
        )
