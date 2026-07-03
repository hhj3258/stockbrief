"""증권사 연결 추상화 — 0..N 개를 꽂아 쓴다. **증권사 0개여도 키리스로 동작.**

각 `Brokerage` 는 그 증권사의 provider(보유·시세·수급)를 묶는다(지원 안 하는 건 None).
`assemble()` 이 N개를 합치고 빠진 자리를 키리스 기본(pykrx·yfinance·CNN·Google·ECB)으로 채워
`Advisor` 에 넣을 provider dict 를 만든다.

    from stockbrief import Advisor, AdvisorConfig, build_markdown
    from stockbrief.brokerage import TossBrokerage, KisBrokerage, assemble

    # 증권사 2개
    provs = assemble([TossBrokerage(), KisBrokerage(kis_session, quote_fn=..., ohlcv_fn=...)])
    # 증권사 0개(키리스) — 보유만 직접 주입
    provs = assemble([], holdings=JsonHoldingsProvider("holdings.json"))
    md = build_markdown(Advisor(AdvisorConfig.default(), **provs).run(), AdvisorConfig.default())

의존성은 전부 메서드 안 lazy import — 이 모듈 import 만으로 무거운 dep(pandas/pykis) 를 끌지 않는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Brokerage(ABC):
    """한 증권사 연결. 보유는 필수, 시세·수급은 지원하면 provider, 아니면 None."""

    name: str = "brokerage"

    @abstractmethod
    def holdings(self):
        """HoldingsProvider — 보유 조회. 없는 증권사면 None."""

    def quotes(self):
        """QuoteProvider | None — 시세."""
        return None

    def flow(self):
        """FlowProvider | None — 코스피 수급 등."""
        return None


class TossBrokerage(Brokerage):
    """토스증권 — 보유 + 시세. TOSS_CLIENT_ID/SECRET(또는 인자)."""

    name = "toss"

    def __init__(self, client_id=None, client_secret=None, *,
                 country="KR", region_map=None, ignore_symbols=None):
        self._auth = {"client_id": client_id, "client_secret": client_secret}
        self._hkw = {"country": country, "region_map": region_map, "ignore_symbols": ignore_symbols}

    def holdings(self):
        from .integrations.toss import TossHoldingsProvider
        return TossHoldingsProvider(**self._auth, **self._hkw)

    def quotes(self):
        from .integrations.toss import TossQuoteProvider
        return TossQuoteProvider(**self._auth)


class KisBrokerage(Brokerage):
    """한국투자증권 — 보유 + (콜러블 주면)시세 + 수급. pykis 세션 주입."""

    name = "kis"

    def __init__(self, session, *, quote_fn=None, ohlcv_fn=None,
                 country="KR", region_map=None, ignore_symbols=None):
        self.session = session
        self.quote_fn, self.ohlcv_fn = quote_fn, ohlcv_fn
        self._hkw = {"country": country, "region_map": region_map, "ignore_symbols": ignore_symbols}

    def holdings(self):
        from .integrations.kis import KisHoldingsProvider
        return KisHoldingsProvider(self.session, **self._hkw)

    def quotes(self):
        if not (self.quote_fn and self.ohlcv_fn):
            return None
        from .providers.quotes_kis import KisQuoteProvider
        return KisQuoteProvider(self.session, self.quote_fn, self.ohlcv_fn)

    def flow(self):
        from .providers.flow_kis import KisFlowProvider
        return KisFlowProvider(self.session)


def _keyless_quotes():
    """시세 소스 없을 때 폴백: pykrx(KR)+yfinance(US) 라우팅. (dep 없으면 호출 시 graceful skip)"""
    from .providers.quotes_composite import CompositeQuoteProvider
    from .providers.quotes_pykrx import PykrxQuoteProvider
    from .providers.quotes_yf import YfinanceQuoteProvider
    return CompositeQuoteProvider({"KR": PykrxQuoteProvider(), "US": YfinanceQuoteProvider()})


def assemble(brokerages=(), *, holdings=None, quotes=None, sentiment=None, news=None,
             naver_news=None, fx=None, flow=None, keyless_quotes=True) -> dict:
    """0..N 증권사 + 키리스 폴백 → `Advisor(**provs)` 에 넣을 provider dict.

    - 보유: 증권사 보유들 + `holdings=`(직접) 를 **병합**(2개↑면 CompositeHoldingsProvider). 하나도 없으면 에러.
    - 시세: `quotes=` 우선 → 증권사 첫 시세 → 키리스(pykrx/yf). 다 없으면 None(시세 단계 skip).
    - 수급: `flow=` 우선 → 증권사 첫 flow. 없으면 None.
    - 심리·뉴스·환율: 인자 우선, 없으면 키리스 기본(CNN·Google·ECB).
    """
    brokerages = list(brokerages)
    hlist = [h for h in (b.holdings() for b in brokerages) if h is not None]
    if holdings is not None:
        hlist.append(holdings)
    if not hlist:
        raise ValueError("보유 소스가 없습니다 — 증권사를 1개 이상 넣거나 holdings= 로 보유를 주세요.")
    if len(hlist) == 1:
        holdings_p = hlist[0]
    else:
        from .providers.holdings_composite import CompositeHoldingsProvider
        holdings_p = CompositeHoldingsProvider(hlist)

    if quotes is None:
        quotes = next((q for q in (b.quotes() for b in brokerages) if q is not None), None)
        if quotes is None and keyless_quotes:
            quotes = _keyless_quotes()
    if flow is None:
        flow = next((f for f in (b.flow() for b in brokerages) if f is not None), None)

    from .providers.fx_free import FreeFxProvider
    from .providers.news_google import GoogleNewsProvider
    from .providers.sentiment_cnn import CnnFngProvider
    return {
        "holdings": holdings_p, "quotes": quotes,
        "sentiment": sentiment or CnnFngProvider(),
        "news": news or GoogleNewsProvider(), "naver_news": naver_news,
        "fx": fx or FreeFxProvider(), "flow": flow,
    }
