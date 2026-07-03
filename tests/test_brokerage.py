"""증권사 0..N 조립(brokerage.assemble / Advisor.from_brokerages) — 합성, 네트워크 없음."""

import pytest

from stockbrief import Advisor, AdvisorConfig, assemble
from stockbrief.brokerage import Brokerage
from stockbrief.models import Quote
from stockbrief.providers import DictHoldingsProvider
from stockbrief.providers.base import FlowProvider, QuoteProvider
from stockbrief.providers.holdings_composite import CompositeHoldingsProvider
from stockbrief.providers.quotes_composite import CompositeQuoteProvider

KR = [{"code": "069500", "name": "x", "market": "KR", "region": "KR", "qty": 1, "avg_price": 1, "eval_amount": 100}]
US = [{"ticker": "NVDA", "name": "n", "market": "US", "region": "US", "qty": 1, "avg_price_krw": 1, "eval_amount": 200}]


class FakeQuotes(QuoteProvider):
    def quotes(self, keys, markets=None):
        return {k: Quote(key=k, price=1.0) for k in keys}


class FakeFlow(FlowProvider):
    def kospi_flows(self, days=5):
        return {"flows": []}


class FakeBrokerage(Brokerage):
    def __init__(self, holdings, q=None, f=None):
        self._h, self._q, self._f = holdings, q, f

    def holdings(self):
        return self._h

    def quotes(self):
        return self._q

    def flow(self):
        return self._f


def test_zero_brokerages_keyless():
    dp = DictHoldingsProvider(KR)
    provs = assemble([], holdings=dp)                  # 증권사 0개 → 키리스
    assert provs["holdings"] is dp
    assert provs["sentiment"] and provs["news"] and provs["fx"]   # 키리스 기본 채워짐
    assert provs["flow"] is None
    assert isinstance(provs["quotes"], CompositeQuoteProvider)    # pykrx/yf 폴백


def test_zero_brokerages_no_quotes_option():
    provs = assemble([], holdings=DictHoldingsProvider(KR), keyless_quotes=False)
    assert provs["quotes"] is None                    # 시세 소스 0개여도 동작(단계 skip)


def test_no_holdings_raises():
    with pytest.raises(ValueError):
        assemble([])                                  # 증권사도 holdings 도 없으면 에러


def test_n_brokerages_merge():
    b1 = FakeBrokerage(DictHoldingsProvider(KR), q=FakeQuotes())
    b2 = FakeBrokerage(DictHoldingsProvider(US), f=FakeFlow())
    provs = assemble([b1, b2])
    assert isinstance(provs["holdings"], CompositeHoldingsProvider)   # 2개 병합
    assert len(provs["holdings"].holdings().positions) == 2           # KR + US
    assert provs["quotes"] is b1._q                                   # 첫 증권사 시세
    assert provs["flow"] is b2._f                                     # 첫 수급


def test_from_brokerages_wires_advisor():
    b = FakeBrokerage(DictHoldingsProvider(KR), q=FakeQuotes())
    adv = Advisor.from_brokerages(AdvisorConfig.default(), [b])
    assert adv.p_holdings is b._h and adv.p_quotes is b._q
