"""
Настройка HTTP(S)-прокси для requests-парсеров (zakupki.gov.ru и др.).

Если сервер не может достучаться до ЕИС напрямую, задайте в .env или окружении:
  PARSER_HTTP_PROXY=http://user:pass@host:port
  или строку из панели прокси: host:port:user:pass

Если задан только OPENAI_HTTP_PROXY и не задан HTTPS_PROXY — используем его же для парсеров.
"""
from __future__ import annotations

import os
from urllib.parse import quote


def _proxy_line_to_url(raw: str) -> str:
    """host:port:user:password → http://user:pass@host:port (password может содержать ':')."""
    raw = raw.strip()
    if not raw or "://" in raw:
        return raw
    parts = raw.split(":", 3)
    if len(parts) != 4:
        return raw
    host, port, user, password = parts
    if not port.isdigit():
        return raw
    u = quote(user, safe="")
    pw = quote(password, safe="")
    return f"http://{u}:{pw}@{host}:{port}"


def apply_parser_http_proxy_from_env() -> None:
    p = os.environ.get("PARSER_HTTP_PROXY", "").strip()
    if p:
        p = _proxy_line_to_url(p)
        os.environ["PARSER_HTTP_PROXY"] = p
        os.environ["HTTPS_PROXY"] = p
        os.environ["HTTP_PROXY"] = p
        return
    if os.environ.get("HTTPS_PROXY", "").strip() or os.environ.get("HTTP_PROXY", "").strip():
        return
    p = os.environ.get("OPENAI_HTTP_PROXY", "").strip()
    if p:
        os.environ["HTTPS_PROXY"] = p
        os.environ["HTTP_PROXY"] = p


apply_parser_http_proxy_from_env()
