
import db
import pandas as pd

def inspect_raw():
    conn = db.get_connection()
    ids = [
        "8c8281698b9a76c1b6812c5b909269d9",
        "57e874aa0e7cc50258b0238911952146"
    ]
    ph = '%s' if db.is_postgres() else '?'
    # Postgres uses %s but tuple interpolation for "IN" is tricky.
    # Just looping is easier for 2 items.
    
    for tx_id in ids:
        q = f"SELECT * FROM transactions WHERE id = '{tx_id}'"
        try:
            df = pd.read_sql_query(q, conn)
            if not df.empty:
                print(f"\n--- Transaction {tx_id} ---")
                print(f"Description: {df.iloc[0]['description']}")
                print(f"Amount: {df.iloc[0]['amount']}")
                print(f"Account: {df.iloc[0]['account']}")
                print(f"Raw Data: {df.iloc[0]['raw_data']}")
        except Exception as e:
            print(e)
            
    conn.close()

if __name__ == "__main__":
    inspect_raw()
