from typing import (
    Literal as _Literal,
)
from datetime import (
    datetime as _datetime,
)
from pydantic import (
    BaseModel as _BaseModel,
)
from tickshock.ground.types import (
    Candle as _Candle,
)
from tickshock.ground.exceptions import (
    TickShockException as _TickShockException,
)
from ._instrument import (
    SymbolLiteral as _SymbolLiteral,
)

CandleIntervalLiteral = _Literal["m", "5m", "15m", "30m", "h", "2h", "4h", "d", "w", "mo"]


class CandleDto(_BaseModel):
    symbol: _SymbolLiteral
    type: _Literal["Candle"]
    candleType: CandleIntervalLiteral
    open: float
    close: float
    high: float
    low: float
    volume: float
    time: _datetime

    def to_bo(self) -> _Candle[_SymbolLiteral]:
        if self.candleType == "mo":
            raise _TickShockException(f"'{self.symbol}' must have up to a 1-week interval")
        return _Candle(
            self.symbol,
            self.candleType,
            self.open,
            self.close,
            self.high,
            self.low,
            self.volume,
            self.time,
        )
