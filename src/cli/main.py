from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from loguru import logger


CLI_ENV_ERROR: str | None = None


def _load_cli_env() -> None:
    """
    Locate and load the install's `.env`. Two layouts to support:
      - compat-inplace: code at <ROOT>/src/cli/main.py     → .env at <ROOT>/.env
      - release-layout: code at <ROOT>/releases/<ver>/src/cli/main.py
                        → .env at <ROOT>/.env (two levels up from release dir)

    Walk up from this file looking for the first `.env`, with bounded depth so
    we never accidentally pick up a `.env` from a user's home or /etc.
    """
    global CLI_ENV_ERROR
    here = Path(__file__).resolve()
    candidates = []
    # parents[0]=cli, [1]=src, [2]=<release-or-install-root>, [3]=releases, [4]=<install-root-in-release-layout>
    for depth in range(2, 5):
        try:
            candidates.append(here.parents[depth] / ".env")
        except IndexError:
            break
    # explicit final fallbacks for known install paths
    candidates.append(Path("/opt/vpnmanager/.env"))
    candidates.append(Path("/opt/spongebot/.env"))

    seen: set[Path] = set()
    for env_file in candidates:
        if env_file in seen:
            continue
        seen.add(env_file)
        if env_file.exists():
            try:
                load_dotenv(env_file, override=False)
                return
            except PermissionError:
                CLI_ENV_ERROR = (
                    f"Cannot read {env_file}. Run vpnmanager with sudo or as root."
                )
                return


_load_cli_env()

from src.cli.output import (
    render_backup_result,
    render_restore_result,
    render_health,
    render_json,
    render_license_status,
    render_services_restart_result,
    render_services_status,
    render_status,
    render_support_bundle_result,
)
from src.modules.backup_cli import create_backup_command
from src.modules.restore_cli import create_restore_command
from src.modules.operational_mode import set_maintenance_mode
from src.modules.service_cli import create_services_restart_command
from src.modules.support_bundle import create_support_bundle
from src.modules.system_status.collector import collect_system_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vpnmanager")

    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("status", "show overall system status"),
        ("health", "run health checks"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--json", action="store_true", help="machine-readable JSON output")

    license_parser = subparsers.add_parser("license", help="license operations")
    license_subparsers = license_parser.add_subparsers(dest="license_command", required=True)
    license_status = license_subparsers.add_parser("status", help="show license status")
    license_status.add_argument("--json", action="store_true", help="machine-readable JSON output")

    services_parser = subparsers.add_parser("services", help="service operations")
    services_subparsers = services_parser.add_subparsers(dest="services_command", required=True)
    services_status = services_subparsers.add_parser("status", help="show services status")
    services_status.add_argument("--json", action="store_true", help="machine-readable JSON output")
    services_restart = services_subparsers.add_parser("restart", help="restart managed product services")
    restart_scope = services_restart.add_mutually_exclusive_group()
    restart_scope.add_argument("--api", action="store_true", help="restart API service only")
    restart_scope.add_argument("--portal", action="store_true", help="restart client portal only")
    restart_scope.add_argument("--worker", action="store_true", help="restart worker only")
    restart_scope.add_argument("--bots", action="store_true", help="restart bot services only")
    restart_scope.add_argument("--all", action="store_true", help="restart all managed product services")
    services_restart.add_argument("--yes", action="store_true", help="confirm full service restart")
    services_restart.add_argument("--json", action="store_true", help="machine-readable JSON output")

    maintenance = subparsers.add_parser("maintenance", help="toggle maintenance mode")
    maintenance_sub = maintenance.add_subparsers(dest="maintenance_command", required=True)
    maintenance_on = maintenance_sub.add_parser("on", help="enable maintenance mode")
    maintenance_on.add_argument("--reason", required=True, help="maintenance reason")
    maintenance_on.add_argument("--json", action="store_true", help="machine-readable JSON output")
    maintenance_off = maintenance_sub.add_parser("off", help="disable maintenance mode")
    maintenance_off.add_argument("--json", action="store_true", help="machine-readable JSON output")

    bundle = subparsers.add_parser("support-bundle", help="collect diagnostic support bundle")
    bundle.add_argument("--output", help="output directory for the archive")
    bundle.add_argument("--since", help="journalctl --since value")
    bundle.add_argument("--include-journal", action="store_true", help="include recent journal excerpts")
    bundle.add_argument("--include-update-logs", action="store_true", help="include last apply.log if available")
    bundle.add_argument("--redact-strict", action="store_true", help="redact aggressively")
    bundle.add_argument("--json", action="store_true", help="machine-readable JSON output")

    backup = subparsers.add_parser("backup", help="create product backup")
    backup_type_group = backup.add_mutually_exclusive_group()
    backup_type_group.add_argument("--full", action="store_true", help="create full backup")
    backup_type_group.add_argument("--db-only", action="store_true", help="create database-only backup")
    backup.add_argument("--output", help="output directory or explicit archive path")
    backup.add_argument("--name", help="optional backup label")
    backup.add_argument("--yes", action="store_true", help="reserved for future interactive confirmations")
    backup.add_argument("--json", action="store_true", help="machine-readable JSON output")

    restore = subparsers.add_parser("restore", help="restore product state from a backup archive")
    restore.add_argument("--archive", help="path to vpnmanager-backup-*.tar.gz")
    restore.add_argument("--from-dir", help="directory containing the restore archive")
    restore.add_argument("--yes", action="store_true", help="confirm destructive restore")
    restore.add_argument("--json", action="store_true", help="machine-readable JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    json_output = False
    if "--json" in raw_argv:
        json_output = True
        raw_argv = [arg for arg in raw_argv if arg != "--json"]

    parser = build_parser()
    args = parser.parse_args(raw_argv)

    if json_output or getattr(args, "json", False):
        logger.remove()

    if CLI_ENV_ERROR and os.geteuid() != 0:
        payload = {
            "success": False,
            "action": args.command,
            "error": CLI_ENV_ERROR,
        }
        if json_output or getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"RESULT: FAILED\nAction: {args.command}\nError: {CLI_ENV_ERROR}")
        return 1

    if args.command == "maintenance":
        enabled = args.maintenance_command == "on"
        reason = getattr(args, "reason", None)
        try:
            mode = set_maintenance_mode(enabled, reason=reason, source="cli", actor="vpnmanager")
            payload = {
                "success": True,
                "action": "maintenance_on" if enabled else "maintenance_off",
                "mode": mode.mode,
                "reason": mode.maintenance_reason,
            }
            if json_output or getattr(args, "json", False):
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"RESULT: SUCCESS\nMode: {mode.mode}\nReason: {mode.maintenance_reason or '-'}")
            return 0
        except Exception as exc:
            payload = {
                "success": False,
                "action": "maintenance_on" if enabled else "maintenance_off",
                "error": str(exc),
            }
            if json_output or getattr(args, "json", False):
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"RESULT: FAILED\nAction: {'maintenance_on' if enabled else 'maintenance_off'}\nError: {exc}")
            return 1

    if args.command == "support-bundle":
        result = create_support_bundle(
            output_dir=getattr(args, "output", None),
            since=getattr(args, "since", None),
            include_journal=getattr(args, "include_journal", False),
            include_update_logs=getattr(args, "include_update_logs", False),
            redact_strict=getattr(args, "redact_strict", False),
        )
        if json_output or getattr(args, "json", False):
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_support_bundle_result(result))
        return 0 if result.success else 1

    if args.command == "backup":
        backup_type = "db-only" if getattr(args, "db_only", False) else "full"
        result = create_backup_command(
            backup_type=backup_type,
            output=getattr(args, "output", None),
            name=getattr(args, "name", None),
        )
        if json_output or getattr(args, "json", False):
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_backup_result(result))
        return 0 if result.success else 1

    if args.command == "restore":
        if not getattr(args, "yes", False):
            if json_output or getattr(args, "json", False):
                payload = {
                    "success": False,
                    "action": "restore_full",
                    "error": "Restore requires confirmation; rerun with --yes",
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 1
            reply = input("Restore will overwrite database and local configuration. Continue? [y/N]: ").strip().lower()
            if reply not in {"y", "yes", "restore"}:
                print("RESULT: FAILED\nAction: restore failed\nError: confirmation declined")
                return 1
        result = create_restore_command(
            archive=getattr(args, "archive", None),
            from_dir=getattr(args, "from_dir", None),
        )
        if json_output or getattr(args, "json", False):
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_restore_result(result))
        return 0 if result.success else 1

    if args.command == "services" and args.services_command == "restart":
        scope = "all"
        for candidate in ("api", "portal", "worker", "bots", "all"):
            if getattr(args, candidate.replace("-", "_"), False):
                scope = "all" if candidate == "all" else candidate
                break
        if scope == "all" and not getattr(args, "yes", False):
            if json_output or getattr(args, "json", False):
                payload = {
                    "success": False,
                    "action": "services_restart",
                    "error": "Full service restart requires confirmation; rerun with --yes",
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 1
            reply = input("Restart all managed product services? [y/N]: ").strip().lower()
            if reply not in {"y", "yes", "restart"}:
                print("RESULT: FAILED\nAction: services restart failed\nError: confirmation declined")
                return 1
        result = create_services_restart_command(scope=scope)
        if json_output or getattr(args, "json", False):
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_services_restart_result(result))
        return 0 if result.success else 1

    status = collect_system_status()

    if json_output or getattr(args, "json", False):
        print(render_json(status))
    elif args.command == "status":
        print(render_status(status))
    elif args.command == "health":
        print(render_health(status))
    elif args.command == "license" and args.license_command == "status":
        print(render_license_status(status))
    elif args.command == "services" and args.services_command == "status":
        print(render_services_status(status))
    else:
        parser.error(f"Unknown command: {args.command}")

    if args.command == "health":
        return 1 if status.result == "failed" else 0
    if args.command == "services" and args.services_command == "status":
        return 1 if status.health.services.status == "failed" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
