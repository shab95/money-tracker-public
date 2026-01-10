import db
import pandas as pd

def inspect():
    if not db.is_postgres():
        print("Not connected to Postgres.")
        return

    conn = db.get_connection()
    try:
        # Postgres way to check columns
        df = pd.read_sql_query("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'transactions';
        """, conn)
        print(df)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect()
