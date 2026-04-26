#!/bin/bash
#===============================================================================
# VPN Management Studio — Uninstaller
# Completely removes the product from the server
#===============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

echo ""
echo -e "${RED}${BOLD}"
echo "  ╔═══════════════════════════════════════════════╗"
echo "  ║     VPN Management Studio — Uninstaller       ║"
echo "  ╚═══════════════════════════════════════════════╝"
echo -e "${NC}"

[[ $EUID -eq 0 ]] || { echo -e "${RED}Run as root: sudo bash uninstall.sh${NC}"; exit 1; }

INSTALL_DIR="/opt/vpnmanager"
[[ -d "$INSTALL_DIR" ]] || INSTALL_DIR="/opt/spongebot"
[[ -d "$INSTALL_DIR" ]] || { echo -e "${YELLOW}No installation found.${NC}"; exit 0; }

echo -e "${YELLOW}This will permanently remove VPN Management Studio from this server.${NC}"
echo -e "  Install dir: ${BOLD}$INSTALL_DIR${NC}"
echo ""
read -p "Are you sure? Type YES to confirm: " confirm
[[ "$confirm" == "YES" ]] || { echo "Cancelled."; exit 0; }
echo ""

# Stop services
echo -ne "  Stopping services... "
for prefix in vpnmanager spongebot; do
    for svc in $(systemctl list-units --type=service --no-legend "${prefix}-*" 2>/dev/null | awk '{print $1}'); do
        systemctl stop "$svc" 2>/dev/null || true
        systemctl disable "$svc" 2>/dev/null || true
    done
done
echo -e "${GREEN}OK${NC}"

# Remove systemd units
echo -ne "  Removing systemd units... "
rm -f /etc/systemd/system/vpnmanager-*.service /etc/systemd/system/spongebot-*.service
systemctl daemon-reload 2>/dev/null || true
echo -e "${GREEN}OK${NC}"

# Remove CLI symlink
echo -ne "  Removing CLI... "
rm -f /usr/local/bin/vpnmanager
echo -e "${GREEN}OK${NC}"

# Remove nginx configs
echo -ne "  Removing nginx configs... "
rm -f /etc/nginx/sites-enabled/vpnmanager* /etc/nginx/sites-available/vpnmanager*
rm -f /etc/nginx/sites-enabled/spongebot* /etc/nginx/sites-available/spongebot*
nginx -t &>/dev/null && systemctl reload nginx 2>/dev/null || true
echo -e "${GREEN}OK${NC}"

# Ask about database
echo ""
read -p "  Delete PostgreSQL database too? (y/N): " del_db
if [[ "$del_db" =~ ^[Yy]$ ]]; then
    echo -ne "  Dropping database... "
    sudo -u postgres dropdb spongebot_db 2>/dev/null || true
    sudo -u postgres dropuser spongebot 2>/dev/null || true
    echo -e "${GREEN}OK${NC}"
else
    echo -e "  ${YELLOW}Database kept (spongebot_db)${NC}"
fi

# Ask about WireGuard
echo ""
read -p "  Remove WireGuard interfaces? (y/N): " del_wg
if [[ "$del_wg" =~ ^[Yy]$ ]]; then
    echo -ne "  Removing WireGuard... "
    for iface in $(wg show interfaces 2>/dev/null); do
        wg-quick down "$iface" 2>/dev/null || true
        rm -f "/etc/wireguard/${iface}.conf"
    done
    echo -e "${GREEN}OK${NC}"
else
    echo -e "  ${YELLOW}WireGuard configs kept${NC}"
fi

# Remove install directory
echo -ne "  Removing $INSTALL_DIR... "
rm -rf "$INSTALL_DIR"
echo -e "${GREEN}OK${NC}"

echo ""
echo -e "${GREEN}${BOLD}  Uninstall complete.${NC}"
echo -e "  To reinstall: ${BOLD}curl -fsSL https://example.com/install.sh | sudo bash${NC}"
echo ""
