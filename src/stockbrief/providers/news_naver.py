"""NaverNewsProvider — 네이버 뉴스 검색 API(한국 커버리지↑). 앱 키 필요(선택).

키: NaverNewsProvider(client_id, client_secret) 또는 환경변수 NAVER_CLIENT_ID/SECRET.
키 없으면 사용 측에서 GoogleNewsProvider 로 폴백.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

from .._util import get_json
from ..models import NewsItem
from .base import NewsProvider
from .news_google import _clean, _within

logger = logging.getLogger(__name__)


class NaverNewsProvider(NewsProvider):
    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 limit: int = 6, timeout: int = 10):
        self.cid = client_id or os.environ.get("NAVER_CLIENT_ID")
        self.csec = client_secret or os.environ.get("NAVER_CLIENT_SECRET")
        self.limit, self.timeout = limit, timeout

    @property
    def available(self) -> bool:
        return bool(self.cid and self.csec)

    def search(self, query: str, days: int = 7, asof=None) -> list[NewsItem]:
        if not self.available:
            return []
        now = asof or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff = now - timedelta(days=days)
        url = ("https://openapi.naver.com/v1/search/news.json?"
               + urllib.parse.urlencode({"query": query, "display": 20, "sort": "date"}))
        out: list[NewsItem] = []
        try:
            data = get_json(url, headers={
                "X-Naver-Client-Id": self.cid, "X-Naver-Client-Secret": self.csec,
                "User-Agent": "stockbrief"}, timeout=self.timeout, label=f"Naver news {query!r}")
        except Exception as e:  # noqa: BLE001
            logger.warning("Naver 뉴스 조회 실패 (query=%r): %s", query, e)
            return out
        for it in data.get("items", []):
            ok, date = _within(it.get("pubDate"), cutoff)
            if not ok:
                continue
            link = it.get("originallink") or it.get("link")
            if not link:
                continue
            out.append(NewsItem(date=date, title=_clean(it.get("title")), url=link, source="Naver"))
            if len(out) >= self.limit:
                break
        return out
