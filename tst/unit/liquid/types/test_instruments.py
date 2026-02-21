import pytest
import re
from datetime import time, datetime, timezone, timedelta
from pydantic import ValidationError
from src.tickshock.relay.liquid.types._instrument import (
    _TradingHourDto,
    _InstrumentDto,
    _ForexDto,
    TradingHour,
    Session,
    Instrument,
    InstrumentsDtoCollection,
)


@pytest.fixture
def focal_time():
    return datetime(2023, 10, 25, 12, 0, 0, tzinfo=timezone.utc)  # A Wednesday


@pytest.mark.parametrize(
    "day, time_str, event",
    [
        ("Monday", "00:00:00Z", "SESSION_OPEN"),
        ("Friday", "23:59:59Z", "SESSION_CLOSE"),
        ("Sunday", "21:00:00Z", "SESSION_OPEN"),
    ],
)
def test_trading_hour_dto_validation_success(day, time_str, event):
    dto = _TradingHourDto(weekDay=f"{day}, {time_str}", eventType=event)
    assert dto.weekDay == f"{day}, {time_str}"


@pytest.mark.parametrize(
    "invalid_weekday",
    [
        "Mon, 12:00:00Z",
        "Funday, 12:00:00Z",
        "Monday 12:00:00Z",
        "Monday, 12:00Z",
    ],
)
def test_trading_hour_dto_validation_failure(invalid_weekday):
    with pytest.raises(ValidationError):
        _TradingHourDto(weekDay=invalid_weekday, eventType="SESSION_OPEN")


@pytest.mark.parametrize(
    "day_name, day_int, time_obj",
    [
        ("Monday", 0, time(9, 0)),
        ("Wednesday", 2, time(17, 30)),
        ("Sunday", 6, time(22, 0)),
    ],
)
def test_trading_hour_bo_init(day_name, day_int, time_obj):
    dto = _TradingHourDto(weekDay=f"{day_name}, {time_obj}Z", eventType="SESSION_OPEN")
    bo = TradingHour(dto)
    assert bo.week_day == day_name
    assert bo.week_day_int == day_int
    assert bo.time == time_obj


@pytest.mark.parametrize(
    "th_day, th_time, expected_dt",
    [
        ("Wednesday", time(10, 0), datetime(2023, 10, 25, 10, 0, tzinfo=timezone.utc)),
        ("Wednesday", time(15, 0), datetime(2023, 10, 18, 15, 0, tzinfo=timezone.utc)),
        ("Tuesday", time(10, 0), datetime(2023, 10, 24, 10, 0, tzinfo=timezone.utc)),
        ("Monday", time(9, 0), datetime(2023, 10, 23, 9, 0, tzinfo=timezone.utc)),
    ],
)
def test_trading_hour_to_dt(focal_time, th_day, th_time, expected_dt):
    th = TradingHour.const(th_day, th_time, "SESSION_OPEN")
    assert th.to_dt(focal_time) == expected_dt


def test_trading_hour_dto_to_bo():
    now = datetime(2023, 10, 23, 9, 0, tzinfo=timezone.utc)
    actual = _TradingHourDto(weekDay="Monday, 23:30:00Z", eventType="SESSION_OPEN")
    assert isinstance(actual.to_bo(), TradingHour)


def test_session_init_success(focal_time):
    th_open = TradingHour.const("Monday", time(9, 0), "SESSION_OPEN")
    th_close = TradingHour.const("Monday", time(17, 0), "SESSION_CLOSE")
    session = Session(th_open, th_close, focal_time)
    assert session.open_time < session.close_time
    assert session.close_time - session.open_time == timedelta(hours=8)


def test_session_invalid_event_types(focal_time):
    th1 = TradingHour.const("Monday", time(9, 0), "SESSION_CLOSE")
    th2 = TradingHour.const("Monday", time(17, 0), "SESSION_OPEN")
    with pytest.raises(ValueError, match="sessions need to begin and end"):
        Session(th1, th2, focal_time)


def test_session_too_long(focal_time):
    th_open = TradingHour.const("Monday", time(9, 0), "SESSION_OPEN")
    th_close = TradingHour.const("Tuesday", time(10, 0), "SESSION_CLOSE")
    with pytest.raises(ValueError, match="can not be longer than 24 hours"):
        Session(th_open, th_close, focal_time)


def test_instrument_dto_collection_polymorphism():
    data = {
        "instruments": [
            {
                "symbol": "EURUSD",
                "type": "FOREX",
                "version": 1,
                "description": "Euro",
                "priceIncrement": 0.00001,
                "pipSize": 0.0001,
                "lotSize": 100000,
                "multiplier": 1,
                "currency": "USD",
                "firstCurrency": "EUR",
                "assetClass": "FX",
            },
            {
                "symbol": "AAPL",
                "type": "CFD_STOCK",
                "version": 1,
                "description": "Apple",
                "priceIncrement": 0.01,
                "pipSize": 0.01,
                "lotSize": 1,
                "multiplier": 1,
                "currency": "USD",
                "assetClass": "EQUITY",
            },
        ]
    }
    collection = InstrumentsDtoCollection(**data)
    assert len(collection.instruments) == 2
    assert isinstance(collection.instruments[0], _ForexDto)
    assert collection.instruments[1].type == "CFD_STOCK"


@pytest.mark.parametrize("symbol", ["BTC$", "ETHUSDTPERP", "XAUUSD.cent", "AAPL"])
def test_instrument_bo_mapping(symbol):
    dto = _InstrumentDto(
        symbol=symbol,
        version=1,
        description="Test",
        priceIncrement=0.1,
        pipSize=0.1,
        lotSize=1.0,
        multiplier=1.0,
        tradingHours=[{"weekDay": "Monday, 09:00:00Z", "eventType": "SESSION_OPEN"}],
    )
    ins = Instrument(dto)
    assert ins.symbol == symbol
    assert len(ins.trading_hours) == 1
    assert isinstance(ins.trading_hours[0], TradingHour)


def test_session_create_sessions_batch(focal_time):
    ths = [
        TradingHour.const("Monday", time(9, 0), "SESSION_OPEN"),
        TradingHour.const("Monday", time(17, 0), "SESSION_CLOSE"),
        TradingHour.const("Tuesday", time(9, 0), "SESSION_OPEN"),
        TradingHour.const("Tuesday", time(17, 0), "SESSION_CLOSE"),
    ]
    sessions = Session.create_sessions(ths, focal_time)
    assert len(sessions) == 2
    assert sessions[0].start_day == "Monday"
    assert sessions[1].start_day == "Tuesday"
