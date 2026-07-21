r"""
股票資料服務

行情抓取已改由 yolab-quote 提供，本檔只保留 LINE bot 需要的展示層
（StockInfo.format_message 等）與既有的公開介面，呼叫端不需修改。

改用套件後一併修正的問題：
  * `_detect_market` 原本用 `code.isdigit()` 判斷台股，對槓桿／反向 ETF
    （00631L、00632R）會失敗而誤判為美股。套件用 `^\d{4,6}[A-Z]{0,2}$`。
  * `get_multiple_stocks` 原本逐檔查詢並 `time.sleep(0.5)`，改為執行緒池併發。
  * 查詢失敗原本一律回 None，無法區分「查無此股」與「網路異常」；
    套件會拋出帶原因的例外，這裡轉回 None 以維持既有介面，但會寫進 log。
  * 新增中文名稱顯示（本版原本沒有對照表）。
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

import yolab_quote as yq
from yolab_quote import QuoteClient

logger = logging.getLogger(__name__)

#: 台股大盤指數
TW_INDEX_SYMBOL = "^TWII"

#: 報價快取秒數；LINE 指令常在短時間內重複查詢同一檔。
CACHE_TTL_SECONDS = 30

#: 批次查詢的併發數。
BATCH_WORKERS = 8

TW_TIMEZONE = timezone(timedelta(hours=8))

class Market(Enum):
    """市場類型"""
    TW = "tw"      # 台股
    US = "us"      # 美股
    UNKNOWN = "unknown"


@dataclass
class StockInfo:
    """股票資訊"""
    code: str                           # 股票代碼
    name: str                           # 股票名稱
    price: float                        # 現價
    change: float                       # 漲跌
    change_percent: float               # 漲跌幅 (%)
    volume: int = 0                     # 成交量
    open_price: Optional[float] = None  # 開盤價
    high_price: Optional[float] = None  # 最高價
    low_price: Optional[float] = None   # 最低價
    prev_close: Optional[float] = None  # 昨收
    pe_ratio: Optional[float] = None    # 本益比
    market_cap: Optional[int] = None    # 市值
    market: str = "unknown"             # 市場 (tw/us)
    source: str = "unknown"             # 資料來源 (yfinance/scraper)
    update_time: str = ""               # 更新時間
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def format_message(self) -> str:
        """格式化為 LINE 訊息"""
        from datetime import datetime
        
        # 漲跌符號（根據漲跌幅判斷，因為 change 可能解析失敗）
        if self.change_percent > 0:
            trend = "🔺"
        elif self.change_percent < 0:
            trend = "🔻"
        else:
            trend = "➖"
        
        # 貨幣符號
        currency = "NT$" if self.market == "tw" else "$"
        
        # 如果 change 是 0 但 change_percent 不是 0，從價格反算
        change = self.change
        if change == 0 and self.change_percent != 0:
            change = self.price * self.change_percent / 100
        
        # 判斷是否已收盤
        now = datetime.now()
        is_closed = self._is_market_closed(now)
        
        msg = f"📊 {self.name} ({self.code})\n"
        msg += f"━━━━━━━━━━━━\n"
        
        # 開盤價
        if self.open_price:
            msg += f"開盤：{currency}{self.open_price:,.2f}\n"
        
        # 現價或收盤價
        if is_closed:
            msg += f"收盤：{currency}{self.price:,.2f}\n"
        else:
            msg += f"現價：{currency}{self.price:,.2f}\n"
        
        # 漲跌
        msg += f"漲跌：{trend} {change:+.2f} ({self.change_percent:+.2f}%)\n"
        
        # 成交量
        if self.volume and self.volume > 0:
            if self.market == "tw":
                msg += f"成交量：{self.volume:,} 張\n"
            else:
                msg += f"成交量：{self.volume:,}\n"
        
        msg += f"━━━━━━━━━━━━\n"
        msg += f"⏰ {self.update_time}"
        
        return msg
    
    def _is_market_closed(self, now: 'datetime') -> bool:
        """判斷市場是否已收盤"""
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()  # 0=週一, 6=週日
        
        # 週末一定是收盤
        if weekday >= 5:
            return True
        
        if self.market == "tw":
            # 台股：09:00 - 13:30
            current_time = hour * 60 + minute  # 轉成分鐘
            market_open = 9 * 60      # 09:00
            market_close = 13 * 60 + 30  # 13:30
            
            if current_time < market_open or current_time >= market_close:
                return True
            return False
        
        elif self.market == "us":
            # 美股（台灣時間）：
            # 夏令：21:30 - 04:00
            # 冬令：22:30 - 05:00
            # 簡化處理：05:00 - 21:30 之間算收盤
            current_time = hour * 60 + minute
            
            # 05:00 到 21:30 之間是收盤
            if 5 * 60 <= current_time < 21 * 60 + 30:
                return True
            return False
        
        return False


# ============================================
# yfinance 資料提供者
# ============================================

# --------------------------------------------------------------------------- #
# yolab-quote -> StockInfo
# --------------------------------------------------------------------------- #
def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _quote_to_stock_info(code: str, quote) -> StockInfo:
    """把套件的 Quote 轉成既有的 StockInfo。

    `code` 用呼叫端原本傳入的代碼而不是正規化後的 symbol，
    這樣訊息裡顯示的還是使用者輸入的「2330」而非「2330.TW」。
    """
    market = "tw" if quote.market == yq.TW_STOCK else "us"
    # 套件內建中文名對照；查不到才退回資料源給的名稱。
    name = yq.get_name(quote.symbol) or quote.name or code

    return StockInfo(
        code=code,
        name=name,
        price=quote.price or 0.0,
        change=quote.change or 0.0,
        change_percent=quote.change_percent or 0.0,
        volume=_to_int(quote.volume),
        open_price=quote.open,
        high_price=quote.high,
        low_price=quote.low,
        prev_close=quote.previous_close,
        pe_ratio=quote.extra.get("pe_ratio"),
        market_cap=_optional_int(quote.extra.get("market_cap")),
        market=market,
        source=quote.source,
        update_time=quote.updated_at.astimezone(TW_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
    )


class StockDataService:
    """股票資料服務。

    使用方式不變：
        service = StockDataService()
        stock = service.get_stock("2330")   # 自動判斷台股
        stock = service.get_stock("AAPL")   # 自動判斷美股
    """

    def __init__(self, prefer_yfinance: bool = True):
        """
        Args:
            prefer_yfinance: True 時以 yfinance 為主、Yahoo 為備援；
                False 則反過來。兩者皆失敗才算失敗。
        """
        order = ["yfinance", "yahoo"] if prefer_yfinance else ["yahoo", "yfinance"]
        self.prefer_yfinance = prefer_yfinance
        self._client = QuoteClient(
            priority={yq.TW_STOCK: order, yq.US_STOCK: order},
            ttl=CACHE_TTL_SECONDS,
            max_workers=BATCH_WORKERS,
        )
        self.stats = {
            "success": 0,
            "fail": 0,
        }
        logger.info("StockDataService 初始化完成（yolab-quote %s）", yq.__version__)

    # -- 公開介面（維持原簽名） ------------------------------------------- #
    def get_stock(self, code: str, market: Market = Market.UNKNOWN) -> Optional[StockInfo]:
        """取得單檔股票資料，失敗回 None。"""
        code = code.strip().upper()
        try:
            quote = self._client.get_quote(code, self._market_arg(market))
        except yq.QuoteError as exc:
            self.stats["fail"] += 1
            # 例外帶著每個資料源各自的失敗原因，比原本的靜默 None 好查。
            logger.warning("[Service] 取得 %s 失敗: %s", code, exc)
            return None
        self.stats["success"] += 1
        logger.info("[Service] %s 由 %s 取得", code, quote.source)
        return _quote_to_stock_info(code, quote)

    def get_multiple_stocks(self, codes: List[str]) -> List[StockInfo]:
        """批次取得多檔股票（併發）。查不到的會被略過。"""
        if not codes:
            return []
        cleaned = [c.strip().upper() for c in codes if c and c.strip()]
        quotes = self._client.get_quotes(cleaned)
        self.stats["success"] += len(quotes)
        self.stats["fail"] += len(cleaned) - len(quotes)
        return [_quote_to_stock_info(code, quotes[code]) for code in cleaned if code in quotes]

    def get_market_index(self) -> Optional[Dict]:
        """取得台股大盤指數。"""
        try:
            # 明確指定市場：指數代號以 ^ 開頭，不適用一般代碼推導規則。
            quote = self._client.get_quote(TW_INDEX_SYMBOL, yq.TW_STOCK)
        except yq.QuoteError as exc:
            logger.warning("[Service] 取得大盤失敗: %s", exc)
            return None
        return {
            "name": "加權指數",
            "price": quote.price or 0.0,
            "change": quote.change or 0.0,
            "change_percent": quote.change_percent or 0.0,
            "source": quote.source,
            "update_time": quote.updated_at.astimezone(TW_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def get_stats(self) -> Dict:
        """統計資訊。`yfinance_available` 供 /health 端點使用。"""
        health = self._client.health()
        yfinance_health = health.get("yfinance")
        return {
            **self.stats,
            "yfinance_available": bool(yfinance_health and yfinance_health.ok),
            "prefer_yfinance": self.prefer_yfinance,
            "providers": {name: h.status for name, h in health.items()},
        }

    # -- 內部 -------------------------------------------------------------- #
    @staticmethod
    def _market_arg(market: Market) -> Optional[str]:
        """把 Market enum 轉成套件的市場字串；UNKNOWN 交給套件自行推導。"""
        if market == Market.TW:
            return yq.TW_STOCK
        if market == Market.US:
            return yq.US_STOCK
        return None

    def _detect_market(self, code: str) -> Market:
        """判斷市場。

        改用套件的規則，因此 00631L / 00632R 這類帶字尾的台股 ETF
        不會再被誤判為美股。
        """
        try:
            detected = yq.detect_market(code)
        except yq.SymbolError:
            return Market.UNKNOWN
        if detected == yq.TW_STOCK:
            return Market.TW
        if detected == yq.US_STOCK:
            return Market.US
        return Market.UNKNOWN


# --------------------------------------------------------------------------- #
# 模組層級便捷函式（維持原簽名）
# --------------------------------------------------------------------------- #
_service: Optional[StockDataService] = None


def _get_service() -> StockDataService:
    global _service
    if _service is None:
        _service = StockDataService()
    return _service


def get_stock(code: str) -> Optional[StockInfo]:
    """取得股票資料（自動判斷市場）。"""
    return _get_service().get_stock(code)


def get_tw_stock(code: str) -> Optional[StockInfo]:
    """取得台股資料。"""
    return _get_service().get_stock(code, Market.TW)


def get_us_stock(code: str) -> Optional[StockInfo]:
    """取得美股資料。"""
    return _get_service().get_stock(code, Market.US)


def get_market() -> Optional[Dict]:
    """取得大盤指數。"""
    return _get_service().get_market_index()


def get_stocks(codes: List[str]) -> List[StockInfo]:
    """批次取得多檔股票。"""
    return _get_service().get_multiple_stocks(codes)
