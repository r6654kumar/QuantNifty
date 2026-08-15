import numpy as np
import pandas as pd
from typing import Dict, Optional
from pydantic import BaseModel


class StrategyMetrics(BaseModel):
    """Statistical evaluation metrics for a trading signal strategy or baseline."""
    strategy_name: str
    horizon: str
    total_signals: int = 0
    bullish_signals: int = 0
    bearish_signals: int = 0
    neutral_count: int = 0
    
    accuracy: float = 0.0           # Correct direction hit-rate %
    bullish_accuracy: float = 0.0   # Hit-rate on bullish signals %
    bearish_accuracy: float = 0.0   # Hit-rate on bearish signals %
    precision: float = 0.0
    recall: float = 0.0
    
    mean_return_pct: float = 0.0    # Average forward return per trade
    median_return_pct: float = 0.0  # Median forward return per trade
    win_rate: float = 0.0           # Percentage of profitable trades
    profit_factor: float = 0.0      # Gross profits / Gross losses
    
    max_adverse_movement: float = 0.0   # Average worst drawdown while in trade (MAE %)
    max_favorable_movement: float = 0.0 # Average best profit reached during trade (MFE %)
    
    cumulative_return_pct: float = 0.0  # Total compounding return
    max_drawdown_pct: float = 0.0       # Maximum Peak-to-Trough drop %
    sharpe_ratio: float = 0.0           # Annualized Sharpe ratio


def calculate_strategy_metrics(
    signals: pd.Series,
    future_returns: pd.Series,
    strategy_name: str = "Sector Model",
    horizon: str = "15m",
    cost_per_trade_bps: float = 2.0, # 2 bps (0.02%) slippage + transaction cost
    bars_per_year: int = 75 * 252,
) -> StrategyMetrics:
    """
    Computes rigorous statistical metrics for directional signal evaluations.
    
    Args:
        signals: Series of directional signals (+1 for Long, -1 for Short, 0 for Neutral).
        future_returns: Series of percentage forward returns over horizon.
        strategy_name: Name of strategy.
        horizon: Horizon label (e.g. '15m').
        cost_per_trade_bps: Transaction cost & slippage in basis points.
    """
    # Align and drop NaNs
    valid = pd.DataFrame({"signal": signals, "fwd_ret": future_returns}).dropna()
    if valid.empty:
        return StrategyMetrics(strategy_name=strategy_name, horizon=horizon)

    total_bars = len(valid)
    active = valid[valid["signal"] != 0].copy()
    neutral_count = total_bars - len(active)

    if active.empty:
        return StrategyMetrics(
            strategy_name=strategy_name,
            horizon=horizon,
            total_signals=0,
            neutral_count=neutral_count,
        )

    # Strategy trade return = signal * forward_return - cost
    cost_pct = cost_per_trade_bps / 100.0
    active["trade_ret"] = (active["signal"] * active["fwd_ret"]) - cost_pct
    active["is_win"] = active["trade_ret"] > 0

    bullish_mask = active["signal"] > 0
    bearish_mask = active["signal"] < 0

    bullish_trades = active[bullish_mask]
    bearish_trades = active[bearish_mask]

    bullish_acc = (bullish_trades["fwd_ret"] > 0).mean() * 100.0 if not bullish_trades.empty else 0.0
    bearish_acc = (bearish_trades["fwd_ret"] < 0).mean() * 100.0 if not bearish_trades.empty else 0.0
    overall_acc = active["is_win"].mean() * 100.0

    # Precision & Recall for directional movement
    actual_bullish = valid["fwd_ret"] > 0
    pred_bullish = valid["signal"] > 0
    true_positive = (actual_bullish & pred_bullish).sum()
    false_positive = (~actual_bullish & pred_bullish).sum()
    false_negative = (actual_bullish & ~pred_bullish).sum()

    precision = (true_positive / (true_positive + false_positive) * 100.0) if (true_positive + false_positive) > 0 else 0.0
    recall = (true_positive / (true_positive + false_negative) * 100.0) if (true_positive + false_negative) > 0 else 0.0

    # Profit Factor
    gross_profits = active.loc[active["trade_ret"] > 0, "trade_ret"].sum()
    gross_losses = abs(active.loc[active["trade_ret"] < 0, "trade_ret"].sum())
    profit_factor = round(gross_profits / gross_losses, 2) if gross_losses > 0 else (float("inf") if gross_profits > 0 else 0.0)

    # Equity Curve & Max Drawdown
    equity_curve = (1.0 + active["trade_ret"] / 100.0).cumprod()
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak * 100.0
    max_dd = abs(drawdown.min()) if not drawdown.empty else 0.0
    cum_ret = ((equity_curve.iloc[-1] - 1.0) * 100.0) if not equity_curve.empty else 0.0

    # Sharpe Ratio
    mean_ret = active["trade_ret"].mean()
    std_ret = active["trade_ret"].std()
    sharpe = (mean_ret / std_ret * np.sqrt(bars_per_year)) if std_ret and std_ret > 0 else 0.0

    # Maximum Adverse & Favorable Movement proxies
    mae = abs(active.loc[active["trade_ret"] < 0, "trade_ret"].mean()) if (active["trade_ret"] < 0).any() else 0.0
    mfe = active.loc[active["trade_ret"] > 0, "trade_ret"].mean() if (active["trade_ret"] > 0).any() else 0.0

    return StrategyMetrics(
        strategy_name=strategy_name,
        horizon=horizon,
        total_signals=len(active),
        bullish_signals=len(bullish_trades),
        bearish_signals=len(bearish_trades),
        neutral_count=neutral_count,
        accuracy=round(overall_acc, 2),
        bullish_accuracy=round(bullish_acc, 2),
        bearish_accuracy=round(bearish_acc, 2),
        precision=round(precision, 2),
        recall=round(recall, 2),
        mean_return_pct=round(mean_ret, 4),
        median_return_pct=round(active["trade_ret"].median(), 4),
        win_rate=round(overall_acc, 2),
        profit_factor=profit_factor if profit_factor != float("inf") else 999.9,
        max_adverse_movement=round(mae, 4),
        max_favorable_movement=round(mfe, 4),
        cumulative_return_pct=round(cum_ret, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
    )
