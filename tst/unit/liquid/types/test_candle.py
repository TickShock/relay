import pytest
import re
from datetime import datetime, timezone
from pydantic import ValidationError
from tickshock.ground.exceptions import TickShockException
from tickshock.ground.types import Candle
from src.tickshock.relay.liquid.types._candle import CandleDto

MOCK_TIME = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "candle_type, open_val, close_val, high_val, low_val, volume",
    [
        ("m", 100.0, 105.0, 110.0, 95.0, 1000.0),
        ("5m", 50.5, 50.2, 51.0, 50.0, 500.0),
        ("h", 1.234, 1.235, 1.236, 1.233, 10.0),
        ("d", 60000.0, 61000.0, 62000.0, 59000.0, 0.5),
        ("w", 10.0, 20.0, 25.0, 5.0, 100.0),
    ],
)
def test_candle_dto_to_bo_success(
    candle_type, open_val, close_val, high_val, low_val, volume
):
    dto = CandleDto(
        symbol="BTC$",
        type="Candle",
        candleType=candle_type,
        open=open_val,
        close=close_val,
        high=high_val,
        low=low_val,
        volume=volume,
        time=MOCK_TIME,
    )

    bo = dto.to_bo()

    assert isinstance(bo, Candle)
    assert bo.symbol == "BTC$"
    assert bo.type == candle_type
    assert bo.open == open_val
    assert bo.close == close_val
    assert bo.high == high_val
    assert bo.low == low_val
    assert bo.volume == volume
    assert bo.time == MOCK_TIME


def test_candle_dto_to_bo_monthly_raises():
    dto = CandleDto(
        symbol="BTC$",
        type="Candle",
        candleType="mo",
        open=100.0,
        close=110.0,
        high=120.0,
        low=90.0,
        volume=1.0,
        time=MOCK_TIME,
    )

    with pytest.raises(
        TickShockException, match=re.escape("'BTC$' must have up to a 1-week interval")
    ):
        dto.to_bo()


@pytest.mark.parametrize(
    "invalid_field, invalid_value",
    [
        ("candleType", "1m"),  # Invalid literal
        ("candleType", "hourly"),  # Invalid literal
        ("type", "Trade"),  # Must be "Candle"
        ("open", "not-a-float"),  # Type mismatch
        ("symbol", "INVALID_SYM"),  # Not in SymbolLiteral
    ],
)
def test_candle_dto_validation_errors(invalid_field, invalid_value):
    base_data = {
        "symbol": "BTC$",
        "type": "Candle",
        "candleType": "m",
        "open": 100.0,
        "close": 105.0,
        "high": 110.0,
        "low": 95.0,
        "volume": 1000.0,
        "time": MOCK_TIME,
    }
    base_data[invalid_field] = invalid_value

    with pytest.raises(ValidationError):
        CandleDto(**base_data)


def test_candle_dto_from_iso_string():
    iso_time = "2023-05-01T10:00:00Z"
    dto = CandleDto(
        symbol="ETH$",
        type="Candle",
        candleType="h",
        open=2000.0,
        close=2010.0,
        high=2020.0,
        low=1990.0,
        volume=5.0,
        time=iso_time,  # Pydantic handles string to datetime conversion
    )

    assert dto.time.year == 2023
    assert dto.time.month == 5
    assert dto.time.day == 1
