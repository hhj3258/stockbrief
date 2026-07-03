# StockBrief 사용법

보유 종목과 시장 데이터를 받아 데일리 브리핑을 만듭니다. 데이터 소스(provider)를 끼워 쓰는 구조라 **필요한 것만** 연결하면 됩니다.
(전체 개요는 [README](../README.md), 내부 구조는 [ARCHITECTURE](../ARCHITECTURE.md)를 보세요. 용어는 README의 "핵심 개념"에 정리해 두었습니다.)

---

## 1. 설치

```bash
pip install "stockbrief[quotes-kr,quotes-us]"   # 무료 시세(pykrx·yfinance·pandas)
pip install "stockbrief[kis]"                   # 한국투자증권 시세·잔고(pykis)
pip install "stockbrief[all]"                   # 전부
# 개발용: pip install -e ".[dev]" 뒤  python -m pytest
```

계산 코어(`stockbrief.lib`·`metrics`·`benchmark`·`reconcile`·`retrospect`·`config`·`models`)는 **표준 라이브러리만** 씁니다. pandas·pykrx·yfinance·pykis는 시세 provider를 쓸 때만 필요합니다.

---

## 2. 가장 빠른 길 — Advisor

`Advisor`가 provider들을 묶어 `run()` 한 번에 브리핑 입력을 만듭니다. **넘긴 provider만 쓰고, 없는 것은 건너뜁니다.**

```python
from stockbrief.config import AdvisorConfig
from stockbrief.pipeline import Advisor
from stockbrief.briefing import build_markdown
from stockbrief.providers import DictHoldingsProvider, FreeFxProvider, CnnFngProvider, GoogleNewsProvider
from stockbrief.providers.quotes_composite import CompositeQuoteProvider
from stockbrief.providers.quotes_pykrx import PykrxQuoteProvider
from stockbrief.providers.quotes_yf import YfinanceQuoteProvider

advisor = Advisor(
    config=AdvisorConfig.default(),
    holdings=DictHoldingsProvider([...]),                         # 필수
    quotes=CompositeQuoteProvider({"KR": PykrxQuoteProvider(),    # 선택
                                   "US": YfinanceQuoteProvider()}),
    fx=FreeFxProvider(),         # 선택 — 미국 종목 평가액의 원화 환산
    sentiment=CnnFngProvider(),  # 선택 — 미국 투자 심리(Fear & Greed)
    news=GoogleNewsProvider(),   # 선택 — 종목 뉴스
    naver_news=None,             # 선택 — 한국 상장 종목은 네이버로
    flow=None,                   # 선택 — 코스피 수급(KisFlowProvider)
)
inputs = advisor.run(news_days=7)        # → BriefingInputs
md = build_markdown(inputs, advisor.config, title="오늘 브리핑", date="2026-06-15")
```

`run()`이 돌려주는 **BriefingInputs**는 대시보드나 LLM이 바로 쓸 수 있는 구조화 데이터입니다.

| 필드 | 내용 |
|---|---|
| `regions` | 시장별 국면 `{region: {flag, weight_pct, n, label, tone, detail}}` |
| `weights` | 종목 비중 `{key: {name, eval, weight_pct}}` |
| `overheat` | `(ratio, hot, have)` — 과열도(RSI 70 초과 종목 비율) |
| `quotes` | `{key: 시세 dict}` (price·rate·rsi14·ma·ma_align·w52_*) — 환율은 별도 `fx` 필드 |
| `news` | `{key: [NewsItem...]}` |
| `fx`·`sentiment`·`flow`·`total_eval`·`holdings`·`tradable` | 부가 데이터 |

---

## 2.5. 증권사 0..N개 조립 — `assemble` (권장 진입점)

provider를 하나씩 손으로 묶는 대신, **증권사(Brokerage)를 0..N개** 넘기면 `assemble`이 알아서 조립합니다.
빠진 자리는 키리스 기본으로 채우므로 **증권사 0개여도 완전 동작**합니다.

```python
from stockbrief import Advisor, AdvisorConfig, build_markdown, assemble, TossBrokerage, KisBrokerage
from stockbrief.providers import JsonHoldingsProvider

# 증권사 0개 — 보유만 직접, 나머지는 무료 소스(pykrx·yfinance·CNN·Google·ECB)
provs = assemble([], holdings=JsonHoldingsProvider("holdings.json"))

# 증권사 N개 — 보유 자동 병합, 시세는 증권사 것, 빠진 자리는 키리스
provs = assemble([TossBrokerage(),                                   # 토스: 보유+시세
                  KisBrokerage(kis_session, quote_fn=..., ohlcv_fn=...)])  # KIS: 보유+시세+수급

md = build_markdown(Advisor(AdvisorConfig.default(), **provs).run(), AdvisorConfig.default())
# 한 줄 단축: Advisor.from_brokerages(AdvisorConfig.default(), [TossBrokerage()])
```

`assemble` 우선순위: **보유** = 증권사들 + `holdings=` 전부 병합(2개↑면 `CompositeHoldingsProvider`, 없으면 에러) · **시세** = `quotes=` → 증권사 첫 시세 → 키리스(pykrx/yf, `keyless_quotes=False`로 끔) · **수급** = `flow=` → 증권사 첫 flow → 없으면 비활성 · **심리·뉴스·환율** = 인자 없으면 키리스 기본.

내장 브로커: **토스증권**(보유+시세) · **한국투자증권**(보유+시세+수급). 새 증권사 = `Brokerage` 하나 구현(`holdings()` 필수, `quotes()`/`flow()`는 있으면).

---

## 3. 보유 종목(Holdings) 주입 — 가장 중요

브리핑의 유일한 **필수** 입력입니다. 정규화된 형태(`Position`)로만 들어가면 어떤 소스든 됩니다.

### 3a. 딕셔너리 리스트 (메모리)
```python
from stockbrief.providers import DictHoldingsProvider
DictHoldingsProvider([
    {"code": "069500", "name": "KODEX200", "market": "KR", "region": "KR",
     "qty": 1, "avg_price": 120000, "eval_amount": 129270, "profit_pct": 7.7},
    {"ticker": "NVDA", "name": "엔비디아", "market": "US", "region": "US",
     "qty": 1, "avg_price_krw": 200000, "eval_amount": 311000, "profit_pct": 55.0},
], cash=1_000_000)
```
- 한국 종목은 `code` + `avg_price`, 미국 종목은 `ticker` + `avg_price_krw`(원화로 환산한 평균 매수가)를 씁니다.
- `region`을 생략하면 `market` 값을 씁니다. `eval_amount`·`profit_pct`는 선택이며, 있으면 표와 비중 계산에 쓰입니다.

### 3b. JSON 파일
```python
from stockbrief.providers import JsonHoldingsProvider
JsonHoldingsProvider("holdings.json")   # {"tradable_holdings": [...], "trades_*": [...], "context_assets": {...}}
```

### 3c. 증권사 잔고 API (직접 어댑터)
`HoldingsProvider`를 구현해 `holdings() -> Holdings`만 돌려주면 됩니다. 바로 제공되는 어댑터:
- **한국투자증권**: `integrations.kis.KisHoldingsProvider`(pykis 세션 → 7절).
- **토스증권**: `integrations.toss.TossHoldingsProvider`(보유) + `TossQuoteProvider`(시세) — 토스 Open API(OAuth2). `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET` 환경변수. 읽기 전용(주문 API 미사용), 미국주는 환율로 원화 환산. **토스만 붙여도 보유+시세 완결** — `build_briefing(kis_or_toss_session)`은 시세 미지정 시 `TossQuoteProvider`를 자동 사용(KIS와 동등).

### 3d. 여러 계좌 병합 (`CompositeHoldingsProvider`)
보유가 여러 증권사에 나뉘어 있으면 각 provider 를 합칩니다(한 소스 실패 시 나머지로 진행).
```python
from stockbrief.providers import CompositeHoldingsProvider, JsonHoldingsProvider
from stockbrief.integrations.toss import TossHoldingsProvider
holdings = CompositeHoldingsProvider([
    TossHoldingsProvider(),               # 미국주(토스 API)
    JsonHoldingsProvider("kb.json"),      # 한국주(다른 증권사, 수동/외부)
])
```

---

## 4. provider 카탈로그

```python
# 시세
from stockbrief.providers.quotes_pykrx import PykrxQuoteProvider       # 한국, 키 0개
from stockbrief.providers.quotes_yf import YfinanceQuoteProvider       # 미국, 키 0개
from stockbrief.providers.quotes_composite import CompositeQuoteProvider  # market별 라우팅
from stockbrief.providers.quotes_kis import KisQuoteProvider           # 선택: KisQuoteProvider(session, get_quote, get_daily_ohlcv)
from stockbrief.integrations.toss import TossQuoteProvider             # 선택: 토스 Market Data(현재가+일봉→지표). TOSS_CLIENT_ID/SECRET
# 환율·심리·뉴스·수급
from stockbrief.providers import FreeFxProvider, CnnFngProvider, GoogleNewsProvider
from stockbrief.providers.news_naver import NaverNewsProvider          # NaverNewsProvider(client_id, client_secret) 또는 NAVER_CLIENT_ID/SECRET 환경변수
from stockbrief.providers.flow_kis import KisFlowProvider              # KisFlowProvider(pykis_session)
```
- **네이버 키가 없으면** Advisor가 자동으로 구글 뉴스로 대체합니다.
- **시세 provider가 없으면** 국면을 보유 정보만으로 제한 판정합니다(추세·과열도 미산출). 환율이 없으면 미국 종목 평가액은 입력값을 그대로 씁니다.

---

## 5. 설정 (AdvisorConfig)

```python
from stockbrief.config import AdvisorConfig
cfg = AdvisorConfig.default()                    # 내장 기본값(US/KR/JP/CN/global)
cfg = AdvisorConfig.from_yaml("stockbrief.yaml") # YAML에서
cfg = AdvisorConfig.from_dict({...})             # dict에서
```
주요 키:
```yaml
regions:                       # 시장 목록(확장 지점) — 시장 추가 = 여기 한 줄 + 보유에 region 태그
  US: { sentiment: cnn_fng, trend_proxy: "360750", flag: "🇺🇸" }
  KR: { trend_proxy: "069500", flow: kis, flag: "🇰🇷" }
  JP: { trend_proxy: "241180", flag: "🇯🇵" }
instrument_themes: { "069500": 한국대형지수, ... }   # 종목 → 테마(집중도 계산용)
high_vol_themes: [우주테크, 양자컴퓨팅]               # 고변동 테마는 비중 점수 −0.5
news_queries:                                       # 종목별 검색어
  "NVDA": { primary: 엔비디아, kr: [AI 반도체, HBM], en: [NVIDIA] }
thresholds: { stop_loss_pct: -10, max_position_pct: 30, target_cash_pct: 25, rsi_overheat: 70 }
```
- `trend_proxy`: 그 시장의 추세를 판정할 때 쓰는 대표 지수 종목코드(시세 필요).
- `sentiment: cnn_fng`로 지정한 시장만 CNN 지수를 쓰고, 나머지는 지표로 심리를 자체 추정합니다(README "용어"의 투자 심리 지수 참고).

---

## 6. 계산 코어만 쓰기 (provider 없이)

브리핑 파이프라인 없이 계산식만 필요하면 직접 호출하면 됩니다.
```python
from stockbrief.lib import (region_regime, star_score, star_breakdown,
                            weights, overheat_ratio, portfolio_concentration)
from stockbrief.metrics import all_regions
from stockbrief.benchmark import my_value, resolve_fx, excess_pct
from stockbrief.reconcile import reconcile          # 보유 변화 → 거래 복원 + 순현금흐름
from stockbrief.retrospect import evaluate          # 회고 % 평가

region_regime(27.5, "혼조", -1.2, 0.0)               # → ("공포 우위", {...})
star_score(4, 3.5, 4.5, 3.5)                         # → 3.5
star_breakdown(4, 3.5, 4.5, 3.5)                     # → "왜 이 점수인가" 컴포넌트별 기여도 + stars
all_regions(tradable, quotes, cfg.regions, cnn_score=34.0, investor=flow)
portfolio_concentration(tradable, theme_map={"AI": ["NVDA"]})  # 종목·시장·테마 비중 + 집중 경고
```
- **별점 근거**: `star_breakdown(...)` → `{components: {thesis|value_trend|weight_fit|relative: {raw, weight, contribution}}, raw_total, stars}`. 최종 별점은 `star_score`와 동일하고, 어느 요소가 점수를 끌어올렸는지 노출합니다.
- **포트폴리오 집중도**: `portfolio_concentration(...)` → 단일 종목·기반시장·테마 비중과 임계 초과 경고(`flags`). 시장 국면 자체의 판단 근거는 `all_regions(...)[region]["detail"]`(F&G 점수·추세 등)에 이미 담겨 있습니다.

---

## 7. 한국투자증권(KIS) 계좌 연동

[pykis](https://github.com/Soju06/python-kis) 세션을 넘기면 보유 종목을 KIS 잔고에서 자동으로 읽어 브리핑 파일을 만듭니다.
```python
from stockbrief.integrations.kis import build_briefing
from stockbrief.providers.quotes_composite import CompositeQuoteProvider
from stockbrief.providers.quotes_pykrx import PykrxQuoteProvider
from stockbrief.providers.quotes_yf import YfinanceQuoteProvider
from stockbrief.providers.flow_kis import KisFlowProvider

result = build_briefing(
    kis,                                   # pykis 세션(본인 KIS 앱키·계좌)
    quotes=CompositeQuoteProvider({"KR": PykrxQuoteProvider(), "US": YfinanceQuoteProvider()}),  # 키 0개 시세(선택)
    region_map={"360750": "US", "241180": "JP"},   # 한국 상장이지만 기반 시장이 다른 종목
    flow=KisFlowProvider(kis),             # 코스피 수급(선택)
    out_dir="out",
)
# result = {"markdown", "path": "out/briefing_YYYYMMDD.md", "date"}
```
- 보유만 KIS로 읽고, 시세는 키가 필요 없는 pykrx·yfinance로 섞어 쓸 수 있습니다. 시세까지 KIS로 하려면 `quotes=KisQuoteProvider(...)`를 넘기면 됩니다.
- 만들어진 마크다운을 웹 대시보드·메신저 등에 그대로 띄우면 됩니다(예: `examples/kis_account.py`).

---

## 8. 판단·서술 스킬 (선택)

StockBrief는 **데이터와 계산**까지만 합니다. 사고팔지에 대한 **판단 + 종목 점수 + 설명 문장**이 필요하면, `skills/`에 들어 있는 Claude 스킬을 쓰는 프로젝트의 `.claude/skills/`로 복사하세요. 스킬이 BriefingInputs(또는 마크다운)을 받아 4요소 종목 점수·매매 액션·리밸런싱·'오늘의 고찰'을 작성합니다. (계산은 패키지, 판단은 스킬)

---

## 9. 레시피

- **키 0개로 전체 브리핑**: 2절 코드 그대로 (pykrx·yfinance·CNN·구글·환율).
- **한국 종목만**: `quotes=PykrxQuoteProvider()`, 미국 종목이 없으면 yfinance는 필요 없습니다.
- **시세 없이 가볍게**: `quotes=None` → 보유·비중·뉴스만(국면은 제한 판정).
- **KIS 정밀**: `quotes=KisQuoteProvider(session, get_quote, get_daily_ohlcv)` + `flow=KisFlowProvider(session)`.
- **한국 뉴스 강화**: `naver_news=NaverNewsProvider()` (NAVER_CLIENT_ID/SECRET) — 한국 상장 종목은 네이버로 검색합니다.

## 10. 운영 확장 (재시도·상태저장·LLM 산문·배포)

- **재시도 + 자동 건너뜀**: 무료 네트워크 provider(CNN·Google·Naver)는 일시 실패 시 짧은 백오프로 1회 재시도하고, 끝내 실패하면 그 섹션만 건너뛰고 **브리핑 전체는 강행**합니다(graceful degrade). 원인은 `logging`으로 노출.
- **임계값 튜닝**: `thresholds.rsi_overheat`(과열 RSI 기준)를 비롯한 임계값을 `AdvisorConfig`로 덮어쓸 수 있습니다. `from_dict({"thresholds": {...}})` 또는 YAML.
- **LLM 산문(선택)**: 패키지는 키·벤더를 다루지 않습니다. 마크다운을 사용자 LLM 콜러블로 산문화:
  ```python
  from stockbrief.llm import summarize
  text = summarize(build_markdown(advisor.run(), cfg), my_llm_fn)   # my_llm_fn(prompt)->str
  ```
- **상태 저장(벤치마크·알파)**: 일별 평가액을 누적 기록해 어제·지난주 대비 변화율을 계산합니다.
  ```python
  from stockbrief.state import StateStore
  st = StateStore("state.json"); st.record("2026-06-15", total_eval=12_500_000)
  st.change_pct("2026-06-08")          # 지난주 대비 %
  ```
- **배포 템플릿**: `examples/telegram_bot.py`(키리스 브리핑 → 텔레그램) + `examples/github-actions-daily.yml`(매일 09:30 KST cron). 서버 없이 봇 구축.

## 11. 주의

- 정보 제공용입니다. 매매·주문 기능은 없습니다.
- 평균 매수가·평가액은 입력 통화 기준입니다(미국 종목은 원화로 환산한 평균 매수가를 권장). 비교는 % 기준이라 통화만 맞으면 됩니다.
- 무료 시세는 지연되거나 장 막판 값이 다를 수 있습니다. 장중 실시간 정밀도가 필요하면 KIS provider를 쓰세요.
- 자체 추정 투자 심리(한국·일본·중국)는 **공식 지수가 아닙니다** — RSI·52주 위치·추세(+수급)를 합성한 값입니다.
