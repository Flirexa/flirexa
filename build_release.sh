#!/bin/bash
#===============================================================================
# VPN Manager — Release Build Script
# Creates a clean distributable package with no personal data
#
# Usage:
#   bash build_release.sh [version]
#   bash build_release.sh 1.0.0
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null | tr -d '[:space:]')}"
VERSION="${VERSION:-1.0.0}"

# ── VENDOR: license server URLs ───────────────────────────────────────────────
VENDOR_LICENSE_PRIMARY_URL="${VENDOR_LICENSE_PRIMARY_URL:-https://flirexa.biz}"
VENDOR_LICENSE_BACKUP_URL="${VENDOR_LICENSE_BACKUP_URL:-}"
# ─────────────────────────────────────────────────────────────────────────────
PRODUCT_NAME="vpn-manager"
PACKAGE_NAME="${PRODUCT_NAME}-v${VERSION}"
BUILD_DIR=$(mktemp -d "/tmp/${PACKAGE_NAME}-build.XXXXXX")
OUTPUT_DIR="${SCRIPT_DIR}"
ARCHIVE="${OUTPUT_DIR}/${PACKAGE_NAME}.tar.gz"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "============================================"
echo "  VPN Manager v${VERSION} — Release Builder"
echo "============================================"
echo ""

# Verify we're in the project directory
[[ -f "$SCRIPT_DIR/main.py" ]] || log_error "Run from the project root directory"

# ── Step 1: Build Admin Frontend ──
log_info "Building admin frontend..."
FRONTEND_DIR="$SCRIPT_DIR/src/web/frontend"
cd "$FRONTEND_DIR"
if [[ ! -d "node_modules" ]]; then
    npm install --silent 2>&1 | tail -1
fi
npm run build 2>&1 | tail -3
cd "$SCRIPT_DIR"
log_success "Admin frontend built"

# ── Step 2: Build Client Portal Frontend ──
log_info "Building client portal frontend..."
CP_FRONTEND_DIR="$SCRIPT_DIR/src/web/client-portal"
cd "$CP_FRONTEND_DIR"
if [[ ! -d "node_modules" ]]; then
    npm install --silent 2>&1 | tail -1
fi
npm run build 2>&1 | tail -3
cd "$SCRIPT_DIR"
log_success "Client portal frontend built"

# ── Step 3: Create clean copy ──
log_info "Creating clean copy..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Copy source files (excluding unnecessary dirs)
rsync -a \
    --exclude='.git' \
    --exclude='.gitignore' \
    --exclude='.claude' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='*.egg-info' \
    --exclude='.env' \
    --exclude='*.tar.gz' \
    --exclude='build_release.sh' \
    --exclude='deploy.sh' \
    --exclude='android-app' \
    --exclude='distribution' \
    "$SCRIPT_DIR/" "$BUILD_DIR/"

log_success "Files copied"

# ── Step 4: Remove personal/development files ──
log_info "Removing personal data and dev files..."

# Development & AI context files
rm -rf "$BUILD_DIR/CLAUDE.md"
rm -rf "$BUILD_DIR/MEMORY.md"
rm -rf "$BUILD_DIR/PLAN.md"
rm -rf "$BUILD_DIR/docs/"
# Copy buyer-facing documentation (clean, no personal data)
if [[ -d "$SCRIPT_DIR/distribution/docs" ]]; then
    cp -r "$SCRIPT_DIR/distribution/docs" "$BUILD_DIR/docs"
    log_success "Distribution docs included ($(ls "$SCRIPT_DIR/distribution/docs/" | wc -l) files)"
else
    log_warn "distribution/docs/ not found — release will not include documentation"
fi
rm -rf "$BUILD_DIR/AGENT_ARCHITECTURE.md"
rm -rf "$BUILD_DIR/AGENT_QUICKSTART.md"
rm -rf "$BUILD_DIR/2026-"*  # session continuation files
rm -rf "$BUILD_DIR/NEW_MODULES_CLIENT_PORTAL/"

# Build & packaging scripts (internal use only)
rm -rf "$BUILD_DIR/package.sh"
# NOTE: update.sh and deploy/ are KEPT for buyer use

# Android app is excluded from distribution (too large; buyer builds APK separately)

# Tests (not needed in distribution)
rm -rf "$BUILD_DIR/tests/"
rm -rf "$BUILD_DIR/pytest.ini"

# Remove pre-built branded APKs (buyer builds their own)
rm -f "$BUILD_DIR/src/web/static/SpongeBot-"*.apk
rm -f "$BUILD_DIR/src/web/static/spongebot-"*.apk

# License generation tool and private key (seller-only, NOT included)
rm -rf "$BUILD_DIR/tools/generate_license.py"
rm -rf "$BUILD_DIR/tools/license_private.pem"
rm -rf "$BUILD_DIR/tools/license_public.pem"

# Existing env file
rm -f "$BUILD_DIR/.env"

# Runtime-generated license state must never ship in a release package.
rm -f "$BUILD_DIR/data/first_startup_at.txt"
rm -f "$BUILD_DIR/data/license_cache.json"

# Runtime-generated license state must never ship in a release package.
rm -f "$BUILD_DIR/data/first_startup_at.txt"
rm -f "$BUILD_DIR/data/license_cache.json"

# Keep Alembic metadata and migration files for database upgrades
# Only remove legacy JSON import data if that old path exists
rm -f "$BUILD_DIR/migrations/json_import/"*.json 2>/dev/null || true

# Setup.py (dev only)
rm -f "$BUILD_DIR/setup.py"

# Copy distribution README
if [[ -f "$SCRIPT_DIR/README.dist.md" ]]; then
    cp "$SCRIPT_DIR/README.dist.md" "$BUILD_DIR/README.md"
fi

log_success "Personal data removed"

# ── Step 5: Clean hardcoded values ──
log_info "Cleaning hardcoded values..."

# Replace hardcoded IPs with placeholders in config
if [[ -f "$BUILD_DIR/config/default.py" ]]; then
    sed -i 's|88\.210\.21\.252:[0-9]*|YOUR_SERVER_IP:51820|g' "$BUILD_DIR/config/default.py"
    sed -i 's|/root/spongebot_new/data|/opt/vpnmanager/data|g' "$BUILD_DIR/config/default.py"
    sed -i 's|APP_NAME: str = "SpongeBot"|APP_NAME: str = "VPN Manager"|g' "$BUILD_DIR/config/default.py"
fi

# Clean hardcoded IPs in server_manager
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|88\.210\.21\.252:[0-9]*|YOUR_SERVER_IP:51820|g' {} +

# Clean hardcoded IPs in test fixtures (if any tests remain)
find "$BUILD_DIR" -name "*.py" -exec sed -i 's|88\.210\.21\.117|REMOTE_SERVER_IP|g' {} +

# Remove hardcoded database credentials from connection.py
if [[ -f "$BUILD_DIR/src/database/connection.py" ]]; then
    sed -i 's|postgresql://spongebot:spongebot@localhost:5432/spongebot_db|postgresql://vpnmanager:password@localhost:5432/vpnmanager_db|g' "$BUILD_DIR/src/database/connection.py"
fi

# Clean backup paths
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|/opt/spongebot|/opt/vpnmanager|g' {} +
find "$BUILD_DIR" -name "*.py" -exec sed -i 's|spongebot-salt|vpnmanager-salt|g' {} +
find "$BUILD_DIR" -name "*.py" -exec sed -i 's|spongebot-fallback|vpnmanager-fallback|g' {} +

# Clean service names in bots.py and similar
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|spongebot-admin-bot|vpnmanager-admin-bot|g' {} +
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|spongebot-client-bot|vpnmanager-client-bot|g' {} +
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|spongebot-worker|vpnmanager-worker|g' {} +

# Clean DB fallback defaults
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|"spongebot_db"|"vpnmanager_db"|g' {} +
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|"spongebot")|"vpnmanager")|g' {} +

# Clean env var names (SPONGEBOT_BACKUP_DIR → BACKUP_DIR, SPONGEBOT_ENCRYPTION_KEY → ENCRYPTION_KEY)
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|SPONGEBOT_BACKUP_DIR|BACKUP_DIR|g' {} +
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|SPONGEBOT_ENCRYPTION_KEY|ENCRYPTION_KEY|g' {} +

# Clean mount points
find "$BUILD_DIR" -name "*.py" -exec sed -i 's|/mnt/spongebot-backup|/mnt/vpnmanager-backup|g' {} +

# Clean agent_bootstrap.py: spongebot-agent → vpnmanager-agent
find "$BUILD_DIR/src" -name "*.py" -exec sed -i 's|spongebot-agent|vpnmanager-agent|g' {} +
find "$BUILD_DIR" -name "agent.py" -exec sed -i 's|spongebot-agent|vpnmanager-agent|g' {} +

# Clean hardcoded IPs in Vue source files (placeholder IPs)
find "$BUILD_DIR/src/web" -name "*.vue" -exec sed -i 's|88\.210\.21\.117|your.server.ip|g' {} +

# Clean npm package names
find "$BUILD_DIR/src/web" -name "package.json" -exec sed -i 's|"spongebot-panel"|"vpn-manager-panel"|g' {} +
find "$BUILD_DIR/src/web" -name "package.json" -exec sed -i 's|"spongebot-client-portal"|"vpn-manager-client-portal"|g' {} +
find "$BUILD_DIR/src/web" -name "package-lock.json" -exec sed -i 's|"spongebot-panel"|"vpn-manager-panel"|g' {} +
find "$BUILD_DIR/src/web" -name "package-lock.json" -exec sed -i 's|"spongebot-client-portal"|"vpn-manager-client-portal"|g' {} +

# Clean Vue frontend strings
find "$BUILD_DIR/src/web" -name "*.vue" -exec sed -i "s|/opt/spongebot/backups|/opt/vpnmanager/backups|g" {} +
find "$BUILD_DIR/src/web" -name "*.vue" -exec sed -i "s|/mnt/spongebot-backup|/mnt/vpnmanager-backup|g" {} +
find "$BUILD_DIR/src/web" -name "*.vue" -exec sed -i "s|spongebot-client|vpnmanager-client|g" {} +
find "$BUILD_DIR/src/web" -name "*.vue" -exec sed -i "s|SpongeBot|VPN Manager|g" {} +
find "$BUILD_DIR/src/web" -name "*.js" -exec sed -i "s|SpongeBot|VPN Manager|g" {} +

# Clean Python docstrings and comments
find "$BUILD_DIR/src" -name "*.py" -exec sed -i "s|SpongeBot|VPN Manager|g" {} +
find "$BUILD_DIR" -maxdepth 1 -name "*.py" -exec sed -i "s|SpongeBot|VPN Manager|g" {} +

# Clean requirements.txt
sed -i "s|SpongeBot|VPN Manager|g" "$BUILD_DIR/requirements.txt" 2>/dev/null || true

# Clean config module
find "$BUILD_DIR/config" -name "*.py" -exec sed -i "s|SpongeBot|VPN Manager|g" {} +
find "$BUILD_DIR/config" -name "*.py" -exec sed -i "s|spongebot:spongebot@localhost:5432/spongebot_db|vpnmanager:vpnmanager@localhost:5432/vpnmanager_db|g" {} +

# Clean alembic DB URL
if [[ -f "$BUILD_DIR/alembic/env.py" ]]; then
    sed -i 's|spongebot:spongebot@localhost:5432/spongebot_db|vpnmanager:vpnmanager@localhost:5432/vpnmanager_db|g' "$BUILD_DIR/alembic/env.py"
fi

# Clean .env.example
if [[ -f "$BUILD_DIR/.env.example" ]]; then
    sed -i 's|spongebot-worker|vpnmanager-worker|g' "$BUILD_DIR/.env.example"
    sed -i 's|spongebot|vpnmanager|g' "$BUILD_DIR/.env.example"
fi

# Clean index.html files
find "$BUILD_DIR/src/web" -name "index.html" -exec sed -i "s|SpongeBot[^\"]*|VPN Manager|g" {} +

# Clean update script
if [[ -f "$BUILD_DIR/update.sh" ]]; then
    sed -i 's|/opt/spongebot|/opt/vpnmanager|g' "$BUILD_DIR/update.sh"
    sed -i 's|/root/spongebot_new|/opt/vpnmanager|g' "$BUILD_DIR/update.sh"
    sed -i 's|/root/spongebot_backups|/root/vpnmanager_backups|g' "$BUILD_DIR/update.sh"
    sed -i 's|spongebot-api|vpnmanager-api|g' "$BUILD_DIR/update.sh"
    sed -i 's|spongebot-admin-bot|vpnmanager-admin-bot|g' "$BUILD_DIR/update.sh"
    sed -i 's|spongebot-client-bot|vpnmanager-client-bot|g' "$BUILD_DIR/update.sh"
    sed -i 's|spongebot-client-portal|vpnmanager-client-portal|g' "$BUILD_DIR/update.sh"
    sed -i 's|spongebot-worker|vpnmanager-worker|g' "$BUILD_DIR/update.sh"
    sed -i 's|/tmp/spongebot-|/tmp/vpnmanager-|g' "$BUILD_DIR/update.sh"
    sed -i 's|echo "spongebot"|echo "vpnmanager"|g' "$BUILD_DIR/update.sh"
    sed -i 's|"spongebot"|"vpnmanager"|g' "$BUILD_DIR/update.sh"
    sed -i 's|"spongebot_db"|"vpnmanager_db"|g' "$BUILD_DIR/update.sh"
    sed -i 's|SpongeBot|VPN Manager|g' "$BUILD_DIR/update.sh"
    sed -i 's|SPONGEBOT_DIR|APP_DIR|g' "$BUILD_DIR/update.sh"
fi

# Clean install script
if [[ -f "$BUILD_DIR/install.sh" ]]; then
    sed -i 's|INSTALL_DIR="/opt/spongebot"|INSTALL_DIR="/opt/vpnmanager"|g' "$BUILD_DIR/install.sh"
    sed -i 's|DB_USER="spongebot"|DB_USER="vpnmanager"|g' "$BUILD_DIR/install.sh"
    sed -i 's|DB_NAME="spongebot_db"|DB_NAME="vpnmanager_db"|g' "$BUILD_DIR/install.sh"
    sed -i 's|spongebot-api|vpnmanager-api|g' "$BUILD_DIR/install.sh"
    sed -i 's|spongebot-client-portal|vpnmanager-client-portal|g' "$BUILD_DIR/install.sh"
    sed -i 's|SpongeBot|VPN Manager|g' "$BUILD_DIR/install.sh"
    sed -i 's|SPONGEBOT_VERSION|APP_VERSION|g' "$BUILD_DIR/install.sh"
fi

# Rename and clean systemd service files
if [[ -d "$BUILD_DIR/deploy/systemd" ]]; then
    for svc in "$BUILD_DIR/deploy/systemd/spongebot-"*.service; do
        [[ -f "$svc" ]] || continue
        newname=$(basename "$svc" | sed 's/spongebot-/vpnmanager-/')
        sed -i 's|SpongeBot|VPN Manager|g; s|/opt/spongebot|/opt/vpnmanager|g; s|spongebot-|vpnmanager-|g' "$svc"
        mv "$svc" "$BUILD_DIR/deploy/systemd/$newname"
    done
fi
if [[ -f "$BUILD_DIR/deploy/spongebot-client-portal.service" ]]; then
    sed -i 's|SpongeBot|VPN Manager|g; s|/opt/spongebot|/opt/vpnmanager|g; s|spongebot-|vpnmanager-|g' "$BUILD_DIR/deploy/spongebot-client-portal.service"
    mv "$BUILD_DIR/deploy/spongebot-client-portal.service" "$BUILD_DIR/deploy/vpnmanager-client-portal.service"
fi


log_success "Hardcoded values cleaned"

# ── Step 5b: Bake license server URLs into server_config.py ──
log_info "Baking license server URLs into server_config.py..."
SERVER_CONFIG_FILE="$BUILD_DIR/src/modules/license/server_config.py"

if [[ -n "$VENDOR_LICENSE_PRIMARY_URL" ]]; then
    sed -i "s|_FALLBACK_PRIMARY = \"\".*# VENDOR_PRIMARY_PLACEHOLDER|_FALLBACK_PRIMARY = \"${VENDOR_LICENSE_PRIMARY_URL}\"   # baked by build_release.sh|" "$SERVER_CONFIG_FILE"
    sed -i "s|_FALLBACK_BACKUP  = \"\".*# VENDOR_BACKUP_PLACEHOLDER|_FALLBACK_BACKUP  = \"${VENDOR_LICENSE_BACKUP_URL}\"   # baked by build_release.sh|" "$SERVER_CONFIG_FILE"
    log_success "License server URLs baked in: primary=$VENDOR_LICENSE_PRIMARY_URL"
else
    log_warn "VENDOR_LICENSE_PRIMARY_URL not set — fallback URLs will be empty"
    log_info "  Set them via: VENDOR_LICENSE_PRIMARY_URL=https://... bash build_release.sh"
fi

# ── Step 5c: Generate license_servers.signed ──
PRIVATE_KEY="$SCRIPT_DIR/license_server/keys/server_verify_private.pem"
if [[ -n "$VENDOR_LICENSE_PRIMARY_URL" && -f "$PRIVATE_KEY" ]]; then
    log_info "Generating license_servers.signed..."
    mkdir -p "$BUILD_DIR/data"
    python3 - "$VENDOR_LICENSE_PRIMARY_URL" "$VENDOR_LICENSE_BACKUP_URL" "$PRIVATE_KEY" "$BUILD_DIR/data/license_servers.signed" <<'PYEOF'
import base64, json, sys
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key

primary, backup, key_path, output = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
payload = json.dumps({
    "primary":   primary,
    "backup":    backup,
    "issued_at": datetime.now(timezone.utc).isoformat(),
    "version":   1,
}, separators=(',', ':')).encode()
payload_b64 = base64.urlsafe_b64encode(payload).rstrip(b'=').decode()

with open(key_path, 'rb') as f:
    private_key = load_pem_private_key(f.read(), password=None)

sig = private_key.sign(
    payload_b64.encode('ascii'),
    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
    hashes.SHA256()
)
sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b'=').decode()
with open(output, 'w') as f:
    json.dump({"payload": payload_b64, "signature": sig_b64}, f, indent=2)
print(f"Generated: {output}")
PYEOF
    log_success "license_servers.signed generated"
else
    if [[ -z "$VENDOR_LICENSE_PRIMARY_URL" ]]; then
        log_warn "Skipped license_servers.signed — VENDOR_LICENSE_PRIMARY_URL not set"
    else
        log_warn "Skipped license_servers.signed — server_verify_private.pem not found at $PRIVATE_KEY"
    fi
fi

# ── Step 6: Code protection (PyArmor + optional Nuitka) ──────────────────────
LICENSE_DIR="$BUILD_DIR/src/modules/license"
PROTECT_OK=0

# ── 6a. PyArmor: obfuscate entire license package (cross-platform, Python 3.10+) ──
if command -v pyarmor &>/dev/null; then
    log_info "Obfuscating license module with PyArmor..."
    PYARMOR_TMP=$(mktemp -d)

    # Generate obfuscated package + runtime
    cd "$BUILD_DIR/src"
    if pyarmor gen --recursive --output "$PYARMOR_TMP" modules/license/ 2>/dev/null; then
        # Replace original .py files with obfuscated versions
        # PyArmor strips the leading path component → output is in $TMP/license/
        cp "$PYARMOR_TMP/license/"*.py "$LICENSE_DIR/"

        # Bundle pyarmor_runtime into src/ (importable as pyarmor_runtime_000000)
        if [[ -d "$PYARMOR_TMP/pyarmor_runtime_000000" ]]; then
            rm -rf "$BUILD_DIR/src/pyarmor_runtime_000000"
            cp -r "$PYARMOR_TMP/pyarmor_runtime_000000" "$BUILD_DIR/src/"
        fi

        # Remove stale __pycache__ from license module (pyarmor replaces .py files;
        # old .pyc bytecodes would expose original code structure)
        rm -rf "$LICENSE_DIR/__pycache__"

        PROTECT_OK=1
        log_success "PyArmor: license module obfuscated (5 files + runtime bundled)"
    else
        log_warn "PyArmor failed — skipping obfuscation"
    fi

    rm -rf "$PYARMOR_TMP"
    cd "$SCRIPT_DIR"
else
    log_warn "PyArmor not installed — skipping obfuscation (pip install pyarmor)"
fi

# ── 6b. Nuitka: compile .so extensions (optional, requires NUITKA_BUILD=1) ────
# NOTE: compiled .so files are Python-version specific.
# Only enable if you know the target server's Python version matches the build machine.
# Usage: NUITKA_BUILD=1 bash build_release.sh
if [[ "${NUITKA_BUILD:-0}" == "1" ]]; then
    if python3 -m nuitka --version &>/dev/null 2>&1; then
        log_info "Nuitka: compiling license modules to .so (Python $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'))"
        NUITKA_TMP=$(mktemp -d)
        NUITKA_COUNT=0

        for modname in manager online_validator server_config instance_manager; do
            SRC_FILE="$LICENSE_DIR/${modname}.py"
            [[ -f "$SRC_FILE" ]] || continue

            python3 -m nuitka \
                --module "$SRC_FILE" \
                --output-dir="$NUITKA_TMP" \
                --no-progressbar --quiet 2>/dev/null

            SO_FILE=$(ls "$NUITKA_TMP/${modname}.cpython-"*.so 2>/dev/null | head -1)
            if [[ -n "$SO_FILE" ]]; then
                cp "$SO_FILE" "$LICENSE_DIR/"
                rm "$LICENSE_DIR/${modname}.py"  # remove .py: .so takes precedence
                NUITKA_COUNT=$((NUITKA_COUNT + 1))
            fi
        done

        rm -rf "$NUITKA_TMP"
        [[ $NUITKA_COUNT -gt 0 ]] && \
            log_success "Nuitka: compiled $NUITKA_COUNT modules to .so (replaces PyArmor .py for those files)" || \
            log_warn "Nuitka: no modules compiled successfully"
    else
        log_warn "Nuitka not installed — skipping .so compilation (pip install nuitka)"
    fi
fi

[[ $PROTECT_OK -eq 0 ]] && log_warn "No code protection applied — install: pip install pyarmor"

# ── Step 7: Compile .py to .pyc (basic protection) ──
log_info "Compiling Python files..."
python3 -m compileall -q "$BUILD_DIR/src/" 2>/dev/null || true
log_success "Python files compiled"

# ── Step 8: Verify no personal data leaked ──
log_info "Verifying clean build..."
LEAKS=0

# Check for known personal data patterns
for pattern in "88\.210\.21\.252" "spongebot_new" "spongebot-agent" "SpongeBot" "/opt/spongebot" "6092707086" "7191621986" "AAGEEsp2Wchkj1tb" "AAHqZPguWEHW" "claude_remote_key" "b5645999f3085c3d"; do
    if grep -r "$pattern" "$BUILD_DIR/" --include="*.py" --include="*.sh" --include="*.env*" --include="*.json" --include="*.yml" --include="*.vue" --include="*.js" --include="*.html" --include="*.pem" -l 2>/dev/null; then
        log_warn "LEAK FOUND: pattern '$pattern' in above files"
        LEAKS=$((LEAKS + 1))
    fi
done

if [[ $LEAKS -gt 0 ]]; then
    log_warn "$LEAKS potential data leaks found — review before distributing!"
else
    log_success "No personal data leaks detected"
fi

# ── Step 9: Package ──
log_info "Creating archive: ${ARCHIVE}..."

BUILD_BASENAME=$(basename "$BUILD_DIR")
cd /tmp
tar -czf "$ARCHIVE" "$BUILD_BASENAME" --transform="s|${BUILD_BASENAME}|${PACKAGE_NAME}|"

# Cleanup
rm -rf "$BUILD_DIR"

# Show result
ARCHIVE_SIZE=$(du -h "$ARCHIVE" | awk '{print $1}')
FILE_COUNT=$(tar -tzf "$ARCHIVE" | wc -l)

echo ""
log_success "Release package created: ${ARCHIVE}"
log_info "  Size: ${ARCHIVE_SIZE}"
log_info "  Files: ${FILE_COUNT}"
echo ""
echo "  Deploy to a fresh server:"
echo "    scp ${ARCHIVE} root@server:/root/"
echo "    ssh root@server"
echo "    tar xzf ${PACKAGE_NAME}.tar.gz"
echo "    cd ${PACKAGE_NAME} && sudo bash install.sh"
echo ""

# ── Step 10: Copy release archive to backups ──────────────────────────────────
cd "$SCRIPT_DIR"
# Delete stale release archives from previous versions (not current)
find . -maxdepth 1 -name "vpn-manager-*.tar.gz" ! -name "$(basename "$ARCHIVE")" -delete 2>/dev/null || true

BACKUP_PATHS=(
    "/home/remzi/my_vpn_project"
    "/media/remzi/Anitka/spongebot_backups"
)

for BDIR in "${BACKUP_PATHS[@]}"; do
    if [[ -d "$BDIR" ]]; then
        # Remove old release archives, keep only current
        find "$BDIR" -maxdepth 1 -name "vpn-manager-*.tar.gz" ! -name "$(basename "$ARCHIVE")" -delete 2>/dev/null || true
        cp "$ARCHIVE" "$BDIR/"
        log_success "Backups copied → ${BDIR}/"
    else
        log_warn "Backup dir not mounted, skipping: ${BDIR}"
    fi
done
