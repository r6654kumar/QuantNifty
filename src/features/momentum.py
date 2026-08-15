import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def calculate_returns(series: pd.Series, periods: int) -> pd.Series:
    """Calculates percentage return over given number of periods: (P_t - P_{t-k}) / P_{t-k} * 100."""
    if series is None or len(series) < periods + 1:
        return pd.Series(np.nan, index=series.index if series is not None else [0])
    return (series / series.shift(periods) - 1.0) * 100.0


def calculate_session_return(last_price: float, session_open: Optional[float]) -> Optional[float]:
    """Calculates session return from day's opening price: (P - Open) / Open * 100."""
    if session_open is None or session_open <= 0 or last_price <= 0:
        return None
    return ((last_price - session_open) / session_open) * 100.0


def calculate_multi_timeframe_momentum(df: pd.DataFrame, windows: Dict[str, int] = None) -> pd.DataFrame:
    """
    Calculates momentum returns across multiple rolling bar windows for a price dataframe.
    
    Args:
        df: DataFrame indexed by timestamp with 'last_price' and 'open' columns.
        windows: Dict of label to bar count, e.g. {'1m': 1, '5m': 5, '15m': 15, '30m': 30}.
        
    Returns:
        DataFrame with added columns: mom_<window>, mom_session.
    """
    if windows is None:
        windows = {"1m": 1, "5m": 5, "15m": 15, "30m": 30}

    result = df.copy()
    
    for label, periods in windows.items():
        col_name = f"mom_{label}"
        result[col_name] = calculate_returns(result["last_price"], periods)

    # Session return (intraday from open)
    if "open" in result.columns:
        result["mom_session"] = ((result["last_price"] - result["open"]) / result["open"]) * 100.0

    return result
