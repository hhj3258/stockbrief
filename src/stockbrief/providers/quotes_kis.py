"""KisQuoteProvider — 한국투자증권 고정밀 시세(선택). 소비자의 KIS 래퍼를 주입.

패키지를 특정 KIS 라이브러리에 묶지 않으려고 **콜러블 주입** 방식:
    quote_fn(session, code) -> {"name","price","prev_price","rate","halt"}
    ohlcv_fn(session, code, days) -> DataFrame(open/high/low/close[/high/low/volume])
이미 KIS 시세 래퍼(get_quote/get_daily_ohlcv)를 가진 프로젝트는 그대로 넘기면 된다. (없으면 키 불필요 pykrx/yfinance 사용)
"""

from __future__ import annotations

import logging

from ..indicators import indicators_from_ohlcv
from ..models import Quote
from .base import QuoteProvider

logger = logging.getLogger(__name__)


class KisQuoteProvider(QuoteProvider):
    def __init__(self, session, quote_fn, ohlcv_fn, ohlcv_days: int = 260):
        self.kis = session
        self.quote_fn = quote_fn
        self.ohlcv_fn = ohlcv_fn
        self.ohlcv_days = ohlcv_days

    def quotes(self, keys, markets=None) -> dict[str, Quote]:
        out: dict[str, Quote] = {}
        for code in keys:
            try:
                q = self.quote_fn(self.kis, code)
            except Exception as e:  # noqa: BLE001
                logger.warning("KIS 시세 실패 (code=%s): %s", code, e)
                continue
            price = q.get("price")
            quote = Quote(key=code, name=q.get("name"), price=price,
                          prev=q.get("prev_price"), rate=q.get("rate"))
            try:
                df = self.ohlcv_fn(self.kis, code, self.ohlcv_days)
                quote.set_indicators(indicators_from_ohlcv(df, float(price or 0)))
            except Exception as e:  # noqa: BLE001
                logger.debug("지표 계산 실패 (code=%s): %s", code, e)
            out[code] = quote
        return out
