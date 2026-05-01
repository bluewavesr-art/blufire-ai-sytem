#!/usr/bin/env bash
# Idempotent uninstall. Stops services; prompts before removing data and config.
#
# Usage: sudo BLUFIRE_TENANT_ID=acme bash uninstall.sh [--keep-data] [--keep-config] [-y]

set -euo pipefail

INSTALL_PREFIX="${BLUFIRE_HOME:-/opt/blufire}"
ETC_DIR="/etc/blufire"
DATA_BASE="/var/lib/blufire"
LOG_BASE="/var/log/blufire"
SYSTEMD_DIR="/etc/systemd/system"

KEEP_DATA=0
KEEP_CONFIG=0
ASSUME_YES=0
TENANT_ID="${BLUFIRE_TENANT_ID:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep-data) KEEP_DATA=1; shift;;
        --keep-config) KEEP_CONFIG=1; shift;;
        -y|--yes) ASSUME_YES=1; shift;;
        *) echo "unknown flag: $1" >&2; exit 2;;
    esac
done

if [[ "${EUID:-0}" -ne 0 ]]; then
    echo "uninstall.sh must be run as root." >&2
    exit 2
fi
if [[ -z "$TENANT_ID" ]]; then
    echo "BLUFIRE_TENANT_ID is required." >&2
    exit 2
fi

confirm() {
    local prompt="$1"
    if [[ "$ASSUME_YES" -eq 1 ]]; then
        return 0
    fi
    read -rp "$prompt [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

# --- Disable services ---------------------------------------------------------
systemctl disable --now "blufire-leadgen@${TENANT_ID}.timer" 2>/dev/null || true
systemctl disable --now "blufire-leadgen@${TENANT_ID}.service" 2>/dev/null || true
rm -f "$SYSTEMD_DIR/blufire-leadgen@${TENANT_ID}.service"
rm -f "$SYSTEMD_DIR/blufire-leadgen@${TENANT_ID}.timer"
systemctl daemon-reload

# --- Config / env -------------------------------------------------------------
if [[ "$KEEP_CONFIG" -eq 0 ]]; then
    if confirm "Remove $ETC_DIR/$TENANT_ID.yaml and .env?"; then
        rm -f "$ETC_DIR/$TENANT_ID.yaml" "$ETC_DIR/$TENANT_ID.env"
    fi
fi

# --- Data ---------------------------------------------------------------------
# Belt-and-suspenders: ${TENANT_ID:?} aborts the rm if TENANT_ID is somehow
# empty, even though we validated above. Defense in depth on a destructive op.
if [[ "$KEEP_DATA" -eq 0 ]]; then
    if confirm "DELETE $DATA_BASE/$TENANT_ID (suppression list, audit log)?"; then
        rm -rf "${DATA_BASE:?}/${TENANT_ID:?}"
    fi
    if confirm "DELETE $LOG_BASE/$TENANT_ID logs?"; then
        rm -rf "${LOG_BASE:?}/${TENANT_ID:?}"
    fi
fi

# --- venv + source if no other tenants remain --------------------------------
if [[ ! -d "$ETC_DIR" ]] || [[ -z "$(ls -A "$ETC_DIR" 2>/dev/null)" ]]; then
    if confirm "No tenants remain. Remove $INSTALL_PREFIX (venv + source)?"; then
        rm -rf "$INSTALL_PREFIX"
    fi
    if confirm "Remove the 'blufire' system user?"; then
        userdel blufire 2>/dev/null || true
    fi
    rm -f /etc/logrotate.d/blufire
fi

echo "Uninstalled tenant '$TENANT_ID'."
