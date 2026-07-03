# StockBrief

![python](https://img.shields.io/badge/python-3.10+-blue) ![license](https://img.shields.io/badge/license-MIT-green) ![status](https://img.shields.io/badge/status-alpha-orange)

**보유 종목과 시장 데이터를 모아 매일 포트폴리오 브리핑을 만들어 주는 Python 라이브러리입니다.**

시세·투자 심리·뉴스·환율·수급을 받아 **시장별 국면, 종목 점수, 관련 뉴스, 집중도**를 한 장의 브리핑으로 묶어 줍니다. **API 키가 없어도** 무료 데이터 소스만으로 전부 동작하고, 한국투자증권(KIS)·네이버 키를 끼우면 정밀도가 올라갑니다.

> ⚠️ 정보 제공용 계산 도구입니다. 투자 자문이 아니고, 매매·주문 기능도 없습니다.
> 아직 alpha 단계입니다 — 계산 코어와 데이터 연동은 테스트를 거쳤지만 공개 API는 바뀔 수 있습니다.

## 왜 StockBrief인가?

직접 `yfinance`를 호출해 표를 그리는 것과 무엇이 다른가:

- **키 없이 바로 시작** — `pip install` 후 무료 소스(pykrx·yfinance·CNN·구글)만으로 풀 브리핑. 증권사 API 신청·환경 구성 없이 5분.
- **한국 투자자를 위한 설계** — `market`(상장지)과 `region`(기반시장)을 분리합니다. 국내 상장 해외 ETF(미국S&P500·니케이225 ETF 등)를 "어디 상장됐나"가 아니라 **"어느 시장에 베팅하나"**로 올바르게 판정 — 직접 만들면 놓치기 쉬운 부분.
- **믿을 수 있는 숫자** — 비중·국면·별점·과열도·집중도는 입력이 같으면 출력도 같은 **결정적 계산**(테스트 26개). LLM 환각이 끼어들 여지가 없고, "왜 4점?"은 `star_breakdown`이 요소별 기여도로 답합니다.
- **데이터가 아니라 '브리핑'** — 시세 나열이 아니라 시장별 국면·종목 비중·집중도·관련 뉴스를 한 장으로 묶고, **LLM에 그대로 먹일 수 있는 구조화 입력**까지 같이 줍니다.
- **벤더 락인 없음** — 무료로 시작해 필요할 때 한국투자증권·네이버를 한 줄로 끼웁니다. provider만 갈아끼우면 코드 뼈대는 그대로.
- **운영까지 포함** — 일시 실패 자동 재시도 + graceful degrade, 일별 상태 저장, 텔레그램·GitHub Actions 템플릿. 서버 없이 매일 아침 봇.

## 빠른 시작

```python
from stockbrief.config import AdvisorConfig
from stockbrief.pipeline import Advisor
from stockbrief.briefing import build_markdown
from stockbrief.providers import DictHoldingsProvider, FreeFxProvider, CnnFngProvider, GoogleNewsProvider
from stockbrief.providers.quotes_composite import CompositeQuoteProvider
from stockbrief.providers.quotes_pykrx import PykrxQuoteProvider
from stockbrief.providers.quotes_yf import YfinanceQuoteProvider

advisor = Advisor(
    AdvisorConfig.default(),
    holdings=DictHoldingsProvider([
        {"code": "069500", "name": "KODEX200", "market": "KR", "region": "KR", "qty": 1, "avg_price": 120000, "eval_amount": 129270},
        {"ticker": "NVDA", "name": "엔비디아", "market": "US", "region": "US", "qty": 1, "avg_price_krw": 200000, "eval_amount": 311000},
    ]),
    quotes=CompositeQuoteProvider({"KR": PykrxQuoteProvider(), "US": YfinanceQuoteProvider()}),
    fx=FreeFxProvider(), sentiment=CnnFngProvider(), news=GoogleNewsProvider(),   # 모두 키 불필요
)
print(build_markdown(advisor.run(), AdvisorConfig.default()))
```

**여기까지 API 키가 하나도 필요 없습니다.** (바로 실행: `python examples/keyless_demo.py`)

## 출력 예시

위 코드가 만드는 마크다운은 이렇게 생겼습니다(아래는 설명용 합성 데이터):

```markdown
# 보유주식 데일리 브리핑 — 2026-06-15
> 총 평가액 4,998,500 · 과열도 1/3 · 환율 1385.2

## 🌡️ 시장 국면 (시장별 독립)
- 🇺🇸 **US** (62.0%, 1종목): 공포 우위 — F&G 공포(34.0) · 추세 정배열 +0.77% · 분할매수 기회·경계 (공포는 도망 아닌 분할 매수)
- 🇰🇷 **KR** (25.9%, 1종목): 극단탐욕 — 추정감성 75.5(극단탐욕) · 추세 정배열 +0.99% · 과열·신규 매수 자제 (버블 경계)
- 🇯🇵 **JP** (12.1%, 1종목): 과열(주의) — 추정감성 81.1(극단탐욕) · 추세 정배열 +2.44% · 탐욕+과매수 → 신규 추격 자제·분할

## 📊 보유 종목
| 종목 | 시장 | 비중 | 손익 | 현재가 | RSI · 추세 |
|---|---|---:|---:|---:|---|
| TIGER 미국S&P500 | US | 62.04% | +11.9% | 22,150 | 68.5·정배열 |
| KODEX200 | KR | 25.86% | +7.7% | 129,270 | 61.2·정배열 |
| TIGER 일본니케이225 | JP | 12.1% | +14.5% | 18,900 | 72.3·정배열 |

## 📰 종목 뉴스 (발행 7일 내)
- **TIGER 미국S&P500**
  - [2026-06-14] [S&P500 사상 최고…AI 랠리 지속](https://example.com) (Reuters)
- **KODEX200**
  - [2026-06-15] [코스피, 외국인 순매수에 2%대 강세](https://example.com) (한국경제)

---
> 별점·매수/매도/유지 판단은 스킬/LLM 이 위 데이터를 근거로 덧붙입니다. (정보 제공용)
```

- **시장 국면**은 보유가 속한 시장마다 따로 판정됩니다(미국은 공포인데 일본은 과열 — 한 줄로 안 뭉갬).
- 마지막 줄처럼 **별점·매수/매도 판단과 산문**은 패키지가 하지 않고, 함께 제공하는 스킬이나 사용자 LLM이 이 데이터를 받아 덧붙입니다(`stockbrief.llm.summarize`). 계산은 패키지, 판단은 LLM.
- `advisor.run()`은 마크다운만이 아니라 `BriefingInputs`(구조화 dict)도 주므로 대시보드·LLM이 바로 씁니다.

## 주요 특징

- **갈아끼우는 데이터 소스(provider 구조)** — 시세·심리·뉴스·환율·수급을 공통 인터페이스 뒤에 둡니다. 무료 기본 구현이 들어 있고, 필요하면 정밀한 소스(KIS·네이버)로 교체합니다. 넣지 않은 소스는 자동으로 건너뜁니다.
- **보유 종목 주입** — 보유 목록을 코드에 고정하지 않고 쓰는 쪽에서 넣습니다(JSON 파일·딕셔너리·증권사 잔고 API).
- **계산과 판단 분리** — 비중·국면·점수 같은 숫자는 **순수 계산**(표준 라이브러리만 사용)으로 뽑고, 사고팔지 같은 **판단과 서술**은 함께 제공하는 Claude 스킬이 맡습니다.
- **여러 시장 지원** — 미국·한국·일본·중국 등 시장마다 국면을 따로 판정합니다. 시장 추가는 설정 한 줄이면 됩니다.

| 데이터 | 무료 기본(키 불필요) | 정밀 옵션 |
|---|---|---|
| 보유 종목 | `JsonHoldingsProvider` · `DictHoldingsProvider` · 병합 `CompositeHoldingsProvider` | 한국투자증권(`integrations.kis`) · 토스증권(`integrations.toss`) |
| 시세 | `PykrxQuoteProvider`(한국) · `YfinanceQuoteProvider`(미국) | `KisQuoteProvider` · `TossQuoteProvider` |
| 환율 | `FreeFxProvider`(ECB) | — |
| 투자 심리 | `CnnFngProvider`(미국) | — |
| 뉴스 | `GoogleNewsProvider` | `NaverNewsProvider` |
| 수급 | — | `KisFlowProvider` |

## 설치

```bash
pip install stockbrief                 # 코어만 — 순수 계산(표준 라이브러리)
pip install "stockbrief[quotes-kr]"    # + 무료 한국 시세(pykrx)
pip install "stockbrief[quotes-us]"    # + 무료 미국 시세(yfinance)
pip install "stockbrief[kis]"          # + 한국투자증권 시세·잔고(pykis)
pip install "stockbrief[all]"          # 전부
```

> 시세·지표 경로(pykrx·yfinance·KIS)는 **pandas가 필요**합니다 — 위 `quotes-*`·`kis` extras에 포함돼 있습니다. 코어만 설치하고 시세 provider를 쓰면 지표 계산에서 안내 메시지와 함께 막힙니다.
> 데이터 소스 실패는 표준 `logging`으로 경고를 남깁니다. 원인을 보려면 `logging.basicConfig(level=logging.WARNING)`를 켜세요.
> 아직 PyPI에 올리지 않았습니다. 지금은 소스에서 설치하세요: `pip install -e .`

## 핵심 개념

### 상장 시장(market) vs 기반 시장(region)

종목 하나에 시장 개념이 두 가지 붙습니다. 이 둘을 구분하는 것이 StockBrief의 출발점입니다.

| 개념 | 필드 | 뜻 | 쓰임 |
|---|---|---|---|
| **상장 시장** | `market` = KR / US | 종목이 실제 상장·거래되는 거래소 | 시세 조회 · 환율 환산 |
| **기반 시장** | `region` = US / KR / JP / CN / global | 종목 성과가 따라가는 경제권 | 시장 국면 · 투자 심리 판정 |

예를 들어 일본 니케이225를 추종하는 한국 상장 ETF는 `market=KR`(한국 거래소 상장)이면서 `region=JP`(일본 시장에 베팅)입니다. **두 값을 섞지 않습니다.**

### 용어

브리핑에 쓰이는 용어를 미리 정리합니다.

- **시장 국면(regime)** — 한 시장이 지금 공포~탐욕 중 어느 단계인지로 나눈 분위기.
- **종목 점수(별점)** — 종목을 0~5점으로 종합 평가한 값. 산정 근거는 `star_breakdown`이 요소별로 분해.
- **과열도** — 보유 종목 중 RSI가 기준치(기본 70)를 넘는 종목의 비율.
- **수급(flow)** — 외국인·기관·개인의 순매매 동향(코스피 기준).
- **투자 심리 지수** — 시장의 공포·탐욕 정도. 미국은 CNN Fear & Greed 지수를, 그 외 시장은 지표로 자체 추정합니다.
- **집중도** — 한 종목·시장·테마에 비중이 몰렸는지(`portfolio_concentration`).
- **회고** — 과거 한 시점과 비교해 그동안의 매매가 수익에 도움이 됐는지 사후에 평가하는 것.

## 증권사 연결 — 0개부터 N개까지

증권사 API는 **선택 플러그인**입니다. 하나도 안 붙여도(키리스), 여러 개를 붙여도 동작합니다.

```python
from stockbrief import Advisor, AdvisorConfig, build_markdown, assemble, TossBrokerage, KisBrokerage
from stockbrief.providers import JsonHoldingsProvider

# 증권사 0개 — 보유는 직접 주입, 시세·심리·뉴스·환율은 전부 키리스(pykrx·yfinance·CNN·Google·ECB)
provs = assemble([], holdings=JsonHoldingsProvider("holdings.json"))

# 증권사 N개 — 보유는 자동 병합, 시세는 증권사 것, 빠진 자리는 키리스가 채움
provs = assemble([TossBrokerage(), KisBrokerage(kis_session, quote_fn=..., ohlcv_fn=...)])

print(build_markdown(Advisor(AdvisorConfig.default(), **provs).run(), AdvisorConfig.default()))
# 또는 Advisor.from_brokerages(AdvisorConfig.default(), [TossBrokerage()])
```

- **0개**: 브로커 없이도 완전 동작 — 보유만 JSON/dict로 주면 나머지는 무료 소스. (수급 등 일부 기능만 비활성)
- **N개**: `assemble`이 보유를 `CompositeHoldingsProvider`로 병합하고, 시세/수급은 증권사 것을 쓰되 없으면 키리스로 폴백.
- 현재 내장 브로커: **토스증권**(보유+시세) · **한국투자증권**(보유+시세+수급). 새 증권사는 `Brokerage` 하나 구현하면 끝.

바로 붙이는 단축 함수도 있습니다 — `integrations.kis.build_briefing(kis)` / `integrations.toss.build_briefing(toss)`. 전체 예시: [examples/kis_account.py](examples/kis_account.py).

## 문서

| 문서 | 내용 |
|---|---|
| **[docs/USAGE.md](docs/USAGE.md)** | 설치부터 provider·설정·KIS 연동·운영(재시도·상태저장·LLM·배포)까지 단계별 사용법 |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | 내부 구조·데이터 계약·확장 지점 (수정·기여 전에 읽기) |
| [examples/](examples/) | `keyless_demo.py`(키 0개) · `kis_account.py`(KIS 계좌) · `telegram_bot.py`(텔레그램) · `github-actions-daily.yml`(매일 cron) |
| [skills/](skills/) | 판단·회고용 Claude 스킬 |

## 라이선스

MIT.

> 이 저장소에는 **개인 보유·계좌·키가 전혀 들어 있지 않습니다.** 예시와 테스트는 모두 합성 데이터입니다.
