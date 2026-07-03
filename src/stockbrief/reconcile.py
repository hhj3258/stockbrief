"""거래 reconcile — 이전/새 보유 diff → trades 자동 복원 + 순현금흐름(결정적).

체결가 자동 복원: 매수=평단 역산(정확), 매도=시세 프록시(fill_estimated), 신규=avg_after.
스크린샷 해석·reason 태그는 호출 측(에이전트) 몫. IO·출력도 호출 측.
"""

from __future__ import annotations

from .lib import avg_of, backcalc_buy_fill, classify_trade, holding_key, qty_of


def _as_tradable(obj):
    """새 보유 입력 정규화: 리스트거나 {tradable_holdings:[...]} 허용."""
    if isinstance(obj, list):
        return obj, None
    return obj.get("tradable_holdings", []), obj.get("account_summary")


def reconcile(old_h, new_obj, quotes, date, fx=None, us_buy_proxy=False):
    """이전/새 보유 diff → (trades, 순현금흐름 C(KRW), 병합결과, warnings).

    us_buy_proxy: True 면 미국주 '매수'도 평단 역산 대신 그날 시세 프록시를 쓴다.
      (토스 API 처럼 평단이 '오늘 환율' 환산이라 역산이 부정확한 소스용.)
    """
    old_t = old_h["tradable_holdings"]
    new_t, new_summary = _as_tradable(new_obj)
    old_by = {holding_key(h): h for h in old_t}
    new_by = {holding_key(h): h for h in new_t}

    trades = []
    cashflow = 0.0
    warnings = []

    keys = list(dict.fromkeys(list(old_by) + list(new_by)))
    for k in keys:
        o = old_by.get(k)
        n = new_by.get(k)
        qb = qty_of(o) if o else 0
        qa = qty_of(n) if n else 0
        side = classify_trade(qb, qa)
        if side == "unchanged":
            continue

        ref = n or o
        is_us = ref.get("market") == "US" or ref.get("ticker")
        name = ref.get("name")
        entry = {"name": name, "side": side, "qty": round(abs(qa - qb), 6),
                 "qty_before": qb, "qty_after": qa, "reason": None}
        if ref.get("code"):
            entry["code"] = ref["code"]
        if ref.get("ticker"):
            entry["ticker"] = ref["ticker"]

        # 매수는 평단 역산(정확). 단 us_buy_proxy 면 미국주 매수도 시세 프록시.
        if side == "buy" and not (us_buy_proxy and is_us):
            avg_a = avg_of(n)
            fill = backcalc_buy_fill(qb, avg_of(o) if o else 0, qa, avg_a)
            entry["fill_price_krw" if is_us else "fill_price"] = round(fill)
            entry["avg_after" + ("_krw" if is_us else "")] = avg_a
            entry["fill_source"] = "avg_backcalc"
            entry["fill_estimated"] = False
            cashflow += (qa - qb) * fill
        else:  # 매도 전체 + (옵션)미국주 매수 → 그날 시세 프록시(추정)
            px = quotes.get(k, {}).get("price")
            sign = 1 if side == "buy" else -1        # 매수=현금유출(+C), 매도=유입(-C)
            dq = abs(qa - qb)
            if px is None:
                warnings.append(f"{name}({k}) {side} — quotes에 시세 없음, fill 미정")
                entry["fill_price"] = None
            elif is_us:
                entry["fill_price_usd"] = px
                if fx:
                    entry["fill_price_krw"] = round(px * fx)
                    cashflow += sign * dq * px * fx
                else:
                    warnings.append(f"{name} {side} US — fx 없어 KRW 환산·C 반영 생략")
            else:
                entry["fill_price"] = px
                cashflow += sign * dq * px
            entry["fill_source"] = "kis_quote_proxy"
            entry["fill_estimated"] = True
            if qa > 0:
                entry["avg_after" + ("_krw" if is_us else "")] = avg_of(n)

        trades.append(entry)

    merged = dict(old_h)
    merged["tradable_holdings"] = new_t
    merged["last_updated"] = date
    merged["stale"] = False
    if new_summary:
        merged["account_summary"] = new_summary
    merged[f"trades_{date}"] = trades
    return trades, round(cashflow), merged, warnings
