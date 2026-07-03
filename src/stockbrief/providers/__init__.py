"""StockBrief providers.

키 불필요 기본 provider 는 패키지 import 시 바로 쓸 수 있다.
시세 provider(pykrx·yfinance·KIS)는 선택 의존성이라 **명시 경로로** import:
    from stockbrief.providers.quotes_pykrx import PykrxQuoteProvider
    from stockbrief.providers.quotes_kis import KisQuoteProvider
"""

from __future__ import annotations

from .base import (  # noqa: F401
    FlowProvider,
    FxProvider,
    HoldingsProvider,
    NewsProvider,
    QuoteProvider,
    SentimentProvider,
)
from .fx_free import FreeFxProvider  # noqa: F401
from .holdings_composite import CompositeHoldingsProvider  # noqa: F401
from .holdings_dict import DictHoldingsProvider  # noqa: F401
from .holdings_json import JsonHoldingsProvider  # noqa: F401
from .news_google import GoogleNewsProvider  # noqa: F401
from .quotes_composite import CompositeQuoteProvider  # noqa: F401
from .sentiment_cnn import CnnFngProvider  # noqa: F401

__all__ = [
    "HoldingsProvider", "QuoteProvider", "FxProvider", "SentimentProvider",
    "NewsProvider", "FlowProvider",
    "JsonHoldingsProvider", "DictHoldingsProvider", "CompositeHoldingsProvider",
    "CompositeQuoteProvider", "FreeFxProvider", "CnnFngProvider", "GoogleNewsProvider",
]
