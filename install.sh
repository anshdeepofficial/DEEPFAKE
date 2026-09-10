#!/usr/bin/env bash
# DeepGuard permanent Linux installer
set -euo pipefail

SERVICE_NAME="deepguard"
INSTALL_DIR="/opt/deepguard"
VENV_DIR="${INSTALL_DIR}/venv"
LOG_DIR="/var/log/deepguard"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
APP_PORT="${DEEPGUARD_PORT:-8000}"
APP_USER="${DEEPGUARD_USER:-deepguard}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

fail() { echo "[DeepGuard] ERROR: $*" >&2; exit 1; }
info() { echo "[DeepGuard] $*"; }

[[ ${EUID} -eq 0 ]] || fail "Run with sudo: sudo bash install.sh"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v systemctl >/dev/null 2>&1 || fail "systemd is required"
[[ -d "${SOURCE_DIR}/app" ]] || fail "app/ directory not found"
[[ -f "${SOURCE_DIR}/requirements.txt" ]] || fail "requirements.txt not found"

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

info "Installing application in ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}" "${LOG_DIR}"
rm -rf "${INSTALL_DIR}/app"
cp -a "${SOURCE_DIR}/app" "${INSTALL_DIR}/app"
cp "${SOURCE_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"

python3 -m venv "${VENV_DIR}" || fail "python3-venv is required on this Linux distribution"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}" "${LOG_DIR}"

cat > "${SERVICE_FILE}" <<SERVICE
[Unit]
Description=DeepGuard – Multimodal Forensic Analysis and Claim Verification
Documentation=https://github.com/anshdeepofficial/DEEPFAKE
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT} --workers 1
Restart=always
RestartSec=5
StandardOutput=append:${LOG_DIR}/access.log
StandardError=append:${LOG_DIR}/error.log
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=${INSTALL_DIR}
Environment=DEEPGUARD_MAX_UPLOAD_MB=${DEEPGUARD_MAX_UPLOAD_MB:-50}
Environment=DEEPGUARD_RATE_LIMIT_PER_MIN=${DEEPGUARD_RATE_LIMIT_PER_MIN:-30}
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${LOG_DIR}

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 2
if "${VENV_DIR}/bin/python" - <<PY
import urllib.request
urllib.request.urlopen("http://127.0.0.1:${APP_PORT}/api/health", timeout=5).read()
PY
then
  info "DeepGuard is healthy at http://127.0.0.1:${APP_PORT}"
else
  systemctl --no-pager --full status "${SERVICE_NAME}" || true
  fail "Service started but health check failed. See ${LOG_DIR}/error.log"
fi

if [[ "${DEEPGUARD_OPEN_FIREWALL:-0}" == "1" ]] && command -v ufw >/dev/null 2>&1; then
  ufw allow "${APP_PORT}/tcp"
  info "UFW port ${APP_PORT}/tcp opened because DEEPGUARD_OPEN_FIREWALL=1"
else
  info "Firewall was not changed automatically. Open port ${APP_PORT} only if you intentionally expose this server."
fi
