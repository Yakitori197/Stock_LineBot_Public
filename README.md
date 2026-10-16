# 📈 Stock LINE Bot

台股/美股即時報價 LINE 機器人 - 雙模式備援架構（yfinance + 爬蟲）

---

##  Features

-  **Real-time Stock Quotes** - Taiwan & US stocks
-  **Dual-mode Fallback** - yfinance + web scraper
-  **Watchlist** - Save your favorite stocks
-  **Price Alerts** - Get notified when price hits target
-  **Market Index** - Taiwan weighted index

---

##  Demo

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

##  Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Yakitori197/Stock_LineBot_Public.git
cd Stock_LineBot_Public
```

### 2. Create virtual environment

需要 Python 3.11（與 Docker 映像一致）及 Git；`git --version` 應可執行，因為 yolab-quote 從固定 Git tag 安裝。

Windows PowerShell：

```powershell
$env:PYTHONUTF8 = "1"
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Windows 預設編碼可能是 cp950；請在每次開新終端機時設定 `PYTHONUTF8=1`，避免 pip 讀取含中文註解的 requirements.txt 時解碼失敗。cmd 使用 `set PYTHONUTF8=1`，再執行 `venv\Scripts\activate.bat`。也可單次使用 `python -X utf8 -m pip install -r requirements.txt`；只改 `chcp 65001` 不等於啟用 Python UTF-8 模式。

Linux / macOS：

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
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

##  Project Structure

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

##  Dual-mode Architecture

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

##  Docker Deployment

```bash
docker-compose up -d
```

---

## 測試與自動驗證

已安裝 requirements.txt 後，Windows PowerShell 執行：

```powershell
$env:PYTHONUTF8 = "1"
python -m pip check
python -m pytest tests -q
```

Linux / macOS 使用相同的 Python 指令即可。測試使用暫存 SQLite 資料庫，涵蓋自選股、到價提醒儲存及跨行程共用，不需要 LINE 憑證。

[CI workflow](.github/workflows/ci.yml) 在推送 `main`、向 `main` 提出 PR 或手動執行時：

- 在 Windows 與 Linux 的 Python 3.11 安裝依賴、執行 `pip check` 與既有測試，並設定 `PYTHONUTF8=1`。
- 在 Linux 建置正式 Dockerfile，檢查映像依賴與 yolab-quote 0.1.1。
- 以合成憑證、暫存資料庫及 `--network none` 載入 Web／scheduler 模組，用 Flask test client 檢查 `/health`，不啟動提醒迴圈或向 LINE 發送訊息。

CI 不推送映像、不執行部署，也不使用正式憑證。這些檢查不代表已驗證真實 LINE Webhook、到價通知或線上行情服務。

---

##  License

MIT License - feel free to use this project for personal or commercial purposes.

---

##  Author

**YoLab 工作室**

- GitHub: [@Yakitori197](https://github.com/Yakitori197)
- LINE: [@442fjdqq](https://line.me/R/ti/p/@442fjdqq)

---

##  Contact

有任何問題或合作需求，歡迎透過 LINE 聯繫我們！

[![LINE](https://img.shields.io/badge/LINE-@442fjdqq-00C300.svg?logo=line&logoColor=white)](https://line.me/R/ti/p/@442fjdqq)

---

##  Star this repo if you find it useful!
