"""
Sector Score Engine — Signal Enhancement Phases 2–5
Calculates weighted sector and macro directional signals for NIFTY 50.

Signal Architecture (v2 — Post Phase 5 Enhancement):
  Momentum            35%  (sector weighted returns)
  Relative Strength   20%  (sector vs NIFTY outperformance)
  Breadth             15%  (% advancing sectors)
  Macro               15%  (12 global indicators: equity, commodity, currency, rates)
  Style Rotation      10%  (NIFTY Midcap 100 vs NIFTY 50 — new Phase 5)
  Banking Structure    5%  (PSU Bank vs Private Bank — new Phase 5)

Macro Sub-Component (15%):
  Equity Indices      40%  (S&P, Nasdaq, HSI, KOSPI, STI, Nikkei)
  Commodities         30%  (Brent, Gold, Copper)
  Currencies          20%  (USD/INR, DXY)
  Rate Expectations   10%  (India 10Y GSec yield — Phase 3)
"""
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
    momentum_score: float = 0.0           # Contribution from weighted sector momentum (-100 to +100)
    relative_strength_score: float = 0.0  # Contribution from sector relative strength vs NIFTY (-100 to +100)
    breadth_score: float = 0.0            # Contribution from market breadth participation (-100 to +100)
    macro_score: float = 0.0              # Contribution from global indices, crude & forex (-100 to +100)
    # Phase 5 new components
    style_rotation_score: float = 0.0    # NIFTY Midcap 100 vs NIFTY 50 rotation signal (-100 to +100)
    banking_risk_appetite_score: float = 0.0  # PSU Bank vs Private Bank risk appetite (-100 to +100)
    # Phase 3 new sub-signals (surfaced separately for transparency)
    rate_expectations_score: float = 0.0  # India 10Y GSec yield signal (-100 to +100)
    # Phase 4 new sub-signals
    fii_flow_signal: float = 0.0          # FII/DII daily flow signal (-100 to +100)
    # VIX & composite
    vix_modifier: float = 1.0             # Dampener or amplifier based on VIX regime
    raw_composite_score: float = 0.0      # Weighted pre-clamped score
    final_score: float = 0.0              # Final directional score clamped to [-100.0, +100.0]
    regime: MarketRegime = MarketRegime.NEUTRAL
    agreement_ratio: float = 0.0          # Fraction of components that agree with directional sign (0.0 to 1.0)


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

    # Phase 5: Updated from 4-component to 6-component architecture
    DEFAULT_COMPONENT_WEIGHTS = {
        "momentum": 0.35,           # ↓ from 0.40
        "relative_strength": 0.20,  # ↓ from 0.25
        "breadth": 0.15,            # ↓ from 0.20
        "macro": 0.15,              # unchanged (but now covers 12 indicators)
        "style_rotation": 0.10,     # NEW: NIFTY Midcap 100 vs NIFTY 50 rotation
        "banking_structure": 0.05,  # NEW: PSU Bank vs Private Bank risk appetite
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

    # ──────────────────────────────────────────────────────────────
    # Component 1: Momentum Score (unchanged)
    # ──────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────
    # Component 2: Relative Strength Score (unchanged)
    # ──────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────
    # Component 3: Macro Score (Phase 2 — upgraded to 4-bucket, 12 signals)
    # ──────────────────────────────────────────────────────────────

    def _calculate_rate_expectations_score(self, features: MarketSnapshotFeatures) -> float:
        """
        Phase 3: Rate expectations signal from India 10Y GSec yield.

        Interpretation:
          - Yield < 6.80% → RBI easing/growth expectations → PE expansion → Bullish (+75 to +100)
          - Yield 6.80%–7.00% → Neutral zone → 0
          - Yield > 7.00% → RBI tightening/inflation fears → PE compression → Bearish (-75 to -100)
          - Every 20 bps move in yield → ±30 momentum modifier

        Research: -0.65 correlation to NIFTY (strongest missing signal in baseline model)
        """
        gsec_yield = features.india_gsec_10y_yield
        gsec_change = features.india_gsec_change_bps or 0.0

        if gsec_yield is None:
            return 0.0

        neutral_low = 6.80
        neutral_high = 7.00

        # Level score from yield band
        if gsec_yield < neutral_low:
            # Easing bias: deeper into low territory → stronger bullish signal
            level_score = min(100.0, 75.0 + ((neutral_low - gsec_yield) / 0.20) * 25.0)
        elif gsec_yield > neutral_high:
            # Tightening bias: higher yield → stronger bearish signal
            level_score = max(-100.0, -75.0 - ((gsec_yield - neutral_high) / 0.20) * 25.0)
        else:
            level_score = 0.0

        # Momentum score: rising yields (positive change_bps) → bearish pressure
        # +20 bps rise → -30 pts penalty (tightening surprise)
        momentum_score = -(gsec_change / 20.0) * 30.0
        momentum_score = max(-50.0, min(50.0, momentum_score))  # cap momentum contribution

        # Combine: 70% level + 30% momentum
        total_score = (level_score * 0.7) + (momentum_score * 0.3)
        return max(-100.0, min(100.0, total_score))

    def _calculate_macro_score(self, features: MarketSnapshotFeatures) -> float:
        """
        Phase 2 Upgraded: Computes global risk-on vs risk-off score from 12 macro proxies.

        4-bucket weighting:
          Equity indices  40%  — S&P, Nasdaq, Nikkei, HSI, KOSPI, STI
          Commodities     30%  — Brent (cost headwind ↓), Gold (safe-haven ↓), Copper (growth ↑)
          Currencies      20%  — USD/INR (↓ INR = headwind), DXY (↑ USD = headwind)
          Rate Expectations 10% — India 10Y GSec (Phase 3)
        """
        macros = features.macro_returns
        if not macros:
            return 0.0

        # ── 1. Equity indices (40% weight) ──────────────────────────
        equity_scores = []
        # US indices: 1% move → 50 pts (higher predictive weight)
        for key in ("sp500", "nasdaq"):
            if key in macros and macros[key] is not None:
                equity_scores.append((macros[key] / 1.0) * 50.0)
        # Asian indices: 1% move → 40 pts
        for key in ("nikkei", "hang_seng", "kospi", "singapore_sti"):
            if key in macros and macros[key] is not None:
                equity_scores.append((macros[key] / 1.0) * 40.0)

        equity_component = (sum(equity_scores) / len(equity_scores)) if equity_scores else 0.0

        # ── 2. Commodities (30% weight) ─────────────────────────────
        commodity_scores = []
        # Brent crude: cost headwind for India (oil importer) — negative signal
        if "brent_crude" in macros and macros["brent_crude"] is not None:
            commodity_scores.append(-(macros["brent_crude"] / 2.0) * 25.0)
        # Gold: safe-haven rally = risk-off = bearish for equities
        if "gold_spot" in macros and macros["gold_spot"] is not None:
            commodity_scores.append(-(macros["gold_spot"] / 1.0) * 30.0)
        # Copper: "Dr. Copper" growth indicator — positive signal
        if "copper_spot" in macros and macros["copper_spot"] is not None:
            commodity_scores.append((macros["copper_spot"] / 1.0) * 25.0)

        commodity_component = (sum(commodity_scores) / len(commodity_scores)) if commodity_scores else 0.0

        # ── 3. Currencies (20% weight) ──────────────────────────────
        currency_scores = []
        # USD/INR: INR depreciation = FII outflow pressure = headwind
        if "usd_inr" in macros and macros["usd_inr"] is not None:
            currency_scores.append(-(macros["usd_inr"] / 0.5) * 25.0)
        # DXY: Strong dollar = EM outflows = headwind for NIFTY
        if "dxy" in macros and macros["dxy"] is not None:
            currency_scores.append(-(macros["dxy"] / 1.0) * 20.0)

        currency_component = (sum(currency_scores) / len(currency_scores)) if currency_scores else 0.0

        # ── 4. Rate Expectations (10% weight) ───────────────────────
        rate_component = self._calculate_rate_expectations_score(features)

        # ── Weighted composite macro score ───────────────────────────
        macro_score = (
            equity_component * 0.40
            + commodity_component * 0.30
            + currency_component * 0.20
            + rate_component * 0.10
        )

        return max(-100.0, min(100.0, macro_score))

    # ──────────────────────────────────────────────────────────────
    # Component 5 (new): Style Rotation Signal — Phase 5
    # ──────────────────────────────────────────────────────────────

    def _calculate_style_rotation_score(self, features: MarketSnapshotFeatures) -> float:
        """
        Phase 5: NIFTY Midcap 100 vs NIFTY 50 relative performance.

        Interpretation:
          - Midcap outperforming (+spread) → risk-on, retail optimism → Bullish
          - Largecap outperforming (-spread) → flight to quality → Bearish
          - 1% spread = 50 points; clamped to [-100, +100]

        Research: When NIFTY Midcap 100 opens +1.5% while NIFTY 50 opens +0.5%
        → Bullish momentum tends to persist for 2-3 hours.
        """
        style_score = features.style_rotation_score
        if style_score is None:
            return 0.0
        return float(style_score)

    # ──────────────────────────────────────────────────────────────
    # Component 6 (new): Banking Structure Signal — Phase 5
    # ──────────────────────────────────────────────────────────────

    def _calculate_banking_risk_appetite(self, features: MarketSnapshotFeatures) -> float:
        """
        Phase 5: PSU Bank vs Private Bank relative strength — banking risk appetite.

        Interpretation:
          - Private bank outperforming PSU → FII preference for growth banks → Risk-on → Bullish
          - PSU bank outperforming private → Flight to government-backed → Risk-off → Bearish
          - 1% private-vs-PSU spread = 50 pts; clamped to [-100, +100]

        Research: Ratio momentum leads NIFTY BANK next 1-3 days.
        """
        psu_feat = features.sector_features.get("NIFTY PSU BANK")
        pvt_feat = features.sector_features.get("NIFTY PRIVATE BANK")

        if not psu_feat or not pvt_feat:
            return 0.0

        psu_ret = psu_feat.percent_change_day or 0.0
        pvt_ret = pvt_feat.percent_change_day or 0.0

        # Positive spread → private outperforming → risk-on
        spread = pvt_ret - psu_ret
        scaled = (spread / 1.0) * 50.0
        return max(-100.0, min(100.0, scaled))

    # ──────────────────────────────────────────────────────────────
    # Phase 4: FII/DII Flow Signal
    # ──────────────────────────────────────────────────────────────

    def _calculate_fii_flow_signal(self, fii_flows: Optional[Dict[str, float]]) -> float:
        """
        Phase 4: FII/DII daily flow signal.

        Interpretation:
          - Large FII inflow (>500 Cr/day) → Bullish structural signal
          - Large FII outflow (<-500 Cr/day) → Bearish structural signal
          - DII absorption: if FII selling + DII buying, moderates the bearish score
          - 1000 Cr FII flow = 50 points; clamped to [-100, +100]

        Note: End-of-day data; use previous day's flows as next-day feature.
        Research: +0.55 correlation; 1-3 day predictive horizon.
        """
        if not fii_flows:
            return 0.0

        fii_flow = fii_flows.get("fii_inflow_crores", 0.0) or 0.0
        dii_flow = fii_flows.get("dii_inflow_crores", 0.0) or 0.0

        # Base score: 1000 Cr FII flow → 50 pts
        fii_score = (fii_flow / 1000.0) * 50.0

        # DII absorption modifier:
        # If FII is selling but DII is buying, DII support dampens the bearish impact
        if fii_flow < 0 and dii_flow > 0:
            absorption_factor = min(1.0, dii_flow / abs(fii_flow))
            fii_score *= (1.0 - 0.5 * absorption_factor)

        return max(-100.0, min(100.0, fii_score))

    # ──────────────────────────────────────────────────────────────
    # Regime Classification
    # ──────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────
    # Main Evaluation
    # ──────────────────────────────────────────────────────────────

    def evaluate(
        self,
        features: MarketSnapshotFeatures,
        fii_flows: Optional[Dict[str, float]] = None,
    ) -> SignalBreakdown:
        """
        Evaluates all feature components and returns the composite directional score and breakdown.

        Args:
            features: Engineered feature matrix from FeatureEngine.process_snapshot()
            fii_flows: Optional dict with keys 'fii_inflow_crores', 'dii_inflow_crores' (Phase 4)
        """
        # ── Calculate all components ─────────────────────────────
        mom_score = self._calculate_momentum_score(features)
        rs_score = self._calculate_relative_strength_score(features)
        breadth_score = features.market_breadth.sector_breadth_score
        macro_score = self._calculate_macro_score(features)
        style_score = self._calculate_style_rotation_score(features)
        banking_score = self._calculate_banking_risk_appetite(features)
        rate_score = self._calculate_rate_expectations_score(features)  # surfaced separately
        fii_score = self._calculate_fii_flow_signal(fii_flows)

        # ── Component weights ─────────────────────────────────────
        w_mom = self.component_weights.get("momentum", 0.35)
        w_rs = self.component_weights.get("relative_strength", 0.20)
        w_breadth = self.component_weights.get("breadth", 0.15)
        w_macro = self.component_weights.get("macro", 0.15)
        w_style = self.component_weights.get("style_rotation", 0.10)
        w_banking = self.component_weights.get("banking_structure", 0.05)

        # ── Composite weighted sum ────────────────────────────────
        raw_score = (
            mom_score * w_mom
            + rs_score * w_rs
            + breadth_score * w_breadth
            + macro_score * w_macro
            + style_score * w_style
            + banking_score * w_banking
        )

        final_score = round(max(-100.0, min(100.0, raw_score)), 2)
        regime = self.classify_regime(final_score)

        # ── Component agreement ratio ─────────────────────────────
        sub_scores = [mom_score, rs_score, breadth_score, macro_score, style_score, banking_score]
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
            style_rotation_score=round(style_score, 2),
            banking_risk_appetite_score=round(banking_score, 2),
            rate_expectations_score=round(rate_score, 2),
            fii_flow_signal=round(fii_score, 2),
            raw_composite_score=round(raw_score, 2),
            final_score=final_score,
            regime=regime,
            agreement_ratio=agreement,
        )
