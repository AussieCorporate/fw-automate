import yfinance as yf
from flatwhite.db import insert_signal, get_current_week_iso

TICKER = "^AXJO"
LOOKBACK_DAYS = 60
MOMENTUM_WINDOW_DAYS = 20

def pull_asx_momentum() -> float:
    ticker = yf.Ticker(TICKER)
    hist = ticker.history(period=f"{LOOKBACK_DAYS}d")

    if hist.empty or len(hist) < MOMENTUM_WINDOW_DAYS:
        normalised = 50.0
        raw_value = 0.0
    else:
        current_price = float(hist["Close"].iloc[-1])
        price_4wk_ago = float(hist["Close"].iloc[-MOMENTUM_WINDOW_DAYS])
        raw_value = ((current_price - price_4wk_ago) / price_4wk_ago) * 100.0

        normalised = max(0.0, min(100.0, 50.0 + (raw_value * 5.0)))

    week_iso = get_current_week_iso()

    insert_signal(
        signal_name="asx_momentum",
        lane="pulse",
        area="economic",
        raw_value=raw_value,
        normalised_score=normalised,
        source_weight=1.0,
        week_iso=week_iso,
    )
    return normalised
