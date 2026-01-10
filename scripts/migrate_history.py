import pandas as pd
import db
import os

HISTORY_FILE = 'money_wrapped_2024/raw_data/final_data.csv'

def migrate():
    print(f"Reading history from {HISTORY_FILE}...")
    try:
        df = pd.read_csv(HISTORY_FILE)
    except FileNotFoundError:
        print("❌ Historical file not found.")
        return

    # Map columns to DB schema
    # DB: date, amount, description, category, type, method, status, user_notes, tags
    
    # Clean/Normalize Data
    migrated_txs = []
    
    for _, row in df.iterrows():
        # Handle Amount/Type logic
        # Historical: Amount is signed (+ Income, - Expense). 
        # New DB: Amount is magnitude (positive). Type determines sign.
        # Wait, let's check db.py schema. 
        # DB schema is flexible but sync_simplefin stores amount as Positive.
        
        raw_amt = float(row['Amount'])
        tx_type = row['Type']
        category = row['Category']

        # Handle 'Paid Back' mapping
        if category == 'Paid Back':
            if raw_amt < 0:
                category = 'Restaurants' # User request: Negative Paid Back -> Restaurants
            else:
                category = 'Pass-Through (Reimbursed)'

        # Ensure 'Type' matches new conventions if needed
        # Old Types: Expense, Income, Reimbursement, Investment?
        # New Categories: Interest Income (Type=Income), Rewards (Type=Income)
        
        # Logic: 
        # If type is Expense/Reimbursement -> Amount positive
        # If type is Income -> Amount positive
        
        # Actually, let's keep it simple: Absolute value for amount.
        amount = abs(raw_amt)
        
        # Map Type
        # If raw_amt > 0 -> likely Income or Refund
        # If raw_amt < 0 -> Expense
        # We trust the 'Type' column from the cleaned history mostly.
        
        migrated_txs.append({
            'date': row['Date'],
            'amount': amount,
            'description': row['Description'],
            'category': category,
            'type': tx_type,
            'method': row['Method'],
            'status': 'REVIEWED', # History is considered reviewed
            'user_notes': row['User Description'],
            'tags': '', # No tags in old data
            'raw_data': '{"source": "migration_v1"}' 
        })
        
    if migrated_txs:
        new_df = pd.DataFrame(migrated_txs)
        print(f"Migrating {len(new_df)} transactions...")
        count = db.upsert_transactions(new_df)
        print(f"✅ Successfully added {count} historical transactions to tracker.db!")
    else:
        print("No transactions to migrate.")

if __name__ == "__main__":
    migrate()
