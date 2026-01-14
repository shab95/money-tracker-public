import base64
import requests
import pandas as pd
import os
from datetime import datetime, timedelta
import db

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

def sync():
    # 1. Auth Logic
    access_url = SIMPLEFIN_ACCESS_URL
    if not access_url and SIMPLEFIN_SETUP_TOKEN:
        print("Obtaining new Access URL...")
        access_url = claim_access_url(SIMPLEFIN_SETUP_TOKEN)
        print(f"IMPORTANT: Please update app_secrets.py with:\nSIMPLEFIN_ACCESS_URL = '{access_url}'")
    
    if not access_url:
        print("❌ Authorization failed. Check tokens.")
        return

    # 2. Fetch from December 1st, 2025 (Fixed Start)
    # Reverted 90-day logic per user request to avoid duplicate/old data.
    end_dt = datetime.now()
    start_date = '2025-12-01'
    end_date = end_dt.strftime('%Y-%m-%d')
    
    try:
        json_data = fetch_data(access_url, start_date=start_date, end_date=end_date)
    except Exception as e:
        print(f"Error fetching from SimpleFin: {e}")
        return

    # 3. Process & Normalize
    all_txs = []
    
    for account in json_data.get('accounts', []):
        bank_name = account.get('org', {}).get('name', 'Unknown Bank')
        account_name = account.get('name', 'Unknown Acct')
        
        for tx in account.get('transactions', []):
            # NOISE FILTER: Skip transactions from Locked/Investment Accounts
            # We track their balances in the Net Worth tab, but we don't need their internal noise in the Inbox.
            # User Rule: "Only credit cards and checking accounts"
            # Strategy: Exclude known investment keywords from Account Name OR Bank Name.
            
            SKIP_KEYWORDS = [
                "401K", "401k",
                "Brokerage", "brokerage",
                "IRA", "ira",
                "Investment", "investment",
                "Stock Plan", "stock plan",
                "Crypto", "crypto",
                "Savings", "savings" # If user wants to exclude savings too? User said "savings accounts i cant touch until 60" about some, but usually savings account interest is income. 
                # User's specifics: "fidelity: CAPITAL ONE 401K", "SimpleFin", "E*Trade"
            ]
            
            # Specific Account Names to Skip (User Specified)
            SKIP_EXACT = [
                "CAPITAL ONE 401K ASP",
                "Self-Directed Brokerage",
                "Robinhood Roth IRA",
                "Robinhood managed Roth IRA",
                "Robinhood managed individual",
                "Robinhood individual",
                "Crypto",
                "Brokerage Health Savings",
                "Brokerage General Investing Person",
                "Stock Plan",
                "Individual Brokerage"
            ]
            
            # Check if we should skip
            should_skip = False
            
            # Check 1: Keywords in Name
            if any(k in account_name for k in SKIP_KEYWORDS):
                should_skip = True
                
            # Check 2: Exact list
            if any(exact in account_name for exact in SKIP_EXACT):
                should_skip = True
                
            # Check 3: Check Bank Name for "E*Trade" or "Robinhood" or "Fidelity"
            # User update: Wants to track "E*Trade" because Salary/RSU hits there.
            # We keep blocking Robinhood/Fidelity if not requested.
            
            if "Robinhood" in bank_name:
                should_skip = True
                
            if "E*Trade" in bank_name:
               should_skip = True
            
            # Special Exception: If it's E*Trade, we might want to Ignore "Stock Plan" keyword block above?
            # The keyword block runs first.
            if "E*Trade" in bank_name and should_skip:
                # If it was skipped purely due to keywords like "Stock Plan" or "Brokerage", un-skip it?
                # But maybe "Stock Plan" is just shares, not cash? 
                # Let's assume user wants to see it.
                should_skip = False
                
            if should_skip:
                # print(f"   Skipping {bank_name} - {account_name}")
                continue

            # E*Trade Specific Filtering
            # User wants Salary/RSU but NOT Dividends/Reinvestments
            if "E*Trade" in bank_name:
                desc_upper = (tx.get('description') or "").upper()
                if "DIVIDEND" in desc_upper or "REINVESTMENT" in desc_upper:
                    # print(f"   Skipping E*Trade Dividend/Reinvestment: {desc_upper}")
                    continue

            raw_amt = float(tx.get('amount', 0))
            
            # Normalization Logic
            # SimpleFin: usually negative = expense, positive = income
            # App Convention: Amount always positive. Type determines sign.
            
            if raw_amt < 0:
                amount = abs(raw_amt)
                tx_type = 'Expense'
            else:
                amount = raw_amt
                tx_type = 'Income'
                
            raw_date_ts = tx.get('posted')
            date_str = datetime.fromtimestamp(raw_date_ts).strftime('%Y-%m-%d')
            
            all_txs.append({
                'date': date_str,
                'description': tx.get('description') or tx.get('memo') or 'No Desc',
                'amount': amount,
                'category': 'Uncategorized', 
                'type': tx_type,
                'method': f"{bank_name} - {account_name}",
                'account': account_name,
                'posted_date': date_str,
                'details': tx.get('memo', ''),
                'status': 'PENDING',
                'raw_data': str(tx)
            })
            
    # 4. Save to DB
    if all_txs:
        df = pd.DataFrame(all_txs)
        added_count = db.upsert_transactions(df)
        print(f"✅ Sync Complete. Processed {len(all_txs)} transactions.")
        print(f"📥 Added {added_count} NEW transactions to the Inbox.")
    else:
        print("No transactions found.")

if __name__ == "__main__":
    sync()
