
import db
import pandas as pd

def inspect_all_dec31():
    conn = db.get_connection()
    # Broad query for date
    q = "SELECT * FROM transactions WHERE date LIKE '2025-12-31%'"
    
    try:
        df = pd.read_sql_query(q, conn)
        if not df.empty:
            print(f"Found {len(df)} transactions on Dec 31:")
            for _, row in df.iterrows():
                print(f"ID: {row['id']} | Desc: {row['description']} | Amt: {row['amount']} | Acct: {row['account']}")
        else:
            print("No transactions found for 2025-12-31.")
            
            # Check most recent date
            recent = pd.read_sql_query("SELECT date FROM transactions ORDER BY date DESC LIMIT 5", conn)
            print("\nMost recent dates in DB:")
            print(recent)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_all_dec31()
