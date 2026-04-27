#!/bin/bash
# Деплой Tendrix на сервер 95.174.95.179
#
# Если видите "Permission denied (publickey)":
#   ssh-add ~/.ssh/id_ed25519   # или ваш ключ
# или один раз:
#   DEPLOY_SSH_KEY=~/.ssh/id_ed25519 ./deploy.sh
set -e

SERVER="user1@95.174.95.179"
REMOTE_DIR="/home/user1/fz_parser"

RSYNC_SSH="ssh"
SSH_EXTRA=()
if [ -n "${DEPLOY_SSH_KEY:-}" ]; then
  RSYNC_SSH="ssh -i ${DEPLOY_SSH_KEY}"
  SSH_EXTRA=(-i "$DEPLOY_SSH_KEY")
fi

echo "=== 1. Сборка фронтенда ==="
cd "$(dirname "$0")/temp_frontend"
npm run build

echo "=== 2. Копирование в static ==="
cd ..
rm -rf static/assets static/index.html 2>/dev/null || true
cp -r temp_frontend/dist/* static/

echo "=== 3. Синхронизация на сервер ==="
rsync -avz -e "$RSYNC_SSH" --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='sql_app.db' --exclude='node_modules' --exclude='temp_frontend' \
  --exclude='.env' \
  ./ "$SERVER:$REMOTE_DIR/"

echo "=== 4. Настройка и перезапуск на сервере ==="
ssh "${SSH_EXTRA[@]}" "$SERVER" "cd $REMOTE_DIR && \
  if [ ! -f .env ]; then \
    echo 'SMTP_EMAIL=tendrix.io@yandex.ru' > .env; \
    echo 'SMTP_PASSWORD=' >> .env; \
    echo 'SITE_BASE_URL=https://tendrix.io' >> .env; \
  fi && \
  sudo cp tendrix.service /etc/systemd/system/ 2>/dev/null || true && \
  sudo systemctl daemon-reload 2>/dev/null || true && \
  sudo systemctl restart tendrix && \
  sleep 2 && sudo systemctl status tendrix --no-pager"

echo "=== Готово ==="
