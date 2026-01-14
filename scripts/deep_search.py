
import db
import pandas as pd
import json

def deep_search():
    conn = db.get_connection()
    
    # 1. Search for generic Qty/Price strings in raw_data
    print("Searching for 'Qty' or 'Price' in raw_data...")
    try:
        df = pd.read_sql_query("SELECT id, raw_data FROM transactions WHERE raw_data LIKE '%Qty%' OR raw_data LIKE '%Price%'", conn)
        if not df.empty:
            print(f"Found {len(df)} rows with Qty/Price in raw_data.")
            print("Sample:", df.iloc[0]['raw_data'])
        else:
            print("No 'Qty' or 'Price' found in raw_data string.")
    except Exception as e:
        print(e)

    # 2. Search for the specific amount
    print("\nSearching for amount 1756...")
    try:
        # Check Amount column
        df2 = pd.read_sql_query("SELECT * FROM transactions WHERE amount > 1756 AND amount < 1757", conn)
        if not df2.empty:
            print("Found in Amount column:")
            print(df2[['date', 'description', 'amount', 'raw_data']])
        else:
            print("Not found in Amount column.")
            
    except Exception as e:
        print(e)
        
    conn.close()

if __name__ == "__main__":
    deep_search()
