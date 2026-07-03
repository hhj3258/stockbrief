"""KisFlowProvider — 코스피 투자자 수급(외인·기관·개인), 한국투자증권(선택).

pykis PyKis 세션을 받아 일별 투자자매매동향 TR(FHPTJ04040000)을 직접 조회.
'지수 반등 ≠ 바닥' 판정용 — 외인 연속매도일까지 요약.
"""

from __future__ import annotations

from datetime import date

from .base import FlowProvider


def _num(v, scale: float = 1.0):
    try:
        return round(float(str(v).replace(",", "").strip()) * scale, 1)
    except (ValueError, TypeError, AttributeError):
        return None


class KisFlowProvider(FlowProvider):
    def __init__(self, session):
        self.kis = session

    def kospi_flows(self, days: int = 5) -> dict:
        today = date.today().strftime("%Y%m%d")
        resp = self.kis.fetch(
            "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
            params={"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "0001",
                    "FID_INPUT_DATE_1": today, "FID_INPUT_ISCD_1": "KSP",
                    "FID_INPUT_DATE_2": today, "FID_INPUT_ISCD_2": "0001"},
            headers={"tr_id": "FHPTJ04040000"}, domain="real")
        raw = resp.raw() if callable(getattr(resp, "raw", None)) else getattr(resp, "raw", None)
        if not isinstance(raw, dict) or str(raw.get("rt_cd", "1")) != "0":
            mc = raw.get("msg_cd", "") if isinstance(raw, dict) else ""
            m1 = raw.get("msg1", "") if isinstance(raw, dict) else ""
            raise RuntimeError(f"수급 조회 실패: [{mc}] {m1}")
        flows = []
        for r in (raw.get("output") or [])[:days]:
            flows.append({
                "date": r.get("stck_bsop_date"),
                "kospi_close": _num(r.get("bstp_nmix_prpr")),
                "kospi_rate_pct": _num(r.get("bstp_nmix_prdy_ctrt")),
                "foreign_eok": _num(r.get("frgn_ntby_tr_pbmn"), 0.01),
                "individual_eok": _num(r.get("prsn_ntby_tr_pbmn"), 0.01),
                "institution_eok": _num(r.get("orgn_ntby_tr_pbmn"), 0.01),
            })
        return {"market": "KOSPI", "unit": "억원", "flows": flows, "summary": _summarize(flows)}


def _summarize(flows: list[dict]) -> dict:
    if not flows:
        return {}
    today_row = flows[0]
    _dir = lambda v: "n/a" if v is None else ("순매수" if v > 0 else ("순매도" if v < 0 else "보합"))  # noqa: E731
    streak = 0
    for f in flows:
        v = f.get("foreign_eok")
        if v is not None and v < 0:
            streak += 1
        else:
            break
    return {
        "today_foreign": _dir(today_row.get("foreign_eok")),
        "today_institution": _dir(today_row.get("institution_eok")),
        "today_individual": _dir(today_row.get("individual_eok")),
        "foreign_sell_streak_days": streak,
    }


# flow_score 의 정본은 metrics.py 에 있다(중복 제거). 과거 이 경로 import 호환용 재노출.
from ..metrics import flow_score  # noqa: E402,F401
