import yfinance as yf
import numpy as np
from flatwhite.db import insert_signal, get_current_week_iso

TICKER = "^AXJO"
LOOKBACK_DAYS = 30
VOLATILITY_WINDOW = 5

def pull_asx_volatility() -> float:
    ticker = yf.Ticker(TICKER)
    hist = ticker.history(period=f"{LOOKBACK_DAYS}d")

    if hist.empty or len(hist) < VOLATILITY_WINDOW:
        normalised = 50.0
        raw_value = 0.0
    else:
        daily_returns = hist["Close"].pct_change().dropna()
        volatility_5d = float(daily_returns.tail(VOLATILITY_WINDOW).std()) * 100.0
        raw_value = volatility_5d

        rolling_vols = daily_returns.rolling(VOLATILITY_WINDOW).std().dropna() * 100.0
        if len(rolling_vols) > 0:
            percentile = float((rolling_vols < volatility_5d).mean()) * 100.0
        else:
            percentile = 50.0

        normalised = 100.0 - percentile

    normalised = max(0.0, min(100.0, normalised))
    week_iso = get_current_week_iso()

    insert_signal(
        signal_name="asx_volatility",
        lane="pulse",
        area="economic",
        raw_value=raw_value,
        normalised_score=normalised,
        source_weight=1.0,
        week_iso=week_iso,
    )
    return normalised
