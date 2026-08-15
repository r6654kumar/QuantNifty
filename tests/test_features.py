import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone

from src.features.breadth import calculate_sector_breadth_score, compute_market_breadth_from_sectors
from src.features.feature_engine import FeatureEngine
from src.features.momentum import calculate_multi_timeframe_momentum, calculate_returns, calculate_session_return
from src.features.relative_strength import calculate_relative_strength, calculate_relative_strength_matrix
from src.features.volatility import calculate_intraday_range, calculate_rolling_volatility
from src.data.nse_client import IndexData
from src.data.macro_client import MacroData


def test_calculate_returns():
    series = pd.Series([100.0, 102.0, 105.0, 103.0])
    returns = calculate_returns(series, 1)
    assert np.isnan(returns.iloc[0])
    assert round(returns.iloc[1], 2) == 2.0
    assert round(returns.iloc[2], 2) == 2.94
    assert round(returns.iloc[3], 2) == -1.90


def test_calculate_session_return():
    assert round(calculate_session_return(24500.0, 24000.0), 2) == 2.08
    assert calculate_session_return(24500.0, None) is None
    assert calculate_session_return(24500.0, 0.0) is None


def test_calculate_relative_strength():
    sector_ret = pd.Series([1.5, 2.0, -0.5])
    bench_ret = pd.Series([1.0, 0.5, 0.0])
    rs = calculate_relative_strength(sector_ret, bench_ret)
    assert list(rs) == [0.5, 1.5, -0.5]


def test_calculate_intraday_range():
    assert round(calculate_intraday_range(24600.0, 24400.0, 24500.0), 2) == 0.82
    assert calculate_intraday_range(None, 24400.0, 24500.0) is None


def test_breadth_calculations():
    # 8 advancing, 2 declining, 2 unchanged
    sector_returns = {
        "BANK": 1.2,
        "IT": 0.8,
        "AUTO": 0.5,
        "FMCG": 0.2,
        "PHARMA": 0.4,
        "METAL": 1.1,
        "ENERGY": 0.9,
        "REALTY": 0.3,
        "MEDIA": -0.4,
        "PSU": -0.6,
        "FIN": 0.0,
        "PVT": 0.0,
    }
    breadth = compute_market_breadth_from_sectors(sector_returns)
    assert breadth.total_sectors == 12
    assert breadth.advancing_sectors == 8
    assert breadth.declining_sectors == 2
    assert breadth.unchanged_sectors == 2
    assert breadth.sector_advance_decline_ratio == 4.0
    assert breadth.sector_breadth_score == 50.0  # (8 - 2) / 12 * 100 = 50.0


def test_feature_engine_process_snapshot():
    engine = FeatureEngine(benchmark_name="NIFTY 50")
    now = datetime.now(timezone.utc)

    indices = {
        "NIFTY 50": IndexData(
            index_name="NIFTY 50",
            last_price=24500.0,
            open=24400.0,
            high=24550.0,
            low=24380.0,
            percent_change=0.50,
            variation=120.0,
            timestamp=now,
        ),
        "NIFTY BANK": IndexData(
            index_name="NIFTY BANK",
            last_price=52000.0,
            open=51500.0,
            high=52100.0,
            low=51400.0,
            percent_change=1.20,
            variation=600.0,
            timestamp=now,
        ),
        "NIFTY IT": IndexData(
            index_name="NIFTY IT",
            last_price=35000.0,
            open=35200.0,
            high=35300.0,
            low=34900.0,
            percent_change=-0.30,
            variation=-100.0,
            timestamp=now,
        ),
        "INDIA VIX": IndexData(
            index_name="INDIA VIX",
            last_price=12.50,
            percent_change=-2.0,
            timestamp=now,
        ),
    }

    macro = {
        "sp500": MacroData(indicator_key="sp500", ticker_symbol="^GSPC", last_price=5800.0, percent_change=0.60),
        "brent_crude": MacroData(indicator_key="brent_crude", ticker_symbol="BZ=F", last_price=78.0, percent_change=-1.20),
    }

    features = engine.process_snapshot(indices=indices, macro_data=macro, timestamp=now)

    assert features.nifty_price == 24500.0
    assert features.india_vix == 12.50
    assert features.sector_features["NIFTY BANK"].relative_strength_vs_nifty == 0.70  # 1.20 - 0.50
    assert features.sector_features["NIFTY IT"].relative_strength_vs_nifty == -0.80   # -0.30 - 0.50
    assert features.market_breadth.advancing_sectors == 1
    assert features.market_breadth.declining_sectors == 1
