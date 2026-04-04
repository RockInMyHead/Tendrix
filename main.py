try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Query, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional
from datetime import timedelta, datetime
from pydantic import BaseModel, Field
import uvicorn
import os
import httpx
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from openai import AsyncOpenAI

# DB & Auth Imports
from database import SessionLocal, engine, User, PromoCode, Tender, init_db
from auth import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

import asyncio
import random
import string
import os
from sqlalchemy import text, or_, and_, func, case, literal_column
from email_sender import send_verification_code_email

# Manual migration for existing DB
def migrate_db():
    conn = engine.connect()
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN telegram_id INTEGER"))
        print("Migrated: Added telegram_id")
    except Exception as e:
        pass # Expected if exists
        
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN telegram_connect_code VARCHAR"))
        print("Migrated: Added telegram_connect_code")
    except Exception as e:
        pass

    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_pro BOOLEAN DEFAULT 0"))
        print("Migrated: Added is_pro")
    except Exception as e:
        pass

    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN company_description TEXT"))
        print("Migrated: Added company_description")
    except Exception as e:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN company_description_last_saved VARCHAR"))
        print("Migrated: Added company_description_last_saved")
    except Exception as e:
        pass
    try:
        conn.execute(text("ALTER TABLE tenders ADD COLUMN tg_notified_at VARCHAR"))
        print("Migrated: Added tg_notified_at")
    except Exception as e:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR"))
        print("Migrated: Added email")
    except Exception as e:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
        print("Migrated: Added email_verified")
    except Exception as e:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN email_verification_token VARCHAR"))
        print("Migrated: Added email_verification_token")
    except Exception as e:
        pass
    # Индексы для ускорения фильтрации
    for idx_name, col in [("ix_tenders_region", "region"), ("ix_tenders_procurement_type", "procurement_type"),
                          ("ix_tenders_stage", "stage"), ("ix_tenders_price", "price")]:
        try:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON tenders ({col})"))
            print(f"Migrated: Index {idx_name}")
        except Exception as e:
            pass
    conn.commit()
    conn.close()

# Initialize DB models
print("Initializing DB...")
init_db()
print("DB Initialized")
migrate_db() # Run migration

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Pydantic Models ---
class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6)
    email: str = Field(..., min_length=3)

class Token(BaseModel):
    access_token: str
    token_type: str
    email_sent: Optional[bool] = None


class VerifyEmailCodeBody(BaseModel):
    code: str = Field(..., min_length=1, max_length=6)

class DescriptionUpdate(BaseModel):
    description: str

class PromoCreate(BaseModel):
    code: str
    description: Optional[str] = None

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

def create_default_admin():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            hashed_pw = get_password_hash("admin123")
            admin = User(username="admin", hashed_password=hashed_pw, is_admin=True)
            db.add(admin)
            db.commit()
            print("Default admin created: admin / admin123")
    finally:
        db.close()

# Create default admin on module load
create_default_admin()

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user
# Import the parser
from zakupki_parser import ZakupkiContractParser, ContractRecord
from sberbank_ast_parser import SberbankAstParser, SberTender
from roseltorg_parser import RoseltorgEisParser
from rts_tender_parser import RtsTenderEisParser
from etpgpb_parser import EtpGpbEisParser
from etp_ets_parser import EtpEtsEisParser
from lot_online_parser import LotOnlineEisParser
from zakazrf_parser import ZakazRfEisParser
from tektorg_parser import TekTorgEisParser
from external_parsers import sync_external_sources
from tg_notify import sync_currently_published_tenders, queue_new_tender
from tender_collector import TenderCollector

import hashlib
import json
import logging
import time

app = FastAPI(title="Zakupki Parser API")

# Кэш live-sync: при смене только фильтров (law44, law223 и т.д.) не дергать внешние API
_sync_cache: dict = {}
_SYNC_CACHE_TTL_SEC = 45

def _sync_cache_key(search: Optional[str], price_from: Optional[float], price_to: Optional[float]) -> str:
    return f"{search or ''}|{price_from}|{price_to}"

def _should_skip_live_sync(search: Optional[str], price_from: Optional[float], price_to: Optional[float]) -> bool:
    key = _sync_cache_key(search, price_from, price_to)
    now = time.time()
    if key in _sync_cache and (now - _sync_cache[key]) < _SYNC_CACHE_TTL_SEC:
        return True
    return False

def _mark_sync_done(search: Optional[str], price_from: Optional[float], price_to: Optional[float]):
    _sync_cache[_sync_cache_key(search, price_from, price_to)] = time.time()

# Initialize the parser
parser = ZakupkiContractParser()
sber_parser = SberbankAstParser()
roseltorg_parser = RoseltorgEisParser()
rts_parser = RtsTenderEisParser()
etpgpb_parser = EtpGpbEisParser()
etp_ets_parser = EtpEtsEisParser()
lot_online_parser = LotOnlineEisParser()
zakazrf_parser = ZakazRfEisParser()
tektorg_parser = TekTorgEisParser()

# OpenAI: ключ и опционально HTTP-прокси (например http://user:pass@host:port)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
PROXY_URL = os.environ.get("OPENAI_HTTP_PROXY", "").strip() or None
http_client = httpx.AsyncClient(proxy=PROXY_URL) if PROXY_URL else httpx.AsyncClient()
client = AsyncOpenAI(api_key=OPENAI_API_KEY, http_client=http_client)

# Background Sync Thread
import threading
import time

# ---------------------------------------------------------------------------
#  Универсальная функция upsert тендера в БД
# ---------------------------------------------------------------------------
def _upsert_tender(db, number, subject, price, currency, update_date,
                   stage, customer, region, procurement_type, link, supplier=None):
    """Вставить или обновить тендер. Возвращает True если новый."""
    if not number:
        return False
    existing = db.query(Tender).filter(Tender.number == number).first()
    if not existing:
        db.add(Tender(
            number=number, subject=subject, price=price,
            currency=currency, update_date=update_date, stage=stage,
            customer=customer, supplier=supplier, region=region,
            procurement_type=procurement_type, link=link,
        ))
        return True
    # Update existing
    existing.subject = subject or existing.subject
    existing.price = price or existing.price
    existing.currency = currency or existing.currency
    existing.update_date = update_date or existing.update_date
    existing.stage = stage or existing.stage
    existing.customer = customer or existing.customer
    existing.region = region or existing.region
    existing.procurement_type = procurement_type or existing.procurement_type
    existing.link = link or existing.link
    if supplier:
        existing.supplier = supplier
    return False

# ---------------------------------------------------------------------------
#  Поток 1: ЕИС (zakupki.gov.ru) — контракты, HTML-скрапинг
# ---------------------------------------------------------------------------
def _sync_eis():
    """Непрерывный сбор тендеров из ЕИС (zakupki.gov.ru)."""
    keywords = ["", "строительство", "it", "поставка", "охрана", "медицина",
                "услуги", "ремонт", "оборудование", "транспорт", "продукты",
                "лекарства", "уборка", "логистика", "консалтинг"]
    
    while True:
        for kw in keywords:
            for page in range(1, 51):
                try:
                    result = parser.search(
                        search_string=kw if kw else None,
                        records_per_page=200, page=page,
                        law_44=True, law_223=True,
                    )
                    records = result.get("records", [])
                    if not records:
                        break

                    with SessionLocal() as db:
                        new = 0
                        for rec in records:
                            if _upsert_tender(
                                db, rec.number, rec.subject, rec.price, rec.currency,
                                rec.update_date, rec.stage, rec.customer, rec.region,
                                rec.procurement_type, rec.link, rec.supplier,
                            ):
                                new += 1
                        db.commit()
                    print(f"[ЕИС] '{kw}' p{page}: +{new} new")

                    time.sleep(15)
                except Exception as e:
                    print(f"[ЕИС] error '{kw}' p{page}: {e}")
                    time.sleep(60)

        print("[ЕИС] Цикл завершён, пауза 10 мин")
        time.sleep(600)

# ---------------------------------------------------------------------------
#  Поток 2: Сбербанк-АСТ (sberbank-ast.ru) — ElasticSearch API
# ---------------------------------------------------------------------------
def _sync_sberbank():
    """Непрерывный сбор тендеров с Сбербанк-АСТ."""
    keywords = ["", "строительство", "поставка", "услуги", "ремонт",
                "оборудование", "медицина", "it", "охрана", "транспорт",
                "продукты", "лекарства", "уборка", "логистика", "энергетика"]
    
    while True:
        for kw in keywords:
            for page_num in range(5):  # 5 страниц × 100 = до 500 тендеров/ключевое слово
                try:
                    results = sber_parser.search(
                        kw if kw else "закупка",
                        max_items=100, page=page_num,
                    )
                    if not results:
                        break

                    with SessionLocal() as db:
                        new = 0
                        for t in results:
                            tender_date = t.deadline or t.published_at
                            if _upsert_tender(
                                db, t.reg_number, t.title, t.price, t.currency or "₽",
                                tender_date,
                                t.stage or "Подача заявок",
                                t.customer or "Не указан", t.region,
                                "44-ФЗ (Сбербанк-АСТ)",
                                t.eis_link or t.link,
                            ):
                                new += 1
                        db.commit()
                        print(f"[Сбербанк-АСТ] '{kw}' p{page_num}: +{new} new ({len(results)} total)")

                    time.sleep(5)
                except Exception as e:
                    print(f"[Сбербанк-АСТ] error '{kw}' p{page_num}: {e}")
                    time.sleep(30)

            time.sleep(3)  # Между ключевыми словами

        print("[Сбербанк-АСТ] Цикл завершён, пауза 5 мин")
        time.sleep(300)

# ---------------------------------------------------------------------------
#  Поток 3: Внешние парсеры (sitemap/HTML — tektorg, otc, b2b-center и т.д.)
# ---------------------------------------------------------------------------
def _sync_external():
    """Непрерывный сбор тендеров из внешних источников."""
    while True:
        print("[External] Запуск синхронизации внешних источников...")
        try:
            with SessionLocal() as db:
                def _upsert_ext(t: dict):
                    if not t or not t.get("number"):
                        return
                    if _upsert_tender(
                        db, t["number"], t.get("subject"), t.get("price"),
                        t.get("currency"), t.get("update_date"), t.get("stage"),
                        t.get("customer"), t.get("region"),
                        t.get("procurement_type"), t.get("link"),
                        t.get("supplier"),
                    ):
                        pass
                    db.commit()

                sync_external_sources(
                    sources_path="external_sources.json",
                    upsert_fn=_upsert_ext,
                    max_urls_per_source=2000,
                )
            print("[External] Цикл завершён, пауза 30 мин")
        except Exception as e:
            print(f"[External] error: {e}")

        time.sleep(1800)

# ---------------------------------------------------------------------------
#  Поток 3b: TenderCollector — универсальный сбор с 30 площадок (HTML/RSS)
# ---------------------------------------------------------------------------
def _parse_collector_price(price_str: str) -> Optional[float]:
    """Извлечь число из строки цены ('123 руб.', '1.5 млн руб.' и т.д.)"""
    if not price_str:
        return None
    import re
    s = re.sub(r'[^\d\s.,]', '', price_str).replace(' ', '').replace(',', '.')
    match = re.search(r'(\d+\.?\d*)', s)
    if match:
        val = float(match.group(1))
        if 'млн' in price_str.lower() or 'млн' in price_str:
            val *= 1_000_000
        elif 'млрд' in price_str.lower() or 'млрд' in price_str:
            val *= 1_000_000_000
        return val if 0.01 <= val <= 100e9 else None
    return None

def _sync_collector():
    """Сбор тендеров с множества площадок через TenderCollector (tenders_config.json)."""
    import os
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tenders_config.json')

    while True:
        if not os.path.exists(config_path):
            print("[Collector] tenders_config.json не найден, повтор через 1 ч")
            time.sleep(3600)
            continue

        collector = TenderCollector()
        collector.load_sources_from_config(config_path)
        try:
            tenders = collector.collect_all_tenders()
            new_count = 0
            with SessionLocal() as db:
                for idx, t in enumerate(tenders):
                    number = t.get('number', '').strip()
                    if not number:
                        title_val = t.get('title', '') or ''
                        link_val = t.get('link', '') or ''
                        # Включаем source и idx для уникальности при пустых title+link
                        number = 'col_' + hashlib.md5(
                            (f"{t.get('source', '')}_{title_val}_{link_val}_{idx}").encode()
                        ).hexdigest()[:16]
                    price = _parse_collector_price(t.get('price', ''))
                    proc_type = f"Источник: {t.get('source', '')}"
                    if _upsert_tender(
                        db, number, t.get('title'), price, '₽',
                        t.get('deadline') or t.get('published', ''),
                        'Подача заявок',
                        t.get('customer') or 'Не указан',
                        None, proc_type, t.get('link', '') or '',
                    ):
                        new_count += 1
                db.commit()
            print(f"[Collector] Добавлено {new_count} новых из {len(tenders)}")
        except Exception as e:
            print(f"[Collector] error: {e}")
            import traceback
            traceback.print_exc()
        print("[Collector] Пауза 2 часа")
        time.sleep(7200)

# ---------------------------------------------------------------------------
#  Поток 4: Свежие тендеры — только первая страница за сегодня (фильтр по дате)
# ---------------------------------------------------------------------------
def _sync_fresh_today():
    """
    Каждую минуту: берём 1-ю страницу (сортировка по дате, новое сверху).
    Фильтр по дате = сегодня. Если первый в списке уже в БД — обновлений нет.
    Иначе — добавляем новые.
    """
    from datetime import datetime as _dt, timedelta as _td
    while True:
        msk = _dt.utcnow() + _td(hours=3)
        today = msk.strftime("%d.%m.%Y")
        try:
            # ЕИС — только 1-я страница (новое сверху)
            try:
                result = parser.search(
                    records_per_page=200, page=1,
                    law_44=True, law_223=True,
                    publish_date_from=today,
                    publish_date_to=today,
                )
                records = result.get("records", [])
                if records:
                    with SessionLocal() as db:
                        new = 0
                        for rec in records:
                            if _upsert_tender(
                                db, rec.number, rec.subject, rec.price, rec.currency,
                                rec.update_date, rec.stage, rec.customer, rec.region,
                                rec.procurement_type, rec.link, rec.supplier,
                            ):
                                new += 1
                                queue_new_tender(
                                    rec.number, rec.subject, rec.price, rec.currency,
                                    rec.customer, rec.region, rec.update_date, rec.link,
                                    rec.procurement_type, rec.stage,
                                )
                        db.commit()
                        if new:
                            print(f"[Fresh ЕИС] +{new} new -> TG")
            except Exception as e:
                print(f"[Fresh ЕИС] error: {e}")

            # Сбербанк-АСТ — только 1-я страница
            try:
                results = sber_parser.search(
                    "закупка",
                    max_items=100, page=0,
                    date_from=today,
                    date_to=today,
                )
                if results:
                    with SessionLocal() as db:
                        new = 0
                        for t in results:
                            tender_date = t.deadline or t.published_at
                            if _upsert_tender(
                                db, t.reg_number, t.title, t.price, t.currency or "₽",
                                tender_date,
                                t.stage or "Подача заявок",
                                t.customer or "Не указан", t.region,
                                "44-ФЗ (Сбербанк-АСТ)",
                                t.eis_link or t.link,
                            ):
                                new += 1
                                queue_new_tender(
                                    t.reg_number, t.title, t.price, t.currency or "₽",
                                    t.customer or "Не указан", t.region, tender_date,
                                    t.eis_link or t.link, "44-ФЗ (Сбербанк-АСТ)", t.stage,
                                )
                        db.commit()
                        if new:
                            print(f"[Fresh Сбербанк] +{new} new -> TG")
            except Exception as e:
                print(f"[Fresh Сбербанк] error: {e}")
        except Exception as e:
            print(f"[Fresh] error: {e}")
        time.sleep(1)  # каждую секунду

# ---------------------------------------------------------------------------
#  Поток 5: TG — рассылка только активных тендеров (срок в будущем)
# ---------------------------------------------------------------------------
def _sync_tg_current():
    """Периодически отправляет в Telegram только тендеры, опубликованные сейчас."""
    while True:
        try:
            sync_currently_published_tenders(limit=10)
        except Exception as e:
            print(f"[TG] error: {e}")
        time.sleep(1800)  # каждые 30 мин

# ---------------------------------------------------------------------------
#  Запуск всех потоков синхронизации
# ---------------------------------------------------------------------------
print("=== Starting 24/7 sync threads ===")
threading.Thread(target=_sync_fresh_today, daemon=True, name="sync-fresh").start()
threading.Thread(target=_sync_eis, daemon=True, name="sync-eis").start()
threading.Thread(target=_sync_sberbank, daemon=True, name="sync-sberbank").start()
threading.Thread(target=_sync_external, daemon=True, name="sync-external").start()
threading.Thread(target=_sync_collector, daemon=True, name="sync-collector").start()
threading.Thread(target=_sync_tg_current, daemon=True, name="sync-tg").start()
print("=== 6 sync threads: Fresh, ЕИС, Сбербанк-АСТ, External, Collector (30 площадок), TG ===")

async def get_ai_keywords(description: str) -> str:
    """Ask GPT-4o to extract search keywords from the company description."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Вы — ассистент по госзакупкам. Из описания компании выделите 3-5 КОНКРЕТНЫХ ключевых слов для поиска тендеров. Избегай слишком общих корней (обеспеч, поставк, услуг — дают мусор). Используй специфичные термины: для IT — 'программ', 'разработк', 'сервер'; для строительства — 'строй', 'ремонт', 'капремонт'; для медицины — 'медицин', 'оборудован', 'препарат'. Верни ТОЛЬКО слова через пробел. Без пояснений."},
                {"role": "user", "content": f"Описание компании: {description}"}
            ],
            temperature=0.1
        )
        keywords = response.choices[0].message.content.strip()
        # Clean up any quotes or extra punctuation
        keywords = keywords.replace('"', '').replace("'", "").replace(".", "")
        return keywords
    except Exception as e:
        print(f"Error getting keywords: {e}")
        return ""

async def get_ai_scores(description: str, records: List[ContractRecord]) -> dict:
    """Ask GPT-4o to score relevance of contracts and provide reasoning."""
    if not records:
        return {}
        
    # Prepare a simplified list for the LLM
    items = []
    for rec in records:
        price_str = f"{rec.price} {rec.currency}" if rec.price else "Unknown price"
        items.append(f"ID: {rec.number}\nSubject: {rec.subject}\nCustomer: {rec.customer}\nPrice: {price_str}")
    
    items_text = "\n---\n".join(items)
    
    prompt = f"""
    Оцени релевантность тендеров для компании по описанию: "{description}"
    
    Шкала (будь строгим):
    - 0-25: совершенно не по профилю (другая отрасль: медицина/ТКО/энергия/продукты, когда компания делает IT/строй и т.д.)
    - 26-50: косвенно связано, но не основная деятельность
    - 51-75: подходит по направлению
    - 76-100: идеально соответствует профилю компании
    
    Для каждого тендера верни score (0-100) и reason (1 предложение). Начинай reason с "Подходит, потому что..." или "Не подходит, так как...".
    
    Tenders:
    {items_text}
    
    Верни JSON: ключи — ID тендеров (точно как в списке), значения — {{"score": int, "reason": str}}.
    """
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты эксперт по госзакупкам. Оценивай релевантность строго. Возвращай только валидный JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        content = response.choices[0].message.content
        scores = json.loads(content)
        return scores
    except Exception as e:
        print(f"Error scoring records: {e}")
        return {}

async def get_ai_pitfalls(detailed_info: str) -> str:
    """Ask GPT-4o to find 'pitfalls' in the detailed contract info."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Вы — профессиональный юрист в сфере госзакупок (ФЗ-44, ФЗ-223). Проанализируйте предоставленную детальную информацию по контракту и найдите 'подводные камни' (риски) для поставщика по сравнению с обычными закупками. Обратите внимание на необычные условия оплаты, штрафы, сроки или требования к объекту закупки. Ответ дайте в виде списка ключевых рисков на русском языке."},
                {"role": "user", "content": f"Детальная информация по контракту:\n{detailed_info}"}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error getting pitfalls: {e}")
        return "Произошла ошибка при анализе подводных камней."

# AI functions left above...

@app.get("/api/tenders/{reestr_number}/pitfalls")
async def analyze_pitfalls(reestr_number: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_pro:
        raise HTTPException(status_code=403, detail="Требуется Pro подписка")
    
    try:
        # Check DB first
        tender = db.query(Tender).filter(Tender.number == reestr_number).first()
        if tender and tender.pitfalls:
            return {"reestr_number": reestr_number, "pitfalls": tender.pitfalls}
            
        detailed_info = parser.get_detailed_info(reestr_number)
        pitfalls = await get_ai_pitfalls(detailed_info)
        
        # Save to DB if tender exists
        if tender:
            tender.pitfalls = pitfalls
            db.commit()
            
        return {"reestr_number": reestr_number, "pitfalls": pitfalls}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/me/pro")
async def activate_pro(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.is_pro:
        return {"status": "success", "message": "Already Pro", "is_pro": True}
    
    current_user.is_pro = True
    db.commit()
    return {"status": "success", "message": "Pro activated", "is_pro": True}

# Источники данных для фильтра (по procurement_type)
# Каждый источник: (label, patterns) — patterns для ILIKE (основной парсер + external "Источник: X")
TENDER_SOURCES = [
    ("ЕИС Закупки", None),  # None = без суффикса ЭТП
    ("Сбербанк-АСТ", ["Сбербанк-АСТ", "Sberbank", "sberbank-ast"]),
    ("Росэлторг", ["Росэлторг", "Roseltorg", "roseltorg"]),
    ("РТС-тендер", ["РТС-тендер", "РТС", "RTS-tender", "rts-tender"]),
    ("Газпромбанк", ["Газпромбанк", "GPB", "etpgpb"]),
    ("Национальная ЭП", ["Национальная ЭП", "ETS", "etp-ets"]),
    ("ЛОТ-Онлайн", ["ЛОТ-Онлайн", "Lot-Online", "lot-online"]),
    ("ЗаказРФ", ["ЗаказРФ", "ZakazRF-Site", "ZakazRF"]),
    ("ТЭК-Торг", ["ТЭК-Торг", "TEK-Torg-Site", "TEK-Torg"]),
    ("Zakupki-Mos", ["Zakupki-Mos", "zakupki.mos"]),
    ("OTC", ["OTC", "otc.ru"]),
    ("Tender-Pro", ["Tender-Pro", "tender.pro"]),
    ("B2B-Center", ["B2B-Center", "b2b-center"]),
    ("Fabrikant", ["Fabrikant", "fabrikant"]),
]

@app.get("/api/sources")
def get_tender_sources():
    """Список источников данных для фильтра."""
    return [{"id": "all", "label": "Все источники"}] + [
        {"id": label, "label": label} for label, _ in TENDER_SOURCES
    ]

@app.get("/api/search")
async def search_contracts(
    search_string: Optional[str] = None,
    company_description: Optional[str] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    publish_date_from: Optional[str] = None,
    publish_date_to: Optional[str] = None,
    law_44: bool = True,
    law_223: bool = True,
    page: int = 1,
    records_per_page: int = 50,
    region: Optional[str] = None,
    source: Optional[str] = None,
    sort: Optional[str] = None,
    stage: Optional[str] = None,
    hours_ago: Optional[int] = None,
    hide_micro: bool = False,
    ai_search: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # 1. Determine search query. AI — только при явном запросе (ai_search=True), не при смене фильтров
        final_search_string = search_string
        using_ai = False
        if ai_search and current_user.is_pro and not final_search_string and company_description and len(company_description) > 10:
            final_search_string = await get_ai_keywords(company_description)
            using_ai = True
            print(f"AI generated keywords: {final_search_string}")

        # 2. Live Sync — только при поиске по ключевым словам. Без поиска — данные из фоновых потоков
        has_search = bool(final_search_string and str(final_search_string).strip())
        skip_sync = not has_search or _should_skip_live_sync(final_search_string, price_from, price_to)
        if not skip_sync:
            loop = asyncio.get_running_loop()
            eis_result = None
            sber_results = []

            def _run_eis():
                return parser.search(
                    search_string=final_search_string,
                    stage_list=[0, 1, 2, 3],
                    price_from=price_from,
                    price_to=price_to,
                    publish_date_from=publish_date_from,
                    publish_date_to=publish_date_to,
                    law_44=True,
                    law_223=True,
                    page=page,
                    records_per_page=records_per_page
                )

            def _run_sber():
                return sber_parser.search(final_search_string, max_items=20) if final_search_string else []

            try:
                # Параллельный запрос ЕИС и Сбербанк — ускоряет синхронизацию (таймаут 20 сек)
                eis_task = loop.run_in_executor(None, _run_eis)
                sber_task = loop.run_in_executor(None, _run_sber)
                eis_result, sber_results = await asyncio.wait_for(
                    asyncio.gather(eis_task, sber_task),
                    timeout=20.0
                )
            except asyncio.TimeoutError:
                print("Parallel sync timeout (20s)")
            except Exception as par_err:
                print(f"Parallel sync error: {par_err}")
                try:
                    eis_result = _run_eis()
                except Exception as e:
                    print(f"EIS sync error: {e}")
                try:
                    sber_results = _run_sber() if final_search_string else []
                except Exception as e:
                    print(f"Sber sync error: {e}")

            try:
                if eis_result and eis_result.get('records'):
                    for rec in eis_result['records']:
                        existing = db.query(Tender).filter(Tender.number == rec.number).first()
                        if not existing:
                            db.add(Tender(
                                number=rec.number,
                                subject=rec.subject,
                                price=rec.price,
                                currency=rec.currency,
                                update_date=rec.update_date,
                                stage=rec.stage,
                                customer=rec.customer,
                                supplier=rec.supplier,
                                region=rec.region,
                                procurement_type=rec.procurement_type or "44-ФЗ",
                                link=rec.link
                            ))
                        else:
                            existing.region = rec.region
                            existing.procurement_type = rec.procurement_type
                            existing.update_date = rec.update_date
                            existing.stage = rec.stage
                            existing.price = rec.price
                            existing.currency = rec.currency
                    db.commit()
            except Exception as sync_error:
                print(f"Sync error (skipping): {sync_error}")

            try:
                for s_rec in sber_results or []:
                    existing = db.query(Tender).filter(Tender.number == s_rec.reg_number).first()
                    proc_type = "44-ФЗ (Сбербанк-АСТ)"
                    tender_date = s_rec.deadline or s_rec.published_at
                    if not existing:
                        db.add(Tender(
                            number=s_rec.reg_number,
                            subject=s_rec.title,
                            price=s_rec.price,
                            currency=s_rec.currency or "₽",
                            update_date=tender_date,
                            stage=s_rec.stage or "Подача заявок",
                            customer=s_rec.customer or "Не указан",
                            region=s_rec.region,
                            procurement_type=proc_type,
                            link=s_rec.eis_link or s_rec.link
                        ))
                    else:
                        existing.price = s_rec.price or existing.price
                        existing.update_date = tender_date or existing.update_date
                        existing.region = s_rec.region or existing.region
                        existing.procurement_type = proc_type
                db.commit()
            except Exception as sber_sync_err:
                print(f"Sber live sync error: {sber_sync_err}")

            _mark_sync_done(final_search_string, price_from, price_to)

        # 2c-2i. RSS-парсеры (Росэлторг, РТС, GPB, ETS, Lot-Online, ЗаказРФ, ТЭК-Торг)
        # ОТКЛЮЧЕНЫ — RSS ЕИС больше не содержит поле «Электронная площадка».
        # Данные с этих площадок поступают через фоновые потоки sync-sberbank и sync-external.

        # 3. Query from DB (The requested way)
        query = db.query(Tender)
        
        # Исключаем нулевые и мусорные тендеры (всегда)
        query = query.filter(Tender.price.isnot(None), Tender.price > 0, Tender.price < 100e9)
        query = query.filter(Tender.subject.isnot(None), func.length(Tender.subject) >= 5)
        query = query.filter(~Tender.subject.ilike("%предмет не указан%"))
        query = query.filter(Tender.link.isnot(None), Tender.link != "")
        # Исключаем ссылки на общие списки (не на конкретный тендер)
        query = query.filter(~Tender.link.ilike("%/new-tenders%"))
        
        if final_search_string:
            words = [w.strip().replace(',', '').replace(';', '') for w in final_search_string.split() if len(w.strip()) >= 2]
            if words:
                word_conditions = []
                for word in words:
                    search_filter = f"%{word}%"
                    word_conditions.append(
                        (Tender.subject.ilike(search_filter)) |
                        (Tender.customer.ilike(search_filter)) |
                        (Tender.number.ilike(search_filter))
                    )
                query = query.filter(or_(*word_conditions))
        
        # Filter by Law (Step 3 - Query from DB)
        if law_44 and not law_223:
            # Только 44-ФЗ: procurement_type содержит "44-ФЗ" ИЛИ NULL (без типа)
            query = query.filter(
                or_(
                    Tender.procurement_type.ilike("%44-ФЗ%"),
                    Tender.procurement_type == None,
                )
            )
        elif law_223 and not law_44:
            # Только 223-ФЗ
            query = query.filter(Tender.procurement_type.ilike("%223-ФЗ%"))
        elif not law_44 and not law_223:
            # Ничего не выбрано — пустой результат
            query = query.filter(Tender.id < 0)
        
        if price_from is not None:
            query = query.filter(Tender.price >= price_from)
        if price_to is not None:
            query = query.filter(Tender.price <= price_to)
        
        if region:
            query = query.filter(Tender.region.ilike(f"%{region}%"))
        
        # Фильтр по источнику данных
        if source and source != "all":
            if source == "ЕИС Закупки":
                # ЕИС = без суффикса ЭТП (zakupki.gov.ru) и без "Источник:" (внешние парсеры)
                etp_suffixes = ["Сбербанк", "Росэлторг", "РТС-тендер", "Газпромбанк", "Национальная ЭП", "ЛОТ-Онлайн", "ЗаказРФ", "ТЭК-Торг",
                                "Источник:", "TEK-Torg", "Zakupki-Mos", "OTC", "Tender-Pro", "B2B-Center", "Fabrikant", "ZakazRF-Site"]
                no_etp = and_(*[~Tender.procurement_type.ilike(f"%{suf}%") for suf in etp_suffixes])
                query = query.filter(or_(Tender.procurement_type == None, no_etp))
            else:
                # Паттерны для источника (основной парсер + external "Источник: X")
                patterns = next((p for lbl, p in TENDER_SOURCES if lbl == source), [source])
                if isinstance(patterns, list):
                    query = query.filter(or_(*[Tender.procurement_type.ilike(f"%{p}%") for p in patterns]))
                else:
                    query = query.filter(Tender.procurement_type.ilike(f"%{source}%"))
            
        # Фильтр по стадии (stage)
        if stage:
            query = query.filter(Tender.stage.ilike(f"%{stage}%"))
        
        # Фильтр по времени — тендеры за последние N часов
        if hours_ago and hours_ago > 0:
            from datetime import datetime as _dt, timedelta as _td
            cutoff = _dt.now() - _td(hours=hours_ago)
            cutoff_str = cutoff.strftime("%d.%m.%Y %H:%M")
            query = query.filter(Tender.update_date >= cutoff_str)
        
        # Скрыть микролоты < 100K
        if hide_micro:
            query = query.filter(or_(Tender.price == None, Tender.price >= 100000))
            
        # Get total count matching these filters in DB
        db_total_count = query.count()
        
        # FALLBACK: If AI search returned 0 but user has description, try common search
        if db_total_count == 0 and using_ai:
            print("AI search returned 0 results, falling back to all tenders")
            query = db.query(Tender)
            query = query.filter(Tender.price.isnot(None), Tender.price > 0, Tender.price < 100e9)
            query = query.filter(Tender.subject.isnot(None), func.length(Tender.subject) >= 5)
            query = query.filter(~Tender.subject.ilike("%предмет не указан%"))
            query = query.filter(Tender.link.isnot(None), Tender.link != "")
            query = query.filter(~Tender.link.ilike("%/new-tenders%"))
            if law_44 and not law_223:
                query = query.filter(
                    or_(Tender.procurement_type.ilike("%44-ФЗ%"), Tender.procurement_type == None)
                )
            elif law_223 and not law_44:
                query = query.filter(Tender.procurement_type.ilike("%223-ФЗ%"))
            if region:
                query = query.filter(Tender.region.ilike(f"%{region}%"))
            if source and source != "all":
                if source == "ЕИС Закупки":
                    etp_suffixes_fb = ["Сбербанк", "Росэлторг", "РТС-тендер", "Газпромбанк", "Национальная ЭП", "ЛОТ-Онлайн", "ЗаказРФ", "ТЭК-Торг",
                                       "Источник:", "TEK-Torg", "Zakupki-Mos", "OTC", "Tender-Pro", "B2B-Center", "Fabrikant", "ZakazRF-Site"]
                    no_etp = and_(*[~Tender.procurement_type.ilike(f"%{suf}%") for suf in etp_suffixes_fb])
                    query = query.filter(or_(Tender.procurement_type == None, no_etp))
                else:
                    patterns = next((p for lbl, p in TENDER_SOURCES if lbl == source), [source])
                    if isinstance(patterns, list):
                        query = query.filter(or_(*[Tender.procurement_type.ilike(f"%{p}%") for p in patterns]))
                    else:
                        query = query.filter(Tender.procurement_type.ilike(f"%{source}%"))
            db_total_count = query.count()
            final_search_string = None  # Signal that we are not using keywords anymore

        # --- Серверная сортировка ---
        # update_date хранится как "DD.MM.YYYY HH:MM", для сортировки преобразуем в YYYYMMDDHHMM
        _date_sort = text(
            "COALESCE(SUBSTR(tenders.update_date,7,4)||SUBSTR(tenders.update_date,4,2)||"
            "SUBSTR(tenders.update_date,1,2)||REPLACE(COALESCE(SUBSTR(tenders.update_date,12,5),'00:00'),':',''), '00000000')"
        )

        if sort:
            if sort == "date-desc":
                query = query.order_by(text(
                    "COALESCE(SUBSTR(tenders.update_date,7,4)||SUBSTR(tenders.update_date,4,2)||"
                    "SUBSTR(tenders.update_date,1,2)||REPLACE(COALESCE(SUBSTR(tenders.update_date,12,5),'00:00'),':',''), '00000000') DESC"
                ), Tender.id.desc())
            elif sort == "date-asc":
                query = query.order_by(text(
                    "COALESCE(SUBSTR(tenders.update_date,7,4)||SUBSTR(tenders.update_date,4,2)||"
                    "SUBSTR(tenders.update_date,1,2)||REPLACE(COALESCE(SUBSTR(tenders.update_date,12,5),'00:00'),':',''), '00000000') ASC"
                ), Tender.id.asc())
            elif sort == "price-desc":
                query = query.order_by(text("tenders.price DESC NULLS LAST"), Tender.id.desc())
            elif sort == "price-asc":
                query = query.order_by(text("tenders.price ASC NULLS LAST"), Tender.id.asc())
            else:
                query = query.order_by(Tender.id.desc())
        else:
            query = query.order_by(Tender.id.desc())

        # Pagination
        items_per_page = records_per_page if records_per_page > 0 else 500
        offset = (page - 1) * items_per_page
        
        # Get results
        tenders = query.offset(offset).limit(items_per_page).all()
        
        # Показывать relevance/reason только при активном AI-поиске (описание + ai_search).
        # Иначе старые кэшированные оценки из БД не показываем.
        show_ai_scores = ai_search and current_user.is_pro and company_description and len(company_description) > 10
        processed_records = []
        for t in tenders:
            rec_dict = {
                "number": t.number,
                "subject": t.subject,
                "price": t.price,
                "currency": t.currency or "₽",
                "update_date": t.update_date,
                "stage": t.stage,
                "customer": t.customer,
                "supplier": t.supplier,
                "region": t.region,
                "procurement_type": t.procurement_type,
                "link": t.link,
                "relevance": t.relevance_score if show_ai_scores else None,
                "reason": t.relevance_reason if show_ai_scores else None
            }
            # AI Scoring if PRO and no score yet
            if current_user.is_pro and company_description and rec_dict['relevance'] is None:
                # We could score here, but for now let's just use what's in DB
                pass
            processed_records.append(rec_dict)

        # 4. AI Scoring — только при явном ai_search, не при смене фильтров
        if ai_search and current_user.is_pro and company_description and processed_records:
            # Only score items that don't have a score yet or re-score if needed
            to_score = [r for r in processed_records if r['relevance'] is None]
            if to_score:
                # Convert back to simple objects for get_ai_scores
                from dataclasses import dataclass
                @dataclass
                class TempRec:
                    number: str
                    subject: str
                    customer: str
                    price: float
                    currency: str

                score_input = [TempRec(r['number'], r['subject'], r['customer'], r['price'], r['currency']) for r in to_score]
                scores_data = await get_ai_scores(company_description, score_input)
                
                for r in processed_records:
                    if r['number'] in scores_data:
                        data = scores_data[r['number']]
                        score = data.get('score', 0) if isinstance(data, dict) else 0
                        reason = data.get('reason', "") if isinstance(data, dict) else ""
                        
                        r['relevance'] = score
                        r['reason'] = reason
                        
                        # Update DB
                        db_tender = db.query(Tender).filter(Tender.number == r['number']).first()
                        if db_tender:
                            db_tender.relevance_score = score
                            db_tender.relevance_reason = reason
                db.commit()

        # Final filtering and sorting for PRO — только при AI-поиске
        if ai_search and current_user.is_pro and company_description:
            # Показываем только релевантные (score >= 50). Fallback: если 0 — показываем топ-15 по score
            has_scores = any(r.get('relevance') is not None for r in processed_records)
            if has_scores:
                filtered = [r for r in processed_records if r.get('relevance') is not None and r.get('relevance', 0) >= 50]
                if not filtered:
                    # Fallback: хотя бы топ-15 по релевантности, чтобы не было пустого экрана
                    processed_records.sort(key=lambda x: (x.get('relevance') or 0, x.get('update_date') or ''), reverse=True)
                    processed_records = processed_records[:15]
                else:
                    processed_records = filtered
                    processed_records.sort(key=lambda x: (x.get('relevance') or 0, x.get('update_date') or ''), reverse=True)
            else:
                processed_records = [r for r in processed_records if r.get('relevance') is None or r.get('relevance', 0) >= 1]
                processed_records.sort(key=lambda x: (x.get('relevance') or 0, x.get('update_date') or ''), reverse=True)

        return {
            "status": "success", 
            "count": len(processed_records), 
            "total": db_total_count,
            "data": processed_records,
            "generated_query": final_search_string if final_search_string != search_string else None
        }
    except Exception as e:
        print(f"Final error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# --- Auth Endpoints ---

@app.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже зарегистрирован")
    email_lower = user.email.strip().lower()
    if db.query(User).filter(User.email.isnot(None), func.lower(User.email) == email_lower).first():
        raise HTTPException(status_code=400, detail="Этот email уже зарегистрирован")
    
    hashed_password = get_password_hash(user.password)
    verify_code = f"{random.randint(0, 999999):06d}"

    new_user = User(
        username=user.username.strip(),
        hashed_password=hashed_password,
        is_admin=False,
        email=email_lower,
        email_verified=False,
        email_verification_token=verify_code,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    ok = send_verification_code_email(user.email, user.username, verify_code)
    if not ok:
        print(f"[Register] Не удалось отправить письмо на {user.email}")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "email_sent": ok}

@app.get("/api/verify-email")
def api_verify_email(token: str = Query(..., description="Токен верификации"), db: Session = Depends(get_db)):
    """Верификация email по токену из письма (устаревшая ссылка) или 6-значному коду в query."""
    user = db.query(User).filter(User.email_verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Недействительный или устаревший токен")
    user.email_verified = True
    user.email_verification_token = None
    db.commit()
    return {"status": "success", "message": "Email подтверждён"}


@app.post("/api/verify-email-code")
def api_verify_email_code(
    body: VerifyEmailCodeBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Подтверждение email по 6-значному коду из письма (требуется JWT после регистрации)."""
    raw = body.code.strip()
    if len(raw) != 6 or not raw.isdigit():
        raise HTTPException(status_code=400, detail="Введите 6-значный код из письма")
    if current_user.email_verified:
        return {"status": "success", "message": "Email уже подтверждён"}
    stored = current_user.email_verification_token
    if not stored or stored != raw:
        raise HTTPException(status_code=400, detail="Неверный код")
    current_user.email_verified = True
    current_user.email_verification_token = None
    db.commit()
    return {"status": "success", "message": "Email подтверждён"}


@app.post("/api/resend-verification-code")
def api_resend_verification_code(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Повторная отправка кода на email (пользователь авторизован)."""
    if current_user.email_verified:
        raise HTTPException(status_code=400, detail="Email уже подтверждён")
    if not current_user.email:
        raise HTTPException(status_code=400, detail="Email не указан")
    verify_code = f"{random.randint(0, 999999):06d}"
    current_user.email_verification_token = verify_code
    db.commit()
    ok = send_verification_code_email(current_user.email, current_user.username, verify_code)
    if not ok:
        raise HTTPException(status_code=503, detail="Не удалось отправить письмо")
    return {"status": "success", "email_sent": True}


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

def _can_save_description_free(last_saved: Optional[datetime]) -> bool:
    """Первое сохранение в месяц — бесплатно."""
    if not last_saved:
        return True
    now = datetime.utcnow()
    return last_saved.month != now.month or last_saved.year != now.year

@app.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    last_saved = current_user.company_description_last_saved
    can_save_free = _can_save_description_free(last_saved)
    return {
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "id": current_user.id,
        "telegram_id": current_user.telegram_id,
        "is_pro": current_user.is_pro,
        "email": current_user.email,
        "email_verified": getattr(current_user, "email_verified", True),
        "company_description": current_user.company_description,
        "can_save_description_free": can_save_free,
        "description_last_saved": last_saved.isoformat() if last_saved else None,
    }

@app.post("/api/users/me/description")
async def update_company_description(
    data: DescriptionUpdate,
    paid_299: bool = Query(False, description="Оплата 299 ₽ за повторное изменение"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    can_free = _can_save_description_free(current_user.company_description_last_saved)
    if not can_free and not paid_299:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SAVE_LIMIT",
                "message": "Повторное изменение: 1 раз в месяц бесплатно или за 299 ₽",
                "paid_unlock_price": 299,
            },
        )
    current_user.company_description = data.description
    current_user.company_description_last_saved = datetime.utcnow()
    db.commit()
    return {"status": "success", "message": "Description updated"}

@app.get("/api/users/me/telegram-link")
async def get_telegram_link(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Generate code if not exists
    if not current_user.telegram_connect_code:
        # Generate 8-digit code
        code = ''.join(random.choices(string.digits, k=8))
        # Ensure regex uniqueness? For MVP collisions unlikely for 8 digits with small userbase
        current_user.telegram_connect_code = code
        db.commit()
    
    code = current_user.telegram_connect_code
    bot_name = "tendrix_io_bot" # Correct bot username
    link = f"https://t.me/{bot_name}?start={code}"
    
    return {
        "code": code,
        "link": link
    }

# --- Admin Endpoints ---

@app.get("/admin/users", dependencies=[Depends(get_current_admin)])
def read_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{
        "id": u.id,
        "username": u.username,
        "email": u.email or "",
        "email_verified": getattr(u, "email_verified", True),
        "is_admin": u.is_admin,
        "is_active": u.is_active,
    } for u in users]


@app.delete("/admin/users/{user_id}", dependencies=[Depends(get_current_admin)])
def delete_user(user_id: int, current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Удаление пользователя. Нельзя удалить себя или последнего админа."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить свой аккаунт")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.is_admin:
        admin_count = db.query(User).filter(User.is_admin == True).count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Нельзя удалить последнего администратора")
    db.delete(target)
    db.commit()
    return {"status": "deleted"}

@app.post("/admin/promocodes", dependencies=[Depends(get_current_admin)])
def create_promo(promo: PromoCreate, db: Session = Depends(get_db)):
    db_promo = db.query(PromoCode).filter(PromoCode.code == promo.code).first()
    if db_promo:
        raise HTTPException(status_code=400, detail="Promo code already exists")
    
    new_promo = PromoCode(code=promo.code, description=promo.description)
    db.add(new_promo)
    db.commit()
    db.refresh(new_promo)
    return {"status": "created", "code": new_promo.code}

@app.get("/admin/promocodes", dependencies=[Depends(get_current_admin)])
def read_promos(db: Session = Depends(get_db)):
    promos = db.query(PromoCode).all()
    return promos

# SPA Catch-all for React Router
@app.get("/app")
@app.get("/auth")
@app.get("/admin")
@app.get("/admin/")
@app.get("/verify-email")
@app.get("/verify-email-code")
async def serve_spa():
    return FileResponse("static/index.html")

# Mount static files for assets
if not os.path.exists("static"):
    os.makedirs("static")

# Mount assets directory
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

# Catch-all route for SPA (must be last)
@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    # Serve static files if they exist
    file_path = os.path.join("static", full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    # Otherwise serve index.html for SPA routing
    return FileResponse("static/index.html")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
