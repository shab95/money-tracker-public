import db

def cleanup():
    conn = db.get_connection()
    c = conn.cursor()
    
    # List of substrings to search for in 'method'
    SKIP_KEYWORDS = [
        "CAPITAL ONE 401K ASP",
        "Self-Directed Brokerage",
        "Robinhood Roth IRA",
        "Robinhood managed Roth IRA",
        "Robinhood managed individual",
        "Robinhood individual",
        "Crypto",
        "Brokerage Health Savings",
        "Brokerage General Investing Person",
        "Stock Plan",
        "Individual Brokerage"
    ]
    
    total_deleted = 0
    
    for kw in SKIP_KEYWORDS:
        # Use LIKE %keyword%
        c.execute("DELETE FROM transactions WHERE status='PENDING' AND method LIKE ?", (f'%{kw}%',))
        deleted = c.rowcount
        if deleted > 0:
            print(f"Deleted {deleted} rows matching '{kw}'")
            total_deleted += deleted
            
    conn.commit()
    conn.close()
    print(f"Total deleted: {total_deleted}")

if __name__ == "__main__":
    cleanup()
