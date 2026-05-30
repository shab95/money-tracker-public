import pandas as pd
from datetime import datetime

from conftest import reload_db


def test_upsert_transactions_persists_source_fields(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    df = pd.DataFrame([{
        "id": "tx-1",
        "date": "2026-04-28",
        "amount": 4.95,
        "description": "WASIF PERVEZ",
        "category": "Uncategorized",
        "type": "Income",
        "method": "Capital One - 360 Checking (3285)",
        "account": "360 Checking (3285)",
        "posted_date": "2026-04-28",
        "details": "memo",
        "raw_data": "{'id': 'tx-1'}",
        "ml_confidence": 0.5,
        "ml_category_confidence": 0.4,
        "ml_type_confidence": 0.8,
    }])

    assert db.upsert_transactions(df) == 1
    saved = db.get_all_transactions()
    row = saved.iloc[0]
    assert row["account"] == "360 Checking (3285)"
    assert row["posted_date"] == "2026-04-28"
    assert row["details"] == "memo"
    assert row["ml_confidence"] == 0.5
    assert pd.isna(row["reviewed_at"])


def test_sync_report_roundtrip(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    report = {
        "started_at": "2026-04-29T01:00:00",
        "finished_at": "2026-04-29T01:00:02",
        "status": "success",
        "transactions_seen": 2,
        "transactions_inserted": 1,
        "duplicates": 1,
        "balance_accounts_seen": 1,
        "sync_start_date": "2026-04-01",
        "sync_end_date": "2026-04-29",
        "accounts": [
            {
                "bank": "Capital One",
                "account": "360 Checking",
                "included": True,
                "skip_reason": "",
                "transaction_count": 2,
                "inserted_count": 1,
                "duplicate_count": 1,
                "latest_transaction_date": "2026-04-28",
                "balance": 123.45,
                "currency": "USD",
                "health_status": "Healthy",
                "error": "",
            },
            {
                "bank": "Robinhood",
                "account": "Robinhood Roth IRA (0799)",
                "included": False,
                "skip_reason": "retirement_or_restricted_account",
                "transaction_count": 10,
                "inserted_count": 0,
                "duplicate_count": 0,
                "error": "",
            },
        ],
    }

    db.save_sync_report(report)
    latest, accounts = db.get_latest_sync_account_results()
    assert latest.iloc[0]["transactions_inserted"] == 1
    assert latest.iloc[0]["balance_accounts_seen"] == 1
    assert latest.iloc[0]["sync_start_date"] == "2026-04-01"
    assert set(accounts["skip_reason"]) == {"", "retirement_or_restricted_account"}
    checking = accounts[accounts["account"] == "360 Checking"].iloc[0]
    assert checking["latest_transaction_date"] == "2026-04-28"
    assert checking["health_status"] == "Healthy"


def test_simplefin_id_does_not_duplicate_legacy_hash_row(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    legacy_row = {
        "date": "2026-04-28",
        "amount": 4.95,
        "description": "WASIF PERVEZ",
        "category": "Uncategorized",
        "type": "Income",
        "method": "Capital One - 360 Checking (3285)",
    }
    db.upsert_transactions(pd.DataFrame([legacy_row]))

    simplefin_row = {
        **legacy_row,
        "id": "TRN-cf4b5e86-4530-4615-abfb-7eb6b7df70c7",
        "account": "360 Checking (3285)",
        "posted_date": "2026-04-28",
        "raw_data": "{'id': 'TRN-cf4b5e86-4530-4615-abfb-7eb6b7df70c7'}",
    }
    assert db.upsert_transactions(pd.DataFrame([simplefin_row])) == 0
    assert len(db.get_all_transactions()) == 1


def test_simplefin_id_does_not_duplicate_legacy_hash_row_with_amount_format_drift(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    conn = db.get_connection()
    legacy_id = db.generate_legacy_id({
        "date": "2026-01-30",
        "amount": "4.90",
        "description": "OLD PAYMENT",
    })
    conn.execute("""
        INSERT INTO transactions
            (id, date, amount, description, category, type, method, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        legacy_id,
        "2026-01-30",
        4.90,
        "OLD PAYMENT",
        "Restaurants",
        "Expense",
        "Capital One - 360 Checking (3285)",
        "REVIEWED",
    ))
    conn.commit()
    conn.close()

    simplefin_row = {
        "id": "TRN-old-payment",
        "date": "2026-01-30",
        "amount": 4.9,
        "description": "OLD PAYMENT",
        "category": "Uncategorized",
        "type": "Expense",
        "method": "Capital One - 360 Checking (3285)",
        "account": "360 Checking (3285)",
        "posted_date": "2026-01-30",
        "raw_data": "{'id': 'TRN-old-payment'}",
    }
    assert db.upsert_transactions(pd.DataFrame([simplefin_row])) == 0
    assert len(db.get_all_transactions()) == 1


def test_simplefin_legacy_guard_matches_masked_account_suffix(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    legacy_row = {
        "date": "2026-02-03",
        "amount": 500.00,
        "description": "ATM",
        "category": "Misc Expense",
        "type": "Expense",
        "method": "Capital One - 360 Checking",
        "account": "360 Checking",
        "status": "REVIEWED",
    }
    db.upsert_transactions(pd.DataFrame([legacy_row]))

    simplefin_row = {
        **legacy_row,
        "id": "TRN-with-masked-suffix",
        "method": "Capital One - 360 Checking (3285)",
        "account": "360 Checking (3285)",
        "status": "PENDING",
        "posted_date": "2026-02-03",
        "raw_data": "{'id': 'TRN-with-masked-suffix'}",
    }

    assert db.upsert_transactions(pd.DataFrame([simplefin_row])) == 0
    saved = db.get_all_transactions()
    assert len(saved) == 1
    assert saved.iloc[0]["status"] == "REVIEWED"


def test_simplefin_legacy_guard_allows_same_charge_on_different_account(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    legacy_row = {
        "date": "2026-04-28",
        "amount": 19.99,
        "description": "SUBSCRIPTION",
        "category": "Subscriptions",
        "type": "Expense",
        "method": "American Express - Gold Card",
    }
    db.upsert_transactions(pd.DataFrame([legacy_row]))

    simplefin_row = {
        **legacy_row,
        "id": "TRN-distinct-account",
        "method": "Capital One - Quicksilver",
        "account": "Quicksilver (4116)",
        "posted_date": "2026-04-28",
        "raw_data": "{'id': 'TRN-distinct-account'}",
    }
    assert db.upsert_transactions(pd.DataFrame([simplefin_row])) == 1
    assert len(db.get_all_transactions()) == 2


def test_venmo_import_does_not_duplicate_reviewed_row_with_changed_csv_id(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    reviewed_row = {
        "id": "venmo-old-export-id",
        "date": "2026-05-20",
        "amount": 3.30,
        "description": "Venmo - Shabarish Nair / Starbucks",
        "category": "Restaurants",
        "type": "Expense",
        "method": "Venmo",
        "account": "Venmo",
        "status": "REVIEWED",
        "tags": "venmo_import",
    }
    db.upsert_transactions(pd.DataFrame([reviewed_row]))

    fresh_upload_row = {
        **reviewed_row,
        "id": "venmo-new-export-id",
        "status": "PENDING",
        "category": "Uncategorized",
        "details": "Venmo ID: venmo-new-export-id",
    }

    assert db.upsert_transactions(pd.DataFrame([fresh_upload_row])) == 0
    saved = db.get_all_transactions()
    assert len(saved) == 1
    assert saved.iloc[0]["status"] == "REVIEWED"
    assert saved.iloc[0]["category"] == "Restaurants"


def test_venmo_import_does_not_duplicate_reviewed_bank_side_venmo_row(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    reviewed_bank_row = {
        "id": "TRN-bank-venmo-starbucks",
        "date": "2026-05-21",
        "amount": 3.30,
        "description": "VENMO",
        "category": "Fast Food",
        "type": "Expense",
        "method": "Capital One - 360 Checking (3285)",
        "account": "360 Checking (3285)",
        "status": "REVIEWED",
        "user_notes": "starbucks",
    }
    db.upsert_transactions(pd.DataFrame([reviewed_bank_row]))

    venmo_upload_row = {
        "id": "4601433857539888093",
        "date": "2026-05-20",
        "amount": 3.30,
        "description": "Venmo - Shabarish Nair / Starbucks",
        "category": "Uncategorized",
        "type": "Expense",
        "method": "Venmo",
        "account": "Venmo",
        "status": "PENDING",
        "tags": "venmo_import",
    }

    assert db.upsert_transactions(pd.DataFrame([venmo_upload_row])) == 0
    saved = db.get_all_transactions()
    assert len(saved) == 1
    assert saved.iloc[0]["id"] == "TRN-bank-venmo-starbucks"
    assert saved.iloc[0]["status"] == "REVIEWED"


def test_review_transaction_sets_audit_fields(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.upsert_transactions(pd.DataFrame([{
        "id": "tx-review",
        "date": "2026-04-28",
        "amount": 4.95,
        "description": "WASIF PERVEZ",
        "category": "Uncategorized",
        "type": "Income",
        "method": "Capital One - 360 Checking (3285)",
        "status": "PENDING",
    }]))

    db.review_transaction(
        "tx-review",
        "Restaurants",
        "lunch",
        "food",
        "Expense",
        reviewed_by="admin",
        review_source="manual",
    )
    row = db.get_all_transactions().iloc[0]
    assert row["status"] == "REVIEWED"
    assert row["category"] == "Restaurants"
    assert row["reviewed_at"]
    assert row["reviewed_by"] == "admin"
    assert row["review_source"] == "manual"


def test_reviewed_insert_gets_default_audit_fields(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.upsert_transactions(pd.DataFrame([{
        "id": "tx-reviewed",
        "date": "2026-04-28",
        "amount": 100.0,
        "description": "Manual income",
        "category": "Salary",
        "type": "Income",
        "method": "E*Trade - Manual",
        "status": "REVIEWED",
        "reviewed_by": "admin",
        "review_source": "manual_etrade",
    }]))

    row = db.get_all_transactions().iloc[0]
    assert row["reviewed_at"]
    assert row["reviewed_by"] == "admin"
    assert row["review_source"] == "manual_etrade"


def test_balance_freshness_tracks_current_unchanged_streak(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    conn = db.get_connection()
    c = conn.cursor()
    for date in ("2026-03-01", "2026-04-01", "2026-04-29"):
        c.execute("""
            INSERT INTO balance_history (date, bank, account, balance, classification)
            VALUES (?, ?, ?, ?, ?)
        """, (date, "Fidelity Investments", "Brokerage Health Savings (6355)", 169.23, "Retirement / Restricted"))
    c.execute("""
        INSERT INTO balance_history (date, bank, account, balance, classification)
        VALUES (?, ?, ?, ?, ?)
    """, ("2026-02-01", "Fidelity Investments", "Brokerage Health Savings (6355)", 100.00, "Retirement / Restricted"))
    conn.commit()
    conn.close()

    freshness = db.get_balance_freshness(as_of_date="2026-04-29")
    row = freshness.iloc[0]
    assert row["balance_unchanged_since"] == "2026-03-01"
    assert row["days_balance_unchanged"] == 59


def test_balance_snapshot_upserts_without_erasing_other_accounts(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.save_balance_snapshot(pd.DataFrame([
        {
            "Bank": "Capital One",
            "Account": "360 Checking (3285)",
            "Balance": 100.0,
            "Classification": "Cash",
        },
        {
            "Bank": "Fidelity Investments",
            "Account": "Self-Directed Brokerage (3743)",
            "Balance": 500.0,
            "Classification": "Taxable Investments",
        },
    ]))
    db.save_balance_snapshot(pd.DataFrame([
        {
            "Bank": "Capital One",
            "Account": "360 Checking (3285)",
            "Balance": 150.0,
            "Classification": "Cash",
        },
    ]))

    history = db.get_balance_history_details()
    assert set(history["account"]) == {"360 Checking (3285)", "Self-Directed Brokerage (3743)"}
    checking = history[history["account"] == "360 Checking (3285)"].iloc[0]
    brokerage = history[history["account"] == "Self-Directed Brokerage (3743)"].iloc[0]
    assert checking["balance"] == 150.0
    assert brokerage["balance"] == 500.0


def test_balance_snapshot_replace_mode_removes_missing_accounts(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.save_balance_snapshot(pd.DataFrame([
        {
            "Bank": "Capital One",
            "Account": "360 Checking (3285)",
            "Balance": 100.0,
            "Classification": "Cash",
        },
        {
            "Bank": "Closed Bank",
            "Account": "Old Account",
            "Balance": 25.0,
            "Classification": "Cash",
        },
    ]))
    db.save_balance_snapshot(pd.DataFrame([
        {
            "Bank": "Capital One",
            "Account": "360 Checking (3285)",
            "Balance": 150.0,
            "Classification": "Cash",
        },
    ]), replace_for_today=True)

    history = db.get_balance_history_details()
    assert set(history["account"]) == {"360 Checking (3285)"}
    assert history.iloc[0]["balance"] == 150.0
    latest = db.get_latest_balance_snapshot()
    assert set(latest["account"]) == {"360 Checking (3285)"}


def test_empty_balance_snapshot_replace_mode_clears_today(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.save_balance_snapshot(pd.DataFrame([
        {
            "Bank": "Capital One",
            "Account": "360 Checking (3285)",
            "Balance": 100.0,
            "Classification": "Cash",
        },
    ]))
    db.save_balance_snapshot(pd.DataFrame(), replace_for_today=True)

    assert db.get_balance_history_details().empty
    latest_run = db.get_latest_balance_snapshot_run()
    assert latest_run.iloc[0]["account_count"] == 0
    assert db.get_latest_balance_snapshot().empty


def test_latest_balance_context_reports_balance_count(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.save_balance_snapshot(pd.DataFrame([
        {
            "Bank": "Capital One",
            "Account": "360 Checking (3285)",
            "Balance": 100.0,
            "Classification": "Cash",
        },
    ]), replace_for_today=True)
    db.save_sync_report({
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "status": "success",
        "transactions_seen": 0,
        "transactions_inserted": 0,
        "duplicates": 0,
        "balance_accounts_seen": 1,
        "accounts": [],
    })

    context = db.get_latest_balance_context()

    assert context["has_successful_sync"] is True
    assert context["latest_sync_returned_no_balances"] is False
    assert context["balance_accounts_seen"] == 1
    assert len(context["balances"]) == 1


def test_account_rules_roundtrip(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)

    saved = db.upsert_account_rules([{
        "bank": "Fidelity Investments",
        "account": "Self-Directed Brokerage (3743)",
        "classification": "Retirement / Restricted",
        "include_in_inbox": False,
        "include_in_net_worth": True,
        "notes": "Retirement account",
    }])

    assert saved == 1
    rules = db.get_account_rules()
    assert len(rules) == 1
    row = rules.iloc[0]
    assert row["classification"] == "Retirement / Restricted"
    assert bool(row["include_in_inbox"]) is False
    assert bool(row["include_in_net_worth"]) is True
