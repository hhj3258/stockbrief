"""FreeFxProvider — USD/KRW 환율, 키 불필요. frankfurter(ECB) → open.er-api 폴백."""

from __future__ import annotations

import logging

from .._util import get_json
from .base import FxProvider

logger = logging.getLogger(__name__)

_SOURCES = [
    ("https://api.frankfurter.app/latest?from=USD&to=KRW",
     lambda d: (d["rates"]["KRW"], d.get("date"))),
    ("https://open.er-api.com/v6/latest/USD",
     lambda d: (d["rates"]["KRW"], d.get("time_last_update_utc"))),
]


class FreeFxProvider(FxProvider):
    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self.last = None  # {"USDKRW", "source", "asof"}

    def usdkrw(self) -> float | None:
        for url, parse in _SOURCES:
            try:
                d = get_json(url, headers={"User-Agent": "stockbrief"},
                             timeout=self.timeout, label=f"FX {url.split('/')[2]}")
                rate_raw, asof = parse(d)
                rate = round(float(rate_raw), 2)
                self.last = {"USDKRW": rate, "source": url.split("/")[2], "asof": asof}
                return rate
            except Exception as e:  # noqa: BLE001
                logger.debug("환율 소스 실패 (%s): %s", url.split("/")[2], e)
                continue
        logger.warning("환율 수집 실패 — 모든 소스 실패(frankfurter·er-api)")
        return None
