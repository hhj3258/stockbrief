"""StockBrief — pluggable daily stock-portfolio briefing engine.

Feed it your holdings + market data (via swappable providers) and it produces
a per-market regime read, per-holding star ratings, news, and a benchmark
scoreboard for a daily briefing. The deterministic math is in `stockbrief.lib`;
data sources are providers you inject (run key-free with the bundled defaults,
or plug in KIS / Naver for higher fidelity).
"""

from __future__ import annotations

__version__ = "0.6.0"

from . import lib  # noqa: F401
from .briefing import build_markdown  # noqa: F401
from .config import AdvisorConfig  # noqa: F401
from .lib import (  # noqa: F401
    backcalc_buy_fill,
    classify_trade,
    computed_sentiment,
    fng_band,
    holding_key,
    overheat_ratio,
    pct_return,
    portfolio_concentration,
    region_regime,
    region_weights,
    retro_verdict,
    star_breakdown,
    star_score,
    theme_weights,
    weight_fit_score,
    weights,
)
from .brokerage import Brokerage, KisBrokerage, TossBrokerage, assemble  # noqa: F401,E402
from .metrics import all_regions  # noqa: F401,E402
from .pipeline import Advisor, BriefingInputs  # noqa: F401,E402

__all__ = [
    "__version__",
    "lib",
    "Advisor",
    "BriefingInputs",
    "build_markdown",
    "AdvisorConfig",
    "all_regions",
    "Brokerage",
    "TossBrokerage",
    "KisBrokerage",
    "assemble",
    "weights",
    "theme_weights",
    "region_weights",
    "portfolio_concentration",
    "overheat_ratio",
    "fng_band",
    "computed_sentiment",
    "region_regime",
    "weight_fit_score",
    "star_score",
    "star_breakdown",
    "backcalc_buy_fill",
    "classify_trade",
    "pct_return",
    "retro_verdict",
    "holding_key",
]
