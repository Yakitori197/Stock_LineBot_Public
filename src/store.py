"""
SQLite 資料存取層（自選股 / 到價提醒）。

為什麼需要這層：
原本自選股與到價提醒存在 app 行程內的字典（user_data = {}），造成兩個實際故障：

1. docker-compose 把 scheduler 開成獨立 container，它 `from src.app import check_price_alerts`
   時只會在自己的行程建立一份**全新的空字典** → 到價提醒永遠不會觸發。
2. gunicorn `--workers 2` 時各 worker 記憶體獨立（A 設的自選股 B 看不到），且重啟即失憶。

改用 SQLite 後，webhook 與 scheduler 共用同一份狀態（docker-compose 以 volume 掛載
/app/data），並且重啟不再遺失資料。
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Tuple


def _db_path() -> str:
    """每次讀取環境變數，方便測試以 DB_PATH 指向暫存檔。"""
    return os.getenv("DB_PATH", "data/linebot.db")


@contextmanager
def _conn():
    path = _db_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # 允許多行程同時讀寫
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """建立資料表（可重複呼叫）。"""
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id TEXT NOT NULL,
                code    TEXT NOT NULL,
                PRIMARY KEY (user_id, code)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT NOT NULL,
                code      TEXT NOT NULL,
                condition TEXT NOT NULL,
                price     REAL NOT NULL,
                name      TEXT,
                created   TEXT NOT NULL
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id)")


# ---------------------------------------------------------------- 自選股

def get_watchlist(user_id: str) -> List[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT code FROM watchlist WHERE user_id = ? ORDER BY rowid", (user_id,)
        ).fetchall()
    return [r["code"] for r in rows]


def in_watchlist(user_id: str, code: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND code = ?", (user_id, code)
        ).fetchone()
    return row is not None


def add_to_watchlist(user_id: str, code: str) -> bool:
    """加入自選股；已存在回傳 False。"""
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO watchlist (user_id, code) VALUES (?, ?)", (user_id, code)
            )
        except sqlite3.IntegrityError:
            return False
    return True


def remove_from_watchlist(user_id: str, code: str) -> bool:
    """移除自選股；不存在回傳 False。"""
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND code = ?", (user_id, code)
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------- 到價提醒

def add_alert(user_id: str, code: str, condition: str, price: float, name: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO alerts (user_id, code, condition, price, name, created)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, code, condition, price, name, datetime.now().isoformat()),
        )


def get_alerts(user_id: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, code, condition, price, name, created FROM alerts"
            " WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def iter_alerts() -> List[Tuple[str, Dict[str, Any]]]:
    """
    取出所有使用者的提醒，供排程器檢查。
    回傳 [(user_id, alert), ...]；alert 內含 id 供觸發後刪除。
    """
    with _conn() as c:
        rows = c.execute(
            "SELECT id, user_id, code, condition, price, name, created FROM alerts"
            " ORDER BY user_id, id"
        ).fetchall()
    return [(r["user_id"], dict(r)) for r in rows]


def remove_alert(alert_id: int) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        return cur.rowcount > 0
