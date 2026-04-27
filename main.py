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
from urllib.parse import parse_qs, urljoin, urlparse
import uvicorn
import os
import parser_http_env  # noqa: F401 — PARSER_HTTP_PROXY / OPENAI_HTTP_PROXY для requests
import httpx
import requests
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from openai import AsyncOpenAI
from bs4 import BeautifulSoup

# DB & Auth Imports
from database import SessionLocal, engine, User, PromoCode, Tender, init_db, RegistrationEmailPending
from auth import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

import asyncio
import random
import string
import os
import secrets
import re
import ipaddress
import threading
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
    for col_sql, label in [
        ("ALTER TABLE tenders ADD COLUMN relevance_score INTEGER", "relevance_score"),
        ("ALTER TABLE tenders ADD COLUMN relevance_reason TEXT", "relevance_reason"),
        ("ALTER TABLE tenders ADD COLUMN pitfalls TEXT", "pitfalls"),
    ]:
        try:
            conn.execute(text(col_sql))
            print(f"Migrated: Added tenders.{label}")
        except Exception:
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
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN openai_tokens_total INTEGER DEFAULT 0"))
        print("Migrated: Added users.openai_tokens_total")
    except Exception:
        pass
    # Telegram ID больше не уникален: снимаем UNIQUE-индекс, если он был создан ранее.
    try:
        conn.execute(text("DROP INDEX IF EXISTS ix_users_telegram_id"))
        # Не печатаем "Migrated" каждый раз — индекс мог и не существовать.
    except Exception:
        pass
    # Обычный (не unique) индекс для ускорения выборок по telegram_id
    try:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)"))
    except Exception:
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
print("Initializing DB...") ##########################################################Mistake I've made here to stop the script
init_db()
print("DB Initialized")
migrate_db() # Run migration

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Pydantic Models ---
class RegisterComplete(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6)
    completion_token: str = Field(..., min_length=16)


class RegisterRequestCode(BaseModel):
    email: str = Field(..., min_length=3)


class RegisterVerifyCodeBody(BaseModel):
    email: str = Field(..., min_length=3)
    code: Optional[str] = None

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


class PromoPatch(BaseModel):
    is_active: Optional[bool] = None

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
            admin = User(
                username="admin",
                hashed_password=hashed_pw,
                is_admin=True,
                email_verified=True,
            )
            db.add(admin)
            db.commit()
            print("Default admin created: admin / admin123")
        elif admin.is_admin and not admin.email and not admin.email_verified:
            # Старые БД: встроенный admin без почты не должен требовать верификацию
            admin.email_verified = True
            db.commit()
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
from external_parsers import SourceConfig, fetch_tender_from_url, sync_external_sources
from tg_notify import sync_currently_published_tenders, queue_new_tender
from tender_collector import TenderCollector

import hashlib
import json
import logging
import time

app = FastAPI(title="Zakupki Parser API")

# Кэш live-sync: при смене только фильтров (law44, law223 и т.д.) не дергать внешние API
_sync_cache: dict = {}
_sync_inflight: set[str] = set()
_sync_lock = threading.Lock()
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


def _run_live_sync_worker(
    *,
    search_string: str,
    price_from: Optional[float],
    price_to: Optional[float],
    publish_date_from: Optional[str],
    publish_date_to: Optional[str],
    page: int,
    records_per_page: int,
) -> None:
    """Синхронизирует свежие результаты в фоне, не блокируя /api/search."""
    key = _sync_cache_key(search_string, price_from, price_to)
    sync_db = SessionLocal()
    local_parser = ZakupkiContractParser(timeout=8)
    local_sber_parser = SberbankAstParser(timeout=8, max_retries=1)
    try:
        eis_result = None
        sber_results = []

        try:
            eis_result = local_parser.search(
                search_string=search_string,
                stage_list=[0, 1, 2, 3],
                price_from=price_from,
                price_to=price_to,
                publish_date_from=publish_date_from,
                publish_date_to=publish_date_to,
                law_44=True,
                law_223=True,
                page=page,
                records_per_page=records_per_page,
            )
        except Exception as e:
            print(f"Live sync EIS error: {e}")

        try:
            sber_results = local_sber_parser.search(search_string, max_items=20) if search_string else []
        except Exception as e:
            print(f"Live sync Sber error: {e}")

        try:
            if eis_result and eis_result.get("records"):
                for rec in eis_result["records"]:
                    existing = sync_db.query(Tender).filter(Tender.number == rec.number).first()
                    if not existing:
                        sync_db.add(Tender(
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
                sync_db.commit()
        except Exception as sync_error:
            print(f"Live sync DB upsert error: {sync_error}")
            sync_db.rollback()

        try:
            for s_rec in sber_results or []:
                existing = sync_db.query(Tender).filter(Tender.number == s_rec.reg_number).first()
                proc_type = "44-ФЗ (Сбербанк-АСТ)"
                tender_date = s_rec.deadline or s_rec.published_at
                if not existing:
                    sync_db.add(Tender(
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
            sync_db.commit()
        except Exception as sber_sync_err:
            print(f"Sber live sync error: {sber_sync_err}")
            sync_db.rollback()
    finally:
        sync_db.close()
        with _sync_lock:
            _sync_inflight.discard(key)
            _mark_sync_done(search_string, price_from, price_to)


def _trigger_live_sync(
    *,
    search_string: Optional[str],
    price_from: Optional[float],
    price_to: Optional[float],
    publish_date_from: Optional[str],
    publish_date_to: Optional[str],
    page: int,
    records_per_page: int,
) -> bool:
    """Запускает live-sync один раз на ключ/TTL и сразу возвращает управление."""
    if not search_string or not str(search_string).strip():
        return False

    normalized_search = str(search_string).strip()
    key = _sync_cache_key(normalized_search, price_from, price_to)
    with _sync_lock:
        if _should_skip_live_sync(normalized_search, price_from, price_to) or key in _sync_inflight:
            return False
        _sync_inflight.add(key)

    threading.Thread(
        target=_run_live_sync_worker,
        kwargs={
            "search_string": normalized_search,
            "price_from": price_from,
            "price_to": price_to,
            "publish_date_from": publish_date_from,
            "publish_date_to": publish_date_to,
            "page": page,
            "records_per_page": records_per_page,
        },
        daemon=True,
        name=f"live-sync:{normalized_search[:24]}",
    ).start()
    return True

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

# OpenAI: ключ и HTTP-прокси (httpx). Сначала PARSER_HTTP_PROXY (как у парсеров), иначе OPENAI_HTTP_PROXY.
# Формат прокси: http://user:pass@host:port или host:port:user:pass — см. parser_http_env.py
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
PROXY_URL = (
    os.environ.get("PARSER_HTTP_PROXY", "").strip()
    or os.environ.get("OPENAI_HTTP_PROXY", "").strip()
    or None
)
http_client = httpx.AsyncClient(proxy=PROXY_URL) if PROXY_URL else httpx.AsyncClient()
client = AsyncOpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
SEARCH_GOOGLE_URL = os.environ.get("SEARCH_GOOGLE_URL", "https://159.194.208.20.nip.io/api/search/google").strip()
SEARCH_GOOGLE_API_KEY = os.environ.get("SEARCH_GOOGLE_API_KEY", "").strip()
SEARCH_GOOGLE_SIZE = max(1, min(int(os.environ.get("SEARCH_GOOGLE_SIZE", "5")), 10))
SEARCH_GOOGLE_TIMEOUT = float(os.environ.get("SEARCH_GOOGLE_TIMEOUT", "18"))


def _record_user_openai_tokens(user_id: int, usage) -> None:
    """Увеличивает openai_tokens_total пользователя по полю usage ответа Chat Completions."""
    if not usage or not user_id:
        return
    total = getattr(usage, "total_tokens", None)
    if total is None:
        pt = getattr(usage, "prompt_tokens", None) or 0
        ct = getattr(usage, "completion_tokens", None) or 0
        total = pt + ct
    try:
        total = int(total)
    except (TypeError, ValueError):
        return
    if total <= 0:
        return
    udb = SessionLocal()
    try:
        u = udb.query(User).filter(User.id == user_id).first()
        if not u:
            return
        prev = int(getattr(u, "openai_tokens_total", None) or 0)
        u.openai_tokens_total = prev + total
        udb.commit()
    except Exception as e:
        print(f"_record_user_openai_tokens: {e}")
        udb.rollback()
    finally:
        udb.close()


# Background Sync Thread
import time
import urllib.error
import urllib.request

_telegram_bot_public_url_cache: Optional[str] = None


def _resolve_telegram_bot_public_url() -> str:
    """Публичная ссылка на бота: TELEGRAM_BOT_URL, либо username, либо getMe по TELEGRAM_BOT_TOKEN."""
    u = os.environ.get("TELEGRAM_BOT_URL", "").strip()
    if u:
        return u
    un = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if un:
        return f"https://t.me/{un}"
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return ""
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getMe",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
        username = (data.get("result") or {}).get("username")
        if isinstance(username, str) and username:
            return f"https://t.me/{username}"
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return ""


def get_telegram_bot_public_url() -> str:
    global _telegram_bot_public_url_cache
    if _telegram_bot_public_url_cache is None:
        _telegram_bot_public_url_cache = _resolve_telegram_bot_public_url()
    return _telegram_bot_public_url_cache


def _telegram_bot_username_for_deeplink() -> str:
    """Имя бота (без @) для t.me/...?start= из публичного URL или запасной вариант."""
    base = get_telegram_bot_public_url().rstrip("/")
    if not base:
        return "tendrix_io_bot"
    low = base.lower()
    marker = "t.me/"
    idx = low.find(marker)
    if idx >= 0:
        u = base[idx + len(marker) :].split("/")[0].split("?")[0].strip()
        if u:
            return u
    return "tendrix_io_bot"


# ---------------------------------------------------------------------------
#  Валидация тендеров из best-effort источников
# ---------------------------------------------------------------------------
ENABLE_EXTERNAL_SYNC = os.environ.get("ENABLE_EXTERNAL_SYNC", "0").strip().lower() not in {"0", "false", "no"}
ENABLE_COLLECTOR_SYNC = os.environ.get("ENABLE_COLLECTOR_SYNC", "0").strip().lower() in {"1", "true", "yes"}
LEGACY_SEARCH_ENABLED = os.environ.get("LEGACY_SEARCH_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
LEGACY_SEARCH_URL = os.environ.get("LEGACY_SEARCH_URL", "https://tendrix.io").strip().rstrip("/")
LEGACY_SEARCH_USERNAME = os.environ.get("LEGACY_SEARCH_USERNAME", "admin").strip()
LEGACY_SEARCH_PASSWORD = os.environ.get("LEGACY_SEARCH_PASSWORD", "admin123").strip()
LEGACY_SEARCH_MIN_LOCAL_TOTAL = int(os.environ.get("LEGACY_SEARCH_MIN_LOCAL_TOTAL", "1000"))
# Минимум релевантности (0–100) для показа тендера при умном поиске (ниже — слишком много «чужой» отрасли)
AI_SEARCH_MIN_RELEVANCE = int(os.environ.get("AI_SEARCH_MIN_RELEVANCE", "60"))
# Сколько тендеров за один запрос к модели при скоринге (меньше — строже и стабильнее JSON)
AI_SEARCH_SCORE_CHUNK = max(3, min(int(os.environ.get("AI_SEARCH_SCORE_CHUNK", "12")), 30))
# Сколько страниц legacy-выдачи последовательно сканировать при умном поиске (каждая страница — отдельная оценка ИИ)
AI_SEARCH_SCAN_MAX_PAGES = max(1, min(int(os.environ.get("AI_SEARCH_SCAN_MAX_PAGES", "12")), 40))
_legacy_search_token_cache = {"token": None, "expires_at": 0.0}

# Одна строка после описания компании — часто случайный запрос из поля «поиск», не часть профиля
_TRAILING_LINE_SEARCH_NOISE_WORDS = frozenset(
    {
        "ремонт",
        "поставка",
        "поставки",
        "закупка",
        "закупки",
        "услуги",
        "услуга",
        "монтаж",
        "поиск",
        "доставка",
        "аренда",
        "строительство",
        "тендер",
        "тендеры",
        "косметический",
        "текущий",
        "капитальный",
    }
)


def _strip_accidental_trailing_search_line_from_company(text: str) -> str:
    """Если ровно две строки и вторая — одно короткое слово из типичных «поисковых», оставляем только первую строку."""
    t = (text or "").replace("\r\n", "\n").strip()
    if "\n" not in t:
        return t
    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    if len(lines) != 2:
        return "\n".join(lines)
    second = lines[1].strip().lower().strip(".,;:")
    if second in _TRAILING_LINE_SEARCH_NOISE_WORDS and len(lines[1]) <= 24:
        return lines[0]
    return "\n".join(lines)


def _expand_company_description_for_ai(description: str) -> str:
    """Расширяет слишком короткое описание для промптов ИИ (скоринг и ключевые слова), без изменения текста в профиле."""
    d = (description or "").strip()
    if not d:
        return ""
    low = d.lower()
    it_hint = any(
        x in low
        for x in (
            "it-компан",
            "ит-компан",
            "it компан",
            "ит компан",
            "айти-компан",
            "it company",
            "software",
            "saas",
            "erp",
            "crm",
            "веб-студ",
            "цифров",
            "информационн",
            "разработк",
            "программн",
        )
    )
    if it_hint and len(d) < 80:
        return (
            f"{d} — профиль: разработка ПО, веб- и мобильные приложения, сайты, интеграции "
            f"(API, ERP/CRM/1С), ИТ-инфраструктура, серверы, сети, ИБ, техподдержка и сопровождение ПО, "
            f"лицензии и ИТ-оборудование под эти задачи"
        )
    return d


_GENERIC_EXTERNAL_TITLES = (
    "о компании", "регистрация", "тарифы", "контрагенты", "документы",
    "центр поддержки", "видеоматериалы", "подписка на закупки", "подписка",
    "услуги и сервисы", "эффективные закупки", "быстрая регистрация",
    "заказчикам", "поставщикам", "начать работу", "тендерное сопровождение",
    "интернет-магазин", "продажи", "реализациянеликвидов",
    "противодействие коррупции", "управление государственными и муниципальными закупками",
)
_GENERIC_EXTERNAL_PATH_PARTS = (
    "/registration", "/register", "/help", "/docs", "/documents", "/services",
    "/service", "/support", "/api/landings/", "/api/register", "/api/sys_news",
    "/api/nomenclature/", "/api/tenders/search", "/procedures", "/tenders",
    "/subscription", "/auth/login",
)
_GENERIC_EXTERNAL_LAST_SEGMENTS = {
    "tender", "tenders", "purchase", "purchases", "auction", "auctions",
    "trade", "trades", "notice", "notices", "detail", "details",
    "procedure", "procedures", "documents", "services", "service",
    "help", "support", "registration",
}


def _get_legacy_search_token() -> Optional[str]:
    if not (LEGACY_SEARCH_ENABLED and LEGACY_SEARCH_URL and LEGACY_SEARCH_USERNAME and LEGACY_SEARCH_PASSWORD):
        return None

    now = time.time()
    cached_token = _legacy_search_token_cache.get("token")
    cached_exp = float(_legacy_search_token_cache.get("expires_at") or 0.0)
    if cached_token and cached_exp > now:
        return str(cached_token)

    session = requests.Session()
    session.trust_env = False
    response = session.post(
        f"{LEGACY_SEARCH_URL}/token",
        data={"username": LEGACY_SEARCH_USERNAME, "password": LEGACY_SEARCH_PASSWORD},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    if not token:
        return None
    _legacy_search_token_cache["token"] = token
    _legacy_search_token_cache["expires_at"] = now + 15 * 60
    return str(token)


def _legacy_row_number(r: dict) -> str:
    """Номер закупки в ответе legacy/API: разные ключи у разных версий фронта."""
    if not isinstance(r, dict):
        return ""
    for key in ("number", "reestr_number", "reestrNumber", "notice_number", "purchase_number"):
        v = r.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _proxy_legacy_search(params: dict) -> Optional[dict]:
    token = _get_legacy_search_token()
    if not token:
        return None

    # Иначе upstream (тот же инстанс tendrix) снова включает умный поиск → рекурсия и «тот же» ответ без фильтра.
    upstream = {**params, "ai_search": "false"}

    session = requests.Session()
    session.trust_env = False
    response = session.get(
        f"{LEGACY_SEARCH_URL}/api/search",
        headers={"Authorization": f"Bearer {token}"},
        params=upstream,
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("status") == "success":
        return payload
    return None


def _proxy_legacy_pitfalls(reestr_number: str) -> Optional[str]:
    token = _get_legacy_search_token()
    if not token:
        return None

    session = requests.Session()
    session.trust_env = False
    response = session.get(
        f"{LEGACY_SEARCH_URL}/api/tenders/{reestr_number}/pitfalls",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        text = payload.get("pitfalls")
        if isinstance(text, str) and text.strip():
            cleaned = _sanitize_pitfalls_text(text)
            return cleaned or text.strip()
    return None


def _is_placeholder_pitfalls(text: Optional[str]) -> bool:
    normalized = " ".join((text or "").strip().lower().split())
    if not normalized:
        return True
    bad_patterns = (
        "к сожалению, предоставленная информация",
        "предоставленная информация по контракту содержит ошибки",
        "невозможным проведение полноценного анализа",
        "необходимо получить доступ к полной информации",
        "я могу предложить общие риски",
        "общие риски, которые часто встречаются",
        "без конкретной информации по контракту",
        "важно проверить",
        "убедитесь, что",
        "часто в контрактах прописываются",
        "часто в контрактах",
        "это общие рекомендации",
        "общие рекомендации, которые",
        "ошибк при загрузке",
        "ошибки при загрузке",
        "проблемы с доступом к информации",
        "дополнительных переговоров",
        "произошла ошибка при анализе подводных камней",
        "явные нетипичные риски по доступным данным не обнаружены",
        "нетипичные риски по доступным данным не обнаружены",
        "риски по доступным данным не обнаружены",
        "подводных камней не обнаружено",
        "существенных рисков не выявлено",
    )
    return any(pat in normalized for pat in bad_patterns)


def _is_vacuous_pitfalls_response(text: Optional[str]) -> bool:
    """Ответ «ничего не нашли» или слишком короткий — нужен повтор или fallback."""
    if not text or not str(text).strip():
        return True
    normalized = " ".join(str(text).strip().lower().split())
    if len(normalized) < 40:
        return True
    vacuous = (
        "явные нетипичные риски",
        "нетипичные риски по доступным данным не обнаружены",
        "риски по доступным данным не обнаружены",
        "существенных рисков не выявлено",
        "подводных камней не обнаружено",
    )
    if any(v in normalized for v in vacuous):
        return True
    # Короткий ответ в одну строку без нумерации — часто заглушка
    raw_s = str(text).strip()
    lines = [ln.strip() for ln in raw_s.splitlines() if ln.strip()]
    if len(raw_s) < 200 and len(lines) <= 1 and not re.search(r"^\d+\.", raw_s, re.MULTILINE):
        return True
    return False


def _has_meaningful_detailed_info(detailed_info: Optional[str]) -> bool:
    text = (detailed_info or "").strip()
    if len(text) < 250:
        return False
    error_markers = text.count("[Ошибка при загрузке данных]")
    return error_markers < 3


def _has_meaningful_tender_page_text(text: Optional[str]) -> bool:
    return len((text or "").strip()) >= 200


# Браузероподобный запрос: ЕИС часто отдаёт «пустую» разметку ботам с нестандартным User-Agent.
_PITFALLS_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _pitfall_page_url_candidates(
    reestr_number: str,
    tender_link: Optional[str],
    query_link: Optional[str],
    procurement_type: Optional[str],
) -> list[str]:
    """Порядок: ссылка из запроса (как у кнопки «Открыть»), затем из БД, затем типовые URL карточки извещения ЕИС."""
    out: list[str] = []
    seen: set[str] = set()

    def add(u: Optional[str]) -> None:
        if not u:
            return
        s = str(u).strip()
        if not s or s in seen:
            return
        if _is_safe_http_url_for_fetch(s):
            seen.add(s)
            out.append(s)

    add(query_link)
    add(tender_link)
    rn = (reestr_number or "").strip()
    if re.fullmatch(r"\d{11,}", rn):
        pt = (procurement_type or "").lower()
        if "223" in pt:
            add(f"https://zakupki.gov.ru/epz/order/notice/notice223/view/common-info.html?regNumber={rn}")
        else:
            add(f"https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber={rn}")
            add(f"https://zakupki.gov.ru/epz/order/notice/zk20/view/common-info.html?regNumber={rn}")
        if "223" not in pt:
            add(f"https://zakupki.gov.ru/epz/order/notice/notice223/view/common-info.html?regNumber={rn}")
    return out


def _prepare_detailed_info_for_pitfalls(detailed_info: Optional[str]) -> str:
    parts: list[str] = []
    current_lines: list[str] = []
    current_has_error = False

    for line in (detailed_info or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("==="):
            if current_lines and not current_has_error:
                parts.append("\n".join(current_lines).strip())
            current_lines = [stripped]
            current_has_error = False
            continue
        if "[Ошибка при загрузке данных]" in stripped:
            current_has_error = True
            continue
        if stripped:
            current_lines.append(stripped)

    if current_lines and not current_has_error:
        parts.append("\n".join(current_lines).strip())

    cleaned = "\n\n".join(part for part in parts if part)
    return cleaned[:15000]


def _sanitize_pitfalls_text(text: Optional[str]) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    banned_fragments = (
        "ошибк при загрузке",
        "ошибки при загрузке",
        "отсутствие информации",
        "проблемы с доступом к информации",
        "доступ к необходимой информации",
        "необходимо получить доступ к полной информации",
        "невозможным проведение полноценного анализа",
        "эти риски требуют внимательного анализа",
        "дополнительных переговоров",
        "я могу предложить общие риски",
        "общие риски, которые часто встречаются",
    )

    items: list[str] = []
    current: list[str] = []

    def flush_current():
        if not current:
            return
        item = " ".join(part.strip() for part in current if part.strip()).strip()
        item = re.sub(r"^\d+\.\s*", "", item)
        item = re.sub(r"^-\s*", "", item)
        normalized = " ".join(item.lower().split())
        if item and not any(fragment in normalized for fragment in banned_fragments):
            items.append(item)

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = " ".join(stripped.lower().split())
        if lowered.startswith("на основании предоставленной информации"):
            continue
        if lowered.startswith("к сожалению, предоставленная информация"):
            continue
        if re.match(r"^\d+\.\s+", stripped) or stripped.startswith("- "):
            flush_current()
            current = [stripped]
        else:
            if current:
                current.append(stripped)

    flush_current()

    if items:
        return "\n\n".join(f"{idx}. {item}" for idx, item in enumerate(items, 1))
    return ""


def _build_tender_context_for_pitfalls(tender: Optional[Tender], reestr_number: str) -> str:
    lines = [f"Реестровый номер: {reestr_number}"]
    if tender:
        if tender.subject:
            lines.append(f"Предмет: {tender.subject}")
        if tender.customer:
            lines.append(f"Заказчик: {tender.customer}")
        if tender.price is not None:
            currency = tender.currency or "₽"
            lines.append(f"Цена: {tender.price} {currency}")
        if tender.update_date:
            lines.append(f"Дата/обновление: {tender.update_date}")
        if tender.stage:
            lines.append(f"Стадия: {tender.stage}")
        if tender.procurement_type:
            lines.append(f"Тип закупки: {tender.procurement_type}")
        if tender.region:
            lines.append(f"Регион: {tender.region}")
        if tender.link:
            lines.append(f"Ссылка: {tender.link}")
    return "\n".join(lines)


def _build_pitfalls_search_query(tender: Optional[Tender], reestr_number: str) -> str:
    """Запрос для RAG: только идентификаторы и суть закупки — без общих «штрафы/контракт», иначе в ответ попадают однотипные статьи."""
    parts = [reestr_number]
    if tender:
        if tender.subject:
            parts.append(str(tender.subject)[:220])
        if tender.customer:
            parts.append(str(tender.customer)[:140])
        if tender.procurement_type:
            parts.append(str(tender.procurement_type)[:60])
    return " ".join(part.strip() for part in parts if part and str(part).strip())


def _trim_web_context_for_pitfalls(web_context: str, page_ok: bool) -> str:
    """При наличии полного текста извещения сильно режем RAG — иначе модель копирует общие юридические сводки."""
    w = (web_context or "").strip()
    if not w:
        return ""
    max_len = 2800 if page_ok else 8000
    if len(w) <= max_len:
        return w
    return w[:max_len] + "\n\n[…фрагменты веб-поиска обрезаны: приоритет — текст извещения выше…]"


_PITFALLS_GROUND_STOP = frozenset(
    """
    который которой которого этот эта этого этой этом этими этих также такой такая такое
    """.split()
)


def _pitfalls_response_looks_ungrounded(response: str, tender_page_text: str) -> bool:
    """
    Эвристика: ответ слишком общий относительно текста страницы (мало пересечения с фактами из извещения).
    """
    page = (tender_page_text or "").strip()
    if len(page) < 500:
        return False
    resp = (response or "").strip()
    if len(resp) < 120:
        return True
    rlow = resp.lower()
    if len(re.findall(r"\d", rlow)) >= 5:
        return False
    words = re.findall(r"[\wа-яё]{6,}", page.lower(), flags=re.UNICODE)
    seen: set[str] = set()
    distinct: list[str] = []
    for w in words:
        if w in _PITFALLS_GROUND_STOP:
            continue
        if w in seen:
            continue
        seen.add(w)
        distinct.append(w)
        if len(distinct) >= 45:
            break
    hits = sum(1 for w in distinct if w in rlow)
    if hits >= 3:
        return False
    generic_hits = sum(
        1
        for phrase in (
            "в соответствии с фз",
            "ст. 14.32",
            "ст. 178",
            "коап рф",
            "общие риски",
            "типичн",
            "как правило",
            "веб-источник",
            "март 2025",
            "изменен",
        )
        if phrase in rlow
    )
    if generic_hits >= 2 and hits < 2:
        return True
    return hits < 2


def _pitfalls_response_looks_advisory(response: str) -> bool:
    """
    Ответ в стиле чеклиста («проверьте», «убедитесь») вместо собственного вывода по тексту извещения.
    """
    if not (response or "").strip():
        return False
    r = " ".join(response.lower().split())
    markers = (
        "важно проверить",
        "необходимо проверить",
        "следует проверить",
        "рекомендуется проверить",
        "убедитесь, что",
        "убедитесь что",
        "общие рекомендации",
        "без конкретной информации по контракту",
        "часто в контрактах прописываются",
        "может помочь в оценке рисков",
        "это общие рекомендации",
    )
    mcount = sum(1 for m in markers if m in r)
    if mcount >= 2:
        return True
    if r.count("убедитесь") >= 2 or r.count("проверьте") >= 2:
        return True
    if mcount >= 1 and len(re.findall(r"\d", r)) < 4:
        return True
    return False


async def _fetch_google_rag_context_for_pitfalls(tender: Optional[Tender], reestr_number: str) -> str:
    if not (SEARCH_GOOGLE_URL and SEARCH_GOOGLE_API_KEY):
        return ""

    payload = {
        "query": _build_pitfalls_search_query(tender, reestr_number),
        "size": SEARCH_GOOGLE_SIZE,
        "prepare_rag_chunks": True,
    }
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": SEARCH_GOOGLE_API_KEY,
    }

    timeout = httpx.Timeout(SEARCH_GOOGLE_TIMEOUT, connect=min(10.0, SEARCH_GOOGLE_TIMEOUT))

    try:
        async with httpx.AsyncClient(timeout=timeout) as search_client:
            response = await search_client.post(SEARCH_GOOGLE_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        print(f"Google search API error for pitfalls: {e}")
        return ""

    hits = []
    if isinstance(data, dict):
        raw_hits = data.get("hits")
        if isinstance(raw_hits, list):
            hits = raw_hits
        elif isinstance(data.get("data"), list):
            hits = data.get("data") or []

    blocks: list[str] = []
    chunk_count = 0
    for idx, hit in enumerate(hits[:SEARCH_GOOGLE_SIZE], 1):
        if not isinstance(hit, dict):
            continue

        title = str(hit.get("title") or "").strip()
        url = str(hit.get("url") or hit.get("link") or "").strip()
        content = str(hit.get("content") or "").strip()
        block_lines = [f"[Веб-источник {idx}]"]
        if title:
            block_lines.append(f"Заголовок: {title}")
        if url:
            block_lines.append(f"URL: {url}")
        if content:
            block_lines.append(f"Сводка: {content[:900]}")

        rag_chunks = hit.get("rag_chunks")
        if isinstance(rag_chunks, list):
            for rag_idx, chunk in enumerate(rag_chunks[:2], 1):
                if not isinstance(chunk, dict):
                    continue
                chunk_text = str(chunk.get("content") or "").strip()
                if not chunk_text:
                    continue
                metadata = chunk.get("metadata") or {}
                meta_parts = []
                if isinstance(metadata, dict):
                    source = metadata.get("source") or metadata.get("url")
                    if source:
                        meta_parts.append(f"source={source}")
                    chunk_title = metadata.get("title")
                    if chunk_title:
                        meta_parts.append(f"title={chunk_title}")
                chunk_label = f"Фрагмент {rag_idx}"
                if meta_parts:
                    chunk_label += f" ({', '.join(meta_parts)})"
                block_lines.append(f"{chunk_label}: {chunk_text[:1200]}")
                chunk_count += 1
                if chunk_count >= 6:
                    break
        blocks.append("\n".join(block_lines))
        if chunk_count >= 6:
            break

    return "\n\n".join(blocks)[:8000]


async def _fetch_detailed_info_for_pitfalls(reestr_number: str, timeout_seconds: float = 35.0) -> str:
    try:
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: parser.get_detailed_info(reestr_number)),
            timeout=timeout_seconds,
        )
    except Exception as e:
        print(f"Detailed info fetch error for pitfalls {reestr_number}: {e}")
        return ""


def _is_safe_http_url_for_fetch(url: str) -> bool:
    """Базовая защита от SSRF: только http(s), без loopback и частных адресов."""
    try:
        p = urlparse(url.strip())
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower().strip()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    except ValueError:
        pass
    return True


def _sync_fetch_tender_page_text(url: str) -> str:
    """Скачивает HTML и извлекает видимый текст для анализа подводных камней."""
    max_bytes = 2_000_000
    max_chars = 28_000
    session = requests.Session()
    session.trust_env = True
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except Exception:
        host = ""
    headers = {
        "User-Agent": _PITFALLS_CHROME_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
    }
    if "zakupki.gov.ru" in host:
        headers["Referer"] = "https://zakupki.gov.ru/"
    try:
        r = session.get(url, timeout=(12, 30), headers=headers, allow_redirects=True)
        r.raise_for_status()
        raw = r.content
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
        enc = r.encoding
        if not enc or enc.lower() == "iso-8859-1":
            enc = r.apparent_encoding or "utf-8"
        html = raw.decode(enc, errors="replace")
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
            tag.decompose()
        main = soup.select_one("main") or soup.select_one("#content") or soup.select_one(".content") or soup.body
        if main is not None:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)
        if len(text.strip()) < 400:
            text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[…текст обрезан по объёму…]"
        return text.strip()
    except Exception as e:
        print(f"Tender page fetch error for {url[:96]}: {e}")
        return ""


async def _fetch_best_tender_page_text_from_urls(urls: list[str]) -> str:
    """Пробует несколько URL (кнопка «Открыть», БД, типовые страницы ЕИС) и берёт самый содержательный текст."""
    best = ""
    seen: set[str] = set()
    loop = asyncio.get_running_loop()
    for raw in urls:
        if not raw:
            continue
        u = str(raw).strip()
        if u in seen or not _is_safe_http_url_for_fetch(u):
            continue
        seen.add(u)
        text = await loop.run_in_executor(None, lambda url=u: _sync_fetch_tender_page_text(url))
        if len(text) > len(best):
            best = text
        if len(text) >= 12_000:
            break
    return best


def _looks_like_detail_link(link: Optional[str]) -> bool:
    if not link:
        return False
    try:
        parsed = urlparse(link.strip())
    except Exception:
        return False
    path = (parsed.path or "").lower().rstrip("/")
    query = parsed.query or ""

    if not parsed.scheme or not parsed.netloc:
        return False
    if any(part in path for part in _GENERIC_EXTERNAL_PATH_PARTS):
        return False

    segments = [seg for seg in path.split("/") if seg]
    last_segment = (segments[-1] if segments else "").lower()
    query_map = parse_qs(query)

    if any(k in query_map for k in ("id", "guid", "lotid", "tradeid", "purchaseid", "noticeinfoid")):
        return True
    if "view_public" in path:
        return True
    if any(re.fullmatch(r"\d{6,}", seg) for seg in segments):
        return True
    if any(re.fullmatch(r"[0-9a-f]{8,}", seg.lower()) for seg in segments):
        return True
    if any(token in path for token in ("/detail", "/details", "/lot/", "/tender/", "/purchase/", "/auction/", "/trade/", "/notice/")):
        return bool(last_segment and last_segment not in _GENERIC_EXTERNAL_LAST_SEGMENTS)
    return False


def _looks_like_generic_external_subject(subject: Optional[str]) -> bool:
    normalized = " ".join((subject or "").strip().lower().split())
    if not normalized or len(normalized) < 10:
        return True
    return any(bad in normalized for bad in _GENERIC_EXTERNAL_TITLES)


def _is_real_tender_record(
    number: Optional[str],
    subject: Optional[str],
    price,
    update_date: Optional[str],
    customer: Optional[str],
    procurement_type: Optional[str],
    link: Optional[str],
) -> bool:
    proc_type = (procurement_type or "").strip()
    if not proc_type.startswith("Источник:"):
        return True

    if _looks_like_generic_external_subject(subject):
        return False

    normalized_number = (number or "").strip()
    normalized_customer = (customer or "").strip()
    detail_link = _looks_like_detail_link(link)
    has_number = bool(
        normalized_number
        and not normalized_number.startswith("col_")
        and not normalized_number.startswith("TEKTORG_SITE:")
        and not normalized_number.startswith("TENDER_PRO:")
        and re.search(r"\d{6,}", normalized_number)
    )
    has_price = price is not None and isinstance(price, (int, float)) and price > 0
    has_date = bool(update_date and re.search(r"\d{2}\.\d{2}\.\d{4}", str(update_date)))
    has_customer = bool(
        normalized_customer
        and normalized_customer.lower() not in {"не указан", "поставщикам", "заказчикам"}
        and len(normalized_customer) >= 5
    )

    quality_signals = sum([detail_link, has_number, has_price, has_date, has_customer])
    return quality_signals >= 2 and (detail_link or has_number)


def _purge_invalid_external_tenders() -> None:
    removed = 0
    with SessionLocal() as db:
        bad_rows = db.query(Tender).filter(Tender.procurement_type.ilike("Источник:%")).all()
        for tender in bad_rows:
            if not _is_real_tender_record(
                tender.number,
                tender.subject,
                tender.price,
                tender.update_date,
                tender.customer,
                tender.procurement_type,
                tender.link,
            ):
                db.delete(tender)
                removed += 1
        if removed:
            db.commit()
    print(f"[Startup] Purged invalid external tenders: {removed}")


# ---------------------------------------------------------------------------
#  Универсальная функция upsert тендера в БД
# ---------------------------------------------------------------------------
def _upsert_tender(db, number, subject, price, currency, update_date,
                   stage, customer, region, procurement_type, link, supplier=None):
    """Вставить или обновить тендер. Возвращает True если новый."""
    if not number:
        return False
    if not _is_real_tender_record(number, subject, price, update_date, customer, procurement_type, link):
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
#  Поток 2b: ЭТП через ЕИС RSS (zakupki.gov.ru) — TEK-Torg, РТС, Лот-Онлайн и т.д.
# ---------------------------------------------------------------------------
def _etp_notice_number(t) -> str:
    """Уникальный номер для БД: реестровый номер из ЕИС или стабильный хэш по ссылке."""
    reg = (getattr(t, "reg_number", None) or "").strip()
    if reg:
        return reg
    link = getattr(t, "link", "") or ""
    title = getattr(t, "title", "") or ""
    return "etp_" + hashlib.md5(f"{link}_{title}".encode()).hexdigest()[:24]


def _upsert_from_etp_tender(db, t, platform_label: str) -> bool:
    """Запись тендера из dataclass Tender парсеров *EisParser."""
    num = _etp_notice_number(t)
    subject = (getattr(t, "purchase_object", None) or "").strip() or (
        getattr(t, "title", None) or ""
    ).strip() or "Без названия"
    etp = getattr(t, "etp_name", None) or platform_label
    law = (getattr(t, "law", None) or "").strip()
    proc = f"{law}-ФЗ · {etp}" if law else str(etp)
    upd = getattr(t, "published_at", None) or getattr(t, "bids_deadline", None) or ""
    stage = "Подача заявок"
    bd = getattr(t, "bids_deadline", None)
    if bd:
        stage = f"Срок заявок: {bd}"
    return _upsert_tender(
        db,
        num,
        subject,
        getattr(t, "price", None),
        getattr(t, "currency", None) or "₽",
        str(upd) if upd else None,
        stage,
        getattr(t, "customer", None) or "Не указан",
        None,
        proc,
        getattr(t, "link", "") or "",
        None,
    )


def _sync_etp_eis_rss():
    """
    Сбор объявлений с площадок, заданных в парсерах (RSS zakupki.gov.ru, фильтр по ЭТП).
    Каждый парсер оставляет только «свои» площадки по токенам в коде.
    """
    etp_parsers = (
        ("ТЭК-Торг", tektorg_parser),
        ("Росэлторг", roseltorg_parser),
        ("РТС-Тендер", rts_parser),
        ("ЭТП ГПБ", etpgpb_parser),
        ("ЭТП ЕТС", etp_ets_parser),
        ("Лот-Онлайн", lot_online_parser),
        ("ЗаказРФ", zakazrf_parser),
    )
    keywords = [
        "закупка",
        "поставка",
        "услуги",
        "строительство",
        "it",
        "ремонт",
        "медицина",
        "транспорт",
    ]
    while True:
        for label, p in etp_parsers:
            for kw in keywords:
                try:
                    tenders = p.search(kw, fz44=True, fz223=True, max_items=80)
                    if not tenders:
                        time.sleep(4)
                        continue
                    with SessionLocal() as db:
                        new = 0
                        for t in tenders:
                            if _upsert_from_etp_tender(db, t, label):
                                new += 1
                        db.commit()
                    print(f"[ЭТП ЕИС RSS] {label} «{kw}»: +{new} new / {len(tenders)} parsed")
                except Exception as e:
                    print(f"[ЭТП ЕИС RSS] {label} «{kw}»: {e}")
                    time.sleep(30)
                time.sleep(10)
            time.sleep(5)
        print("[ЭТП ЕИС RSS] Цикл по площадкам завершён, пауза 15 мин")
        time.sleep(900)

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
#  Поток 3b: Tender.Pro — прямой парсинг публичной ленты/карточек
# ---------------------------------------------------------------------------
def _sync_tender_pro_public():
    """Собирает реальные публичные тендеры Tender.Pro без sitemap/robots эвристик."""
    source = SourceConfig(
        source_id="tender_pro_public",
        label="Tender-Pro",
        base_url="https://www.tender.pro",
        patterns=("view_public",),
        max_items=60,
        sleep_s=0.1,
    )
    list_urls = [
        "https://www.tender.pro/",
        "https://www.tender.pro/api/tenders/list?search_type=tenders",
    ]
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    })

    while True:
        seen_links = set()
        parsed = 0
        new_count = 0
        try:
            with SessionLocal() as db:
                for page_url in list_urls:
                    try:
                        response = session.get(page_url, timeout=20)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.text, "html.parser")
                        for anchor in soup.select('a[href*="/api/tender/"][href*="/view_public"]'):
                            href = (anchor.get("href") or "").strip()
                            if not href:
                                continue
                            full_url = urljoin(page_url, href)
                            if full_url in seen_links:
                                continue
                            seen_links.add(full_url)
                            tender = fetch_tender_from_url(source, full_url)
                            parsed += 1
                            if not tender:
                                continue
                            if _upsert_tender(
                                db,
                                tender.get("number"),
                                tender.get("subject"),
                                tender.get("price"),
                                tender.get("currency"),
                                tender.get("update_date"),
                                tender.get("stage"),
                                tender.get("customer"),
                                tender.get("region"),
                                tender.get("procurement_type"),
                                tender.get("link"),
                                tender.get("supplier"),
                            ):
                                new_count += 1
                    except Exception as e:
                        print(f"[Tender.Pro direct] list error {page_url}: {e}")
                db.commit()
            print(f"[Tender.Pro direct] +{new_count} new / {parsed} parsed / {len(seen_links)} links")
        except Exception as e:
            print(f"[Tender.Pro direct] error: {e}")

        time.sleep(900)

# ---------------------------------------------------------------------------
#  Поток 3c: TenderCollector — универсальный сбор с 30 площадок (HTML/RSS)
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
    """Сбор тендеров с множества площадок через TenderCollector (реестр в tender_sources_registry.py)."""
    while True:
        collector = TenderCollector()
        collector.load_sources_from_registry()
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
_purge_invalid_external_tenders()

print("=== Starting 24/7 sync threads ===")
_started_sync_threads = []
threading.Thread(target=_sync_fresh_today, daemon=True, name="sync-fresh").start()
_started_sync_threads.append("Fresh")
threading.Thread(target=_sync_eis, daemon=True, name="sync-eis").start()
_started_sync_threads.append("ЕИС")
threading.Thread(target=_sync_sberbank, daemon=True, name="sync-sberbank").start()
_started_sync_threads.append("Сбербанк-АСТ")
threading.Thread(target=_sync_etp_eis_rss, daemon=True, name="sync-etp-eis-rss").start()
_started_sync_threads.append("ЭТП (ЕИС RSS)")
threading.Thread(target=_sync_tender_pro_public, daemon=True, name="sync-tender-pro").start()
_started_sync_threads.append("Tender.Pro direct")
if ENABLE_EXTERNAL_SYNC:
    threading.Thread(target=_sync_external, daemon=True, name="sync-external").start()
    _started_sync_threads.append("External")
else:
    print("[Startup] External sitemap sync disabled")
if ENABLE_COLLECTOR_SYNC:
    threading.Thread(target=_sync_collector, daemon=True, name="sync-collector").start()
    _started_sync_threads.append("Collector")
else:
    print("[Startup] Collector sync disabled")
threading.Thread(target=_sync_tg_current, daemon=True, name="sync-tg").start()
_started_sync_threads.append("TG")
print(f"=== {len(_started_sync_threads)} sync threads: {', '.join(_started_sync_threads)} ===")

async def get_ai_keywords(description: str, user_id: Optional[int] = None) -> str:
    """Ask GPT-4o to extract search keywords from the company description."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Вы — ассистент по госзакупкам. По описанию компании выделите 3–6 ключевых слов для поиска тендеров по ПРЕДМЕТУ закупки. "
                        "Избегайте общих слов: поставк, обеспеч, услуг без уточнения, просто «ремонт»/«монтаж» без IT — дают мусор. "
                        "Если компания IT/ПО/сайты/интеграции — используйте корни: программ, разработк, сервер, лиценз, интеграц, "
                        "веб, сайт, сопровожд, 1с, crm, сетев, информационн, автоматиз, ПО, видеонаблюд (как ИТ). "
                        "НЕ подставляйте строительный/промышленный «ремонт» и бытовое оборудование, если в описании нет стройки/пищевого производства. "
                        "Верни ТОЛЬКО слова через пробел, без пояснений."
                    ),
                },
                {"role": "user", "content": f"Описание компании: {description}"}
            ],
            temperature=0.1
        )
        if user_id is not None:
            _record_user_openai_tokens(user_id, getattr(response, "usage", None))
        raw = response.choices[0].message.content
        keywords = (raw or "").strip()
        # Clean up any quotes or extra punctuation
        keywords = keywords.replace('"', '').replace("'", "").replace(".", "")
        return keywords
    except Exception as e:
        print(f"Error getting keywords: {e}")
        return ""

async def get_ai_scores(description: str, records: List[ContractRecord], user_id: Optional[int] = None) -> dict:
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
    Оцени релевантность каждого тендера для компании по описанию: "{description}"

    Правила строгости:
    - Сопоставляй с РЕАЛЬНЫМ профилем из описания. Если в описании IT/ПО/сайты/интеграции — закупки другой отрасли
      (продукты питания, мясо, сельхоз, птицефабрики, сырьё, металлургия, металлопрокат, арматура,
      ремонт и ТО промышленного оборудования (мойки высокого давления, станки, дебикаторы, конвейеры) без ИТ в предмете,
      хозтовары, уборка, транспорт грузов без ИТ-систем) почти всегда 0–35.
    - Слово «аппарат» или «аппаратный комплекс» в промышленном/сельхоз/бытовом смысле — НЕ серверы и не ИТ; для IT-профиля такие закупки 0–35, если в предмете нет ПО, сетей, лицензий, интеграций.
    - «Косвенно» (офисная мебель без IT, общие стройработы без автоматизации) — 36–55 только если есть явная связь с ИТ в предмете закупки.
    - 56–75 — предмет явно про ПО, сайты, лицензии, серверы, сети, видеонаблюдение/СКУД как ИТ-проект, SAP/1С, интеграции, ЦОД, техподдержка ПО.
    - 76–100 — почти полное совпадение с профилем (например разработка/внедрение именно того типа услуг, что в описании).

    Для каждого тендера: score (0–100) и reason (одно предложение, с «Подходит, потому что...» или «Не подходит, так как...»).

    Тендеры:
    {items_text}

    Верни один JSON-объект: ключи — строки ID тендеров ТОЧНО как в поле ID выше (без пробелов в начале/конце),
    значения — объекты {{"score": int, "reason": str}}.
    """

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты эксперт по госзакупкам. Оценивай релевантность очень строго: не завышай баллы "
                        "для закупок вне отрасли компании. Возвращай только валидный JSON-объект без пояснений снаружи."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.05,
        )
        if user_id is not None:
            _record_user_openai_tokens(user_id, getattr(response, "usage", None))
        content = response.choices[0].message.content
        scores = json.loads(content or "{}")
        if not isinstance(scores, dict):
            return {}
        out: dict = {}
        for k, v in scores.items():
            nk = str(k).strip()
            if nk and isinstance(v, dict):
                out[nk] = v
        return out
    except Exception as e:
        print(f"Error scoring records: {e}")
        return {}


async def get_ai_scores_batched(
    description: str, records: List[ContractRecord], user_id: Optional[int] = None
) -> dict:
    """Те же оценки, что get_ai_scores, но несколько малых запросов к модели — стабильнее и строже на больших списках."""
    if not records:
        return {}
    merged: dict = {}
    for i in range(0, len(records), AI_SEARCH_SCORE_CHUNK):
        batch = records[i : i + AI_SEARCH_SCORE_CHUNK]
        part = await get_ai_scores(description, batch, user_id=user_id)
        if isinstance(part, dict):
            merged.update(part)
    return merged


async def _score_legacy_data_rows(
    data: List[dict],
    effective_description: str,
    user_id: int,
    db: Session,
    synthetic_id_prefix: str = "",
) -> List[dict]:
    """Присваивает relevance/reason строкам выдачи legacy (один вызов get_ai_scores на батч)."""
    if not data or not effective_description or len(effective_description) <= 10:
        return [dict(r) for r in data if isinstance(r, dict)]

    from dataclasses import dataclass

    @dataclass
    class TempRec:
        number: str
        subject: str
        customer: str
        price: float
        currency: str

    score_input: List[TempRec] = []
    for i, r in enumerate(data):
        if not isinstance(r, dict):
            continue
        raw_num = _legacy_row_number(r)
        num = raw_num or f"{synthetic_id_prefix}row{i}"
        subj = str(r.get("subject") or r.get("title") or r.get("purchase_object") or "")
        cust = str(r.get("customer") or r.get("customer_name") or "")
        p = r.get("price")
        try:
            price_f = float(p) if p is not None else 0.0
        except (TypeError, ValueError):
            price_f = 0.0
        score_input.append(
            TempRec(
                num,
                subj,
                cust,
                price_f,
                str(r.get("currency") or "₽"),
            )
        )

    if not score_input:
        return [dict(r) for r in data if isinstance(r, dict)]

    try:
        scores_data = await get_ai_scores_batched(effective_description, score_input, user_id=user_id)
    except Exception as e:
        print(f"Legacy AI scoring failed: {e}")
        return [dict(r) for r in data if isinstance(r, dict)]

    enriched: List[dict] = []
    for i, r in enumerate(data):
        if not isinstance(r, dict):
            continue
        raw_num = _legacy_row_number(r)
        num = raw_num or f"{synthetic_id_prefix}row{i}"
        rd = dict(r)
        if raw_num:
            rd["number"] = raw_num
        elif not str(rd.get("number") or "").strip():
            rd["number"] = num
        if num in scores_data:
            d = scores_data[num]
            if isinstance(d, dict):
                rd["relevance"] = d.get("score", 0)
                rd["reason"] = d.get("reason", "")
            else:
                rd["relevance"] = None
                rd["reason"] = None
        else:
            rd["relevance"] = None
            rd["reason"] = None
        enriched.append(rd)
        bt = db.query(Tender).filter(Tender.number == num).first()
        if bt and rd.get("relevance") is not None:
            bt.relevance_score = rd["relevance"]
            bt.relevance_reason = rd.get("reason") or ""
    try:
        db.commit()
    except Exception as e:
        print(f"legacy AI score DB update: {e}")
        db.rollback()

    return enriched


async def _legacy_smart_search_scan_and_paginate(
    proxy_params_base: dict,
    effective_description: str,
    user_id: int,
    db: Session,
    display_page: int,
    records_per_page: int,
    generated_query: Optional[str],
) -> Optional[dict]:
    """Сканирует несколько страниц legacy, оценивает ИИ, собирает все релевантные, затем отдаёт срез page.
    Возвращает None, если первая страница legacy недоступна (прокси вернул ошибку) — вызывающий делает fallback на локальную БД.
    """
    loop = asyncio.get_running_loop()
    scan_chunk = max(min(int(records_per_page) or 50, 100), 50)

    all_relevant: List[dict] = []
    seen: set[str] = set()

    for scan_page in range(1, AI_SEARCH_SCAN_MAX_PAGES + 1):
        params = {**proxy_params_base, "page": scan_page, "records_per_page": scan_chunk}
        params = {k: v for k, v in params.items() if v not in (None, "", "none")}
        try:
            legacy_payload = await loop.run_in_executor(None, lambda p=params: _proxy_legacy_search(p))
        except Exception as e:
            print(f"[AI scan] legacy page {scan_page} error: {e}")
            if scan_page == 1:
                return None
            break
        if not isinstance(legacy_payload, dict) or legacy_payload.get("status") != "success":
            if scan_page == 1:
                return None
            break
        data = legacy_payload.get("data")
        if not isinstance(data, list) or not data:
            if scan_page == 1:
                return None
            break

        enriched = await _score_legacy_data_rows(
            data,
            effective_description,
            user_id,
            db,
            synthetic_id_prefix=f"p{scan_page}_",
        )
        for r in enriched:
            if r.get("relevance") is None:
                continue
            if int(r.get("relevance") or 0) < AI_SEARCH_MIN_RELEVANCE:
                continue
            num = _legacy_row_number(r)
            if not num or num in seen:
                continue
            seen.add(num)
            all_relevant.append(r)

        if len(data) < scan_chunk:
            break

    all_relevant.sort(
        key=lambda x: (int(x.get("relevance") or 0), str(x.get("update_date") or "")),
        reverse=True,
    )

    total = len(all_relevant)
    offset = max(0, (max(1, display_page) - 1) * max(1, int(records_per_page) or 50))
    page_size = max(1, int(records_per_page) or 50)
    slice_data = all_relevant[offset : offset + page_size]

    return {
        "status": "success",
        "count": len(slice_data),
        "total": total,
        "data": slice_data,
        "generated_query": generated_query,
    }


async def _enrich_legacy_search_payload_with_ai(
    legacy_payload: dict,
    effective_description: str,
    user_id: int,
    db: Session,
    ai_search: bool,
    is_pro: bool,
) -> dict:
    """Одна страница legacy: relevance/reason + фильтр (без многостраничного скана)."""
    if not isinstance(legacy_payload, dict):
        return legacy_payload
    data = legacy_payload.get("data")
    if not isinstance(data, list) or not data:
        return legacy_payload
    if not (ai_search and is_pro and effective_description and len(effective_description) > 10):
        return legacy_payload

    enriched = await _score_legacy_data_rows(data, effective_description, user_id, db)
    filtered = [
        r
        for r in enriched
        if r.get("relevance") is not None
        and int(r.get("relevance") or 0) >= AI_SEARCH_MIN_RELEVANCE
    ]
    filtered.sort(
        key=lambda x: (int(x.get("relevance") or 0), str(x.get("update_date") or "")),
        reverse=True,
    )

    out = dict(legacy_payload)
    out["data"] = filtered
    out["count"] = len(filtered)
    out["total"] = len(filtered)
    return out


async def get_ai_pitfalls(
    detailed_info: str,
    tender_context: str = "",
    web_context: str = "",
    tender_page_text: str = "",
    user_id: Optional[int] = None,
) -> str:
    """Ask GPT-4o to find contract pitfalls using contract text and optional web context."""
    prepared_info = _prepare_detailed_info_for_pitfalls(detailed_info)
    page_ok = _has_meaningful_tender_page_text(tender_page_text)
    if page_ok:
        if not (prepared_info or "").strip():
            prepared_info = (
                "Парсер в этом запросе обращался к реестру контрактов ЕИС по номеру; для извещений о закупке "
                "данные там часто отсутствуют. Условия закупки смотрите в блоке «Текст со страницы извещения» выше."
            )
        elif "[Ошибка при загрузке данных]" in (detailed_info or "") or "Ошибка при загрузке" in (
            detailed_info or ""
        ):
            prepared_info = (
                f"{prepared_info}\n\n"
                "(Пояснение: ошибки выше относятся к попытке открыть вкладки реестра контрактов по этому номеру; "
                "карточка извещения о закупке в ЕИС — другой раздел. Если в блоке «Текст со страницы извещения» "
                "есть условия, не утверждайте, что «контракт/текст недоступен».)"
            )

    page_body = (tender_page_text or "").strip()
    web_for_prompt = _trim_web_context_for_pitfalls(web_context, page_ok)
    if page_ok:
        rag_note = (
            "Ниже — сжатый веб/RAG только как подсказка; не копируйте общие юридические статьи вместо условий из извещения."
            if (web_for_prompt or "").strip()
            else "Внешний RAG не вернул фрагментов (проверьте SEARCH_GOOGLE_* в окружении); опирайтесь на текст страницы и карточку."
        )
        user_prompt = (
            "=== ПРИОРИТЕТ: текст со страницы закупки (как в браузере по ссылке из карточки, кнопка «Открыть на…») ===\n"
            f"{page_body}\n\n"
            f"Краткие сведения из базы:\n{tender_context or 'Нет структурированных данных'}\n\n"
            f"Дополнительно: парсер ЕИС (реестр контрактов; не путать с извещением):\n{prepared_info}\n\n"
            f"Доп. контекст веб-поиска (второстепенно, не подменяет извещение): {rag_note}\n"
            f"{web_for_prompt or '—'}\n\n"
            "Требование: это не чеклист для поставщика. Не пишите «проверьте», «убедитесь», «важно убедиться» без своего вывода. "
            "Нужно: по тексту извещения сделать оценку (нереалистично / завышено / односторонне / неоднозначно) и объяснить её фактами из блока ПРИОРИТЕТ "
            "(суммы, %, даты, срок исполнения vs сложность предмета закупки)."
        )
    else:
        user_prompt = (
            f"Карточка тендера:\n{tender_context or 'Нет структурированных данных'}\n\n"
            f"Текст контракта / карточки (ЕИС/парсер):\n{prepared_info or 'Нет доступного текста'}\n\n"
            "(Страница закупки по ссылке не загружена или текст пуст — по возможности опишите риски по данным парсера и карточки.)\n\n"
            f"Контекст из веб-поиска и RAG:\n{web_context or 'Веб-поиск не дал полезных данных'}"
        )

    system_grounding_fix: Optional[str] = None
    system_advisory_fix: Optional[str] = None
    if page_ok:
        system_primary = (
            "Вы — эксперт-аналитик по госзакупкам (ФЗ-44, ФЗ-223). Нужен АНАЛИЗ рисков по опубликованному извещению, а не список советов «что проверить».\n"
            "ЗАПРЕЩЕНО: «важно проверить», «убедитесь», «рекомендуется убедиться», абзацы без фактов из извещения, общие чеклисты по контрактам.\n"
            "ОБЯЗАТЕЛЬНЫЙ формат КАЖДОГО пункта (4–6 пунктов, нумерация 1. 2. 3.):\n"
            "— Сначала ВЫВОД/ОЦЕНКА одной фразой (например: «срок исполнения нереалистичен для заявленного объёма», «обеспечение заявки существенно относительно НМЦК», "
            "«формулировка одностороннего отказа увеличивает риск для поставщика»).\n"
            "— Затем ФАКТ из блока «ПРИОРИТЕТ» в сообщении пользователя: число, дата, % или короткая цитата в кавычках из текста извещения.\n"
            "— Затем 1–2 предложения: почему это риск именно здесь — сопоставьте предмет закупки, сложность/масштаб работ, срок, цену, обеспечение (логика «сам проверил текст»).\n"
            "Пример: «Срок 2 месяца на разработку сложной информационной системы выглядит нереалистичным: в извещении срок исполнения … при описании объёма … Риск срыва сроков и санкций (страница извещения).»\n"
            "Веб/RAG в запросе — вторично; не подменяйте ими вывод по извещению.\n"
            "В конце пункта источник: (страница извещения) или (веб), если добавили факт только из веб-блока."
        )
        system_retry = (
            "Ответ отклонён. 5–6 нумерованных пунктов. Только анализ по блоку «ПРИОРИТЕТ»: вывод + факт из текста + почему риск для этого тендера.\n"
            "Без инструкций «проверьте/убедитесь». Без общих лекций про закон.\n"
            "Формат: нумерованный список на русском."
        )
        system_grounding_fix = (
            "Предыдущий ответ был СЛИШКОМ ОБЩИМ. Перепишите целиком.\n"
            "В КАЖДОМ пункте обязательно: либо сумма/процент/дата из блока «ПРИОРИТЕТ», либо короткая прямая цитата из этого блока в кавычках.\n"
            "Не упоминайте статьи КоАП/УК и «веб-источники», если они не нужны для объяснения условий именно этого извещения.\n"
            "5–6 пунктов, нумерация 1. 2. 3."
        )
        system_advisory_fix = (
            "Вы выдали СОВЕТЫ («проверьте», «убедитесь», общие рекомендации) вместо собственного анализа по тексту извещения. Перепишите ВЕСЬ ответ.\n"
            "Каждый пункт = готовый вывод по данным из блока «ПРИОРИТЕТ» (оценка нереалистичности срока, завышенности обеспечения, жёсткости условий и т.д.), "
            "с фактом из извещения и кратким обоснованием. Не повторяйте шаблоны из типовых статей о контрактах.\n"
            "5–6 пунктов, нумерация 1. 2. 3."
        )
    else:
        system_primary = (
            "Вы — эксперт-аналитик по госзакупкам (ФЗ-44, ФЗ-223). Нужен анализ рисков по данным запроса, не чеклист «что проверить».\n"
            "Правила:\n"
            "- Опирайтесь на карточку, парсер ЕИС и веб-фрагменты; не выдумывайте цифры.\n"
            "- Каждый пункт: ваш вывод (оценка) + факт из текста + почему это риск. Без «убедитесь», «важно проверить» без вывода.\n"
            "- 4–6 нумерованных пунктов. Запрещено «рисков не обнаружено».\n"
            "- В конце пункта источник: (карточка), (парсер ЕИС) или (веб)."
        )
        system_retry = (
            "Предыдущий ответ был недопустим. Сейчас ОБЯЗАТЕЛЬНО выведите 5–6 нумерованных пунктов с подводными камнями по данным карточки, парсера и веб-контекста.\n"
            "Запрещено писать, что «рисков нет». Формат: нумерованный список на русском."
        )

    async def _call(system_content: str, temperature: float = 0.25) -> str:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        if user_id is not None:
            _record_user_openai_tokens(user_id, getattr(response, "usage", None))
        raw = response.choices[0].message.content
        return _sanitize_pitfalls_text(raw) or (raw or "").strip()

    try:
        t0 = 0.12 if page_ok else 0.22
        out = await _call(system_primary, t0)
        if _is_vacuous_pitfalls_response(out):
            out = await _call(system_retry, 0.2 if page_ok else 0.25)
        if _is_vacuous_pitfalls_response(out):
            # последняя попытка: чуть выше температура, тот же запрет заглушки
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": system_retry
                        + " Минимум 5 пунктов. Каждый пункт начинается с номера 1. 2. 3.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.38,
            )
            if user_id is not None:
                _record_user_openai_tokens(user_id, getattr(response, "usage", None))
            raw = response.choices[0].message.content
            out = _sanitize_pitfalls_text(raw) or (raw or "").strip()
        if (
            page_ok
            and system_grounding_fix
            and out
            and _pitfalls_response_looks_ungrounded(out, tender_page_text)
        ):
            out = await _call(system_grounding_fix, 0.1)
        if (
            page_ok
            and system_advisory_fix
            and out
            and _pitfalls_response_looks_advisory(out)
        ):
            out = await _call(system_advisory_fix, 0.12)
        return out
    except Exception as e:
        print(f"Error getting pitfalls: {e}")
        return "Произошла ошибка при анализе подводных камней."

# AI functions left above...

@app.get("/api/tenders/{reestr_number}/pitfalls")
async def analyze_pitfalls(
    reestr_number: str,
    link: Optional[str] = Query(
        None,
        max_length=2048,
        description="URL страницы закупки (как у кнопки «Открыть на…»); надёжнее, чем только ссылка из БД.",
    ),
    refresh: bool = Query(
        False,
        description="Если true — не использовать кэш pitfalls в БД, пересчитать заново.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_pro:
        raise HTTPException(status_code=403, detail="Требуется Pro подписка")
    
    try:
        # Кэш в БД ускоряет повторные запросы; refresh=true — всегда новый расчёт (после смены логики/промпта).
        tender = db.query(Tender).filter(Tender.number == reestr_number).first()
        if not refresh and tender and tender.pitfalls:
            cached_pitfalls = _sanitize_pitfalls_text(tender.pitfalls) or tender.pitfalls.strip()
            if cached_pitfalls != tender.pitfalls:
                tender.pitfalls = cached_pitfalls
                db.commit()
            if not _is_placeholder_pitfalls(cached_pitfalls):
                return {"reestr_number": reestr_number, "pitfalls": cached_pitfalls}

        should_use_legacy_pitfalls = LEGACY_SEARCH_ENABLED and (
            tender is None or db.query(Tender).count() < LEGACY_SEARCH_MIN_LOCAL_TOTAL
        )

        pitfalls = None
        tender_context = _build_tender_context_for_pitfalls(tender, reestr_number)
        query_link = (link or "").strip()
        if query_link and not _is_safe_http_url_for_fetch(query_link):
            query_link = ""
        db_link = (tender.link if tender else None) or None
        page_urls = _pitfall_page_url_candidates(
            reestr_number,
            db_link,
            query_link or None,
            tender.procurement_type if tender else None,
        )
        detailed_info, tender_page_text, web_context = await asyncio.gather(
            _fetch_detailed_info_for_pitfalls(reestr_number),
            _fetch_best_tender_page_text_from_urls(page_urls),
            _fetch_google_rag_context_for_pitfalls(tender, reestr_number),
        )

        if (
            tender
            or _has_meaningful_detailed_info(detailed_info)
            or web_context
            or _has_meaningful_tender_page_text(tender_page_text)
        ):
            pitfalls = await get_ai_pitfalls(
                detailed_info=detailed_info,
                tender_context=tender_context,
                web_context=web_context,
                tender_page_text=tender_page_text,
                user_id=current_user.id,
            )
            if _is_placeholder_pitfalls(pitfalls) or _is_vacuous_pitfalls_response(pitfalls):
                pitfalls = None

        if not pitfalls and should_use_legacy_pitfalls:
            try:
                loop = asyncio.get_running_loop()
                pitfalls = await loop.run_in_executor(None, lambda: _proxy_legacy_pitfalls(reestr_number))
            except Exception as legacy_error:
                print(f"Legacy pitfalls fallback error: {legacy_error}")

        if not pitfalls:
            raise HTTPException(
                status_code=503,
                detail="Не удалось загрузить достаточный объём данных по контракту и из внешнего поиска для анализа."
            )
        
        # Save to DB if tender exists
        if tender:
            tender.pitfalls = pitfalls
            db.commit()
            
        return {"reestr_number": reestr_number, "pitfalls": pitfalls}
    except HTTPException:
        raise
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


@app.get("/api/public/telegram-bot")
def api_public_telegram_bot():
    """Ссылка на Telegram-бота из .env (для кнопки на сайте)."""
    return {"url": get_telegram_bot_public_url()}


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
    procurement_kind: Optional[str] = None,
    ai_search: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        local_total_records = db.query(Tender).count()

        # Описание компании: из запроса или из профиля (чтобы умный поиск не терял контекст)
        effective_description = (company_description or "").strip() or (
            (current_user.company_description or "").strip() if current_user else ""
        )
        effective_description = _strip_accidental_trailing_search_line_from_company(effective_description)
        scoring_description = _expand_company_description_for_ai(effective_description)

        if ai_search and not current_user.is_pro:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Умный поиск доступен на тарифе Pro.",
            )
        if ai_search and len(effective_description.strip()) <= 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите описание компании (более 10 символов) в профиле или в поле умного поиска.",
            )

        # 1. Поисковая строка: при ai_search параметр search_string из запроса игнорируется — только ключевые слова из описания компании.
        final_search_string = "" if ai_search else (search_string or "").strip()
        using_ai = False
        if ai_search and current_user.is_pro and effective_description and len(effective_description) > 10:
            final_search_string = await get_ai_keywords(
                scoring_description, user_id=current_user.id
            )
            using_ai = True
            print(f"AI generated keywords (from company description only): {final_search_string}")

        # Legacy: малый локальный каталог ИЛИ умный поиск Pro (иначе при большой локальной БД остаётся «сырой» SQL без скана ИИ).
        use_legacy_for_smart = bool(
            ai_search
            and current_user.is_pro
            and effective_description
            and len(effective_description.strip()) > 10
        )
        should_use_legacy_search = (
            LEGACY_SEARCH_ENABLED
            and (source or "all") != "Tender-Pro"
            and (
                local_total_records < LEGACY_SEARCH_MIN_LOCAL_TOTAL
                or use_legacy_for_smart
            )
        )
        if should_use_legacy_search:
            proxy_params = {
                "search_string": final_search_string,
                "company_description": scoring_description,
                "ai_search": str(ai_search).lower(),
                "price_from": price_from,
                "price_to": price_to,
                "publish_date_from": publish_date_from,
                "publish_date_to": publish_date_to,
                "law_44": str(law_44).lower(),
                "law_223": str(law_223).lower(),
                "page": page,
                "records_per_page": records_per_page,
                "region": region,
                "source": source,
                "sort": sort,
                "stage": stage,
                "hours_ago": hours_ago,
                "hide_micro": str(hide_micro).lower(),
                "procurement_kind": procurement_kind,
            }
            proxy_params = {k: v for k, v in proxy_params.items() if v not in (None, "", "none")}
            try:
                # Умный поиск: скан legacy; если первая страница не пришла — None и fallback на локальную БД с ИИ
                if ai_search and current_user.is_pro and effective_description and len(effective_description) > 10:
                    base_params = {k: v for k, v in proxy_params.items() if k not in ("page", "records_per_page")}
                    smart_legacy = await _legacy_smart_search_scan_and_paginate(
                        base_params,
                        scoring_description,
                        current_user.id,
                        db,
                        page,
                        records_per_page,
                        final_search_string if using_ai else None,
                    )
                    if smart_legacy is not None:
                        return smart_legacy
                    print(
                        "[search] Умный поиск: legacy не вернул данные (токен / сеть / URL). "
                        "Используем локальную базу и скоринг OpenAI."
                    )
                loop = asyncio.get_running_loop()
                legacy_payload = await loop.run_in_executor(None, lambda: _proxy_legacy_search(proxy_params))
                if legacy_payload:
                    legacy_payload = await _enrich_legacy_search_payload_with_ai(
                        legacy_payload,
                        scoring_description,
                        current_user.id,
                        db,
                        ai_search,
                        bool(current_user.is_pro),
                    )
                    return legacy_payload
            except Exception as legacy_error:
                print(f"Legacy search fallback error: {legacy_error}")

        # 2. Live Sync — запускаем в фоне, чтобы поиск не зависал на внешних площадках.
        _trigger_live_sync(
            search_string=final_search_string,
            price_from=price_from,
            price_to=price_to,
            publish_date_from=publish_date_from,
            publish_date_to=publish_date_to,
            page=page,
            records_per_page=records_per_page,
        )

        # 2c-2i. RSS-парсеры (Росэлторг, РТС, GPB, ETS, Lot-Online, ЗаказРФ, ТЭК-Торг)
        # ОТКЛЮЧЕНЫ — RSS ЕИС больше не содержит поле «Электронная площадка».
        # Данные с этих площадок поступают через фоновые потоки sync-sberbank и sync-external.

        external_real_record = and_(
            Tender.procurement_type.ilike("Источник:%"),
            Tender.link.isnot(None),
            Tender.link != "",
        )

        priced_record = and_(
            Tender.price.isnot(None),
            Tender.price > 0,
            Tender.price < 100e9,
        )

        # 3. Query from DB (The requested way)
        query = db.query(Tender)
        
        # Исключаем мусорные тендеры, но разрешаем реальные внешние источники без цены.
        query = query.filter(or_(priced_record, external_real_record))
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
            
        # Фильтр по стадии (stage) — редко нужен с фронта; тематика ищется через search_string
        if stage:
            query = query.filter(Tender.stage.ilike(f"%{stage}%"))

        # Способ закупки (фрагмент из procurement_type: аукцион, конкурс и т.д.)
        if procurement_kind:
            query = query.filter(Tender.procurement_type.ilike(f"%{procurement_kind}%"))
        
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
        if db_total_count == 0 and using_ai:
            print("[AI search] 0 результатов по ключевым словам в локальной БД — широкий fallback «все тендеры» отключён (ломал релевантность).")

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
        show_ai_scores = ai_search and current_user.is_pro and effective_description and len(effective_description) > 10
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
            if current_user.is_pro and effective_description and rec_dict['relevance'] is None:
                # We could score here, but for now let's just use what's in DB
                pass
            processed_records.append(rec_dict)

        # 4. AI Scoring — только при явном ai_search, не при смене фильтров
        if ai_search and current_user.is_pro and effective_description and processed_records:
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
                scores_data = await get_ai_scores_batched(
                    scoring_description, score_input, user_id=current_user.id
                )
                
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
        if ai_search and current_user.is_pro and effective_description:
            # Только тендеры с релевантностью >= порога; без подмены «все подряд» при пустой выдаче
            has_scores = any(r.get('relevance') is not None for r in processed_records)
            if has_scores:
                filtered = [
                    r for r in processed_records
                    if r.get('relevance') is not None and int(r.get('relevance', 0) or 0) >= AI_SEARCH_MIN_RELEVANCE
                ]
                if not filtered:
                    processed_records = []
                else:
                    processed_records = filtered
                    processed_records.sort(
                        key=lambda x: (x.get('relevance') or 0, x.get('update_date') or ''),
                        reverse=True,
                    )
            else:
                processed_records = [r for r in processed_records if r.get('relevance') is None or r.get('relevance', 0) >= 1]
                processed_records.sort(key=lambda x: (x.get('relevance') or 0, x.get('update_date') or ''), reverse=True)

        # При умном поиске total = число отфильтрованных по релевантности на этой странице (иначе «33 из 700000» вводит в заблуждение)
        return_total = len(processed_records) if (
            ai_search and current_user.is_pro and effective_description and len(effective_description) > 10
        ) else db_total_count

        return {
            "status": "success",
            "count": len(processed_records),
            "total": return_total,
            "data": processed_records,
            "generated_query": final_search_string if using_ai or (final_search_string and final_search_string != (search_string or "").strip()) else None
        }
    except Exception as e:
        print(f"Final error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# --- Auth Endpoints ---

@app.post("/api/register/request-code")
def register_request_code(data: RegisterRequestCode, db: Session = Depends(get_db)):
    """Шаг 1: отправить 6-значный код на email (учётная запись ещё не создаётся)."""
    email_lower = data.email.strip().lower()
    if db.query(User).filter(User.email.isnot(None), func.lower(User.email) == email_lower).first():
        raise HTTPException(status_code=400, detail="Этот email уже зарегистрирован")
    code = f"{random.randint(0, 999999):06d}"
    exp = datetime.utcnow() + timedelta(minutes=30)
    pending = db.query(RegistrationEmailPending).filter(
        RegistrationEmailPending.email == email_lower
    ).first()
    if pending:
        pending.code = code
        pending.expires_at = exp
        pending.completion_token = None
        pending.completion_expires_at = None
    else:
        pending = RegistrationEmailPending(email=email_lower, code=code, expires_at=exp)
        db.add(pending)
    db.commit()
    ok = send_verification_code_email(data.email.strip(), "пользователь", code)
    if not ok:
        print(f"[Register] Не удалось отправить письмо на {data.email}")
    return {"email_sent": ok}


@app.post("/api/register/verify-code")
def register_verify_code(body: RegisterVerifyCodeBody, db: Session = Depends(get_db)):
    """Шаг 2: проверить код из письма, выдать completion_token для финального шага."""
    email_lower = body.email.strip().lower()
    pending = db.query(RegistrationEmailPending).filter(
        RegistrationEmailPending.email == email_lower
    ).first()
    if not pending:
        raise HTTPException(status_code=400, detail="Сначала запросите код на почту")
    now = datetime.utcnow()
    if (
        pending.completion_token
        and pending.completion_expires_at
        and pending.completion_expires_at >= now
    ):
        return {"completion_token": pending.completion_token}
    raw = (body.code or "").strip()
    if len(raw) != 6 or not raw.isdigit():
        raise HTTPException(status_code=400, detail="Введите 6-значный код из письма")
    if pending.expires_at < now:
        raise HTTPException(status_code=400, detail="Код истёк — запросите новый")
    if not pending.code or pending.code != raw:
        raise HTTPException(status_code=400, detail="Неверный код")
    token = secrets.token_urlsafe(32)
    pending.completion_token = token
    pending.completion_expires_at = now + timedelta(hours=1)
    pending.code = ""
    db.commit()
    return {"completion_token": token}


@app.post("/register", response_model=Token)
def register_complete(body: RegisterComplete, db: Session = Depends(get_db)):
    """Шаг 3: создать пользователя после подтверждения email (completion_token из verify-code)."""
    pending = db.query(RegistrationEmailPending).filter(
        RegistrationEmailPending.completion_token == body.completion_token.strip()
    ).first()
    if (
        not pending
        or not pending.completion_expires_at
        or pending.completion_expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail="Сессия регистрации недействительна или истекла — начните с отправки кода на почту",
        )
    email_lower = pending.email.lower()
    if db.query(User).filter(User.email.isnot(None), func.lower(User.email) == email_lower).first():
        db.delete(pending)
        db.commit()
        raise HTTPException(status_code=400, detail="Этот email уже зарегистрирован")
    uname = body.username.strip()
    if db.query(User).filter(User.username == uname).first():
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже зарегистрирован")
    hashed_password = get_password_hash(body.password)
    new_user = User(
        username=uname,
        hashed_password=hashed_password,
        is_admin=False,
        email=email_lower,
        email_verified=True,
        email_verification_token=None,
    )
    db.add(new_user)
    db.delete(pending)
    db.commit()
    db.refresh(new_user)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "email_sent": True}

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
async def get_telegram_link(
    regenerate: bool = Query(False, description="Новый 8-значный код для повторной привязки в боте"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    need_new = regenerate or not current_user.telegram_connect_code
    if need_new:
        code = None
        for _ in range(32):
            cand = "".join(random.choices(string.digits, k=8))
            clash = (
                db.query(User)
                .filter(User.telegram_connect_code == cand, User.id != current_user.id)
                .first()
            )
            if not clash:
                code = cand
                break
        if not code:
            code = "".join(random.choices(string.digits, k=8))
        current_user.telegram_connect_code = code
        db.commit()

    code = current_user.telegram_connect_code
    bot_name = _telegram_bot_username_for_deeplink()
    link = f"https://t.me/{bot_name}?start={code}"
    
    return {
        "code": code,
        "link": link
    }

# --- Admin Endpoints ---

@app.get("/admin/stats", dependencies=[Depends(get_current_admin)])
def admin_stats(db: Session = Depends(get_db)):
    tokens_sum = db.query(func.coalesce(func.sum(User.openai_tokens_total), 0)).scalar()
    return {
        "users": db.query(User).count(),
        "admins": db.query(User).filter(User.is_admin == True).count(),
        "tenders": db.query(Tender).count(),
        "promocodes": db.query(PromoCode).count(),
        "email_verified": db.query(User).filter(User.email_verified == True).count(),
        "openai_tokens_total": int(tokens_sum or 0),
    }


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
        "openai_tokens_total": int(getattr(u, "openai_tokens_total", None) or 0),
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
    promos = db.query(PromoCode).order_by(PromoCode.id.desc()).all()
    return [
        {
            "id": p.id,
            "code": p.code,
            "is_active": p.is_active,
            "description": p.description or "",
        }
        for p in promos
    ]


@app.patch("/admin/promocodes/{promo_id}", dependencies=[Depends(get_current_admin)])
def patch_promo(promo_id: int, body: PromoPatch, db: Session = Depends(get_db)):
    p = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    if body.is_active is not None:
        p.is_active = body.is_active
    db.commit()
    return {"status": "ok", "id": p.id, "is_active": p.is_active}


@app.delete("/admin/promocodes/{promo_id}", dependencies=[Depends(get_current_admin)])
def delete_promo(promo_id: int, db: Session = Depends(get_db)):
    p = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    db.delete(p)
    db.commit()
    return {"status": "deleted"}

# SPA Catch-all for React Router
@app.get("/app")
@app.get("/profile")
@app.get("/auth")
@app.get("/admin")
@app.get("/admin/")
@app.get("/verify-email")
@app.get("/verify-email-code")
async def serve_spa():
    # Important: index.html must not be cached, otherwise users can get a stale
    # HTML that points to outdated JS bundles (and won't see new UI like cookie banner).
    return FileResponse(
        "static/index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )

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
    return FileResponse(
        "static/index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
