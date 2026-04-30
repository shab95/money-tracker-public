import importlib
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def reload_db(monkeypatch, tmp_path):
    monkeypatch.setenv("MONEY_TRACKER_ENV", "test")
    monkeypatch.setenv("MONEY_TRACKER_DB_FILE", str(tmp_path / "tracker_test.db"))
    import config
    import db

    importlib.reload(config)
    return importlib.reload(db)
