#!/usr/bin/env python3
"""
VPN Management Studio Migration Script
Migrates data from wg_clients.json to PostgreSQL database

Usage:
    python -m src.database.migrations.migrate_from_json \
        --clients-json /path/to/wg_clients.json \
        --config-json /path/to/bot_config.json
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sqlalchemy.orm import Session
from loguru import logger

from src.database.connection import engine, SessionLocal, init_db
from src.database.models import (
    Base, Server, Client, TelegramUser,
    ClientStatus, ServerStatus
)


class MigrationResult:
    """Stores migration results"""
    def __init__(self):
        self.servers_created = 0
        self.clients_migrated = 0
        self.clients_skipped = 0
        self.errors = []
        self.warnings = []


def load_json_file(path: str) -> Optional[Dict]:
    """Load and parse JSON file"""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {path}: {e}")
        return None


def migrate_server(
    db: Session,
    config: Dict,
    result: MigrationResult
) -> Optional[Server]:
    """Create server from bot_config.json"""

    # Check if server already exists
    existing = db.query(Server).filter(Server.interface == "wg0").first()
    if existing:
        logger.info(f"Server 'wg0' already exists (id={existing.id})")
        return existing

    # Extract server info from config
    endpoint = config.get("wg_server_endpoint", "203.0.113.1:51820")
    public_key = config.get("wg_server_public_key", "")
    interface = config.get("wg_interface", "wg0")
    config_path = config.get("wg_server_config", "/etc/wireguard/wg0.conf")
    dns = config.get("wg_dns", "1.1.1.1,1.0.0.1")

    # Extract IP pool from base addresses
    ipv4_base = config.get("wg_client_ip_base", "10.66.66.")
    ipv6_base = config.get("wg_client_ip6_base", "fd42:42:42::")

    # Construct pool CIDR
    ipv4_pool = ipv4_base + "0/24"
    ipv6_pool = ipv6_base + "/64" if ipv6_base else None

    # We need to get/generate the private key
    # Try to read from config file
    private_key = ""
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                for line in f:
                    if line.strip().startswith("PrivateKey"):
                        private_key = line.split("=")[1].strip()
                        break
    except Exception as e:
        logger.warning(f"Could not read private key from config: {e}")

    if not private_key:
        result.warnings.append("Private key not found, server may need manual configuration")
        private_key = "PLACEHOLDER_NEEDS_CONFIGURATION"

    if not public_key:
        result.warnings.append("Public key not found in config")
        public_key = "PLACEHOLDER_NEEDS_CONFIGURATION"

    server = Server(
        name="Main Server",
        interface=interface,
        endpoint=endpoint,
        listen_port=int(endpoint.split(":")[1]) if ":" in endpoint else 51820,
        public_key=public_key,
        private_key=private_key,
        address_pool_ipv4=ipv4_pool,
        address_pool_ipv6=ipv6_pool,
        dns=dns,
        config_path=config_path,
        status=ServerStatus.ONLINE,
        max_clients=250,
        description="Main WireGuard server (migrated from JSON)",
    )

    db.add(server)
    db.commit()
    db.refresh(server)

    result.servers_created = 1
    logger.info(f"Created server '{server.name}' (id={server.id})")

    return server


def migrate_admin_users(
    db: Session,
    config: Dict,
    result: MigrationResult
) -> None:
    """Migrate admin Telegram users"""
    allowed_users = config.get("allowed_users", [])

    for user_id in allowed_users:
        existing = db.query(TelegramUser).filter(
            TelegramUser.telegram_id == user_id
        ).first()

        if existing:
            if not existing.is_admin:
                existing.is_admin = True
                db.commit()
                logger.info(f"Updated user {user_id} to admin")
        else:
            user = TelegramUser(
                telegram_id=user_id,
                is_admin=True,
            )
            db.add(user)
            db.commit()
            logger.info(f"Created admin user {user_id}")


def migrate_clients(
    db: Session,
    clients_data: Dict,
    server: Server,
    result: MigrationResult
) -> None:
    """Migrate clients from wg_clients.json"""

    for client_name, client_info in clients_data.items():
        try:
            # Check if client already exists
            existing = db.query(Client).filter(
                Client.name == client_name,
                Client.server_id == server.id
            ).first()

            if existing:
                logger.info(f"Client '{client_name}' already exists, skipping")
                result.clients_skipped += 1
                continue

            # Extract client data
            ip_index = client_info.get("ip", 0)
            ipv4 = client_info.get("ipv4", f"10.66.66.{ip_index}")
            ipv6 = client_info.get("ipv6")
            public_key = client_info.get("public_key", "")
            enabled = client_info.get("enabled", True)
            bandwidth = client_info.get("bandwidth")
            traffic_limit = client_info.get("traffic_limit")

            # Parse expiry date
            expiry_date = None
            expiry_str = client_info.get("expiry_date")
            if expiry_str:
                try:
                    expiry_date = datetime.fromisoformat(expiry_str)
                except (ValueError, TypeError):
                    pass

            # Traffic tracking
            traffic_used_rx = client_info.get("traffic_used_rx", 0)
            traffic_used_tx = client_info.get("traffic_used_tx", 0)
            traffic_baseline_rx = client_info.get("traffic_baseline_rx", 0)
            traffic_baseline_tx = client_info.get("traffic_baseline_tx", 0)

            traffic_reset_date = None
            reset_str = client_info.get("traffic_reset_date")
            if reset_str:
                try:
                    traffic_reset_date = datetime.fromisoformat(reset_str)
                except (ValueError, TypeError):
                    pass

            traffic_limit_expiry = None
            expiry_str = client_info.get("traffic_limit_expiry")
            if expiry_str:
                try:
                    traffic_limit_expiry = datetime.fromisoformat(expiry_str)
                except (ValueError, TypeError):
                    pass

            # Determine status
            if not enabled:
                if expiry_date and expiry_date < datetime.now():
                    status = ClientStatus.EXPIRED
                else:
                    status = ClientStatus.DISABLED
            else:
                status = ClientStatus.ACTIVE

            # We don't have the private key in wg_clients.json
            # It's stored separately in wg0-client-{name}.conf files
            private_key = ""
            preshared_key = ""

            # Try to read from client config file
            client_config_path = f"/root/wg0-client-{client_name}.conf"
            psk_path = f"/root/wg0-client-{client_name}.psk"

            if os.path.exists(client_config_path):
                try:
                    with open(client_config_path, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("PrivateKey"):
                                private_key = line.split("=")[1].strip()
                except Exception:
                    pass

            if os.path.exists(psk_path):
                try:
                    with open(psk_path, 'r') as f:
                        preshared_key = f.read().strip()
                except Exception:
                    pass

            if not private_key:
                result.warnings.append(f"Private key not found for {client_name}")
                private_key = "PLACEHOLDER_NEEDS_REGENERATION"

            # Create client
            client = Client(
                name=client_name,
                server_id=server.id,
                public_key=public_key,
                private_key=private_key,
                preshared_key=preshared_key if preshared_key else None,
                ip_index=ip_index,
                ipv4=ipv4,
                ipv6=ipv6,
                status=status,
                enabled=enabled,
                bandwidth_limit=bandwidth if bandwidth and bandwidth > 0 else None,
                traffic_limit_mb=traffic_limit,
                traffic_limit_expiry=traffic_limit_expiry,
                traffic_used_rx=traffic_used_rx,
                traffic_used_tx=traffic_used_tx,
                traffic_baseline_rx=traffic_baseline_rx,
                traffic_baseline_tx=traffic_baseline_tx,
                traffic_reset_date=traffic_reset_date,
                expiry_date=expiry_date,
            )

            db.add(client)
            db.commit()

            result.clients_migrated += 1
            logger.info(f"Migrated client '{client_name}' (ip={ipv4}, enabled={enabled})")

        except Exception as e:
            result.errors.append(f"Failed to migrate {client_name}: {e}")
            logger.error(f"Failed to migrate {client_name}: {e}")
            db.rollback()


def run_migration(
    clients_json_path: str,
    config_json_path: str,
    dry_run: bool = False
) -> MigrationResult:
    """
    Run the complete migration

    Args:
        clients_json_path: Path to wg_clients.json
        config_json_path: Path to bot_config.json
        dry_run: If True, don't commit changes

    Returns:
        MigrationResult with statistics
    """
    result = MigrationResult()

    # Load JSON files
    logger.info("Loading JSON files...")

    clients_data = load_json_file(clients_json_path)
    if clients_data is None:
        result.errors.append(f"Could not load {clients_json_path}")
        return result

    config_data = load_json_file(config_json_path)
    if config_data is None:
        result.errors.append(f"Could not load {config_json_path}")
        return result

    logger.info(f"Found {len(clients_data)} clients to migrate")

    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Create session
    db = SessionLocal()

    try:
        # Migrate server
        logger.info("Migrating server configuration...")
        server = migrate_server(db, config_data, result)

        if not server:
            result.errors.append("Failed to create/get server")
            return result

        # Migrate admin users
        logger.info("Migrating admin users...")
        migrate_admin_users(db, config_data, result)

        # Migrate clients
        logger.info("Migrating clients...")
        migrate_clients(db, clients_data, server, result)

        if dry_run:
            logger.info("DRY RUN - Rolling back changes")
            db.rollback()
        else:
            db.commit()
            logger.info("Migration committed successfully")

    except Exception as e:
        result.errors.append(f"Migration failed: {e}")
        logger.error(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

    return result


def print_result(result: MigrationResult) -> None:
    """Print migration results"""
    print("\n" + "=" * 50)
    print("MIGRATION RESULTS")
    print("=" * 50)

    print(f"\nServers created: {result.servers_created}")
    print(f"Clients migrated: {result.clients_migrated}")
    print(f"Clients skipped: {result.clients_skipped}")

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"  ⚠️  {w}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for e in result.errors:
            print(f"  ❌ {e}")

    if not result.errors:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration completed with errors")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Migrate VPN Manager data from JSON to PostgreSQL"
    )
    parser.add_argument(
        "--clients-json",
        default="/root/wg_clients.json",
        help="Path to wg_clients.json"
    )
    parser.add_argument(
        "--config-json",
        default="/root/bot_config.json",
        help="Path to bot_config.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't commit changes, just test"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=log_level)

    print("=" * 50)
    print("Migration Tool")
    print("=" * 50)
    print(f"\nClients JSON: {args.clients_json}")
    print(f"Config JSON: {args.config_json}")
    print(f"Dry run: {args.dry_run}")
    print()

    result = run_migration(
        clients_json_path=args.clients_json,
        config_json_path=args.config_json,
        dry_run=args.dry_run,
    )

    print_result(result)

    # Exit with error code if there were errors
    sys.exit(1 if result.errors else 0)


if __name__ == "__main__":
    main()
