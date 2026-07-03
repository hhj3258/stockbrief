"""models·config·providers 단위테스트 — 전부 합성 데이터(개인정보 없음), 네트워크 미사용."""

from stockbrief.config import AdvisorConfig
from stockbrief.models import Holdings, Quote
from stockbrief.providers import CompositeHoldingsProvider, DictHoldingsProvider
from stockbrief.providers.base import QuoteProvider
from stockbrief.providers.quotes_composite import CompositeQuoteProvider

# 합성 보유(가짜) — 삼성전자·애플 임의 수량
FAKE = [
    {"code": "005930", "name": "삼성전자", "market": "KR", "region": "KR",
     "qty": 10, "avg_price": 70000, "eval_amount": 800000},
    {"ticker": "AAPL", "name": "Apple", "market": "US", "region": "US",
     "qty": 2, "avg_price_krw": 250000, "eval_amount": 520000},
]


def test_position_roundtrip():
    h = Holdings.from_tradable_dicts(FAKE)
    assert len(h.positions) == 2
    kr, us = h.positions
    assert kr.key == "005930" and kr.market == "KR" and kr.region == "KR"
    assert us.key == "AAPL" and us.market == "US"
    d = us.as_holding_dict()
    assert d["ticker"] == "AAPL" and d["avg_price_krw"] == 250000


def test_region_fallback_to_market():
    h = Holdings.from_tradable_dicts([{"code": "069500", "name": "x", "market": "KR", "qty": 1, "avg_price": 1}])
    assert h.positions[0].region == "KR"   # region 미지정 → market 폴백


def test_config_defaults():
    c = AdvisorConfig.from_dict(None)
    assert "US" in c.regions and c.regions["US"]["sentiment"] == "cnn_fng"
    assert c.thresholds["stop_loss_pct"] == -10
    c2 = AdvisorConfig.from_dict({"instrument_themes": {"005930": "반도체"}, "high_vol_themes": ["반도체"]})
    assert c2.theme_of("005930") == "반도체"
    assert c2.is_high_vol("005930") is True


def test_dict_holdings_provider():
    prov = DictHoldingsProvider(FAKE, cash=1_000_000)
    h = prov.holdings()
    assert h.cash == 1_000_000 and len(h.positions) == 2


def test_composite_holdings_merge():
    toss = DictHoldingsProvider([{"ticker": "NVDA", "name": "엔비디아", "market": "US",
                                  "region": "US", "qty": 2, "avg_price_krw": 200000, "eval_amount": 500000}])
    kb = DictHoldingsProvider([{"code": "069500", "name": "KODEX200", "market": "KR",
                                "region": "KR", "qty": 10, "avg_price": 12000, "eval_amount": 130000}], cash=50000)
    merged = CompositeHoldingsProvider([toss, kb]).holdings()
    keys = {p.key for p in merged.positions}
    assert keys == {"NVDA", "069500"} and merged.cash == 50000

    class Boom(DictHoldingsProvider):
        def holdings(self):
            raise RuntimeError("source down")
    # 한 소스 실패해도 나머지로 진행(비엄격)
    ok = CompositeHoldingsProvider([Boom([]), kb]).holdings()
    assert {p.key for p in ok.positions} == {"069500"}


def test_composite_quote_routing():
    class FakeKR(QuoteProvider):
        def quotes(self, keys, markets=None):
            return {k: Quote(key=k, price=100.0) for k in keys}

    class FakeUS(QuoteProvider):
        def quotes(self, keys, markets=None):
            return {k: Quote(key=k, price=200.0) for k in keys}

    comp = CompositeQuoteProvider({"KR": FakeKR(), "US": FakeUS()})
    q = comp.quotes(["005930", "AAPL"], {"005930": "KR", "AAPL": "US"})
    assert q["005930"].price == 100.0 and q["AAPL"].price == 200.0


def test_quote_providers_import_without_deps():
    # 선택 의존성이 없어도 모듈 import 는 되어야(lazy import)
    import stockbrief.providers.quotes_pykrx  # noqa: F401
    import stockbrief.providers.quotes_yf  # noqa: F401
    import stockbrief.providers.quotes_kis  # noqa: F401
    import stockbrief.providers.flow_kis  # noqa: F401
    import stockbrief.providers.news_naver  # noqa: F401
