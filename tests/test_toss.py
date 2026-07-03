"""토스 provider 정규화 테스트 — 합성 데이터·고정 환율(네트워크 없음)."""

import stockbrief.integrations.toss as toss
from stockbrief.integrations.toss import TossHoldingsProvider, TossQuoteProvider, _num


def test_num():
    assert _num("1,234.5") == 1234.5
    assert _num(None) is None
    assert _num("x") is None


def test_toss_normalization_with_fx():
    # fx 를 고정 float 로 주면 네트워크 없이 결정적. raw_holdings 를 합성 응답으로 대체.
    p = TossHoldingsProvider(client_id="x", client_secret="y", account_seq=1, fx=1500.0)
    p.raw_holdings = lambda: {"result": {"items": [
        {"symbol": "NVDA", "name": "엔비디아", "marketCountry": "US", "currency": "USD",
         "quantity": "2", "averagePurchasePrice": "100",
         "marketValue": {"purchaseAmount": "200", "amount": "240"},
         "profitLoss": {"rate": "0.2"}},
        {"symbol": "069500", "name": "KODEX200", "marketCountry": "KR", "currency": "KRW",
         "quantity": "10", "averagePurchasePrice": "12000",
         "marketValue": {"purchaseAmount": "120000", "amount": "130000"},
         "profitLoss": {"rate": "0.0833"}},
    ]}}
    by = {pos.key: pos for pos in p.holdings().positions}

    nv = by["NVDA"]                       # 미국주 → 원화 환산(×1500)
    assert nv.market == "US" and nv.currency == "KRW"
    assert nv.avg_price_krw == 100 * 1500
    assert nv.eval_amount == 240 * 1500
    assert round(nv.profit_pct, 2) == 20.0

    kr = by["069500"]                     # 한국주 → 그대로
    assert kr.market == "KR" and kr.avg_price_krw == 12000
    assert kr.eval_amount == 130000


def test_toss_quote_provider(monkeypatch):
    """prices(현재가) + candles(일봉) → Quote + 지표. api_get 을 합성 응답으로 대체."""
    monkeypatch.setattr(toss, "get_token", lambda *a, **k: "TOK")

    def fake_get(path, token, **kw):
        params = kw.get("params") or {}
        if path == "/api/v1/prices":
            return {"result": [{"symbol": s, "lastPrice": "100"} for s in params["symbols"].split(",")]}
        if path == "/api/v1/candles":  # 지그재그(상승·하락 공존) → RSI 정의됨
            cs = [{"timestamp": f"2026-06-{d:02d}T00:00:00+09:00", "openPrice": "100",
                   "highPrice": "110", "lowPrice": "80",
                   "closePrice": str(103 if d % 2 == 0 else 97), "volume": "1000"}
                  for d in range(1, 21)]
            return {"result": {"candles": cs, "nextBefore": None}}
        return {"result": {}}
    monkeypatch.setattr(toss, "api_get", fake_get)

    v = TossQuoteProvider(client_id="x", client_secret="y").quotes(["NVDA"])["NVDA"]
    assert v.price == 100.0
    assert v.prev == 97.0                               # 일봉 직전 종가(d=19)
    assert v.rate == round(100 * (100 - 97) / 97, 2)
    assert v.rsi14 is not None                          # 20봉·상하락 공존 → 정의됨
    assert v.w52_low == 80.0 and v.w52_high == 110.0


def test_toss_ignore_symbols():
    p = TossHoldingsProvider(client_id="x", client_secret="y", account_seq=1,
                             fx=1500.0, ignore_symbols=["DRAM"])
    p.raw_holdings = lambda: {"result": {"items": [
        {"symbol": "DRAM", "currency": "USD", "quantity": "1",
         "marketValue": {"amount": "10"}, "profitLoss": {"rate": "0"}},
    ]}}
    assert p.holdings().positions == []
