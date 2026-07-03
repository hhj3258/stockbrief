"""토스 provider 정규화 테스트 — 합성 데이터·고정 환율(네트워크 없음)."""

from stockbrief.integrations.toss import TossHoldingsProvider, _num


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


def test_toss_ignore_symbols():
    p = TossHoldingsProvider(client_id="x", client_secret="y", account_seq=1,
                             fx=1500.0, ignore_symbols=["DRAM"])
    p.raw_holdings = lambda: {"result": {"items": [
        {"symbol": "DRAM", "currency": "USD", "quantity": "1",
         "marketValue": {"amount": "10"}, "profitLoss": {"rate": "0"}},
    ]}}
    assert p.holdings().positions == []
