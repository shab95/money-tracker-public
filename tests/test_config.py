import importlib
import sys
from types import SimpleNamespace


def install_fake_streamlit(monkeypatch, secrets):
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(secrets=secrets))


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


def test_streamlit_cloud_with_db_secret_defaults_to_production(monkeypatch):
    install_fake_streamlit(monkeypatch, {"DB_CONNECTION_STRING": "postgres://example"})
    monkeypatch.delenv("MONEY_TRACKER_ENV", raising=False)
    monkeypatch.delenv("MONEY_TRACKER_USE_PRODUCTION_DB", raising=False)
    monkeypatch.setenv("USER", "appuser")
    monkeypatch.setenv("HOME", "/home/appuser")

    import config

    config = importlib.reload(config)
    assert config.get_app_env() == "production"
    assert config.should_use_production_db()


def test_local_streamlit_db_secret_still_defaults_to_sqlite(monkeypatch):
    install_fake_streamlit(monkeypatch, {"DB_CONNECTION_STRING": "postgres://example"})
    monkeypatch.delenv("MONEY_TRACKER_ENV", raising=False)
    monkeypatch.delenv("MONEY_TRACKER_USE_PRODUCTION_DB", raising=False)
    monkeypatch.setenv("USER", "local-user")
    monkeypatch.setenv("HOME", "/Users/local-user")

    import config

    config = importlib.reload(config)
    assert config.get_app_env() == "local"
    assert not config.should_use_production_db()


def test_explicit_local_overrides_streamlit_cloud_db_secret(monkeypatch):
    install_fake_streamlit(
        monkeypatch,
        {"MONEY_TRACKER_ENV": "local", "DB_CONNECTION_STRING": "postgres://example"},
    )
    monkeypatch.delenv("MONEY_TRACKER_ENV", raising=False)
    monkeypatch.delenv("MONEY_TRACKER_USE_PRODUCTION_DB", raising=False)
    monkeypatch.setenv("USER", "appuser")
    monkeypatch.setenv("HOME", "/home/appuser")

    import config

    config = importlib.reload(config)
    assert config.get_app_env() == "local"
    assert not config.should_use_production_db()
