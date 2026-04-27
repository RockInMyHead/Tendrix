"""
zakupki_parser.py
-------------------

This module provides a small helper class to query the contract register on
`zakupki.gov.ru` and extract contract information.  It attempts to emulate the
filtering capabilities exposed on the public contract search page and presents
the results in a Python-friendly form.  The parser is designed around the
query string parameters observed in public links to the contract search
endpoint.  While the unified information system (ЕИС) makes heavy use of
JavaScript, the underlying search API still accepts traditional GET
parameters – therefore it is possible to craft your own queries without a
browser.

Notes
-----
* The portal changed its data access strategy in 2025 and now relies on a
  token‑protected SOAP service for bulk data.  The approach here only
  scrapes the HTML results of the public search interface and is best suited
  for occasional queries.  Heavy scraping of the site may violate the
  portal’s terms of use.  Always respect robots.txt and rate limit your
  requests.
* The contract search page supports dozens of filters.  Only the most
  commonly used parameters are exposed here.  If you need additional fields
  (e.g. regional codes, currency, budget level, etc.), extend
  `build_params` accordingly.
* Because we cannot access the live site from this environment, the parser
  has not been executed end‑to‑end.  It should be treated as a starting
  point – inspect the actual HTML to refine the CSS selectors used in
  `parse_contracts`.

Example
-------
```python
from zakupki_parser import ZakupkiContractParser

# Create a parser with default options (morphology on, 44‑FZ contracts)
parser = ZakupkiContractParser()

# Search for contracts containing a particular tax ID or keyword
results = parser.search(
    search_string="5911082529",
    stage_list=[0, 1, 2, 3],
    price_from=0,
    price_to=10_000_000,
    publish_date_from="01.01.2025",
    publish_date_to="31.12.2025",
    records_per_page=10,
)

for contract in results:
    print(contract['number'], contract['price'], contract['subject'])
```
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass
class ContractRecord:
    """Container for contract search results.

    Attributes
    ----------
    number : str
        The contract number as shown on the site.
    subject : str
        Brief description of the contract’s subject.
    price : Optional[float]
        Contract price in Russian roubles, if parsable.
    currency : Optional[str]
        Currency code (e.g. '₽').  `None` if unavailable.
    update_date : Optional[str]
        The date when the record was last updated, in ISO format.
    stage : Optional[str]
        Human‑readable stage of the contract (e.g. 'Подготовка проекта').
    customer : Optional[str]
        Name of the customer organisation.
    supplier : Optional[str]
        Name of the supplier organisation.
    region : Optional[str]
        Region of the customer organisation.
    procurement_type : Optional[str]
        Type of procurement (e.g. 'Электронный аукцион').
    link : str
        Absolute URL to the contract detail page.
    """

    number: str
    subject: str
    price: Optional[float] = None
    currency: Optional[str] = None
    update_date: Optional[str] = None
    stage: Optional[str] = None
    customer: Optional[str] = None
    supplier: Optional[str] = None
    region: Optional[str] = None
    procurement_type: Optional[str] = None
    link: str = ""


class ZakupkiContractParser:
    """Parser for the contract search page of zakupki.gov.ru.

    This class wraps the construction of query parameters and the parsing of
    the resulting HTML.  It exposes a `search` method that returns a list of
    :class:`ContractRecord` objects.  Where possible, filters mirror the
    options described in the user manual for the contract register search
    page【41098085417111†L2314-L2382】.
    """

    BASE_URL = "https://zakupki.gov.ru/epz/contract/search/results.html"
    
    def __init__(self, *, user_agent: Optional[str] = None, timeout: int = 15) -> None:
        self.session = requests.Session()
        self.timeout = timeout
        # Provide a browser‑like user agent to avoid trivial blocks.
        self.session.headers.update(
            {
                "User-Agent": user_agent
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_stage_params(self, stage_list: Iterable[int]) -> Dict[str, str]:
        """Translate a list of stage codes into query parameters.

        The contract search page uses `contractStageList_i=on` checkboxes for
        each stage, and a comma‑separated `contractStageList` field to encode
        the selected values.  Valid stage codes (as of version 13.2 of the
        portal) include:

        0 – "Подготовка проекта контракта" (drafting stage)
        1 – "Подписание поставщиком" (supplier signing)
        2 – "Подписание заказчиком" (customer signing)
        3 – "Контракт заключен" (contract concluded)

        A fifth value `4` may correspond to "Контракт не заключен", but it
        is not displayed by default【41098085417111†L2376-L2382】.
        """
        params: Dict[str, str] = {}
        stages = [str(int(s)) for s in stage_list if isinstance(s, (int, str))]
        for s in stages:
            params[f"contractStageList_{s}"] = "on"
        if stages:
            params["contractStageList"] = ",".join(stages)
        return params

    def _build_params(
        self,
        search_string: Optional[str] = None,
        stage_list: Optional[Iterable[int]] = None,
        price_from: Optional[float] = None,
        price_to: Optional[float] = None,
        publish_date_from: Optional[str] = None,
        publish_date_to: Optional[str] = None,
        contract_date_from: Optional[str] = None,
        contract_date_to: Optional[str] = None,
        currency_id: int = -1,
        law_44: bool = True,
        law_223: bool = False,
        sort_by: str = "UPDATE_DATE",
        sort_descending: bool = True,
        page: int = 1,
        records_per_page: int = 10,
        morphology: bool = True,
        show_lots_info: bool = False,
        additional_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Construct a dictionary of query parameters.

        Parameters mirror the visible search options available to users on the
        contract search page【41098085417111†L2314-L2382】.  Dates should be provided
        in DD.MM.YYYY format.  If you omit optional values, the parameter is
        simply not included in the query.
        """
        params: Dict[str, str] = {}
        if search_string:
            # Generic search string; may include contract number, supplier name
            # or tax identifier.  The site performs morphological analysis
            # when `morphology=on` is set.
            params["searchString"] = search_string
        if morphology:
            params["morphology"] = "on"
        if law_44:
            params["fz44"] = "on"
        if law_223:
            params["fz223"] = "on"
        # Stage list (0–4).  Pass a list or tuple to control which checkboxes
        # are selected.
        if stage_list:
            params.update(self._build_stage_params(stage_list))
        # Price range – the site uses min and max price fields
        if price_from is not None:
            params["contractPriceFrom"] = str(price_from)
        if price_to is not None:
            params["contractPriceTo"] = str(price_to)
        # Publication date range (date when contract draft was posted)
        if publish_date_from:
            params["publishDateFrom"] = publish_date_from
        if publish_date_to:
            params["publishDateTo"] = publish_date_to
        # Contract conclusion date range
        if contract_date_from:
            params["contractDateFrom"] = contract_date_from
        if contract_date_to:
            params["contractDateTo"] = contract_date_to
        # Currency filter (–1 = any).  The portal uses numeric IDs for each
        # currency; 1 for RUB, 2 for USD, etc.  Values can be obtained from
        # the site’s dropdown via developer tools.  The example link uses –1.
        params["contractCurrencyID"] = str(currency_id)
        # Sorting
        params["sortBy"] = sort_by
        params["sortDirection"] = "false" if sort_descending else "true"
        # Paging
        params["pageNumber"] = str(page)
        # The portal encodes `recordsPerPage` values with a leading underscore.
        # Valid options are 10, 20, 50 and 200.
        params["recordsPerPage"] = f"_{records_per_page}"
        # Hidden parameter that controls whether lot information is expanded
        params["showLotsInfoHidden"] = "true" if show_lots_info else "false"
        # Merge any user‑supplied extras (e.g. budgetLevelsIdNameHidden,
        # customer titles, region IDs)
        if additional_params:
            params.update(additional_params)
        return params

    def _fetch(self, params: Dict[str, str]) -> str:
        """Fetch the raw HTML for a given set of query parameters.

        Returns the response text.  An exception is raised if the request
        fails or times out.  The portal sometimes redirects to a generic
        error page when an invalid combination of filters is selected – it is
        advisable to validate your inputs before calling this method.
        """
        logger.info("Fetching contracts page, params=%s", params)
        response = self.session.get(
            self.BASE_URL,
            params=params,
            allow_redirects=True,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _guess_region_from_text(text: str) -> Optional[str]:
        """Heuristically extract region from customer name."""
        if not text:
            return None
        text_upper = text.upper()
        
        # Major Cities
        if "МОСКВА" in text_upper or "МОСКВЫ" in text_upper: return "Москва"
        if "САНКТ-ПЕТЕРБУРГ" in text_upper: return "Санкт-Петербург"
        if "СЕВАСТОПОЛЬ" in text_upper: return "Севастополь"
        
        # Keywords to look for
        keywords = [
            "ОБЛАСТЬ", "ОБЛАСТИ", "КРАЙ", "КРАЯ", "РЕСПУБЛИКА", "РЕСПУБЛИКИ", 
            "ОКРУГ", "ОКРУГА"
        ]
        
        # Simple extraction: find the word before/after common markers
        # Actually, let's look for specific known regions if we want high quality
        # Or just return the phrase containing the marker.
        
        # Quick robust list of Russian regions (shortened)
        regions_db = [
            "Адыгея", "Башкортостан", "Бурятия", "Алтай", "Дагестан", "Ингушетия", "Кабардино-Балкар", "Калмыкия",
            "Карачаево-Черкес", "Карелия", "Коми", "Крым", "Марий Эл", "Мордовия", "Саха", "Осетия", "Татарстан",
            "Тыва", "Удмурт", "Хакасия", "Чечен", "Чуваш", "Алтайск", "Краснодар", "Красноярск", "Приморск",
            "Ставрополь", "Хабаровск", "Амурск", "Архангельск", "Астрахан", "Белгород", "Брянск", "Владимир",
            "Волгоград", "Вологод", "Воронеж", "Иванов", "Иркутск", "Калининград", "Калуж", "Камчат", "Кемеров",
            "Киров", "Костром", "Курган", "Курск", "Ленинград", "Липецк", "Магадан", "Московск", "Мурманск",
            "Нижегород", "Новгород", "Новосибир", "Омск", "Оренбург", "Орлов", "Пензен", "Перм", "Псков",
            "Ростов", "Рязан", "Самар", "Саратов", "Сахалин", "Свердлов", "Смоленск", "Тамбов", "Твер", "Томск",
            "Тульск", "Тюмен", "Ульянов", "Челябин", "Ярослав", "Байконур", "Ненецк", "Ханты-Мансий", "Чукот", "Ямало-Ненец"
        ]
        
        for r in regions_db:
             if r.upper() in text_upper:
                 # Map 'Калуж' -> 'Калужская область' could be better but 'Калужская область' is fine enough
                 # We try to grab the full phrase if possible?
                 # No, just return the detected root for now, or the full region name if we had a map.
                 # Let's return a clean formatted version if we can.
                 if "ОБЛ" in text_upper or "КРАЙ" in text_upper or "РЕСП" in text_upper:
                     # Attempt to extract context
                     return r + " (регион)" # Simple marker
                 return r
                 
        return None

    @staticmethod
    def _parse_price(raw_price: str) -> Tuple[Optional[float], Optional[str]]:
        """Extract a numeric price and currency symbol from a raw string.

        The portal displays prices like: ``496 763,18 ₽``
        """
        if not raw_price:
            return None, None
        
        # Clean: remove non-breaking spaces, specialized spaces, and newlines
        cleaned = raw_price.replace("\xa0", "").replace("\u202f", "").replace("&nbsp;", "")
        cleaned = re.sub(r"\s+", "", cleaned)
        
        # Match number part (digits, commas, dots) and currency part
        # Example: 496763,18₽
        match = re.search(r"([\d.,]+)([^\d.,]+)?", cleaned)
        if not match:
            return None, None
            
        number_str = match.group(1)
        currency_part = match.group(2)
        
        # Normalize number: remove spaces (already done), replace comma with dot
        number_str = number_str.replace(",", ".")
        
        try:
            price_val = float(number_str)
        except ValueError:
            price_val = None
            
        currency = currency_part.strip() if currency_part else "₽"
        return price_val, currency

    def parse_contracts(self, html: str) -> List[ContractRecord]:
        """Parse the HTML returned by the search page into records."""
        soup = BeautifulSoup(html, "lxml")
        records: List[ContractRecord] = []
        
        # Select the main container for each result
        items = soup.select("div.search-registry-entry-block")
        if not items:
            # Fallback for old design or different view
            items = soup.select("div.registry-entry")
            
        for item in items:
            # --- NUMBER & LINK ---
            # Usually in header: div.registry-entry__header-mid__number a
            number_tag = item.select_one("div.registry-entry__header-mid__number a")
            if not number_tag:
                # Fallback
                number_tag = item.select_one("a[href*='contractCard']")
                
            if not number_tag:
                continue
                
            link = number_tag.get("href")
            if link and link.startswith("/"):
                link = "https://zakupki.gov.ru" + link
                
            # Text often contains "№ " prefix
            number = number_tag.get_text(strip=True).replace("№", "").strip()

            # --- SUBJECT ---
            # div.lots-wrap-content__body__val -> span
            subject_tag = item.select_one("div.lots-wrap-content__body__val")
            if subject_tag:
                # Take the first text node or span, ignoring "Show all" links
                subject = subject_tag.get_text(" ", strip=True)
                # Cleanup "Show all" text if present
                if "Посмотреть все" in subject:
                    subject = subject.split("Посмотреть все")[0].strip()
            else:
                # Fallback to body value if "lots" not found
                subject_tag_alt = item.select_one("div.registry-entry__body-value") 
                subject = subject_tag_alt.get_text(strip=True) if subject_tag_alt else "Предмет не указан"

            # --- PRICE ---
            # div.price-block__value
            price_tag = item.select_one("div.price-block__value")
            raw_price = price_tag.get_text(strip=True) if price_tag else ""
            price_val, currency = self._parse_price(raw_price)

            # --- STAGE ---
            # div.registry-entry__header-mid__title
            stage_tag = item.select_one("div.registry-entry__header-mid__title")
            stage = stage_tag.get_text(strip=True) if stage_tag else None

            # --- CUSTOMER ---
            # Look for block titled "Заказчик"
            customer = None
            for block in item.select("div.registry-entry__body-block"):
                title = block.select_one("div.registry-entry__body-title")
                if title and "Заказчик" in title.get_text():
                    customer_link = block.select_one("div.registry-entry__body-href a") or block.select_one("a")
                    if customer_link:
                        customer = customer_link.get_text(strip=True)
                    break
            
            # --- SUPPLIER ---
            # Look for block titled "Поставщик"
            supplier = None
            for block in item.select("div.registry-entry__body-block"):
                title = block.select_one("div.registry-entry__body-title")
                if title and "Поставщик" in title.get_text():
                    supplier_link = block.select_one("div.registry-entry__body-href a") or block.select_one("a")
                    if supplier_link:
                        supplier = supplier_link.get_text(strip=True)
                    break

            # --- DATES ---
            update_date = None
            deadline_date = None
            date_blocks = item.select("div.data-block")
            for db_item in date_blocks:
                title_tag = db_item.select_one("div.data-block__title")
                val_tag = db_item.select_one("div.data-block__value")
                if title_tag and val_tag:
                    title_text = title_tag.get_text(strip=True).lower()
                    val_text = val_tag.get_text(strip=True)
                    if "окончание подачи" in title_text:
                        deadline_date = val_text
                    elif "обновлено" in title_text or "размещено" in title_text:
                        if not update_date: # Keep the first one found if no deadline
                            update_date = val_text
            
            # Use deadline if found, otherwise update date
            final_date = deadline_date or update_date
            
            if not final_date:
                # Last resort fallback
                for db_item in date_blocks:
                    val = db_item.select_one("div.data-block__value")
                    if val:
                        final_date = val.get_text(strip=True)
                        break
            
            update_date = final_date

            # --- REGION ---
            # 1. Try explicit header (rare in Contract Registry)
            region = None
            region_tag = item.select_one("div.registry-entry__header-top__title")
            if region_tag:
                raw_text = region_tag.get_text(strip=True)
                if "№" not in raw_text and len(raw_text) > 2:
                     region = raw_text

            # 2. Key heuristic: Extract from Customer Name or Text
            if not region and customer:
                region = self._guess_region_from_text(customer)
            
            # --- PROCUREMENT TYPE ---
            proc_type = "44-ФЗ"
            
            # 1. Try icon/label
            label_tag = item.select_one("div.registry-entry__header-top__icon")
            if label_tag:
                label_text = label_tag.get_text(strip=True)
                if "223" in label_text:
                    proc_type = "223-ФЗ"
            
            # 2. Deep search in lot vars for "Реквизиты закупки"
            # Often contains: "Электронный аукцион"
            if item.select_one(".lots-vars"):
                # Use regex or simple search in the 'val' blocks
                vals = item.select("div.lots-wrap-content__body__val")
                for v in vals:
                    vt = v.get_text(strip=True)
                    if "Электронный аукцион" in vt:
                        proc_type = "Электронный аукцион" # Or stick to Law? User might prefer type.
                        # Actually user asked for type like "44-FZ", but specific type is also good. 
                        # Let's keep 44/223 detection as primary, but finding the exact method is cool.
                        pass
                    if "223-ФЗ" in vt:
                        proc_type = "223-ФЗ"

            records.append(
                ContractRecord(
                    number=number,
                    subject=subject,
                    price=price_val,
                    currency=currency,
                    update_date=update_date,
                    stage=stage,
                    customer=customer,
                    supplier=supplier,
                    region=region,
                    procurement_type=proc_type,
                    link=link or "",
                )
            )
        return records

    # ------------------------------------------------------------------
    # Detailed Parsing
    # ------------------------------------------------------------------
    def _fetch_and_extract_text(self, reestr_number: str, path: str, label: str) -> str:
        """Fetch a detail tab and extract clean text for LLM."""
        try:
            url = f"https://zakupki.gov.ru/epz/contract/contractCard/{path}?reestrNumber={reestr_number}"
            logger.info("Fetching %s: %s", label, url)
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Focus on the main content area if possible
            main_content = soup.select_one("div.card-wrapper") or soup.select_one("body")
            
            # Extract text
            text = main_content.get_text(separator=" ", strip=True)
            # Remove excessive whitespace
            text = re.sub(r"\s+", " ", text)
            
            return f"\n=== {label} ===\n{text[:5000]}" # Limit per tab to avoid hitting token limits too hard
        except Exception as e:
            logger.error("Error fetching %s for %s: %s", label, reestr_number, e)
            return f"\n=== {label} ===\n[Ошибка при загрузке данных]"

    def get_detailed_info(self, reestr_number: str) -> str:
        """Fetch and combine text from all 6 main tabs of a contract."""
        tabs = [
            ("common-info.html", "ОБЩАЯ ИНФОРМАЦИЯ"),
            ("payment-info-and-target-of-order.html", "ПЛАТЕЖИ И ОБЪЕКТЫ ЗАКУПКИ"),
            ("execution-and-termination-info.html", "ИСПОЛНЕНИЕ (РАСТОРЖЕНИЕ) КОНТРАКТА"),
            ("documents.html", "ВЛОЖЕНИЯ"),
            ("contract-view.html", "ЖУРНАЛ ВЕРСИЙ"),
            ("event-journal.html", "ЖУРНАЛ СОБЫТИЙ"),
        ]
        
        full_text = []
        for path, label in tabs:
            full_text.append(self._fetch_and_extract_text(reestr_number, path, label))
            
        return "\n".join(full_text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_total_count(soup: BeautifulSoup) -> int:
        """Extract total number of records from the search results page."""
        total_tag = soup.select_one("div.search-results__total")
        if not total_tag:
            return 0
        text = total_tag.get_text(strip=True)
        # Usually format is "X записей" or "1 234 записей"
        # Extract digits
        digits = re.sub(r"\D", "", text)
        return int(digits) if digits else 0

    def search(
        self,
        search_string: Optional[str] = None,
        stage_list: Optional[Iterable[int]] = None,
        price_from: Optional[float] = None,
        price_to: Optional[float] = None,
        publish_date_from: Optional[str] = None,
        publish_date_to: Optional[str] = None,
        contract_date_from: Optional[str] = None,
        contract_date_to: Optional[str] = None,
        currency_id: int = -1,
        law_44: bool = True,
        law_223: bool = False,
        sort_by: str = "UPDATE_DATE",
        sort_descending: bool = True,
        page: int = 1,
        records_per_page: int = 10,
        morphology: bool = True,
        show_lots_info: bool = False,
        additional_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        """Query the contract register and return records + total count."""
        params = self._build_params(
            search_string=search_string,
            stage_list=stage_list,
            price_from=price_from,
            price_to=price_to,
            publish_date_from=publish_date_from,
            publish_date_to=publish_date_to,
            contract_date_from=contract_date_from,
            contract_date_to=contract_date_to,
            currency_id=currency_id,
            law_44=law_44,
            law_223=law_223,
            sort_by=sort_by,
            sort_descending=sort_descending,
            page=page,
            records_per_page=records_per_page,
            morphology=morphology,
            show_lots_info=show_lots_info,
            additional_params=additional_params,
        )
        html = self._fetch(params)
        soup = BeautifulSoup(html, "lxml")
        total_count = self._parse_total_count(soup)
        
        # Parse records using existing logic but parse_contracts expects raw HTML string
        # Let's just call parse_contracts with html string since we already have it
        records = self.parse_contracts(html)
        
        return {
            "total": total_count,
            "records": records
        }
