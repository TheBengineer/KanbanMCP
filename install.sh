#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────
# Kanban — systemd service installer
# Installs to /opt/kanban and registers a systemd service.
# ────────────────────────────────────────────────────────────

KANBAN_USER="${KANBAN_USER:-kanban}"
KANBAN_GROUP="${KANBAN_GROUP:-kanban}"
KANBAN_DIR="/opt/kanban"
SERVICE_NAME="kanban"
SERVICE_FILE="${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root (sudo)."
    exit 1
fi

echo "==> Creating system user '${KANBAN_USER}' (if missing)..."
if ! id "${KANBAN_USER}" &>/dev/null; then
    useradd --system --user-group --home-dir "${KANBAN_DIR}" --shell /usr/sbin/nologin "${KANBAN_USER}"
fi

echo "==> Copying project to ${KANBAN_DIR}..."
mkdir -p "${KANBAN_DIR}"
cp -r "$(dirname "$0")/kanban" "${KANBAN_DIR}/kanban"
cp "$(dirname "$0")/kanban.py" "${KANBAN_DIR}/"
cp "$(dirname "$0")/pyproject.toml" "${KANBAN_DIR}/" 2>/dev/null || true
cp -r "$(dirname "$0")/templates" "${KANBAN_DIR}/" 2>/dev/null || true
cp -r "$(dirname "$0")/static" "${KANBAN_DIR}/" 2>/dev/null || true
chown -R "${KANBAN_USER}:${KANBAN_GROUP}" "${KANBAN_DIR}"

echo "==> Creating Python virtual environment..."
sudo -u "${KANBAN_USER}" python3 -m venv "${KANBAN_DIR}/venv"
sudo -u "${KANBAN_USER}" "${KANBAN_DIR}/venv/bin/pip" install --no-cache-dir \
    fastapi>=0.110.0 \
    uvicorn[standard]>=0.27.0 \
    pydantic>=2.0.0 \
    jinja2 \
    python-multipart

echo "==> Installing systemd service..."
cp "$(dirname "$0")/${SERVICE_FILE}" "/etc/systemd/system/${SERVICE_FILE}"
chmod 644 "/etc/systemd/system/${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"

echo "==> Done."
systemctl status "${SERVICE_NAME}" --no-pager
