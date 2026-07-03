"""Advisor.run + build_markdown 통합 테스트 — 합성 provider(네트워크 없음). 핵심 출력 포맷 고정."""

from stockbrief import Advisor, AdvisorConfig, build_markdown
from stockbrief.models import NewsItem, Quote
from stockbrief.providers import DictHoldingsProvider
from stockbrief.providers.base import FxProvider, NewsProvider, QuoteProvider, SentimentProvider


class FakeQuotes(QuoteProvider):
    def quotes(self, keys, markets=None):
        return {k: Quote(key=k, price=100.0, prev=99.0, rate=1.0,
                         rsi14=72.0, ma_align="정배열", w52_pos_pct=95.0) for k in keys}


class FakeFx(FxProvider):
    def usdkrw(self):
        return 1400.0


class FakeSent(SentimentProvider):
    def score(self, region):
        return 30.0 if region == "US" else None

    def detail(self, region):
        return {"score": 30.0} if region == "US" else None


class FakeNews(NewsProvider):
    def search(self, query, days=7, asof=None):
        return [NewsItem(date="2026-07-03", title=f"{query} 관련 뉴스", url="https://ex.com/1", source="X")]


HOLDINGS = [
    {"code": "069500", "name": "KODEX200", "market": "KR", "region": "KR",
     "qty": 1, "avg_price": 120000, "eval_amount": 130000, "profit_pct": 8.3},
    {"ticker": "NVDA", "name": "엔비디아", "market": "US", "region": "US",
     "qty": 1, "avg_price_krw": 200000, "eval_amount": 300000, "profit_pct": 50.0},
]


def _advisor():
    return Advisor(AdvisorConfig.default(), DictHoldingsProvider(HOLDINGS),
                   quotes=FakeQuotes(), fx=FakeFx(), sentiment=FakeSent(), news=FakeNews())


def test_advisor_run_structure():
    inp = _advisor().run(news_days=7)
    assert inp.fx == 1400.0
    assert "_fx" not in inp.quotes                       # 매직키 제거 고정
    assert set(inp.weights) == {"069500", "NVDA"}
    assert inp.total_eval == 430000
    assert "US" in inp.regions and "KR" in inp.regions
    assert inp.regions["US"]["detail"]["sentiment_kind"] == "CNN"
    assert inp.news["NVDA"]                               # 뉴스 수집


def test_build_markdown_format():
    md = build_markdown(_advisor().run(), AdvisorConfig.default(), title="테스트 브리핑", date="2026-07-03")
    assert md.startswith("# 테스트 브리핑 — 2026-07-03")
    assert "총 평가액" in md and "Σ" not in md            # 쉬운 말·수학기호 없음
    assert "## 🌡️ 시장 국면" in md
    assert "## 📊 보유 종목" in md and "엔비디아" in md and "KODEX200" in md
    assert "## 📰 종목 뉴스" in md
    assert "별점·매수/매도" in md                          # 판단은 스킬/LLM 몫(안내 문구)
