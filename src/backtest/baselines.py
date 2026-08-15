import numpy as np
import pandas as pd
from typing import Dict


class BaselineStrategies:
    """Generates benchmark comparison signals to validate whether the Sector Model has true predictive edge."""

    @staticmethod
    def random_direction(index_series: pd.Index, seed: int = 42) -> pd.Series:
        """Baseline 1: Random directional guess (+1 or -1)."""
        rng = np.random.default_rng(seed)
        random_choices = rng.choice([-1, 1], size=len(index_series))
        return pd.Series(random_choices, index=index_series, name="signal_random")

    @staticmethod
    def always_bullish(index_series: pd.Index) -> pd.Series:
        """Baseline 2: Always Long (+1) to capture passive market drift."""
        return pd.Series(1, index=index_series, name="signal_always_bullish")

    @staticmethod
    def previous_direction(nifty_returns: pd.Series) -> pd.Series:
        """Baseline 3: Follows direction of immediate preceding return."""
        signal = np.where(nifty_returns > 0, 1, np.where(nifty_returns < 0, -1, 0))
        return pd.Series(signal, index=nifty_returns.index, name="signal_prev_direction")

    @staticmethod
    def nifty_momentum_only(nifty_prices: pd.Series, fast_window: int = 3, slow_window: int = 8) -> pd.Series:
        """
        Baseline 4: NIFTY Price Action Only (Fast EMA > Slow EMA = Bullish, else Bearish).
        Uses NO sector or macro information.
        """
        fast_ema = nifty_prices.ewm(span=fast_window, adjust=False).mean()
        slow_ema = nifty_prices.ewm(span=slow_window, adjust=False).mean()
        
        signal = np.where(fast_ema > slow_ema, 1, np.where(fast_ema < slow_ema, -1, 0))
        return pd.Series(signal, index=nifty_prices.index, name="signal_nifty_mom_only")
