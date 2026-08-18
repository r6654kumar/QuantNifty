from datetime import datetime, timezone
from typing import Dict, Optional
import math
from pydantic import BaseModel, Field
import yfinance as yf

from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.macro")


class MacroData(BaseModel):
    """Normalized macro data point."""
    indicator_key: str
    ticker_symbol: str
    last_price: float
    change: Optional[float] = 0.0
    percent_change: Optional[float] = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MacroClient:
    """Client to retrieve global commodities, currencies, and index proxies."""

    DEFAULT_TICKERS = {
        # --- Existing: US & Japan equity proxies + commodities + FX ---
        "brent_crude": "BZ=F",
        "wti_crude": "CL=F",
        "usd_inr": "USDINR=X",
        "sp500": "^GSPC",
        "nasdaq": "^IXIC",
        "nikkei": "^N225",
        # --- Phase 2 New: Safe haven, growth proxy, currency, Asia sentiment ---
        "gold_spot": "GC=F",           # Safe-haven proxy; inverse risk appetite
        "copper_spot": "HG=F",         # "Dr. Copper" — leading economic growth indicator
        "dxy": "DX-Y.NYB",                 # US Dollar Index (ICE futures; inverse of INR/EM strength)
        "hang_seng": "^HSI",           # China/Asia macro sentiment (trades pre-Indian open)
        "kospi": "^KS11",              # Korea — semiconductor & tech cycle bellwether
        "singapore_sti": "^STI",       # Singapore STI — Asia regional proxy
    }

    def __init__(self, tickers: Optional[Dict[str, str]] = None):
        self.tickers = tickers or self.DEFAULT_TICKERS

    def fetch_all(self) -> Dict[str, MacroData]:
        """Fetches latest prices for configured macro tickers."""
        results: Dict[str, MacroData] = {}
        now = datetime.now(timezone.utc)

        for key, symbol in self.tickers.items():
            try:
                ticker = yf.Ticker(symbol)
                # Fetch recent 2-day history for fast single-bar extraction
                hist = ticker.history(period="2d", interval="1d")
                if hist.empty:
                    # Try intraday 1d
                    hist = ticker.history(period="1d", interval="5m")

                if not hist.empty:
                    last_price = float(hist["Close"].iloc[-1])
                    
                    # Defensive: Check if last_price is valid (not NaN, not inf)
                    if not math.isfinite(last_price):
                        logger.warning(
                            f"Invalid last_price for macro ticker {key} ({symbol}): {last_price} "
                            f"(non-finite value). Skipping."
                        )
                        continue
                    
                    # Get previous close, defaulting to open if only 1 bar available
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else float(hist["Open"].iloc[0])
                    
                    # Defensive: Check if prev_close is valid (not NaN, not inf, not zero)
                    if not math.isfinite(prev_close) or prev_close == 0.0:
                        logger.warning(
                            f"Invalid prev_close for macro ticker {key} ({symbol}): {prev_close} "
                            f"(non-finite or zero). Skipping."
                        )
                        continue
                    
                    # Compute change and percent change
                    change = last_price - prev_close
                    pct_change = (change / prev_close) * 100.0
                    
                    # Defensive: Sanitize to 0.0 if somehow NaN (extra safety)
                    if not math.isfinite(change):
                        change = 0.0
                    if not math.isfinite(pct_change):
                        pct_change = 0.0

                    results[key] = MacroData(
                        indicator_key=key,
                        ticker_symbol=symbol,
                        last_price=round(last_price, 4),
                        change=round(change, 4),
                        percent_change=round(pct_change, 4),
                        timestamp=now,
                    )
                else:
                    logger.warning(f"No price history returned for macro ticker {key} ({symbol})")
            except Exception as e:
                logger.warning(f"Error fetching macro ticker {key} ({symbol}): {e}")

        logger.info(f"Successfully retrieved {len(results)}/{len(self.tickers)} macro indicators.")
        return results
