
import db
import pandas as pd

def inspect_duplicates():
    conn = db.get_connection()
    # Query for Dec 31 transactions related to Stock Plan
    q = """
    SELECT * FROM transactions 
    WHERE date LIKE '%-12-31' 
    AND (description LIKE '%Stock%' OR account LIKE '%Stock%' OR category LIKE '%Stock%')
    """
    
    try:
        df = pd.read_sql_query(q, conn)
        if not df.empty:
            print(f"Found {len(df)} transactions:")
            for _, row in df.iterrows():
                print("--------------------------------------------------")
                print(f"ID: {row['id']}")
                print(f"Date: {row['date']}")
                print(f"Description: {row['description']}")
                print(f"Amount: {row['amount']}")
                print(f"Account: {row['account']}")
                print(f"Raw Data: {row['raw_data']}")
        else:
            print("No matching transactions found.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_duplicates()
