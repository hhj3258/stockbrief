"""YfinanceQuoteProvider — 미국 상장 시세·지표, **키 불필요**. `pip install "stockbrief[quotes-us]"`."""

from __future__ import annotations

import logging

from ..indicators import indicators_from_ohlcv
from ..models import Quote
from .base import QuoteProvider

logger = logging.getLogger(__name__)


class YfinanceQuoteProvider(QuoteProvider):
    def __init__(self, period: str = "1y"):
        self.period = period

    def quotes(self, keys, markets=None) -> dict[str, Quote]:
        import yfinance as yf  # lazy
        out: dict[str, Quote] = {}
        for tkr in keys:
            if markets and markets.get(tkr) == "KR":
                continue
            try:
                df = yf.Ticker(tkr).history(period=self.period, auto_adjust=True)
            except Exception as e:  # noqa: BLE001
                logger.warning("yfinance 시세 실패 (ticker=%s): %s", tkr, e)
                continue
            if df is None or not len(df):
                continue
            df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                    "Close": "close", "Volume": "volume"})
            price = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
            rate = round(100.0 * (price - prev) / prev, 2) if prev else None
            q = Quote(key=tkr, price=round(price, 2), prev=round(prev, 2) if prev else None, rate=rate)
            q.set_indicators(indicators_from_ohlcv(df, price))
            out[tkr] = q
        return out
