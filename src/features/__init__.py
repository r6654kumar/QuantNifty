"""Feature engineering module."""

from src.features.breadth import (
    ConstituentBreadth,
    MarketBreadth,
    calculate_sector_breadth_score,
    compute_market_breadth_from_sectors,
)
from src.features.feature_engine import (
    FeatureEngine,
    MarketSnapshotFeatures,
    SectorFeatureSet,
)
from src.features.momentum import (
    calculate_multi_timeframe_momentum,
    calculate_returns,
    calculate_session_return,
)
from src.features.relative_strength import (
    calculate_relative_strength,
    calculate_relative_strength_matrix,
)
from src.features.volatility import (
    calculate_intraday_range,
    calculate_rolling_volatility,
)

__all__ = [
    "FeatureEngine",
    "MarketSnapshotFeatures",
    "SectorFeatureSet",
    "MarketBreadth",
    "ConstituentBreadth",
    "calculate_sector_breadth_score",
    "compute_market_breadth_from_sectors",
    "calculate_returns",
    "calculate_session_return",
    "calculate_multi_timeframe_momentum",
    "calculate_relative_strength",
    "calculate_relative_strength_matrix",
    "calculate_intraday_range",
    "calculate_rolling_volatility",
]
