from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, IndexSnapshot, MacroSnapshot


def test_database_models_sqlite_in_memory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    now = datetime.now(timezone.utc)

    # Insert Index snapshot
    idx = IndexSnapshot(
        timestamp=now,
        index_name="NIFTY 50",
        index_symbol="NIFTY 50",
        last_price=24500.0,
        variation=50.0,
        percent_change=0.20,
        open=24450.0,
        high=24550.0,
        low=24400.0,
        previous_close=24450.0,
    )
    session.add(idx)

    # Insert Macro snapshot
    macro = MacroSnapshot(
        timestamp=now,
        indicator_key="brent_crude",
        ticker_symbol="BZ=F",
        last_price=78.50,
        change=-0.45,
        percent_change=-0.57,
    )
    session.add(macro)
    session.commit()

    # Query back
    saved_idx = session.query(IndexSnapshot).filter_by(index_name="NIFTY 50").first()
    assert saved_idx is not None
    assert saved_idx.last_price == 24500.0
    assert saved_idx.percent_change == 0.20

    saved_macro = session.query(MacroSnapshot).filter_by(indicator_key="brent_crude").first()
    assert saved_macro is not None
    assert saved_macro.last_price == 78.50

    session.close()
