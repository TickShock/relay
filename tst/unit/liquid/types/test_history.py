import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from src.tickshock.relay.liquid.types._history import (
    HistoricalOrderDto,
    _OrderLegDto,
    _ExecutionDto,
    _CashTransactionDto,
)

MOCK_TIME = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def valid_leg_data():
    return {
        "instrument": "BTC$",
        "positionEffect": "OPEN",
        "positionCode": "POS123",
        "legRatio": 1.0,
        "quantity": 1.5,
        "filledQuantity": 1.5,
        "remainingQuantity": 0.0,
        "averagePrice": 50000.0,
    }


@pytest.fixture
def valid_execution_data():
    return {
        "account": "ACC-001",
        "executionCode": "EXEC-123",
        "orderCode": "ORD-123",
        "updateOrderId": 1,
        "version": 1,
        "actionCode": "BUY",
        "instrument": "BTC$",
        "status": "COMPLETED",
        "finalStatus": True,
        "filledQuantity": 1.5,
        "lastQuantity": 1.5,
        "filledQuantityNotional": 75000.0,
        "lastQuantityNotional": 75000.0,
        "transactionTime": MOCK_TIME,
    }


@pytest.fixture
def valid_cash_data():
    return {
        "account": "ACC-001",
        "transactionCode": "TRX-123",
        "orderCode": "ORD-123",
        "tradeCode": "T-123",
        "version": 1,
        "type": "COMMISSION",
        "value": -10.5,
        "currency": "USD",
        "transactionTime": MOCK_TIME,
    }


class TestHistoricalOrderDto:
    @pytest.mark.parametrize("order_type", ["MARKET", "LIMIT", "STOP"])
    @pytest.mark.parametrize("tif", ["GTC", "DAY", "GTD"])
    def test_historical_order_initialization(
        self, valid_leg_data, valid_execution_data, valid_cash_data, order_type, tif
    ):
        order_data = {
            "account": "ACC-001",
            "version": 1,
            "orderId": 999,
            "orderCode": "ORD-123",
            "actionCode": "NEW",
            "legCount": 1,
            "type": order_type,
            "instrument": "BTC$",
            "status": "COMPLETED",
            "finalStatus": True,
            "legs": [valid_leg_data],
            "side": "BUY",
            "tif": tif,
            "issueTime": MOCK_TIME,
            "transactionTime": MOCK_TIME,
            "executions": [valid_execution_data],
            "cashTransactions": [valid_cash_data],
        }
        order = HistoricalOrderDto(**order_data)
        assert order.order_id == 999
        assert order.order_type == order_type

    @pytest.mark.parametrize(
        "missing_field",
        [
            "account",
            "version",
            "orderId",
            "orderCode",
            "actionCode",
            "legCount",
            "type",
            "instrument",
            "status",
            "finalStatus",
            "legs",
            "side",
            "tif",
            "issueTime",
            "transactionTime",
            "executions",
            "cashTransactions",
        ],
    )
    def test_historical_order_required_fields(
        self, valid_leg_data, valid_execution_data, valid_cash_data, missing_field
    ):
        order_data = {
            "account": "ACC-001",
            "version": 1,
            "orderId": 999,
            "orderCode": "ORD-123",
            "actionCode": "NEW",
            "legCount": 1,
            "type": "MARKET",
            "instrument": "BTC$",
            "status": "COMPLETED",
            "finalStatus": True,
            "legs": [valid_leg_data],
            "side": "BUY",
            "tif": "GTC",
            "issueTime": MOCK_TIME,
            "transactionTime": MOCK_TIME,
            "executions": [valid_execution_data],
            "cashTransactions": [valid_cash_data],
        }
        del order_data[missing_field]
        with pytest.raises(ValidationError):
            HistoricalOrderDto(**order_data)

    def test_historical_order_empty_lists_allowed(self, valid_leg_data):
        order_data = {
            "account": "ACC-001",
            "version": 1,
            "orderId": 999,
            "orderCode": "ORD-123",
            "actionCode": "NEW",
            "legCount": 0,
            "type": "MARKET",
            "instrument": "BTC$",
            "status": "WORKING",
            "finalStatus": False,
            "legs": [],
            "side": "SELL",
            "tif": "DAY",
            "issueTime": MOCK_TIME,
            "transactionTime": MOCK_TIME,
            "executions": [],
            "cashTransactions": [],
        }
        order = HistoricalOrderDto(**order_data)
        assert order.legs == []
        assert order.executions == []
        assert order.cash_transactions == []


class TestCashTransactionDto:
    @pytest.mark.parametrize(
        "raw_currency, expected",
        [
            ("USD$", "USD"),
            ("EUR", "EUR"),
            (" USDT$ ", "USDT"),
        ],
    )
    def test_currency_cleaning(self, valid_cash_data, raw_currency, expected):
        valid_cash_data["currency"] = raw_currency
        tx = _CashTransactionDto(**valid_cash_data)
        assert tx.currency == expected

    @pytest.mark.parametrize(
        "input_currency, expected_output",
        [
            ("USD$", "USD"),
            ("EUR", "EUR"),
            ("  GBP$  ", "GBP"),
            ("USDT$", "USDT"),
            ("CNH", "CNH"),
        ],
    )
    def test_clean_currency_validator(self, input_currency, expected_output):
        """
        Tests that the 'clean_currency' validator correctly removes the '$'
        suffix and strips whitespace from currency strings.
        """
        transaction_data = {
            "account": "ACC-123",
            "transactionCode": "TX-999",
            "orderCode": "ORD-001",
            "tradeCode": "TRD-002",
            "version": 1,
            "type": "COMMISSION",
            "value": -5.0,
            "currency": input_currency,
            "transactionTime": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }

        dto = _CashTransactionDto(**transaction_data)

        assert dto.currency == expected_output

    def test_clean_currency_non_string_bypass(self):
        """
        Ensures that if the value is not a string (e.g., None),
        the validator returns it as-is without crashing.
        """
        result = _CashTransactionDto.clean_currency(None)
        assert result is None
