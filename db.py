import sqlite3
import pandas as pd
import hashlib
import os

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

DB_URL = None

# 1. Try Streamlit Secrets (Cloud)
try:
    import streamlit as st
    if hasattr(st, 'secrets'):
         DB_URL = st.secrets.get("DB_CONNECTION_STRING") or st.secrets.get("DIRECT_CONNECTION")
except:
    pass

# 2. Try Local Secrets (app_secrets.py)
if not DB_URL:
    try:
        import app_secrets
        DB_URL = getattr(app_secrets, 'DB_CONNECTION_STRING', None) or getattr(app_secrets, 'DIRECT_CONNECTION', None)
    except ImportError:
        pass

DB_FILE = 'tracker.db'

def get_connection():
    """
    Returns a connection object.
    If DB_URL is present, returns a Postgres connection.
    Else returns SQLite connection.
    """
    if DB_URL and psycopg2:
        return psycopg2.connect(DB_URL)
    else:
        return sqlite3.connect(DB_FILE)

def is_postgres():
    return bool(DB_URL and psycopg2)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # DDL differences
    if is_postgres():
        # Postgres DDL
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT,
                amount REAL,
                description TEXT,
                category TEXT,
                type TEXT,
                method TEXT,
                status TEXT DEFAULT 'PENDING',
                user_notes TEXT,
                tags TEXT,
                raw_data TEXT,
                account TEXT,
                posted_date TEXT,
                details TEXT
            );
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_history (
                id SERIAL PRIMARY KEY,
                date TEXT,
                bank TEXT,
                account TEXT,
                balance REAL,
                UNIQUE(date, bank, account)
            );
        ''')
    else:
        # SQLite DDL
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT,
                amount REAL,
                description TEXT,
                category TEXT,
                type TEXT,
                method TEXT,
                status TEXT DEFAULT 'PENDING',
                user_notes TEXT,
                tags TEXT,
                raw_data TEXT
            )
        ''')
        
        # Migration: Add 'tags' column if it doesn't exist
        try:
            c.execute("SELECT tags FROM transactions LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE transactions ADD COLUMN tags TEXT")

        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                bank TEXT,
                account TEXT,
                balance REAL,
                UNIQUE(date, bank, account)
            )
        ''')
    
    conn.commit()
    conn.close()

def generate_id(row):
    # Create a deterministic ID to avoid duplicates
    raw_str = f"{row['date']}{row['amount']}{row['description']}"
    return hashlib.md5(raw_str.encode()).hexdigest()

def upsert_transactions(df):
    """
    Inserts new transactions. Ignores duplicates (based on ID).
    """
    if df.empty:
        return 0
        
    conn = get_connection()
    c = conn.cursor()
    
    count = 0
    # SQL Dialect: Placeholder
    ph = '%s' if is_postgres() else '?'
    
    for _, row in df.iterrows():
        # Ensure ID exists
        if 'id' not in row or not row['id']:
            tx_id = generate_id(row)
        else:
            tx_id = row['id']
            
        try:
            # We use INSERT OR IGNORE (SQLite) / ON CONFLICT DO NOTHING (Postgres)
            # Need strict values list
            vals = (
                tx_id, 
                row['date'], 
                row['amount'], 
                row['description'], 
                row.get('category', 'Uncategorized'), 
                row.get('type', 'Expense'), 
                row.get('method', 'Unknown'), 
                row.get('status', 'PENDING'),
                row.get('user_notes', ''),
                row.get('tags', ''),
                str(row.to_dict())
            )

            if is_postgres():
                c.execute(f'''
                    INSERT INTO transactions 
                    (id, date, amount, description, category, type, method, status, user_notes, tags, raw_data)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT (id) DO NOTHING
                ''', vals)
                # rowcount in pg is usually reliable
                # But executemany/on conflict can be tricky. Assume if no exception, it worked?
                # Actually cursor.rowcount works for individual insert.
                if c.rowcount > 0:
                    count += 1
            else:
                c.execute(f'''
                    INSERT OR IGNORE INTO transactions 
                    (id, date, amount, description, category, type, method, status, user_notes, tags, raw_data)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ''', vals)
                if c.rowcount > 0:
                    count += 1
                    
        except Exception as e:
            print(f"Error inserting row: {e}")
            
    conn.commit()
    conn.close()
    return count

def get_pending_transactions():
    conn = get_connection()
    q = "SELECT * FROM transactions WHERE status='PENDING' ORDER BY date DESC"
    
    if is_postgres():
        df = pd.read_sql_query(q, conn)
    else:
        df = pd.read_sql_query(q, conn)
        
    conn.close()
    return df

def get_all_transactions():
    conn = get_connection()
    q = "SELECT * FROM transactions ORDER BY date DESC"
    df = pd.read_sql_query(q, conn)
    conn.close()
    return df

def update_transaction_status(tx_ids, new_status='REVIEWED'):
    if not tx_ids:
        return
    conn = get_connection()
    c = conn.cursor()
    
    # parameterized query for list
    ph = '%s' if is_postgres() else '?'
    placeholders = ','.join(ph for _ in tx_ids)
    
    sql = f"UPDATE transactions SET status={ph} WHERE id IN ({placeholders})"
    
    # Params needs to be tuple/list
    params = [new_status] + tx_ids
    
    c.execute(sql, params)
    conn.commit()
    conn.close()

# Initialize on import
init_db()

from datetime import datetime

def save_balance_snapshot(balances_df):
    """
    Saves a snapshot of current balances for today.
    Overwrites if exists for today.
    """
    conn = get_connection()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    ph = '%s' if is_postgres() else '?'
    
    # Clean up existing
    c.execute(f"DELETE FROM balance_history WHERE date = {ph}", (today,))
    
    for _, row in balances_df.iterrows():
        bank = row['Bank']
        account = row['Account']
        balance = row['Balance']
        
        if is_postgres():
            c.execute(f'''
                INSERT INTO balance_history (date, bank, account, balance)
                VALUES ({ph}, {ph}, {ph}, {ph})
                ON CONFLICT (date, bank, account) DO UPDATE SET balance = EXCLUDED.balance
            ''', (today, bank, account, balance)) 
        else:
            c.execute(f'''
                INSERT OR REPLACE INTO balance_history (date, bank, account, balance)
                VALUES ({ph}, {ph}, {ph}, {ph})
            ''', (today, bank, account, balance))

    conn.commit()
    conn.close()
    return True

def get_net_worth_history():
    """
    Returns DataFrame: date, total_nw
    """
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT date, SUM(balance) as total_nw
        FROM balance_history
        GROUP BY date
        ORDER BY date ASC
    ''', conn)
    conn.close()
    return df

def get_balance_history_details():
    """
    Returns full history for granular charting
    """
    conn = get_connection()
    df = pd.read_sql_query('SELECT * FROM balance_history', conn)
    conn.close()
    return df
