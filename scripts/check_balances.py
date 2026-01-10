import requests
import pandas as pd
from datetime import datetime
import sys

try:
    import app_secrets as secrets
    SIMPLEFIN_ACCESS_URL = getattr(secrets, 'SIMPLEFIN_ACCESS_URL', "")
except ImportError:
    SIMPLEFIN_ACCESS_URL = ""
    print("❌ 'app_secrets.py' not found.")
    sys.exit(1)

def check_balances():
    if not SIMPLEFIN_ACCESS_URL:
        print("❌ Authorization missing. Check app_secrets.py.")
        return

    print("🔎 Fetching Account Balances via SimpleFin...")
    
    # We fetch accounts. We don't need a date range for balances, usually returns current state.
    try:
        res = requests.get(SIMPLEFIN_ACCESS_URL + "/accounts")
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return

    accounts = data.get('accounts', [])
    print(f"✅ Found {len(accounts)} accounts.\n")
    
    # Create a nice list
    # Fields: org.name, name, type, balance, currency, available-balance
    
    row_data = []
    
    total_net_worth = 0.0
    
    for acct in accounts:
        bank = acct.get('org', {}).get('name', 'Unknown Bank')
        name = acct.get('name', 'Unknown Acct')
        
        # User Logic: "Fidelity 401k" is often a duplicate of "Fidelity Investments".
        # Hide it to prevent double counting.
        if bank == "Fidelity 401k":
            continue
            
        # Balance is usually a string "123.45"
        bal_str = acct.get('balance', '0')
        currency = acct.get('currency', 'USD')
        
        try:
            balance = float(bal_str)
        except:
            balance = 0.0
            
        # In SimpleFin (and often API standards):
        # Credit Card Positive Balance = Debt? Or Negative?
        # Usually: 
        # Checking/Savings Positive = Asset
        # Credit Card Positive = Debt (Liability)
        
        # Let's just print raw first.
        
        row_data.append({
            "Bank": bank,
            "Account": name,
            "Balance": balance,
            "Currency": currency
        })
        
        # Naive Net Worth Sum (assuming standard sign convention)
        # Checking with simplefin docs: "Balances are signed such that a positive number is an asset and a negative number is a liability."
        # WAIT. Some APIs do "Credit Card Balance: $500" (meaning debt). 
        # SimpleFin typically normalizes. Start with raw summation.
        total_net_worth += balance

    if row_data:
        df = pd.DataFrame(row_data)
        # Sort by Bank
        df = df.sort_values(by=['Bank', 'Account'])
        
        # Save to DB for History
        import db
        db.save_balance_snapshot(df)
        print("✅ Saved snapshot to History DB.")
        
        # Format for display
        print(df.to_string(index=False, formatters={'Balance': '${:,.2f}'.format}))
        print("-" * 50)
        print(f"💰 Total Net Worth (Est): ${total_net_worth:,.2f}")
    else:
        print("No accounts returned.")

if __name__ == "__main__":
    check_balances()
