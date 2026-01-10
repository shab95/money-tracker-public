import sys
import os
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

FILE_PATH = "Financial Statements/Venmo/VenmoStatement_Dec_2025_Jan_2026 (1).csv"

def import_venmo():
    print(f"📥 Importing {FILE_PATH}...")
    
    if not os.path.exists(FILE_PATH):
        print("❌ File not found.")
        return

    try:
        # 1. Read CSV (Skip row 1-2, Header at 3)
        # Wait, user's previous file had header at row 3 (index 2).
        # Let's assume consistent format.
        df = pd.read_csv(FILE_PATH, header=2)
        df.columns = df.columns.str.strip()
        
        if 'ID' not in df.columns:
            print("❌ 'ID' column not found. Header format mismatch?")
            print(f"Columns found: {df.columns.tolist()}")
            # Fallback: maybe header is at index 0 or 1?
            return
            
        processed_txs = []
        
        for _, row in df.iterrows():
            if pd.isna(row['ID']):
                continue
                
            v_id = str(row['ID'])
            v_date = pd.to_datetime(row['Datetime']).strftime('%Y-%m-%d')
            
            # Amount
            raw_amt_str = str(row['Amount (total)']).replace('$', '').replace(',', '').replace(' ', '')
            is_positive = '+' in raw_amt_str or (not '-' in raw_amt_str and float(raw_amt_str) > 0)
            clean_amt = float(raw_amt_str.replace('+', '').replace('-', ''))
            
            # Formatting (Per Request)
            desc = f"Venmo - {row['From']} / {row['To']}"
            user_note = row['Note'] if not pd.isna(row['Note']) else ""
            
            # Type Logic
            tx_type = 'Expense'
            category = 'Uncategorized'
            v_type = row['Type']
            
            if v_type == 'Standard Transfer':
                tx_type = 'Transfer'
                category = 'Transfer'
            elif is_positive:
                tx_type = 'Reimbursement'
            else:
                tx_type = 'Expense'

            processed_txs.append({
                'id': v_id,
                'date': v_date,
                'amount': abs(clean_amt),
                'description': desc,
                'category': category,
                'type': tx_type,
                'method': 'Venmo',
                'tags': 'venmo_import',
                'user_notes': user_note,
                'status': 'PENDING',
                'raw_data': str(row.to_dict()),
                'account': 'Venmo',
                'posted_date': v_date,
                'details': f"Statement Period: {row.get('Statement Period Venmo Fees', '')}"
            })
            
        if processed_txs:
            new_df = pd.DataFrame(processed_txs)
            count = db.upsert_transactions(new_df)
            print(f"✅ Imported {count} Venmo transactions.")
        else:
            print("⚠️ No valid transactions found.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    import_venmo()
