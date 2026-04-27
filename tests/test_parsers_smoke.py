import pytest
import external_parsers as ep
from sberbank_ast_parser import SberbankAstParser
from roseltorg_parser import RoseltorgEisParser
from rts_tender_parser import RtsTenderEisParser
from etpgpb_parser import EtpGpbEisParser
from etp_ets_parser import EtpEtsEisParser
from lot_online_parser import LotOnlineEisParser
from zakazrf_parser import ZakazRfEisParser
from tektorg_parser import TekTorgEisParser


def _make_rss_xml(token: str) -> str:
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss><channel>
<item>
<title>Test Tender</title>
<link>https://zakupki.gov.ru/epz/order/notice/printForm/viewXml.html?regNumber=0123456789012345678</link>
<pubDate>Mon, 02 Feb 2026 10:00:00 +0300</pubDate>
<description><![CDATA[
Наименование объекта закупки: Тестовый предмет<br>
Начальная (максимальная) цена контракта: 1 234 567 руб.<br>
Окончание подачи заявок: 01.02.2026 12:00<br>
Электронная площадка: {token}<br>
]]></description>
</item>
</channel></rss>
"""


def _assert_common(item):
    assert item.reg_number == "0123456789012345678"
    assert item.price == 1234567.0
    assert item.purchase_object == "Тестовый предмет"


@pytest.mark.skip(
    reason="SberbankAstParser больше не парсит RSS ЕИС (нет parse_rss_items; используется API площадки)",
)
def test_sberbank_ast_parse_rss_items_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = SberbankAstParser()
    items = parser.parse_rss_items(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_roseltorg_parse_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = RoseltorgEisParser(tokens=("TOKEN",))
    items = parser.parse(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_rts_parse_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = RtsTenderEisParser(tokens=("TOKEN",))
    items = parser.parse(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_etpgpb_parse_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = EtpGpbEisParser(tokens=("TOKEN",))
    items = parser.parse(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_etp_ets_parse_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = EtpEtsEisParser(tokens=("TOKEN",))
    items = parser.parse(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_lot_online_parse_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = LotOnlineEisParser(tokens=("TOKEN",))
    items = parser.parse(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_zakazrf_parse_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = ZakazRfEisParser(tokens=("TOKEN",))
    items = parser.parse(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_tektorg_parse_smoke():
    xml = _make_rss_xml("TOKEN")
    parser = TekTorgEisParser(tokens=("TOKEN",))
    items = parser.parse(xml)
    assert len(items) == 1
    _assert_common(items[0])


def test_external_parsers_sitemap_index_and_html(monkeypatch):
    def fake_get_text(url, timeout_s=25):
        if url.endswith("sitemap.xml"):
            return """
<sitemapindex>
  <sitemap><loc>https://example.com/s1.xml</loc></sitemap>
</sitemapindex>
"""
        if url.endswith("s1.xml"):
            return """
<urlset>
  <url><loc>https://example.com/tender/123456</loc></url>
</urlset>
"""
        if url.endswith("/tender/123456"):
            return """
<html>
  <head><title>Test Tender Page</title></head>
  <body>
    <div>Заказчик: ООО Ромашка</div>
    <div>Начальная цена: 123 456 руб.</div>
    <div>Окончание подачи заявок: 01.02.2026</div>
  </body>
</html>
"""
        return ""

    monkeypatch.setattr(ep, "_get_text", fake_get_text)

    urls = ep.fetch_all_sitemap_urls(["https://example.com/sitemap.xml"], max_urls=10)
    assert urls == ["https://example.com/tender/123456"]

    src = ep.SourceConfig(
        source_id="test",
        label="Test",
        base_url="https://example.com",
        patterns=("/tender/",),
        max_items=10,
        sleep_s=0.0,
    )
    tender = ep.fetch_tender_from_url(src, urls[0])
    assert tender is not None
    assert tender["number"] == "123456"
    assert tender["subject"] == "Test Tender Page"
    assert tender["price"] == 123456.0
    assert tender["customer"] == "ООО Ромашка"
