from datetime import datetime, timezone
from typing import Dict, Optional
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
        "brent_crude": "BZ=F",
        "wti_crude": "CL=F",
        "usd_inr": "USDINR=X",
        "sp500": "^GSPC",
        "nasdaq": "^IXIC",
        "nikkei": "^N225",
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
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else float(hist["Open"].iloc[0])
                    change = last_price - prev_close
                    pct_change = (change / prev_close) * 100.0 if prev_close else 0.0

                    results[key] = MacroData(
                        indicator_key=key,
                        ticker_symbol=symbol,
                        last_price=last_price,
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
