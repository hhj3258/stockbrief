"""metrics·benchmark·reconcile·retrospect 단위테스트 — 합성 데이터(개인정보 없음)."""

from stockbrief.benchmark import excess_pct, my_value, resolve_fx
from stockbrief.metrics import all_regions, flow_score
from stockbrief.pipeline import _is_similar_title, _title_tokens
from stockbrief.reconcile import reconcile
from stockbrief.retrospect import evaluate

REGIONS = {
    "US": {"sentiment": "cnn_fng", "trend_proxy": "SPY", "flag": "🇺🇸"},
    "JP": {"trend_proxy": "JPX", "flag": "🇯🇵"},
    "global": {"flag": "🌐"},
}
TRADABLE = [
    {"code": "JPX_ETF", "name": "JP idx", "region": "JP", "qty": 1, "eval_amount": 600},
    {"ticker": "AAA", "name": "US a", "market": "US", "region": "US", "qty": 1, "eval_amount": 300},
    {"code": "GOLD", "name": "gold", "region": "global", "qty": 1, "eval_amount": 100},
]
QUOTES = {
    "SPY": {"rsi14": 50, "w52_pos_pct": 60, "ma_align": "혼조", "rate": -1.0, "price": 100},
    "JPX": {"rsi14": 70, "w52_pos_pct": 95, "ma_align": "정배열", "rate": 2.0, "price": 200},
}


def test_all_regions_sentiment_sources():
    r = all_regions(TRADABLE, QUOTES, REGIONS, cnn_score=27.5, investor=None)
    assert r["US"]["detail"]["sentiment_kind"] == "CNN"        # cnn_fng → cnn_score
    assert r["US"]["label"] == "공포 우위"
    assert r["JP"]["detail"]["sentiment_kind"] == "추정"        # trend_proxy → computed
    assert r["global"]["label"] == "N/A"                       # proxy 없음 → N/A


def test_flow_score():
    assert flow_score({"flows": [{"foreign_eok": 1000}], "summary": {"foreign_sell_streak_days": 0}}) == 65
    assert flow_score(None) is None


def test_my_value_and_fx():
    holdings = {"tradable_holdings": [
        {"code": "K", "market": "KR", "qty": 2, "eval_amount": 1000},
        {"ticker": "U", "market": "US", "qty": 3, "eval_amount": 9999},
    ]}
    quotes = {"K": {"price": 600}, "U": {"price": 10}, "_fx": {"USDKRW": 1500}}
    # K: 2*600=1200, U: 3*10*1500=45000 → 46200
    assert my_value(holdings, quotes, fx=resolve_fx(None, quotes)) == 46200
    # quotes 없으면 eval 합
    assert my_value(holdings) == 1000 + 9999
    assert excess_pct(110, 100) == 10.0


def test_reconcile_buy_sell():
    old = {"tradable_holdings": [
        {"code": "K", "name": "k", "market": "KR", "qty": 10, "avg_price": 100, "eval_amount": 1100},
        {"code": "S", "name": "s", "market": "KR", "qty": 5, "avg_price": 200, "eval_amount": 1000},
    ]}
    new = [
        {"code": "K", "name": "k", "market": "KR", "qty": 12, "avg_price": 110, "eval_amount": 1320},  # 매수
        {"code": "S", "name": "s", "market": "KR", "qty": 3, "avg_price": 200, "eval_amount": 600},    # 매도
    ]
    quotes = {"S": {"price": 250}}
    trades, C, merged, warns = reconcile(old, new, quotes, "2026-01-02")
    by = {t["code"]: t for t in trades}
    assert by["K"]["side"] == "buy" and by["K"]["fill_source"] == "avg_backcalc"
    assert by["S"]["side"] == "sell" and by["S"]["fill_estimated"] is True and by["S"]["fill_price"] == 250
    # C = 매수(2*160) - 매도(2*250) = 320 - 500 = -180
    assert by["K"]["fill_price"] == 160 and C == -180
    assert "trades_2026-01-02" in merged


def test_reconcile_us_buy_proxy():
    old = {"tradable_holdings": [{"ticker": "NVDA", "name": "n", "market": "US", "qty": 10, "avg_price_krw": 200000}]}
    new = [{"ticker": "NVDA", "name": "n", "market": "US", "qty": 12, "avg_price_krw": 260000}]  # 미국주 매수
    quotes = {"NVDA": {"price": 200}}  # USD 시세
    t0 = reconcile(old, new, quotes, "2026-07-03", fx=1500)[0][0]           # 기본=평단 역산
    assert t0["fill_source"] == "avg_backcalc" and t0["fill_estimated"] is False
    t1 = reconcile(old, new, quotes, "2026-07-03", fx=1500, us_buy_proxy=True)[0][0]  # 미국주 매수 프록시
    assert t1["fill_source"] == "kis_quote_proxy" and t1["fill_estimated"] is True
    assert t1["fill_price_usd"] == 200 and t1["fill_price_krw"] == 300000


def test_news_title_dedup():
    seen = [_title_tokens("엔비디아 실적 호조에 주가 급등")]
    # 사실상 같은 이슈(토큰 다수 겹침) → 중복
    assert _is_similar_title(_title_tokens("엔비디아 실적 호조에 주가 상승"), seen)
    # 다른 주제 → 중복 아님
    assert not _is_similar_title(_title_tokens("삼성전자 HBM 신규 공급 계약"), seen)


def test_retrospect_verdicts():
    add = evaluate({"name": "x", "start_qty": 10, "start_avg": 100, "end_qty": 12, "end_avg": 110, "now_price": 120})
    assert add["kind"] == "추가매수"
    sell = evaluate({"name": "y", "start_qty": 10, "start_avg": 100, "end_qty": 0, "end_avg": 100,
                     "now_price": 90, "sold_price": 130})
    assert sell["kind"] == "매도" and sell["diff"] > 0   # 130에 팔아 90보다 나음
