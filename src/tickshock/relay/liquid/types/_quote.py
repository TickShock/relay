from typing import (
    Literal as _Literal,
    Final as _Final,
)
from datetime import (
    datetime as _datetime,
)
from pydantic import (
    BaseModel as _BaseModel,
)
from ._instrument import (
    SymbolLiteral as _SymbolLiteral,
)


class Quote:
    def __init__(
        self,
        symbol: _SymbolLiteral,
        bid: float,
        ask: float,
        time: _datetime,
    ) -> None:
        self.symbol: _Final = symbol
        self.bid: _Final = bid
        self.ask: _Final = ask
        self.time: _Final = time


class QuoteDto(_BaseModel):
    type: _Literal["Quote"]
    symbol: _SymbolLiteral
    bid: float
    ask: float
    time: _datetime

    def to_bo(self) -> Quote:
        return Quote(
            self.symbol,
            self.bid,
            self.ask,
            self.time,
        )
