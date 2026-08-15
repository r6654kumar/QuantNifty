import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from curl_cffi import requests
from pydantic import BaseModel, Field

from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.nse")


class IndexData(BaseModel):
    """Normalized index data model."""
    index_name: str
    index_symbol: Optional[str] = None
    last_price: float
    variation: Optional[float] = 0.0
    percent_change: Optional[float] = 0.0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    previous_close: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    dy: Optional[float] = None
    volume: Optional[int] = None
    turnover: Optional[float] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NSEClient:
    """Robust client for fetching live index data from NSE using curl_cffi browser impersonation."""

    def __init__(
        self,
        base_url: str = "https://www.nseindia.com",
        all_indices_endpoint: str = "/api/allIndices",
        timeout: int = 15,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        min_request_gap: float = 3.0,
        session_refresh_minutes: int = 4,
    ):
        self.base_url = base_url.rstrip("/")
        self.all_indices_endpoint = all_indices_endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.min_request_gap = min_request_gap
        self.session_refresh_minutes = session_refresh_minutes

        self._session: Optional[requests.Session] = None
        self._session_created_at: float = 0.0
        self._last_request_time: float = 0.0

        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
            "Connection": "keep-alive",
        }

    def _ensure_session(self) -> requests.Session:
        """Initializes or refreshes the browser-impersonated session with fresh NSE cookies."""
        now = time.time()
        session_age_minutes = (now - self._session_created_at) / 60.0

        if self._session is None or session_age_minutes >= self.session_refresh_minutes:
            if self._session is not None:
                logger.info(f"Session expired ({session_age_minutes:.1f}m old). Refreshing...")
                try:
                    self._session.close()
                except Exception:
                    pass

            logger.info("Initializing new NSE session with Chrome TLS impersonation...")
            self._session = requests.Session(impersonate="chrome120")
            self._session.headers.update(self.default_headers)

            # Visit homepage to trigger cookie handshake (bm_sv, ak_bmsc, etc.)
            try:
                home_resp = self._session.get(
                    self.base_url,
                    timeout=self.timeout,
                )
                if home_resp.status_code != 200:
                    logger.warning(f"NSE homepage returned status {home_resp.status_code}")
                self._session_created_at = time.time()
                logger.info(f"NSE session established. Cookies obtained: {len(self._session.cookies)}")
            except Exception as e:
                logger.error(f"Failed to bootstrap NSE session cookies: {e}")
                # We don't fail hard here; subsequent call might still succeed or retry

        return self._session

    def _rate_limit_wait(self):
        """Enforces a safe cooldown gap between consecutive API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_request_gap:
            sleep_time = self.min_request_gap - elapsed
            time.sleep(sleep_time)

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely parses float values from raw strings or numbers, handling commas and dashes."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if not cleaned or cleaned == "-":
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely parses integer values from raw strings or numbers."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if not cleaned or cleaned == "-":
                return None
            try:
                return int(float(cleaned))
            except ValueError:
                return None
        return None

    def fetch_all_indices_raw(self) -> Dict[str, Any]:
        """Fetches raw JSON payload from /api/allIndices with retry & backoff."""
        url = f"{self.base_url}{self.all_indices_endpoint}"
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self._rate_limit_wait()
                session = self._ensure_session()

                self._last_request_time = time.time()
                response = session.get(url, timeout=self.timeout)

                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and isinstance(data["data"], list):
                        return data
                    else:
                        logger.warning(f"Unexpected response structure on attempt {attempt}: keys={list(data.keys())}")
                elif response.status_code in (401, 403):
                    logger.warning(f"Received status {response.status_code} (access restricted). Forcing session re-creation...")
                    self._session = None  # Force new session next attempt
                else:
                    logger.warning(f"Attempt {attempt}/{self.max_retries}: HTTP {response.status_code}")

            except Exception as e:
                last_exception = e
                logger.warning(f"Attempt {attempt}/{self.max_retries} failed: {e}")

            if attempt < self.max_retries:
                backoff_wait = self.retry_delay * (2 ** (attempt - 1))
                time.sleep(backoff_wait)

        error_msg = f"Failed to fetch NSE allIndices after {self.max_retries} attempts."
        if last_exception:
            error_msg += f" Last error: {last_exception}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)

    def fetch_indices(self, target_names: Optional[List[str]] = None) -> Dict[str, IndexData]:
        """
        Fetches all indices and returns a dictionary mapped by normalized index name.
        If target_names is specified, only returns those indices (or all found).
        """
        raw_payload = self.fetch_all_indices_raw()
        items = raw_payload.get("data", [])
        snapshot_time = datetime.now(timezone.utc)
        result: Dict[str, IndexData] = {}

        target_set = {name.upper() for name in target_names} if target_names else None

        for item in items:
            name = item.get("index") or item.get("indexSymbol")
            if not name:
                continue

            name_clean = name.strip()
            name_upper = name_clean.upper()

            if target_set and name_upper not in target_set:
                # Also allow partial match for synonyms like "NIFTY PRIVATE BANK" vs "NIFTY PVT BANK"
                continue

            last_price = self._safe_float(item.get("last"))
            if last_price is None:
                continue

            index_obj = IndexData(
                index_name=name_clean,
                index_symbol=item.get("indexSymbol"),
                last_price=last_price,
                variation=self._safe_float(item.get("variation")) or 0.0,
                percent_change=self._safe_float(item.get("percentChange")) or 0.0,
                open=self._safe_float(item.get("open")),
                high=self._safe_float(item.get("high")),
                low=self._safe_float(item.get("low")),
                previous_close=self._safe_float(item.get("previousClose")),
                pe=self._safe_float(item.get("pe")),
                pb=self._safe_float(item.get("pb")),
                dy=self._safe_float(item.get("dy")),
                volume=self._safe_int(item.get("totalTradedVolume")),
                turnover=self._safe_float(item.get("totalTurnover")),
                timestamp=snapshot_time,
            )
            result[name_upper] = index_obj

        logger.info(f"Successfully fetched and parsed {len(result)} indices from NSE.")
        return result
