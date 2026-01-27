"""
股票 LINE Bot 設定管理
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """應用程式設定"""
    
    # LINE Bot
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
    
    # App
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    PORT: int = int(os.getenv("PORT", "5000"))
    
    # 提醒檢查間隔（秒）
    ALERT_CHECK_INTERVAL: int = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))
    
    def __post_init__(self):
        if not self.LINE_CHANNEL_ACCESS_TOKEN:
            raise ValueError("LINE_CHANNEL_ACCESS_TOKEN is required")
        if not self.LINE_CHANNEL_SECRET:
            raise ValueError("LINE_CHANNEL_SECRET is required")
