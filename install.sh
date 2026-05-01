#!/usr/bin/env bash
# Blufire idempotent installer.
#
# Usage:
#   sudo BLUFIRE_TENANT_ID=acme bash install.sh \
#       [--config-from PATH] [--env-from PATH] [--ref TAG] \
#       [--non-interactive] [--allow-prerelease] [--no-systemd]
#
# Requires: a checked-out copy of this repo. Installs to:
#   /opt/blufire             — source + venv
#   /etc/blufire             — config + .env (mode 0750, owned by root:blufire)
#   /var/lib/blufire/<tenant> — SQLite DBs (mode 0700, owned by blufire)
#   /var/log/blufire/<tenant> — log files (mode 0750, owned by blufire)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INSTALL_PREFIX="${BLUFIRE_HOME:-/opt/blufire}"
SOURCE_DIR="$INSTALL_PREFIX/source"
VENV_DIR="$INSTALL_PREFIX/venv"
ETC_DIR="/etc/blufire"
DATA_BASE="/var/lib/blufire"
LOG_BASE="/var/log/blufire"
SYSTEMD_DIR="/etc/systemd/system"

CONFIG_FROM=""
ENV_FROM=""
REF=""
NON_INTERACTIVE=0
ALLOW_PRERELEASE=0
INSTALL_SYSTEMD=1

usage() {
    sed -n '2,15p' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config-from) CONFIG_FROM="$2"; shift 2;;
        --env-from)    ENV_FROM="$2"; shift 2;;
        --ref)         REF="$2"; shift 2;;
        --non-interactive) NON_INTERACTIVE=1; shift;;
        --allow-prerelease) ALLOW_PRERELEASE=1; shift;;
        --no-systemd)  INSTALL_SYSTEMD=0; shift;;
        -h|--help)     usage; exit 0;;
        *) echo "unknown flag: $1" >&2; usage; exit 2;;
    esac
done

if [[ "${EUID:-0}" -ne 0 ]]; then
    echo "install.sh must be run as root (use sudo)." >&2
    exit 2
fi

TENANT_ID="${BLUFIRE_TENANT_ID:-}"
if [[ -z "$TENANT_ID" ]]; then
    if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
        echo "BLUFIRE_TENANT_ID is required (set env var or run interactively)." >&2
        exit 2
    fi
    read -rp "Tenant ID (slug, e.g. acme-agency): " TENANT_ID
fi
if [[ -z "$TENANT_ID" ]]; then
    echo "Tenant ID cannot be empty." >&2
    exit 2
fi

DATA_DIR="$DATA_BASE/$TENANT_ID"
LOG_DIR="$LOG_BASE/$TENANT_ID"
TENANT_CONFIG="$ETC_DIR/$TENANT_ID.yaml"
TENANT_ENV="$ETC_DIR/$TENANT_ID.env"

# --- Validate repo ref --------------------------------------------------------
if [[ -n "$REF" ]]; then
    if ! [[ "$REF" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] && [[ "$ALLOW_PRERELEASE" -ne 1 ]]; then
        echo "Refusing to install from non-tag ref '$REF'. Pass --allow-prerelease to override." >&2
        exit 2
    fi
fi

# --- Dedicated user -----------------------------------------------------------
if ! id -u blufire >/dev/null 2>&1; then
    useradd --system --home "$DATA_BASE" --shell /usr/sbin/nologin blufire
fi

# --- Directories --------------------------------------------------------------
install -d -o root -g blufire -m 0750 "$ETC_DIR"
install -d -o blufire -g blufire -m 0700 "$DATA_DIR"
install -d -o blufire -g blufire -m 0750 "$LOG_DIR"
install -d -o root -g root -m 0755 "$INSTALL_PREFIX"

# --- Sync source --------------------------------------------------------------
if [[ -d "$SOURCE_DIR/.git" ]]; then
    git -C "$SOURCE_DIR" fetch --tags --prune
    if [[ -n "$REF" ]]; then
        git -C "$SOURCE_DIR" checkout --quiet "$REF"
    fi
    git -C "$SOURCE_DIR" reset --hard HEAD
else
    install -d -o root -g root -m 0755 "$SOURCE_DIR"
    cp -a "$REPO_ROOT/." "$SOURCE_DIR/"
    if [[ -n "$REF" && -d "$SOURCE_DIR/.git" ]]; then
        git -C "$SOURCE_DIR" checkout --quiet "$REF"
    fi
fi
chown -R root:root "$SOURCE_DIR"

# --- Venv ---------------------------------------------------------------------
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip wheel
"$VENV_DIR/bin/pip" install --quiet -e "$SOURCE_DIR[prod]"

# --- Config + .env ------------------------------------------------------------
if [[ -n "$CONFIG_FROM" ]]; then
    install -m 0640 -o root -g blufire "$CONFIG_FROM" "$TENANT_CONFIG"
elif [[ ! -f "$TENANT_CONFIG" ]]; then
    install -m 0640 -o root -g blufire "$SOURCE_DIR/config.example.yaml" "$TENANT_CONFIG"
    echo "Wrote default config at $TENANT_CONFIG. Review before starting services."
fi

if [[ -n "$ENV_FROM" ]]; then
    install -m 0640 -o root -g blufire "$ENV_FROM" "$TENANT_ENV"
elif [[ ! -f "$TENANT_ENV" ]]; then
    install -m 0640 -o root -g blufire "$SOURCE_DIR/.env.example" "$TENANT_ENV"
    echo "Wrote default .env at $TENANT_ENV. Fill in your secrets before starting."
fi

# --- systemd ------------------------------------------------------------------
if [[ "$INSTALL_SYSTEMD" -eq 1 ]]; then
    UNIT_SUFFIX="$TENANT_ID"
    SERVICE_PATH="$SYSTEMD_DIR/blufire-leadgen@${UNIT_SUFFIX}.service"
    TIMER_PATH="$SYSTEMD_DIR/blufire-leadgen@${UNIT_SUFFIX}.timer"

    sed \
        -e "s|@VENV@|$VENV_DIR|g" \
        -e "s|@SOURCE@|$SOURCE_DIR|g" \
        -e "s|@TENANT@|$TENANT_ID|g" \
        -e "s|@DATA@|$DATA_BASE|g" \
        -e "s|@LOG@|$LOG_BASE|g" \
        "$SOURCE_DIR/packaging/systemd/blufire-leadgen.service.in" \
        > "$SERVICE_PATH"
    install -m 0644 "$SOURCE_DIR/packaging/systemd/blufire-leadgen.timer" "$TIMER_PATH"
    install -m 0644 "$SOURCE_DIR/packaging/logrotate/blufire" /etc/logrotate.d/blufire

    systemctl daemon-reload
    systemctl enable --now "blufire-leadgen@${UNIT_SUFFIX}.timer"
    echo "Enabled blufire-leadgen@${UNIT_SUFFIX}.timer"
fi

# --- Sanity check -------------------------------------------------------------
"$VENV_DIR/bin/blufire" --version
echo
echo "Blufire installed for tenant '$TENANT_ID'."
echo "  Config: $TENANT_CONFIG"
echo "  Env:    $TENANT_ENV"
echo "  Data:   $DATA_DIR"
echo "  Logs:   $LOG_DIR"
echo
echo "Next: edit $TENANT_ENV with your secrets, then run:"
echo "  sudo -u blufire BLUFIRE_CONFIG=$TENANT_CONFIG $VENV_DIR/bin/blufire doctor"
