"""
股票資料模組 - 雙模式備援架構
===============================

優先使用 yfinance，失敗時自動切換到爬蟲備援

架構：
┌─────────────────────────────────────┐
│           get_stock()               │
│    ┌──────────┴──────────┐          │
│    ▼                     ▼          │
│ [yfinance]  ──失敗──>  [爬蟲備援]    │
└─────────────────────────────────────┘

Author: Yakitori197
GitHub: https://github.com/Yakitori197
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Literal
from datetime import datetime
from enum import Enum
import logging
import time

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 嘗試導入 yfinance
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
    logger.info("✅ yfinance 可用")
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("⚠️ yfinance 未安裝，將只使用爬蟲模式")


# ============================================
# 資料結構
# ============================================
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
class YFinanceProvider:
    """yfinance 資料提供者"""
    
    def __init__(self):
        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance is not installed")
    
    def get_stock(self, code: str, market: Market = Market.UNKNOWN) -> Optional[StockInfo]:
        """
        使用 yfinance 取得股票資料
        
        Args:
            code: 股票代碼
            market: 市場類型
        
        Returns:
            StockInfo 或 None
        """
        try:
            # 判斷完整代碼
            symbol = self._get_symbol(code, market)
            
            logger.info(f"[yfinance] 查詢 {symbol}...")
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # 檢查是否有有效資料
            price = info.get('regularMarketPrice') or info.get('currentPrice')
            if not price:
                logger.warning(f"[yfinance] {symbol} 無價格資料")
                return None
            
            # 計算漲跌
            prev_close = info.get('previousClose', 0) or info.get('regularMarketPreviousClose', 0)
            change = price - prev_close if prev_close else 0
            change_percent = (change / prev_close * 100) if prev_close else 0
            
            # 判斷市場
            actual_market = "tw" if symbol.endswith(".TW") or symbol.endswith(".TWO") else "us"
            
            return StockInfo(
                code=code.upper(),
                name=info.get('longName') or info.get('shortName') or code,
                price=float(price),
                change=round(change, 2),
                change_percent=round(change_percent, 2),
                volume=info.get('volume', 0) or 0,
                open_price=info.get('open') or info.get('regularMarketOpen'),
                high_price=info.get('dayHigh') or info.get('regularMarketDayHigh'),
                low_price=info.get('dayLow') or info.get('regularMarketDayLow'),
                prev_close=prev_close,
                pe_ratio=info.get('trailingPE') or info.get('forwardPE'),
                market_cap=info.get('marketCap'),
                market=actual_market,
                source="yfinance",
                update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
        except Exception as e:
            logger.error(f"[yfinance] 錯誤: {e}")
            return None
    
    def _get_symbol(self, code: str, market: Market) -> str:
        """轉換為 yfinance 格式的代碼"""
        code = code.upper().strip()
        
        # 已經是完整格式
        if code.endswith(".TW") or code.endswith(".TWO"):
            return code
        
        # 判斷市場
        if market == Market.TW:
            return f"{code}.TW"
        elif market == Market.US:
            return code
        else:
            # 自動判斷：純數字是台股，純英文是美股
            if code.isdigit():
                return f"{code}.TW"
            else:
                return code
    
    def get_market_index(self) -> Optional[Dict]:
        """取得大盤指數"""
        try:
            ticker = yf.Ticker("^TWII")  # 台灣加權指數
            info = ticker.info
            
            price = info.get('regularMarketPrice', 0)
            prev_close = info.get('previousClose', 0)
            change = price - prev_close if prev_close else 0
            change_percent = (change / prev_close * 100) if prev_close else 0
            
            return {
                "name": "加權指數",
                "price": price,
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "source": "yfinance",
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"[yfinance] 大盤錯誤: {e}")
            return None


# ============================================
# 爬蟲資料提供者（備援）
# ============================================
class ScraperProvider:
    """爬蟲資料提供者（備援方案）"""
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    def get_stock(self, code: str, market: Market = Market.UNKNOWN) -> Optional[StockInfo]:
        """
        使用爬蟲取得股票資料
        
        Args:
            code: 股票代碼
            market: 市場類型
        
        Returns:
            StockInfo 或 None
        """
        code = code.upper().strip()
        
        # 判斷市場
        if market == Market.UNKNOWN:
            market = Market.TW if code.isdigit() else Market.US
        
        if market == Market.TW:
            return self._get_tw_stock(code)
        else:
            return self._get_us_stock(code)
    
    def _get_tw_stock(self, code: str) -> Optional[StockInfo]:
        """爬取台股資料"""
        url = f"https://tw.stock.yahoo.com/quote/{code}.TW"
        
        try:
            logger.info(f"[Scraper] 爬取台股 {code}...")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 解析股票名稱 - 從 title 或特定元素取得
            name = code
            
            # 方法1: 從 <title> 標籤取得
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.text.strip()
                # 格式通常是 "台積電 (2330.TW) ..." 或 "台積電(2330.TW)..."
                if "(" in title_text:
                    name = title_text.split("(")[0].strip()
            
            # 方法2: 如果方法1失敗，嘗試從 h1 取得
            if name == code or "Yahoo" in name:
                h1_tag = soup.select_one("h1")
                if h1_tag:
                    h1_text = h1_tag.text.strip()
                    if "(" in h1_text:
                        name = h1_text.split("(")[0].strip()
                    elif h1_text and "Yahoo" not in h1_text:
                        name = h1_text
            
            # 解析價格
            price = self._extract_price(soup)
            if not price:
                return None
            
            # 解析漲跌
            change, change_percent = self._extract_change(soup)
            
            # 解析成交量 - 改進版
            volume = self._extract_volume_tw(soup)
            
            return StockInfo(
                code=code,
                name=name,
                price=price,
                change=change,
                change_percent=change_percent,
                volume=volume,
                market="tw",
                source="scraper",
                update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
        except Exception as e:
            logger.error(f"[Scraper] 台股錯誤: {e}")
            return None
    
    def _extract_volume_tw(self, soup: BeautifulSoup) -> int:
        """提取台股成交量"""
        import re
        
        # 方法1: 找所有文字，搜尋「成交」相關
        text = soup.get_text()
        
        # 嘗試匹配 "成交量 53,450" 或 "成交 53,450" 的模式
        patterns = [
            r'成交[量張]?\s*[：:]\s*([\d,]+)',
            r'成交[量張]?\s*([\d,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    vol_str = match.group(1).replace(",", "")
                    return int(vol_str)
                except ValueError:
                    continue
        
        # 方法2: 尋找特定元素
        volume_labels = ["成交量", "成交張數", "成交"]
        for label in volume_labels:
            elements = soup.find_all(string=re.compile(label))
            for elem in elements:
                parent = elem.find_parent()
                if parent:
                    # 找同層或下一個元素的數字
                    next_elem = parent.find_next_sibling() or parent.find_next()
                    if next_elem:
                        try:
                            vol_text = next_elem.get_text().strip().replace(",", "")
                            # 只取數字部分
                            vol_num = re.search(r'[\d,]+', vol_text)
                            if vol_num:
                                return int(vol_num.group().replace(",", ""))
                        except (ValueError, AttributeError):
                            continue
        
        return 0
    
    def _get_us_stock(self, code: str) -> Optional[StockInfo]:
        """爬取美股資料"""
        url = f"https://finance.yahoo.com/quote/{code}"
        
        try:
            logger.info(f"[Scraper] 爬取美股 {code}...")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 解析名稱 - 從 title 取得
            name = code
            
            # 方法1: 從 <title> 標籤取得
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.text.strip()
                # 格式通常是 "Apple Inc. (AAPL) Stock Price..." 
                if "(" in title_text:
                    name = title_text.split("(")[0].strip()
            
            # 方法2: 從 h1 取得
            if name == code or "Yahoo" in name:
                h1_tag = soup.select_one("h1")
                if h1_tag:
                    h1_text = h1_tag.text.strip()
                    # h1 格式可能是 "Apple Inc. (AAPL)"
                    if "(" in h1_text:
                        name = h1_text.split("(")[0].strip()
                    elif h1_text and "Yahoo" not in h1_text:
                        name = h1_text
            
            # 解析價格 - 嘗試多種選擇器
            price = None
            price_selectors = [
                "[data-testid='qsp-price']",
                "fin-streamer[data-field='regularMarketPrice']",
                "span.Fw\\(b\\)",
            ]
            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem:
                    try:
                        price = float(elem.text.replace(",", ""))
                        break
                    except ValueError:
                        continue
            
            if not price:
                return None
            
            # 解析漲跌
            change = 0.0
            change_percent = 0.0
            
            change_elem = soup.select_one("[data-testid='qsp-price-change']")
            if change_elem:
                try:
                    change = float(change_elem.text.replace(",", "").replace("+", ""))
                except ValueError:
                    pass
            
            pct_elem = soup.select_one("[data-testid='qsp-price-change-percent']")
            if pct_elem:
                try:
                    pct_text = pct_elem.text.replace("%", "").replace("(", "").replace(")", "").replace("+", "")
                    change_percent = float(pct_text)
                except ValueError:
                    pass
            
            # 如果 change 是 0 但 change_percent 不是，反算
            if change == 0 and change_percent != 0:
                change = price * change_percent / 100
            
            # 解析成交量
            volume = self._extract_volume_us(soup)
            
            return StockInfo(
                code=code,
                name=name,
                price=price,
                change=change,
                change_percent=change_percent,
                volume=volume,
                market="us",
                source="scraper",
                update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
        except Exception as e:
            logger.error(f"[Scraper] 美股錯誤: {e}")
            return None
    
    def _extract_volume_us(self, soup: BeautifulSoup) -> int:
        """提取美股成交量"""
        import re
        
        # 方法1: 找 Volume 相關文字
        text = soup.get_text()
        
        # 匹配 "Volume 123,456,789" 或 "Vol 123M"
        patterns = [
            r'Volume[:\s]*([\d,]+)',
            r'Vol[:\s]*([\d,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    vol_str = match.group(1).replace(",", "")
                    return int(vol_str)
                except ValueError:
                    continue
        
        # 方法2: 找 data-field="regularMarketVolume" 的元素
        vol_elem = soup.select_one("fin-streamer[data-field='regularMarketVolume']")
        if vol_elem:
            try:
                vol_text = vol_elem.get_text().strip().replace(",", "")
                return int(vol_text)
            except ValueError:
                pass
        
        return 0
    
    def get_market_index(self) -> Optional[Dict]:
        """爬取大盤指數"""
        url = "https://tw.stock.yahoo.com/quote/%5ETWII"
        
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            price = self._extract_price(soup)
            change, change_percent = self._extract_change(soup)
            
            return {
                "name": "加權指數",
                "price": price or 0,
                "change": change,
                "change_percent": change_percent,
                "source": "scraper",
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"[Scraper] 大盤錯誤: {e}")
            return None
    
    # === 輔助方法 ===
    
    def _extract_text(self, soup: BeautifulSoup, selector: str) -> Optional[str]:
        """提取文字"""
        elem = soup.select_one(selector)
        return elem.text.strip() if elem else None
    
    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """提取價格"""
        # 嘗試多種選擇器
        selectors = [
            "span.Fz\\(32px\\)",
            "span[class*='Fz(32']",
            "fin-streamer[data-field='regularMarketPrice']",
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                try:
                    return float(elem.text.strip().replace(",", ""))
                except ValueError:
                    continue
        
        return None
    
    def _extract_change(self, soup: BeautifulSoup) -> tuple:
        """提取漲跌幅"""
        change = 0.0
        change_percent = 0.0
        
        # 尋找所有可能包含漲跌的元素
        spans = soup.find_all("span")
        
        for span in spans:
            text = span.text.strip()
            
            # 匹配 +50.00 或 -50.00
            if text and text[0] in ['+', '-'] and text[1:].replace('.', '').replace(',', '').isdigit():
                try:
                    val = float(text.replace(",", ""))
                    if abs(val) < 1000:  # 可能是漲跌點數
                        change = val
                except ValueError:
                    pass
            
            # 匹配百分比
            if "%" in text:
                try:
                    pct = text.replace("%", "").replace("+", "").replace("(", "").replace(")", "").replace(",", "")
                    if pct.replace("-", "").replace(".", "").isdigit():
                        change_percent = float(pct)
                except ValueError:
                    pass
        
        return change, change_percent
    
    def _extract_number(self, soup: BeautifulSoup, label: str) -> int:
        """提取標籤對應的數字"""
        import re
        
        elem = soup.find(string=re.compile(f"^{label}"))
        if elem:
            parent = elem.find_parent()
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    try:
                        return int(sibling.text.strip().replace(",", ""))
                    except ValueError:
                        pass
        return 0


# ============================================
# 主要介面：雙模式備援
# ============================================
class StockDataService:
    """
    股票資料服務 - 雙模式備援架構
    
    使用方式：
        service = StockDataService()
        stock = service.get_stock("2330")  # 自動判斷台股
        stock = service.get_stock("AAPL")  # 自動判斷美股
    """
    
    def __init__(self, prefer_yfinance: bool = True):
        """
        初始化服務
        
        Args:
            prefer_yfinance: 是否優先使用 yfinance（預設 True）
        """
        self.prefer_yfinance = prefer_yfinance and YFINANCE_AVAILABLE
        
        # 初始化提供者
        self.yfinance_provider = YFinanceProvider() if YFINANCE_AVAILABLE else None
        self.scraper_provider = ScraperProvider()
        
        # 統計
        self.stats = {
            "yfinance_success": 0,
            "yfinance_fail": 0,
            "scraper_success": 0,
            "scraper_fail": 0,
        }
        
        logger.info(f"StockDataService 初始化完成")
        logger.info(f"  - yfinance: {'✅ 可用' if YFINANCE_AVAILABLE else '❌ 不可用'}")
        logger.info(f"  - 優先模式: {'yfinance' if self.prefer_yfinance else 'scraper'}")
    
    def get_stock(self, code: str, market: Market = Market.UNKNOWN) -> Optional[StockInfo]:
        """
        取得股票資料（自動備援）
        
        Args:
            code: 股票代碼（如 2330, AAPL）
            market: 市場類型（可選，會自動判斷）
        
        Returns:
            StockInfo 或 None
        """
        code = code.strip().upper()
        
        # 自動判斷市場
        if market == Market.UNKNOWN:
            market = self._detect_market(code)
        
        # 優先使用 yfinance
        if self.prefer_yfinance and self.yfinance_provider:
            result = self.yfinance_provider.get_stock(code, market)
            if result:
                self.stats["yfinance_success"] += 1
                logger.info(f"[Service] ✅ yfinance 成功取得 {code}")
                return result
            else:
                self.stats["yfinance_fail"] += 1
                logger.warning(f"[Service] ⚠️ yfinance 失敗，切換到爬蟲備援")
        
        # 備援：使用爬蟲
        result = self.scraper_provider.get_stock(code, market)
        if result:
            self.stats["scraper_success"] += 1
            logger.info(f"[Service] ✅ 爬蟲成功取得 {code}")
            return result
        else:
            self.stats["scraper_fail"] += 1
            logger.error(f"[Service] ❌ 所有方法都失敗 {code}")
            return None
    
    def get_market_index(self) -> Optional[Dict]:
        """取得大盤指數（自動備援）"""
        # 優先使用 yfinance
        if self.prefer_yfinance and self.yfinance_provider:
            result = self.yfinance_provider.get_market_index()
            if result:
                return result
        
        # 備援：使用爬蟲
        return self.scraper_provider.get_market_index()
    
    def get_multiple_stocks(self, codes: List[str]) -> List[StockInfo]:
        """
        批次取得多支股票
        
        Args:
            codes: 股票代碼列表
        
        Returns:
            StockInfo 列表
        """
        results = []
        for code in codes:
            stock = self.get_stock(code)
            if stock:
                results.append(stock)
            time.sleep(0.5)  # 避免請求過快
        return results
    
    def get_stats(self) -> Dict:
        """取得統計資訊"""
        return {
            **self.stats,
            "yfinance_available": YFINANCE_AVAILABLE,
            "prefer_yfinance": self.prefer_yfinance,
        }
    
    def _detect_market(self, code: str) -> Market:
        """自動判斷市場"""
        code = code.upper().strip()
        
        # 已包含後綴
        if code.endswith(".TW") or code.endswith(".TWO"):
            return Market.TW
        
        # 純數字 = 台股
        if code.isdigit():
            return Market.TW
        
        # 純英文 = 美股
        if code.isalpha():
            return Market.US
        
        return Market.UNKNOWN


# ============================================
# 便捷函式
# ============================================

# 全域服務實例
_service: Optional[StockDataService] = None

def _get_service() -> StockDataService:
    """取得全域服務實例"""
    global _service
    if _service is None:
        _service = StockDataService()
    return _service


def get_stock(code: str) -> Optional[StockInfo]:
    """
    快速取得股票資料
    
    Args:
        code: 股票代碼
    
    Returns:
        StockInfo 或 None
    
    Example:
        >>> stock = get_stock("2330")
        >>> print(stock.price)
    """
    return _get_service().get_stock(code)


def get_tw_stock(code: str) -> Optional[StockInfo]:
    """快速取得台股資料"""
    return _get_service().get_stock(code, Market.TW)


def get_us_stock(code: str) -> Optional[StockInfo]:
    """快速取得美股資料"""
    return _get_service().get_stock(code, Market.US)


def get_market() -> Optional[Dict]:
    """快速取得大盤指數"""
    return _get_service().get_market_index()


def get_stocks(codes: List[str]) -> List[StockInfo]:
    """批次取得多支股票"""
    return _get_service().get_multiple_stocks(codes)


# ============================================
# 測試
# ============================================
if __name__ == "__main__":
    print("=" * 60)
    print("股票資料服務 - 雙模式備援架構測試")
    print("=" * 60)
    
    service = StockDataService()
    
    # 測試台股
    print("\n🇹🇼 測試台股 - 台積電 (2330)")
    print("-" * 40)
    stock = service.get_stock("2330")
    if stock:
        print(stock.format_message())
    else:
        print("❌ 無法取得資料")
    
    # 測試美股
    print("\n🇺🇸 測試美股 - Apple (AAPL)")
    print("-" * 40)
    stock = service.get_stock("AAPL")
    if stock:
        print(stock.format_message())
    else:
        print("❌ 無法取得資料")
    
    # 測試大盤
    print("\n📊 測試大盤指數")
    print("-" * 40)
    market = service.get_market_index()
    if market:
        print(f"名稱: {market['name']}")
        print(f"指數: {market['price']:,.2f}")
        print(f"漲跌: {market['change']:+.2f} ({market['change_percent']:+.2f}%)")
        print(f"來源: {market['source']}")
    else:
        print("❌ 無法取得資料")
    
    # 顯示統計
    print("\n📈 統計資訊")
    print("-" * 40)
    stats = service.get_stats()
    print(f"yfinance 可用: {stats['yfinance_available']}")
    print(f"yfinance 成功: {stats['yfinance_success']}")
    print(f"yfinance 失敗: {stats['yfinance_fail']}")
    print(f"爬蟲成功: {stats['scraper_success']}")
    print(f"爬蟲失敗: {stats['scraper_fail']}")
