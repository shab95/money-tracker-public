import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

def wipe_recent_venmo():
    print("🧹 Wiping Venmo transactions from 2025-12-01 onwards...")
    conn = db.get_connection()
    c = conn.cursor()
    
    # Criteria: Date >= 2025-12-01 AND (method='Venmo' OR description LIKE '%Venmo%')
    # This targets both the CSV imports (method=Venmo) and Bank Syncs (desc=VENMO...)
    
    ph = '%s' if db.is_postgres() else '?'
    
    # Postgres ILIKE, SQLite LIKE (case insensitive usually? or use lower)
    # db.py doesn't expose dialect easily for query building, just use SQL standard-ish.
    
    pattern = '%Venmo%'
    date_cutoff = '2025-12-01'
    
    sql = f"""
        DELETE FROM transactions 
        WHERE date >= {ph} 
        AND (
            method = 'Venmo'
            OR description LIKE {ph}
            OR method LIKE {ph}
        )
    """
    
    c.execute(sql, (date_cutoff, pattern, pattern))
    deleted = c.rowcount
    
    conn.commit()
    conn.close()
    print(f"✅ Deleted {deleted} transactions.")

if __name__ == "__main__":
    wipe_recent_venmo()
