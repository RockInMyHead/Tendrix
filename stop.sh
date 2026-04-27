#!/usr/bin/env bash
# Остановка локального Tendrix: бэкенд (порт 8080) и bot.py из этого каталога.
#
# Если вы ставили systemd-юниты и сервисы называются tendrix / tendrix-bot:
#   sudo systemctl stop tendrix tendrix-bot
#
# Запуск из каталога проекта:
#   ./stop.sh

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Tendrix: остановка (каталог: $ROOT) ==="

if command -v fuser >/dev/null 2>&1; then
  if fuser 8080/tcp >/dev/null 2>&1; then
    echo "Завершаю процесс на порту 8080..."
    fuser -k 8080/tcp 2>/dev/null || true
    sleep 1
  else
    echo "Порт 8080 свободен."
  fi
else
  echo "Нет команды fuser (пакет psmisc); пробую только pkill по имени скрипта."
fi

# Процессы из venv этого проекта (main.py, bot.py)
for script in main.py bot.py; do
  esc="${script//./\\.}"
  pat="${ROOT}/.venv/bin/python.*${esc}"
  if pgrep -f "$pat" >/dev/null 2>&1; then
    echo "Завершаю: $script ..."
    pkill -f "$pat" 2>/dev/null || true
  fi
done

# Запуск без venv: python3 .../main.py
for script in main.py bot.py; do
  esc="${script//./\\.}"
  pat="python.*${ROOT}/${esc}"
  if pgrep -f "$pat" >/dev/null 2>&1; then
    echo "Завершаю (не venv): $script ..."
    pkill -f "$pat" 2>/dev/null || true
  fi
done

# uvicorn из unit-файла: python -m uvicorn main:app
if pgrep -f "uvicorn main:app.*${ROOT}" >/dev/null 2>&1; then
  echo "Завершаю uvicorn main:app ..."
  pkill -f "uvicorn main:app.*${ROOT}" 2>/dev/null || true
fi

sleep 1
echo ""
echo "Проверка:"
if command -v ss >/dev/null 2>&1; then
  ss -tlnp 2>/dev/null | grep -E ':8080\s' && echo "(если выше есть :8080 — процесс ещё держит порт)" || echo "  порт 8080 не слушается"
else
  (command -v fuser >/dev/null && fuser 8080/tcp 2>/dev/null && echo "  порт 8080 ещё занят") || echo "  порт 8080 свободен"
fi
if pgrep -f "${ROOT}.*main\\.py" >/dev/null 2>&1 || pgrep -f "${ROOT}.*bot\\.py" >/dev/null 2>&1; then
  echo "  Внимание: остались процессы Python с путём к проекту. Список:"
  pgrep -af "${ROOT}" 2>/dev/null | head -20 || true
else
  echo "  main.py / bot.py из этого каталога не найдены в списке процессов."
fi
echo "Готово."
