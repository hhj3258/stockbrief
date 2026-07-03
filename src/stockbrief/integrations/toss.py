"""토스증권(Toss Securities) Open API 연동 — 잔고로 보유를 자동 조회.

토스증권 WTS(설정 > Open API)에서 발급한 client_id/client_secret 으로 OAuth2 토큰을 받아
본인 계좌 보유종목을 정규화 Holdings 로 바꾼다. **읽기 전용** — 주문(Order) API 는 쓰지 않는다.

자격증명은 환경변수 TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 로 (코드·리포에 넣지 말 것).

    from stockbrief.integrations.toss import TossHoldingsProvider, build_briefing
    res = build_briefing(TossHoldingsProvider(), out_dir="out")   # out/briefing_YYYYMMDD.md
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .._util import retry_call
from ..briefing import build_markdown
from ..config import AdvisorConfig
from ..models import Holdings, Position
from ..pipeline import Advisor
from ..providers.base import HoldingsProvider
from ..providers.fx_free import FreeFxProvider
from ..providers.news_google import GoogleNewsProvider
from ..providers.sentiment_cnn import CnnFngProvider

logger = logging.getLogger(__name__)

_BASE = "https://openapi.tossinvest.com"


def issue_token(client_id: str, client_secret: str, *, base_url: str = _BASE, timeout: int = 15) -> str:
    """OAuth2 Client Credentials → access_token(24h). refresh 없음 — 만료 시 재발급."""
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id, "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        base_url + "/oauth2/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["access_token"]


def api_get(path: str, token: str, *, account_seq=None, params: dict | None = None,
            base_url: str = _BASE, timeout: int = 15) -> dict:
    """GET 호출 — 계좌/자산 API 는 X-Tossinvest-Account 헤더(accountSeq) 필요."""
    url = base_url + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Authorization": f"Bearer {token}"}
    if account_seq is not None:
        headers["X-Tossinvest-Account"] = str(account_seq)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return json.load(r)


def _num(v):
    try:
        return float(str(v).replace(",", "")) if v is not None else None
    except (TypeError, ValueError):
        return None


class TossHoldingsProvider(HoldingsProvider):
    """토스 잔고 → 정규화 Holdings.

    client_id/secret 미지정 시 환경변수(TOSS_CLIENT_ID/SECRET). account_seq 미지정 시 첫 계좌.
    region_map: 종목→기반시장(미지정 시 marketCountry). ignore_symbols: 제외 종목.
    """

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 account_seq=None, *, region_map: dict | None = None,
                 ignore_symbols=None, fx=None, base_url: str = _BASE):
        self.client_id = client_id or os.environ.get("TOSS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("TOSS_CLIENT_SECRET")
        self.account_seq = account_seq
        self.region_map = region_map or {}
        self.ignore = set(ignore_symbols or [])
        self.fx = fx   # USD→KRW 환산: float 환율 | FxProvider | None(→FreeFxProvider 자동)
        self.base_url = base_url
        self._token = None

    def _usdkrw(self):
        if isinstance(self.fx, (int, float)):
            return float(self.fx)
        if self.fx is not None and hasattr(self.fx, "usdkrw"):
            return self.fx.usdkrw()
        from ..providers.fx_free import FreeFxProvider
        return FreeFxProvider().usdkrw()

    def accounts(self) -> list:
        return api_get("/api/v1/accounts", self._tok(), base_url=self.base_url).get("result") or []

    def _tok(self) -> str:
        if not self._token:
            if not (self.client_id and self.client_secret):
                raise RuntimeError("TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 가 필요합니다(환경변수).")
            self._token = retry_call(
                lambda: issue_token(self.client_id, self.client_secret, base_url=self.base_url),
                label="Toss token")
        return self._token

    def _seq(self, token):
        if self.account_seq is None:
            accts = api_get("/api/v1/accounts", token, base_url=self.base_url).get("result") or []
            if not accts:
                raise RuntimeError("토스 계좌가 없습니다.")
            self.account_seq = accts[0].get("accountSeq")
        return self.account_seq

    def raw_holdings(self) -> dict:
        """원본 /holdings 응답(스키마 확인·디버그용)."""
        token = self._tok()
        return api_get("/api/v1/holdings", token, account_seq=self._seq(token), base_url=self.base_url)

    def holdings(self) -> Holdings:
        result = self.raw_holdings().get("result") or {}
        items = [it for it in (result.get("items") or [])
                 if it.get("symbol") and it.get("symbol") not in self.ignore]
        # 종목별 값은 원통화(native)로 온다(미국주=USD). 계좌 요약의 krw 는 0 이라 못 쓴다 →
        # 미국주는 환율로 원화 환산해 KRW 로 통일(비중·합계 계산이 한 통화라야 함).
        rate = None
        if any((it.get("currency") or "").upper() == "USD" for it in items):
            rate = self._usdkrw()
            if not rate:
                logger.warning("USD 보유가 있으나 환율 조회 실패 — 미국 종목을 원통화 값 그대로 사용")
        positions = []
        for it in items:
            cur = (it.get("currency") or "KRW").upper()
            market = (it.get("marketCountry") or ("US" if cur == "USD" else "KR")).upper()
            qty = _num(it.get("quantity")) or 0.0
            conv = rate if (cur == "USD" and rate) else 1.0
            mv = it.get("marketValue") or {}
            amount = _num(mv.get("amount"))                     # 총 평가액(원통화)
            avg_native = _num(it.get("averagePurchasePrice"))   # 주당 평단(원통화)
            if avg_native is None:
                purchase = _num(mv.get("purchaseAmount"))       # 총 매수금액(원통화)
                avg_native = (purchase / qty) if (purchase and qty) else None
            rate_pl = _num((it.get("profitLoss") or {}).get("rate"))  # 예: -0.2546 → -25.46%
            positions.append(Position(
                key=it["symbol"], name=it.get("name") or it["symbol"], market=market,
                region=self.region_map.get(it["symbol"], market),
                qty=qty,
                avg_price_krw=(avg_native * conv) if avg_native is not None else None,
                currency="KRW" if (cur == "KRW" or conv != 1.0) else cur,
                eval_amount=(amount * conv) if amount is not None else None,
                profit_pct=(rate_pl * 100 if rate_pl is not None else None),
            ))
        return Holdings(positions=positions, cash=None)


def build_briefing(
    provider: TossHoldingsProvider | None = None, *, config: AdvisorConfig | None = None,
    region_map: dict | None = None, ignore_symbols=None,
    quotes=None, sentiment=None, news=None, naver_news=None, fx=None, flow=None,
    out_dir: str | Path | None = None, date: str | None = None,
    title: str = "보유주식 데일리 브리핑",
) -> dict:
    """토스 보유로 브리핑 마크다운 생성(+선택 파일 저장). 반환 {markdown, path?, date}.

    quotes 미지정 시 시세 단계는 graceful skip — 키 불필요 시세는 CompositeQuoteProvider 를 넘긴다.
    sentiment/news/fx 미지정 시 키 불필요 기본(CNN·Google·ECB) 사용.
    """
    config = config or AdvisorConfig.default()
    date = date or datetime.now().strftime("%Y-%m-%d")
    holdings = provider or TossHoldingsProvider(region_map=region_map, ignore_symbols=ignore_symbols)
    advisor = Advisor(
        config, holdings,
        quotes=quotes,
        fx=fx or FreeFxProvider(),
        sentiment=sentiment or CnnFngProvider(),
        news=news or GoogleNewsProvider(),
        naver_news=naver_news,
        flow=flow,
    )
    md = build_markdown(advisor.run(), config, title=title, date=date)
    out = {"markdown": md, "date": date, "path": None}
    if out_dir:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"briefing_{date.replace('-', '')}.md"
        path.write_text(md, encoding="utf-8")
        out["path"] = str(path)
    return out
