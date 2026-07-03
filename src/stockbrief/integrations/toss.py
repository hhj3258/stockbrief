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
from ..indicators import indicators_from_ohlcv
from ..models import Holdings, Position, Quote
from ..pipeline import Advisor
from ..providers.base import HoldingsProvider, QuoteProvider
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


# 토스는 "클라이언트당 유효 토큰 1개"(재발급 시 이전 토큰 무효) → 프로세스 내 공유 캐시.
# 보유·시세 provider 가 각자 발급하면 서로 무효화되므로 (client_id, base_url) 별로 한 번만 발급.
_token_cache: dict = {}


def get_token(client_id: str, client_secret: str, *, base_url: str = _BASE, timeout: int = 15) -> str:
    """공유 access_token(캐시). 여러 토스 provider 가 같은 토큰을 쓰게 한다."""
    key = (client_id, base_url)
    tok = _token_cache.get(key)
    if not tok:
        tok = retry_call(lambda: issue_token(client_id, client_secret, base_url=base_url, timeout=timeout),
                         label="Toss token")
        _token_cache[key] = tok
    return tok


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
        if not (self.client_id and self.client_secret):
            raise RuntimeError("TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 가 필요합니다(환경변수).")
        return get_token(self.client_id, self.client_secret, base_url=self.base_url)

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


class TossQuoteProvider(QuoteProvider):
    """토스 Market Data 시세·지표 — 보유와 같은 토큰 공유(KIS 시세와 동등 역할).

    /api/v1/prices(현재가 배치) + /api/v1/candles(일봉) → Quote + RSI·이동평균·52주.
    지표엔 pandas 필요(없으면 현재가만). 국내(6자리)·미국(티커) 모두 지원.
    """

    _MAX_PER_CALL = 200   # 토스 candles count 상한

    def __init__(self, client_id: str | None = None, client_secret: str | None = None, *,
                 ohlcv_count: int = 252, base_url: str = _BASE, timeout: int = 15):
        self.client_id = client_id or os.environ.get("TOSS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("TOSS_CLIENT_SECRET")
        self.ohlcv_count = ohlcv_count   # 52주(≈252거래일) — max 200/콜이라 페이지네이션
        self.base_url = base_url
        self.timeout = timeout

    def _tok(self) -> str:
        if not (self.client_id and self.client_secret):
            raise RuntimeError("TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 가 필요합니다(환경변수).")
        return get_token(self.client_id, self.client_secret, base_url=self.base_url)

    def _candles(self, code: str, token: str):
        import pandas as pd
        rows, before = [], None
        while len(rows) < self.ohlcv_count:   # 200/콜 상한 → nextBefore 로 과거 페이지 이어받기
            params = {"symbol": code, "interval": "1d",
                      "count": min(self._MAX_PER_CALL, self.ohlcv_count - len(rows))}
            if before:
                params["before"] = before
            res = (api_get("/api/v1/candles", token, base_url=self.base_url,
                           timeout=self.timeout, params=params).get("result") or {})
            batch = res.get("candles") or []
            rows.extend(batch)
            before = res.get("nextBefore")
            if not batch or not before:
                break
        if not rows:
            return None
        df = pd.DataFrame([{
            "open": _num(c.get("openPrice")), "high": _num(c.get("highPrice")),
            "low": _num(c.get("lowPrice")), "close": _num(c.get("closePrice")),
            "volume": _num(c.get("volume")), "ts": c.get("timestamp"),
        } for c in rows]).drop_duplicates("ts").sort_values("ts")   # 오름차순(최신이 마지막)
        return df[["open", "high", "low", "close", "volume"]].reset_index(drop=True)

    def quotes(self, keys, markets=None) -> dict[str, Quote]:
        keys = list(keys)
        if not keys:
            return {}
        token = self._tok()
        prices = {}
        try:  # 현재가 배치(최대 200)
            resp = api_get("/api/v1/prices", token, base_url=self.base_url, timeout=self.timeout,
                           params={"symbols": ",".join(keys)})
            prices = {r.get("symbol"): r for r in (resp.get("result") or [])}
        except Exception as e:  # noqa: BLE001
            logger.warning("토스 현재가 조회 실패: %s", e)
        out: dict[str, Quote] = {}
        for code in keys:
            price = _num((prices.get(code) or {}).get("lastPrice"))
            if price is None:
                continue
            q = Quote(key=code, price=price)
            try:  # 일봉 → 지표 + 전일종가/등락률(pandas 없으면 현재가만)
                df = self._candles(code, token)
                if df is not None and len(df):
                    q.set_indicators(indicators_from_ohlcv(df, price))
                    if len(df) >= 2:
                        q.prev = float(df["close"].iloc[-2])
                        q.rate = round(100.0 * (price - q.prev) / q.prev, 2) if q.prev else None
            except Exception as e:  # noqa: BLE001
                logger.debug("토스 일봉/지표 실패 (%s): %s", code, e)
            out[code] = q
        return out


def build_briefing(
    provider: TossHoldingsProvider | None = None, *, config: AdvisorConfig | None = None,
    region_map: dict | None = None, ignore_symbols=None,
    quotes=None, sentiment=None, news=None, naver_news=None, fx=None, flow=None,
    out_dir: str | Path | None = None, date: str | None = None,
    title: str = "보유주식 데일리 브리핑",
) -> dict:
    """토스 보유로 브리핑 마크다운 생성(+선택 파일 저장). 반환 {markdown, path?, date}.

    quotes 미지정 시 **토스 시세(TossQuoteProvider)** 를 자동 사용 — 토스만 붙여도 보유+시세 완결.
    (다른 시세를 원하면 quotes=CompositeQuoteProvider(...) 등을 넘긴다.)
    sentiment/news/fx 미지정 시 키 불필요 기본(CNN·Google·ECB) 사용.
    """
    config = config or AdvisorConfig.default()
    date = date or datetime.now().strftime("%Y-%m-%d")
    holdings = provider or TossHoldingsProvider(region_map=region_map, ignore_symbols=ignore_symbols)
    advisor = Advisor(
        config, holdings,
        quotes=quotes if quotes is not None else TossQuoteProvider(),
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
