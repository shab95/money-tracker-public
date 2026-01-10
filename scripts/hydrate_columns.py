import sys
import os
import ast
import pandas as pd
import sqlite3
import psycopg2
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

def hydrate():
    print("🌊 Starting Data Hydration (Source: Local SQLite)...")
    
    # 1. Connect to Local SQLite (Source of Truth for Raw Data)
    if not os.path.exists("tracker.db"):
        print("❌ 'tracker.db' not found locally. Cannot hydrate.")
        return
        
    sqlite_conn = sqlite3.connect("tracker.db")
    df = pd.read_sql_query("SELECT id, raw_data, method FROM transactions", sqlite_conn)
    sqlite_conn.close()
    
    print(f"Loaded {len(df)} transactions from Local SQLite.")
    
    if df.empty:
        return

    # 2. Connect to Cloud Postgres (Target)
    if not db.is_postgres():
        print("❌ App is not connected to Postgres. Check app_secrets.py.")
        return
        
    pg_conn = db.get_connection()
    c = pg_conn.cursor()
    
    # Ensure raw_data column exists in Postgres
    try:
        c.execute("ALTER TABLE transactions ADD COLUMN raw_data TEXT")
        pg_conn.commit()
        print("✅ Added missing 'raw_data' column to Postgres.")
    except Exception:
        pg_conn.rollback() # Column likely exists or other error
    
    print("Parsing and Updating Cloud DB...")
    
    count = 0
    
    for idx, row in df.iterrows():
        changes = {}
        tx_id = row['id']
        
        # Always update raw_data to ensure it's there
        changes['raw_data'] = row['raw_data']
        
        # 1. Account Name (from Method)
        method = row.get('method')
        if method and ' - ' in method:
            parts = method.split(' - ')
            # Usually strict format: "Bank - Account"
            if len(parts) >= 2:
                changes['account'] = parts[-1]
                
        # 2. Parse Raw Data
        raw_str = row.get('raw_data')
        if raw_str:
            try:
                data = ast.literal_eval(raw_str)
                if 'posted' in data:
                    ts = data['posted']
                    dt = datetime.fromtimestamp(ts)
                    changes['posted_date'] = dt.strftime('%Y-%m-%d')
                
                if 'memo' in data and data['memo']:
                    changes['details'] = data['memo']
            except:
                pass
                
        # Update Query
        if changes:
            set_clauses = []
            vals = []
            
            for col, val in changes.items():
                set_clauses.append(f"{col} = %s")
                vals.append(val)
            
            vals.append(tx_id)
            
            sql = f"UPDATE transactions SET {', '.join(set_clauses)} WHERE id = %s"
            
            try:
                c.execute(sql, vals)
                count += 1
            except Exception as e:
                # print(f"Failed {tx_id}: {e}")
                pg_conn.rollback()
                continue
                
    pg_conn.commit()
    pg_conn.close()
    print(f"✅ Hydration Complete. Updated {count} rows in Supabase.")

if __name__ == "__main__":
    hydrate()
