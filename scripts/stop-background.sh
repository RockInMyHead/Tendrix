#!/usr/bin/env bash
# Остановка процессов, запущенных через start-background.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

for name in api bot; do
  pidfile="logs/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "${name}: pid-файл не найден, пропуск"
    continue
  fi
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" && echo "${name}: остановлен (PID $pid)" || echo "${name}: ошибка kill $pid"
  else
    echo "${name}: процесс $pid не найден, удаляю pid-файл"
  fi
  rm -f "$pidfile"
done
