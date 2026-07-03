"""CompositeHoldingsProvider — 여러 보유 소스를 하나의 Holdings 로 병합.

보유가 여러 증권사 계좌에 나뉜 경우(예: 미국주=토스 API, 한국주=KB 수동 JSON) 각 소스의
HoldingsProvider 를 순서대로 합친다. 실패한 소스는 건너뛰고 나머지로 진행(strict=True 면 예외).
같은 종목(key) 이 여러 소스에 있으면 **먼저 온 소스**를 유지. 현금은 합산.
"""

from __future__ import annotations

import logging

from ..models import Holdings
from .base import HoldingsProvider

logger = logging.getLogger(__name__)


class CompositeHoldingsProvider(HoldingsProvider):
    def __init__(self, providers, *, strict: bool = False):
        self.providers = list(providers)
        self.strict = strict

    def holdings(self) -> Holdings:
        positions, seen = [], set()
        cash = None
        for prov in self.providers:
            try:
                h = prov.holdings()
            except Exception as e:  # noqa: BLE001
                if self.strict:
                    raise
                logger.warning("보유 소스 실패 — 건너뜀: %s", e)
                continue
            for p in h.positions:
                if p.key in seen:
                    logger.warning("중복 종목 %s — 먼저 온 소스 유지", p.key)
                    continue
                seen.add(p.key)
                positions.append(p)
            if h.cash is not None:
                cash = (cash or 0.0) + h.cash
        return Holdings(positions=positions, cash=cash)
