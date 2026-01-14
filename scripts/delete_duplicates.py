
import db

def delete_duplicates():
    conn = db.get_connection()
    c = conn.cursor()
    # IDs from previous inspection
    ids = [
        "8c8281698b9a76c1b6812c5b909269d9",
        "57e874aa0e7cc50258b0238911952146"
    ]
    ph = '%s' if db.is_postgres() else '?'
    
    deleted_count = 0
    for tx_id in ids:
        try:
            c.execute(f"DELETE FROM transactions WHERE id = '{tx_id}'")
            if c.rowcount > 0:
                print(f"Deleted {tx_id}")
                deleted_count += 1
        except Exception as e:
            print(f"Error: {e}")
            
    conn.commit()
    conn.close()
    print(f"Total deleted: {deleted_count}")

if __name__ == "__main__":
    delete_duplicates()
