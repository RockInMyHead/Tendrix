"""
Отправка email через SMTP (по умолчанию Yandex) для верификации при регистрации.
Параметры: SMTP_HOST, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os


def _get_smtp_config():
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.yandex.ru"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "email": os.environ.get("SMTP_EMAIL", "tendrix.io@yandex.ru"),
        "password": os.environ.get("SMTP_PASSWORD", "") or "",
    }


def _smtp_send(cfg: dict, to_email: str, message: str) -> None:
    """465 — SMTP_SSL; 587 — STARTTLS (как у Yandex при «без шифрования»)."""
    context = ssl.create_default_context()
    host = cfg["host"]
    port = cfg["port"]
    if port == 587:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(cfg["email"], cfg["password"])
            server.sendmail(cfg["email"], to_email, message)
    else:
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(cfg["email"], cfg["password"])
            server.sendmail(cfg["email"], to_email, message)


def send_verification_code_email(to_email: str, username: str, code: str) -> bool:
    """Отправить 6-значный код подтверждения email."""
    cfg = _get_smtp_config()
    if not cfg["password"]:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Код подтверждения — Tendrix"
    msg["From"] = cfg["email"]
    msg["To"] = to_email

    text = f"""Здравствуйте, {username}!

Ваш код подтверждения: {code}

Введите его на странице подтверждения в Tendrix.
Код действителен 24 часа.

Если вы не регистрировались на Tendrix, проигнорируйте это письмо.

— Команда Tendrix"""

    html = f"""
<html>
<body style="font-family: sans-serif;">
<p>Здравствуйте, {username}!</p>
<p>Ваш код подтверждения:</p>
<p style="font-size: 28px; font-weight: bold; letter-spacing: 0.3em;">{code}</p>
<p>Введите этот код на сайте tendrix.io после регистрации.</p>
<p style="color:#666;">Если вы не регистрировались на Tendrix, проигнорируйте это письмо.</p>
<p>— Команда Tendrix</p>
</body>
</html>"""

    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        _smtp_send(cfg, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[Email] Ошибка отправки кода: {e}")
        return False


def send_verification_email(to_email: str, username: str, verify_url: str) -> bool:
    """Отправить письмо с ссылкой для верификации email."""
    cfg = _get_smtp_config()
    if not cfg["password"]:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Подтверждение email — Tendrix"
    msg["From"] = cfg["email"]
    msg["To"] = to_email

    text = f"""Здравствуйте, {username}!

Подтвердите ваш email, перейдя по ссылке:
{verify_url}

Если вы не регистрировались на Tendrix, проигнорируйте это письмо.

— Команда Tendrix"""

    html = f"""
<html>
<body style="font-family: sans-serif;">
<p>Здравствуйте, {username}!</p>
<p>Подтвердите ваш email, нажав на кнопку:</p>
<p><a href="{verify_url}" style="background:#2563eb;color:white;padding:10px 20px;text-decoration:none;border-radius:6px;">Подтвердить email</a></p>
<p>Или скопируйте ссылку в браузер:<br><small>{verify_url}</small></p>
<p style="color:#666;">Если вы не регистрировались на Tendrix, проигнорируйте это письмо.</p>
<p>— Команда Tendrix</p>
</body>
</html>"""

    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        _smtp_send(cfg, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[Email] Ошибка отправки: {e}")
        return False
