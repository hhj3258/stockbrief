"""CnnFngProvider — CNN 공포탐욕지수(미국 심리), 키 불필요.

CNN 비공식 dataviz JSON 에서 직접. region='US' 만 점수 제공(그 외 None → 자체 추정/추세 폴백).
"""

from __future__ import annotations

import logging

from .._util import get_json
from .base import SentimentProvider

logger = logging.getLogger(__name__)

_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
    "Origin": "https://www.cnn.com",
}


class CnnFngProvider(SentimentProvider):
    """region='US' 의 감성지수. 한 번 받아 캐시."""

    def __init__(self, region: str = "US", timeout: int = 20):
        self.region = region
        self.timeout = timeout
        self._cache = None  # full fng dict

    def _fetch(self) -> dict | None:
        if self._cache is not None:
            return self._cache
        try:
            data = get_json(_URL, headers=_HEADERS, timeout=self.timeout, label="CNN F&G")
            fg = data.get("fear_and_greed", {}) or {}
            r1 = lambda x: round(float(x), 1) if x is not None else None  # noqa: E731
            self._cache = {
                "score": r1(fg.get("score")), "rating": fg.get("rating"),
                "prev_close": r1(fg.get("previous_close")),
                "w1": r1(fg.get("previous_1_week")), "m1": r1(fg.get("previous_1_month")),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("CNN 공포탐욕지수 조회 실패: %s", e)
            self._cache = {}
        return self._cache

    def score(self, region: str) -> float | None:
        if region != self.region:
            return None
        return (self._fetch() or {}).get("score")

    def detail(self, region: str) -> dict | None:
        if region != self.region:
            return None
        return self._fetch()
