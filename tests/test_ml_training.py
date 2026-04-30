import importlib

import pandas as pd

from conftest import reload_db


def reload_ml(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    import ml_utils

    return importlib.reload(ml_utils)


def test_training_skips_pending_predictions(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.upsert_transactions(pd.DataFrame([{
        "id": f"pending-{idx}",
        "date": "2026-04-28",
        "amount": 10 + idx,
        "description": f"PENDING GUESS {idx}",
        "category": "Restaurants",
        "type": "Expense",
        "method": "SimpleFIN",
        "status": "PENDING",
    } for idx in range(12)]))

    ml_utils = reload_ml(monkeypatch, tmp_path)
    report = ml_utils.classifier.train()

    assert report["status"] == "skipped"
    assert report["reviewed_samples"] == 0
    assert "No reviewed transactions to train on." in report["warnings"]


def test_training_uses_reviewed_rows(monkeypatch, tmp_path):
    db = reload_db(monkeypatch, tmp_path)
    db.upsert_transactions(pd.DataFrame([{
        "id": f"reviewed-{idx}",
        "date": "2026-04-28",
        "amount": 10 + idx,
        "description": f"REVIEWED RESTAURANT {idx}",
        "category": "Restaurants",
        "type": "Expense",
        "method": "SimpleFIN",
        "status": "REVIEWED",
        "reviewed_by": "admin",
        "review_source": "manual",
    } for idx in range(12)]))

    ml_utils = reload_ml(monkeypatch, tmp_path)
    report = ml_utils.classifier.train()

    assert report["status"] == "success"
    assert report["reviewed_samples"] == 12
    assert report["category_model"] == "trained"
