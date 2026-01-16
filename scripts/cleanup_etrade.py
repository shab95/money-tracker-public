
import db

def cleanup_etrade():
    conn = db.get_connection()
    c = conn.cursor()
    
    print("Deleting 'Leaked' E*Trade transactions (preserving Manual Entries)...")
    
    # Logic: Delete where account/method is E*Trade AND tags is NOT 'manual_entry'
    # Note: checks for NULL tags too just in case
    
    ph = '%s' if db.is_postgres() else '?'
    
    q = f"""
        DELETE FROM transactions 
        WHERE (account LIKE '%E*Trade%' OR method LIKE '%E*Trade%') 
        AND (tags IS NULL OR tags != 'aspp')
    """
    
    try:
        c.execute(q)
        print(f"Deleted {c.rowcount} transactions.")
    except Exception as e:
        print(f"Error: {e}")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    cleanup_etrade()
