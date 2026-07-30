from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_installers_prefer_lock_with_legacy_fallback():
    expectations = {
        "install.sh": (
            '$INSTALL_DIR/requirements.lock',
            '$INSTALL_DIR/requirements.txt',
        ),
        "update.sh": (
            '$INSTALL_DIR/requirements.lock',
            '$INSTALL_DIR/requirements.txt',
        ),
        "update_apply.sh": (
            '$TARGET_RELEASE_DIR/requirements.lock',
            '$TARGET_RELEASE_DIR/requirements.txt',
        ),
    }

    for filename, required_fragments in expectations.items():
        source = (ROOT / filename).read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in source


def test_release_builder_includes_production_lock():
    builder = ROOT / "build_release.sh"
    if not builder.exists():
        pytest.skip("vendor release builder is intentionally absent from open core")
    source = builder.read_text(encoding="utf-8")

    assert "--exclude='requirements.lock'" not in source
    assert 'rm -rf "$BUILD_DIR/requirements.lock"' not in source
    assert "--exclude='requirements-runtime-bootstrap.lock'" not in source
    assert 'rm -rf "$BUILD_DIR/requirements-runtime-bootstrap.lock"' not in source
    assert "--exclude='requirements-dev.txt'" in source
    assert "--exclude='requirements-dev.lock'" in source


def test_runtime_lock_input_excludes_development_tools():
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    development = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    for package in ("pytest", "pytest-asyncio", "black", "ruff"):
        assert not any(
            line.strip().lower().startswith(f"{package}>=")
            for line in runtime.splitlines()
        )
        assert any(
            line.strip().lower().startswith(f"{package}>=")
            for line in development.splitlines()
        )


def test_fresh_installer_seeds_locked_build_backend_before_fallback():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")
    bootstrap = source.index('$INSTALL_DIR/requirements-runtime-bootstrap.lock')
    main_lock = source.index('$INSTALL_DIR/requirements.lock', bootstrap)
    fallback = source.index("--no-build-isolation", main_lock)

    assert bootstrap < main_lock < fallback
    assert "--timeout 60 --retries 5" in source
    assert "pip_install_retry" in source
    assert (ROOT / "requirements-runtime-bootstrap.lock").is_file()
