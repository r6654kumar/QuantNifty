# QuantNifty: NIFTY 50 Quantitative Sector & Macro Analysis System

An experimental research and quantitative backtesting system investigating whether live sector-index momentum, relative strength, breadth, and macro drivers (Brent crude, USD/INR, global index proxies, India VIX) can provide a statistically meaningful edge for predicting short-term direction of NIFTY 50 (15/30/60-minute horizons).

> **Important**: This is a pure research and backtesting engine. It does not place live trades.

---

## Architecture & Project Structure

```
d:\QuantNifty\
├── config/
│   └── settings.yaml          # Polling interval, target indices, macro tickers
├── src/
│   ├── data/
│   │   ├── nse_client.py      # NSE session manager & data parser (curl_cffi TLS impersonation)
│   │   ├── macro_client.py    # Global proxies & commodities fetcher (yfinance)
│   │   └── collector.py       # Orchestrator & CLI table visualizer
│   ├── db/
│   │   ├── models.py          # SQLAlchemy models (IndexSnapshot, MacroSnapshot)
│   │   └── connection.py      # PostgreSQL (Neon) & SQLite engine manager
│   ├── features/              # Feature engineering (Phase 4)
│   ├── signals/               # Weighted sector score (Phase 5)
│   ├── backtest/              # Event-driven backtester & baselines (Phase 7)
│   └── utils/
│       └── logging_config.py  # Structured logging
├── data/
│   ├── raw/                   # Raw snapshots (SQLite / Parquet)
│   └── processed/             # Engineered feature matrices
├── scripts/
│   └── run_collector.py       # Live collector CLI entry point
└── tests/
    ├── test_nse_client.py     # Unit tests for NSE parser & numeric conversions
    └── test_db.py             # Unit tests for database models
```

---

## Setup & Quickstart

### 1. Environment Setup
```powershell
# Create venv and activate
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Database (Optional Neon Postgres)
Copy `.env.example` to `.env`:
```env
# Optional: Neon Serverless PostgreSQL connection string
DATABASE_URL=postgresql://user:password@ep-sample-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```
*If `DATABASE_URL` is omitted, the engine automatically uses local SQLite (`data/raw/market_data.db`).*

### 3. Run Unit Tests
```powershell
.\.venv\Scripts\pytest tests/ -v
```

### 4. Run Data Collector
```powershell
# Single snapshot test
.\.venv\Scripts\python.exe scripts/run_collector.py --once

# Continuous periodic collection daemon
.\.venv\Scripts\python.exe scripts/run_collector.py
```
