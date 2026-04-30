import os


VALID_ENVS = {"local", "test", "qa", "production"}


def get_secret_env():
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            return st.secrets.get("MONEY_TRACKER_ENV") or st.secrets.get("APP_ENV")
    except Exception:
        return None
    return None


def get_app_env():
    env = (os.getenv("MONEY_TRACKER_ENV") or get_secret_env() or "local").strip().lower()
    if env not in VALID_ENVS:
        return "local"
    return env


def is_production_env():
    return get_app_env() == "production"


def is_qa_env():
    return get_app_env() == "qa"


def allow_local_production_db():
    return os.getenv("MONEY_TRACKER_USE_PRODUCTION_DB", "").strip() == "1"


def should_use_production_db():
    return is_production_env() or allow_local_production_db()


def get_db_file():
    if get_app_env() == "test":
        return os.getenv("MONEY_TRACKER_DB_FILE", "tracker_test.db")
    if get_app_env() == "qa":
        return os.getenv("MONEY_TRACKER_DB_FILE", "tracker_qa.db")
    return os.getenv("MONEY_TRACKER_DB_FILE", "tracker.db")
