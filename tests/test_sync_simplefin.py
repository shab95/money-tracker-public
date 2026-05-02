from conftest import reload_db
from datetime import datetime
import pandas as pd


class FakeClassifier:
    def predict(self, description, signed_amount):
        return {
            "category": "Uncategorized",
            "type": "Expense" if signed_amount < 0 else "Income",
            "confidence": 0.7,
            "cat_confidence": 0.7,
            "type_confidence": 0.9,
            "model_available": True,
            "prediction_source": "model",
        }


class UntrainedClassifier:
    def predict(self, description, signed_amount):
        return {
            "category": "Uncategorized",
            "type": "Expense" if signed_amount < 0 else "Income",
            "confidence": 0.0,
            "cat_confidence": 0.0,
            "type_confidence": 0.0,
            "model_available": False,
            "prediction_source": "fallback_untrained",
        }


def test_sync_report_includes_and_skips_accounts(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    import sync_simplefin

    monkeypatch.setattr(sync_simplefin, "db", db)
    monkeypatch.setattr(sync_simplefin, "SIMPLEFIN_ACCESS_URL", "https://example.test")
    monkeypatch.setattr(sync_simplefin.ml_utils, "classifier", FakeClassifier())
    monkeypatch.setattr(sync_simplefin, "fetch_data", lambda *_args, **_kwargs: {
        "accounts": [
            {
                "org": {"name": "Capital One"},
                "name": "360 Checking (3285)",
                "balance": "1000.25",
                "currency": "USD",
                "transactions": [{
                    "id": "sf-1",
                    "posted": 1777377600,
                    "amount": "-12.34",
                    "description": "COFFEE",
                    "memo": "",
                }],
            },
            {
                "org": {"name": "Robinhood"},
                "name": "Robinhood Roth IRA (0799)",
                "balance": "2500.00",
                "currency": "USD",
                "transactions": [{
                    "id": "sf-2",
                    "posted": 1777377600,
                    "amount": "50",
                    "description": "DIVIDEND",
                    "memo": "",
                }],
            },
        ]
    })

    report = sync_simplefin.sync()
    assert report["transactions_inserted"] == 1
    assert len(report["accounts"]) == 2
    included = [item for item in report["accounts"] if item["included"]]
    assert included[0]["health_status"] == "Healthy"
    assert included[0]["latest_transaction_date"] == "2026-04-28"
    assert included[0]["balance"] == 1000.25
    skipped = [item for item in report["accounts"] if not item["included"]]
    assert skipped[0]["skip_reason"] == "retirement_or_restricted_account"
    history = db.get_balance_history_details()
    assert set(history["account"]) == {"360 Checking (3285)", "Robinhood Roth IRA (0799)"}
    checking = history[history["account"] == "360 Checking (3285)"].iloc[0]
    assert checking["balance"] == 1000.25
    assert checking["classification"] == "Cash"
    roth = history[history["account"] == "Robinhood Roth IRA (0799)"].iloc[0]
    assert roth["balance"] == 2500.0
    assert roth["classification"] == "Retirement / Restricted"


def test_sync_notes_untrained_model_without_low_confidence_percent(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    import sync_simplefin

    monkeypatch.setattr(sync_simplefin, "db", db)
    monkeypatch.setattr(sync_simplefin, "SIMPLEFIN_ACCESS_URL", "https://example.test")
    monkeypatch.setattr(sync_simplefin.ml_utils, "classifier", UntrainedClassifier())
    monkeypatch.setattr(sync_simplefin, "fetch_data", lambda *_args, **_kwargs: {
        "accounts": [{
            "org": {"name": "Capital One"},
            "name": "360 Checking (3285)",
            "balance": "1000.25",
            "currency": "USD",
            "transactions": [{
                "id": "sf-untrained",
                "posted": 1777377600,
                "amount": "-12.34",
                "description": "COFFEE",
                "memo": "",
            }],
        }]
    })

    sync_simplefin.sync()

    saved = db.get_all_transactions().iloc[0]
    assert saved["user_notes"] == "ML model not trained"
    assert saved["ml_confidence"] == 0.0


def test_account_rules_control_sync_and_balance_snapshot(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    import sync_simplefin

    db.upsert_account_rules([{
        "bank": "Capital One",
        "account": "360 Checking (3285)",
        "classification": "Retirement / Restricted",
        "include_in_inbox": False,
        "include_in_net_worth": False,
    }])
    monkeypatch.setattr(sync_simplefin, "db", db)
    monkeypatch.setattr(sync_simplefin, "SIMPLEFIN_ACCESS_URL", "https://example.test")
    monkeypatch.setattr(sync_simplefin.ml_utils, "classifier", FakeClassifier())
    monkeypatch.setattr(sync_simplefin, "fetch_data", lambda *_args, **_kwargs: {
        "accounts": [{
            "org": {"name": "Capital One"},
            "name": "360 Checking (3285)",
            "balance": "1000.25",
            "currency": "USD",
            "transactions": [{
                "id": "sf-rule",
                "posted": 1777377600,
                "amount": "-12.34",
                "description": "COFFEE",
                "memo": "",
            }],
        }]
    })

    report = sync_simplefin.sync()

    assert report["balance_accounts_seen"] == 0
    assert report["transactions_inserted"] == 0
    assert report["accounts"][0]["included"] is False
    assert report["accounts"][0]["skip_reason"] == "account_rule_excluded_from_inbox"
    assert db.get_balance_history_details().empty


def test_sync_replaces_today_balance_snapshot(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    import sync_simplefin

    db.save_balance_snapshot(pd.DataFrame([
        {
            "Bank": "Old Bank",
            "Account": "Closed Account",
            "Balance": 10.0,
            "Classification": "Cash",
        },
    ]))
    monkeypatch.setattr(sync_simplefin, "db", db)
    monkeypatch.setattr(sync_simplefin, "SIMPLEFIN_ACCESS_URL", "https://example.test")
    monkeypatch.setattr(sync_simplefin.ml_utils, "classifier", FakeClassifier())
    monkeypatch.setattr(sync_simplefin, "fetch_data", lambda *_args, **_kwargs: {
        "accounts": [
            {
                "org": {"name": "Capital One"},
                "name": "360 Checking (3285)",
                "balance": "1000.25",
                "currency": "USD",
                "transactions": [],
            },
        ]
    })

    sync_simplefin.sync()

    history = db.get_balance_history_details()
    assert set(history["account"]) == {"360 Checking (3285)"}


def test_empty_sync_does_not_fall_back_to_previous_balance_snapshot(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    import sync_simplefin

    conn = db.get_connection()
    conn.execute("""
        INSERT INTO balance_history (date, bank, account, balance, classification)
        VALUES (?, ?, ?, ?, ?)
    """, ("2026-04-28", "Old Bank", "Closed Account", 10.0, "Cash"))
    conn.commit()
    conn.close()

    monkeypatch.setattr(sync_simplefin, "db", db)
    monkeypatch.setattr(sync_simplefin, "SIMPLEFIN_ACCESS_URL", "https://example.test")
    monkeypatch.setattr(sync_simplefin.ml_utils, "classifier", FakeClassifier())
    monkeypatch.setattr(sync_simplefin, "fetch_data", lambda *_args, **_kwargs: {
        "accounts": []
    })

    sync_simplefin.sync()

    assert db.get_latest_balance_snapshot().empty
    context = db.get_latest_balance_context()
    assert context["has_successful_sync"] is True
    assert context["latest_sync_returned_no_balances"] is True
    assert context["balance_accounts_seen"] == 0
    assert context["balances"].empty
    history = db.get_balance_history_details()
    assert set(history["account"]) == {"Closed Account"}


def test_account_health_no_transactions_in_window():
    import sync_simplefin

    assert sync_simplefin.get_account_health_status(True, "", 0, "", 100.0) == "Healthy, no activity"
    assert sync_simplefin.get_account_health_status(True, "", 0, "", None) == "Needs review"
    assert sync_simplefin.get_account_health_status(False, "retirement_or_restricted_account", 0, "", 100.0) == "Healthy, no activity"


def test_fidelity_401k_duplicate_prefers_fidelity_investments():
    import sync_simplefin

    accounts = [
        {
            "org": {"name": "Fidelity Investments"},
            "name": "Self-Directed Brokerage (3743)",
            "transactions": [],
        },
        {
            "org": {"name": "Fidelity 401k"},
            "name": "Self-Directed Brokerage (3743)",
            "transactions": [],
        },
    ]
    reasons = sync_simplefin.find_duplicate_connection_reasons(accounts)
    assert reasons[("Fidelity 401k", "Self-Directed Brokerage (3743)")] == "duplicate_connection_prefer_fidelity_investments"


def test_balance_snapshot_skips_duplicate_fidelity_401k():
    import sync_simplefin

    accounts = [
        {
            "org": {"name": "Fidelity 401k"},
            "name": "Self-Directed Brokerage (3743)",
            "balance": "10.00",
            "transactions": [],
        },
        {
            "org": {"name": "Fidelity Investments"},
            "name": "Self-Directed Brokerage (3743)",
            "balance": "20.00",
            "transactions": [],
        },
    ]
    reasons = sync_simplefin.find_duplicate_connection_reasons(accounts)
    rows = sync_simplefin.build_balance_snapshot_rows(accounts, reasons)

    assert rows == [{
        "Bank": "Fidelity Investments",
        "Account": "Self-Directed Brokerage (3743)",
        "Balance": 20.0,
        "Classification": "Retirement / Restricted",
    }]


def test_duplicate_detection_does_not_skip_unrelated_same_account_names():
    import sync_simplefin

    accounts = [
        {
            "org": {"name": "Capital One"},
            "name": "360 Checking (1111)",
            "transactions": [],
        },
        {
            "org": {"name": "Other Bank"},
            "name": "360 Checking (2222)",
            "transactions": [],
        },
    ]
    assert sync_simplefin.find_duplicate_connection_reasons(accounts) == {}


def test_local_sync_window_defaults_to_recent(monkeypatch):
    import sync_simplefin

    monkeypatch.setenv("MONEY_TRACKER_ENV", "local")
    monkeypatch.delenv("MONEY_TRACKER_SIMPLEFIN_START_DATE", raising=False)
    monkeypatch.delenv("MONEY_TRACKER_LOCAL_SYNC_DAYS", raising=False)

    start_date, end_date = sync_simplefin.get_sync_date_range(datetime(2026, 4, 29))
    assert start_date == "2026-03-30"
    assert end_date == "2026-04-29"


def test_production_sync_window_defaults_to_recent(monkeypatch):
    import sync_simplefin

    monkeypatch.setenv("MONEY_TRACKER_ENV", "production")
    monkeypatch.delenv("MONEY_TRACKER_SIMPLEFIN_START_DATE", raising=False)
    monkeypatch.delenv("MONEY_TRACKER_SYNC_DAYS", raising=False)

    start_date, end_date = sync_simplefin.get_sync_date_range(datetime(2026, 4, 29))
    assert start_date == "2026-03-30"
    assert end_date == "2026-04-29"


def test_sync_window_can_be_explicitly_backfilled(monkeypatch):
    import sync_simplefin

    monkeypatch.setenv("MONEY_TRACKER_ENV", "production")
    monkeypatch.setenv("MONEY_TRACKER_SIMPLEFIN_START_DATE", "2025-12-01")

    start_date, end_date = sync_simplefin.get_sync_date_range(datetime(2026, 4, 29))
    assert start_date == "2025-12-01"
    assert end_date == "2026-04-29"
