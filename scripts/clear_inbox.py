
import db

def clear_inbox():
    print("Clearing inbox (deleting all PENDING transactions)...")
    conn = db.get_connection()
    c = conn.cursor()
    
    ph = '%s' if db.is_postgres() else '?'
    
    # We want to clear PENDING transactions.
    # The user said "clear my inbox", which usually means "mark as done" or "delete".
    # But since they want to "sync again", deleting is safer so they can be re-imported.
    # If we mark as reviewed, they won't show up in Inbox, but they won't be re-imported if ID exists.
    # So deleting them is the way to go if the goal is to "try clicking the button" (re-sync).
    
    try:
        c.execute(f"DELETE FROM transactions WHERE status='PENDING'")
        deleted = c.rowcount
        print(f"Deleted {deleted} pending transactions.")
        conn.commit()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clear_inbox()
