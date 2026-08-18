"""
FII/DII Flows Client — Phase 4 Signal Enhancement
Fetches daily Foreign Institutional Investor (FII) and Domestic Institutional Investor (DII)
equity flow data from NSE India.

Predictive Horizon: 1–3 day leading indicator (end-of-day data used for next-day forecasting)
Correlation to NIFTY 50: +0.55 for FII (structural capital flow driver)

Data Source: NSE India public API
Latency: End-of-day (~16:30 IST). Use previous day's data as next-day feature.

NOTE: NSE API endpoints occasionally change structure. The client implements
graceful degradation — returns None if data is unavailable or malformed.

Endpoint discovery:
  Primary: /api/fiidiiTradeReact (equity + derivatives combined)
  Fallback: /api/fii-fo-participant
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import requests
from pydantic import BaseModel, Field

from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.fii")


class FIIDIISnapshot(BaseModel):
    """Daily FII/DII equity flows snapshot."""
    date: str                                      # YYYY-MM-DD
    fii_inflow_crores: float                       # Positive = Inflow, Negative = Outflow
    dii_inflow_crores: float                       # DII flows (usually counter to FII)
    net_flow_crores: float                         # FII + DII combined
    fii_volume: Optional[float] = None             # Total FII notional traded (Cr)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FIIClient:
    """
    Fetches FII/DII equity flows from NSE India.

    Usage::
        client = FIIClient()
        data = client.fetch_daily_flows()
        if data:
            print(f"FII: {data.fii_inflow_crores:+.0f} Cr | DII: {data.dii_inflow_crores:+.0f} Cr")
    """

    NSE_BASE_URL = "https://www.nseindia.com"
    REQUEST_TIMEOUT = 15  # seconds

    # Ordered list of endpoints to try (NSE changes these periodically)
    ENDPOINTS = [
        "/api/fiidiiTradeReact",       # Primary: equity + derivatives combined view
        "/api/fii-fo-participant",     # Fallback 1: F&O participant-wise data
        "/api/fii-stats",              # Fallback 2: older endpoint
    ]

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
        })
        self._establish_nse_session()

    def _establish_nse_session(self) -> None:
        """
        NSE requires a valid browser session cookie before API calls succeed.
        Hits the homepage first to acquire session cookies.
        """
        try:
            self.session.get(
                self.NSE_BASE_URL,
                timeout=self.timeout,
                allow_redirects=True,
            )
        except Exception as e:
            logger.debug(f"FIIClient: Session establishment warning (non-fatal): {e}")

    def fetch_daily_flows(self) -> Optional[FIIDIISnapshot]:
        """
        Fetch most recent available FII/DII equity flows.

        Returns:
            FIIDIISnapshot with flow data in crores,
            or None if all endpoints fail / data is unavailable.
        """
        for endpoint in self.ENDPOINTS:
            result = self._try_endpoint(endpoint)
            if result is not None:
                return result

        logger.warning(
            "FIIClient: All NSE endpoints failed. FII/DII signal will default to 0.0. "
            "Check NSE API structure or network connectivity."
        )
        return None

    def _try_endpoint(self, endpoint: str) -> Optional[FIIDIISnapshot]:
        """Attempt to fetch and parse FII/DII data from a specific NSE endpoint."""
        url = f"{self.NSE_BASE_URL}{endpoint}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            snapshot = self._parse_response(data)
            if snapshot:
                logger.info(
                    f"FIIClient [{endpoint}]: "
                    f"FII {snapshot.fii_inflow_crores:+.0f} Cr | "
                    f"DII {snapshot.dii_inflow_crores:+.0f} Cr | "
                    f"Net {snapshot.net_flow_crores:+.0f} Cr"
                )
            return snapshot

        except requests.exceptions.Timeout:
            logger.debug(f"FIIClient: Timeout on {endpoint}")
            return None
        except requests.exceptions.RequestException as e:
            logger.debug(f"FIIClient: Request error on {endpoint}: {e}")
            return None
        except (ValueError, KeyError) as e:
            logger.debug(f"FIIClient: Parse error on {endpoint}: {e}")
            return None
        except Exception as e:
            logger.debug(f"FIIClient: Unexpected error on {endpoint}: {e}")
            return None

    def _parse_response(self, data: dict) -> Optional[FIIDIISnapshot]:
        """
        Parse NSE API response into FIIDIISnapshot.
        Handles multiple known response structures defensively.
        """
        now = datetime.now(timezone.utc)
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Structure 1: {"data": [{"date": ..., "fii": ..., "dii": ...}]}
        if isinstance(data, dict) and "data" in data:
            rows = data["data"]
            if rows and isinstance(rows, list):
                latest = rows[0]
                fii = self._safe_float(latest, ["fii", "FII", "net_fii", "netBuyingValue"])
                dii = self._safe_float(latest, ["dii", "DII", "net_dii"])
                date_str = latest.get("date", latest.get("tradeDate", today_str))
                if fii is not None and dii is not None:
                    return FIIDIISnapshot(
                        date=str(date_str)[:10],
                        fii_inflow_crores=fii,
                        dii_inflow_crores=dii,
                        net_flow_crores=round(fii + dii, 2),
                        timestamp=now,
                    )

        # Structure 2: list of participant rows (F&O endpoint or TradeReact)
        if isinstance(data, list) and len(data) > 0:
            fii_row = next(
                (r for r in data if str(r.get("clientType", r.get("category", ""))).upper() in ("FII", "FII/FPI")),
                None,
            )
            dii_row = next(
                (r for r in data if str(r.get("clientType", r.get("category", ""))).upper() == "DII"),
                None,
            )
            if fii_row:
                fii = self._safe_float(fii_row, ["netAmount", "net", "buyAmount", "netValue"])
                dii = self._safe_float(dii_row, ["netAmount", "net", "buyAmount", "netValue"]) if dii_row else 0.0
                if fii is not None:
                    # Also try to get date
                    date_str = fii_row.get("date", today_str)
                    return FIIDIISnapshot(
                        date=str(date_str)[:11],
                        fii_inflow_crores=fii,
                        dii_inflow_crores=dii,
                        net_flow_crores=round(fii + dii, 2),
                        timestamp=now,
                    )

        return None

    @staticmethod
    def _safe_float(row: dict, keys: list) -> Optional[float]:
        """Try multiple key names and return the first valid float found."""
        for key in keys:
            val = row.get(key)
            if val is not None:
                try:
                    return round(float(str(val).replace(",", "")), 2)
                except (ValueError, TypeError):
                    continue
        return None
