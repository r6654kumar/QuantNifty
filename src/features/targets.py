import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def create_forward_returns(
    price_series: pd.Series,
    horizons: Dict[str, int] = None,
) -> pd.DataFrame:
    """
    Creates strictly forward-looking return target variables:
    Forward_Return_{k} = (Price_{t+k} - Price_{t}) / Price_{t} * 100
    
    IMPORTANT: Used ONLY for model training, calibration, and backtest evaluation.
    Must NEVER be fed into the feature engine at timestamp T.
    
    Args:
        price_series: Series of prices indexed by timestamp in chronological order.
        horizons: Dict of label to future bar count, e.g. {'5m': 1, '15m': 3, '30m': 6, '60m': 12}
        
    Returns:
        DataFrame with columns 'fwd_ret_<label>' and binary classification labels 'target_dir_<label>'.
    """
    if horizons is None:
        # Default assuming 5-minute bars
        horizons = {"5m": 1, "15m": 3, "30m": 6, "60m": 12}

    df = pd.DataFrame(index=price_series.index)
    df["price_t"] = price_series

    for label, periods in horizons.items():
        # Shift price backward: price at t+periods
        future_price = price_series.shift(-periods)
        fwd_ret = ((future_price - price_series) / price_series) * 100.0
        
        df[f"fwd_ret_{label}"] = fwd_ret
        # Binary direction: 1 if positive return, -1 if negative, 0 if flat
        df[f"target_dir_{label}"] = np.where(fwd_ret > 0.0, 1, np.where(fwd_ret < 0.0, -1, 0))
        # Mask future NaN values where forward price does not yet exist
        df.loc[fwd_ret.isna(), f"target_dir_{label}"] = np.nan

    return df.drop(columns=["price_t"])
