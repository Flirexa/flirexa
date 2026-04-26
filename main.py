#!/usr/bin/env python3
"""
VPN Manager - WireGuard VPN Management Platform
Main entry point
"""

import sys
import os
import argparse
from loguru import logger
from dotenv import load_dotenv

# Load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Add project root and src/ to path (src/ needed for PyArmor runtime lookup)
_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "src"))


def setup_logging(level: str = "INFO", log_file: str = None):
    """Configure logging — delegates to centralized log_config for the api component."""
    from src.modules.log_config import setup_logging as _setup
    import os
    if level:
        os.environ.setdefault("LOG_LEVEL", level)
    _setup("api", level=level)


def run_api(host: str, port: int, reload: bool = False):
    """Run the FastAPI server"""
    from src.api.main import run_server
    run_server(host=host, port=port, reload=reload)


def run_admin_bot():
    """Run the admin Telegram bot"""
    from src.bots.admin_bot import main
    main()


def run_client_bot():
    """Run the client Telegram bot"""
    from src.bots.client_bot import main
    main()


def run_migration(clients_json: str, config_json: str, dry_run: bool = False):
    """Run database migration from JSON"""
    from src.database.migrations.migrate_from_json import run_migration, print_result
    result = run_migration(clients_json, config_json, dry_run)
    print_result(result)
    return 0 if not result.errors else 1


def init_database():
    """Initialize the database"""
    from src.database.connection import init_db
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")


def check_status():
    """Check system status"""
    from src.database.connection import SessionLocal, check_db_connection
    from src.core.management import ManagementCore

    print("\n=== VPN Manager Status ===\n")

    # Check database
    db_ok = check_db_connection()
    print(f"Database: {'OK' if db_ok else 'FAILED'}")

    if db_ok:
        db = SessionLocal()
        core = ManagementCore(db)
        status = core.get_system_status()

        print(f"\nServers: {status['servers']['total']} ({status['servers']['online']} online)")
        print(f"Clients: {status['clients']['total']} ({status['clients']['active']} active)")
        print(f"Traffic: {status['traffic']['total_formatted']}")
        print(f"Expiring soon: {status['expiry']['expiring_week']} clients")

        db.close()

    # Check WireGuard
    import subprocess
    try:
        result = subprocess.run(["wg", "show"], capture_output=True, timeout=5)
        wg_ok = result.returncode == 0
    except Exception:
        wg_ok = False

    print(f"\nWireGuard: {'OK' if wg_ok else 'NOT RUNNING'}")

    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="VPN Manager - WireGuard VPN Management Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  api           Start the REST API server
  admin-bot     Start the admin Telegram bot
  client-bot    Start the client Telegram bot
  migrate       Migrate data from JSON to database
  init-db       Initialize the database
  status        Check system status

Examples:
  python main.py api --port 10086
  python main.py admin-bot
  python main.py migrate --clients /root/wg_clients.json --config /root/bot_config.json
        """
    )

    parser.add_argument(
        "command",
        choices=["api", "admin-bot", "client-bot", "worker", "migrate", "init-db", "status"],
        help="Command to run"
    )

    # API options
    parser.add_argument("--host", default="0.0.0.0", help="API host")
    parser.add_argument("--port", type=int, default=10086, help="API port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # Migration options
    parser.add_argument("--clients", help="Path to wg_clients.json")
    parser.add_argument("--config", help="Path to bot_config.json")
    parser.add_argument("--dry-run", action="store_true", help="Don't commit changes")

    # Logging options
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--log-file", help="Log file path")

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level, args.log_file)

    # Run command
    if args.command == "api":
        run_api(args.host, args.port, args.reload)

    elif args.command == "admin-bot":
        run_admin_bot()

    elif args.command == "client-bot":
        run_client_bot()

    elif args.command == "worker":
        from worker_main import main as worker_main
        worker_main()

    elif args.command == "migrate":
        clients_json = args.clients or "/root/wg_clients.json"
        config_json = args.config or "/root/bot_config.json"
        sys.exit(run_migration(clients_json, config_json, args.dry_run))

    elif args.command == "init-db":
        init_database()

    elif args.command == "status":
        check_status()


if __name__ == "__main__":
    main()
