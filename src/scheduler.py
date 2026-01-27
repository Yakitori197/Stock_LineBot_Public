"""
到價提醒排程檢查器

此腳本獨立運行，定期檢查用戶設定的到價提醒
可使用 cron 或 systemd timer 執行

使用方式：
1. 直接執行（持續運行）：python scheduler.py
2. 搭配 cron（每分鐘執行一次）：* * * * * python scheduler.py --once

Author: Yakitori197
"""

import time
import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app import check_price_alerts, stock_service
from config.settings import Settings


def run_scheduler(interval: int = 60):
    """持續運行的排程器"""
    stats = stock_service.get_stats()
    
    print(f"🚀 到價提醒排程器已啟動")
    print(f"   檢查間隔：{interval} 秒")
    print(f"   yfinance: {'✅' if stats['yfinance_available'] else '❌'}")
    print("-" * 40)
    
    while True:
        try:
            print(f"⏰ 檢查到價提醒... ", end="")
            check_price_alerts()
            print("✅ 完成")
        except Exception as e:
            print(f"❌ 錯誤: {e}")
        
        time.sleep(interval)


def run_once():
    """執行一次檢查"""
    print("🔔 執行到價提醒檢查...")
    check_price_alerts()
    print("✅ 完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="到價提醒排程器")
    parser.add_argument("--once", action="store_true", help="只執行一次")
    parser.add_argument("--interval", type=int, default=60, help="檢查間隔（秒）")
    args = parser.parse_args()
    
    if args.once:
        run_once()
    else:
        settings = Settings()
        run_scheduler(args.interval)
