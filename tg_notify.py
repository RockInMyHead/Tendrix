"""
Отправка в Telegram только тендеров, опубликованных в текущий момент
(активные, срок подачи в будущем). Без эмодзи, аккуратный формат со ссылкой.
"""
import threading
import time
import logging
from queue import Queue, Empty
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

import os

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = None
TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""
)
SEND_DELAY = 1.2  # ~1 msg/sec per chat, чтобы не превысить лимит Telegram

_tender_queue = Queue()
_worker_started = [False]


def _parse_deadline(date_str):
    """Парсит DD.MM.YYYY HH:MM или DD.MM.YYYY. Возвращает datetime или None."""
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    parts = s.split()
    date_part = parts[0] if parts else ""
    time_part = parts[1] if len(parts) > 1 else "00:00"
    d_parts = date_part.split(".")
    if len(d_parts) < 3:
        return None
    try:
        day, month, year = int(d_parts[0]), int(d_parts[1]), int(d_parts[2])
        h, m = 0, 0
        if ":" in time_part:
            tm = time_part.split(":")
            h, m = int(tm[0]) if tm[0].isdigit() else 0, int(tm[1]) if len(tm) > 1 and tm[1].isdigit() else 0
        return datetime(year, month, day, h, m)
    except (ValueError, IndexError):
        return None


def _is_deadline_in_future(date_str):
    """Срок подачи в будущем — тендер ещё открыт."""
    dt = _parse_deadline(date_str)
    return dt is not None and dt > datetime.now()


def _is_active_stage(stage):
    """
    Активная стадия — приём заявок или рассмотрение.
    Не отправляем: завершённые, отменённые, заключение контракта, размещён в реестре, исполнение.
    """
    if not stage:
        return True  # без стадии считаем активным
    s = (stage or "").lower()
    exclude = (
        "завершен", "отменен", "отказ", "аннулир",
        "заключение контракта",           # контракт уже заключён
        "размещен контракт в реестре",    # контракт в реестре — аукцион завершён
        "размещен в реестре контрактов",
        "исполнение",                     # исполнение контракта — закупка завершена
    )
    return not any(x in s for x in exclude)


def _format_price(price, currency):
    if price is None:
        return "—"
    try:
        p = float(price)
        cur = currency or "₽"
        if p >= 1_000_000_000:
            v = p / 1_000_000_000
            return f"{v:.1f} млрд {cur}".replace(".0 ", " ")
        if p >= 1_000_000:
            v = p / 1_000_000
            return f"{v:.1f} млн {cur}".replace(".0 ", " ")
        if p >= 1_000:
            v = p / 1_000
            return f"{v:.1f} тыс {cur}".replace(".0 ", " ")
        return f"{p:.0f} {cur}"
    except (TypeError, ValueError):
        return str(price) if price else "—"


def _format_tender_message(number, subject, price, currency, customer, region, update_date, link, procurement_type):
    """Формирует текст сообщения без эмодзи."""
    price_str = _format_price(price, currency)
    subject_short = (subject or "—")[:200]
    if subject and len(subject) > 200:
        subject_short += "..."
    customer_short = (customer or "—")[:80]
    region_str = region or "—"
    date_str = update_date or "—"
    proc_str = procurement_type or "—"

    lines = [
        "Новый тендер",
        "",
        f"Название: {subject_short}",
        f"Заказчик: {customer_short}",
        f"Цена: {price_str}",
        f"Регион: {region_str}",
        f"Срок: {date_str}",
        f"Тип: {proc_str}",
        "",
    ]
    text = "\n".join(lines)
    if link:
        text += f"\n{link}"
    return text


def _send_to_telegram(chat_id: int, text: str) -> bool:
    if not requests or not TELEGRAM_API:
        return False
    try:
        r = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if r.status_code == 200:
            return True
        if r.status_code == 429:
            try:
                data = r.json()
                retry_after = data.get("parameters", {}).get("retry_after", 60)
                logger.warning(f"Telegram rate limit 429, sleeping {retry_after}s")
                time.sleep(retry_after)
                return _send_to_telegram(chat_id, text)  # retry
            except Exception:
                pass
        logger.warning(f"Telegram send failed: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")
        return False


def _get_telegram_users():
    """Возвращает список chat_id пользователей, привязавших Telegram."""
    try:
        from database import SessionLocal, User
        with SessionLocal() as db:
            users = db.query(User.telegram_id).filter(User.telegram_id.isnot(None)).all()
            return [u[0] for u in users if u[0]]
    except Exception as e:
        logger.warning(f"Failed to get telegram users: {e}")
        return []


def _worker():
    while True:
        try:
            item = _tender_queue.get(timeout=5)
            if item is None:
                break
            chat_ids = list(item.get("chat_ids") or [])
            if not chat_ids and TELEGRAM_CHANNEL_ID:
                chat_ids = [TELEGRAM_CHANNEL_ID]
            if not chat_ids:
                chat_ids = _get_telegram_users()
            text = item.get("text", "")
            if not text or not chat_ids:
                continue
            for cid in chat_ids:
                _send_to_telegram(cid, text)
                time.sleep(SEND_DELAY)
        except Empty:
            continue
        except Exception as e:
            logger.warning(f"TG worker error: {e}")


def _ensure_worker():
    if not _worker_started[0]:
        _worker_started[0] = True
        t = threading.Thread(target=_worker, daemon=True, name="tg-notify")
        t.start()


def queue_new_tender(number, subject, price, currency, customer, region, update_date, link, procurement_type=None, stage=None):
    """Поставить тендер в очередь на отправку в Telegram. Только если актуален (срок в будущем, стадия активная)."""
    if not link:
        return
    if not _is_deadline_in_future(update_date):
        return  # аукцион уже закончился — не отправляем
    if not _is_active_stage(stage):
        return  # заключение контракта / размещён в реестре / исполнение — не отправляем
    text = _format_tender_message(
        number, subject, price, currency, customer, region, update_date, link, procurement_type
    )
    _ensure_worker()
    _tender_queue.put({"text": text, "chat_ids": None})


def sync_currently_published_tenders(limit=50):
    """
    Отправляет в Telegram только тендеры СЕГОДНЯШНЕГО дня (добавленные сегодня по МСК).
    """
    try:
        from database import SessionLocal, Tender
        from datetime import timedelta

        # Начало сегодняшнего дня по Москве (00:00 МСК в UTC)
        msk_now = datetime.utcnow() + timedelta(hours=3)
        today_start_utc = datetime(msk_now.year, msk_now.month, msk_now.day) - timedelta(hours=3)

        with SessionLocal() as db:
            # Только тендеры, добавленные сегодня
            tenders = db.query(Tender).filter(
                Tender.link.isnot(None),
                Tender.tg_notified_at.is_(None),
                Tender.published_at >= today_start_utc,
            ).order_by(Tender.published_at.desc().nullslast()).limit(limit * 3).all()

            sent = 0
            for t in tenders:
                if not t.link:
                    continue
                if not _is_active_stage(t.stage):
                    continue
                # Сначала — только со сроком в будущем
                if not _is_deadline_in_future(t.update_date):
                    continue
                queue_new_tender(
                    t.number, t.subject, t.price, t.currency,
                    t.customer, t.region, t.update_date, t.link,
                    t.procurement_type, t.stage,
                )
                t.tg_notified_at = datetime.utcnow()
                sent += 1
                if sent >= limit:
                    break

            # 2. Fallback — те же критерии (сегодня)
            if sent == 0:
                recent = db.query(Tender).filter(
                    Tender.link.isnot(None),
                    Tender.tg_notified_at.is_(None),
                    Tender.published_at >= today_start_utc,
                ).order_by(Tender.published_at.desc()).limit(limit).all()
                for t in recent:
                    if not _is_active_stage(t.stage):
                        continue
                    if not _is_deadline_in_future(t.update_date):
                        t.tg_notified_at = datetime.utcnow()  # помечаем, чтобы не брать снова
                        continue
                    queue_new_tender(
                        t.number, t.subject, t.price, t.currency,
                        t.customer, t.region, t.update_date, t.link,
                        t.procurement_type, t.stage,
                    )
                    t.tg_notified_at = datetime.utcnow()
                    sent += 1

            db.commit()
            if sent:
                logger.info(f"TG: отправлено {sent} тендеров")
    except Exception as e:
        logger.warning(f"TG sync error: {e}")
