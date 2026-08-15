import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.backtest.engine import BacktestEngine
from src.data.collector import DataCollector
from src.db.connection import get_db_session
from src.db.models import IndexSnapshot, MacroSnapshot
from src.signals.ai_summary import AISummaryEngine
from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.api")

app = FastAPI(
    title="QuantNifty API",
    description="Quantitative NIFTY 50 Sector Momentum & Macro Analysis Backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
collector = DataCollector(config_path="config/settings.yaml")
backtest_engine = BacktestEngine(
    score_engine=collector.score_engine,
    feature_engine=collector.feature_engine,
)
ai_summary_engine = AISummaryEngine()

# Static files path
static_dir = Path(__file__).resolve().parent.parent.parent / "static"
if not static_dir.exists():
    static_dir.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/snapshot")
def get_live_snapshot(refresh: bool = False):
    """
    Returns the latest market snapshot, engineered features, directional sector score,
    and AI quantitative intelligence briefing with options trade recommendations.
    """
    result = collector.collect_once(force=refresh)
    market_closed = result.get("market_closed", False)

    ai_summary = ai_summary_engine.generate_summary(
        features=result.get("features"),
        signal=result.get("signal"),
        indices=result.get("indices", {}),
        macro_data=result.get("macro", {}),
    )

    return {
        "timestamp": result["timestamp"].isoformat(),
        "market_closed": market_closed,
        "nifty_price": result["features"].nifty_price if result["features"] else None,
        "indices": {k: v.model_dump() for k, v in result["indices"].items()} if result["indices"] else {},
        "macro": {k: v.model_dump() for k, v in result["macro"].items()} if result["macro"] else {},
        "features": result["features"].model_dump() if result["features"] else None,
        "signal": result["signal"].model_dump() if result["signal"] else None,
        "ai_summary": ai_summary.model_dump(),
    }


@app.get("/api/backtest")
def run_backtest(
    horizon: str = Query(default="15m", pattern="^(5m|15m|30m|60m)$"),
    source: str = Query(default="simulation", pattern="^(simulation|database)$"),
):
    """
    Runs quantitative backtest evaluating Sector Model against all 4 baselines.
    """
    horizon_bars = {"5m": 1, "15m": 3, "30m": 6, "60m": 12}.get(horizon, 3)

    if source == "database":
        result = backtest_engine.run_from_database(horizon_label=horizon, horizon_bars=horizon_bars)
    else:
        result = backtest_engine.run_calibrated_simulation(n_bars=300, horizon_label=horizon, horizon_bars=horizon_bars)

    return result.model_dump()


@app.get("/api/history")
def get_history(limit: int = 50):
    """Returns recent historical database records for NIFTY 50 and key sectors."""
    with get_db_session() as session:
        records = (
            session.query(IndexSnapshot)
            .filter(IndexSnapshot.index_name == "NIFTY 50")
            .order_by(IndexSnapshot.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "last_price": r.last_price,
                "change": r.change,
                "percent_change": r.percent_change,
            }
            for r in reversed(records)
        ]


# Mount static directory
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def serve_dashboard():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "QuantNifty API is running. Place index.html in static/"}
