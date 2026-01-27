# 📈 Stock LINE Bot

台股/美股即時報價 LINE 機器人 - 雙模式備援架構（yfinance + 爬蟲）

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![LINE](https://img.shields.io/badge/LINE-Messaging%20API-00C300.svg)](https://developers.line.biz/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

- 📊 **Real-time Stock Quotes** - Taiwan & US stocks
- 🔄 **Dual-mode Fallback** - yfinance + web scraper
- 📋 **Watchlist** - Save your favorite stocks
- 🔔 **Price Alerts** - Get notified when price hits target
- 📈 **Market Index** - Taiwan weighted index

---

## 📱 Demo

```
You: 2330
Bot:
📊 台積電 (2330)
━━━━━━━━━━━━
開盤：NT$1,770.00
收盤：NT$1,780.00
漲跌：🔺 +10.00 (+0.56%)
成交量：53,450 張
━━━━━━━━━━━━
⏰ 2026-01-27 14:30:00

You: AAPL
Bot:
📊 Apple Inc. (AAPL)
━━━━━━━━━━━━
開盤：$250.00
現價：$255.41
漲跌：🔺 +5.41 (+2.16%)
━━━━━━━━━━━━
⏰ 2026-01-27 22:30:00
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/Stock_LineBot.git
cd Stock_LineBot
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env and add your LINE Bot credentials
```

### 5. Run the bot

```bash
python src/app.py
```

---

## 🔧 LINE Bot Setup

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Create a new Messaging API channel
3. Get your **Channel Secret** and **Channel Access Token**
4. Set up Webhook URL: `https://your-domain.com/callback`

---

## 📖 Commands

| Command | Description |
|---------|-------------|
| `2330` | Query Taiwan stock |
| `AAPL` | Query US stock |
| `/help` | Show help message |
| `/market` | Show market index |
| `/add 2330` | Add to watchlist |
| `/del 2330` | Remove from watchlist |
| `/list` | Show watchlist |
| `/alert 2330 > 1000` | Set price alert |
| `/alerts` | Show all alerts |

---

## 📁 Project Structure

```
Stock_LineBot/
├── src/
│   ├── app.py              # LINE Bot main app
│   ├── stock_service.py    # Dual-mode stock service
│   └── scheduler.py        # Price alert scheduler
├── config/
│   └── settings.py         # Configuration
├── .env.example            # Environment variables template
├── requirements.txt        # Python dependencies
├── Start.bat               # Windows startup script
├── Stop.bat                # Windows stop script
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🔄 Dual-mode Architecture

```
┌─────────────────────────────────────────┐
│          StockDataService               │
│                                         │
│   ┌─────────────┐    ┌─────────────┐   │
│   │  yfinance   │───▶│  Scraper    │   │
│   │  (Primary)  │fail│  (Fallback) │   │
│   └─────────────┘    └─────────────┘   │
└─────────────────────────────────────────┘
```

- **Primary**: yfinance - Fast and reliable
- **Fallback**: Web scraper - Works when yfinance fails

---

## 🐳 Docker Deployment

```bash
docker-compose up -d
```

---

## 📝 License

MIT License - feel free to use this project for personal or commercial purposes.

---

## 👤 Author

**Yakitori197**

- GitHub: [@Yakitori197](https://github.com/Yakitori197)

---

## ⭐ Star this repo if you find it useful!
