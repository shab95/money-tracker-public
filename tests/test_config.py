import importlib


def test_qa_mode_uses_qa_sqlite_file(monkeypatch):
    monkeypatch.setenv("MONEY_TRACKER_ENV", "qa")
    monkeypatch.delenv("MONEY_TRACKER_DB_FILE", raising=False)
    import config

    config = importlib.reload(config)
    assert config.is_qa_env()
    assert not config.is_production_env()
    assert config.get_db_file() == "tracker_qa.db"


def test_only_production_or_override_uses_production_db(monkeypatch):
    import config

    monkeypatch.setenv("MONEY_TRACKER_ENV", "qa")
    monkeypatch.delenv("MONEY_TRACKER_USE_PRODUCTION_DB", raising=False)
    config = importlib.reload(config)
    assert not config.should_use_production_db()

    monkeypatch.setenv("MONEY_TRACKER_ENV", "production")
    config = importlib.reload(config)
    assert config.should_use_production_db()

    monkeypatch.setenv("MONEY_TRACKER_ENV", "local")
    monkeypatch.setenv("MONEY_TRACKER_USE_PRODUCTION_DB", "1")
    config = importlib.reload(config)
    assert config.should_use_production_db()
