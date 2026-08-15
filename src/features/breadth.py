from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ConstituentBreadth(BaseModel):
    """Breadth metrics for constituents within a single index/sector."""
    index_name: str
    total_constituents: int = 0
    advances: int = 0
    declines: int = 0
    unchanged: int = 0
    advance_decline_ratio: Optional[float] = None
    percent_advancing: Optional[float] = None


class MarketBreadth(BaseModel):
    """Overall market breadth metrics across all tracked sector indices."""
    total_sectors: int = 0
    advancing_sectors: int = 0
    declining_sectors: int = 0
    unchanged_sectors: int = 0
    sector_advance_decline_ratio: Optional[float] = None
    sector_breadth_score: float = 0.0 # Normalized score between -100 and +100
    has_constituent_level_data: bool = False
    constituent_breadths: Dict[str, ConstituentBreadth] = Field(default_factory=dict)


def calculate_sector_breadth_score(advancing: int, declining: int, total: int) -> float:
    """
    Computes a normalized breadth score from -100 to +100:
    Score = ((Advances - Declines) / Total) * 100
    """
    if total <= 0:
        return 0.0
    return ((advancing - declining) / total) * 100.0


def compute_market_breadth_from_sectors(sector_returns: Dict[str, float]) -> MarketBreadth:
    """
    Computes sector-level participation breadth from dictionary of sector returns.
    Does NOT fake constituent data — sets has_constituent_level_data=False.
    """
    if not sector_returns:
        return MarketBreadth()

    advances = 0
    declines = 0
    unchanged = 0

    for ret in sector_returns.values():
        if ret is None:
            continue
        if ret > 0.001:
            advances += 1
        elif ret < -0.001:
            declines += 1
        else:
            unchanged += 1

    total = advances + declines + unchanged
    ad_ratio = round(advances / declines, 2) if declines > 0 else (float(advances) if advances > 0 else 1.0)
    score = calculate_sector_breadth_score(advances, declines, total)

    return MarketBreadth(
        total_sectors=total,
        advancing_sectors=advances,
        declining_sectors=declines,
        unchanged_sectors=unchanged,
        sector_advance_decline_ratio=ad_ratio,
        sector_breadth_score=round(score, 2),
        has_constituent_level_data=False,
    )
