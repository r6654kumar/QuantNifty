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

    # Phase 3: Rate expectations signal — India 10Y GSec yield
    india_gsec_10y_yield: Optional[float] = None   # e.g. 6.95 for 6.95%
    india_gsec_change_bps: Optional[float] = None  # Intraday change in basis points

    # Phase 5: Style rotation signal — NIFTY 50 vs NIFTY Midcap 100
    largecap_midcap_ratio: Optional[float] = None  # NIFTY 50 price / NIFTY Midcap 100 price
    style_rotation_score: Optional[float] = None   # -100 (midcap leading) to +100 (largecap leading)

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
        gsec_data: Optional[any] = None,
        timestamp: Optional[datetime] = None,
    ) -> MarketSnapshotFeatures:
        """
        Extracts point-in-time features from a live or historical snapshot dictionary.

        Args:
            indices: Dict mapping index_name -> IndexData/IndexSnapshot object.
            macro_data: Dict mapping indicator_key -> MacroData/MacroSnapshot object.
            gsec_data: Optional GSECYieldData object from GSECYieldClient (Phase 3).
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

        # 6. GSec Yield (Phase 3: Rate expectations signal)
        gsec_yield = None
        gsec_change_bps = None
        if gsec_data is not None:
            gsec_yield = getattr(gsec_data, "yield_percent", None)
            gsec_change_bps = getattr(gsec_data, "change_bps", None)

        # 7. Style Rotation Signal (Phase 5: Largecap vs Midcap)
        largecap_midcap_ratio = None
        style_rotation_score = None
        midcap_data = indices.get("NIFTY MIDCAP 100")
        if midcap_data is not None:
            midcap_price = float(midcap_data.last_price)
            if midcap_price and midcap_price > 0:
                largecap_midcap_ratio = round(nifty_price / midcap_price, 6)
            midcap_day_pct = midcap_data.percent_change or 0.0
            # Spread: positive = midcap outperforming (risk-on), negative = largecap leading (risk-off)
            # Research: 1% midcap outperformance → +50 pts style rotation score
            spread = midcap_day_pct - nifty_day_pct
            style_rotation_score = round(max(-100.0, min(100.0, (spread / 1.0) * 50.0)), 2)

        return MarketSnapshotFeatures(
            timestamp=timestamp,
            nifty_price=nifty_price,
            nifty_session_return=nifty_session_ret,
            nifty_day_change_pct=nifty_day_pct,
            nifty_intraday_range_pct=nifty_range,
            india_vix=vix_price,
            india_vix_change_pct=vix_pct,
            india_gsec_10y_yield=gsec_yield,
            india_gsec_change_bps=gsec_change_bps,
            largecap_midcap_ratio=largecap_midcap_ratio,
            style_rotation_score=style_rotation_score,
            sector_features=sector_features,
            market_breadth=breadth,
            macro_returns=macro_ret_dict,
        )
