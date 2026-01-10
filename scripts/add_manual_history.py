import pandas as pd
import sys
import os

# Add parent dir to path to import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

def add_manual_etrade():
    print("📝 Preparing to add manual E*Trade history from raw data...")
    
    # Raw Data provided by user
    # Date, Price, Qty
    raw_data = [
        # ("MM/DD/YYYY", Price, Qty),
    ]
    
    txs = []
    total_income = 0
    
    for date_str, price, qty in raw_data:
        # User Instruction: Date, Purchase Price, Purchased Qty (Ignore others)
        # Assuming Income Amount = Purchase Price * Quantity (The cash value)
        amount = round(price * qty, 2)
        total_income += amount
        
        # Convert date MM/DD/YYYY -> YYYY-MM-DD
        dt = pd.to_datetime(date_str)
        fmt_date = dt.strftime('%Y-%m-%d')
        
        txs.append({
            'date': fmt_date,
            'amount': amount,
            'description': f"E*Trade Income (Manual: {qty} @ ${price})",
            'category': 'Paycheck', # Better default than Uncategorized
            'type': 'Income',
            'method': 'E*Trade - Manual',
            'account': 'E*Trade',
            'posted_date': fmt_date,
            'details': f"Manual Entry: Price ${price} * Qty {qty}",
            'status': 'PENDING',
            'raw_data': '{}',
            'user_notes': 'Historical Salary/RSU/ESPP'
        })
        
    df = pd.DataFrame(txs)
    print(f"Adding {len(df)} transactions totaling ${total_income:,.2f}...")
    
    count = db.upsert_transactions(df)
    print(f"✅ Successfully added {count} transactions to Inbox.")

if __name__ == "__main__":
    add_manual_etrade()
