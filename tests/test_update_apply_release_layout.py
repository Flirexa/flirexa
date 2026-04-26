import hashlib
import os
import subprocess
import tarfile
from pathlib import Path


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


def _run_apply(tmp_path: Path, install_dir: Path, staging_dir: Path, package_path: Path, target_version: str) -> subprocess.CompletedProcess[str]:
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
            "REQUIRES_MIGRATION": "false",
            "REQUIRES_RESTART": "true",
            "SYSTEMD_UNIT_DIR": str(units_dir),
        }
    )
    return subprocess.run(
        ["bash", str(Path(__file__).resolve().parent.parent / "update_apply.sh")],
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


def test_update_apply_uses_release_layout_for_legacy_spongebot_with_template_adaptation(tmp_path: Path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    _write(install_dir / "VERSION", "1.2.82")
    _write(install_dir / ".env", "API_SERVICE=spongebot-api\n")
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
    _write(install_dir / ".env", "API_SERVICE=spongebot-api\n")
    (install_dir / "releases").mkdir()
    current = install_dir / "current"
    current.symlink_to(install_dir)

    staging_dir, package_path = _prepare_staging(tmp_path, "1.2.83", with_vpnmanager_units=False)
    proc = _run_apply(tmp_path, install_dir, staging_dir, package_path, "1.2.83")

    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    assert (tmp_path / "backup" / "phase_symlink_switched").read_text() == "compat-inplace"
    assert (install_dir / "VERSION").read_text() == "1.2.83"
    assert current.resolve() == install_dir.resolve()
