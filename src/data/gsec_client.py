"""
GSec Yield Client — Phase 3 Signal Enhancement
Fetches India 10-Year Government Security yield as a real-time rate expectations proxy.

Correlation to NIFTY 50: -0.65 (inverse; rising yields = tighter monetary conditions = equity headwind)
Predictive Horizon: 15-minute to 4-hour signals

Data Source: Moneycontrol (webscrape, real-time)
Fallback: Returns None gracefully; calling code must handle missing data.

TODO: If Moneycontrol HTML structure changes, update CSS selectors below or switch to:
  - CBONDS.IN (dedicated bond portal)
  - NSE Interest Rate Products (https://www.nseindia.com/market-data/gov-securities-data)
  - RBI official website (https://rbi.org.in)
"""

from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.gsec")


class GSECYieldData(BaseModel):
    """India 10Y Government Security yield snapshot."""
    yield_percent: float                           # e.g. 6.95 for 6.95%
    change_bps: float = 0.0                        # Intraday change in basis points
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GSECYieldClient:
    """
    Fetches India 10Y GSec yield from Moneycontrol (real-time webscrape).

    Usage::
        client = GSECYieldClient()
        data = client.fetch_10y_yield()
        if data:
            print(f"10Y GSec: {data.yield_percent}% ({data.change_bps:+.1f} bps)")
    """

    MONEYCONTROL_URL = "https://www.moneycontrol.com/bonds/gsec-bonds/"
    REQUEST_TIMEOUT = 10  # seconds

    # CSS selectors for Moneycontrol page — update here if scraping breaks
    YIELD_SELECTORS = [
        # Primary: span with class font14 fw600 (observed in 2026 layout)
        {"tag": "span", "attrs": {"class": "font14 fw600"}},
        # Fallback 1: td cell in gsec table
        {"tag": "td", "attrs": {"class": "grnClr"}},
        # Fallback 2: generic bond yield cell
        {"tag": "span", "attrs": {"id": "sp_14_210"}},
    ]

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        # Cache last fetched yield to compute change_bps across calls
        self._last_yield: Optional[float] = None

    def fetch_10y_yield(self) -> Optional[GSECYieldData]:
        """
        Fetch current India 10Y GSec yield.

        Returns:
            GSECYieldData with yield_percent (e.g. 6.95) and change_bps,
            or None if fetch/parse fails (caller must handle gracefully).
        """
        try:
            response = requests.get(
                self.MONEYCONTROL_URL,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            yield_value = self._parse_yield(soup)

            if yield_value is None:
                logger.warning(
                    "GSECYieldClient: Could not parse 10Y yield from Moneycontrol HTML. "
                    "Page structure may have changed — update YIELD_SELECTORS."
                )
                return None

            # Calculate change_bps from last cached value
            change_bps = 0.0
            if self._last_yield is not None:
                change_bps = round((yield_value - self._last_yield) * 100.0, 2)  # % → bps

            self._last_yield = yield_value

            result = GSECYieldData(
                yield_percent=yield_value,
                change_bps=change_bps,
            )
            logger.info(f"GSec 10Y: {yield_value:.2f}% ({change_bps:+.1f} bps)")
            return result

        except requests.exceptions.Timeout:
            logger.warning("GSECYieldClient: Request timed out — will retry next cycle.")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"GSECYieldClient: Network error fetching GSec yield: {e}")
            return None
        except Exception as e:
            logger.warning(f"GSECYieldClient: Unexpected error: {e}")
            return None

    def _parse_yield(self, soup: BeautifulSoup) -> Optional[float]:
        """
        Attempt to extract 10Y GSec yield percentage from parsed HTML.
        Tries multiple selectors in priority order.
        """
        for selector in self.YIELD_SELECTORS:
            elements = soup.find_all(selector["tag"], attrs=selector["attrs"])
            for el in elements:
                text = el.get_text(strip=True)
                # Strip common suffixes and try to parse as float
                clean = text.replace("%", "").replace(",", "").strip()
                try:
                    value = float(clean)
                    # Sanity check: India 10Y GSec yield is realistically in 5.5% – 9.0% range
                    if 5.0 <= value <= 12.0:
                        return round(value, 4)
                except ValueError:
                    continue

        # Last resort: search for any text matching a yield pattern in the page
        import re
        text = soup.get_text()
        # Look for patterns like "6.95" or "7.12" near "10" or "10Y"
        matches = re.findall(r"\b([6-8]\.\d{2})\b", text)
        if matches:
            # Take the most commonly occurring value (mode)
            from collections import Counter
            most_common = Counter(matches).most_common(1)[0][0]
            value = float(most_common)
            if 5.0 <= value <= 12.0:
                logger.debug(f"GSECYieldClient: Used regex fallback, found yield: {value}")
                return round(value, 4)

        return None
