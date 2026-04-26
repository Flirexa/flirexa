from pathlib import Path


def test_systemd_templates_use_current_runtime_root():
    files = [
        Path("deploy/systemd/vpnmanager-api.service"),
        Path("deploy/systemd/vpnmanager-worker.service"),
        Path("deploy/systemd/vpnmanager-admin-bot.service"),
        Path("deploy/systemd/vpnmanager-client-bot.service"),
        Path("deploy/spongebot-client-portal.service"),
    ]

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "WorkingDirectory=" in text
        assert "/current" in text


def test_update_sh_can_adapt_vpnmanager_templates_for_legacy_prefixes():
    text = Path("update.sh").read_text(encoding="utf-8")
    assert 'source_prefix="vpnmanager"' in text
    assert 'install_service_unit_from_template' in text
    assert 's|vpnmanager-|${SERVICE_PREFIX}-|g' in text


def test_update_apply_log_scan_is_scoped_to_current_startup_window():
    text = Path("update_apply.sh").read_text(encoding="utf-8")
    assert 'STARTUP_LOG_SINCE="$(date --iso-8601=seconds)"' in text
    assert 'journalctl -u "$svc" "${since_args[@]}" -n 120 --no-pager' in text
