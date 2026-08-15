"""Backtesting and statistical evaluation engine."""

from src.backtest.baselines import BaselineStrategies
from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.metrics import StrategyMetrics, calculate_strategy_metrics

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "StrategyMetrics",
    "calculate_strategy_metrics",
    "BaselineStrategies",
]
