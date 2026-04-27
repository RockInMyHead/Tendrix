#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sberbank-AST parser — парсинг тендеров напрямую с sberbank-ast.ru.

Обходит JS challenge (BotMitigation), затем использует ElasticSearch API
(POST /SearchQuery.aspx?name=Main) для получения структурированных данных.

Основные возможности:
- Автоматическое решение JS challenge
- Поиск по ключевым словам
- Фильтрация по цене, дате, этапу, региону
- Пагинация
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SberTender:
    """Тендер с площадки Сбербанк-АСТ."""
    reg_number: str
    title: str
    link: str
    price: Optional[float] = None
    currency: Optional[str] = None
    customer: Optional[str] = None
    region: Optional[str] = None
    published_at: Optional[str] = None
    deadline: Optional[str] = None
    stage: Optional[str] = None
    purchase_type: Optional[str] = None
    eis_link: Optional[str] = None
    source: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# JS Challenge solver
# ---------------------------------------------------------------------------

def _solve_challenge(challenge: int) -> str:
    """
    Порт JS-функции test(var1) со страницы Сбербанк-АСТ.
    
    Алгоритм:
    1. Разбить Challenge на массив цифр
    2. Реверсировать → получить LastDig
    3. Отсортировать → получить minDig
    4. Вычислить subvar1, subvar2, my_pow, x, y, answer
    5. Результат — строковая конкатенация answer + subvar2
    """
    digits = list(str(challenge))
    digits_rev = list(reversed(digits))
    last_dig = digits_rev[0]
    digits_sorted = sorted(digits_rev)
    min_dig = digits_sorted[0]

    subvar1 = 2 * int(digits_sorted[2]) + int(digits_sorted[1])
    # В JS: (2 * number) + string = строковая конкатенация
    subvar2_str = str(2 * int(digits_sorted[2])) + digits_sorted[1]

    my_pow = math.pow(int(digits_sorted[0]) + 2, int(digits_sorted[1]))

    x = challenge * 3 + subvar1
    y = math.cos(math.pi * int(subvar2_str))
    answer = x * y - my_pow + int(min_dig) - int(last_dig)

    # В JS: number + string = строковая конкатенация
    return str(int(round(answer))) + subvar2_str


def _bypass_challenge(session: requests.Session, page_url: str) -> bool:
    """
    Обойти JS anti-bot challenge на сайте Сбербанк-АСТ.
    
    Returns True если challenge пройден.
    """
    r = session.get(page_url, timeout=20)
    
    ch_match = re.search(r"Challenge=(\d+);", r.text)
    chid_match = re.search(r"ChallengeId=(\d+);", r.text)

    if not ch_match or not chid_match:
        # Нет challenge — возможно уже есть валидная cookie
        if "Challenge=" not in r.text and len(r.text) > 5000:
            return True
        logger.warning("Challenge pattern not found on page")
        return False

    challenge = int(ch_match.group(1))
    challenge_id = int(chid_match.group(1))
    answer = _solve_challenge(challenge)

    r2 = session.post(
        page_url,
        headers={
            "X-AA-Challenge-ID": str(challenge_id),
            "X-AA-Challenge-Result": answer,
            "X-AA-Challenge": str(challenge),
            "Content-Type": "text/plain",
        },
        timeout=20,
    )

    cookie_val = r2.headers.get("X-AA-Cookie-Value")
    if not cookie_val:
        logger.error("Challenge solve failed — no cookie returned")
        return False

    return True


# ---------------------------------------------------------------------------
# XML builder
# ---------------------------------------------------------------------------

def _build_xml(
    query: str = "",
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    stage: Optional[str] = None,
    region: Optional[str] = None,
    page_size: int = 50,
    page_from: int = 0,
    search_type: str = "phrase_prefix",
    min_match: str = "100%",
) -> str:
    """Сформировать XML-запрос для ElasticSearch API Сбербанк-АСТ."""

    price_min = str(price_from) if price_from is not None else ""
    price_max = str(price_to) if price_to is not None else ""
    pub_min = date_from or ""
    pub_max = date_to or ""
    stage_val = stage or ""
    region_val = region or ""

    return (
        f"<elasticrequest>"
        f"<personid>0</personid>"
        f"<buid>0</buid>"
        f"<filters>"
        f"<mainSearchBar>"
        f"<value>{query}</value>"
        f"<type>{search_type}</type>"
        f"<minimum_should_match>{min_match}</minimum_should_match>"
        f"</mainSearchBar>"
        f"<purchAmount><minvalue>{price_min}</minvalue><maxvalue>{price_max}</maxvalue></purchAmount>"
        f"<PublicDate><minvalue>{pub_min}</minvalue><maxvalue>{pub_max}</maxvalue></PublicDate>"
        f"<PurchaseStageTerm><value>{stage_val}</value><visiblepart></visiblepart></PurchaseStageTerm>"
        f"<SourceTerm><value></value><visiblepart></visiblepart></SourceTerm>"
        f"<RegionNameTerm><value>{region_val}</value><visiblepart></visiblepart></RegionNameTerm>"
        f"<RequestStartDate><minvalue></minvalue><maxvalue></maxvalue></RequestStartDate>"
        f"<RequestDate><minvalue></minvalue><maxvalue></maxvalue></RequestDate>"
        f"<AuctionBeginDate><minvalue></minvalue><maxvalue></maxvalue></AuctionBeginDate>"
        f"<okdp2MultiMatch><value></value></okdp2MultiMatch>"
        f"<okdp2tree><value></value><productField></productField><branchField></branchField></okdp2tree>"
        f"<classifier><visiblepart></visiblepart></classifier>"
        f"<orgCondition><value></value></orgCondition>"
        f"<orgDictionary><value></value></orgDictionary>"
        f"<organizator><visiblepart></visiblepart></organizator>"
        f"<CustomerCondition><value></value></CustomerCondition>"
        f"<CustomerDictionary><value></value></CustomerDictionary>"
        f"<customer><visiblepart></visiblepart></customer>"
        f"<PurchaseTypeNameTerm><value></value><visiblepart></visiblepart></PurchaseTypeNameTerm>"
        f"<BranchNameTerm><value></value><visiblepart></visiblepart></BranchNameTerm>"
        f"<isSharedTerm><value></value><visiblepart></visiblepart></isSharedTerm>"
        f"<notificationFeatures><value></value><visiblepart></visiblepart></notificationFeatures>"
        f"<statistic><totalProc></totalProc><TotalSum></TotalSum><DistinctOrgs></DistinctOrgs></statistic>"
        f"</filters>"
        f"<sort><value>default</value><direction></direction></sort>"
        f"<aggregations><empty><filterType>filter_aggregation</filterType><field></field></empty></aggregations>"
        f"<size>{page_size}</size>"
        f"<from>{page_from}</from>"
        f"</elasticrequest>"
    )


# ---------------------------------------------------------------------------
# XML response parser
# ---------------------------------------------------------------------------

def _parse_xml_value(xml_str: str, tag: str) -> Optional[str]:
    """Извлечь значение тега из XML-строки (простой regex)."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml_str, re.S)
    return m.group(1).strip() if m else None


def _parse_price_value(raw: Optional[str]) -> Optional[float]:
    """Парсинг числовой строки цены."""
    if not raw:
        return None
    cleaned = raw.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_hits(table_xml: str) -> List[SberTender]:
    """Парсинг XML-ответа ElasticSearch в список SberTender."""
    tenders: List[SberTender] = []

    # Разбиваем по hit-блокам (содержат _id и _source)
    # Извлекаем _id (purchaseId) отдельно, т.к. он вне _source
    hits_raw = re.findall(r"<_id>(.*?)</_id>\s*<_score>.*?</(_score>)\s*<_source>(.*?)</_source>", table_xml, re.S)
    if not hits_raw:
        # Fallback: только по _source
        hits_raw = [(None, None, src) for src in re.findall(r"<_source>(.*?)</_source>", table_xml, re.S)]

    for hit in hits_raw:
        if len(hit) == 3:
            purchase_id = hit[0] or ""
            src = hit[2]
        else:
            purchase_id = ""
            src = hit
        bid_name = _parse_xml_value(src, "BidName") or ""
        customer = _parse_xml_value(src, "CustomerFullName") or _parse_xml_value(src, "OrgFullName") or ""
        customer_nick = _parse_xml_value(src, "CustomerNickName") or _parse_xml_value(src, "OrgNickName") or ""
        region = _parse_xml_value(src, "RegionName") or ""
        price_raw = _parse_xml_value(src, "purchAmount") or _parse_xml_value(src, "purchAmountRUB")
        currency = _parse_xml_value(src, "purchCurrency") or "RUB"
        pub_date = _parse_xml_value(src, "PublicDate") or ""
        request_date = _parse_xml_value(src, "RequestDate") or ""
        stage = _parse_xml_value(src, "PurchaseStageTerm") or ""

        # Фильтрация placeholder-дат Сбербанк-АСТ (01.01.2079 и т.п.)
        # Если deadline — placeholder (год >= 2050), заменяем на published_at
        if request_date:
            try:
                year_str = request_date.split(".")[-1].split()[0] if "." in request_date else ""
                if year_str and int(year_str) >= 2050:
                    request_date = pub_date  # Заменяем на дату публикации
            except (ValueError, IndexError):
                pass
        purchase_type = _parse_xml_value(src, "PurchaseTypeNameTerm") or _parse_xml_value(src, "PurchaseTypeName") or ""
        eis_href = _parse_xml_value(src, "OOSHref") or ""
        source_term = _parse_xml_value(src, "SourceTerm") or ""
        create_href = _parse_xml_value(src, "CreateRequestHrefTerm") or ""

        # Реестровый номер из ЕИС-ссылки
        reg_number = ""
        m = re.search(r"regNumber=(\d+)", eis_href)
        if m:
            reg_number = m.group(1)
        elif purchase_id:
            reg_number = f"SBER-{purchase_id}"

        if not reg_number and not bid_name:
            continue

        price = _parse_price_value(price_raw)

        # Ссылка на Сбербанк-АСТ
        link = ""
        if purchase_id:
            link = f"https://www.sberbank-ast.ru/ViewPurchase.aspx?purchid={purchase_id}"
        elif create_href:
            link = create_href

        tender = SberTender(
            reg_number=reg_number or f"SBER-{hash(bid_name) % 10**10}",
            title=bid_name,
            link=link,
            price=price,
            currency=currency if currency != "RUB" else "₽",
            customer=customer_nick or customer,
            region=region,
            published_at=pub_date,
            deadline=request_date,
            stage=stage,
            purchase_type=purchase_type,
            eis_link=eis_href,
            source=source_term,
            raw={},
        )
        tenders.append(tender)

    return tenders


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------

class SberbankAstParser:
    """Парсер тендеров с площадки Сбербанк-АСТ (sberbank-ast.ru)."""

    BASE_URL = "https://www.sberbank-ast.ru"
    PAGE_URL = f"{BASE_URL}/purchaseList.aspx"
    SEARCH_URL = f"{BASE_URL}/SearchQuery.aspx?name=Main"

    def __init__(
        self,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        })
        self._challenge_solved = False

    def _ensure_session(self) -> bool:
        """Убедиться, что сессия прошла JS challenge."""
        if self._challenge_solved:
            return True

        for attempt in range(self.max_retries):
            try:
                if _bypass_challenge(self.session, self.PAGE_URL):
                    # Проверяем — загружается ли реальная страница
                    r = self.session.get(self.PAGE_URL, timeout=self.timeout)
                    if "Challenge=" not in r.text and len(r.text) > 5000:
                        self._challenge_solved = True
                        logger.info("Sberbank-AST challenge solved (attempt %d)", attempt + 1)
                        return True
            except Exception as e:
                logger.warning("Challenge attempt %d failed: %s", attempt + 1, e)

            time.sleep(2 ** attempt)

        logger.error("Failed to solve Sberbank-AST challenge after %d attempts", self.max_retries)
        return False

    def search(
        self,
        query: str = "",
        *,
        max_items: int = 50,
        price_from: Optional[float] = None,
        price_to: Optional[float] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        stage: Optional[str] = None,
        region: Optional[str] = None,
        page: int = 0,
    ) -> List[SberTender]:
        """
        Поиск тендеров на Сбербанк-АСТ.

        Args:
            query: Поисковый запрос (ключевые слова)
            max_items: Максимальное количество результатов (макс. 100)
            price_from: Минимальная цена
            price_to: Максимальная цена
            date_from: Дата публикации от (дд.мм.гггг)
            date_to: Дата публикации до (дд.мм.гггг)
            stage: Этап проведения
            region: Регион
            page: Номер страницы (0-based)

        Returns:
            Список SberTender
        """
        if not self._ensure_session():
            logger.error("Cannot search — session not established")
            return []

        page_size = min(max_items, 100)
        page_from = page * page_size

        xml_data = _build_xml(
            query=query,
            price_from=price_from,
            price_to=price_to,
            date_from=date_from,
            date_to=date_to,
            stage=stage,
            region=region,
            page_size=page_size,
            page_from=page_from,
        )

        data = {
            "xmlData": xml_data,
            "orgId": "0",
            "targetPageCode": "ESPurchaseList",
            "PID": "0",
        }

        for attempt in range(self.max_retries):
            try:
                r = self.session.post(
                    self.SEARCH_URL,
                    data=data,
                    timeout=self.timeout,
                )
                r.raise_for_status()

                resp = json.loads(r.text)
                if resp.get("result") != "success":
                    logger.warning("API returned non-success: %s", resp.get("result"))
                    # Возможно сессия протухла
                    self._challenge_solved = False
                    if self._ensure_session():
                        continue
                    return []

                inner = resp.get("data", "")
                if isinstance(inner, str):
                    inner = json.loads(inner)

                table_xml = inner.get("tableXml", "")
                if not table_xml:
                    logger.info("Empty tableXml for query '%s'", query)
                    return []

                tenders = _parse_hits(table_xml)
                logger.info(
                    "Sberbank-AST: query='%s', got %d tenders", query, len(tenders)
                )
                return tenders

            except json.JSONDecodeError as e:
                logger.warning("JSON decode error (attempt %d): %s", attempt + 1, e)
                # Возможно challenge протух
                self._challenge_solved = False
                if not self._ensure_session():
                    return []
            except requests.RequestException as e:
                logger.warning("Request error (attempt %d): %s", attempt + 1, e)
                time.sleep(2 ** attempt)

        return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(description="Sberbank-AST tender parser")
    ap.add_argument("query", nargs="?", default="", help="Search query")
    ap.add_argument("--max", type=int, default=20, help="Max items")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    parser = SberbankAstParser()
    results = parser.search(args.query or "закупка", max_items=args.max)

    if not results:
        print("No results found.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import dataclasses
        print(json.dumps(
            [dataclasses.asdict(t) for t in results],
            ensure_ascii=False,
            indent=2,
        ))
    else:
        for i, t in enumerate(results, 1):
            print(f"\n{'='*60}")
            print(f"  #{i}  {t.reg_number}")
            print(f"  {t.title}")
            print(f"  Цена: {t.price:,.2f} {t.currency}" if t.price else "  Цена: —")
            print(f"  Заказчик: {t.customer}")
            print(f"  Регион: {t.region}")
            print(f"  Этап: {t.stage}")
            print(f"  Опубликовано: {t.published_at}")
            print(f"  Дедлайн: {t.deadline}")
            print(f"  Тип: {t.purchase_type}")
            print(f"  Ссылка: {t.link}")
            if t.eis_link:
                print(f"  ЕИС: {t.eis_link}")
