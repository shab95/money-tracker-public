import sqlite3
import psycopg2
import pandas as pd
import app_secrets

def migrate():
    # 1. Connect to Local SQLite
    print("Reading from local SQLite (tracker.db)...")
    sqlite_conn = sqlite3.connect("tracker.db")
    
    # Read Tables
    try:
        transactions_df = pd.read_sql("SELECT * FROM transactions", sqlite_conn)
        print(f"Loaded {len(transactions_df)} transactions.")
    except Exception as e:
        print(f"Error reading transactions: {e}")
        transactions_df = pd.DataFrame()

    try:
        balance_df = pd.read_sql("SELECT * FROM balance_history", sqlite_conn)
        print(f"Loaded {len(balance_df)} balance records.")
    except Exception as e:
        print(f"Error reading balance_history: {e}")
        balance_df = pd.DataFrame()
        
    sqlite_conn.close()
    
    # 2. Connect to Cloud Postgres
    db_url = getattr(app_secrets, "DB_CONNECTION_STRING", None)
    if not db_url:
        db_url = getattr(app_secrets, "DIRECT_CONNECTION", None)
        
    if not db_url:
        print("ERROR: DB_CONNECTION_STRING or DIRECT_CONNECTION not found in app_secrets.py")
        return

    print("Connecting to Postgres...")
    try:
        pg_conn = psycopg2.connect(db_url)
        cursor = pg_conn.cursor()
    except Exception as e:
        print(f"Failed to connect to Postgres: {e}")
        return

    # 3. Create Tables in Postgres (Idempotent)
    # Note: Postgres uses SERIAL for auto-increment, SQLite uses INTEGER PRIMARY KEY AUTOINCREMENT
    
    create_tx_table = """
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        date TEXT,
        description TEXT,
        amount REAL,
        category TEXT,
        account TEXT,
        posted_date TEXT,
        status TEXT,
        details TEXT,
        type TEXT,
        tags TEXT,
        user_notes TEXT,
        method TEXT
    );
    """
    
    create_bal_table = """
    CREATE TABLE IF NOT EXISTS balance_history (
        date TEXT,
        bank TEXT,
        account TEXT,
        balance REAL,
        UNIQUE(date, bank, account)
    );
    """
    
    print("Creating tables...")
    cursor.execute(create_tx_table)
    cursor.execute(create_bal_table)
    pg_conn.commit()
    
    # 4. Bulk Insert Data
    # Transactions
    if not transactions_df.empty:
        print("Migrating transactions...")
        # Prepare list of tuples
        # Handle NaN values explicitly if needed, but pandas usually handles them
        transactions_df = transactions_df.where(pd.notnull(transactions_df), None)
        
        tx_tuples = [tuple(x) for x in transactions_df.to_numpy()]
        
        # Prepare missing columns
        for col in ['account', 'posted_date', 'details']:
            if col not in transactions_df.columns:
                transactions_df[col] = None
        
        # Columns in dataframe must match table columns order!
        # Let's ensure order
        cols = ['id', 'date', 'description', 'amount', 'category', 'account', 'posted_date', 'status', 'details', 'type', 'tags', 'user_notes', 'method']
        # Filter DF to these cols only just in case
        transactions_df = transactions_df[cols]
        tx_tuples = [tuple(x) for x in transactions_df.to_numpy()]
        
        query = """
        INSERT INTO transactions (id, date, description, amount, category, account, posted_date, status, details, type, tags, user_notes, method)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING;
        """
        
        cursor.executemany(query, tx_tuples)
        pg_conn.commit()
        print(f"Inserted {len(tx_tuples)} transactions.")

    # Balances
    if not balance_df.empty:
        print("Migrating balances...")
        balance_df = balance_df.where(pd.notnull(balance_df), None)
        cols = ['date', 'bank', 'account', 'balance']
        balance_df = balance_df[cols]
        bal_tuples = [tuple(x) for x in balance_df.to_numpy()]
        
        query = """
        INSERT INTO balance_history (date, bank, account, balance)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (date, bank, account) DO NOTHING;
        """
        
        cursor.executemany(query, bal_tuples)
        pg_conn.commit()
        print(f"Inserted {len(bal_tuples)} balance records.")

    print("Migration Complete! 🎉")
    cursor.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()
