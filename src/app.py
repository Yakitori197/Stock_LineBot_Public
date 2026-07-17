"""
股票 LINE Bot - 主程式（雙模式備援版）
=====================================

功能：
1. 查詢台股/美股即時報價
2. 到價提醒
3. 自選股清單
4. 大盤指數

資料來源：
- 優先：yfinance
- 備援：爬蟲（Yahoo 股市）

Author: Yakitori197
GitHub: https://github.com/Yakitori197
"""

import os
import sys
import re
from datetime import datetime
from typing import Optional
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent,
)
from linebot.v3.exceptions import InvalidSignatureError

# 載入模組
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.stock_service import StockDataService
from src import store
from config.settings import Settings

# ============================================
# 初始化
# ============================================
app = Flask(__name__)
settings = Settings()
configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

# 股票資料服務（雙模式備援）
stock_service = StockDataService(prefer_yfinance=True)

# 自選股 / 到價提醒改存 SQLite（見 src/store.py）。
# 原本用行程內字典，導致獨立的 scheduler container 讀不到、提醒永不觸發，
# 且 gunicorn 多 worker 間狀態不一致、重啟即失憶。
store.init_db()


# ============================================
# Webhook 路由
# ============================================
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return "OK"


@app.route("/health", methods=["GET"])
def health():
    stats = stock_service.get_stats()
    return {
        "status": "healthy",
        "service": "Stock LINE Bot",
        "yfinance_available": stats["yfinance_available"],
        "stats": stats,
    }


# ============================================
# 訊息處理
# ============================================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """處理用戶訊息"""
    text = event.message.text.strip()
    user_id = event.source.user_id
    
    # 判斷是否為群組訊息
    is_group = event.source.type in ["group", "room"]

    # 指令路由
    if text.lower() == "/help":
        reply = get_help_message()
    elif text.lower() == "/market" or text == "大盤":
        reply = get_market_info()
    elif text.lower() == "/list" or text == "自選":
        reply = get_watchlist(user_id)
    elif text.lower().startswith("/add "):
        code = text[5:].strip().upper()
        reply = add_to_watchlist(user_id, code)
    elif text.lower().startswith("/del "):
        code = text[5:].strip().upper()
        reply = remove_from_watchlist(user_id, code)
    elif text.lower().startswith("/alert "):
        reply = set_price_alert(user_id, text[7:].strip())
    elif text.lower() == "/alerts":
        reply = get_alerts(user_id)
    elif text.lower() == "/stats":
        reply = get_service_stats()
    else:
        # 嘗試解析為股票代碼
        reply = query_stock(text, is_group)
    
    # 如果有回覆內容才發送
    if reply:
        send_reply(event.reply_token, reply)


@handler.add(FollowEvent)
def handle_follow(event):
    """歡迎訊息"""
    welcome = """
🎉 歡迎使用 YoLab 股票機器人！

【快速查詢】
直接輸入股票代碼即可
• 台股：2330、0050
• 美股：AAPL、TSLA

【更多功能】
輸入 /help 查看完整說明

📡 資料來源：Yahoo Finance
🔄 雙模式備援架構
""".strip()
    send_reply(event.reply_token, welcome)


# ============================================
# 功能實作
# ============================================
def query_stock(text: str, is_group: bool = False) -> Optional[str]:
    """查詢股票
    
    Args:
        text: 輸入文字
        is_group: 是否為群組訊息
    
    Returns:
        回覆訊息，如果在群組中且格式不符則回傳 None（不回覆）
    """
    code = text.strip().upper()
    
    # 驗證格式：只接受純數字（台股）或純英文（美股）
    is_valid_format = re.match(r'^[A-Z]{1,5}$', code) or re.match(r'^\d{4,6}$', code)
    
    # 如果格式不符
    if not is_valid_format:
        # 群組中不回應無效格式
        if is_group:
            return None
        # 私訊才顯示錯誤
        return f"❌ 無法識別：{text}\n\n請輸入正確格式：\n• 台股：2330\n• 美股：AAPL"
    
    # 查詢股票
    stock = stock_service.get_stock(code)
    
    if not stock:
        # 群組中找不到股票也不回應
        if is_group:
            return None
        return f"❌ 找不到股票：{code}\n請確認代碼是否正確"
    
    return stock.format_message()


def get_market_info() -> str:
    """取得大盤資訊"""
    market = stock_service.get_market_index()
    
    if not market:
        return "❌ 無法取得大盤資訊"
    
    if market.get("change", 0) > 0:
        trend = "🔺"
    elif market.get("change", 0) < 0:
        trend = "🔻"
    else:
        trend = "➖"
    
    return f"""
📈 台股大盤
━━━━━━━━━━━━━━━━━━━
{trend} {market.get('name')}
指數：{market.get('price', 0):,.2f}
漲跌：{market.get('change', 0):+.2f} ({market.get('change_percent', 0):+.2f}%)
━━━━━━━━━━━━━━━━━━━
📡 來源：{market.get('source', 'unknown')}
⏰ {market.get('update_time', '')}
""".strip()


def add_to_watchlist(user_id: str, code: str) -> str:
    """加入自選股"""
    if store.in_watchlist(user_id, code):
        return f"⚠️ {code} 已在自選股清單中"

    # 驗證股票是否存在
    stock = stock_service.get_stock(code)
    if not stock:
        return f"❌ 找不到股票：{code}"

    store.add_to_watchlist(user_id, code)
    return f"✅ 已將 {stock.name} ({code}) 加入自選股"


def remove_from_watchlist(user_id: str, code: str) -> str:
    """移除自選股"""
    if not store.remove_from_watchlist(user_id, code):
        return f"⚠️ {code} 不在自選股清單中"

    return f"✅ 已將 {code} 從自選股移除"


def get_watchlist(user_id: str) -> str:
    """查看自選股"""
    watchlist = store.get_watchlist(user_id)

    if not watchlist:
        return "📋 自選股清單為空\n\n使用 /add 股票代碼 新增"
    
    msg = "📋 我的自選股\n━━━━━━━━━━━━━━━━━━━\n"
    
    stocks = stock_service.get_multiple_stocks(watchlist)
    
    for stock in stocks:
        if stock.change > 0:
            trend = "🔺"
        elif stock.change < 0:
            trend = "🔻"
        else:
            trend = "➖"
        
        currency = "NT$" if stock.market == "tw" else "$"
        msg += f"{trend} {stock.name[:6]} {currency}{stock.price:,.2f} ({stock.change_percent:+.2f}%)\n"
    
    # 標記找不到的股票
    found_codes = [s.code for s in stocks]
    for code in watchlist:
        if code not in found_codes:
            msg += f"❓ {code} (無法取得)\n"
    
    msg += "━━━━━━━━━━━━━━━━━━━"
    return msg


def set_price_alert(user_id: str, text: str) -> str:
    """設定到價提醒"""
    match = re.match(r'(\w+)\s*([><])\s*([\d.]+)', text)
    if not match:
        return "❌ 格式錯誤\n\n正確格式：\n/alert 2330 > 1000\n/alert AAPL < 150"
    
    code = match.group(1).upper()
    condition = match.group(2)
    price = float(match.group(3))
    
    # 驗證股票
    stock = stock_service.get_stock(code)
    if not stock:
        return f"❌ 找不到股票：{code}"
    
    # 新增提醒
    store.add_alert(user_id, code, condition, price, stock.name)

    condition_text = "高於" if condition == ">" else "低於"
    return f"✅ 已設定提醒\n\n當 {stock.name} ({code})\n{condition_text} {price:,.2f} 時通知您\n\n目前價格：{stock.price:,.2f}"


def get_alerts(user_id: str) -> str:
    """查看所有提醒"""
    alerts = store.get_alerts(user_id)

    if not alerts:
        return "🔔 尚未設定任何到價提醒\n\n使用 /alert 股票代碼 > 價格 設定"
    
    msg = "🔔 我的到價提醒\n━━━━━━━━━━━━━━━━━━━\n"
    
    for i, alert in enumerate(alerts, 1):
        condition_text = ">" if alert["condition"] == ">" else "<"
        msg += f"{i}. {alert['name'][:6]} {condition_text} {alert['price']:,.2f}\n"
    
    msg += "━━━━━━━━━━━━━━━━━━━"
    return msg


def get_service_stats() -> str:
    """取得服務統計"""
    stats = stock_service.get_stats()
    
    return f"""
📊 服務統計
━━━━━━━━━━━━━━━━━━━
yfinance 狀態：{'✅ 可用' if stats['yfinance_available'] else '❌ 不可用'}
優先模式：{'yfinance' if stats['prefer_yfinance'] else 'scraper'}

📈 查詢統計：
• yfinance 成功：{stats['yfinance_success']}
• yfinance 失敗：{stats['yfinance_fail']}
• 爬蟲成功：{stats['scraper_success']}
• 爬蟲失敗：{stats['scraper_fail']}
━━━━━━━━━━━━━━━━━━━
""".strip()


def get_help_message() -> str:
    """說明訊息"""
    return """
📖 股票機器人使用說明
━━━━━━━━━━━━━━━━━━━

【查詢股價】
直接輸入代碼即可
• 台股：2330、0050
• 美股：AAPL、TSLA

【自選股】
• /add 2330 - 加入
• /del 2330 - 移除
• /list - 查看清單

【到價提醒】
• /alert 2330 > 1000
• /alert AAPL < 150
• /alerts - 查看提醒

【其他】
• /market - 大盤指數
• /stats - 系統狀態
• /help - 本說明

━━━━━━━━━━━━━━━━━━━
🔄 雙模式備援架構
📡 資料來源：Yahoo Finance
""".strip()


# ============================================
# 到價提醒檢查（供排程器呼叫）
# ============================================
def check_price_alerts():
    """
    檢查所有用戶的到價提醒。

    從 SQLite 讀取（而非行程內字典），因此獨立的 scheduler container
    也能看到 webhook 寫入的提醒。
    """
    for user_id, alert in store.iter_alerts():
        stock = stock_service.get_stock(alert["code"])

        if not stock:
            continue

        triggered = False
        if alert["condition"] == ">" and stock.price > alert["price"]:
            triggered = True
        elif alert["condition"] == "<" and stock.price < alert["price"]:
            triggered = True

        if not triggered:
            continue

        condition_text = "突破" if alert["condition"] == ">" else "跌破"
        msg = f"""
🔔 到價提醒觸發！

{alert['name']} ({alert['code']})
目前價格：{stock.price:,.2f}
已{condition_text} {alert['price']:,.2f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""".strip()

        send_push_message(user_id, msg)
        store.remove_alert(alert["id"])  # 觸發後移除


# ============================================
# 輔助函式
# ============================================
def send_reply(reply_token: str, message: str):
    """發送回覆"""
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=message)]
            )
        )


def send_push_message(user_id: str, message: str):
    """主動推播訊息"""
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=message)]
                )
            )
    except Exception as e:
        print(f"[Push Error] {e}")


# ============================================
# 主程式
# ============================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🚀 Stock LINE Bot 啟動中...")
    print("=" * 50)
    print(f"📡 雙模式備援架構")
    stats = stock_service.get_stats()
    print(f"   yfinance: {'✅ 可用' if stats['yfinance_available'] else '❌ 不可用'}")
    print(f"   爬蟲備援: ✅ 可用")
    print(f"🌐 Port: {port}")
    print("=" * 50)
    
    app.run(host="0.0.0.0", port=port, debug=settings.DEBUG)
