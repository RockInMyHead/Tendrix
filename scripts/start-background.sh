#!/usr/bin/env bash
# Запуск API и бота в фоне (переживает выход из SSH).
# Требуется: рабочий .venv и .env в корне проекта.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
mkdir -p logs
PY="${DIR}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  echo "Не найден интерпретатор: $PY (создайте venv и установите зависимости)" >&2
  exit 1
fi

start_one() {
  local name="$1" script="$2"
  local pidfile="logs/${name}.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "${name}: уже запущен (PID $(cat "$pidfile"))"
    return
  fi
  nohup "$PY" -u "$script" >> "logs/${name}.log" 2>&1 &
  echo $! > "$pidfile"
  echo "${name}: запущен PID $(cat "$pidfile"), лог: logs/${name}.log"
}

start_one api main.py
start_one bot bot.py
