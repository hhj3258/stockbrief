"""작은 공용 유틸 — 네트워크 일시 오류 자동 재시도.

무료 스크래핑 provider(CNN·Google·Naver 등)는 일시적 트래픽 제한·네트워크 흔들림으로
간헐 실패한다. 짧은 백오프로 1회 더 시도해 성공률을 올린다. 끝내 실패하면 예외를 그대로
올리고, 호출 측(provider)이 잡아 graceful degrade(빈 결과) 한다 → 브리핑 전체는 강행.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)


def retry_call(fn, *, attempts: int = 2, base_delay: float = 0.6,
               exceptions: tuple = (Exception,), label: str = ""):
    """fn() 을 최대 attempts 회 시도. 실패 사이에 base_delay*i 초 대기(선형 백오프).

    마지막 시도까지 실패하면 마지막 예외를 raise. attempts=1 이면 재시도 없음.
    """
    last = None
    for i in range(1, max(1, attempts) + 1):
        try:
            return fn()
        except exceptions as e:  # noqa: BLE001
            last = e
            if i < attempts:
                logger.debug("%s 재시도 %d/%d: %s", label or "call", i, attempts, e)
                time.sleep(base_delay * i)
    raise last


def get_json(url: str, *, headers: dict | None = None, timeout: int = 10,
             attempts: int = 2, label: str = ""):
    """네트워크 GET → JSON. 일시 오류는 retry_call 로 재시도(모든 JSON provider 공용)."""
    def _do():
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    return retry_call(_do, attempts=attempts, label=label or url)
