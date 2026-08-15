from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from pydantic import BaseModel, Field

from src.features.breadth import MarketBreadth, compute_market_breadth_from_sectors
from src.features.momentum import calculate_returns, calculate_session_return
from src.features.relative_strength import calculate_relative_strength
from src.features.volatility import calculate_intraday_range
from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.feature_engine")


class SectorFeatureSet(BaseModel):
    """Engineered features for a single sector index at a given timestamp."""
    index_name: str
    last_price: float
    session_return: Optional[float] = None
    percent_change_day: Optional[float] = None
    relative_strength_vs_nifty: Optional[float] = None
    intraday_range_pct: Optional[float] = None
    pe: Optional[float] = None


class MarketSnapshotFeatures(BaseModel):
    """Complete engineered feature matrix for a specific point in time."""
    timestamp: datetime
    nifty_price: float
    nifty_session_return: Optional[float] = None
    nifty_day_change_pct: Optional[float] = None
    nifty_intraday_range_pct: Optional[float] = None
    india_vix: Optional[float] = None
    india_vix_change_pct: Optional[float] = None
    
    sector_features: Dict[str, SectorFeatureSet] = Field(default_factory=dict)
    market_breadth: MarketBreadth = Field(default_factory=MarketBreadth)
    macro_returns: Dict[str, float] = Field(default_factory=dict)


class FeatureEngine:
    """Orchestrates multi-timeframe feature generation for live streaming and historical datasets."""

    def __init__(self, benchmark_name: str = "NIFTY 50"):
        self.benchmark_name = benchmark_name

    def process_snapshot(
        self,
        indices: Dict[str, any],
        macro_data: Optional[Dict[str, any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> MarketSnapshotFeatures:
        """
        Extracts point-in-time features from a live or historical snapshot dictionary.
        
        Args:
            indices: Dict mapping index_name -> IndexData/IndexSnapshot object.
            macro_data: Dict mapping indicator_key -> MacroData/MacroSnapshot object.
            timestamp: Snapshot evaluation time.
        """
        if not timestamp:
            timestamp = datetime.utcnow()

        # 1. Benchmark (NIFTY 50) extraction
        nifty_data = indices.get(self.benchmark_name) or indices.get(self.benchmark_name.upper())
        if nifty_data is None:
            raise ValueError(f"Benchmark index '{self.benchmark_name}' missing from snapshot.")

        nifty_price = float(nifty_data.last_price)
        nifty_session_ret = calculate_session_return(nifty_price, nifty_data.open)
        nifty_day_pct = nifty_data.percent_change or 0.0
        nifty_range = calculate_intraday_range(nifty_data.high, nifty_data.low, nifty_price)

        # 2. INDIA VIX extraction
        vix_data = indices.get("INDIA VIX")
        vix_price = float(vix_data.last_price) if vix_data else None
        vix_pct = float(vix_data.percent_change) if vix_data and vix_data.percent_change is not None else None

        # 3. Sector Features & Relative Strength
        sector_features: Dict[str, SectorFeatureSet] = {}
        sector_returns_for_breadth: Dict[str, float] = {}

        for name, item in indices.items():
            if name.upper() in (self.benchmark_name.upper(), "INDIA VIX"):
                continue

            item_price = float(item.last_price)
            item_day_pct = item.percent_change or 0.0
            item_session_ret = calculate_session_return(item_price, item.open)
            
            # Relative strength: Sector return - NIFTY return
            rs_score = None
            if item_day_pct is not None and nifty_day_pct is not None:
                rs_score = round(item_day_pct - nifty_day_pct, 4)

            item_range = calculate_intraday_range(item.high, item.low, item_price)

            sector_feat = SectorFeatureSet(
                index_name=name,
                last_price=item_price,
                session_return=item_session_ret,
                percent_change_day=item_day_pct,
                relative_strength_vs_nifty=rs_score,
                intraday_range_pct=item_range,
                pe=item.pe if hasattr(item, "pe") else None,
            )
            sector_features[name] = sector_feat
            sector_returns_for_breadth[name] = item_day_pct

        # 4. Market Breadth
        breadth = compute_market_breadth_from_sectors(sector_returns_for_breadth)

        # 5. Macro Returns
        macro_ret_dict = {}
        if macro_data:
            for k, m in macro_data.items():
                macro_ret_dict[k] = m.percent_change if hasattr(m, "percent_change") else 0.0

        return MarketSnapshotFeatures(
            timestamp=timestamp,
            nifty_price=nifty_price,
            nifty_session_return=nifty_session_ret,
            nifty_day_change_pct=nifty_day_pct,
            nifty_intraday_range_pct=nifty_range,
            india_vix=vix_price,
            india_vix_change_pct=vix_pct,
            sector_features=sector_features,
            market_breadth=breadth,
            macro_returns=macro_ret_dict,
        )
