"""
VPN Management Studio Backup Manager
Full backup, restore, and disaster recovery functionality.

Backup format v2: vpnmanager-backup-YYYYMMDD-HHMMSS.tar.gz
Archive layout:
  backup/
    metadata.json          # version, timestamp, hostname, checksums
    database.sql.gz        # pg_dump -Fc | gzip
    env.env                # copy of .env (600 perms)
    wireguard/
      wg0.conf             # local /etc/wireguard/*.conf files
    servers/
      server_1_name.json   # client + server data export
      wg_config_1_name.conf
    system/
      version.txt

Legacy format v1: backup_YYYYMMDD_HHMMSS/ directories (read-only, listed alongside v2)
"""

import os
import re
import json
import gzip
import shutil
import hashlib
import socket
import subprocess
import tarfile
import tempfile
from urllib.parse import urlparse, unquote
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, load_only
from loguru import logger

from src.database.models import Server, Client, AuditLog, AuditAction
from src.database.connection import SessionLocal


BACKUP_DIR = os.getenv("VMS_BACKUP_DIR", str(Path(__file__).parent.parent / "backups"))
CURRENT_VERSION = "5.2"


def _get_pg_params() -> dict:
    """
    Return PostgreSQL connection parameters for pg_dump/pg_restore.
    Prefers individual DB_* env vars; falls back to parsing DATABASE_URL so
    installs that only set DATABASE_URL (not separate vars) work correctly.
    """
    db_url = os.getenv("DATABASE_URL", "")

    # Parse DATABASE_URL as fallback when individual vars use their defaults
    url_host = url_user = url_pass = url_port = url_name = ""
    if db_url:
        try:
            import urllib.parse as _up
            # Strip scheme (postgresql:// or postgres://)
            rest = db_url.split("://", 1)[1] if "://" in db_url else db_url
            # user:pass@host:port/dbname
            auth, hostpath = rest.rsplit("@", 1) if "@" in rest else ("", rest)
            if "/" in hostpath:
                host_part, url_name = hostpath.split("/", 1)
                url_name = url_name.split("?")[0]  # strip query params
            else:
                host_part = hostpath
            if ":" in host_part:
                url_host, url_port = host_part.rsplit(":", 1)
            else:
                url_host = host_part
            if ":" in auth:
                url_user, url_pass = auth.split(":", 1)
                url_pass = _up.unquote(url_pass)
            else:
                url_user = auth
        except Exception:
            pass  # malformed URL — fall through to individual vars

    db_host = os.getenv("DB_HOST") or url_host or "127.0.0.1"
    db_port = os.getenv("DB_PORT") or url_port or "5432"
    db_user = os.getenv("DB_USER") or url_user or "vpnmanager"
    db_pass = os.getenv("DB_PASSWORD") or url_pass or "vpnmanager"
    db_name = os.getenv("DB_NAME") or url_name or "vpnmanager_db"

    # Always use 127.0.0.1 instead of localhost to avoid IPv6 auth failures
    if db_host == "localhost":
        db_host = "127.0.0.1"

    return {
        "host": db_host,
        "port": db_port,
        "user": db_user,
        "password": db_pass,
        "name": db_name,
    }

# Backup ID patterns
_NEW_ID_RE = re.compile(r'^\d{8}-\d{6}$')           # YYYYMMDD-HHMMSS  (tar.gz)
_OLD_ID_RE = re.compile(r'^\d{8}_\d{6}$')            # YYYYMMDD_HHMMSS  (dir)


def _sanitize_backup_id(backup_id: str) -> str:
    """Sanitize backup_id to prevent path traversal (allows digits, hyphens, underscores)."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '', backup_id)
    if not clean:
        raise ValueError("Invalid backup_id")
    return clean


def _sanitize_name_for_filename(value: str) -> str:
    """Sanitize dynamic names before using them in backup filenames."""
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", (value or "").strip())
    clean = clean.strip("._-")
    return clean or "unnamed"


def _sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _pg_params_from_env_file(env_path: str) -> dict[str, str] | None:
    """Parse DATABASE_URL from a restored .env file."""
    try:
        for line in Path(env_path).read_text(encoding="utf-8").splitlines():
            if not line.startswith("DATABASE_URL="):
                continue
            parsed = urlparse(line.split("=", 1)[1].strip())
            host = parsed.hostname or "127.0.0.1"
            if host == "localhost":
                host = "127.0.0.1"
            return {
                "host": host,
                "port": str(parsed.port or 5432),
                "user": parsed.username or "vpnmanager",
                "password": unquote(parsed.password or ""),
                "name": (parsed.path or "/vpnmanager_db").lstrip("/") or "vpnmanager_db",
            }
    except Exception:
        return None
    return None


def _is_new_format(backup_id: str) -> bool:
    """Return True if backup_id matches new tar.gz format (YYYYMMDD-HHMMSS)."""
    return bool(_NEW_ID_RE.match(backup_id))


class BackupManager:
    """Manages full system backups: database, WireGuard, .env, and server configs."""

    def __init__(self, db: Session, backup_dir: Optional[str] = None):
        self.db = db
        self.backup_dir = backup_dir or self._get_backup_dir()

    def _write_audit_log_safe(
        self,
        *,
        action: AuditAction,
        target_type: str,
        target_name: str | None = None,
        details: dict | None = None,
        user_type: str = "system",
    ) -> None:
        payload = details or {}
        try:
            self.db.add(
                AuditLog(
                    user_type=user_type,
                    action=action,
                    target_type=target_type,
                    target_name=target_name,
                    details=payload,
                )
            )
            self.db.commit()
            return
        except Exception as exc:
            logger.warning(f"Audit log write failed for action={action}: {exc}")
            self.db.rollback()

        try:
            fallback_details = dict(payload)
            fallback_details["original_action"] = action.value if hasattr(action, "value") else str(action)
            fallback_details["audit_fallback"] = True
            self.db.add(
                AuditLog(
                    user_type=user_type,
                    action=AuditAction.CONFIG_CHANGE,
                    target_type=target_type,
                    target_name=target_name,
                    details=fallback_details,
                )
            )
            self.db.commit()
        except Exception as exc:
            logger.warning(f"Audit log fallback failed: {exc}")
            self.db.rollback()

    @staticmethod
    def _safe_attr(obj, name: str, default=None):
        """Read optionally-unloaded ORM column without triggering lazy-load."""
        return obj.__dict__.get(name, default)

    # ── Config helpers ────────────────────────────────────────────────────────

    def _get_backup_dir(self) -> str:
        """Get backup directory from DB config or env/default."""
        try:
            from src.database.models import SystemConfig
            rows = self.db.query(SystemConfig).filter(
                SystemConfig.key.in_(["backup_storage_type", "backup_path", "backup_mount_point"])
            ).all()
            cfg = {r.key: r.value for r in rows}
            storage_type = cfg.get("backup_storage_type", "local")
            if storage_type == "network":
                mount_point = cfg.get("backup_mount_point")
                if mount_point:
                    return mount_point
            else:
                path = cfg.get("backup_path")
                if path:
                    return path
        except Exception:
            pass
        return os.getenv("VMS_BACKUP_DIR", str(Path(__file__).parent.parent / "backups"))

    def _get_retention_cfg(self) -> dict:
        """Return retention settings from DB or defaults."""
        defaults = {"keep_count": 10, "keep_days": 30}
        try:
            from src.database.models import SystemConfig
            rows = self.db.query(SystemConfig).filter(
                SystemConfig.key.in_(["backup_keep_count", "backup_keep_days"])
            ).all()
            cfg = {r.key: r.value for r in rows}
            if "backup_keep_count" in cfg:
                defaults["keep_count"] = int(cfg["backup_keep_count"])
            if "backup_keep_days" in cfg:
                defaults["keep_days"] = int(cfg["backup_keep_days"])
        except Exception:
            pass
        return defaults

    def _find_env_file(self) -> Optional[str]:
        """Locate .env file relative to project root."""
        candidates = [
            Path(__file__).parent.parent / ".env",
            Path(__file__).parent.parent.parent / ".env",
            Path("/opt/vpnmanager/.env"),
            Path("/opt/spongebot/.env"),
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
        return None

    def _sync_local_database_password_from_env(self, env_path: str) -> None:
        """
        Ensure the local PostgreSQL role password matches the restored .env.
        This is required for disaster recovery onto a new server where install.sh
        generated a different local DB password before restore.
        """
        pg = _pg_params_from_env_file(env_path)
        if not pg or not pg.get("password"):
            return
        if pg["host"] not in {"127.0.0.1", "::1"}:
            return

        user = pg["user"].replace('"', '""')
        password = pg["password"].replace("'", "''")
        cmd = [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f"ALTER ROLE \"{user}\" WITH PASSWORD '{password}';",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            raise RuntimeError(f"failed to sync PostgreSQL password from restored .env: {stderr or proc.returncode}")

    # ── Public: create backup ─────────────────────────────────────────────────

    def _build_archive_name(self, *, label: str | None = None) -> tuple[str, str]:
        """Return (backup_id, archive_name) for a new backup archive."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_id = timestamp
        if label:
            suffix = _sanitize_name_for_filename(label)
            backup_id = f"{timestamp}-{suffix}"
        archive_name = f"vpnmanager-backup-{backup_id}.tar.gz"
        return backup_id, archive_name

    def create_full_backup(
        self,
        *,
        archive_name: str | None = None,
        label: str | None = None,
        audit_user_type: str = "system",
        audit_source: str = "system",
        audit_actor: str | None = None,
    ) -> dict:
        """
        Create full system backup as a tar.gz archive (v2 format).

        Archive: vpnmanager-backup-YYYYMMDD-HHMMSS.tar.gz
        Returns metadata dict.
        """
        os.makedirs(self.backup_dir, exist_ok=True)

        # Disk space guard: require at least 300 MB free
        stat = shutil.disk_usage(self.backup_dir)
        if stat.free < 300 * 1024 * 1024:
            raise RuntimeError(
                f"Insufficient disk space in {self.backup_dir}: "
                f"{stat.free // (1024 * 1024)} MB free (need ≥ 300 MB)"
            )

        backup_id, default_archive_name = self._build_archive_name(label=label)
        archive_name = archive_name or default_archive_name
        archive_path = os.path.join(self.backup_dir, archive_name)

        metadata: Dict[str, Any] = {
            "format": "tar.gz/v2",
            "version": CURRENT_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "backup_id": backup_id,
            "backup_type": "full",
            "label": label,
            "hostname": socket.gethostname(),
            "database_dump": False,
            "env_backed_up": False,
            "server_count": 0,
            "client_count": 0,
            "servers": [],
            "errors": [],
            "checksums": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            inner = os.path.join(tmpdir, "backup")
            os.makedirs(os.path.join(inner, "wireguard"))
            os.makedirs(os.path.join(inner, "servers"))
            os.makedirs(os.path.join(inner, "system"))

            # 1. Database dump
            db_path = os.path.join(inner, "database.sql.gz")
            try:
                self._dump_database_to(db_path)
                metadata["database_dump"] = True
                metadata["checksums"]["database.sql.gz"] = _sha256(db_path)
            except Exception as e:
                err = f"Database dump failed: {e}"
                logger.error(err)
                metadata["errors"].append(err)

            # 2. .env backup
            env_src = self._find_env_file()
            if env_src:
                env_dst = os.path.join(inner, "env.env")
                shutil.copy2(env_src, env_dst)
                os.chmod(env_dst, 0o600)
                metadata["env_backed_up"] = True
                metadata["checksums"]["env.env"] = _sha256(env_dst)

            # 3. Local WireGuard + AmneziaWG configs
            for wg_src_dir in ("/etc/wireguard", "/etc/amneziawg"):
                if os.path.isdir(wg_src_dir):
                    for conf in Path(wg_src_dir).glob("*.conf"):
                        dst = os.path.join(inner, "wireguard", conf.name)
                        try:
                            shutil.copy2(str(conf), dst)
                            metadata["checksums"][f"wireguard/{conf.name}"] = _sha256(dst)
                        except Exception as e:
                            metadata["errors"].append(f"WireGuard config {conf.name}: {e}")

            # 4. Per-server export + remote WG configs
            servers = (
                self.db.query(Server)
                .options(
                    load_only(
                        Server.id,
                        Server.name,
                        Server.interface,
                        Server.endpoint,
                        Server.listen_port,
                        Server.public_key,
                        Server.address_pool_ipv4,
                        Server.dns,
                        Server.mtu,
                        Server.persistent_keepalive,
                        Server.config_path,
                        Server.ssh_host,
                        Server.ssh_port,
                        Server.ssh_user,
                        Server.ssh_password,
                        Server.ssh_private_key,
                        Server.is_default,
                        Server.agent_mode,
                        Server.agent_url,
                    )
                )
                .all()
            )
            metadata["server_count"] = len(servers)
            total_clients = 0
            servers_dir = os.path.join(inner, "servers")

            for server in servers:
                srv_info = {
                    "id": server.id,
                    "name": server.name,
                    "clients_exported": 0,
                    "config_saved": False,
                }

                try:
                    n = self._export_server_clients(server, servers_dir)
                    srv_info["clients_exported"] = n
                    total_clients += n
                    fn = f"server_{server.id}_{_sanitize_name_for_filename(server.name)}.json"
                    ck = _sha256(os.path.join(servers_dir, fn))
                    metadata["checksums"][f"servers/{fn}"] = ck
                except Exception as e:
                    metadata["errors"].append(f"Server {server.name} export: {e}")

                try:
                    self._backup_wg_config(server, servers_dir)
                    srv_info["config_saved"] = True
                    for f in Path(servers_dir).glob(f"wg_config_{server.id}_*.conf"):
                        metadata["checksums"][f"servers/{f.name}"] = _sha256(str(f))
                except Exception as e:
                    metadata["errors"].append(f"Server {server.name} WG config: {e}")

                metadata["servers"].append(srv_info)

            metadata["client_count"] = total_clients

            # 5. version.txt
            ver_path = os.path.join(inner, "system", "version.txt")
            with open(ver_path, "w") as f:
                f.write(f"VPN Management Studio v{CURRENT_VERSION}\n")
                f.write(f"Backup created: {metadata['timestamp']}\n")
                f.write(f"Hostname: {metadata['hostname']}\n")
            metadata["checksums"]["system/version.txt"] = _sha256(ver_path)

            # 6. metadata.json (do not self-hash; only payload files participate in checksums)
            meta_path = os.path.join(inner, "metadata.json")
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)

            # 7. Pack tar.gz
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(inner, arcname="backup")

        # Secure the archive
        os.chmod(archive_path, 0o600)

        archive_size = os.path.getsize(archive_path)
        metadata["archive_path"] = archive_path
        metadata["archive_size_bytes"] = archive_size
        metadata["archive_size_mb"] = round(archive_size / (1024 * 1024), 2)

        # Retention cleanup
        self._apply_retention()

        self._write_audit_log_safe(
            user_type=audit_user_type,
            action=AuditAction.BACKUP_CREATE,
            target_type="backup",
            target_name=archive_name,
            details={
                "backup_type": "full",
                "source": audit_source,
                "actor": audit_actor,
                "size_mb": metadata["archive_size_mb"],
                "clients": total_clients,
                "errors": len(metadata["errors"]),
            },
        )

        logger.info(f"EVENT:BACKUP_SUCCESS {archive_name} {metadata['archive_size_mb']}MB clients={total_clients}")
        return metadata

    def create_database_backup(
        self,
        *,
        archive_name: str | None = None,
        label: str | None = None,
        audit_user_type: str = "system",
        audit_source: str = "system",
        audit_actor: str | None = None,
    ) -> dict:
        """
        Create database-only backup as a tar.gz archive.

        Archive layout:
          backup/
            metadata.json
            database.sql.gz
            system/version.txt
        """
        os.makedirs(self.backup_dir, exist_ok=True)

        stat = shutil.disk_usage(self.backup_dir)
        if stat.free < 100 * 1024 * 1024:
            raise RuntimeError(
                f"Insufficient disk space in {self.backup_dir}: "
                f"{stat.free // (1024 * 1024)} MB free (need ≥ 100 MB)"
            )

        backup_id, default_archive_name = self._build_archive_name(label=label)
        archive_name = archive_name or default_archive_name
        archive_path = os.path.join(self.backup_dir, archive_name)

        metadata: Dict[str, Any] = {
            "format": "tar.gz/v2",
            "version": CURRENT_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "backup_id": backup_id,
            "backup_type": "db-only",
            "label": label,
            "hostname": socket.gethostname(),
            "database_dump": False,
            "env_backed_up": False,
            "server_count": 0,
            "client_count": 0,
            "servers": [],
            "errors": [],
            "checksums": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            inner = os.path.join(tmpdir, "backup")
            os.makedirs(os.path.join(inner, "system"))

            db_path = os.path.join(inner, "database.sql.gz")
            self._dump_database_to(db_path)
            metadata["database_dump"] = True
            metadata["checksums"]["database.sql.gz"] = _sha256(db_path)

            ver_path = os.path.join(inner, "system", "version.txt")
            with open(ver_path, "w") as f:
                f.write(f"VPN Management Studio v{CURRENT_VERSION}\n")
                f.write(f"Backup created: {metadata['timestamp']}\n")
                f.write(f"Hostname: {metadata['hostname']}\n")
                f.write("Backup type: db-only\n")
            metadata["checksums"]["system/version.txt"] = _sha256(ver_path)

            meta_path = os.path.join(inner, "metadata.json")
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)

            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(inner, arcname="backup")

        os.chmod(archive_path, 0o600)
        archive_size = os.path.getsize(archive_path)
        metadata["archive_path"] = archive_path
        metadata["archive_size_bytes"] = archive_size
        metadata["archive_size_mb"] = round(archive_size / (1024 * 1024), 2)

        self._apply_retention()

        self._write_audit_log_safe(
            user_type=audit_user_type,
            action=AuditAction.BACKUP_CREATE,
            target_type="backup",
            target_name=archive_name,
            details={
                "backup_type": "db-only",
                "source": audit_source,
                "actor": audit_actor,
                "size_mb": metadata["archive_size_mb"],
                "errors": len(metadata["errors"]),
            },
        )

        logger.info(f"EVENT:BACKUP_SUCCESS {archive_name} {metadata['archive_size_mb']}MB type=db-only")
        return metadata

    # ── Public: verify backup ─────────────────────────────────────────────────

    def verify_backup(self, backup_id: str) -> dict:
        """
        Verify a tar.gz backup:
        - Archive readable / not corrupted
        - metadata.json parseable
        - All checksums match
        - database.sql.gz non-empty
        Returns dict with 'ok' bool and list of 'errors'.
        """
        backup_id = _sanitize_backup_id(backup_id)
        result = {"backup_id": backup_id, "ok": True, "errors": [], "files_checked": 0}

        archive_path = self._archive_path(backup_id)
        if not os.path.isfile(archive_path):
            result["ok"] = False
            result["errors"].append(f"Archive not found: {archive_path}")
            return result

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(tmpdir, filter="data")
            except Exception as e:
                result["ok"] = False
                result["errors"].append(f"Archive extraction failed: {e}")
                return result

            inner = os.path.join(tmpdir, "backup")
            if not os.path.isdir(inner):
                result["ok"] = False
                result["errors"].append("Archive missing 'backup/' directory")
                return result

            meta_path = os.path.join(inner, "metadata.json")
            if not os.path.isfile(meta_path):
                result["ok"] = False
                result["errors"].append("metadata.json missing")
                return result

            try:
                with open(meta_path) as f:
                    metadata = json.load(f)
            except Exception as e:
                result["ok"] = False
                result["errors"].append(f"metadata.json parse error: {e}")
                return result

            result["metadata"] = {
                k: metadata.get(k)
                for k in ("version", "timestamp", "hostname", "database_dump",
                          "env_backed_up", "server_count", "client_count")
            }

            # Checksum verification
            checksums = metadata.get("checksums", {})
            for rel_path, expected_hash in checksums.items():
                abs_path = os.path.join(inner, rel_path)
                if not os.path.isfile(abs_path):
                    result["errors"].append(f"Missing file: {rel_path}")
                    result["ok"] = False
                    continue
                actual = _sha256(abs_path)
                if actual != expected_hash:
                    result["errors"].append(f"Checksum mismatch: {rel_path}")
                    result["ok"] = False
                result["files_checked"] += 1

            # DB dump non-empty check
            db_path = os.path.join(inner, "database.sql.gz")
            if os.path.isfile(db_path):
                if os.path.getsize(db_path) < 100:
                    result["errors"].append("database.sql.gz is suspiciously small (<100 bytes)")
                    result["ok"] = False

        return result

    # ── Public: full system restore ───────────────────────────────────────────

    def restore_full_system(
        self,
        backup_id: str,
        restart_services: bool = True,
        stop_services: bool = True,
        audit_user_type: str = "admin",
        audit_source: str = "system",
        audit_actor: str | None = None,
    ) -> dict:
        """
        Full disaster recovery restore from a v2 tar.gz archive:
        1. Version compatibility check
        2. Pre-restore safety snapshot (DB only, fast)
        3. Restore database
        4. Restore .env
        5. Restore local WireGuard configs
        6. Optionally restart services

        Returns dict with results.
        """
        backup_id = _sanitize_backup_id(backup_id)
        result = {
            "backup_id": backup_id,
            "pre_restore_snapshot": None,
            "services_stopped": [],
            "database_restored": False,
            "env_restored": False,
            "database_credentials_synced": False,
            "wireguard_restored": [],
            "services_restarted": False,
            "errors": [],
        }

        archive_path = self._archive_path(backup_id)
        if not os.path.isfile(archive_path):
            raise FileNotFoundError(f"Backup not found: {archive_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(tmpdir, filter="data")
            except Exception as e:
                raise RuntimeError(f"Failed to extract backup: {e}")

            inner = os.path.join(tmpdir, "backup")
            meta_path = os.path.join(inner, "metadata.json")

            if os.path.isfile(meta_path):
                with open(meta_path) as f:
                    metadata = json.load(f)
                backup_ver = metadata.get("version", "0")
                # Accept same major version
                if backup_ver.split(".")[0] != CURRENT_VERSION.split(".")[0]:
                    result["errors"].append(
                        f"Version mismatch: backup={backup_ver}, current={CURRENT_VERSION}"
                    )
                    logger.warning(f"Restore version warning: {result['errors'][-1]}")

            # 0. Stop services before destructive restore operations
            if stop_services:
                try:
                    result["services_stopped"] = self._stop_services()
                except Exception as e:
                    result["errors"].append(f"Service stop failed: {e}")
                    logger.error(f"Service stop failed: {e}")

            # Pre-restore safety snapshot (quick DB dump only)
            try:
                safety_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                safety_name = f"vpnmanager-prerestore-{safety_ts}.tar.gz"
                safety_path = os.path.join(self.backup_dir, safety_name)
                safety_inner = os.path.join(tmpdir, "safety_inner", "backup", "system")
                os.makedirs(safety_inner)
                safety_db = os.path.join(tmpdir, "safety_inner", "backup", "database.sql.gz")
                self._dump_database_to(safety_db)
                with tarfile.open(safety_path, "w:gz") as tar:
                    tar.add(os.path.join(tmpdir, "safety_inner", "backup"), arcname="backup")
                os.chmod(safety_path, 0o600)
                result["pre_restore_snapshot"] = safety_name
                logger.info(f"Pre-restore snapshot: {safety_name}")
            except Exception as e:
                result["errors"].append(f"Pre-restore snapshot failed (continuing): {e}")

            # 1. Restore database
            db_path = os.path.join(inner, "database.sql.gz")
            if os.path.isfile(db_path):
                try:
                    self._restore_database_from_file(db_path)
                    result["database_restored"] = True
                    logger.info("Database restored successfully")
                except Exception as e:
                    result["errors"].append(f"Database restore failed: {e}")
                    logger.error(f"Database restore failed: {e}")
            else:
                result["errors"].append("database.sql.gz not found in archive")

            # 2. Restore .env
            env_src = os.path.join(inner, "env.env")
            if os.path.isfile(env_src):
                env_dst = self._find_env_file()
                if not env_dst:
                    env_dst = str(Path(__file__).parent.parent / ".env")
                try:
                    shutil.copy2(env_src, env_dst)
                    os.chmod(env_dst, 0o600)
                    self._sync_local_database_password_from_env(env_dst)
                    result["env_restored"] = True
                    result["database_credentials_synced"] = True
                    logger.info(f".env restored to {env_dst}")
                except Exception as e:
                    result["errors"].append(f".env restore failed: {e}")

            # 3. Restore local WireGuard + AmneziaWG configs
            wg_src_dir = os.path.join(inner, "wireguard")
            if os.path.isdir(wg_src_dir):
                for conf in Path(wg_src_dir).glob("*.conf"):
                    # Restore AWG configs to /etc/amneziawg/, WG configs to /etc/wireguard/
                    if conf.name.startswith("awg"):
                        target_dir = "/etc/amneziawg"
                    else:
                        target_dir = "/etc/wireguard"
                    dst = f"{target_dir}/{conf.name}"
                    try:
                        os.makedirs(target_dir, exist_ok=True)
                        shutil.copy2(str(conf), dst)
                        os.chmod(dst, 0o600)
                        result["wireguard_restored"].append(conf.name)
                        logger.info(f"Restored config: {conf.name} → {target_dir}")
                    except Exception as e:
                        result["errors"].append(f"Config {conf.name} restore failed: {e}")

            # 4. Restart services
            if restart_services:
                try:
                    self._restart_services(result.get("services_stopped") or None)
                    result["services_restarted"] = True
                except Exception as e:
                    result["errors"].append(f"Service restart failed: {e}")

        # Audit
        try:
            audit = AuditLog(
                user_type=audit_user_type,
                action=AuditAction.BACKUP_RESTORE,
                target_type="system",
                target_name=backup_id,
                details={
                    "type": "full_system_restore",
                    "database_restored": result["database_restored"],
                    "env_restored": result["env_restored"],
                    "database_credentials_synced": result["database_credentials_synced"],
                    "wg_files": result["wireguard_restored"],
                    "services_stopped": result["services_stopped"],
                    "services_restarted": result["services_restarted"],
                    "errors": len(result["errors"]),
                    "archive_path": archive_path,
                    "source": audit_source,
                    "actor": audit_actor,
                },
            )
            self.db.add(audit)
            self.db.commit()
        except Exception:
            pass

        errors = len(result.get("errors", []))
        status = "EVENT:RESTORE_SUCCESS" if errors == 0 else "EVENT:RESTORE_PARTIAL"
        logger.info(f"{status} from {backup_id} errors={errors}")
        return result

    # ── Public: restore database only ─────────────────────────────────────────

    def restore_database(self, backup_id: str) -> bool:
        """Restore database from backup (supports both v1 dir and v2 tar.gz format)."""
        backup_id = _sanitize_backup_id(backup_id)

        if _is_new_format(backup_id):
            archive_path = self._archive_path(backup_id)
            if not os.path.isfile(archive_path):
                raise FileNotFoundError(f"Archive not found: {archive_path}")
            with tempfile.TemporaryDirectory() as tmpdir:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(tmpdir, filter="data")
                db_path = os.path.join(tmpdir, "backup", "database.sql.gz")
                if not os.path.isfile(db_path):
                    raise FileNotFoundError("database.sql.gz not found in archive")
                self._restore_database_from_file(db_path)
        else:
            # Legacy directory format
            backup_dir = os.path.join(self.backup_dir, f"backup_{backup_id}")
            dump_path = os.path.join(backup_dir, "database.sql.gz")
            if not os.path.isfile(dump_path):
                raise FileNotFoundError(f"Database dump not found: {dump_path}")
            self._restore_database_from_file(dump_path)

        try:
            audit = AuditLog(
                user_type="admin",
                action=AuditAction.BACKUP_RESTORE,
                target_type="database",
                target_name=backup_id,
                details={"type": "database_restore"},
            )
            self.db.add(audit)
            self.db.commit()
        except Exception:
            pass

        logger.info(f"Database restored from backup {backup_id}")
        return True

    # ── Public: list backups ──────────────────────────────────────────────────

    def list_backups(self) -> List[dict]:
        """List all backups (v2 tar.gz and legacy directories), newest first."""
        if not os.path.isdir(self.backup_dir):
            return []

        backups = []

        # V2: tar.gz archives
        for f in Path(self.backup_dir).glob("vpnmanager-backup-*.tar.gz"):
            backup_id = f.stem.replace("vpnmanager-backup-", "").replace(".tar", "")
            # f.stem gives "vpnmanager-backup-YYYYMMDD-HHMMSS" (no .gz since stem of .tar.gz)
            # Actually Path.stem of "x.tar.gz" → "x.tar", so use name parsing
            name = f.name  # vpnmanager-backup-YYYYMMDD-HHMMSS.tar.gz
            backup_id = name[len("vpnmanager-backup-"):-len(".tar.gz")]
            entry = {
                "backup_id": backup_id,
                "format": "tar.gz",
                "filename": name,
                "archive_path": str(f),
                "archive_size_bytes": f.stat().st_size,
                "archive_size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            }
            # Try reading metadata from inside
            try:
                with tarfile.open(str(f), "r:gz") as tar:
                    try:
                        member = tar.getmember("backup/metadata.json")
                        fobj = tar.extractfile(member)
                        if fobj:
                            meta = json.load(fobj)
                            entry.update({
                                "timestamp": meta.get("timestamp"),
                                "version": meta.get("version"),
                                "hostname": meta.get("hostname"),
                                "server_count": meta.get("server_count", 0),
                                "client_count": meta.get("client_count", 0),
                                "database_dump": meta.get("database_dump", False),
                                "env_backed_up": meta.get("env_backed_up", False),
                                "errors": meta.get("errors", []),
                            })
                    except KeyError:
                        pass
            except Exception:
                pass
            if "timestamp" not in entry:
                # Derive from filename
                ts_raw = backup_id  # YYYYMMDD-HHMMSS
                try:
                    dt = datetime.strptime(ts_raw, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
                    entry["timestamp"] = dt.isoformat()
                except Exception:
                    entry["timestamp"] = None
            backups.append(entry)

        # Pre-restore safety snapshots
        for f in Path(self.backup_dir).glob("vpnmanager-prerestore-*.tar.gz"):
            name = f.name
            backup_id = name[len("vpnmanager-prerestore-"):-len(".tar.gz")]
            backups.append({
                "backup_id": backup_id,
                "format": "tar.gz",
                "filename": name,
                "is_prerestore": True,
                "archive_path": str(f),
                "archive_size_bytes": f.stat().st_size,
                "archive_size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "timestamp": None,
            })

        # Legacy V1: directories
        for d in Path(self.backup_dir).iterdir():
            if not d.is_dir() or not d.name.startswith("backup_"):
                continue
            manifest_path = d / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path) as fh:
                    manifest = json.load(fh)
                manifest["format"] = "directory"
                manifest["backup_dir"] = str(d)
                backups.append(manifest)
            else:
                total_size = sum(
                    f.stat().st_size for f in d.rglob("*") if f.is_file()
                )
                backups.append({
                    "backup_id": d.name.replace("backup_", ""),
                    "format": "directory",
                    "backup_dir": str(d),
                    "archive_size_bytes": total_size,
                    "archive_size_mb": round(total_size / (1024 * 1024), 2),
                })

        # Sort by timestamp descending
        def _sort_key(b):
            ts = b.get("timestamp") or ""
            return ts

        backups.sort(key=_sort_key, reverse=True)
        return backups

    # ── Public: delete backup ─────────────────────────────────────────────────

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a specific backup (v2 tar.gz or legacy directory)."""
        backup_id = _sanitize_backup_id(backup_id)

        deleted = False

        # Try v2 tar.gz
        archive_path = self._archive_path(backup_id)
        if os.path.isfile(archive_path):
            os.remove(archive_path)
            deleted = True

        # Try pre-restore snapshot
        prerestore_path = os.path.join(
            self.backup_dir, f"vpnmanager-prerestore-{backup_id}.tar.gz"
        )
        if os.path.isfile(prerestore_path):
            os.remove(prerestore_path)
            deleted = True

        # Try legacy directory
        legacy_path = os.path.join(self.backup_dir, f"backup_{backup_id}")
        if os.path.isdir(legacy_path):
            shutil.rmtree(legacy_path, ignore_errors=True)
            deleted = True

        if not deleted:
            raise FileNotFoundError(f"Backup not found: {backup_id}")

        try:
            audit = AuditLog(
                user_type="admin",
                action=AuditAction.BACKUP_DELETE,
                target_type="backup",
                target_name=backup_id,
                details={"action": "delete"},
            )
            self.db.add(audit)
            self.db.commit()
        except Exception:
            pass

        logger.info(f"Backup deleted: {backup_id}")
        return True

    # ── Public: cleanup / retention ──────────────────────────────────────────

    def cleanup_old_backups(self, keep: int = 10):
        """Delete oldest backups by count (legacy API, used by scheduler)."""
        self._apply_retention(keep_count=keep)

    def _apply_retention(self, keep_count: Optional[int] = None, keep_days: Optional[int] = None):
        """Delete backups exceeding count limit OR age limit."""
        if not os.path.isdir(self.backup_dir):
            return

        cfg = self._get_retention_cfg()
        if keep_count is None:
            keep_count = cfg["keep_count"]
        if keep_days is None:
            keep_days = cfg["keep_days"]

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=keep_days)

        # Collect v2 archives (not pre-restore snapshots)
        archives = sorted(
            [
                f for f in Path(self.backup_dir).glob("vpnmanager-backup-*.tar.gz")
            ],
            key=lambda f: f.name,
        )

        # Delete by age
        for f in archives[:]:
            ts_raw = f.name[len("vpnmanager-backup-"):-len(".tar.gz")]
            try:
                dt = datetime.strptime(ts_raw, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    f.unlink(missing_ok=True)
                    archives.remove(f)
                    logger.info(f"Retention: deleted old backup {f.name} (age > {keep_days}d)")
            except Exception:
                pass

        # Delete by count (keep newest keep_count)
        while len(archives) > keep_count:
            oldest = archives.pop(0)
            oldest.unlink(missing_ok=True)
            logger.info(f"Retention: deleted backup {oldest.name} (count > {keep_count})")

        # Legacy directories: keep last keep_count
        legacy_dirs = sorted(
            [d for d in Path(self.backup_dir).iterdir()
             if d.is_dir() and d.name.startswith("backup_")],
            key=lambda d: d.name,
        )
        while len(legacy_dirs) > keep_count:
            oldest = legacy_dirs.pop(0)
            shutil.rmtree(oldest, ignore_errors=True)
            logger.info(f"Retention: deleted legacy backup {oldest.name}")

    # ── Server restore (legacy + v2 compatible) ───────────────────────────────

    def restore_server_from_backup(self, server_id: int, backup_id: str) -> dict:
        """Restore all clients + WG config for one server from backup."""
        backup_id = _sanitize_backup_id(backup_id)

        # Resolve backup directory (legacy) or extract from archive (v2)
        if _is_new_format(backup_id):
            archive_path = self._archive_path(backup_id)
            if not os.path.isfile(archive_path):
                raise FileNotFoundError(f"Archive not found: {archive_path}")
            tmpdir_ctx = tempfile.TemporaryDirectory()
            tmpdir = tmpdir_ctx.__enter__()
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(tmpdir, filter="data")
                backup_dir = os.path.join(tmpdir, "backup", "servers")
                result = self._do_restore_server(server_id, backup_dir)
            finally:
                tmpdir_ctx.__exit__(None, None, None)
        else:
            backup_dir = os.path.join(self.backup_dir, f"backup_{backup_id}")
            if not os.path.isdir(backup_dir):
                raise FileNotFoundError(f"Backup not found: {backup_dir}")
            result = self._do_restore_server(server_id, backup_dir)

        # Audit
        try:
            server = self.db.query(Server).filter(Server.id == server_id).first()
            audit = AuditLog(
                user_type="admin",
                action=AuditAction.BACKUP_RESTORE,
                target_type="server",
                target_id=server_id,
                target_name=server.name if server else str(server_id),
                details=result,
            )
            self.db.add(audit)
            self.db.commit()
        except Exception:
            pass

        return result

    def _do_restore_server(self, server_id: int, backup_dir: str) -> dict:
        """Internal: restore server from a directory containing server JSON and WG conf."""
        server = self.db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise ValueError(f"Server {server_id} not found")

        server_json = None
        for f in Path(backup_dir).glob("server_*.json"):
            with open(f) as fh:
                data = json.load(fh)
            if data.get("server", {}).get("id") == server_id or \
               data.get("server", {}).get("name") == server.name:
                server_json = data
                break

        if not server_json:
            raise FileNotFoundError(f"Server {server_id} data not found in backup")

        result = {"clients_restored": 0, "peers_added": 0, "config_restored": False}

        server_meta = server_json.get("server", {})
        server_category = server_meta.get("server_category", "vpn")
        is_proxy = server_category == "proxy" or server_meta.get("server_type", "wireguard") in ("hysteria2", "tuic")

        if is_proxy:
            # ── Proxy server restore ──────────────────────────────────────────
            # Restore the proxy config file (Hysteria2 YAML or TUIC JSON).
            # Do NOT attempt WireGuard peer operations — proxy clients have no public_key.
            server_type = server_meta.get("server_type", "hysteria2")
            ext = "yaml" if server_type == "hysteria2" else "json"
            proxy_conf_glob = f"proxy_config_{server_id}_*.{ext}"
            proxy_conf_file = None
            for f in Path(backup_dir).glob(proxy_conf_glob):
                proxy_conf_file = f
                break

            if proxy_conf_file and proxy_conf_file.is_file():
                config_content = proxy_conf_file.read_text()
                config_path = getattr(server, "proxy_config_path", None) or server_meta.get("proxy_config_path")
                if config_path and config_content:
                    from src.core.proxy_base import ProxyBaseManager
                    mgr = ProxyBaseManager(
                        config_path=config_path,
                        service_name=getattr(server, "proxy_service_name", "") or "",
                        ssh_host=server.ssh_host,
                        ssh_port=server.ssh_port or 22,
                        ssh_user=server.ssh_user or "root",
                        ssh_password=server.ssh_password,
                        ssh_private_key=server.ssh_private_key,
                    )
                    try:
                        mgr._write_file(config_path, config_content)
                        result["config_restored"] = True
                        logger.info(f"Proxy config restored to {config_path} on {server.name}")
                    except Exception as e:
                        logger.error(f"Failed to restore proxy config: {e}")
                    finally:
                        mgr.close()
                else:
                    logger.warning(
                        f"Cannot restore proxy config for {server.name}: "
                        f"config_path={config_path!r}, content_len={len(config_content) if config_content else 0}"
                    )
            else:
                logger.warning(
                    f"No proxy config backup found for server {server_id} "
                    f"(looked for {proxy_conf_glob} in {backup_dir})"
                )

            result["clients_restored"] = len(server_json.get("clients", []))

            # ── Post-restore validation ───────────────────────────────────────
            # Run a lightweight health check so the caller knows whether the
            # restored server needs further attention (e.g. bootstrap).
            # We reuse the existing health_check() — it is non-destructive.
            try:
                if server_type == "hysteria2":
                    from src.core.hysteria2 import Hysteria2Manager
                    validator = Hysteria2Manager(
                        config_path=config_path or "/etc/hysteria/config.yaml",
                        cert_path=getattr(server, "proxy_cert_path", None) or "/etc/hysteria/server.crt",
                        key_path=getattr(server, "proxy_key_path", None) or "/etc/hysteria/server.key",
                        service_name=getattr(server, "proxy_service_name", None) or "hysteria2",
                        listen_port=getattr(server, "port", 8443) or 8443,
                        tls_mode=getattr(server, "proxy_tls_mode", "self_signed") or "self_signed",
                        domain=getattr(server, "proxy_domain", None),
                        ssh_host=server.ssh_host,
                        ssh_port=server.ssh_port or 22,
                        ssh_user=server.ssh_user or "root",
                        ssh_password=server.ssh_password,
                        ssh_private_key=server.ssh_private_key,
                    )
                else:
                    from src.core.tuic import TUICManager
                    validator = TUICManager(
                        config_path=config_path or "/etc/tuic/config.json",
                        cert_path=getattr(server, "proxy_cert_path", None) or "/etc/tuic/server.crt",
                        key_path=getattr(server, "proxy_key_path", None) or "/etc/tuic/server.key",
                        service_name=getattr(server, "proxy_service_name", None) or "tuic-server",
                        listen_port=getattr(server, "port", 8444) or 8444,
                        tls_mode=getattr(server, "proxy_tls_mode", "self_signed") or "self_signed",
                        domain=getattr(server, "proxy_domain", None),
                        ssh_host=server.ssh_host,
                        ssh_port=server.ssh_port or 22,
                        ssh_user=server.ssh_user or "root",
                        ssh_password=server.ssh_password,
                        ssh_private_key=server.ssh_private_key,
                    )
                health = validator.health_check()
                validator.close()

                issue_codes = health.get("issue_codes", [])
                result["restore_status"] = "needs_attention" if issue_codes else "ok"
                result["restore_issues"] = issue_codes
                result["restore_health"] = {
                    "binary_ok": health.get("binary_ok", False),
                    "config_ok": health.get("config_ok", False),
                    "cert_ok": health.get("cert_ok", False),
                    "service_active": health.get("service_active", False),
                    "status": health.get("status", "unknown"),
                    "message": health.get("message", ""),
                }
                if issue_codes:
                    logger.warning(
                        f"Post-restore validation for {server.name}: "
                        f"needs_attention — {issue_codes}"
                    )
                else:
                    logger.info(f"Post-restore validation for {server.name}: ok")

            except Exception as val_err:
                logger.warning(f"Post-restore validation failed for {server.name}: {val_err}")
                result["restore_status"] = "unknown"
                result["restore_issues"] = []
                result["restore_health"] = {}

            logger.info(f"Proxy server {server.name} restored: {result}")
            return result

        # ── WireGuard / AmneziaWG restore ────────────────────────────────────
        from src.core.wireguard import WireGuardManager

        # Restore WG config file
        for f in Path(backup_dir).glob(f"wg_config_{server_id}_*.conf"):
            config_content = f.read_text()
            if config_content:
                if server.agent_mode == "agent" and server.agent_url:
                    import httpx
                    resp = httpx.post(
                        f"{server.agent_url}/restore",
                        headers={"X-API-Key": server.agent_api_key or ""},
                        json={"config": config_content, "peers": server_json.get("clients", [])},
                        timeout=30,
                    )
                    result["config_restored"] = resp.status_code == 200
                else:
                    _is_awg = getattr(server, 'server_type', 'wireguard') == 'amneziawg'
                    if _is_awg:
                        from src.core.amneziawg import AmneziaWGManager
                        wg_cfg = AmneziaWGManager(
                            ssh_host=server.ssh_host, ssh_port=server.ssh_port,
                            ssh_user=server.ssh_user, ssh_password=server.ssh_password,
                            ssh_private_key=server.ssh_private_key,
                            interface=server.interface, config_path=server.config_path,
                        )
                    else:
                        wg_cfg = WireGuardManager(
                            ssh_host=server.ssh_host, ssh_port=server.ssh_port,
                            ssh_user=server.ssh_user, ssh_password=server.ssh_password,
                            ssh_private_key=server.ssh_private_key,
                            interface=server.interface, config_path=server.config_path,
                        )
                    try:
                        result["config_restored"] = wg_cfg.write_config_file(config_content)
                    finally:
                        wg_cfg.close()
            break

        # Restore client peers via WG — use correct manager type (AWG or standard)
        _is_awg = getattr(server, 'server_type', 'wireguard') == 'amneziawg'
        if _is_awg:
            from src.core.amneziawg import AmneziaWGManager
            wg = AmneziaWGManager(
                ssh_host=server.ssh_host, ssh_port=server.ssh_port,
                ssh_user=server.ssh_user, ssh_password=server.ssh_password,
                ssh_private_key=server.ssh_private_key,
                interface=server.interface, config_path=server.config_path,
            )
        else:
            wg = WireGuardManager(
                ssh_host=server.ssh_host, ssh_port=server.ssh_port,
                ssh_user=server.ssh_user, ssh_password=server.ssh_password,
                ssh_private_key=server.ssh_private_key,
                interface=server.interface, config_path=server.config_path,
            )
        try:
            for client_data in server_json.get("clients", []):
                if not client_data.get("enabled", True):
                    continue
                pub_key = client_data.get("public_key")
                if not pub_key:
                    # Skip proxy clients that ended up in a VPN server backup
                    logger.warning(f"Skipping client '{client_data.get('name')}' — no public_key")
                    continue
                try:
                    allowed_ips = client_data["ipv4"] + "/32"
                    if client_data.get("ipv6"):
                        allowed_ips += f",{client_data['ipv6']}/128"
                    wg.add_peer(
                        pub_key,
                        allowed_ips,
                        preshared_key=client_data.get("preshared_key"),
                    )
                    result["peers_added"] += 1
                except Exception as e:
                    logger.error(f"Failed to restore peer {client_data.get('name')}: {e}")
        finally:
            wg.close()

        result["clients_restored"] = len(server_json.get("clients", []))
        logger.info(f"Server {server.name} restored: {result}")
        return result

    # ── Server migration (unchanged logic) ───────────────────────────────────

    def migrate_server(
        self,
        backup_id: str,
        server_name: str,
        new_ssh_host: str,
        new_ssh_port: int = 22,
        new_ssh_user: str = "root",
        new_ssh_password: str = "",
        new_ssh_private_key: str = None,
    ) -> dict:
        """Migrate a server to a new host using backup data."""
        backup_id = _sanitize_backup_id(backup_id)

        if _is_new_format(backup_id):
            archive_path = self._archive_path(backup_id)
            if not os.path.isfile(archive_path):
                raise FileNotFoundError(f"Archive not found: {archive_path}")
            tmpctx = tempfile.TemporaryDirectory()
            tmpdir = tmpctx.__enter__()
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(tmpdir, filter="data")
                backup_dir = os.path.join(tmpdir, "backup", "servers")
                return self._do_migrate(
                    backup_dir, server_name,
                    new_ssh_host, new_ssh_port, new_ssh_user, new_ssh_password, new_ssh_private_key
                )
            finally:
                tmpctx.__exit__(None, None, None)
        else:
            backup_dir = os.path.join(self.backup_dir, f"backup_{backup_id}")
            if not os.path.isdir(backup_dir):
                raise FileNotFoundError(f"Backup not found: {backup_dir}")
            return self._do_migrate(
                backup_dir, server_name,
                new_ssh_host, new_ssh_port, new_ssh_user, new_ssh_password, new_ssh_private_key
            )

    def _do_migrate(
        self, backup_dir: str, server_name: str,
        new_ssh_host: str, new_ssh_port: int, new_ssh_user: str, new_ssh_password: str,
        new_ssh_private_key: str = None
    ) -> dict:
        server_data = None
        for f in Path(backup_dir).glob("server_*.json"):
            with open(f) as fh:
                data = json.load(fh)
            if data.get("server", {}).get("name") == server_name:
                server_data = data
                break

        if not server_data:
            raise FileNotFoundError(f"Server '{server_name}' not found in backup")

        result = {
            "agent_installed": False, "config_deployed": False,
            "peers_restored": 0, "db_updated": False,
        }

        try:
            from src.core.agent_bootstrap import AgentBootstrap
            bootstrap = AgentBootstrap(
                ssh_host=new_ssh_host, ssh_port=new_ssh_port,
                ssh_user=new_ssh_user, ssh_password=new_ssh_password,
                ssh_private_key_content=new_ssh_private_key,
            )
            install_result = bootstrap.install_agent()
            result["agent_installed"] = install_result.get("success", False)
        except Exception as e:
            result["agent_install_error"] = str(e)

        _is_awg = server_data["server"].get("server_type", "wireguard") == "amneziawg"
        _iface = server_data["server"].get("interface", "wg0")
        _cfg_path = server_data["server"].get("config_path", f"/etc/wireguard/{_iface}.conf")
        _ssh_kwargs = dict(
            ssh_host=new_ssh_host, ssh_port=new_ssh_port,
            ssh_user=new_ssh_user, ssh_password=new_ssh_password,
            ssh_private_key=new_ssh_private_key,
            interface=_iface,
            config_path=_cfg_path,
        )

        def _make_wg():
            if _is_awg:
                from src.core.amneziawg import AmneziaWGManager
                return AmneziaWGManager(
                    **_ssh_kwargs,
                    jc=server_data["server"].get("awg_jc"),
                    jmin=server_data["server"].get("awg_jmin"),
                    jmax=server_data["server"].get("awg_jmax"),
                    s1=server_data["server"].get("awg_s1"),
                    s2=server_data["server"].get("awg_s2"),
                    h1=server_data["server"].get("awg_h1"),
                    h2=server_data["server"].get("awg_h2"),
                    h3=server_data["server"].get("awg_h3"),
                    h4=server_data["server"].get("awg_h4"),
                )
            from src.core.wireguard import WireGuardManager
            return WireGuardManager(**_ssh_kwargs)

        config_file = None
        for f in Path(backup_dir).glob(f"wg_config_*_{server_name}.conf"):
            config_file = f
            break

        if config_file:
            try:
                wg = _make_wg()
                try:
                    result["config_deployed"] = wg.write_config_file(config_file.read_text())
                finally:
                    wg.close()
            except Exception as e:
                result["config_deploy_error"] = str(e)

        if result.get("config_deployed") or result.get("agent_installed"):
            try:
                wg = _make_wg()
                try:
                    for client_data in server_data.get("clients", []):
                        if not client_data.get("enabled", True):
                            continue
                        try:
                            allowed_ips = client_data["ipv4"] + "/32"
                            if client_data.get("ipv6"):
                                allowed_ips += f",{client_data['ipv6']}/128"
                            wg.add_peer(
                                client_data["public_key"], allowed_ips,
                                preshared_key=client_data.get("preshared_key"),
                            )
                            result["peers_restored"] += 1
                        except Exception:
                            pass
                finally:
                    wg.close()
            except Exception as e:
                result["peer_restore_error"] = str(e)

        server = self.db.query(Server).filter(Server.name == server_name).first()
        if server:
            server.ssh_host = new_ssh_host
            server.ssh_port = new_ssh_port
            server.ssh_user = new_ssh_user
            server.ssh_password = new_ssh_password
            server.endpoint = f"{new_ssh_host}:{server.listen_port}"
            self.db.commit()
            result["db_updated"] = True

        logger.info(f"Server migration '{server_name}' → {new_ssh_host}: {result}")
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _archive_path(self, backup_id: str) -> str:
        """Return expected path to v2 tar.gz archive."""
        return os.path.join(self.backup_dir, f"vpnmanager-backup-{backup_id}.tar.gz")

    def _dump_database_to(self, dest_path: str):
        """pg_dump -Fc | gzip → dest_path (.sql.gz)."""
        pg = _get_pg_params()
        db_host = pg["host"]
        db_port = pg["port"]
        db_user = pg["user"]
        db_name = pg["name"]

        env = os.environ.copy()
        env["PGPASSWORD"] = pg["password"]

        pg_dump = subprocess.Popen(
            ["pg_dump", "-h", db_host, "-p", db_port, "-U", db_user, "-Fc", db_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        with open(dest_path, "wb") as f:
            gzip_proc = subprocess.Popen(
                ["gzip"], stdin=pg_dump.stdout, stdout=f, stderr=subprocess.PIPE,
            )
            pg_dump.stdout.close()
            gzip_proc.communicate()
        pg_dump.wait()
        if pg_dump.returncode != 0:
            stderr = pg_dump.stderr.read().decode() if pg_dump.stderr else ""
            raise RuntimeError(f"pg_dump failed (rc={pg_dump.returncode}): {stderr}")

    def _restore_database_from_file(self, dump_path: str):
        """gunzip | pg_restore from dump_path (.sql.gz)."""
        pg = _get_pg_params()
        db_host = pg["host"]
        db_port = pg["port"]
        db_user = pg["user"]
        db_name = pg["name"]

        env = os.environ.copy()
        env["PGPASSWORD"] = pg["password"]

        gunzip = subprocess.Popen(
            ["gunzip", "-c", dump_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        restore = subprocess.Popen(
            ["pg_restore", "-h", db_host, "-p", db_port, "-U", db_user,
             "-d", db_name, "--clean", "--if-exists"],
            stdin=gunzip.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        gunzip.stdout.close()
        stdout, stderr = restore.communicate()
        gunzip.wait()

        if restore.returncode not in (0, 1):
            raise RuntimeError(f"pg_restore failed (rc={restore.returncode}): {stderr.decode()}")

    def _dump_database(self, backup_dir: str):
        """Legacy helper: dump to backup_dir/database.sql.gz."""
        self._dump_database_to(os.path.join(backup_dir, "database.sql.gz"))

    def _export_server_clients(self, server: Server, backup_dir: str) -> int:
        """Export all clients for a server as JSON into backup_dir."""
        clients = (
            self.db.query(Client)
            .options(
                load_only(
                    Client.id,
                    Client.name,
                    Client.server_id,
                    Client.public_key,
                    Client.private_key,
                    Client.preshared_key,
                    Client.ip_index,
                    Client.ipv4,
                    Client.ipv6,
                    Client.enabled,
                    Client.status,
                    Client.bandwidth_limit,
                    Client.traffic_limit_mb,
                    Client.traffic_used_rx,
                    Client.traffic_used_tx,
                    Client.expiry_date,
                    Client.created_at,
                )
            )
            .filter(Client.server_id == server.id)
            .all()
        )

        server_data = {
            "server": {
                "id": server.id, "name": server.name, "endpoint": server.endpoint,
                "interface": server.interface, "listen_port": server.listen_port,
                "public_key": server.public_key, "address_pool_ipv4": server.address_pool_ipv4,
                "dns": server.dns, "mtu": server.mtu,
                "persistent_keepalive": server.persistent_keepalive,
                "config_path": server.config_path, "ssh_host": server.ssh_host,
                "ssh_port": server.ssh_port, "ssh_user": server.ssh_user,
                "agent_mode": server.agent_mode, "agent_url": server.agent_url,
                "is_default": server.is_default,
                # Protocol metadata
                "server_type": self._safe_attr(server, "server_type", "wireguard"),
                "server_category": self._safe_attr(server, "server_category", "vpn"),
                # AmneziaWG fields
                "awg_jc": self._safe_attr(server, "awg_jc", None),
                "awg_jmin": self._safe_attr(server, "awg_jmin", None),
                "awg_jmax": self._safe_attr(server, "awg_jmax", None),
                "awg_s1": self._safe_attr(server, "awg_s1", None),
                "awg_s2": self._safe_attr(server, "awg_s2", None),
                "awg_h1": self._safe_attr(server, "awg_h1", None),
                "awg_h2": self._safe_attr(server, "awg_h2", None),
                "awg_h3": self._safe_attr(server, "awg_h3", None),
                "awg_h4": self._safe_attr(server, "awg_h4", None),
                "awg_mtu": self._safe_attr(server, "awg_mtu", None),
                "supports_peer_visibility": self._safe_attr(server, "supports_peer_visibility", True),
                # Proxy fields
                "proxy_domain": self._safe_attr(server, "proxy_domain", None),
                "proxy_tls_mode": self._safe_attr(server, "proxy_tls_mode", None),
                "proxy_cert_path": self._safe_attr(server, "proxy_cert_path", None),
                "proxy_key_path": self._safe_attr(server, "proxy_key_path", None),
                "proxy_config_path": self._safe_attr(server, "proxy_config_path", None),
                "proxy_service_name": self._safe_attr(server, "proxy_service_name", None),
                "proxy_obfs_password": self._safe_attr(server, "proxy_obfs_password", None),
            },
            "clients": [],
        }

        for c in clients:
            server_data["clients"].append({
                "id": c.id, "name": c.name, "public_key": c.public_key,
                "private_key": c.private_key, "preshared_key": c.preshared_key,
                "ip_index": c.ip_index, "ipv4": c.ipv4, "ipv6": c.ipv6,
                "enabled": c.enabled,
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "bandwidth_limit": c.bandwidth_limit, "traffic_limit_mb": c.traffic_limit_mb,
                "traffic_used_rx": c.traffic_used_rx, "traffic_used_tx": c.traffic_used_tx,
                "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                # Proxy client auth
                "proxy_password": self._safe_attr(c, "proxy_password", None),
                "proxy_uuid": self._safe_attr(c, "proxy_uuid", None),
            })

        filename = f"server_{server.id}_{_sanitize_name_for_filename(server.name)}.json"
        with open(os.path.join(backup_dir, filename), "w") as f:
            json.dump(server_data, f, indent=2, default=str)

        return len(clients)

    def _backup_wg_config(self, server: Server, backup_dir: str):
        """Backup protocol config file from server into backup_dir."""
        from src.core.wireguard import WireGuardManager

        server_type = self._safe_attr(server, "server_type", "wireguard")
        server_category = self._safe_attr(server, "server_category", "vpn")

        # Proxy servers: read config via SSH / local file
        if server_category == "proxy" or server_type in ("hysteria2", "tuic"):
            self._backup_proxy_config(server, backup_dir)
            return

        if server.agent_mode == "agent" and server.agent_url:
            import httpx
            resp = httpx.get(
                f"{server.agent_url}/config",
                headers={"X-API-Key": server.agent_api_key or ""},
                timeout=10,
            )
            if resp.status_code == 200:
                config_content = resp.json().get("content", "")
            else:
                raise RuntimeError(f"Agent returned {resp.status_code}")
        else:
            is_awg = self._safe_attr(server, "server_type", "wireguard") == "amneziawg"
            if is_awg:
                from src.core.amneziawg import AmneziaWGManager
                # Normalise config_path: prefer DB value, fall back to standard AWG path.
                # Legacy servers or manually-installed AWG may store the conf in a
                # non-standard location (e.g. /opt/amneziawg/config/).
                cfg_path = server.config_path or ""
                if not cfg_path or cfg_path.startswith("/etc/wireguard/"):
                    cfg_path = f"/etc/amneziawg/{server.interface}.conf"
                wg = AmneziaWGManager(
                    ssh_host=server.ssh_host, ssh_port=server.ssh_port,
                    ssh_user=server.ssh_user, ssh_password=server.ssh_password,
                    ssh_private_key=server.ssh_private_key,
                    interface=server.interface, config_path=cfg_path,
                    jc=self._safe_attr(server, "awg_jc", 4) or 4,
                    jmin=self._safe_attr(server, "awg_jmin", 50) or 50,
                    jmax=self._safe_attr(server, "awg_jmax", 100) or 100,
                    s1=self._safe_attr(server, "awg_s1", 80) or 80,
                    s2=self._safe_attr(server, "awg_s2", 40) or 40,
                    h1=self._safe_attr(server, "awg_h1", 0) or 0,
                    h2=self._safe_attr(server, "awg_h2", 0) or 0,
                    h3=self._safe_attr(server, "awg_h3", 0) or 0,
                    h4=self._safe_attr(server, "awg_h4", 0) or 0,
                )
            else:
                wg = WireGuardManager(
                    ssh_host=server.ssh_host, ssh_port=server.ssh_port,
                    ssh_user=server.ssh_user, ssh_password=server.ssh_password,
                    ssh_private_key=server.ssh_private_key,
                    interface=server.interface, config_path=server.config_path,
                )
            config_content = wg.read_config_file()

            # If primary path returned nothing, try well-known fallback locations.
            # This handles manually-installed servers where the conf is not in the
            # standard /etc/wireguard/ or /etc/amneziawg/ directory.
            if not config_content and is_awg:
                iface = server.interface or "awg0"
                fallback_paths = [
                    f"/etc/amneziawg/{iface}.conf",
                    f"/opt/amneziawg/config/{iface}.conf",
                    f"/opt/amneziawg/{iface}.conf",
                ]
                tried = [wg.config_path]
                for fb_path in fallback_paths:
                    if fb_path == wg.config_path:
                        continue
                    tried.append(fb_path)
                    wg.config_path = fb_path
                    config_content = wg.read_config_file()
                    if config_content:
                        logger.warning(
                            f"AWG config not at stored path '{server.config_path}', "
                            f"found at fallback '{fb_path}' — update server config_path in DB"
                        )
                        break

            if not config_content:
                raise RuntimeError(
                    f"Config file not found or empty at '{server.config_path}'"
                )

        config_filename = f"wg_config_{server.id}_{_sanitize_name_for_filename(server.name)}.conf"
        with open(os.path.join(backup_dir, config_filename), "w") as f:
            f.write(config_content)

    def _backup_proxy_config(self, server: Server, backup_dir: str):
        """Backup proxy (Hysteria2 / TUIC) config file from server into backup_dir."""
        from src.core.proxy_base import ProxyBaseManager
        server_type = getattr(server, "server_type", "hysteria2")
        config_path = getattr(server, "proxy_config_path", None) or (
            "/etc/hysteria/config.yaml" if server_type == "hysteria2"
            else "/etc/tuic/config.json"
        )
        mgr = ProxyBaseManager(
            config_path=config_path,
            service_name=getattr(server, "proxy_service_name", "") or "",
            ssh_host=server.ssh_host,
            ssh_port=server.ssh_port or 22,
            ssh_user=server.ssh_user or "root",
            ssh_password=server.ssh_password,
            ssh_private_key=server.ssh_private_key,
        )
        try:
            content = mgr.get_config_for_backup() if hasattr(mgr, 'get_config_for_backup') else mgr._read_file(config_path)
        finally:
            mgr.close()

        if not content:
            logger.warning(
                f"Proxy config not found for server '{server.name}' "
                f"(id={server.id}, type={getattr(server,'server_type','?')}) "
                f"at path '{config_path}'. "
                f"The server may not be bootstrapped yet or the config path in DB is stale."
            )
            return

        ext = "yaml" if server_type == "hysteria2" else "json"
        filename = f"proxy_config_{server.id}_{_sanitize_name_for_filename(server.name)}.{ext}"
        with open(os.path.join(backup_dir, filename), "w") as f:
            f.write(content)

    def _managed_services(self) -> list[str]:
        return [
            "vpnmanager-api", "vpnmanager-worker", "vpnmanager-admin-bot", "vpnmanager-client-bot", "vpnmanager-client-portal",
            "spongebot-api", "spongebot-worker", "spongebot-admin-bot", "spongebot-client-bot", "spongebot-client-portal",
        ]

    def _stop_services(self) -> list[str]:
        """Stop active product services and return the stopped unit names."""
        stopped = []
        for svc in self._managed_services():
            result = subprocess.run(["systemctl", "is-active", "--quiet", svc], capture_output=True)
            if result.returncode == 0:
                subprocess.run(["systemctl", "stop", svc], capture_output=True)
                stopped.append(svc)
        logger.info(f"Stopped services: {stopped}")
        return stopped

    def _restart_services(self, services: Optional[list[str]] = None):
        """Restart product services via systemctl."""
        if services is None:
            services = []
            for svc in self._managed_services():
                result = subprocess.run(["systemctl", "is-active", "--quiet", svc], capture_output=True)
                if result.returncode == 0:
                    services.append(svc)
        restarted = []
        for svc in services:
            subprocess.run(["systemctl", "start", svc], capture_output=True)
            restarted.append(svc)
        logger.info(f"Restarted services: {restarted}")
