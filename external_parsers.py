#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Best-effort external portal parsers (no credentials, HTML + sitemap based).

This module discovers tender URLs via robots.txt/sitemap.xml and attempts
basic extraction from tender pages. It is designed to be config-driven
(external_sources.json).
"""

from __future__ import annotations

import json
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


@dataclass
class SourceConfig:
    source_id: str
    label: str
    base_url: str
    enabled: bool = True
    patterns: Tuple[str, ...] = ()
    max_items: int = 50
    sleep_s: float = 1.0


# ----------------------------
# Config
# ----------------------------

def load_sources(path: str) -> List[SourceConfig]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out: List[SourceConfig] = []
    for item in raw:
        out.append(
            SourceConfig(
                source_id=item["id"],
                label=item.get("label", item["id"]),
                base_url=item["base_url"],
                enabled=bool(item.get("enabled", True)),
                patterns=tuple(item.get("patterns", [])),
                max_items=int(item.get("max_items", 50)),
                sleep_s=float(item.get("sleep_s", 1.0)),
            )
        )
    return out


# ----------------------------
# Sitemap discovery
# ----------------------------

_SITEMAP_RE = re.compile(r"^sitemap:\s*(.+)$", re.I)
_BLOCK_PATTERNS = (
    "captcha",
    "g-recaptcha",
    "hcaptcha",
    "cloudflare",
    "access denied",
    "запрос отклонен",
    "доступ запрещен",
    "подтвердите, что вы не робот",
    "нажмите, чтобы продолжить",
)


def _raw_get_text(url: str, timeout_s: int = 25) -> Optional[str]:
    try:
        r = requests.get(url, timeout=timeout_s, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TenderBot/1.0)",
            "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        })
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        return r.text
    except Exception as e:
        logger.warning("Fetch failed: %s (%s)", url, e)
        return None


def _get_text(url: str, timeout_s: int = 25) -> Optional[str]:
    # Wrapper to allow tests to inject raw text without bypassing block detection.
    text = _raw_get_text(url, timeout_s=timeout_s)
    if not text:
        return None
    low = text.lower()
    if any(pat in low for pat in _BLOCK_PATTERNS):
        logger.warning("Blocked by anti-bot on %s", url)
        return None
    return text


def discover_sitemaps(base_url: str) -> List[str]:
    sitemaps: List[str] = []
    robots_url = urljoin(base_url.rstrip("/") + "/", "robots.txt")
    robots_txt = _get_text(robots_url)
    if robots_txt:
        for line in robots_txt.splitlines():
            m = _SITEMAP_RE.match(line.strip())
            if m:
                sitemaps.append(m.group(1).strip())

    # Fallback guesses
    if not sitemaps:
        sitemaps.append(urljoin(base_url.rstrip("/") + "/", "sitemap.xml"))
        sitemaps.append(urljoin(base_url.rstrip("/") + "/", "sitemap_index.xml"))

    # Dedup preserve order
    seen = set()
    out = []
    for sm in sitemaps:
        if sm not in seen:
            seen.add(sm)
            out.append(sm)
    return out


# ----------------------------
# Sitemap parsing
# ----------------------------

_URL_TAG_RE = re.compile(r"<loc>(.*?)</loc>", re.I | re.S)


def parse_sitemap_urls(xml: str) -> List[str]:
    # Minimal XML parsing without extra deps
    return [u.strip() for u in _URL_TAG_RE.findall(xml) if u.strip()]


def fetch_all_sitemap_urls(sitemap_urls: Iterable[str], max_urls: int = 2000) -> List[str]:
    urls: List[str] = []
    for sm_url in sitemap_urls:
        xml = _get_text(sm_url)
        if not xml:
            continue
        found = parse_sitemap_urls(xml)
        # If this is a sitemap index, recursively fetch child sitemaps
        if re.search(r"<sitemapindex", xml, re.I):
            # best-effort: fetch child sitemap URLs
            child_urls = []
            for child in found:
                if child.endswith(".xml"):
                    child_urls.append(child)
            if child_urls:
                urls.extend(fetch_all_sitemap_urls(child_urls, max_urls=max_urls))
        else:
            urls.extend(found)
        if len(urls) >= max_urls:
            break
    # Dedup preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:max_urls]


# ----------------------------
# Tender extraction (best-effort)
# ----------------------------

_PRICE_RE = re.compile(r"([\d\s]+[.,]?\d*)\s*(₽|RUB|руб\.?|рублей)", re.I)
_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


def _text_lines(soup: BeautifulSoup) -> List[str]:
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return None


def _extract_first_price(lines: List[str]) -> Optional[float]:
    for ln in lines:
        m = _PRICE_RE.search(ln)
        if m:
            num_raw = m.group(1).replace(" ", "").replace(",", ".")
            try:
                return float(num_raw)
            except Exception:
                return None
    return None


def _extract_customer(lines: List[str]) -> Optional[str]:
    labels = ["Заказчик", "Организатор", "Организатор закупки", "Customer", "Buyer"]
    for i, ln in enumerate(lines):
        for label in labels:
            if ln.lower().startswith(label.lower()):
                # "Заказчик: ..." on same line
                if ":" in ln:
                    parts = ln.split(":", 1)
                    val = parts[1].strip()
                    if val:
                        return val
                # value on next line
                if i + 1 < len(lines):
                    return lines[i + 1]
    return None


def _extract_deadline(lines: List[str]) -> Optional[str]:
    keywords = ["оконч", "срок", "прием заявок", "подача заявок", "deadline"]
    for ln in lines:
        if any(k in ln.lower() for k in keywords):
            m = _DATE_RE.search(ln)
            if m:
                return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    # fallback: first date in page
    for ln in lines:
        m = _DATE_RE.search(ln)
        if m:
            return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return None


def _extract_number_from_url(url: str) -> Optional[str]:
    m = re.findall(r"\d{6,}", url)
    return m[-1] if m else None


def _hashed_number(source_id: str, url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"{source_id.upper()}:{h}"


def fetch_tender_from_url(source: SourceConfig, url: str) -> Optional[Dict[str, Optional[str]]]:
    html = _get_text(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    lines = _text_lines(soup)

    title = _extract_title(soup) or ""
    price = _extract_first_price(lines)
    customer = _extract_customer(lines)
    deadline = _extract_deadline(lines)

    number = _extract_number_from_url(url) or _hashed_number(source.source_id, url)

    return {
        "number": number,
        "subject": title,
        "price": price,
        "currency": "RUB" if price is not None else None,
        "update_date": deadline,
        "stage": "Подача заявок" if deadline else None,
        "customer": customer,
        "supplier": None,
        "region": None,
        "procurement_type": f"Источник: {source.label}",
        "link": url,
    }


# Ссылки на общие списки (не на конкретный тендер) — исключаем
_GENERIC_LINK_PATTERNS = ("/new-tenders",)


def _is_generic_link(url: str) -> bool:
    url_lower = url.lower()
    return any(p in url_lower for p in _GENERIC_LINK_PATTERNS)


# ----------------------------
# High-level sync
# ----------------------------


def fetch_source_urls(source: SourceConfig, max_urls: int = 2000) -> List[str]:
    sitemaps = discover_sitemaps(source.base_url)
    urls = fetch_all_sitemap_urls(sitemaps, max_urls=max_urls)
    if source.patterns:
        urls = [u for u in urls if any(p.lower() in u.lower() for p in source.patterns)]
    urls = [u for u in urls if not _is_generic_link(u)]
    return urls[: source.max_items]


def sync_external_sources(
    sources_path: str,
    upsert_fn,
    *,
    max_urls_per_source: int = 2000,
) -> None:
    sources = load_sources(sources_path)
    for src in sources:
        if not src.enabled:
            continue
        try:
            urls = fetch_source_urls(src, max_urls=max_urls_per_source)
            logger.info("External source %s: %d urls", src.source_id, len(urls))
            for url in urls:
                tender = fetch_tender_from_url(src, url)
                if tender:
                    upsert_fn(tender)
                time.sleep(max(src.sleep_s, 0.0))
        except Exception as e:
            logger.warning("External source error %s: %s", src.source_id, e)
