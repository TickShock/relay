import logging as _logging
from typing import (
    cast as _cast,
    Optional as _Optional,
    Any as _Any,
    Dict as _Dict,
    Final as _Final,
    List as _List,
    Tuple as _Tuple,
)
from random import (
    choices as _choices,
)
from string import (
    digits as _digits,
    ascii_letters as _ascii_letters,
)
from urllib.parse import (
    quote as _quote,
)
from datetime import (
    datetime as _datetime,
)
from http import HTTPMethod as _HTTPMethod
from requests import (
    request as _request,
    Response as _Response,
)
from tickshock.ground import (
    to_dict as _to_dict,
    get_env as _get_env,
)
from tickshock.ground.types import (
    Candle as _Candle,
    CandleIntervalLiteral as _CandleIntervalLiteral,
)
from .exceptions import (
    LiquidApiException as _LiquidApiException,
    LiquidApiAuthException as _LiquidApiAuthException,
)
from .types._position import (
    PositionsDto as _PositionsDto,
)
from .types._candle import (
    CandleDto as _CandleDto,
)
from .types._quote import (
    QuoteDto as _QuoteDto,
    Quote as _Quote,
)
from .types import (
    InstrumentsDtoCollection as _InstrumentsDtoCollection,
    Instrument as _Instrument,
    SymbolLiteral as _SymbolLiteral,
    Position as _Position,
    TradeSideLiteral as _TradeSideLiteral,
    PositionEffectLiteral as _PositionEffectLiteral,
    OrderTypeLiteral as _OrderTypeLiteral,
    HistoricalOrderDto as _HistoricalOrderDto,
)

_logger = _logging.getLogger(__name__)


class Liquid:
    def __init__(
        self,
        username: str,
        password: str,
        api_base_url: str,
        account_id: str,
    ) -> None:
        _logger.info("Initializing Liquid relay for account_id: %s", account_id)
        self._username: _Final[str] = username
        self._password: _Final[str] = password
        self._api_base_url: _Final[str] = api_base_url
        self._account_code: _Final[str] = _quote(f"default:{account_id}")
        self._session_token: str = self._get_session_token(
            self._username,
            self._password,
        )

    @staticmethod
    def const_with_envvars() -> "Liquid":
        return Liquid(
            _get_env("LIQUID_UN"),
            _get_env("LIQUID_PW"),
            _get_env("LIQUID_API_BASE_URL"),
            _get_env("LIQUID_ACCOUNT_ID"),
        )

    def _get_session_token(self, username: str, password: str) -> str:
        _logger.debug("Attempting to acquire session token for user: %s", username)
        tkey = "sessionToken"
        result = self._query(
            _HTTPMethod.POST,
            "/login",
            {
                "username": username,
                "password": password,
                "domain": "default",
            },
        ).json()
        if not isinstance(result, dict) or not isinstance(result.get(tkey), str):
            _logger.error("Failed to receive session token. Result: %s", result)
            raise _LiquidApiAuthException("session token not received", result)
        _logger.info("Successfully acquired session token")
        return _cast(str, result.get(tkey))

    def _query(
        self,
        method: _HTTPMethod,
        api_url_path: str,
        data: _Optional[_Dict[str, _Any]] = None,
        num_retries: _Optional[int] = None,
        params: _Optional[_Dict[str, _Any]] = None,
    ) -> _Response:
        if (num_retries or 0) > 2:
            _logger.error("Too many retries for path: %s", api_url_path)
            raise _LiquidApiAuthException("too many retries")
        base_url = self._api_base_url
        url = (
            f"{base_url}/dxsca-web{'/' if api_url_path[0] != '/' else ''}{api_url_path}"
        )
        _logger.debug("Executing %s request to %s", method, url)
        response = _request(
            method=method,
            headers={
                "Content-Type": "application/json",
                **(
                    {"Authorization": f"DXAPI {self._session_token}"}
                    if getattr(self, "_session_token", None)
                    else {}
                ),
            },
            json=data,
            url=url,
            params=params,
            timeout=10,
        )
        if _to_dict(response.text).get("description") == "Authorization required":
            _logger.warning(
                "Authorization required for %s. Attempting token refresh.", api_url_path
            )
            self._session_token = self._get_session_token(
                self._username, self._password
            )
            return self._query(method, api_url_path, data, (num_retries or 0) + 1)

        if not response.ok:
            _logger.error(
                "Request to %s failed with status %d: %s",
                api_url_path,
                response.status_code,
                response.text,
            )

        return response

    def get_instruments(self) -> _List[_Instrument]:
        _logger.info("Fetching instruments")
        result = self._query(
            _HTTPMethod.GET,
            "instruments/query",
        ).json()
        if not isinstance(result, dict) or "instruments" not in result:
            _logger.error("Invalid instruments response: %s", result)
            raise _LiquidApiException("instruments not received", result)
        dtos = _InstrumentsDtoCollection(**result)
        _logger.debug("Successfully parsed %d instruments", len(dtos.instruments))
        return [dto.to_bo() for dto in dtos.instruments]

    def get_quotes(self, symbols: _List[_SymbolLiteral]) -> _List[_Quote]:
        response = self._query(
            _HTTPMethod.POST,
            "marketdata",
            {
                "symbols": symbols,
                "eventTypes": [{"type": "Quote"}],
            },
        ).json()
        if not isinstance(response, dict) or "events" not in response:
            _logger.error(
                "Failed to receive quotes for %s: %s", ",".join(symbols), response
            )
            raise _LiquidApiException(
                f"'{','.join(symbols)}' quotes not received", response
            )
        if not isinstance(response["events"], list) or len(response["events"]) != len(
            symbols
        ):
            _logger.error(
                "Failed to receive all quotes for %s: %s", ",".join(symbols), response
            )
            raise _LiquidApiException(
                f"All of '{','.join(symbols)}' quotes not received", response
            )
        return [_QuoteDto(**event).to_bo() for event in response["events"]]

    def get_market_data(
        self,
        symbol: _SymbolLiteral,
        duration: _CandleIntervalLiteral,
        from_time: _datetime,
        to_time: _datetime,
    ) -> _List[_Candle[_SymbolLiteral]]:
        if from_time >= to_time:
            _logger.error(
                "Invalid time range: from_time (%s) >= to_time (%s)", from_time, to_time
            )
            raise ValueError("'from_time' must be a date-time before 'to_time'")
        _logger.info(
            "Fetching market data for %s (interval: %s) from %s to %s",
            symbol,
            duration,
            from_time,
            to_time,
        )
        response = self._query(
            _HTTPMethod.POST,
            "marketdata",
            {
                "symbols": [symbol],
                "eventTypes": [
                    {
                        "type": "Candle",
                        "candleType": duration,
                        "fromTime": from_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-7]
                        + "Z",
                        "toTime": to_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-7] + "Z",
                    },
                ],
            },
        ).json()

        if not isinstance(response, dict) or "events" not in response:
            _logger.error("Failed to receive market data for %s: %s", symbol, response)
            raise _LiquidApiException(
                f"'{symbol}' at '{from_time}' market data not received", response
            )
        dtos = [_CandleDto(**candle_dict) for candle_dict in response["events"]]
        _logger.debug("Retrieved %d candles for %s", len(dtos), symbol)
        return [dto.to_bo() for dto in dtos]

    def get_open_positions(self) -> _List[_Position]:
        _logger.info("Fetching open positions")
        response = self._query(
            _HTTPMethod.GET,
            f"accounts/{self._account_code}/positions",
        ).json()
        if not isinstance(response, dict) or "positions" not in response:
            _logger.error("Failed to receive positions: %s", response)
            raise _LiquidApiException("positions not received", response)
        dtos = _PositionsDto(**response).positions
        _logger.debug("Successfully parsed %d open positions", len(dtos))
        return [dto.to_bo() for dto in dtos]

    def place_order(
        self,
        symbol: _SymbolLiteral,
        order_type: _OrderTypeLiteral,
        side: _TradeSideLiteral,
        effect: _PositionEffectLiteral,
        quantity: float,
        position_code: _Optional[str] = None,
        limit_price: _Optional[float] = None,
        stop_price: _Optional[float] = None,
    ) -> _Tuple[str, str]:
        order_code = "".join(_choices(_ascii_letters + _digits, k=7))
        _logger.info(
            "Placing %s %s order for %s (qty: %f, effect: %s, code: %s)",
            side,
            order_type,
            symbol,
            quantity,
            effect,
            order_code,
        )
        response = self._query(
            _HTTPMethod.POST,
            f"accounts/{self._account_code}/orders",
            {
                "orderCode": order_code,
                "type": order_type,
                "instrument": symbol,
                "quantity": quantity,
                "side": side,
                "positionEffect": effect,
                "tif": "GTC",
                **(
                    {"positionCode": position_code} if position_code is not None else {}
                ),
                **({"limitPrice": limit_price} if limit_price is not None else {}),
                **({"stopPrice": stop_price} if stop_price is not None else {}),
            },
        ).json()
        if not isinstance(response, dict) or not "orderId" in response:
            _logger.error("Order placement failed for %s: %s", order_code, response)
            raise _LiquidApiException(
                f"'{symbol}' '{order_type}' '{side}' order to '{effect}' amount '{quantity}' not successful",
                response,
            )
        _logger.info(
            "Order successfully placed. orderId: %s, updateOrderId: %s",
            response.get("orderId"),
            response.get("updateOrderId"),
        )
        return (
            _cast(str, response["orderId"]),
            _cast(str, response["updateOrderId"]),
        )

    def get_order_history(
        self,
        symbol: _Optional[_SymbolLiteral] = None,
        order_id: _Optional[str] = None,
    ) -> _List[_HistoricalOrderDto]:
        _logger.info(
            "Fetching order history (symbol: %s, order_id: %s)", symbol, order_id
        )
        response = self._query(
            _HTTPMethod.GET,
            f"accounts/{self._account_code}/orders/history",
            params={
                **({"for-instrument": symbol} if symbol is not None else {}),
                **({"with-order-id": order_id} if order_id is not None else {}),
            },
        ).json()
        if not isinstance(response, dict) or "orders" not in response:
            _logger.error("Failed to receive order history: %s", response)
            raise _LiquidApiException(
                f"'{symbol or order_id}' order history not received", response
            )
        dtos = [_HistoricalOrderDto(**order) for order in response["orders"]]
        _logger.debug("Successfully parsed %d historical orders", len(dtos))
        return dtos
