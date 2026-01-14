
import db
import pandas as pd

def search_precise_amount():
    conn = db.get_connection()
    # Search for anything resembling 1756.86... in amount or raw_data
    val = "1756" 
    
    print(f"Searching for {val}...")
    
    # 1. Search Amount column (approximate)
    try:
        df = pd.read_sql_query(f"SELECT * FROM transactions WHERE amount > 1756 AND amount < 1757", conn)
        if not df.empty:
            print("Found in Amount column:")
            print(df)
    except Exception as e:
        print(f"Amount query error: {e}")
        
    # 2. Search Raw Data string
    try:
        df2 = pd.read_sql_query(f"SELECT * FROM transactions WHERE raw_data LIKE '%{val}%'", conn)
        if not df2.empty:
            print("Found in raw_data column:")
            for _, row in df2.iterrows():
                print(f"ID: {row['id']}")
                print(f"Raw: {row['raw_data']}")
    except Exception as e:
        print(f"Raw data query error: {e}")
        
    conn.close()

if __name__ == "__main__":
    search_precise_amount()
