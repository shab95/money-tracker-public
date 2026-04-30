import pandas as pd

from conftest import reload_db


def test_backfill_transaction_fields_dry_run_and_apply(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    import data_repair

    raw_data = {
        "date": "2026-04-28",
        "description": "WASIF PERVEZ",
        "amount": 4.95,
        "method": "Capital One - 360 Checking (3285)",
        "account": "360 Checking (3285)",
        "posted_date": "2026-04-28",
        "details": "memo",
    }
    db.upsert_transactions(pd.DataFrame([{
        "id": "tx-1",
        "date": "2026-04-28",
        "amount": 4.95,
        "description": "WASIF PERVEZ",
        "method": "Capital One - 360 Checking (3285)",
        "raw_data": str(raw_data),
    }]))

    dry_run = data_repair.backfill_transaction_fields(apply=False)
    assert dry_run["recoverable_rows"] == 1
    assert db.get_all_transactions().iloc[0]["account"] is None

    applied = data_repair.backfill_transaction_fields(apply=True)
    assert applied["recoverable_rows"] == 1
    assert db.get_all_transactions().iloc[0]["account"] == "360 Checking (3285)"
