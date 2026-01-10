import os
import pandas as pd
from datetime import datetime
import db
import glob

DOWNLOAD_DIR = "raw_data/venmo_exports"

def sync():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        print(f"📁 Created directory: {DOWNLOAD_DIR}")
        print("� Please download your Venmo CSV and place it here!")
        return

    # Find all CSVs in the folder
    csv_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv"))
    
    if not csv_files:
        print(f"❌ No CSV files found in {DOWNLOAD_DIR}")
        print("👉 Go to: https://account.venmo.com/api/statement/download?startDate=2025-12-01&endDate=2026-01-04&csv=true")
        print("   (Adjust dates as needed, then save the file to the folder above)")
        return

    print(f"📂 Found {len(csv_files)} CSV files. Processing...")
    
    total_new = 0
    for filepath in csv_files:
        total_new += process_venmo_csv(filepath)
        
    print(f"🎉 Done! Total new Venmo transactions imported: {total_new}")

def process_venmo_csv(filepath):
    print(f"   Processing {os.path.basename(filepath)}...")
    try:
        # Venmo CSVs often have garbage at top.
        # Based on user file:
        # Line 1: Account Statement
        # Line 2: Account Activity
        # Line 3: ,ID,Datetime... (Header)
        # Line 4: Balance info
        
        # We try reading with header=2 (0-indexed, so 3rd line)
        df = pd.read_csv(filepath, header=2)
        
        # Validation: check for 'Datetime' column
        if 'Datetime' not in df.columns:
            # Fallback
            print("   ⚠️ Header not found at row 2, scanning...")
            df = pd.read_csv(filepath, header=3)
            # If still fails, maybe header=1?
             
    except Exception as e:
        print(f"   ❌ Error reading CSV: {e}")
        return 0

    new_txs = []
    
    for _, row in df.iterrows():
        # Clean up rows that are just balance checks or footers
        if pd.isna(row.get('Datetime')):
            continue
            
        # Skip if not complete
        status = row.get('Status')
        if pd.isna(status) or status != 'Complete':
            continue
            
        # Date
        raw_date = row.get('Datetime', '')
        try:
            dt = pd.to_datetime(raw_date)
            date_str = dt.strftime('%Y-%m-%d')
        except:
            continue 

        # Amount
        # Format: "- $42.38" or "+ $104.00"
        # We remove '$', ',', ' ' (spaces)
        raw_amt_str = str(row.get('Amount (total)', '0')).replace('$','').replace(',','').replace(' ','')
        try:
            raw_amt = float(raw_amt_str)
        except:
            continue
        amount = abs(raw_amt)
        
        # Categorization Logic
        note = str(row.get('Note', ''))
        to_user = row.get('To', 'Unknown')
        from_user = row.get('From', 'Unknown')
        type_str = row.get('Type', '')
        
        desc = f"Venmo - {to_user} / {from_user}"
        
        # Determine Direction & Category
        if 'Transfer' in type_str:
            category = 'Transfer'
            tx_type = 'Transfer'
        elif raw_amt < 0:
            # Money OUT (Payment)
            tx_type = 'Expense'
            category = 'Uncategorized' 
        else:
             # Money IN (Request/Return)
             # User requested this be 'Reimbursement' by default to offset expenses
            tx_type = 'Reimbursement' 
            category = None # Blank

        new_txs.append({
            'date': date_str,
            'description': desc,
            'amount': amount,
            'category': category,
            'type': tx_type,
            'method': 'Venmo',
            'status': 'PENDING',
            'user_notes': note,
            'tags': 'venmo_import',
            'raw_data': str(row.to_dict())
        })
        
    if new_txs:
        db_df = pd.DataFrame(new_txs)
        count = db.upsert_transactions(db_df)
        print(f"   -> Added {count} new transactions.")
        return count
    else:
        print("   -> No valid transactions found.")
        return 0

if __name__ == "__main__":
    sync()
