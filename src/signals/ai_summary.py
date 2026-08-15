import math
import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.data.nse_client import IndexData
from src.features.feature_engine import MarketSnapshotFeatures
from src.signals.sector_score import MarketRegime, SignalBreakdown
from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.ai_summary")


class OptionsTradeRecommendation(BaseModel):
    """Actionable options strategy recommendation with strike and risk math."""
    bias: str = Field(description="Trade direction: BUY NIFTY CE, BUY NIFTY PE, or STAY CASH")
    confidence: str = Field(description="Conviction level: HIGH, MODERATE, LOW")
    atm_strike: int = Field(description="Nearest At-The-Money strike (50-point interval)")
    recommended_strike: str = Field(description="Specific recommended strike e.g. 24350 CE or 24400 PE")
    itm_strike: int = Field(description="1-strike In-The-Money alternative for lower theta decay")
    iv_regime: str = Field(description="INDIA VIX regime description and Greeks guidance")
    stop_loss_invalidation: str = Field(description="Quant invalidation condition and price level")
    profit_target_zone: str = Field(description="Target projection based on ATR / range")
    risk_divergence_warning: Optional[str] = Field(default=None, description="Any sector divergence warning")


class AISummaryResult(BaseModel):
    """Complete structured AI market intelligence briefing."""
    headline: str
    regime: str
    directional_score: float
    driver_consensus_pct: float
    executive_synthesis: str
    sector_flow_narrative: str
    macro_risk_narrative: str
    options_playbook: OptionsTradeRecommendation
    key_bullet_points: List[str]


class AISummaryEngine:
    """
    Synthesizes multi-factor market features, sector flows, macro indicators, and
    regime scores into actionable institutional natural-language intelligence and options trade plans.
    """

    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")

    def _round_to_nifty_strike(self, price: float) -> int:
        """Rounds price to nearest 50-strike for NIFTY 50 options."""
        return int(round(price / 50.0) * 50)

    def generate_summary(
        self,
        features: Optional[MarketSnapshotFeatures],
        signal: Optional[SignalBreakdown],
        indices: Dict[str, IndexData],
        macro_data: dict,
    ) -> AISummaryResult:
        """Generates comprehensive AI intelligence synthesis and options playbook."""
        if not features or not signal:
            return self._generate_fallback_summary(indices)

        nifty_price = features.nifty_price
        score = signal.final_score
        regime = signal.regime
        consensus_pct = round(signal.agreement_ratio * 100.0, 0)
        atm_strike = self._round_to_nifty_strike(nifty_price)

        # 1. Sector Leadership & Laggards
        sector_rs = []
        for sec_name, sec_feat in features.sector_features.items():
            if sec_feat.relative_strength_vs_nifty is not None:
                sector_rs.append((sec_name, sec_feat.relative_strength_vs_nifty, sec_feat.percent_change_day or 0.0))

        # Sort by relative strength
        sector_rs.sort(key=lambda x: x[1], reverse=True)
        top_leaders = sector_rs[:2] if len(sector_rs) >= 2 else sector_rs
        top_laggards = sector_rs[-2:] if len(sector_rs) >= 2 else []

        # Heavyweights status (Bank, FinServ, IT)
        heavyweights = ["NIFTY BANK", "NIFTY FINANCIAL SERVICES", "NIFTY IT"]
        hw_status = []
        for hw in heavyweights:
            if hw in features.sector_features and features.sector_features[hw].relative_strength_vs_nifty is not None:
                rs_val = features.sector_features[hw].relative_strength_vs_nifty
                chg_val = indices[hw].percent_change if hw in indices else 0.0
                hw_status.append(f"{hw} ({chg_val:+.2f}%, RS {rs_val:+.2f}%)")

        hw_text = ", ".join(hw_status) if hw_status else "Heavyweight data syncing"

        # 2. Market Breadth Narrative
        adv = features.market_breadth.advancing_sectors
        dec = features.market_breadth.declining_sectors
        b_score = features.market_breadth.sector_breadth_score or 0.0
        breadth_text = f"{adv} advancing sectors vs {dec} declining sectors (Participation Breadth: {b_score:+.1f})"

        # 3. Macro Narrative
        macro_points = []
        for k, m in macro_data.items():
            if "crude" in k.lower():
                macro_points.append(f"Crude at ${m.last_price:.2f} ({m.percent_change:+.2f}%)")
            elif "usd" in k.lower():
                macro_points.append(f"USD/INR at {m.last_price:.2f} ({m.percent_change:+.2f}%)")
            elif "sp500" in k.lower() or "nasdaq" in k.lower():
                macro_points.append(f"{m.indicator_key.upper()} ({m.percent_change:+.2f}%)")
        macro_text = " | ".join(macro_points) if macro_points else "Global macro proxies stable"

        # 4. INDIA VIX & IV Analysis
        vix_val = 12.0
        if "INDIA VIX" in indices:
            vix_val = indices["INDIA VIX"].last_price or 12.0

        if vix_val < 13.0:
            iv_desc = f"INDIA VIX is low at {vix_val:.2f} (Low IV environment). Premiums are relatively cheap; delta behaves linearly. Favorable for directional option buying with strict targets."
        elif vix_val <= 17.0:
            iv_desc = f"INDIA VIX is moderate at {vix_val:.2f} (Standard IV environment). Balanced option pricing; theta decay will accelerate during intraday consolidation."
        else:
            iv_desc = f"INDIA VIX is elevated at {vix_val:.2f} (High IV regime). Premium expansion is high; Vega risk is significant. Consider wider stop-loss buffers."

        # 5. Options Playbook Formulation
        intraday_atr = max(40.0, nifty_price * (features.nifty_intraday_range_pct / 100.0) * 0.4)
        
        if regime in (MarketRegime.BULLISH, MarketRegime.MILDLY_BULLISH):
            bias = "BUY NIFTY CE (Calls)"
            confidence = "HIGH" if score >= 60.0 and consensus_pct >= 75.0 else "MODERATE"
            rec_strike = f"{atm_strike} CE"
            itm_strike = atm_strike - 50
            sl_text = f"Invalidate trade if Sector Score drops below +15.0 or NIFTY breaks below support at {(nifty_price - intraday_atr*0.6):,.0f}"
            tgt_text = f"{(nifty_price + intraday_atr*0.8):,.0f} - {(nifty_price + intraday_atr*1.4):,.0f} spot projection"
            headline = f"🟢 Bullish Sector Accumulation (+{score:.1f}) — Favoring NIFTY Call Options"
            exec_syn = (
                f"NIFTY 50 ({nifty_price:,.2f}) demonstrates an upward directional edge with a composite score of {score:+.2f} "
                f"and {consensus_pct:.0f}% driver alignment. Sector institutional flow is dominated by leadership in "
                f"{', '.join([l[0] for l in top_leaders])}. Heavyweights support the rally: {hw_text}."
            )
        elif regime in (MarketRegime.BEARISH, MarketRegime.MILDLY_BEARISH):
            bias = "BUY NIFTY PE (Puts)"
            confidence = "HIGH" if score <= -60.0 and consensus_pct >= 75.0 else "MODERATE"
            rec_strike = f"{atm_strike} PE"
            itm_strike = atm_strike + 50
            sl_text = f"Invalidate trade if Sector Score rises above -15.0 or NIFTY reclaims resistance at {(nifty_price + intraday_atr*0.6):,.0f}"
            tgt_text = f"{(nifty_price - intraday_atr*0.8):,.0f} - {(nifty_price - intraday_atr*1.4):,.0f} spot projection"
            headline = f"🔴 Bearish Sector Distribution ({score:.1f}) — Favoring NIFTY Put Options"
            exec_syn = (
                f"NIFTY 50 ({nifty_price:,.2f}) is experiencing distribution pressure with a directional score of {score:+.2f} "
                f"and {consensus_pct:.0f}% multi-factor alignment. Key downward drag is led by {', '.join([l[0] for l in top_laggards])}. "
                f"Heavyweight positioning: {hw_text}."
            )
        else:
            bias = "STAY CASH / NO BUY (Theta Risk)"
            confidence = "NEUTRAL"
            rec_strike = f"{atm_strike} Straddle / No Directional Buy"
            itm_strike = atm_strike
            sl_text = "Market is in neutral consolidation. Option buyers face severe theta decay."
            tgt_text = "Wait for directional breakout (Score crossing > +30 or < -30)"
            headline = f"🟡 Neutral Intraday Consolidation ({score:+.1f}) — Avoid Option Buying"
            exec_syn = (
                f"NIFTY 50 ({nifty_price:,.2f}) is oscillating in an equilibrium range with a neutral score of {score:+.2f}. "
                f"Sector participation is mixed ({adv} Adv / {dec} Dec). Risk of whipsaw and theta decay is elevated."
            )

        # Divergence warning
        div_warning = None
        if len(top_leaders) > 0 and len(top_laggards) > 0:
            if regime in (MarketRegime.BEARISH, MarketRegime.MILDLY_BEARISH) and top_leaders[0][1] > 0.5:
                div_warning = f"Positive divergence detected in {top_leaders[0][0]} (+{top_leaders[0][1]:.2f}% RS). Monitor if buying spills over into Heavyweights."
            elif regime in (MarketRegime.BULLISH, MarketRegime.MILDLY_BULLISH) and top_laggards[0][1] < -0.5:
                div_warning = f"Negative divergence detected in {top_laggards[0][0]} ({top_laggards[0][1]:.2f}% RS). Ensure heavyweight volume confirms continuation."

        # Key Bullet Points
        bullets = [
            f"Directional Conviction: {regime.value} ({score:+.2f} / 100) with {consensus_pct:.0f}% consensus",
            f"Sector Breadth: {breadth_text}",
            f"Heavyweight Drivers: {hw_text}",
            f"Macro Climate: {macro_text}",
            f"Volatility Assessment: {iv_desc.split('.')[0]}.",
        ]

        options_playbook = OptionsTradeRecommendation(
            bias=bias,
            confidence=confidence,
            atm_strike=atm_strike,
            recommended_strike=rec_strike,
            itm_strike=itm_strike,
            iv_regime=iv_desc,
            stop_loss_invalidation=sl_text,
            profit_target_zone=tgt_text,
            risk_divergence_warning=div_warning,
        )

        return AISummaryResult(
            headline=headline,
            regime=regime.value,
            directional_score=score,
            driver_consensus_pct=consensus_pct,
            executive_synthesis=exec_syn,
            sector_flow_narrative=f"Leading: {', '.join([f'{l[0]} (+{l[1]:.2f}%)' for l in top_leaders])} | Lagging: {', '.join([f'{l[0]} ({l[1]:.2f}%)' for l in top_laggards])}",
            macro_risk_narrative=macro_text,
            options_playbook=options_playbook,
            key_bullet_points=bullets,
        )

    def _generate_fallback_summary(self, indices: Dict[str, IndexData]) -> AISummaryResult:
        """Graceful fallback when features are still warming up."""
        nifty = indices.get("NIFTY 50")
        price = nifty.last_price if nifty else 24000.0
        atm = self._round_to_nifty_strike(price)

        return AISummaryResult(
            headline="⏳ Initializing Quantitative Engine",
            regime="INITIALIZING",
            directional_score=0.0,
            driver_consensus_pct=0.0,
            executive_synthesis="Collecting real-time sector ticks and calibrating multi-timeframe feature baselines...",
            sector_flow_narrative="Calibrating sector relative strength vectors.",
            macro_risk_narrative="Tracking global proxies.",
            options_playbook=OptionsTradeRecommendation(
                bias="STAY CASH / WARMING UP",
                confidence="LOW",
                atm_strike=atm,
                recommended_strike=f"{atm} CE/PE",
                itm_strike=atm,
                iv_regime="Syncing live INDIA VIX data.",
                stop_loss_invalidation="Engine warming up.",
                profit_target_zone="Baseline calibrating.",
                risk_divergence_warning=None,
            ),
            key_bullet_points=["System is warming up rolling time-series matrices."],
        )
