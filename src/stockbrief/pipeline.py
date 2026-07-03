"""Advisor — provider 들을 묶어 브리핑 입력(구조화 데이터)을 만든다.

주어진 provider 만 쓰고 없는 건 graceful skip. 결과(BriefingInputs)를 briefing.build_markdown
또는 소비자 LLM/대시보드가 사용.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from . import lib
from .config import AdvisorConfig
from .metrics import all_regions
from .models import Holdings

logger = logging.getLogger(__name__)


@dataclass
class BriefingInputs:
    holdings: Holdings
    tradable: list = field(default_factory=list)        # holdings dict 리스트
    quotes: dict = field(default_factory=dict)          # {key: quote dict}
    fx: Optional[float] = None
    sentiment: Optional[dict] = None                    # {"score","rating","w1","m1"} (US F&G)
    flow: Optional[dict] = None
    regions: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)
    overheat: tuple = (0.0, 0, 0)
    total_eval: float = 0.0
    news: dict = field(default_factory=dict)            # {key: [NewsItem...]}


def _news_terms(key, name, market, news_queries):
    cfg = news_queries.get(key)
    if not cfg:
        return [name]
    terms = [cfg.get("primary") or name] + list(cfg.get("kr") or [])[:2]
    if market != "KR":
        terms += list(cfg.get("en") or [])[:1]
    seen, out = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


_NEWS_WORD = re.compile(r"[0-9a-z가-힣]+")


def _title_tokens(title):
    return frozenset(_NEWS_WORD.findall((title or "").lower()))


def _is_similar_title(tokens, seen_tokens, threshold=0.6):
    """제목 토큰 Jaccard 유사도 ≥ threshold 면 같은 이슈로 보고 중복 처리(보수적 기본 0.6).

    "엔비디아 실적 호조에 급등" vs "엔비디아 어닝 서프라이즈에 상승" 같은 사실상 동일 기사를
    걸러 노이즈를 줄인다. 의미 기반(임베딩)이 아니라 결정적 토큰 겹침이라 키 불필요·재현 가능.
    """
    if not tokens:
        return False
    for st in seen_tokens:
        union = len(tokens | st)
        if union and len(tokens & st) / union >= threshold:
            return True
    return False


class Advisor:
    def __init__(self, config: AdvisorConfig, holdings, quotes=None, fx=None,
                 sentiment=None, news=None, naver_news=None, flow=None):
        self.config = config
        self.p_holdings = holdings
        self.p_quotes = quotes
        self.p_fx = fx
        self.p_sentiment = sentiment
        self.p_news = news
        self.p_naver = naver_news
        self.p_flow = flow

    @classmethod
    def from_brokerages(cls, config, brokerages=(), **overrides):
        """0..N 증권사 + 키리스 폴백으로 Advisor 구성(brokerage.assemble 래퍼).

        Advisor.from_brokerages(cfg, [TossBrokerage(), ...])  ·  증권사 0개면 holdings= 필수.
        """
        from .brokerage import assemble
        return cls(config, **assemble(brokerages, **overrides))

    def _proxy_keys(self):
        out = {}
        for region, cfg in self.config.regions.items():
            proxy = cfg.get("trend_proxy")
            if proxy:
                out[proxy] = "KR"   # 지수 프록시는 대개 KRX 상장(필요시 소비자가 quotes에 직접)
        return out

    def collect_news(self, days=7, asof=None, holdings=None):
        if not (self.p_news or self.p_naver):
            return {}
        h = holdings if holdings is not None else self.p_holdings.holdings()
        out = {}
        for p in h.positions:
            terms = _news_terms(p.key, p.name, p.market, self.config.news_queries)
            prov = self.p_naver if (p.market == "KR" and self.p_naver and getattr(self.p_naver, "available", True)) else self.p_news
            if prov is None:
                prov = self.p_news or self.p_naver
            items, seen_tok = [], []
            for t in terms:
                try:
                    for it in prov.search(t, days=days, asof=asof):
                        if not it.url:
                            continue
                        tok = _title_tokens(it.title)
                        if _is_similar_title(tok, seen_tok):   # 유사 제목(같은 이슈) 제거
                            continue
                        seen_tok.append(tok)
                        items.append(it)
                except Exception as e:  # noqa: BLE001
                    logger.warning("뉴스 검색 실패 (%s, term=%r): %s", p.key, t, e)
                    continue
            items.sort(key=lambda x: x.date or "", reverse=True)
            out[p.key] = items[:6]
        return out

    def run(self, news_days=7, asof=None) -> BriefingInputs:
        h = self.p_holdings.holdings()
        tradable = h.tradable_dicts()
        markets = {p.key: p.market for p in h.positions}

        quotes = {}
        if self.p_quotes:
            want = {**markets, **self._proxy_keys()}
            try:
                qmap = self.p_quotes.quotes(list(want.keys()), want)
                quotes = {k: v.as_dict() for k, v in qmap.items()}
            except Exception as e:  # noqa: BLE001
                logger.warning("시세 조회 실패: %s", e, exc_info=True)
                quotes = {}

        fx = None
        if self.p_fx:
            try:
                fx = self.p_fx.usdkrw()
            except Exception as e:  # noqa: BLE001
                logger.warning("환율 조회 실패: %s", e)
                fx = None
        # 환율은 BriefingInputs.fx 로 전달한다(과거의 quotes["_fx"] 매직키는 제거 — 종목 dict 오염 방지).

        sentiment = None
        cnn = None
        if self.p_sentiment:
            cnn = self.p_sentiment.score("US")
            sentiment = getattr(self.p_sentiment, "detail", lambda r: None)("US")

        flow = None
        if self.p_flow:
            try:
                flow = self.p_flow.kospi_flows()
            except Exception as e:  # noqa: BLE001
                logger.warning("수급 조회 실패: %s", e)
                flow = None

        rsi_oh = self.config.thresholds.get("rsi_overheat", 70.0)
        regions = all_regions(tradable, quotes, self.config.regions,
                              cnn_score=cnn, investor=flow, rsi_overheat=rsi_oh)
        w, total = lib.weights(tradable)
        oh = lib.overheat_ratio(tradable, quotes, rsi_overheat=rsi_oh)
        news = self.collect_news(days=news_days, asof=asof, holdings=h)

        return BriefingInputs(holdings=h, tradable=tradable, quotes=quotes, fx=fx,
                              sentiment=sentiment, flow=flow, regions=regions,
                              weights=w, overheat=oh, total_eval=total, news=news)
