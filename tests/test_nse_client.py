from unittest.mock import MagicMock, patch
from src.data.nse_client import IndexData, NSEClient


def test_safe_float_and_int_conversions():
    client = NSEClient()
    
    assert client._safe_float("24,850.50") == 24850.50
    assert client._safe_float(" - ") is None
    assert client._safe_float(None) is None
    assert client._safe_float(123.45) == 123.45
    
    assert client._safe_int("1,234,567") == 1234567
    assert client._safe_int("-") is None
    assert client._safe_int(None) is None


def test_fetch_indices_parsing_mock():
    mock_payload = {
        "data": [
            {
                "index": "NIFTY 50",
                "indexSymbol": "NIFTY 50",
                "last": "24,541.15",
                "variation": "125.30",
                "percentChange": "0.51",
                "open": "24,420.00",
                "high": "24,560.00",
                "low": "24,400.00",
                "previousClose": "24,415.85",
                "pe": "22.4",
                "pb": "4.1",
                "dy": "1.2",
                "totalTradedVolume": "15200300",
                "totalTurnover": "12500.5",
            },
            {
                "index": "NIFTY BANK",
                "indexSymbol": "NIFTY BANK",
                "last": 52340.0,
                "variation": -120.0,
                "percentChange": -0.23,
                "open": 52400.0,
                "high": 52500.0,
                "low": 52200.0,
                "previousClose": 52460.0,
            },
            {
                "index": "INDIA VIX",
                "indexSymbol": "INDIA VIX",
                "last": 13.25,
                "variation": -0.15,
                "percentChange": -1.12,
                "open": 13.40,
                "high": 13.80,
                "low": 13.10,
                "previousClose": 13.40,
            }
        ]
    }

    client = NSEClient()
    with patch.object(client, "fetch_all_indices_raw", return_value=mock_payload):
        indices = client.fetch_indices(target_names=["NIFTY 50", "NIFTY BANK", "INDIA VIX"])

        assert "NIFTY 50" in indices
        assert "NIFTY BANK" in indices
        assert "INDIA VIX" in indices

        nifty50 = indices["NIFTY 50"]
        assert nifty50.last_price == 24541.15
        assert nifty50.variation == 125.30
        assert nifty50.percent_change == 0.51
        assert nifty50.pe == 22.4
        assert nifty50.volume == 15200300

        vix = indices["INDIA VIX"]
        assert vix.last_price == 13.25
        assert vix.percent_change == -1.12
