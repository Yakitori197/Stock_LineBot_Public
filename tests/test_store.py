"""
src/store.py 測試。

重點在最後一組：模擬「webhook 行程寫入 → 獨立 scheduler 行程讀取」，
這正是原本用行程內字典時永遠失敗、導致到價提醒不會觸發的情境。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# 直接把 src/ 加入路徑載入 store 模組。
# 不走 `from src import store`，因為 src/__init__.py 會急切載入 stock_service
# （連帶 requests / yfinance）；store.py 本身只依賴標準庫，測試應保持輕量。
SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import store


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    store.init_db()
    yield


class TestWatchlist:
    def test_empty_initially(self):
        assert store.get_watchlist("U1") == []

    def test_add_and_get(self):
        assert store.add_to_watchlist("U1", "2330") is True
        assert store.get_watchlist("U1") == ["2330"]

    def test_duplicate_rejected(self):
        store.add_to_watchlist("U1", "2330")
        assert store.add_to_watchlist("U1", "2330") is False
        assert store.get_watchlist("U1") == ["2330"]

    def test_in_watchlist(self):
        store.add_to_watchlist("U1", "2330")
        assert store.in_watchlist("U1", "2330") is True
        assert store.in_watchlist("U1", "AAPL") is False

    def test_remove(self):
        store.add_to_watchlist("U1", "2330")
        assert store.remove_from_watchlist("U1", "2330") is True
        assert store.get_watchlist("U1") == []

    def test_remove_missing_returns_false(self):
        assert store.remove_from_watchlist("U1", "9999") is False

    def test_users_are_isolated(self):
        store.add_to_watchlist("U1", "2330")
        store.add_to_watchlist("U2", "AAPL")
        assert store.get_watchlist("U1") == ["2330"]
        assert store.get_watchlist("U2") == ["AAPL"]


class TestAlerts:
    def test_empty_initially(self):
        assert store.get_alerts("U1") == []

    def test_add_and_get(self):
        store.add_alert("U1", "2330", ">", 1000.0, "台積電")
        alerts = store.get_alerts("U1")
        assert len(alerts) == 1
        assert alerts[0]["code"] == "2330"
        assert alerts[0]["condition"] == ">"
        assert alerts[0]["price"] == 1000.0
        assert alerts[0]["name"] == "台積電"
        assert "id" in alerts[0]

    def test_multiple_alerts_same_code_allowed(self):
        store.add_alert("U1", "2330", ">", 1000.0, "台積電")
        store.add_alert("U1", "2330", "<", 800.0, "台積電")
        assert len(store.get_alerts("U1")) == 2

    def test_remove_alert(self):
        store.add_alert("U1", "2330", ">", 1000.0, "台積電")
        alert_id = store.get_alerts("U1")[0]["id"]
        assert store.remove_alert(alert_id) is True
        assert store.get_alerts("U1") == []

    def test_remove_missing_alert_returns_false(self):
        assert store.remove_alert(9999) is False

    def test_iter_alerts_covers_all_users(self):
        store.add_alert("U1", "2330", ">", 1000.0, "台積電")
        store.add_alert("U2", "AAPL", "<", 150.0, "Apple")
        pairs = store.iter_alerts()
        assert len(pairs) == 2
        assert {uid for uid, _ in pairs} == {"U1", "U2"}

    def test_iter_alerts_includes_id_for_removal(self):
        store.add_alert("U1", "2330", ">", 1000.0, "台積電")
        _uid, alert = store.iter_alerts()[0]
        assert store.remove_alert(alert["id"]) is True


class TestCrossProcessSharing:
    """
    回歸測試：原本 user_data 是行程內字典，獨立的 scheduler 行程
    import app 後只會拿到一份空字典 → 提醒永遠不觸發。
    改用 SQLite 後，另一個行程必須能讀到本行程寫入的資料。
    """

    def test_another_process_sees_written_alert(self, tmp_path):
        db = os.environ["DB_PATH"]
        store.add_alert("U1", "2330", ">", 1000.0, "台積電")

        # 另開一個獨立的 Python 行程（等同 scheduler container）
        code = (
            "import sys; sys.path.insert(0, r'%s');"
            "import store;"
            "print(len(store.iter_alerts()))" % str(SRC_DIR)
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "DB_PATH": db},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "1"  # 另一個行程確實看得到

    def test_another_process_sees_watchlist(self, tmp_path):
        db = os.environ["DB_PATH"]
        store.add_to_watchlist("U1", "2330")

        code = (
            "import sys; sys.path.insert(0, r'%s');"
            "import store;"
            "print(store.get_watchlist('U1'))" % str(SRC_DIR)
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "DB_PATH": db},
        )
        assert result.returncode == 0, result.stderr
        assert "2330" in result.stdout
