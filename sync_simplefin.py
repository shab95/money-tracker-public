import base64
import requests
import pandas as pd
import os
from datetime import datetime, timedelta
import account_classifier
import config
import db
import ml_utils

# ---------------------------------------------------------
# Secrets Management
# ---------------------------------------------------------
SIMPLEFIN_SETUP_TOKEN = ""
SIMPLEFIN_ACCESS_URL = ""

# 1. Try Streamlit Secrets (Cloud)
try:
    import streamlit as st
    if hasattr(st, 'secrets'):
        SIMPLEFIN_SETUP_TOKEN = st.secrets.get("SIMPLEFIN_SETUP_TOKEN", "")
        SIMPLEFIN_ACCESS_URL = st.secrets.get("SIMPLEFIN_ACCESS_URL", "")
except Exception:
    pass

# 2. Try Local Secrets (app_secrets.py) - Overrides if present
try:
    import app_secrets as secrets
    if getattr(secrets, 'SIMPLEFIN_SETUP_TOKEN', None):
        SIMPLEFIN_SETUP_TOKEN = secrets.SIMPLEFIN_SETUP_TOKEN
    if getattr(secrets, 'SIMPLEFIN_ACCESS_URL', None):
        SIMPLEFIN_ACCESS_URL = secrets.SIMPLEFIN_ACCESS_URL
except ImportError:
    if not SIMPLEFIN_ACCESS_URL:
        print("⚠️  'app_secrets.py' not found and no Cloud secrets detected.")

def claim_access_url(setup_token):
    try:
        decoded = base64.b64decode(setup_token).decode('utf-8')
        claim_url = decoded
        print(f"Claiming access from: {claim_url}")
        res = requests.post(claim_url)
        res.raise_for_status()
        return res.text 
    except Exception as e:
        print(f"Error claiming token: {e}")
        return None

def fetch_data(access_url, start_date=None, end_date=None):
    print(f"Fetching account data (Date Range: {start_date} to {end_date})...")
    params = {}
    if start_date:
        dt = pd.to_datetime(start_date)
        params['start-date'] = int(dt.timestamp())
        
    if end_date:
        dt = pd.to_datetime(end_date)
        params['end-date'] = int(dt.timestamp())
        
    res = requests.get(access_url + "/accounts", params=params)
    res.raise_for_status()
    return res.json()


def find_duplicate_connection_reasons(accounts):
    fidelity_seen = {}
    duplicate_reasons = {}
    for account in accounts:
        bank_name = account.get('org', {}).get('name', 'Unknown Bank')
        account_name = account.get('name', 'Unknown Acct')
        if bank_name not in ("Fidelity Investments", "Fidelity 401k"):
            continue

        key = account_classifier.normalize_account_name(account_name)
        if key not in fidelity_seen:
            fidelity_seen[key] = (bank_name, account_name)
            continue

        previous_bank, previous_account = fidelity_seen[key]
        if previous_bank == "Fidelity Investments" and bank_name == "Fidelity 401k":
            duplicate_reasons[(bank_name, account_name)] = "duplicate_connection_prefer_fidelity_investments"
        elif previous_bank == "Fidelity 401k" and bank_name == "Fidelity Investments":
            duplicate_reasons[(previous_bank, previous_account)] = "duplicate_connection_prefer_fidelity_investments"
            fidelity_seen[key] = (bank_name, account_name)
    return duplicate_reasons


def get_sync_date_range(now=None):
    now = now or datetime.now()
    end_date = now.strftime('%Y-%m-%d')
    configured_start = os.getenv("MONEY_TRACKER_SIMPLEFIN_START_DATE", "").strip()
    if configured_start:
        return configured_start, end_date
    lookback_days = int(
        os.getenv(
            "MONEY_TRACKER_SYNC_DAYS",
            os.getenv("MONEY_TRACKER_LOCAL_SYNC_DAYS", "30"),
        )
    )
    return (now - timedelta(days=lookback_days)).strftime('%Y-%m-%d'), end_date


def transaction_date_from_timestamp(timestamp_value):
    if not timestamp_value:
        return ""
    try:
        return datetime.fromtimestamp(timestamp_value).strftime('%Y-%m-%d')
    except Exception:
        return ""


def get_latest_transaction_date(transactions):
    dates = [transaction_date_from_timestamp(tx.get('posted')) for tx in transactions]
    dates = [value for value in dates if value]
    return max(dates) if dates else ""


def coerce_balance(balance):
    try:
        return float(balance) if balance not in (None, "") else None
    except (TypeError, ValueError):
        return None


def build_balance_snapshot_rows(accounts, duplicate_reasons, rules_map=None):
    rows = []
    for account in accounts:
        bank_name = account.get('org', {}).get('name', 'Unknown Bank')
        account_name = account.get('name', 'Unknown Acct')
        if duplicate_reasons.get((bank_name, account_name), ""):
            continue
        rule = account_classifier.get_account_rule(rules_map, bank_name, account_name)
        include_in_net_worth = account_classifier.optional_bool(rule.get("include_in_net_worth"))
        if include_in_net_worth is False:
            continue

        balance = coerce_balance(account.get('balance'))
        if balance is None:
            continue

        rows.append({
            "Bank": bank_name,
            "Account": account_name,
            "Balance": balance,
            "Classification": account_classifier.classify_account(bank_name, account_name, balance, rule=rule),
        })
    return rows


def get_account_health_status(included, skip_reason, transaction_count, latest_transaction_date, balance=None):
    if skip_reason.startswith("duplicate_connection"):
        return "Duplicate"
    if balance is not None or transaction_count > 0:
        if transaction_count > 0:
            return "Healthy"
        return "Healthy, no activity"
    if transaction_count > 0:
        return "Healthy"
    return "Needs review"


def sync():
    report = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "status": "running",
        "accounts": [],
        "transactions_seen": 0,
        "transactions_inserted": 0,
        "duplicates": 0,
        "balance_accounts_seen": 0,
        "error": "",
    }

    # 1. Auth Logic
    access_url = SIMPLEFIN_ACCESS_URL
    if not access_url and SIMPLEFIN_SETUP_TOKEN:
        print("Obtaining new Access URL...")
        access_url = claim_access_url(SIMPLEFIN_SETUP_TOKEN)
        print(f"IMPORTANT: Please update app_secrets.py with:\nSIMPLEFIN_ACCESS_URL = '{access_url}'")
    
    if not access_url:
        msg = "Authorization failed. Check tokens."
        print(f"❌ {msg}")
        report["status"] = "failed"
        report["error"] = msg
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        db.save_sync_report(report)
        return report

    # 2. Fetch data. Production keeps the broad backfill window; local uses a
    # shorter window so a fresh SQLite database does not reopen months of work.
    start_date, end_date = get_sync_date_range()
    report["sync_start_date"] = start_date
    report["sync_end_date"] = end_date
    
    try:
        json_data = fetch_data(access_url, start_date=start_date, end_date=end_date)
    except Exception as e:
        msg = f"Error fetching from SimpleFin: {e}"
        print(msg)
        report["status"] = "failed"
        report["error"] = msg
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        db.save_sync_report(report)
        return report

    # 3. Process & Normalize
    accounts = json_data.get('accounts', [])
    rules_map = account_classifier.rules_to_map(db.get_account_rules())
    duplicate_reasons = find_duplicate_connection_reasons(accounts)
    balance_snapshot_rows = build_balance_snapshot_rows(accounts, duplicate_reasons, rules_map)
    report["balance_accounts_seen"] = len(balance_snapshot_rows)
    for account in accounts:
        bank_name = account.get('org', {}).get('name', 'Unknown Bank')
        account_name = account.get('name', 'Unknown Acct')
        txs = account.get('transactions', [])
        duplicate_reason = duplicate_reasons.get((bank_name, account_name), "")
        if duplicate_reason:
            include_account, skip_reason = False, duplicate_reason
        else:
            rule = account_classifier.get_account_rule(rules_map, bank_name, account_name)
            include_account, skip_reason = account_classifier.should_sync_transactions(bank_name, account_name, rule=rule)
        latest_transaction_date = get_latest_transaction_date(txs)
        balance = coerce_balance(account.get('balance'))
        account_report = {
            "bank": bank_name,
            "account": account_name,
            "included": include_account,
            "skip_reason": skip_reason,
            "transaction_count": len(txs),
            "inserted_count": 0,
            "duplicate_count": 0,
            "latest_transaction_date": latest_transaction_date,
            "balance": balance,
            "currency": account.get('currency', ''),
            "health_status": get_account_health_status(
                include_account,
                skip_reason,
                len(txs),
                latest_transaction_date,
                balance,
            ),
            "error": "",
        }

        if not include_account:
            report["accounts"].append(account_report)
            continue

        account_txs = []
        for tx in txs:

            # E*Trade Specific Filtering
            # User wants Salary/RSU but NOT Dividends/Reinvestments
            if "E*Trade" in bank_name:
                desc_upper = (tx.get('description') or "").upper()
                if "DIVIDEND" in desc_upper or "REINVESTMENT" in desc_upper:
                    # print(f"   Skipping E*Trade Dividend/Reinvestment: {desc_upper}")
                    continue

            # Raw amount handling
            raw_amt = float(tx.get('amount', 0))
            
            # --- ML PREDICTION ---
            description = tx.get('description') or tx.get('memo') or 'No Desc'
            
            # Predict Category and Type
            # We pass raw_amt (signed) because Type depends on sign.
            pred = ml_utils.classifier.predict(description, raw_amt)
            
            # Use Prediction
            category = pred.get('category', 'Uncategorized')
            tx_type = pred.get('type', 'Expense') # Default handled by predictor usually
            confidence = pred.get('confidence', 0.0)
            
            # Force absolute amount for storage
            amount = abs(raw_amt)
            
            # Add "🤖" to notes if confidence is low? 
            # Or just log it. Let's add it to user_notes if uncertain.
            user_notes = ""
            if not pred.get('model_available'):
                user_notes = "ML model not trained"
            elif confidence < 0.6:
                user_notes = f"🤖 Low Confidence ({int(confidence*100)}%)"

            date_str = transaction_date_from_timestamp(tx.get('posted'))
            if not date_str:
                account_report["error"] = "transaction_missing_posted_date"
                continue
            
            account_txs.append({
                'id': tx.get('id'),
                'date': date_str,
                'description': description,
                'amount': amount,
                'category': category, 
                'type': tx_type,
                'method': f"{bank_name} - {account_name}",
                'account': account_name,
                'posted_date': date_str,
                'details': tx.get('memo', ''),
                'status': 'PENDING',
                'user_notes': user_notes,
                'raw_data': str(tx),
                'ml_confidence': float(confidence),
                'ml_category_confidence': float(pred.get('cat_confidence', 0.0)),
                'ml_type_confidence': float(pred.get('type_confidence', 0.0)),
            })

        if account_txs:
            df = pd.DataFrame(account_txs)
            added_count = db.upsert_transactions(df)
            account_report["inserted_count"] = added_count
            account_report["duplicate_count"] = max(len(account_txs) - added_count, 0)
            report["transactions_seen"] += len(account_txs)
            report["transactions_inserted"] += added_count
            report["duplicates"] += account_report["duplicate_count"]
        report["accounts"].append(account_report)

    # 4. Save report
    if report["transactions_seen"]:
        print(f"✅ Sync Complete. Processed {report['transactions_seen']} transactions.")
        print(f"📥 Added {report['transactions_inserted']} NEW transactions to the Inbox.")
    else:
        print("No transactions found.")
    report["status"] = "success"
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    db.save_balance_snapshot(pd.DataFrame(balance_snapshot_rows), replace_for_today=True)
    db.save_sync_report(report)
    return report

if __name__ == "__main__":
    sync()
