import numpy as np
import pandas as pd
from typing import Optional


def calculate_intraday_range(high: float, low: float, last_price: float) -> Optional[float]:
    """
    Calculates intraday normalized trading range as percentage of price:
    Range% = (High - Low) / LastPrice * 100
    """
    if high is None or low is None or last_price is None or last_price <= 0:
        return None
    if high < low:
        return 0.0
    return ((high - low) / last_price) * 100.0


def calculate_rolling_volatility(
    price_series: pd.Series,
    window: int = 15,
    annualize: bool = False,
    bars_per_year: int = 75 * 252, # 75 5-minute bars per 6.25 hr trading day * 252 days
) -> pd.Series:
    """
    Calculates rolling standard deviation of log returns.
    
    Args:
        price_series: Series of prices.
        window: Number of rolling bars.
        annualize: If True, scales by sqrt(bars_per_year).
    """
    if price_series is None or len(price_series) < window:
        return pd.Series(np.nan, index=price_series.index if price_series is not None else [0])

    log_returns = np.log(price_series / price_series.shift(1))
    rolling_std = log_returns.rolling(window=window, min_periods=max(2, window // 2)).std()

    if annualize:
        rolling_std = rolling_std * np.sqrt(bars_per_year)

    return rolling_std * 100.0 # Return as percentage
