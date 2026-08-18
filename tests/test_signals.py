import pytest
from datetime import datetime, timezone

from src.features.breadth import MarketBreadth
from src.features.feature_engine import MarketSnapshotFeatures, SectorFeatureSet
from src.signals.sector_score import MarketRegime, SectorScoreEngine


def test_sector_score_regime_classification():
    engine = SectorScoreEngine()
    
    assert engine.classify_regime(75.0) == MarketRegime.BULLISH
    assert engine.classify_regime(45.0) == MarketRegime.MILDLY_BULLISH
    assert engine.classify_regime(10.0) == MarketRegime.NEUTRAL
    assert engine.classify_regime(-15.0) == MarketRegime.NEUTRAL
    assert engine.classify_regime(-45.0) == MarketRegime.MILDLY_BEARISH
    assert engine.classify_regime(-75.0) == MarketRegime.BEARISH


def test_sector_score_evaluation_bullish():
    engine = SectorScoreEngine()
    now = datetime.now(timezone.utc)

    # Bullish scenario: Strong bank & IT moves, positive breadth, positive macro,
    # midcap outperforming (risk-on), private bank leading PSU (risk appetite)
    features = MarketSnapshotFeatures(
        timestamp=now,
        nifty_price=24500.0,
        nifty_day_change_pct=0.80,
        # Phase 5: style rotation — midcap outperforming largecap (risk-on signal)
        style_rotation_score=40.0,     # midcap +0.8% vs nifty → positive score
        largecap_midcap_ratio=0.982,
        sector_features={
            "NIFTY BANK": SectorFeatureSet(
                index_name="NIFTY BANK",
                last_price=52000.0,
                percent_change_day=1.50,
                relative_strength_vs_nifty=0.70,
            ),
            "NIFTY IT": SectorFeatureSet(
                index_name="NIFTY IT",
                last_price=35000.0,
                percent_change_day=1.20,
                relative_strength_vs_nifty=0.40,
            ),
            "NIFTY FINANCIAL SERVICES": SectorFeatureSet(
                index_name="NIFTY FINANCIAL SERVICES",
                last_price=24000.0,
                percent_change_day=1.40,
                relative_strength_vs_nifty=0.60,
            ),
            "NIFTY AUTO": SectorFeatureSet(
                index_name="NIFTY AUTO",
                last_price=25000.0,
                percent_change_day=0.90,
                relative_strength_vs_nifty=0.10,
            ),
            # Phase 5: Banking structure — private bank outperforming PSU (risk-on)
            "NIFTY PRIVATE BANK": SectorFeatureSet(
                index_name="NIFTY PRIVATE BANK",
                last_price=25000.0,
                percent_change_day=1.60,
                relative_strength_vs_nifty=0.80,
            ),
            "NIFTY PSU BANK": SectorFeatureSet(
                index_name="NIFTY PSU BANK",
                last_price=6500.0,
                percent_change_day=0.40,
                relative_strength_vs_nifty=-0.40,
            ),
        },
        market_breadth=MarketBreadth(
            total_sectors=6,
            advancing_sectors=6,
            declining_sectors=0,
            sector_breadth_score=100.0,
        ),
        macro_returns={
            "sp500": 0.80,
            "nasdaq": 1.00,
            "brent_crude": -1.50,  # Drop in crude is positive for Indian macro
            "usd_inr": -0.20,      # Stronger INR is positive
        }
    )

    breakdown = engine.evaluate(features)

    assert breakdown.momentum_score > 50.0
    assert breakdown.breadth_score == 100.0
    assert breakdown.relative_strength_score > 30.0
    assert breakdown.macro_score > 20.0
    # Phase 5 new components — both bullish in this scenario
    assert breakdown.style_rotation_score > 0.0,  "Midcap outperforming should give positive style rotation"
    assert breakdown.banking_risk_appetite_score > 0.0, "Private > PSU bank should give positive banking score"
    assert breakdown.final_score >= 60.0
    assert breakdown.regime == MarketRegime.BULLISH
    # All 6 components agree → agreement_ratio == 1.0
    assert breakdown.agreement_ratio == 1.0
