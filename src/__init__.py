"""Stock LINE Bot - 雙模式備援架構"""
from .stock_service import (
    StockDataService,
    StockInfo,
    Market,
    get_stock,
    get_tw_stock,
    get_us_stock,
    get_market,
)

__version__ = "2.0.0"
