import hashlib
import os
import subprocess
import tarfile
from pathlib import Path


UPDATE_APPLY = Path(__file__).resolve().parents[1] / "update_apply.sh"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_fake_bin(bin_dir: Path) -> None:
    _write(
        bin_dir / "systemctl",
        """#!/bin/sh
set -eu
cmd=\"${1:-}\"
case \"$cmd\" in
  list-unit-files|list-units|daemon-reload|stop|start|restart|enable)
    exit 0
    ;;
  cat)
    unit=\"${2:-}\"
    file=\"${SYSTEMD_UNIT_DIR}/${unit}.service\"
    [ -f \"$file\" ] || file=\"${SYSTEMD_UNIT_DIR}/${unit}\"
    [ -f \"$file\" ] || exit 1
    cat \"$file\"
    ;;
  is-enabled|is-active)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
""",
    )
    _write(
        bin_dir / "curl",
        """#!/bin/sh
case "$*" in
  *"/health?detail=true"*)
    cat <<'EOF'
{"status":"healthy","database":"ok","background_tasks":"external_worker"}
EOF
    ;;
  *)
    cat <<'EOF'
{"status":"ok"}
EOF
    ;;
esac
""",
    )
    _write(bin_dir / "journalctl", "#!/bin/sh\nexit 0\n")
    _write(bin_dir / "sleep", "#!/bin/sh\nexit 0\n")
    for path in bin_dir.iterdir():
        path.chmod(0o755)


def _prepare_staging(tmp_path: Path, target_version: str, with_vpnmanager_units: bool) -> tuple[Path, Path]:
    staging = tmp_path / "staging"
    extract_root = staging / "extracted"
    pkg_root = extract_root / f"vpn-manager-v{target_version}"
    pkg_root.mkdir(parents=True, exist_ok=True)
    _write(pkg_root / "VERSION", target_version)
    _write(pkg_root / "alembic.ini", "[alembic]\nscript_location = alembic\n")
    (pkg_root / "src").mkdir(parents=True, exist_ok=True)
    _write(pkg_root / "src" / "__init__.py", "")
    protected_extension = pkg_root / "src" / "core" / "server_manager.abi3.so"
    protected_extension.parent.mkdir(parents=True, exist_ok=True)
    protected_extension.write_bytes(b"\x7fELFprotected-commercial-runtime")
    _write(pkg_root / "main.py", "print('ok')\n")
    if with_vpnmanager_units:
        unit_body = """[Service]\nWorkingDirectory=/opt/vpnmanager/current\nEnvironmentFile=/opt/vpnmanager/.env\nExecStart=/opt/vpnmanager/venv/bin/python /opt/vpnmanager/current/main.py api\n"""
        _write(pkg_root / "deploy/systemd/vpnmanager-api.service", unit_body)
        _write(pkg_root / "deploy/systemd/vpnmanager-worker.service", unit_body.replace("api", "worker_main.py"))
        _write(pkg_root / "deploy/systemd/vpnmanager-admin-bot.service", unit_body.replace("api", "admin-bot"))
        _write(pkg_root / "deploy/systemd/vpnmanager-client-bot.service", unit_body.replace("api", "client-bot"))
        _write(
            pkg_root / "deploy/vpnmanager-client-portal.service",
            "[Service]\nWorkingDirectory=/opt/vpnmanager/current\nEnvironmentFile=/opt/vpnmanager/.env\nExecStart=/opt/vpnmanager/venv/bin/python /opt/vpnmanager/current/client_portal_main.py\n",
        )
    package_path = tmp_path / f"vpn-manager-v{target_version}.tar.gz"
    with tarfile.open(package_path, "w:gz") as tf:
        tf.add(pkg_root, arcname=pkg_root.name)
    return staging, package_path


def _run_apply(
    tmp_path: Path,
    install_dir: Path,
    staging_dir: Path,
    package_path: Path,
    target_version: str,
    *,
    requires_migration: bool = False,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    backup_dir = tmp_path / "backup"
    units_dir = tmp_path / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    _make_fake_bin(fake_bin)
    sha = hashlib.sha256(package_path.read_bytes()).hexdigest()
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env.get('PATH', '/usr/bin:/bin')}",
            "INSTALL_DIR": str(install_dir),
            "STAGING_DIR": str(staging_dir),
            "BACKUP_DIR": str(backup_dir),
            "UPDATE_PACKAGE": str(package_path),
            "UPDATE_ID": "999",
            "TARGET_VERSION": target_version,
            "EXPECTED_PACKAGE_SHA256": sha,
            "EXPECTED_PACKAGE_SIZE": str(package_path.stat().st_size),
            "REQUIRES_MIGRATION": "true" if requires_migration else "false",
            "REQUIRES_RESTART": "true",
            "SYSTEMD_UNIT_DIR": str(units_dir),
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(UPDATE_APPLY)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_update_apply_uses_release_layout_when_runtime_is_ready(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    _write(install_dir / "VERSION", "1.2.82")
    _write(install_dir / ".env", "API_SERVICE=vpnmanager-api\n")
    (install_dir / "releases").mkdir()
    current = install_dir / "current"
    current.symlink_to(install_dir)

    staging_dir, package_path = _prepare_staging(tmp_path, "1.2.83", with_vpnmanager_units=True)
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "1.2.83")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    target_release = install_dir / "releases" / "1.2.83"
    assert target_release.is_dir()
    assert current.resolve() == target_release.resolve()
    assert (tmp_path / "backup" / "phase_symlink_switched").read_text().startswith("release:")
    assert (tmp_path / "backup" / "previous_release_path").read_text().strip().endswith("/releases/1.2.82")


def test_update_apply_uses_release_layout_for_legacy_prefix_with_template_adaptation(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    _write(install_dir / "VERSION", "1.2.82")
    _write(install_dir / ".env", "API_SERVICE=" + ("sponge" "bot") + "-api\n")
    (install_dir / "releases").mkdir()
    current = install_dir / "current"
    current.symlink_to(install_dir)

    staging_dir, package_path = _prepare_staging(tmp_path, "1.2.83", with_vpnmanager_units=True)
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "1.2.83")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    target_release = install_dir / "releases" / "1.2.83"
    assert target_release.is_dir()
    assert current.resolve() == target_release.resolve()
    assert (tmp_path / "backup" / "phase_symlink_switched").read_text().startswith("release:")


def test_update_apply_falls_back_to_inplace_when_release_layout_templates_missing(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    _write(install_dir / "VERSION", "1.2.82")
    _write(install_dir / ".env", "API_SERVICE=" + ("sponge" "bot") + "-api\n")
    (install_dir / "releases").mkdir()
    current = install_dir / "current"
    current.symlink_to(install_dir)

    staging_dir, package_path = _prepare_staging(tmp_path, "1.2.83", with_vpnmanager_units=False)
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "1.2.83")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    assert (tmp_path / "backup" / "phase_symlink_switched").read_text() == "compat-inplace"
    assert (install_dir / "VERSION").read_text() == "1.2.83"
    assert current.resolve() == install_dir.resolve()


def _seed_paid_install_state(install_dir: Path) -> dict[Path, bytes]:
    state = {
        Path(".env"): b"API_SERVICE=vpnmanager-api\nLICENSE_KEY=signed-paid-license\n",
        Path("data/license_cache.json"): b'{"plan":"enterprise","features":["corporate_vpn"]}\n',
        Path("data/license_servers.signed"): b"signed-license-server-list\n",
        Path("data/vpnmanager.db"): b"customer-database-bytes\n",
    }
    for relative, payload in state.items():
        path = install_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    _write(
        install_dir / "src/core/server_manager.py",
        "# old readable commercial implementation\n",
    )
    _write(
        install_dir / "src/web/frontend/src/design2/screens/D2Applications.vue",
        "<!-- old commercial Vue source -->\n",
    )
    return state


def _assert_paid_state_unchanged(install_dir: Path, state: dict[Path, bytes]) -> None:
    for relative, expected in state.items():
        assert (install_dir / relative).read_bytes() == expected


def test_release_layout_migration_preserves_paid_license_data_and_replaces_sources(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    _write(install_dir / "VERSION", "2.2.59")
    state = _seed_paid_install_state(install_dir)
    (install_dir / "releases").mkdir()
    current = install_dir / "current"
    current.symlink_to(install_dir)

    staging_dir, package_path = _prepare_staging(tmp_path, "2.2.60", with_vpnmanager_units=True)
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "2.2.60")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    _assert_paid_state_unchanged(install_dir, state)
    runtime = current.resolve()
    assert (runtime / "data").is_symlink()
    assert (runtime / "data").resolve() == (install_dir / "data").resolve()
    assert (runtime / "backups").is_symlink()
    assert (runtime / "backups").resolve() == (install_dir / "backups").resolve()
    for relative, expected in state.items():
        if relative.parts[0] == "data":
            assert (runtime / relative).read_bytes() == expected
    protected = (runtime / "src/core/server_manager.abi3.so").read_bytes()
    assert b"protected-commercial-runtime" in protected
    assert not (runtime / "src/core/server_manager.py").exists()
    assert not (runtime / "src/web/frontend").exists()


def test_inplace_migration_preserves_paid_license_data_and_prunes_obsolete_sources(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    _write(install_dir / "VERSION", "2.2.59")
    state = _seed_paid_install_state(install_dir)

    staging_dir, package_path = _prepare_staging(tmp_path, "2.2.60", with_vpnmanager_units=False)
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "2.2.60")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    _assert_paid_state_unchanged(install_dir, state)
    protected = (install_dir / "src/core/server_manager.abi3.so").read_bytes()
    assert b"protected-commercial-runtime" in protected
    assert not (install_dir / "src/core/server_manager.py").exists()
    assert not (install_dir / "src/web/frontend").exists()


def test_release_layout_merges_active_per_release_data_into_shared_storage(tmp_path: Path):
    install_dir = tmp_path / "install"
    old_release = install_dir / "releases" / "2.2.64"
    old_release.mkdir(parents=True)
    _write(install_dir / "VERSION", "2.2.64")
    _write(install_dir / ".env", "API_SERVICE=vpnmanager-api\n")
    _write(install_dir / "data/license_cache.json", "stale-shared-cache\n")
    _write(install_dir / "data/license_servers.signed", "operator-migrated-server-list\n")
    _write(old_release / "VERSION", "2.2.64")
    _write(old_release / "data/license_cache.json", "fresh-active-cache\n")
    _write(old_release / "data/first_startup_at.txt", "1234567890\n")
    current = install_dir / "current"
    current.symlink_to(old_release)

    staging_dir, package_path = _prepare_staging(tmp_path, "2.2.65", with_vpnmanager_units=True)
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "2.2.65")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    assert (install_dir / "data/license_cache.json").read_text() == "fresh-active-cache\n"
    assert (install_dir / "data/first_startup_at.txt").read_text() == "1234567890\n"
    assert (install_dir / "data/license_servers.signed").read_text() == "operator-migrated-server-list\n"
    assert (old_release / "data").is_symlink()
    assert (old_release / "data").resolve() == (install_dir / "data").resolve()
    new_release = install_dir / "releases" / "2.2.65"
    assert (new_release / "data").is_symlink()
    assert (new_release / "data").resolve() == (install_dir / "data").resolve()


def test_release_layout_collects_all_historical_backups_without_overwrite(tmp_path: Path):
    install_dir = tmp_path / "install"
    release_62 = install_dir / "releases" / "2.2.62"
    release_64 = install_dir / "releases" / "2.2.64"
    release_65 = install_dir / "releases" / "2.2.65"
    for release in (release_62, release_64, release_65):
        release.mkdir(parents=True)
        _write(release / "VERSION", release.name)
    _write(install_dir / "VERSION", "2.2.65")
    _write(install_dir / ".env", "API_SERVICE=vpnmanager-api\n")
    _write(
        install_dir / "backups/vpnmanager-backup-20260720-030000.tar.gz",
        "shared-copy\n",
    )
    _write(
        install_dir / "backups/update_backups/keep.txt",
        "update rollback state\n",
    )
    _write(
        release_62 / "backups/vpnmanager-backup-20260718-030000.tar.gz",
        "release-62\n",
    )
    _write(
        release_64 / "backups/vpnmanager-backup-20260720-030000.tar.gz",
        "different-collision\n",
    )
    _write(
        release_65 / "backups/vpnmanager-backup-20260727-030000.tar.gz",
        "latest\n",
    )
    _write(
        release_65 / "backups/backup_20260727_040000/manifest.json",
        '{"backup_id":"20260727_040000"}\n',
    )
    current = install_dir / "current"
    current.symlink_to(release_65)

    staging_dir, package_path = _prepare_staging(
        tmp_path, "2.2.66", with_vpnmanager_units=True
    )
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "2.2.66")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    shared = install_dir / "backups"
    assert (shared / "vpnmanager-backup-20260718-030000.tar.gz").read_text() == "release-62\n"
    assert (shared / "vpnmanager-backup-20260720-030000.tar.gz").read_text() == "shared-copy\n"
    assert (
        shared / "vpnmanager-backup-20260720-030000-from-2_2_64.tar.gz"
    ).read_text() == "different-collision\n"
    assert (shared / "vpnmanager-backup-20260727-030000.tar.gz").read_text() == "latest\n"
    assert (shared / "backup_20260727_040000/manifest.json").is_file()
    assert (shared / "update_backups/keep.txt").read_text() == "update rollback state\n"

    for version in ("2.2.62", "2.2.64", "2.2.65", "2.2.66"):
        release_backups = install_dir / "releases" / version / "backups"
        assert release_backups.is_symlink()
        assert release_backups.resolve() == shared.resolve()


def test_migration_reads_database_url_from_install_env(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    database = install_dir / "data" / "vpnmanager.db"
    _write(database, "sqlite-db\n")
    database_url = f"sqlite:///{database}"
    _write(install_dir / "VERSION", "2.2.64")
    _write(
        install_dir / ".env",
        f"API_SERVICE=vpnmanager-api\nDATABASE_URL={database_url}\n",
    )
    (install_dir / "releases").mkdir()
    (install_dir / "current").symlink_to(install_dir)

    fake_alembic = tmp_path / "fake-alembic"
    _write(
        fake_alembic,
        """#!/bin/sh
set -eu
case "${1:-}" in
  upgrade)
    [ "${DATABASE_URL:-}" = "${EXPECTED_DATABASE_URL}" ]
    ;;
  current|heads)
    echo "053"
    ;;
esac
""",
    )
    fake_alembic.chmod(0o755)
    staging_dir, package_path = _prepare_staging(tmp_path, "2.2.65", with_vpnmanager_units=True)

    proc = _run_apply(
        tmp_path,
        install_dir,
        staging_dir,
        package_path,
        "2.2.65",
        requires_migration=True,
        extra_env={
            "ALEMBIC_BIN": str(fake_alembic),
            "EXPECTED_DATABASE_URL": database_url,
        },
    )

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
