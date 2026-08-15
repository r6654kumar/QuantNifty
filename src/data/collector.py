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
from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.collector")
console = Console()


class DataCollector:
    """Orchestrates periodic collection of NSE indices and macro market data."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = self._load_config(config_path)
        
        collector_cfg = self.config.get("collector", {})
        nse_cfg = self.config.get("nse", {})

        self.interval_seconds = collector_cfg.get("interval_seconds", 300)
        self.target_indices = collector_cfg.get("indices", [])
        self.macro_tickers = collector_cfg.get("macro_tickers", {})

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

        # Initialize database schema
        init_db()

    def _load_config(self, config_path: str) -> dict:
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file not found at {config_path}. Using defaults.")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def collect_once(self) -> Dict[str, any]:
        """Runs a single live collection cycle, persists to database, and displays summary."""
        cycle_time = datetime.now(timezone.utc)
        logger.info(f"Starting data collection cycle at {cycle_time.isoformat()}")

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

        # 3. Persist to Database
        self._persist_data(indices, macro_data, cycle_time)

        # 4. Display Formatted Table
        self._display_summary(indices, macro_data)

        return {"indices": indices, "macro": macro_data, "timestamp": cycle_time}

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

    def _display_summary(self, indices: Dict[str, IndexData], macro_data: dict):
        """Displays rich terminal table with live market snapshot."""
        # Index Table
        table = Table(title="[bold cyan]NIFTY 50 & Sector Indices Snapshot[/bold cyan]", show_header=True, header_style="bold magenta")
        table.add_column("Index Name", style="bold white", no_wrap=True)
        table.add_column("LTP (INR)", justify="right", style="cyan")
        table.add_column("Change", justify="right")
        table.add_column("% Chg", justify="right")
        table.add_column("Day Low", justify="right", style="dim")
        table.add_column("Day High", justify="right", style="dim")
        table.add_column("P/E", justify="right", style="dim")

        # Sort with NIFTY 50 at the top, INDIA VIX at the bottom, others alphabetically
        sorted_keys = sorted(indices.keys(), key=lambda k: (k != "NIFTY 50", k == "INDIA VIX", k))

        for key in sorted_keys:
            idx = indices[key]
            pct = idx.percent_change or 0.0
            color = "green" if pct > 0 else "red" if pct < 0 else "yellow"
            sign = "+" if pct > 0 else ""

            low_val = f"{idx.low:,.2f}" if idx.low else "-"
            high_val = f"{idx.high:,.2f}" if idx.high else "-"
            pe_val = f"{idx.pe:.2f}" if idx.pe else "-"

            table.add_row(
                idx.index_name,
                f"{idx.last_price:,.2f}",
                f"[{color}]{sign}{idx.variation:,.2f}[/{color}]",
                f"[{color}]{sign}{pct:.2f}%[/{color}]",
                low_val,
                high_val,
                pe_val,
            )

        console.print(table)

        # Macro Table
        if macro_data:
            m_table = Table(title="[bold magenta]Macro Indicators & Global Proxies[/bold magenta]", show_header=True, expand=False)
            m_table.add_column("Indicator", style="bold white", width=24)
            m_table.add_column("Ticker", style="dim", width=14)
            m_table.add_column("Price", justify="right", style="cyan", width=14)
            m_table.add_column("% Change", justify="right", width=12)

            for m in macro_data.values():
                pct = m.percent_change or 0.0
                color = "green" if pct > 0 else "red" if pct < 0 else "yellow"
                sign = "+" if pct > 0 else ""

                m_table.add_row(
                    m.indicator_key.replace("_", " ").title(),
                    m.ticker_symbol,
                    f"{m.last_price:,.2f}",
                    f"[{color}]{sign}{pct:.2f}%[/{color}]",
                )

            console.print(m_table)

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
