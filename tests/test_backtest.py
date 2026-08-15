import numpy as np
import pandas as pd
import pytest

from src.backtest.baselines import BaselineStrategies
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import calculate_strategy_metrics
from src.features.targets import create_forward_returns


def test_create_forward_returns():
    prices = pd.Series([100.0, 102.0, 105.0, 103.0, 107.0])
    df = create_forward_returns(prices, {"1bar": 1, "2bars": 2})
    
    # 1-bar forward return from index 0 is (102 - 100)/100 = 2.0%
    assert round(df["fwd_ret_1bar"].iloc[0], 2) == 2.0
    assert df["target_dir_1bar"].iloc[0] == 1
    
    # 2-bar forward return from index 0 is (105 - 100)/100 = 5.0%
    assert round(df["fwd_ret_2bars"].iloc[0], 2) == 5.0
    
    # Last bar forward return must be NaN (no future data)
    assert np.isnan(df["fwd_ret_1bar"].iloc[-1])


def test_calculate_strategy_metrics():
    signals = pd.Series([1, 1, -1, 1, -1])
    fwd_ret = pd.Series([1.5, 0.8, -1.2, -0.5, -0.9])
    
    metrics = calculate_strategy_metrics(
        signals=signals,
        future_returns=fwd_ret,
        strategy_name="TestStrategy",
        horizon="15m",
        cost_per_trade_bps=0.0,
    )
    
    assert metrics.total_signals == 5
    assert metrics.bullish_signals == 3
    assert metrics.bearish_signals == 2
    # Longs: 1.5 (win), 0.8 (win), -0.5 (loss). Shorts: -1.2 (win, because short of -1.2 gives +1.2), -0.9 (win) -> 4 wins out of 5
    assert metrics.win_rate == 80.0
    assert metrics.accuracy == 80.0
    assert metrics.profit_factor > 1.0


def test_backtest_engine_calibrated_simulation():
    engine = BacktestEngine(cost_bps=2.0)
    result = engine.run_calibrated_simulation(n_bars=100, horizon_label="15m", horizon_bars=3)
    
    assert result.horizon == "15m"
    assert result.sample_bars > 50
    assert "random" in result.baseline_metrics
    assert "always_bullish" in result.baseline_metrics
    assert "nifty_momentum" in result.baseline_metrics
    assert "Sector Model" in result.equity_curves
