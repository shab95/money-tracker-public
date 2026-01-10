import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

def clear():
    print("🧹 Clearing ALL Pending Transactions (Inbox)...")
    conn = db.get_connection()
    c = conn.cursor()
    
    # Check count first
    ph = '%s' if db.is_postgres() else '?'
    c.execute(f"SELECT COUNT(*) FROM transactions WHERE status='PENDING'")
    count = c.fetchone()[0]
    
    if count == 0:
        print("Inbox is already empty.")
        conn.close()
        return
        
    print(f"Deleting {count} pending transactions...")
    c.execute(f"DELETE FROM transactions WHERE status='PENDING'")
    
    conn.commit()
    conn.close()
    print("✅ Inbox Cleared.")

if __name__ == "__main__":
    clear()
