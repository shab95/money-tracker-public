
import db
import pandas as pd

def restore_txs():
    # Data from previous logs (Step 156)
    # 1. 8c8281698b9a76c1b6812c5b909269d9 | 1797.24
    # 2. 57e874aa0e7cc50258b0238911952146 | 1676.48
    
    # We reconstruct the rows as best as we can.
    # Note: 'raw_data' strings are in the logs too.
    
    tx1 = {
        'id': '8c8281698b9a76c1b6812c5b909269d9',
        'date': '2025-12-31',
        'amount': 1797.24,
        'description': 'Purchase Date Est. Market Val. info_outline Purchase Price',
        'category': 'Uncategorized',
        'type': 'Income',
        'method': 'E*Trade - Stock Plan',
        'account': 'Stock Plan',
        'posted_date': '2025-12-31',
        'details': '',
        'status': 'PENDING',
        'raw_data': "{'id': 'TRN-72593949-b04d-4b46-b815-c754362ddbb9', 'posted': 1767182400, 'amount': '1797.24', 'description': 'Purchase Date Est. Market Val. info_outline Purchase Price', 'payee': 'Date Est Market Val Info Outline Price', 'memo': '', 'transacted_at': 1767182400}"
    }
    
    tx2 = {
        'id': '57e874aa0e7cc50258b0238911952146',
        'date': '2025-12-31',
        'amount': 1676.48,
        'description': 'Purchase Date Est. Market Val. info_outline Purchase Price',
        'category': 'Uncategorized',
        'type': 'Income',
        'method': 'E*Trade - Stock Plan',
        'account': 'Stock Plan',
        'posted_date': '2025-12-31',
        'details': '',
        'status': 'PENDING',
        'raw_data': "{'id': 'TRN-4450bbd0-46ac-41ab-970f-1ea8cacea8a3', 'posted': 1767182400, 'amount': '1676.48', 'description': 'Purchase Date Est. Market Val. info_outline Purchase Price', 'payee': 'Date Est Market Val Info Outline Price', 'memo': '', 'transacted_at': 1767182400}"
    }
    
    df = pd.DataFrame([tx1, tx2])
    print("Restoring transactions...")
    count = db.upsert_transactions(df)
    print(f"Restored {count} transactions.")

if __name__ == "__main__":
    restore_txs()
