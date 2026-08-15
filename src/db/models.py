from datetime import datetime, timezone
from sqlalchemy import BigInteger, Column, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class IndexSnapshot(Base):
    """Raw snapshot of an index at a given timestamp."""
    __tablename__ = "index_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    index_name = Column(String(64), nullable=False, index=True)
    index_symbol = Column(String(64), nullable=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    last_price = Column(Float, nullable=False)
    previous_close = Column(Float, nullable=True)
    change = Column(Float, nullable=True)
    variation = Column(Float, nullable=True)
    percent_change = Column(Float, nullable=True)
    pe = Column(Float, nullable=True)
    pb = Column(Float, nullable=True)
    dy = Column(Float, nullable=True)
    volume = Column(BigInteger, nullable=True)
    turnover = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_index_timestamp_name", "timestamp", "index_name", unique=True),
    )

    def __repr__(self) -> str:
        return f"<IndexSnapshot(index='{self.index_name}', last={self.last_price}, time='{self.timestamp}')>"


class MacroSnapshot(Base):
    """Raw snapshot of macro indicators (Brent, USDINR, S&P 500, etc.)."""
    __tablename__ = "macro_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    indicator_key = Column(String(64), nullable=False, index=True)
    ticker_symbol = Column(String(32), nullable=False)
    last_price = Column(Float, nullable=False)
    change = Column(Float, nullable=True)
    percent_change = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_macro_timestamp_key", "timestamp", "indicator_key", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MacroSnapshot(indicator='{self.indicator_key}', symbol='{self.ticker_symbol}', price={self.last_price})>"
