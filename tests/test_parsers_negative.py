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


INVALID_XML = "<rss><channel><item><title>broken"


@pytest.mark.skip(
    reason="SberbankAstParser больше не парсит RSS ЕИС (нет parse_rss_items)",
)
def test_sberbank_ast_invalid_xml_returns_empty():
    parser = SberbankAstParser()
    items = parser.parse_rss_items(INVALID_XML)
    assert items == []


def test_roseltorg_invalid_xml_returns_empty():
    parser = RoseltorgEisParser(tokens=("TOKEN",))
    items = parser.parse(INVALID_XML)
    assert items == []


def test_rts_invalid_xml_returns_empty():
    parser = RtsTenderEisParser(tokens=("TOKEN",))
    items = parser.parse(INVALID_XML)
    assert items == []


def test_etpgpb_invalid_xml_returns_empty():
    parser = EtpGpbEisParser(tokens=("TOKEN",))
    items = parser.parse(INVALID_XML)
    assert items == []


def test_etp_ets_invalid_xml_returns_empty():
    parser = EtpEtsEisParser(tokens=("TOKEN",))
    items = parser.parse(INVALID_XML)
    assert items == []


def test_lot_online_invalid_xml_returns_empty():
    parser = LotOnlineEisParser(tokens=("TOKEN",))
    items = parser.parse(INVALID_XML)
    assert items == []


def test_zakazrf_invalid_xml_returns_empty():
    parser = ZakazRfEisParser(tokens=("TOKEN",))
    items = parser.parse(INVALID_XML)
    assert items == []


def test_tektorg_invalid_xml_returns_empty():
    parser = TekTorgEisParser(tokens=("TOKEN",))
    items = parser.parse(INVALID_XML)
    assert items == []


def test_external_no_sitemap_graceful(monkeypatch):
    def fake_get_text(url, timeout_s=25):
        return None

    monkeypatch.setattr(ep, "_get_text", fake_get_text)

    src = ep.SourceConfig(
        source_id="nosm",
        label="NoSitemap",
        base_url="https://example.com",
        patterns=(),
        max_items=10,
        sleep_s=0.0,
    )

    urls = ep.fetch_source_urls(src, max_urls=10)
    assert urls == []


def test_external_fetch_tender_none_on_fetch_fail(monkeypatch):
    def fake_get_text(url, timeout_s=25):
        return None

    monkeypatch.setattr(ep, "_get_text", fake_get_text)

    src = ep.SourceConfig(
        source_id="fail",
        label="Fail",
        base_url="https://example.com",
        patterns=(),
        max_items=10,
        sleep_s=0.0,
    )

    tender = ep.fetch_tender_from_url(src, "https://example.com/tender/1")
    assert tender is None


def test_external_block_page_detected(monkeypatch):
    def fake_raw_get(url, timeout_s=25):
        return "<html>Access Denied. Cloudflare. CAPTCHA</html>"

    monkeypatch.setattr(ep, "_raw_get_text", fake_raw_get)

    src = ep.SourceConfig(
        source_id="block",
        label="Block",
        base_url="https://example.com",
        patterns=(),
        max_items=10,
        sleep_s=0.0,
    )

    tender = ep.fetch_tender_from_url(src, "https://example.com/tender/1")
    assert tender is None


def test_external_sync_with_no_urls_does_not_call_upsert(monkeypatch):
    monkeypatch.setattr(ep, "fetch_source_urls", lambda *args, **kwargs: [])
    monkeypatch.setattr(ep, "load_sources", lambda path: [
        ep.SourceConfig(
            source_id="empty",
            label="Empty",
            base_url="https://example.com",
            patterns=(),
            max_items=10,
            sleep_s=0.0,
        )
    ])

    collected = []

    def upsert_fn(t):
        collected.append(t)

    ep.sync_external_sources("ignored.json", upsert_fn=upsert_fn, max_urls_per_source=10)
    assert collected == []
