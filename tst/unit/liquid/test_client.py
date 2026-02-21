import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime
from http import HTTPMethod
from src.tickshock.relay.liquid import Liquid
from src.tickshock.relay.liquid.exceptions import (
    LiquidApiException,
    LiquidApiAuthException,
)

MOCK_CREDS = {
    "username": "user123",
    "password": "password123",
    "api_base_url": "https://api.test.com",
    "account_id": "888",
}

MOCK_LOGIN_RESPONSE = {"sessionToken": "fake-token-123"}


def append_target_module(var_name: str) -> str:
    return f"src.tickshock.relay.liquid._client.{var_name}"


@pytest.fixture
def mock_requests():
    with patch(append_target_module("_request")) as mocked:
        yield mocked


@pytest.fixture
def liquid_client(mock_requests):
    mock_requests.return_value.json.return_value = MOCK_LOGIN_RESPONSE
    mock_requests.return_value.ok = True
    return Liquid(**MOCK_CREDS)


class TestLiquidInit:
    def test_init_success(self, mock_requests):
        mock_requests.return_value.json.return_value = MOCK_LOGIN_RESPONSE
        mock_requests.return_value.ok = True

        client = Liquid(**MOCK_CREDS)

        assert client._session_token == "fake-token-123"
        assert client._account_code == "default%3A888"
        mock_requests.assert_called_once()

    def test_init_auth_failure(self, mock_requests):
        mock_requests.return_value.json.return_value = {"error": "unauthorized"}

        with pytest.raises(LiquidApiAuthException, match="session token not received"):
            Liquid(**MOCK_CREDS)

    def test_const_with_envvars(self, mock_requests):
        mock_requests.return_value.json.return_value = MOCK_LOGIN_RESPONSE
        mock_requests.return_value.ok = True
        env_map = {
            "LIQUID_UN": "env_user",
            "LIQUID_PW": "env_pw",
            "LIQUID_API_BASE_URL": "https://env.api.com",
            "LIQUID_ACCOUNT_ID": "999",
        }
        with patch(
            "src.tickshock.relay.liquid._client._get_env",
            side_effect=lambda k: env_map[k],
        ):
            client = Liquid.const_with_envvars()
            assert client._username == "env_user"
            assert client._api_base_url == "https://env.api.com"


class TestLiquidMarketData:
    @pytest.mark.parametrize(
        "from_time, to_time, should_raise",
        [
            (datetime(2023, 1, 1), datetime(2023, 1, 2), False),
            (datetime(2023, 1, 2), datetime(2023, 1, 1), True),
            (datetime(2023, 1, 1), datetime(2023, 1, 1), True),
        ],
    )
    def test_get_market_data_validation(
        self, liquid_client, from_time, to_time, should_raise
    ):
        if should_raise:
            with pytest.raises(
                ValueError, match="'from_time' must be a date-time before 'to_time'"
            ):
                liquid_client.get_market_data("BTC$", "m", from_time, to_time)
        else:
            with patch.object(liquid_client, "_query") as mock_query:
                mock_query.return_value.json.return_value = {"events": []}
                liquid_client.get_market_data("BTC$", "m", from_time, to_time)
                assert mock_query.called

    def test_get_market_data_success(self, liquid_client):
        mock_event = {
            "symbol": "BTC$",
            "open": 50000.0,
            "high": 51000.0,
            "low": 49000.0,
            "close": 50500.0,
            "volume": 10.5,
            "time": "2023-01-01T00:00:00Z",
            "type": "Candle",
            "candleType": "m",
        }
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"events": [mock_event]}
            candles = liquid_client.get_market_data(
                "BTC$", "m", datetime(2023, 1, 1), datetime(2023, 1, 2)
            )
            assert len(candles) == 1
            assert candles[0].close == 50500.0

    def test_get_market_data_exception(self, liquid_client):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"malformed": "response"}
            with pytest.raises(LiquidApiException, match="market data not received"):
                liquid_client.get_market_data(
                    "BTC$", "m", datetime(2023, 1, 1), datetime(2023, 1, 2)
                )


class TestLiquidQueryLogic:
    def test_retry_on_auth_required(self, liquid_client):
        mock_response_fail = MagicMock()
        mock_response_fail.text = '{"description": "Authorization required"}'

        mock_response_success = MagicMock()
        mock_response_success.text = '{"status": "ok"}'
        mock_response_success.ok = True

        with patch.object(
            liquid_client, "_get_session_token", return_value="new-token"
        ):
            with patch(
                append_target_module("_request"),
                side_effect=[mock_response_fail, mock_response_success],
            ):
                res = liquid_client._query(HTTPMethod.GET, "/test")

                assert liquid_client._session_token == "new-token"
                assert res == mock_response_success

    def test_max_retries_exceeded(self, liquid_client):
        with pytest.raises(LiquidApiAuthException, match="too many retries"):
            liquid_client._query(HTTPMethod.GET, "/test", num_retries=3)

    def test_query_request_failed_log(self, liquid_client, mock_requests):
        mock_requests.return_value.ok = False
        mock_requests.return_value.status_code = 500
        mock_requests.return_value.text = json.dumps({"description": "Internal Error"})

        res = liquid_client._query(HTTPMethod.GET, "/fail")
        assert res.ok is False
        assert res.status_code == 500


class TestLiquidInstrumentsAndPositions:
    def test_get_instruments_success(self, liquid_client):
        mock_instrument = {
            "symbol": "BTC$",
            "version": 1,
            "description": "Bitcoin",
            "type": "PRODUCT",
            "priceIncrement": 0.01,
            "pipSize": 0.01,
            "lotSize": 1.0,
            "multiplier": 1.0,
            "tradingHours": [],
        }
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {
                "instruments": [mock_instrument]
            }
            instruments = liquid_client.get_instruments()
            assert len(instruments) == 1
            assert instruments[0].symbol == "BTC$"

    def test_get_instruments_exception(self, liquid_client):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"error": "none"}
            with pytest.raises(LiquidApiException, match="instruments not received"):
                liquid_client.get_instruments()

    def test_get_open_positions_success(self, liquid_client):
        mock_position = {
            "symbol": "BTC$",
            "quantity": 1.0,
            "side": "BUY",
            "averagePrice": 50000.0,
            "positionCode": "pos123",
            "account": "default:888",
            "version": 1,
            "quantityNotional": 50000.0,
            "openTime": "2023-01-01T00:00:00Z",
            "openPrice": 50000.0,
            "lastUpdateTime": "2023-01-01T00:00:00Z",
            "marginRate": 0.0,
        }
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"positions": [mock_position]}
            positions = liquid_client.get_open_positions()
            assert len(positions) == 1
            assert positions[0].symbol == "BTC$"

    def test_get_open_positions_exception(self, liquid_client):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"wrong_key": []}
            with pytest.raises(LiquidApiException, match="positions not received"):
                liquid_client.get_open_positions()


class TestLiquidOrders:
    @pytest.mark.parametrize(
        "side, effect, order_type",
        [
            ("BUY", "OPEN", "LIMIT"),
            ("SELL", "CLOSE", "MARKET"),
        ],
    )
    def test_place_order_success(self, liquid_client, side, effect, order_type):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {
                "orderId": "12345",
                "updateOrderId": "67890",
            }

            order_id, update_id = liquid_client.place_order(
                symbol="BTC$",
                order_type=order_type,
                side=side,
                effect=effect,
                quantity=1.0,
            )

            assert order_id == "12345"
            assert update_id == "67890"

    def test_place_order_exception(self, liquid_client):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"status": "rejected"}
            with pytest.raises(LiquidApiException, match="not successful"):
                liquid_client.place_order("BTC$", "LIMIT", "BUY", "OPEN", 1.0)

    @pytest.mark.parametrize(
        "mock_response, symbol_arg, expected_match",
        [
            ({"not_orders": []}, "BTC$", "'BTC\\$' order history not received"),
            (["not", "a", "dict"], "ETH$", "'ETH\\$' order history not received"),
            (None, None, "'None' order history not received"),
            ({}, "AAPL", "'AAPL' order history not received"),
        ],
    )
    def test_get_order_history_error_handling(
        self, liquid_client, mock_response, symbol_arg, expected_match
    ):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = mock_response
            
            with pytest.raises(LiquidApiException, match=expected_match) as exc_info:
                liquid_client.get_order_history(symbol=symbol_arg)
            
            assert exc_info.value.args[1] == mock_response

    def test_get_order_history_params(self, liquid_client):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"orders": []}

            liquid_client.get_order_history(symbol="ETHUSD", order_id="PID-1")

            _, kwargs = mock_query.call_args
            assert kwargs["params"]["for-instrument"] == "ETHUSD"
            assert kwargs["params"]["with-order-id"] == "PID-1"


class TestLiquidQuotes:
    @pytest.mark.parametrize(
        "mock_response, expected_error",
        [
            ({"not_events": []}, "'BTC\\$' quotes not received"),
            ({"events": []}, "All of 'BTC\\$' quotes not received"),
            ("not a dict", "'BTC\\$' quotes not received"),
        ],
    )
    def test_get_quotes_failures(self, liquid_client, mock_response, expected_error):
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = mock_response
            with pytest.raises(LiquidApiException, match=expected_error):
                liquid_client.get_quotes(["BTC$"])

    def test_get_quotes_success(self, liquid_client):
        symbols = ["BTC$", "ETH$"]
        mock_events = [
            {
                "type": "Quote",
                "symbol": "BTC$",
                "bid": 50000.0,
                "ask": 50010.0,
                "time": "2023-01-01T12:00:00Z",
            },
            {
                "type": "Quote",
                "symbol": "ETH$",
                "bid": 3000.0,
                "ask": 3001.0,
                "time": "2023-01-01T12:00:00Z",
            }
        ]
        with patch.object(liquid_client, "_query") as mock_query:
            mock_query.return_value.json.return_value = {"events": mock_events}

            quotes = liquid_client.get_quotes(symbols)

            assert len(quotes) == 2
            assert quotes[0].symbol == "BTC$"
            assert quotes[1].symbol == "ETH$"
            mock_query.assert_called_once()
