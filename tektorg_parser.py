#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TEK-Torg parser (44-FZ / 223-FZ) via zakupki.gov.ru RSS (extended search).

Pipeline:
1) Fetch EIS RSS for query (44/223).
2) Parse RSS items.
3) Keep only notices where ETP field/text matches TEK-Torg tokens.
4) Normalize key fields (object name, price, deadline).
5) Export JSON/CSV.

This follows the same EIS RSS approach as other ETP parsers in the project.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote_plus

import requests
import xml.etree.ElementTree as ET


# ----------------------------
# Config
# ----------------------------

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

EIS_RSS_URL = "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html"

TEKTORG_TOKENS = (
    "ТЭК-Торг",
    "ТЭК-ТОРГ",
    "TEK-Torg",
    "TEK-TORG",
    "tektorg.ru",
    "www.tektorg.ru",
    "АО «ТЭК-Торг»",
    "АО \"ТЭК-Торг\"",
    "ЭТП ТЭК-Торг",
)


# ----------------------------
# Data model
# ----------------------------

@dataclass
class Tender:
    reg_number: str
    law: str  # "44" or "223" (best-effort)
    title: str
    link: str
    published_at: Optional[str] = None  # ISO8601

    etp_name: Optional[str] = None
    purchase_object: Optional[str] = None
    customer: Optional[str] = None

    price: Optional[float] = None
    currency: Optional[str] = None

    bids_deadline: Optional[str] = None  # ISO8601 or raw string if parsing fails

    raw_fields: Dict[str, str] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


# ----------------------------
# HTTP client (retry)
# ----------------------------

class HttpClient:
    def __init__(self, user_agent: str = DEFAULT_UA, timeout_s: int = 25, max_retries: int = 4):
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
            "Connection": "keep-alive",
        })

    def get_text(self, url: str, *, params: Optional[dict] = None) -> str:
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.s.get(url, params=params, timeout=self.timeout_s)
                r.raise_for_status()
                r.encoding = r.encoding or "utf-8"
                return r.text
            except Exception as e:
                last_err = e
                time.sleep(min(2 ** attempt, 12) + 0.1 * attempt)
        raise RuntimeError(f"HTTP GET failed: {url}") from last_err


# ----------------------------
# Parsing helpers
# ----------------------------

_TAG_RE = re.compile(r"<[^>]+>", re.S)
_BR_RE = re.compile(r"<br\s*/?>", re.I)

def strip_html(html: str) -> str:
    if not html:
        return ""
    html = unescape(html)
    html = _BR_RE.sub("\n", html)
    html = _TAG_RE.sub("", html)
    html = html.replace("\xa0", " ")
    return "\n".join(line.strip() for line in html.splitlines() if line.strip())

def parse_kv_lines(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                k, v = parts
                k = k.strip()
                v = v.strip()
                if k and v and k not in out:
                    out[k] = v
    return out

def extract_reg_number(link: str, title: str, desc_text: str) -> Optional[str]:
    m = re.search(r"regNumber=(\d+)", link)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{19}|\d{11})\b", title) or re.search(r"\b(\d{19}|\d{11})\b", desc_text)
    return m.group(1) if m else None

def guess_law(link: str, reg_number: str) -> str:
    if "notice223" in link or (reg_number and len(reg_number) == 11):
        return "223"
    return "44"

def contains_any(hay: str, tokens: Tuple[str, ...]) -> bool:
    h = (hay or "").lower()
    return any(t.lower() in h for t in tokens)

_PRICE_RE = re.compile(r"([\d\s]+[.,]?\d*)\s*([A-ZА-Я]{3})?")

def parse_price(value: str) -> Tuple[Optional[float], Optional[str]]:
    if not value:
        return None, None
    v = value.replace("руб.", "RUB").replace("руб", "RUB")
    m = _PRICE_RE.search(v)
    if not m:
        return None, None
    num_raw = m.group(1).replace(" ", "").replace(",", ".")
    cur = m.group(2)
    try:
        return float(num_raw), cur
    except Exception:
        return None, cur

def normalize_ru_datetime(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    raw = s.strip()
    raw2 = re.sub(r"\(.*?\)", "", raw).strip()
    m = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})\b", raw2)
    if not m:
        return raw  # keep as-is
    dd, mm, yyyy, HH, MM = m.groups()
    try:
        dt = datetime(int(yyyy), int(mm), int(dd), int(HH), int(MM))
        return dt.isoformat()
    except Exception:
        return raw


# ----------------------------
# Parser
# ----------------------------

class TekTorgEisParser:
    def __init__(self, http: Optional[HttpClient] = None, tokens: Tuple[str, ...] = TEKTORG_TOKENS):
        self.http = http or HttpClient()
        self.tokens = tokens

    def build_rss_url(
        self,
        query: str,
        *,
        fz44: bool = True,
        fz223: bool = True,
        morphology: bool = True,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> str:
        params = {
            "searchString": query,
            "morphology": "on" if morphology else "off",
        }
        if fz44:
            params["fz44"] = "on"
        if fz223:
            params["fz223"] = "on"
        if extra_params:
            params.update(extra_params)

        return f"{EIS_RSS_URL}?{urlencode(params, quote_via=quote_plus)}"

    def fetch(self, rss_url: str) -> str:
        return self.http.get_text(rss_url)

    def parse(self, rss_xml: str) -> List[Tender]:
        try:
            root = ET.fromstring(rss_xml)
        except ET.ParseError:
            return []

        items = root.findall(".//item")
        out: List[Tender] = []

        for it in items:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            desc_raw = it.findtext("description") or ""
            desc_txt = strip_html(desc_raw)
            fields = parse_kv_lines(desc_txt)

            reg = extract_reg_number(link, title, desc_txt)
            if not reg:
                continue

            law = guess_law(link, reg)

            pub_iso = None
            if pub:
                try:
                    pub_iso = parsedate_to_datetime(pub).astimezone().isoformat()
                except Exception:
                    pub_iso = None

            etp = (
                fields.get("Наименование электронной площадки в информационно-телекоммуникационной сети «Интернет»")
                or fields.get("Электронная площадка")
                or fields.get("Наименование электронной площадки")
            )

            hay = "\n".join([title, link, desc_txt, etp or ""])
            if not contains_any(hay, self.tokens):
                continue

            t = Tender(
                reg_number=reg,
                law=law,
                title=title,
                link=link,
                published_at=pub_iso,
                etp_name=etp,
                raw_fields=fields,
                debug={"rss_hint": link},
            )

            t.purchase_object = (
                fields.get("Наименование объекта закупки")
                or fields.get("Наименование закупки")
                or None
            )

            price_label = (
                fields.get("Начальная (максимальная) цена контракта")
                or fields.get("Начальная цена договора")
                or fields.get("Начальная (максимальная) цена договора")
                or fields.get("Цена")
            )
            t.price, t.currency = parse_price(price_label or "")

            deadline = (
                fields.get("Окончание подачи заявок")
                or fields.get("Дата и время окончания подачи заявок")
                or fields.get("Окончание подачи предложений")
            )
            t.bids_deadline = normalize_ru_datetime(deadline)

            out.append(t)

        return out

    def search(
        self,
        query: str,
        *,
        fz44: bool = True,
        fz223: bool = True,
        max_items: int = 100,
        extra_rss_params: Optional[Dict[str, str]] = None,
    ) -> List[Tender]:
        rss_url = self.build_rss_url(query, fz44=fz44, fz223=fz223, extra_params=extra_rss_params)
        try:
            rss_xml = self.fetch(rss_url)
            tenders = self.parse(rss_xml)
            return tenders[:max_items]
        except Exception as e:
            print(f"TEK-Torg parser error: {e}")
            return []


# ----------------------------
# Export
# ----------------------------

def save_json(path: str, tenders: List[Tender]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(t) for t in tenders], f, ensure_ascii=False, indent=2)

def save_csv(path: str, tenders: List[Tender]) -> None:
    headers = [
        "reg_number", "law", "title", "link", "published_at",
        "purchase_object", "customer", "price", "currency", "bids_deadline", "etp_name",
        "raw_fields", "debug"
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for t in tenders:
            row = asdict(t)
            row["raw_fields"] = json.dumps(t.raw_fields, ensure_ascii=False)
            row["debug"] = json.dumps(t.debug, ensure_ascii=False)
            w.writerow({k: row.get(k) for k in headers})


# ----------------------------
# CLI
# ----------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="TEK-Torg parser via zakupki.gov.ru RSS")
    ap.add_argument("--query", required=True, help="Search query (e.g. 'строительные работы')")
    ap.add_argument("--max", type=int, default=100, help="Max items (default: 100)")
    ap.add_argument("--out", default="tektorg_tenders.json", help="Output file (.json or .csv)")
    ap.add_argument("--only44", action="store_true", help="Only 44-FZ")
    ap.add_argument("--only223", action="store_true", help="Only 223-FZ")
    ap.add_argument("--publishDateFrom", default=None, help="Optional: dd.mm.yyyy (EIS RSS param)")
    ap.add_argument("--publishDateTo", default=None, help="Optional: dd.mm.yyyy (EIS RSS param)")
    ap.add_argument("--ua", default=DEFAULT_UA, help="Custom User-Agent")
    ns = ap.parse_args()

    fz44 = True
    fz223 = True
    if ns.only44:
        fz223 = False
    if ns.only223:
        fz44 = False

    extra = {}
    if ns.publishDateFrom:
        extra["publishDateFrom"] = ns.publishDateFrom
    if ns.publishDateTo:
        extra["publishDateTo"] = ns.publishDateTo

    parser = TekTorgEisParser(http=HttpClient(user_agent=ns.ua))
    tenders = parser.search(
        ns.query,
        fz44=fz44,
        fz223=fz223,
        max_items=ns.max,
        extra_rss_params=extra or None,
    )

    if ns.out.lower().endswith(".csv"):
        save_csv(ns.out, tenders)
    else:
        save_json(ns.out, tenders)

    print(f"OK: {len(tenders)} items -> {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
