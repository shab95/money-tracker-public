import os


VALID_ENVS = {"local", "test", "qa", "production"}


def get_streamlit_secret(name, default=None):
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            return st.secrets.get(name, default)
    except Exception:
        return default
    return default


def get_secret_env():
    return get_streamlit_secret("MONEY_TRACKER_ENV") or get_streamlit_secret("APP_ENV")


def has_streamlit_database_secret():
    return bool(
        get_streamlit_secret("DB_CONNECTION_STRING")
        or get_streamlit_secret("DIRECT_CONNECTION")
    )


def is_streamlit_cloud_runtime():
    """
    Streamlit Community Cloud does not provide one guaranteed environment flag.
    These markers are intentionally narrow so local `.streamlit/secrets.toml`
    files do not accidentally enable the production DB.
    """
    if os.getenv("STREAMLIT_CLOUD") or os.getenv("IS_STREAMLIT_SHARING"):
        return True
    if os.getenv("USER") == "appuser" and os.getenv("HOME") == "/home/appuser":
        return True
    if os.getenv("USER") == "appuser" and os.path.exists("/mount/src"):
        return True
    return False


def get_app_env():
    explicit_env = os.getenv("MONEY_TRACKER_ENV") or get_secret_env()
    if explicit_env:
        env = explicit_env.strip().lower()
        if env not in VALID_ENVS:
            return "local"
        return env

    if is_streamlit_cloud_runtime() and has_streamlit_database_secret():
        return "production"

    env = "local"
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
