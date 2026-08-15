import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from rich.console import Console
from rich.table import Table

from src.data.macro_client import MacroClient
from src.data.nse_client import IndexData, NSEClient
from src.db.connection import get_db_session, init_db
from src.db.models import IndexSnapshot, MacroSnapshot
from src.features.feature_engine import FeatureEngine, MarketSnapshotFeatures
from src.signals.sector_score import SectorScoreEngine, SignalBreakdown
from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.collector")
console = Console()

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


class DataCollector:
    """Orchestrates periodic collection of NSE indices, feature extraction, and signal scoring."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = self._load_config(config_path)
        
        collector_cfg = self.config.get("collector", {})
        nse_cfg = self.config.get("nse", {})
        signals_cfg = self.config.get("signals", {})

        self.interval_seconds = collector_cfg.get("interval_seconds", 300)
        self.target_indices = collector_cfg.get("indices", [])
        self.macro_tickers = collector_cfg.get("macro_tickers", {})

        # Trading hours gate
        th = collector_cfg.get("trading_hours", {})
        self.trading_start_hour = th.get("start_hour", 8)
        self.trading_start_minute = th.get("start_minute", 0)
        self.trading_end_hour = th.get("end_hour", 14)
        self.trading_end_minute = th.get("end_minute", 0)
        self.trading_tz = ZoneInfo(th.get("timezone", "Asia/Kolkata"))
        self.weekdays_only = th.get("weekdays_only", True)

        self.nse_client = NSEClient(
            base_url=nse_cfg.get("base_url", "https://www.nseindia.com"),
            all_indices_endpoint=nse_cfg.get("all_indices_endpoint", "/api/allIndices"),
            timeout=collector_cfg.get("timeout_seconds", 15),
            max_retries=collector_cfg.get("max_retries", 3),
            retry_delay=collector_cfg.get("retry_delay_seconds", 2.0),
            min_request_gap=collector_cfg.get("min_request_gap_seconds", 3.0),
            session_refresh_minutes=nse_cfg.get("session_refresh_minutes", 4),
        )

        self.macro_client = MacroClient(tickers=self.macro_tickers)
        self.feature_engine = FeatureEngine(benchmark_name="NIFTY 50")
        self.score_engine = SectorScoreEngine(
            sector_weights=signals_cfg.get("sector_weights"),
            component_weights=signals_cfg.get("component_weights"),
            regime_thresholds=signals_cfg.get("regime_thresholds"),
        )
        self._last_result = None

        # Initialize database schema
        init_db()

    def _load_config(self, config_path: str) -> dict:
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file not found at {config_path}. Using defaults.")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def is_within_trading_hours(self) -> bool:
        """Returns True if current IST time is within configured trading window."""
        now_ist = datetime.now(self.trading_tz)
        # Weekend check
        if self.weekdays_only and now_ist.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return False
        # Time window check
        start = now_ist.replace(hour=self.trading_start_hour, minute=self.trading_start_minute, second=0, microsecond=0)
        end = now_ist.replace(hour=self.trading_end_hour, minute=self.trading_end_minute, second=0, microsecond=0)
        return start <= now_ist <= end

    def collect_once(self, force: bool = False) -> Dict[str, any]:
        """
        Runs a live collection cycle, extracts features, calculates score, persists, and displays.
        If force=True (e.g. user clicked Refresh Live), it unconditionally fetches and writes to DB.
        """
        is_open = self.is_within_trading_hours()

        # Gate: skip periodic background collection outside trading hours if not forced
        if not is_open and not force and self._last_result is not None:
            res = dict(self._last_result)
            res["market_closed"] = True
            return res

        cycle_time = datetime.now(timezone.utc)
        logger.info(f"Starting data collection cycle (force={force}, market_open={is_open}) at {cycle_time.isoformat()}")

        # 1. Fetch NSE Indices
        try:
            indices = self.nse_client.fetch_indices(target_names=self.target_indices)
        except Exception as e:
            logger.error(f"Error fetching NSE indices: {e}")
            indices = {}

        # 2. Fetch Macro Indicators
        try:
            macro_data = self.macro_client.fetch_all()
        except Exception as e:
            logger.error(f"Error fetching macro indicators: {e}")
            macro_data = {}

        # 3. Persist Raw Data to Database
        self._persist_data(indices, macro_data, cycle_time)

        # 4. Feature Extraction & Signal Scoring
        features = None
        signal = None
        if "NIFTY 50" in indices or "NIFTY 50".upper() in indices:
            try:
                features = self.feature_engine.process_snapshot(indices, macro_data, cycle_time)
                signal = self.score_engine.evaluate(features)
            except Exception as e:
                logger.error(f"Error evaluating features/signals: {e}")

        # 5. Display Formatted Dashboard
        self._display_summary(indices, macro_data, features, signal)

        result = {
            "indices": indices,
            "macro": macro_data,
            "features": features,
            "signal": signal,
            "timestamp": cycle_time,
            "market_closed": not is_open,
        }
        self._last_result = result
        return result

    def _persist_data(self, indices: Dict[str, IndexData], macro_data: dict, timestamp: datetime):
        """Saves snapshots into the database."""
        if not indices and not macro_data:
            logger.warning("No data to persist this cycle.")
            return

        with get_db_session() as session:
            # Save Index Snapshots
            for idx in indices.values():
                record = IndexSnapshot(
                    timestamp=timestamp,
                    index_name=idx.index_name,
                    index_symbol=idx.index_symbol,
                    open=idx.open,
                    high=idx.high,
                    low=idx.low,
                    last_price=idx.last_price,
                    previous_close=idx.previous_close,
                    change=idx.variation,
                    variation=idx.variation,
                    percent_change=idx.percent_change,
                    pe=idx.pe,
                    pb=idx.pb,
                    dy=idx.dy,
                    volume=idx.volume,
                    turnover=idx.turnover,
                )
                session.add(record)

            # Save Macro Snapshots
            for m in macro_data.values():
                m_record = MacroSnapshot(
                    timestamp=timestamp,
                    indicator_key=m.indicator_key,
                    ticker_symbol=m.ticker_symbol,
                    last_price=m.last_price,
                    change=m.change,
                    percent_change=m.percent_change,
                )
                session.add(m_record)

        logger.info(f"Successfully committed {len(indices)} index records and {len(macro_data)} macro records to DB.")

    def _display_summary(
        self,
        indices: Dict[str, IndexData],
        macro_data: dict,
        features: Optional[MarketSnapshotFeatures] = None,
        signal: Optional[SignalBreakdown] = None,
    ):
        """Displays rich terminal table with live market snapshot and directional signal dashboard."""
        # Index Table
        table = Table(title="[bold cyan]NIFTY 50 & Sector Indices Snapshot[/bold cyan]", show_header=True, header_style="bold magenta")
        table.add_column("Index", style="bold white", no_wrap=True)
        table.add_column("LTP", justify="right", style="cyan")
        table.add_column("Chg", justify="right")
        table.add_column("%Chg", justify="right")
        table.add_column("RelStr", justify="right")
        table.add_column("Low", justify="right", style="dim")
        table.add_column("High", justify="right", style="dim")
        table.add_column("P/E", justify="right", style="dim")

        # Sort with NIFTY 50 at the top, INDIA VIX at the bottom, others alphabetically
        sorted_keys = sorted(indices.keys(), key=lambda k: (k != "NIFTY 50", k == "INDIA VIX", k))

        for key in sorted_keys:
            idx = indices[key]
            pct = idx.percent_change or 0.0
            color = "green" if pct > 0 else "red" if pct < 0 else "yellow"
            sign_str = "+" if pct > 0 else ""

            # Relative strength from features
            rs_str = "-"
            if features and key in features.sector_features:
                rs_val = features.sector_features[key].relative_strength_vs_nifty
                if rs_val is not None:
                    rs_color = "green" if rs_val > 0 else "red" if rs_val < 0 else "dim"
                    rs_sign = "+" if rs_val > 0 else ""
                    rs_str = f"[{rs_color}]{rs_sign}{rs_val:.2f}%[/{rs_color}]"

            low_val = f"{idx.low:,.2f}" if idx.low else "-"
            high_val = f"{idx.high:,.2f}" if idx.high else "-"
            pe_val = f"{idx.pe:.2f}" if idx.pe else "-"

            table.add_row(
                idx.index_name,
                f"{idx.last_price:,.2f}",
                f"[{color}]{sign_str}{idx.variation:,.2f}[/{color}]",
                f"[{color}]{sign_str}{pct:.2f}%[/{color}]",
                rs_str,
                low_val,
                high_val,
                pe_val,
            )

        console.print(table)

        # Macro Table
        if macro_data:
            m_table = Table(title="[bold magenta]Macro Indicators & Global Proxies[/bold magenta]", show_header=True)
            m_table.add_column("Indicator", style="bold white", width=22)
            m_table.add_column("Ticker", style="dim", width=12)
            m_table.add_column("Price", justify="right", style="cyan")
            m_table.add_column("% Change", justify="right")

            for m in macro_data.values():
                pct = m.percent_change or 0.0
                color = "green" if pct > 0 else "red" if pct < 0 else "yellow"
                sign_str = "+" if pct > 0 else ""

                m_table.add_row(
                    m.indicator_key.replace("_", " ").title(),
                    m.ticker_symbol,
                    f"{m.last_price:,.2f}",
                    f"[{color}]{sign_str}{pct:.2f}%[/{color}]",
                )

            console.print(m_table)

        # Directional Score & Market Regime Card
        if signal and features:
            score_color = (
                "bold green" if signal.final_score >= 30.0
                else "bold red" if signal.final_score <= -30.0
                else "bold yellow"
            )
            regime_style = (
                "bold green on black" if "BULLISH" in signal.regime.value
                else "bold red on black" if "BEARISH" in signal.regime.value
                else "bold yellow on black"
            )

            score_table = Table(title="[bold yellow]NIFTY Directional Sector Model Signal[/bold yellow]", show_header=False)
            score_table.add_column("Metric", style="bold white", width=30)
            score_table.add_column("Value", style="bold cyan")

            score_table.add_row("NIFTY 50 Spot", f"{features.nifty_price:,.2f} ({features.nifty_day_change_pct:+.2f}%)")
            score_table.add_row("Directional Sector Score", f"[{score_color}]{signal.final_score:+.2f} / 100.0[/{score_color}]")
            score_table.add_row("Market Regime", f"[{regime_style}] {signal.regime.value} [/{regime_style}]")
            score_table.add_row("Component Agreement", f"{signal.agreement_ratio * 100:.0f}% of drivers aligned")
            score_table.add_row("  - Sector Momentum Score", f"{signal.momentum_score:+.1f}")
            score_table.add_row("  - Relative Strength Score", f"{signal.relative_strength_score:+.1f}")
            score_table.add_row("  - Market Breadth Score", f"{signal.breadth_score:+.1f} ({features.market_breadth.advancing_sectors} Adv / {features.market_breadth.declining_sectors} Dec)")
            score_table.add_row("  - Global Macro Score", f"{signal.macro_score:+.1f}")

            console.print(score_table)


    def run(self):
        """Starts continuous periodic data collection loop."""
        logger.info(f"Starting continuous collector daemon (interval: {self.interval_seconds}s). Press Ctrl+C to stop.")
        try:
            while True:
                start_time = time.time()
                self.collect_once()
                elapsed = time.time() - start_time
                sleep_time = max(1.0, self.interval_seconds - elapsed)
                logger.info(f"Cycle completed in {elapsed:.2f}s. Sleeping for {sleep_time:.1f}s...")
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("Collection loop stopped gracefully by user.")
