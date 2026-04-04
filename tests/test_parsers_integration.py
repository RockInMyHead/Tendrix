from pathlib import Path
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

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _assert_common(item):
    assert item.reg_number == "0123456789012345678"
    assert item.price == 1234567.0
    assert item.purchase_object in ("Поставка офисного оборудования", "Поставка офисного оборудования ")


@pytest.mark.skip(
    reason="Интеграционный тест завязан на fetch_rss; SberbankAstParser использует POST API без RSS",
)
def test_sberbank_ast_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = SberbankAstParser()
    monkeypatch.setattr(parser, "fetch_rss", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_roseltorg_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = RoseltorgEisParser(tokens=("TOKEN_ETP",))
    monkeypatch.setattr(parser, "fetch", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_rts_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = RtsTenderEisParser(tokens=("TOKEN_ETP",))
    monkeypatch.setattr(parser, "fetch", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_etpgpb_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = EtpGpbEisParser(tokens=("TOKEN_ETP",))
    monkeypatch.setattr(parser, "fetch", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_etp_ets_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = EtpEtsEisParser(tokens=("TOKEN_ETP",))
    monkeypatch.setattr(parser, "fetch", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_lot_online_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = LotOnlineEisParser(tokens=("TOKEN_ETP",))
    monkeypatch.setattr(parser, "fetch", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_zakazrf_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = ZakazRfEisParser(tokens=("TOKEN_ETP",))
    monkeypatch.setattr(parser, "fetch", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_tektorg_search_integration(monkeypatch):
    xml = _load_fixture("eis_rss_sample.xml")
    parser = TekTorgEisParser(tokens=("TOKEN_ETP",))
    monkeypatch.setattr(parser, "fetch", lambda url: xml)
    items = parser.search("test", max_items=10)
    assert len(items) == 1
    _assert_common(items[0])


def test_external_sync_integration(monkeypatch):
    sitemap_index = _load_fixture("external_sitemap_index.xml")
    sitemap_urls = _load_fixture("external_sitemap_urls.xml")
    tender_html = _load_fixture("external_tender_page.html")

    def fake_get_text(url, timeout_s=25):
        if url.endswith("robots.txt"):
            return "Sitemap: https://example.com/sitemap.xml\n"
        if url.endswith("sitemap.xml"):
            return sitemap_index
        if url.endswith("s1.xml"):
            return sitemap_urls
        if url.endswith("/tender/123456"):
            return tender_html
        return ""

    monkeypatch.setattr(ep, "_get_text", fake_get_text)
    monkeypatch.setattr(ep, "load_sources", lambda path: [
        ep.SourceConfig(
            source_id="example",
            label="Example",
            base_url="https://example.com",
            patterns=("/tender/",),
            max_items=5,
            sleep_s=0.0,
        )
    ])

    collected = []

    def upsert_fn(t):
        collected.append(t)

    ep.sync_external_sources("ignored.json", upsert_fn=upsert_fn, max_urls_per_source=10)

    assert len(collected) == 1
    t = collected[0]
    assert t["number"] == "123456"
    assert t["subject"] == "Поставка бумаги А4"
    assert t["price"] == 123456.0
    assert t["customer"] == "ООО Ромашка"
