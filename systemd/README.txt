Tendrix: автозапуск при отключении SSH
=====================================

Вариант 1 — systemd (рекомендуется на VPS с Linux)
---------------------------------------------------
Скопируйте unit-файлы и включите сервисы (один раз, от root):

  cp systemd/tendrix-api.service systemd/tendrix-bot.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now tendrix-api tendrix-bot

Проверка:

  systemctl status tendrix-api tendrix-bot
  journalctl -u tendrix-api -u tendrix-bot -f

Перед первым запуском остановите вручную запущенные python main.py / bot.py,
чтобы не занять порт 8080 дважды.

Вариант 2 — без systemd (nohup)
--------------------------------
Из каталога проекта:

  chmod +x scripts/start-background.sh scripts/stop-background.sh
  ./scripts/start-background.sh

Логи: logs/api.log, logs/bot.log. Остановка: ./scripts/stop-background.sh
