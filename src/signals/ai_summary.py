import math
import os
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

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


class AISummaryDetail(BaseModel):
    """Full self-contained briefing for a specific engine (Rule-Based or Gemini)."""
    engine_name: str
    headline: str
    regime: str
    directional_score: float
    driver_consensus_pct: float
    executive_synthesis: str
    sector_flow_narrative: str
    macro_risk_narrative: str
    options_playbook: OptionsTradeRecommendation
    key_bullet_points: List[str]


class AISummaryResult(BaseModel):
    """Complete dual-engine structured intelligence with tab support."""
    active_tab: str = "rule_based"
    rule_based: AISummaryDetail
    gemini_based: AISummaryDetail
    gemini_enabled: bool = False


class AISummaryEngine:
    """
    Synthesizes multi-factor market features, sector flows, macro indicators, and
    regime scores into actionable institutional natural-language intelligence and options trade plans.
    Supports both Google Gemini LLM synthesis (when GEMINI_API_KEY is set) and deterministic fallback.
    """

    def __init__(self):
        load_dotenv()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

    @property
    def gemini_api_key(self) -> Optional[str]:
        load_dotenv()
        return os.getenv("GEMINI_API_KEY")

    def _round_to_nifty_strike(self, price: float) -> int:
        """Rounds price to nearest 50-strike for NIFTY 50 options."""
        return int(round(price / 50.0) * 50)

    def _call_gemini_full(self, context_prompt: str, nifty_price: float) -> Optional[dict]:
        """
        Calls Google Gemini REST API requesting a FULL structured JSON briefing.
        Returns parsed dict with all fields, or None on failure.
        """
        if not self.gemini_api_key:
            return None

        import json
        import urllib.request
        import urllib.error

        atm = self._round_to_nifty_strike(nifty_price)

        system_prompt = (
            "You are a senior quantitative strategist at a leading prop trading desk specializing in Indian equity derivatives (NIFTY 50 options).\n"
            "Analyze the following real-time multi-factor market data and return a COMPLETE structured JSON response.\n"
            "NIFTY 50 options trade in 50-point strike intervals (e.g. 24300, 24350, 24400).\n"
            f"The current ATM (at-the-money) strike is {atm}.\n\n"
            "Return ONLY valid JSON (no markdown, no code fences) with exactly these keys:\n"
            "{\n"
            '  "headline": "1-line market headline with emoji prefix (🟢 bullish / 🔴 bearish / 🟡 neutral)",\n'
            '  "executive_synthesis": "3-4 sentence institutional analysis covering sector rotation, order flow, and derivatives positioning",\n'
            '  "sector_flow_narrative": "1-2 sentences on sector leadership/lagging and institutional rotation",\n'
            '  "macro_risk_narrative": "1-2 sentences on global macro risk factors (crude, currency, global indices)",\n'
            '  "options_bias": "BUY NIFTY CE (Calls)" or "BUY NIFTY PE (Puts)" or "STAY CASH",\n'
            '  "options_confidence": "HIGH" or "MODERATE" or "LOW",\n'
            f'  "options_recommended_strike": "e.g. {atm} CE or {atm} PE",\n'
            f'  "options_atm_strike": {atm},\n'
            '  "options_itm_strike": ATM-50 for CE or ATM+50 for PE,\n'
            '  "options_profit_target": "target zone as price range string",\n'
            '  "options_stop_loss": "invalidation condition and price level",\n'
            '  "options_iv_regime": "VIX assessment and Greeks guidance",\n'
            '  "key_bullets": ["bullet1", "bullet2", "bullet3", "bullet4", "bullet5"]\n'
            "}\n\n"
            f"MARKET DATA:\n{context_prompt}"
        )

        model_candidates = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-flash-latest"]
        # Deduplicate while preserving order
        seen = set()
        models_to_try = [m for m in model_candidates if not (m in seen or seen.add(m))]

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [{"text": system_prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2048,
                    "responseMimeType": "application/json",
                }
            }

            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15.0) as response:
                    if response.status == 200:
                        resp_data = json.loads(response.read().decode("utf-8"))
                        candidates = resp_data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                raw_text = parts[0].get("text", "").strip()
                                # Strip markdown code fences if present
                                if raw_text.startswith("```"):
                                    raw_text = raw_text.split("\n", 1)[-1]
                                    if raw_text.endswith("```"):
                                        raw_text = raw_text[:-3].strip()
                                parsed = json.loads(raw_text)
                                logger.info(f"Gemini model '{model_name}' returned full structured JSON briefing successfully.")
                                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"Gemini model '{model_name}' returned non-JSON response ({e}). Trying next model.")
            except urllib.error.HTTPError as e:
                logger.warning(f"Gemini model '{model_name}' returned HTTP {e.code} ({e.reason}). Trying next model.")
                if e.code == 429:
                    time.sleep(1.2)
            except Exception as e:
                logger.warning(f"Gemini model '{model_name}' call failed or timed out ({e}). Trying next model.")

        return None

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

        # Key Bullet Points (Rule-based)
        bullets_rule = [
            f"Directional Conviction: {regime.value} ({score:+.2f} / 100) with {consensus_pct:.0f}% consensus",
            f"Sector Breadth: {breadth_text}",
            f"Heavyweight Drivers: {hw_text}",
            f"Macro Climate: {macro_text}",
            f"Volatility Assessment: {iv_desc.split('.')[0]}.",
        ]

        options_playbook_rule = OptionsTradeRecommendation(
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

        rule_based_detail = AISummaryDetail(
            engine_name="Rule-Based Quant Engine",
            headline=headline,
            regime=regime.value,
            directional_score=score,
            driver_consensus_pct=consensus_pct,
            executive_synthesis=exec_syn,
            sector_flow_narrative=f"Leading: {', '.join([f'{l[0]} (+{l[1]:.2f}%)' for l in top_leaders])} | Lagging: {', '.join([f'{l[0]} ({l[1]:.2f}%)' for l in top_laggards])}",
            macro_risk_narrative=macro_text,
            options_playbook=options_playbook_rule,
            key_bullet_points=bullets_rule,
        )

        # 6. Gemini LLM Engine — Full Structured Briefing
        gemini_enabled = bool(self.gemini_api_key)
        gemini_json = None

        if gemini_enabled:
            prompt_context = (
                f"NIFTY 50 Spot: {nifty_price:,.2f} ({features.nifty_day_change_pct:+.2f}%)\n"
                f"Market Regime: {regime.value} | Composite Score: {score:+.2f} / 100 | Alignment: {consensus_pct:.0f}%\n"
                f"Sector Leadership: {', '.join([f'{l[0]} (+{l[1]:.2f}%)' for l in top_leaders])}\n"
                f"Sector Laggards: {', '.join([f'{l[0]} ({l[1]:.2f}%)' for l in top_laggards])}\n"
                f"Heavyweights: {hw_text}\n"
                f"Market Breadth: {adv} Adv / {dec} Dec\n"
                f"Global Macro: {macro_text}\n"
                f"INDIA VIX: {vix_val:.2f}\n"
                f"Intraday ATR estimate: {intraday_atr:.0f} points"
            )
            gemini_json = self._call_gemini_full(prompt_context, nifty_price)

        if gemini_json:
            # Build Gemini options playbook from LLM response
            g_atm = gemini_json.get("options_atm_strike", atm_strike)
            g_itm = gemini_json.get("options_itm_strike", g_atm)
            # Ensure strikes are valid 50-point intervals
            if isinstance(g_atm, (int, float)):
                g_atm = self._round_to_nifty_strike(g_atm)
            else:
                g_atm = atm_strike
            if isinstance(g_itm, (int, float)):
                g_itm = self._round_to_nifty_strike(g_itm)
            else:
                g_itm = g_atm

            gemini_playbook = OptionsTradeRecommendation(
                bias=gemini_json.get("options_bias", bias),
                confidence=gemini_json.get("options_confidence", confidence),
                atm_strike=g_atm,
                recommended_strike=str(gemini_json.get("options_recommended_strike", rec_strike)),
                itm_strike=g_itm,
                iv_regime=gemini_json.get("options_iv_regime", iv_desc),
                stop_loss_invalidation=gemini_json.get("options_stop_loss", sl_text),
                profit_target_zone=gemini_json.get("options_profit_target", tgt_text),
                risk_divergence_warning=div_warning,
            )

            gemini_based_detail = AISummaryDetail(
                engine_name="Google Gemini Intelligence",
                headline=gemini_json.get("headline", f"✨ Gemini AI — {regime.value.replace('_', ' ')}"),
                regime=regime.value,
                directional_score=score,
                driver_consensus_pct=consensus_pct,
                executive_synthesis=gemini_json.get("executive_synthesis", exec_syn),
                sector_flow_narrative=gemini_json.get("sector_flow_narrative", f"Leading: {', '.join([l[0] for l in top_leaders])}"),
                macro_risk_narrative=gemini_json.get("macro_risk_narrative", macro_text),
                options_playbook=gemini_playbook,
                key_bullet_points=gemini_json.get("key_bullets", bullets_rule),
            )
        else:
            # No API key or Gemini failed — show placeholder content
            placeholder_syn = (
                f"Gemini LLM generative reasoning ready. Add GEMINI_API_KEY to .env to activate "
                f"live AI-driven analysis including independent options strike selection, target zones, "
                f"and institutional flow commentary for the current {regime.value.lower().replace('_', ' ')} regime."
            )

            gemini_based_detail = AISummaryDetail(
                engine_name="Google Gemini Intelligence",
                headline=f"✨ Gemini AI Intelligence — Awaiting API Key",
                regime=regime.value,
                directional_score=score,
                driver_consensus_pct=consensus_pct,
                executive_synthesis=placeholder_syn,
                sector_flow_narrative="Add GEMINI_API_KEY in .env to see Gemini's independent sector rotation analysis.",
                macro_risk_narrative="Add GEMINI_API_KEY in .env to see Gemini's global macro risk assessment.",
                options_playbook=OptionsTradeRecommendation(
                    bias="GEMINI API KEY REQUIRED",
                    confidence="—",
                    atm_strike=atm_strike,
                    recommended_strike=f"Set GEMINI_API_KEY",
                    itm_strike=atm_strike,
                    iv_regime="Gemini will provide independent IV/Greeks analysis.",
                    stop_loss_invalidation="Gemini will calculate its own stop-loss levels.",
                    profit_target_zone="Gemini will project its own target zones.",
                    risk_divergence_warning=None,
                ),
                key_bullet_points=[
                    "Gemini AI engine is available but requires GEMINI_API_KEY in .env",
                    "Once enabled, ALL content in this tab is generated by Google Gemini",
                    "Gemini provides independent options strike, target, and stop-loss recommendations",
                    "The Rule-Based tab continues to work without any API key",
                ],
            )

        return AISummaryResult(
            active_tab="rule_based",
            rule_based=rule_based_detail,
            gemini_based=gemini_based_detail,
            gemini_enabled=gemini_enabled,
        )

    def _generate_fallback_summary(self, indices: Dict[str, IndexData]) -> AISummaryResult:
        """Graceful fallback when features are still warming up."""
        nifty = indices.get("NIFTY 50")
        price = nifty.last_price if nifty else 24000.0
        atm = self._round_to_nifty_strike(price)

        fallback_msg = "Collecting real-time sector ticks and calibrating multi-timeframe feature baselines..."

        fallback_playbook = OptionsTradeRecommendation(
            bias="STAY CASH / WARMING UP",
            confidence="LOW",
            atm_strike=atm,
            recommended_strike=f"{atm} CE/PE",
            itm_strike=atm,
            iv_regime="Syncing live INDIA VIX data.",
            stop_loss_invalidation="Engine warming up.",
            profit_target_zone="Baseline calibrating.",
            risk_divergence_warning=None,
        )

        detail_rule = AISummaryDetail(
            engine_name="Rule-Based Quant Engine",
            headline="⏳ Initializing Quantitative Engine",
            regime="INITIALIZING",
            directional_score=0.0,
            driver_consensus_pct=0.0,
            executive_synthesis=fallback_msg,
            sector_flow_narrative="Calibrating sector relative strength vectors.",
            macro_risk_narrative="Tracking global proxies.",
            options_playbook=fallback_playbook,
            key_bullet_points=["System is warming up rolling time-series matrices."],
        )

        detail_gemini = AISummaryDetail(
            engine_name="Google Gemini Intelligence",
            headline="⏳ Gemini Engine Warming Up",
            regime="INITIALIZING",
            directional_score=0.0,
            driver_consensus_pct=0.0,
            executive_synthesis=fallback_msg,
            sector_flow_narrative="Awaiting real-time tick baseline.",
            macro_risk_narrative="Tracking global risk proxies.",
            options_playbook=fallback_playbook,
            key_bullet_points=["Awaiting real-time tick baseline."],
        )

        return AISummaryResult(
            active_tab="rule_based",
            rule_based=detail_rule,
            gemini_based=detail_gemini,
            gemini_enabled=bool(self.gemini_api_key),
        )
