"""PykrxQuoteProvider — 한국 상장(KRX) 시세·지표, **키 불필요**. `pip install "stockbrief[quotes-kr]"`.

pykrx 일봉(주식·ETF) → 현재가·등락률 + RSI·이동평균·52주(indicators). 미국 티커는 처리 안 함(YfinanceQuoteProvider 와 합성).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..indicators import indicators_from_ohlcv
from ..models import Quote
from .base import QuoteProvider

logger = logging.getLogger(__name__)
_COLMAP = {"시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}


class PykrxQuoteProvider(QuoteProvider):
    def __init__(self, lookback_days: int = 400):
        self.lookback_days = lookback_days

    def _ohlcv(self, code: str):
        from pykrx import stock  # lazy
        today = datetime.now().strftime("%Y%m%d")
        frm = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y%m%d")
        df = None
        for fn in ("get_market_ohlcv_by_date", "get_etf_ohlcv_by_date"):
            try:
                d = getattr(stock, fn)(frm, today, code)
                if d is not None and len(d):
                    df = d
                    break
            except Exception as e:  # noqa: BLE001
                logger.debug("pykrx %s 실패 (code=%s): %s", fn, code, e)
                continue
        if df is None or not len(df):
            logger.warning("pykrx 일봉 없음 (code=%s)", code)
            return None
        df = df.rename(columns=_COLMAP)
        keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        return df[keep]

    def quotes(self, keys, markets=None) -> dict[str, Quote]:
        out: dict[str, Quote] = {}
        for code in keys:
            if markets and markets.get(code) == "US":
                continue
            df = self._ohlcv(code)
            if df is None or "close" not in df.columns or not len(df):
                continue
            price = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-2]) if len(df) >= 2 else None
            rate = round(100.0 * (price - prev) / prev, 2) if prev else None
            q = Quote(key=code, price=price, prev=prev, rate=rate)
            q.set_indicators(indicators_from_ohlcv(df, price))
            out[code] = q
        return out
