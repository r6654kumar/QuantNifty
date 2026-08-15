from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.features.feature_engine import MarketSnapshotFeatures
from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.signals")


class MarketRegime(str, Enum):
    BULLISH = "BULLISH"
    MILDLY_BULLISH = "MILDLY_BULLISH"
    NEUTRAL = "NEUTRAL"
    MILDLY_BEARISH = "MILDLY_BEARISH"
    BEARISH = "BEARISH"


class SignalBreakdown(BaseModel):
    """Detailed constituent breakdown of the NIFTY directional score."""
    momentum_score: float = 0.0          # Contribution from weighted sector momentum (-100 to +100)
    relative_strength_score: float = 0.0 # Contribution from sector relative strength vs NIFTY (-100 to +100)
    breadth_score: float = 0.0           # Contribution from market breadth participation (-100 to +100)
    macro_score: float = 0.0             # Contribution from global indices, crude & forex (-100 to +100)
    vix_modifier: float = 1.0            # Dampener or amplifier based on VIX regime
    raw_composite_score: float = 0.0     # Weighted pre-clamped score
    final_score: float = 0.0             # Final directional score clamped to [-100.0, +100.0]
    regime: MarketRegime = MarketRegime.NEUTRAL
    agreement_ratio: float = 0.0         # Fraction of components that agree with directional sign (0.0 to 1.0)


class SectorScoreEngine:
    """Calculates weighted sector and macro directional signals for NIFTY 50."""

    DEFAULT_SECTOR_WEIGHTS = {
        "NIFTY BANK": 0.28,
        "NIFTY FINANCIAL SERVICES": 0.12,
        "NIFTY IT": 0.15,
        "NIFTY OIL & GAS": 0.12,
        "NIFTY AUTO": 0.08,
        "NIFTY FMCG": 0.08,
        "NIFTY METAL": 0.05,
        "NIFTY PHARMA": 0.04,
        "NIFTY CONSUMER DURABLES": 0.03,
        "NIFTY REALTY": 0.02,
        "NIFTY PSU BANK": 0.02,
        "NIFTY MEDIA": 0.01,
    }

    DEFAULT_COMPONENT_WEIGHTS = {
        "momentum": 0.40,
        "relative_strength": 0.25,
        "breadth": 0.20,
        "macro": 0.15,
    }

    DEFAULT_REGIME_THRESHOLDS = {
        "bullish": 60.0,
        "mildly_bullish": 30.0,
        "mildly_bearish": -30.0,
        "bearish": -60.0,
    }

    def __init__(
        self,
        sector_weights: Optional[Dict[str, float]] = None,
        component_weights: Optional[Dict[str, float]] = None,
        regime_thresholds: Optional[Dict[str, float]] = None,
    ):
        self.sector_weights = sector_weights or self.DEFAULT_SECTOR_WEIGHTS
        self.component_weights = component_weights or self.DEFAULT_COMPONENT_WEIGHTS
        self.thresholds = regime_thresholds or self.DEFAULT_REGIME_THRESHOLDS

        # Normalize sector weights so they sum to 1.0
        total_w = sum(self.sector_weights.values())
        if total_w > 0:
            self.normalized_sector_weights = {k: v / total_w for k, v in self.sector_weights.items()}
        else:
            self.normalized_sector_weights = self.sector_weights

    def _calculate_momentum_score(self, features: MarketSnapshotFeatures) -> float:
        """Weighted average of sector percentage changes, scaled to [-100, +100]."""
        weighted_sum = 0.0
        total_matched_weight = 0.0

        for sector_name, weight in self.normalized_sector_weights.items():
            feat = features.sector_features.get(sector_name) or features.sector_features.get(sector_name.upper())
            if feat and feat.percent_change_day is not None:
                weighted_sum += feat.percent_change_day * weight
                total_matched_weight += weight

        if total_matched_weight == 0:
            return 0.0

        avg_return = weighted_sum / total_matched_weight
        # Normalize: A +/- 1.5% sector move translates to +/- 100 on sub-score
        scaled_score = (avg_return / 1.5) * 100.0
        return max(-100.0, min(100.0, scaled_score))

    def _calculate_relative_strength_score(self, features: MarketSnapshotFeatures) -> float:
        """Weighted average of sector outperformance vs NIFTY 50."""
        weighted_rs = 0.0
        total_matched_weight = 0.0

        for sector_name, weight in self.normalized_sector_weights.items():
            feat = features.sector_features.get(sector_name) or features.sector_features.get(sector_name.upper())
            if feat and feat.relative_strength_vs_nifty is not None:
                weighted_rs += feat.relative_strength_vs_nifty * weight
                total_matched_weight += weight

        if total_matched_weight == 0:
            return 0.0

        avg_rs = weighted_rs / total_matched_weight
        # Normalize: +/- 1.0% relative strength spread maps to +/- 100
        scaled_rs = (avg_rs / 1.0) * 100.0
        return max(-100.0, min(100.0, scaled_rs))

    def _calculate_macro_score(self, features: MarketSnapshotFeatures) -> float:
        """Computes global risk-on vs risk-off score from macro proxies."""
        macros = features.macro_returns
        if not macros:
            return 0.0

        score = 0.0
        count = 0

        # US and Asian equity indices (Positive = Bullish for NIFTY)
        for key in ("sp500", "nasdaq", "nikkei"):
            if key in macros and macros[key] is not None:
                # 1.0% move in S&P / Nasdaq maps to ~50 points
                score += (macros[key] / 1.0) * 50.0
                count += 1

        # Crude Oil (For India, higher crude is traditionally a cost headwind / negative for currency & trade balance)
        if "brent_crude" in macros and macros["brent_crude"] is not None:
            score -= (macros["brent_crude"] / 2.0) * 25.0
            count += 1

        # USD/INR (Depreciating INR / rising USDINR is generally a headwind for FII flows)
        if "usd_inr" in macros and macros["usd_inr"] is not None:
            score -= (macros["usd_inr"] / 0.5) * 25.0
            count += 1

        if count == 0:
            return 0.0

        avg_macro = score / count
        return max(-100.0, min(100.0, avg_macro))

    def classify_regime(self, score: float) -> MarketRegime:
        """Maps continuous score to discrete market regime based on configured thresholds."""
        if score >= self.thresholds["bullish"]:
            return MarketRegime.BULLISH
        elif score >= self.thresholds["mildly_bullish"]:
            return MarketRegime.MILDLY_BULLISH
        elif score <= self.thresholds["bearish"]:
            return MarketRegime.BEARISH
        elif score <= self.thresholds["mildly_bearish"]:
            return MarketRegime.MILDLY_BEARISH
        else:
            return MarketRegime.NEUTRAL

    def evaluate(self, features: MarketSnapshotFeatures) -> SignalBreakdown:
        """Evaluates all feature components and returns the composite directional score and breakdown."""
        mom_score = self._calculate_momentum_score(features)
        rs_score = self._calculate_relative_strength_score(features)
        breadth_score = features.market_breadth.sector_breadth_score
        macro_score = self._calculate_macro_score(features)

        # Composite weighted sum
        w_mom = self.component_weights.get("momentum", 0.40)
        w_rs = self.component_weights.get("relative_strength", 0.25)
        w_breadth = self.component_weights.get("breadth", 0.20)
        w_macro = self.component_weights.get("macro", 0.15)

        raw_score = (
            mom_score * w_mom
            + rs_score * w_rs
            + breadth_score * w_breadth
            + macro_score * w_macro
        )

        final_score = round(max(-100.0, min(100.0, raw_score)), 2)
        regime = self.classify_regime(final_score)

        # Component agreement ratio
        sub_scores = [mom_score, rs_score, breadth_score, macro_score]
        if abs(final_score) > 5.0:
            target_sign = 1 if final_score > 0 else -1
            agreeing = sum(1 for s in sub_scores if (s * target_sign) > 0)
            agreement = round(agreeing / len(sub_scores), 2)
        else:
            agreement = 0.50

        return SignalBreakdown(
            momentum_score=round(mom_score, 2),
            relative_strength_score=round(rs_score, 2),
            breadth_score=round(breadth_score, 2),
            macro_score=round(macro_score, 2),
            raw_composite_score=round(raw_score, 2),
            final_score=final_score,
            regime=regime,
            agreement_ratio=agreement,
        )
