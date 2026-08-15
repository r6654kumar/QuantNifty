from datetime import datetime, timezone
from src.data.nse_client import IndexData
from src.features.breadth import MarketBreadth
from src.features.feature_engine import MarketSnapshotFeatures, SectorFeatureSet
from src.signals.sector_score import MarketRegime, SignalBreakdown
from src.signals.ai_summary import AISummaryEngine


def test_ai_summary_generation_bearish():
    engine = AISummaryEngine()

    # Mock Features
    features = MarketSnapshotFeatures(
        timestamp=datetime.now(timezone.utc),
        nifty_price=24366.0,
        nifty_day_change_pct=-0.12,
        nifty_intraday_range_pct=0.45,
        india_vix=11.32,
        sector_features={
            "NIFTY AUTO": SectorFeatureSet(index_name="NIFTY AUTO", last_price=29207.0, percent_change_day=-0.63, relative_strength_vs_nifty=-0.51, intraday_range_pct=0.6),
            "NIFTY BANK": SectorFeatureSet(index_name="NIFTY BANK", last_price=57491.0, percent_change_day=-0.25, relative_strength_vs_nifty=-0.13, intraday_range_pct=0.5),
            "NIFTY IT": SectorFeatureSet(index_name="NIFTY IT", last_price=31357.0, percent_change_day=-0.31, relative_strength_vs_nifty=-0.19, intraday_range_pct=0.5),
            "NIFTY FINANCIAL SERVICES": SectorFeatureSet(index_name="NIFTY FINANCIAL SERVICES", last_price=26213.0, percent_change_day=-0.43, relative_strength_vs_nifty=-0.31, intraday_range_pct=0.5),
        },
        market_breadth=MarketBreadth(
            advancing_sectors=2,
            declining_sectors=11,
            unchanged_sectors=0,
            sector_advance_decline_ratio=0.18,
            sector_breadth_score=-69.2,
        ),
        macro_returns={},
    )

    signal = SignalBreakdown(
        momentum_score=-24.6,
        relative_strength_score=-24.8,
        breadth_score=-69.2,
        macro_score=-3.0,
        final_score=-30.33,
        regime=MarketRegime.MILDLY_BEARISH,
        agreement_ratio=1.0,
    )

    indices = {
        "NIFTY 50": IndexData(index_name="NIFTY 50", last_price=24366.0, percent_change=-0.12),
        "INDIA VIX": IndexData(index_name="INDIA VIX", last_price=11.32, percent_change=-0.85),
    }

    result = engine.generate_summary(features, signal, indices, {})

    assert result.directional_score == -30.33
    assert result.regime == "MILDLY_BEARISH"
    assert result.driver_consensus_pct == 100.0
    assert "BUY NIFTY PE" in result.options_playbook.bias
    assert result.options_playbook.atm_strike == 24350
    assert "24350 PE" in result.options_playbook.recommended_strike
    assert result.options_playbook.itm_strike == 24400
    assert len(result.key_bullet_points) >= 4
