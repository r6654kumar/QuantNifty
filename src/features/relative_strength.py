import pandas as pd
from typing import Dict, Optional


def calculate_relative_strength(
    sector_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> pd.Series:
    """
    Calculates the relative strength spread between a sector and NIFTY 50:
    RS = Sector_Return - Benchmark_Return
    
    Positive values indicate sector outperformance; negative indicates underperformance.
    """
    return sector_returns - benchmark_returns


def calculate_relative_strength_matrix(
    returns_df: pd.DataFrame,
    benchmark_col: str = "NIFTY 50",
) -> pd.DataFrame:
    """
    Calculates Relative Strength for all columns in returns_df against the benchmark column.
    
    Args:
        returns_df: DataFrame where each column is an index return series across time.
        benchmark_col: Column name of benchmark (default 'NIFTY 50').
        
    Returns:
        DataFrame of relative strength spreads for each sector.
    """
    if benchmark_col not in returns_df.columns:
        raise ValueError(f"Benchmark column '{benchmark_col}' not found in returns DataFrame.")

    benchmark_series = returns_df[benchmark_col]
    rs_df = pd.DataFrame(index=returns_df.index)

    for col in returns_df.columns:
        if col != benchmark_col:
            rs_df[f"rs_{col}"] = returns_df[col] - benchmark_series

    return rs_df
