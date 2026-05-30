import sqlite3
import pandas as pd
import hashlib
import os
import re
from datetime import datetime

import config

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

DB_URL = None

# 1. Try Streamlit Secrets only when this app is explicitly in production mode.
if config.should_use_production_db():
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
             DB_URL = st.secrets.get("DB_CONNECTION_STRING") or st.secrets.get("DIRECT_CONNECTION")
    except:
        pass

# 2. Try Local Secrets only when explicitly using production DB locally.
if not DB_URL and config.should_use_production_db():
    try:
        import app_secrets
        DB_URL = getattr(app_secrets, 'DB_CONNECTION_STRING', None) or getattr(app_secrets, 'DIRECT_CONNECTION', None)
    except ImportError:
        pass

DB_FILE = config.get_db_file()

def get_connection():
    """
    Returns a connection object.
    If DB_URL is present, returns a Postgres connection.
    Else returns SQLite connection.
    """
    if DB_URL and psycopg2:
        try:
            # Force SSL mode
            dsn = DB_URL
            if 'sslmode' not in dsn and 'localhost' not in dsn:
                if '?' in dsn:
                    dsn += "&sslmode=require"
                else:
                    dsn += "?sslmode=require"
            
            # WORKAROUND: Streamlit Cloud IPv6 issue with Supabase
            # Convert hostname to IPv4 address explicitly
            try:
                import socket
                from urllib.parse import urlparse, urlunparse
                
                # Parse the URL
                parsed = urlparse(dsn)
                hostname = parsed.hostname
                
                if hostname and 'supabase.co' in hostname:
                    # Resolve to IPv4
                    ipv4 = socket.gethostbyname(hostname)
                    # Replace hostname with IP in the URL
                    # Note: We must update the netloc (user:pass@host:port)
                    new_netloc = parsed.netloc.replace(hostname, ipv4)
                    parsed = parsed._replace(netloc=new_netloc)
                    dsn = urlunparse(parsed)
                    print(f"🔧 Resolved {hostname} to {ipv4} for IPv4 connectivity.")
            except Exception as dns_error:
                print(f"⚠️ DNS Resolution failed, trying original DSN: {dns_error}")

            return psycopg2.connect(dsn)
        except Exception as e:
            # IMPORTANT: Print error for Streamlit Cloud logs
            print(f"❌ DATABASE CONNECTION FAILED: {e}")
            # If streamlit is available, show it (but be careful of leaking secrets)
            try:
                import streamlit as st
                st.error(f"Database Connection Error: {e}")
            except:
                pass
            raise e
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
                details TEXT,
                ml_confidence REAL,
                ml_category_confidence REAL,
                ml_type_confidence REAL,
                reviewed_at TEXT,
                reviewed_by TEXT,
                review_source TEXT
            );
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_history (
                id SERIAL PRIMARY KEY,
                date TEXT,
                bank TEXT,
                account TEXT,
                balance REAL,
                classification TEXT,
                UNIQUE(date, bank, account)
            );
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_snapshot_runs (
                id SERIAL PRIMARY KEY,
                snapshot_date TEXT UNIQUE,
                sync_run_id INTEGER,
                account_count INTEGER,
                status TEXT,
                updated_at TEXT
            );
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS sync_runs (
                id SERIAL PRIMARY KEY,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                accounts_seen INTEGER,
                accounts_included INTEGER,
                accounts_skipped INTEGER,
                transactions_seen INTEGER,
                transactions_inserted INTEGER,
                duplicates INTEGER,
                balance_accounts_seen INTEGER,
                sync_start_date TEXT,
                sync_end_date TEXT,
                error TEXT
            );
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS sync_account_results (
                id SERIAL PRIMARY KEY,
                sync_run_id INTEGER REFERENCES sync_runs(id),
                bank TEXT,
                account TEXT,
                included BOOLEAN,
                skip_reason TEXT,
                transaction_count INTEGER,
                inserted_count INTEGER,
                duplicate_count INTEGER,
                latest_transaction_date TEXT,
                balance REAL,
                currency TEXT,
                health_status TEXT,
                error TEXT
            );
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS ml_artifacts (
                name TEXT PRIMARY KEY,
                artifact BYTEA,
                trained_at TEXT,
                metadata TEXT
            );
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS account_rules (
                id SERIAL PRIMARY KEY,
                bank TEXT,
                account TEXT,
                classification TEXT,
                include_in_inbox BOOLEAN,
                include_in_net_worth BOOLEAN,
                notes TEXT,
                updated_at TEXT,
                UNIQUE(bank, account)
            );
        ''')
        _ensure_pg_column(c, "transactions", "account", "TEXT")
        _ensure_pg_column(c, "transactions", "posted_date", "TEXT")
        _ensure_pg_column(c, "transactions", "details", "TEXT")
        _ensure_pg_column(c, "transactions", "ml_confidence", "REAL")
        _ensure_pg_column(c, "transactions", "ml_category_confidence", "REAL")
        _ensure_pg_column(c, "transactions", "ml_type_confidence", "REAL")
        _ensure_pg_column(c, "transactions", "reviewed_at", "TEXT")
        _ensure_pg_column(c, "transactions", "reviewed_by", "TEXT")
        _ensure_pg_column(c, "transactions", "review_source", "TEXT")
        _ensure_pg_column(c, "balance_history", "classification", "TEXT")
        _ensure_pg_column(c, "sync_runs", "sync_start_date", "TEXT")
        _ensure_pg_column(c, "sync_runs", "sync_end_date", "TEXT")
        _ensure_pg_column(c, "sync_runs", "balance_accounts_seen", "INTEGER")
        _ensure_pg_column(c, "sync_account_results", "latest_transaction_date", "TEXT")
        _ensure_pg_column(c, "sync_account_results", "balance", "REAL")
        _ensure_pg_column(c, "sync_account_results", "currency", "TEXT")
        _ensure_pg_column(c, "sync_account_results", "health_status", "TEXT")
        _ensure_pg_column(c, "balance_snapshot_runs", "sync_run_id", "INTEGER")
        _ensure_pg_column(c, "balance_snapshot_runs", "account_count", "INTEGER")
        _ensure_pg_column(c, "balance_snapshot_runs", "status", "TEXT")
        _ensure_pg_column(c, "balance_snapshot_runs", "updated_at", "TEXT")
        _ensure_pg_column(c, "account_rules", "classification", "TEXT")
        _ensure_pg_column(c, "account_rules", "include_in_inbox", "BOOLEAN")
        _ensure_pg_column(c, "account_rules", "include_in_net_worth", "BOOLEAN")
        _ensure_pg_column(c, "account_rules", "notes", "TEXT")
        _ensure_pg_column(c, "account_rules", "updated_at", "TEXT")
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
                raw_data TEXT,
                account TEXT,
                posted_date TEXT,
                details TEXT,
                ml_confidence REAL,
                ml_category_confidence REAL,
                ml_type_confidence REAL,
                reviewed_at TEXT,
                reviewed_by TEXT,
                review_source TEXT
            )
        ''')
        _ensure_sqlite_column(c, "transactions", "tags", "TEXT")
        _ensure_sqlite_column(c, "transactions", "account", "TEXT")
        _ensure_sqlite_column(c, "transactions", "posted_date", "TEXT")
        _ensure_sqlite_column(c, "transactions", "details", "TEXT")
        _ensure_sqlite_column(c, "transactions", "ml_confidence", "REAL")
        _ensure_sqlite_column(c, "transactions", "ml_category_confidence", "REAL")
        _ensure_sqlite_column(c, "transactions", "ml_type_confidence", "REAL")
        _ensure_sqlite_column(c, "transactions", "reviewed_at", "TEXT")
        _ensure_sqlite_column(c, "transactions", "reviewed_by", "TEXT")
        _ensure_sqlite_column(c, "transactions", "review_source", "TEXT")

        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                bank TEXT,
                account TEXT,
                balance REAL,
                classification TEXT,
                UNIQUE(date, bank, account)
            )
        ''')
        _ensure_sqlite_column(c, "balance_history", "classification", "TEXT")
        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_snapshot_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT UNIQUE,
                sync_run_id INTEGER,
                account_count INTEGER,
                status TEXT,
                updated_at TEXT
            )
        ''')
        _ensure_sqlite_column(c, "balance_snapshot_runs", "sync_run_id", "INTEGER")
        _ensure_sqlite_column(c, "balance_snapshot_runs", "account_count", "INTEGER")
        _ensure_sqlite_column(c, "balance_snapshot_runs", "status", "TEXT")
        _ensure_sqlite_column(c, "balance_snapshot_runs", "updated_at", "TEXT")
        c.execute('''
            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                accounts_seen INTEGER,
                accounts_included INTEGER,
                accounts_skipped INTEGER,
                transactions_seen INTEGER,
                transactions_inserted INTEGER,
                duplicates INTEGER,
                balance_accounts_seen INTEGER,
                sync_start_date TEXT,
                sync_end_date TEXT,
                error TEXT
            )
        ''')
        _ensure_sqlite_column(c, "sync_runs", "sync_start_date", "TEXT")
        _ensure_sqlite_column(c, "sync_runs", "sync_end_date", "TEXT")
        _ensure_sqlite_column(c, "sync_runs", "balance_accounts_seen", "INTEGER")
        c.execute('''
            CREATE TABLE IF NOT EXISTS sync_account_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_run_id INTEGER,
                bank TEXT,
                account TEXT,
                included INTEGER,
                skip_reason TEXT,
                transaction_count INTEGER,
                inserted_count INTEGER,
                duplicate_count INTEGER,
                latest_transaction_date TEXT,
                balance REAL,
                currency TEXT,
                health_status TEXT,
                error TEXT
            )
        ''')
        _ensure_sqlite_column(c, "sync_account_results", "latest_transaction_date", "TEXT")
        _ensure_sqlite_column(c, "sync_account_results", "balance", "REAL")
        _ensure_sqlite_column(c, "sync_account_results", "currency", "TEXT")
        _ensure_sqlite_column(c, "sync_account_results", "health_status", "TEXT")
        c.execute('''
            CREATE TABLE IF NOT EXISTS ml_artifacts (
                name TEXT PRIMARY KEY,
                artifact BLOB,
                trained_at TEXT,
                metadata TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS account_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank TEXT,
                account TEXT,
                classification TEXT,
                include_in_inbox INTEGER,
                include_in_net_worth INTEGER,
                notes TEXT,
                updated_at TEXT,
                UNIQUE(bank, account)
            )
        ''')
        _ensure_sqlite_column(c, "account_rules", "classification", "TEXT")
        _ensure_sqlite_column(c, "account_rules", "include_in_inbox", "INTEGER")
        _ensure_sqlite_column(c, "account_rules", "include_in_net_worth", "INTEGER")
        _ensure_sqlite_column(c, "account_rules", "notes", "TEXT")
        _ensure_sqlite_column(c, "account_rules", "updated_at", "TEXT")
    
    conn.commit()
    conn.close()


def _ensure_sqlite_column(cursor, table, column, column_type):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _ensure_pg_column(cursor, table, column, column_type):
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")


def ensure_ml_artifacts_table():
    conn = get_connection()
    c = conn.cursor()
    if is_postgres():
        c.execute('''
            CREATE TABLE IF NOT EXISTS ml_artifacts (
                name TEXT PRIMARY KEY,
                artifact BYTEA,
                trained_at TEXT,
                metadata TEXT
            );
        ''')
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS ml_artifacts (
                name TEXT PRIMARY KEY,
                artifact BLOB,
                trained_at TEXT,
                metadata TEXT
            )
        ''')
    conn.commit()
    conn.close()


def get_account_rules():
    conn = get_connection()
    try:
        return pd.read_sql_query('''
            SELECT bank, account, classification, include_in_inbox,
                   include_in_net_worth, notes, updated_at
            FROM account_rules
            ORDER BY bank, account
        ''', conn)
    finally:
        conn.close()


def _coerce_rule_bool(value):
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "include", "1"}:
            return True
        if lowered in {"false", "no", "exclude", "0"}:
            return False
        return None
    return bool(value)


def upsert_account_rules(rules):
    if not rules:
        return 0
    conn = get_connection()
    c = conn.cursor()
    ph = '%s' if is_postgres() else '?'
    updated_at = datetime.now().isoformat(timespec="seconds")
    count = 0
    for rule in rules:
        bank = clean_text(rule.get("bank"))
        account = clean_text(rule.get("account"))
        if not bank or not account:
            continue
        classification = clean_text(rule.get("classification")) or None
        include_in_inbox = _coerce_rule_bool(rule.get("include_in_inbox"))
        include_in_net_worth = _coerce_rule_bool(rule.get("include_in_net_worth"))
        notes = clean_text(rule.get("notes"))
        values = (
            bank,
            account,
            classification,
            include_in_inbox,
            include_in_net_worth,
            notes,
            updated_at,
        )
        if is_postgres():
            c.execute(f'''
                INSERT INTO account_rules
                    (bank, account, classification, include_in_inbox,
                     include_in_net_worth, notes, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (bank, account) DO UPDATE SET
                    classification = EXCLUDED.classification,
                    include_in_inbox = EXCLUDED.include_in_inbox,
                    include_in_net_worth = EXCLUDED.include_in_net_worth,
                    notes = EXCLUDED.notes,
                    updated_at = EXCLUDED.updated_at
            ''', values)
        else:
            c.execute(f'''
                INSERT INTO account_rules
                    (bank, account, classification, include_in_inbox,
                     include_in_net_worth, notes, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (bank, account) DO UPDATE SET
                    classification = excluded.classification,
                    include_in_inbox = excluded.include_in_inbox,
                    include_in_net_worth = excluded.include_in_net_worth,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
            ''', values)
        count += 1
    conn.commit()
    conn.close()
    return count

def generate_id(row):
    # Create a deterministic ID to avoid duplicates
    raw_data = row.get('raw_data', None)
    if isinstance(raw_data, dict) and raw_data.get('id'):
        return str(raw_data['id'])
    if not is_blank_value(row.get('simplefin_id')):
        return str(row['simplefin_id'])
    return generate_legacy_id(row)


def generate_legacy_id(row):
    raw_str = f"{row['date']}{row['amount']}{row['description']}"
    return hashlib.md5(raw_str.encode()).hexdigest()


def generate_legacy_id_candidates(row):
    """
    Older rows used date + amount + description as the primary key. Pandas and
    database drivers can stringify the same amount differently (4.9 vs 4.90),
    so check the common historical shapes before treating a SimpleFIN ID as new.
    """
    date_value = row['date']
    description = row['description']
    amount_value = row['amount']
    amount_strings = {str(amount_value)}
    try:
        amount_float = float(amount_value)
        amount_strings.add(str(amount_float))
        amount_strings.add(f"{amount_float:.2f}")
        amount_strings.add(str(abs(amount_float)))
        amount_strings.add(f"{abs(amount_float):.2f}")
        if amount_float.is_integer():
            amount_strings.add(str(int(amount_float)))
    except (TypeError, ValueError):
        pass

    return [
        hashlib.md5(f"{date_value}{amount}{description}".encode()).hexdigest()
        for amount in sorted(amount_strings)
    ]


def is_blank_value(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def clean_text(value):
    if is_blank_value(value):
        return ""
    return str(value).strip()


def normalize_source_text(value):
    text = clean_text(value)
    # SimpleFIN commonly appends a masked account suffix, e.g. "360 Checking
    # (3285)"; older reviewed rows may only have "360 Checking".
    return re.sub(r"\s+\(\d{2,}\)$", "", text).strip()


def get_transaction_by_id(tx_id):
    conn = get_connection()
    ph = '%s' if is_postgres() else '?'
    try:
        df = pd.read_sql_query(
            f"SELECT id, account, method, posted_date, details FROM transactions WHERE id = {ph} LIMIT 1",
            conn,
            params=(tx_id,),
        )
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    finally:
        conn.close()


def get_transactions_by_ids(tx_ids):
    tx_ids = list(dict.fromkeys(tx_ids))
    if not tx_ids:
        return []
    conn = get_connection()
    ph = '%s' if is_postgres() else '?'
    placeholders = ','.join(ph for _ in tx_ids)
    try:
        df = pd.read_sql_query(
            f"SELECT id, account, method, posted_date, details FROM transactions WHERE id IN ({placeholders})",
            conn,
            params=tx_ids,
        )
        return df.to_dict('records')
    finally:
        conn.close()


def legacy_duplicate_matches_existing(row, legacy_ids):
    existing_rows = get_transactions_by_ids(legacy_ids)
    if not existing_rows:
        return False

    for existing in existing_rows:
        existing_account = normalize_source_text(existing.get('account'))
        new_account = normalize_source_text(row.get('account'))
        if existing_account and new_account:
            if existing_account == new_account:
                return True
            continue

        existing_method = normalize_source_text(existing.get('method'))
        new_method = normalize_source_text(row.get('method'))
        if existing_method and new_method:
            if existing_method == new_method:
                return True
            continue

        # Old legacy rows may have no source fields at all. In that case there is
        # nothing safer to compare, so keep the guard that prevents reopening them.
        if not existing_account and not existing_method:
            return True

    return False


def is_venmo_import(row):
    tags = clean_text(row.get('tags')).lower()
    account = normalize_source_text(row.get('account')).lower()
    method = normalize_source_text(row.get('method')).lower()
    return "venmo_import" in tags or account == "venmo" or method == "venmo"


def venmo_match_tokens(*values):
    text = " ".join(clean_text(value).lower() for value in values)
    tokens = set(re.findall(r"[a-z0-9]{3,}", text))
    return tokens - {
        "venmo",
        "shabarish",
        "nair",
        "payment",
        "transaction",
        "personal",
        "checking",
        "statement",
        "period",
        "nan",
    }


def venmo_duplicate_matches_existing(row):
    if not is_venmo_import(row):
        return False

    try:
        new_amount = float(row.get('amount'))
    except (TypeError, ValueError):
        return False

    min_amount = new_amount - 0.005
    max_amount = new_amount + 0.005
    conn = get_connection()
    ph = '%s' if is_postgres() else '?'
    try:
        df = pd.read_sql_query(f'''
            SELECT id, date, amount, description, account, method
            FROM transactions
            WHERE date = {ph}
              AND description = {ph}
              AND amount >= {ph}
              AND amount <= {ph}
              AND (account = {ph} OR method = {ph})
        ''', conn, params=(row['date'], row['description'], min_amount, max_amount, 'Venmo', 'Venmo'))
    finally:
        conn.close()

    if df.empty:
        return False

    return True


def mark_matching_bank_venmo_as_transfer(cursor, row, ph):
    if not is_venmo_import(row):
        return 0

    tokens = venmo_match_tokens(
        row.get('description'),
        row.get('user_notes'),
        row.get('details'),
    )
    if not tokens:
        return 0

    try:
        amount = float(row.get('amount'))
        tx_date = pd.to_datetime(row['date'])
    except (TypeError, ValueError):
        return 0

    start_date = (tx_date - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    end_date = (tx_date + pd.Timedelta(days=3)).strftime('%Y-%m-%d')
    min_amount = amount - 0.005
    max_amount = amount + 0.005

    conn = cursor.connection
    candidates = pd.read_sql_query(f'''
        SELECT id, description, user_notes, details, account, method
        FROM transactions
        WHERE date >= {ph}
          AND date <= {ph}
          AND amount >= {ph}
          AND amount <= {ph}
          AND LOWER(description) = {ph}
    ''', conn, params=(start_date, end_date, min_amount, max_amount, 'venmo'))

    updated = 0
    for _, candidate in candidates.iterrows():
        candidate_account = normalize_source_text(candidate.get('account')).lower()
        candidate_method = normalize_source_text(candidate.get('method')).lower()
        if candidate_account == 'venmo' or candidate_method == 'venmo':
            continue

        candidate_tokens = venmo_match_tokens(
            candidate.get('description'),
            candidate.get('user_notes'),
            candidate.get('details'),
        )
        if not tokens.intersection(candidate_tokens):
            continue

        cursor.execute(f'''
            UPDATE transactions
            SET category = {ph},
                type = {ph}
            WHERE id = {ph}
        ''', ('Transfer', 'Transfer', candidate['id']))
        updated += cursor.rowcount

    return updated


def get_review_audit_values(row):
    status = row.get('status', 'PENDING')
    if str(status).upper() != 'REVIEWED':
        return (
            row.get('reviewed_at', None),
            row.get('reviewed_by', None),
            row.get('review_source', None),
        )
    return (
        row.get('reviewed_at') or datetime.now().isoformat(timespec="seconds"),
        row.get('reviewed_by') or 'system',
        row.get('review_source') or 'import',
    )

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
        if 'id' not in row or is_blank_value(row['id']):
            tx_id = generate_id(row)
        else:
            tx_id = row['id']
        legacy_ids = generate_legacy_id_candidates(row)
            
        try:
            if tx_id not in legacy_ids and legacy_duplicate_matches_existing(row, legacy_ids):
                continue
            if venmo_duplicate_matches_existing(row):
                continue

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
                row.get('raw_data', str(row.to_dict())),
                row.get('account', None),
                row.get('posted_date', None),
                row.get('details', None),
                row.get('ml_confidence', None),
                row.get('ml_category_confidence', None),
                row.get('ml_type_confidence', None),
                *get_review_audit_values(row)
            )

            if is_postgres():
                c.execute(f'''
                    INSERT INTO transactions 
                    (id, date, amount, description, category, type, method, status, user_notes, tags, raw_data,
                     account, posted_date, details, ml_confidence, ml_category_confidence, ml_type_confidence,
                     reviewed_at, reviewed_by, review_source)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT (id) DO NOTHING
                ''', vals)
                # rowcount in pg is usually reliable
                # But executemany/on conflict can be tricky. Assume if no exception, it worked?
                # Actually cursor.rowcount works for individual insert.
                if c.rowcount > 0:
                    mark_matching_bank_venmo_as_transfer(c, row, ph)
                    count += 1
            else:
                c.execute(f'''
                    INSERT OR IGNORE INTO transactions 
                    (id, date, amount, description, category, type, method, status, user_notes, tags, raw_data,
                     account, posted_date, details, ml_confidence, ml_category_confidence, ml_type_confidence,
                     reviewed_at, reviewed_by, review_source)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ''', vals)
                if c.rowcount > 0:
                    mark_matching_bank_venmo_as_transfer(c, row, ph)
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
    
    if str(new_status).upper() == 'REVIEWED':
        sql = f'''
            UPDATE transactions
            SET status={ph},
                reviewed_at=COALESCE(reviewed_at, {ph}),
                reviewed_by=COALESCE(reviewed_by, {ph}),
                review_source=COALESCE(review_source, {ph})
            WHERE id IN ({placeholders})
        '''
        params = [new_status, datetime.now().isoformat(timespec="seconds"), 'system', 'status_update'] + tx_ids
    else:
        sql = f"UPDATE transactions SET status={ph} WHERE id IN ({placeholders})"
        params = [new_status] + tx_ids
    
    c.execute(sql, params)
    conn.commit()
    conn.close()

def review_transaction(tx_id, category, user_notes, tags, tx_type, reviewed_by='admin', review_source='manual'):
    conn = get_connection()
    c = conn.cursor()
    ph = '%s' if is_postgres() else '?'
    c.execute(f'''
        UPDATE transactions
        SET category = {ph},
            user_notes = {ph},
            tags = {ph},
            type = {ph},
            status = 'REVIEWED',
            reviewed_at = {ph},
            reviewed_by = {ph},
            review_source = {ph}
        WHERE id = {ph}
    ''', (
        category,
        user_notes,
        tags,
        tx_type,
        datetime.now().isoformat(timespec="seconds"),
        reviewed_by,
        review_source,
        tx_id,
    ))
    conn.commit()
    conn.close()

# Initialize on import
init_db()

def save_balance_snapshot(balances_df, replace_for_today=False, sync_run_id=None):
    """
    Saves a snapshot of current balances for today.
    Upserts accounts present in the provided snapshot. Use replace_for_today
    only when the caller has a full current account set.
    """
    conn = get_connection()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    ph = '%s' if is_postgres() else '?'

    if replace_for_today:
        c.execute(f"DELETE FROM balance_history WHERE date = {ph}", (today,))

    if replace_for_today:
        account_count = 0 if balances_df.empty else len(balances_df)
        updated_at = datetime.now().isoformat(timespec="seconds")
        if is_postgres():
            c.execute(f'''
                INSERT INTO balance_snapshot_runs
                    (snapshot_date, sync_run_id, account_count, status, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (snapshot_date) DO UPDATE SET
                    sync_run_id = EXCLUDED.sync_run_id,
                    account_count = EXCLUDED.account_count,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
            ''', (today, sync_run_id, account_count, "success", updated_at))
        else:
            c.execute(f'''
                INSERT INTO balance_snapshot_runs
                    (snapshot_date, sync_run_id, account_count, status, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (snapshot_date) DO UPDATE SET
                    sync_run_id = excluded.sync_run_id,
                    account_count = excluded.account_count,
                    status = excluded.status,
                    updated_at = excluded.updated_at
            ''', (today, sync_run_id, account_count, "success", updated_at))

    if balances_df.empty:
        conn.commit()
        conn.close()
        return True

    for _, row in balances_df.iterrows():
        bank = row['Bank']
        account = row['Account']
        balance = row['Balance']
        classification = row.get('Classification', row.get('Type', None))
        
        if is_postgres():
            c.execute(f'''
                INSERT INTO balance_history (date, bank, account, balance, classification)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (date, bank, account) DO UPDATE SET
                    balance = EXCLUDED.balance,
                    classification = EXCLUDED.classification
            ''', (today, bank, account, balance, classification)) 
        else:
            c.execute(f'''
                INSERT OR REPLACE INTO balance_history (date, bank, account, balance, classification)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            ''', (today, bank, account, balance, classification))

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


def get_latest_balance_snapshot_run(conn=None):
    own_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        return pd.read_sql_query('''
            SELECT id, snapshot_date, sync_run_id, COALESCE(account_count, 0) AS account_count,
                   status, updated_at
            FROM balance_snapshot_runs
            WHERE status = 'success'
            ORDER BY snapshot_date DESC, id DESC
            LIMIT 1
        ''', conn)
    finally:
        if own_conn:
            conn.close()


def get_latest_balance_snapshot():
    conn = get_connection()
    ph = '%s' if is_postgres() else '?'
    try:
        latest_snapshot_run = get_latest_balance_snapshot_run(conn)
        if not latest_snapshot_run.empty:
            snapshot_date = latest_snapshot_run.iloc[0]["snapshot_date"]
            return pd.read_sql_query(f'''
                SELECT date, bank, account, balance, classification
                FROM balance_history
                WHERE date = {ph}
                ORDER BY classification, bank, account
            ''', conn, params=(snapshot_date,))

        latest_sync = pd.read_sql_query('''
            SELECT finished_at, started_at
            FROM sync_runs
            WHERE status = 'success'
            ORDER BY id DESC
            LIMIT 1
        ''', conn)

        if not latest_sync.empty:
            sync_time = latest_sync.iloc[0]["finished_at"] or latest_sync.iloc[0]["started_at"]
            sync_date = pd.to_datetime(sync_time).strftime("%Y-%m-%d")
            return pd.read_sql_query(f'''
                SELECT date, bank, account, balance, classification
                FROM balance_history
                WHERE date = {ph}
                ORDER BY classification, bank, account
            ''', conn, params=(sync_date,))

        return pd.read_sql_query('''
            SELECT date, bank, account, balance, classification
            FROM balance_history
            WHERE date = (SELECT MAX(date) FROM balance_history)
            ORDER BY classification, bank, account
        ''', conn)
    finally:
        conn.close()


def get_latest_balance_context():
    conn = get_connection()
    ph = '%s' if is_postgres() else '?'
    try:
        latest_snapshot_run = get_latest_balance_snapshot_run(conn)
        latest_sync = pd.read_sql_query('''
            SELECT id, started_at, finished_at, status, accounts_seen, accounts_included,
                   accounts_skipped, transactions_seen, transactions_inserted, duplicates,
                   COALESCE(balance_accounts_seen, 0) AS balance_accounts_seen,
                   sync_start_date, sync_end_date, error
            FROM sync_runs
            WHERE status = 'success'
            ORDER BY id DESC
            LIMIT 1
        ''', conn)

        if latest_sync.empty and latest_snapshot_run.empty:
            fallback = pd.read_sql_query('''
                SELECT date, bank, account, balance, classification
                FROM balance_history
                WHERE date = (SELECT MAX(date) FROM balance_history)
                ORDER BY classification, bank, account
            ''', conn)
            return {
                "latest_sync": pd.DataFrame(),
                "balances": fallback,
                "snapshot_date": fallback["date"].iloc[0] if not fallback.empty else "",
                "balance_accounts_seen": len(fallback),
                "has_successful_sync": False,
                "latest_sync_returned_no_balances": False,
            }

        if not latest_snapshot_run.empty:
            snapshot = latest_snapshot_run.iloc[0]
            sync_date = snapshot["snapshot_date"]
            balance_accounts_seen = int(snapshot.get("account_count") or 0)
        else:
            sync = latest_sync.iloc[0]
            sync_time = sync["finished_at"] or sync["started_at"]
            sync_date = pd.to_datetime(sync_time).strftime("%Y-%m-%d")
            balance_accounts_seen = int(sync.get("balance_accounts_seen") or 0)

        balances = pd.read_sql_query(f'''
            SELECT date, bank, account, balance, classification
            FROM balance_history
            WHERE date = {ph}
            ORDER BY classification, bank, account
        ''', conn, params=(sync_date,))
        return {
            "latest_sync": latest_sync,
            "balances": balances,
            "snapshot_date": sync_date,
            "balance_accounts_seen": balance_accounts_seen,
            "has_successful_sync": not latest_sync.empty,
            "latest_sync_returned_no_balances": balance_accounts_seen == 0,
        }
    finally:
        conn.close()


def get_balance_freshness(as_of_date=None):
    history = get_balance_history_details()
    if history.empty:
        return pd.DataFrame(columns=[
            "bank", "account", "balance_unchanged_since", "days_balance_unchanged"
        ])

    history = history.copy()
    history["date"] = pd.to_datetime(history["date"])
    if as_of_date is None:
        as_of = history["date"].max()
    else:
        as_of = pd.to_datetime(as_of_date)

    rows = []
    for (bank, account), group in history.sort_values("date").groupby(["bank", "account"]):
        group = group.sort_values("date")
        latest = group.iloc[-1]
        latest_balance = latest["balance"]
        unchanged_since = latest["date"]

        for _, row in group.iloc[:-1][::-1].iterrows():
            if row["balance"] != latest_balance:
                break
            unchanged_since = row["date"]

        rows.append({
            "bank": bank,
            "account": account,
            "balance_unchanged_since": unchanged_since.strftime("%Y-%m-%d"),
            "days_balance_unchanged": int((as_of - unchanged_since).days),
        })

    return pd.DataFrame(rows)


def save_sync_report(report):
    conn = get_connection()
    c = conn.cursor()
    ph = '%s' if is_postgres() else '?'
    account_results = report.get('accounts', [])
    accounts_included = sum(1 for item in account_results if item.get('included'))
    accounts_skipped = sum(1 for item in account_results if not item.get('included'))
    values = (
        report.get('started_at'),
        report.get('finished_at'),
        report.get('status'),
        len(account_results),
        accounts_included,
        accounts_skipped,
        report.get('transactions_seen', 0),
        report.get('transactions_inserted', 0),
        report.get('duplicates', 0),
        report.get('balance_accounts_seen', 0),
        report.get('sync_start_date'),
        report.get('sync_end_date'),
        report.get('error', '')
    )
    if is_postgres():
        c.execute(f'''
            INSERT INTO sync_runs
            (started_at, finished_at, status, accounts_seen, accounts_included, accounts_skipped,
             transactions_seen, transactions_inserted, duplicates, balance_accounts_seen,
             sync_start_date, sync_end_date, error)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            RETURNING id
        ''', values)
        sync_run_id = c.fetchone()[0]
    else:
        c.execute(f'''
            INSERT INTO sync_runs
            (started_at, finished_at, status, accounts_seen, accounts_included, accounts_skipped,
             transactions_seen, transactions_inserted, duplicates, balance_accounts_seen,
             sync_start_date, sync_end_date, error)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        ''', values)
        sync_run_id = c.lastrowid

    for item in account_results:
        c.execute(f'''
            INSERT INTO sync_account_results
            (sync_run_id, bank, account, included, skip_reason, transaction_count,
             inserted_count, duplicate_count, latest_transaction_date, balance, currency,
             health_status, error)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        ''', (
            sync_run_id,
            item.get('bank'),
            item.get('account'),
            bool(item.get('included')),
            item.get('skip_reason', ''),
            item.get('transaction_count', 0),
            item.get('inserted_count', 0),
            item.get('duplicate_count', 0),
            item.get('latest_transaction_date', ''),
            item.get('balance', None),
            item.get('currency', ''),
            item.get('health_status', ''),
            item.get('error', '')
        ))

    conn.commit()
    conn.close()
    return sync_run_id


def get_latest_sync_account_results():
    conn = get_connection()
    latest = pd.read_sql_query('''
        SELECT id, started_at, finished_at, status, accounts_seen, accounts_included,
               accounts_skipped, transactions_seen, transactions_inserted, duplicates,
               COALESCE(balance_accounts_seen, 0) AS balance_accounts_seen,
               sync_start_date, sync_end_date, error
        FROM sync_runs
        ORDER BY id DESC
        LIMIT 1
    ''', conn)
    if latest.empty:
        conn.close()
        return latest, pd.DataFrame()
    run_id = int(latest.iloc[0]['id'])
    accounts = pd.read_sql_query(f'''
        SELECT bank, account, included, skip_reason, transaction_count, inserted_count,
               duplicate_count, latest_transaction_date, balance, currency, health_status, error
        FROM sync_account_results
        WHERE sync_run_id = {run_id}
        ORDER BY included DESC, bank, account
    ''', conn)
    conn.close()
    return latest, accounts


def save_ml_artifact(name, artifact_bytes, metadata):
    import json

    ensure_ml_artifacts_table()
    conn = get_connection()
    c = conn.cursor()
    ph = '%s' if is_postgres() else '?'
    trained_at = datetime.now().isoformat(timespec='seconds')
    metadata_json = json.dumps(metadata, default=str)
    if is_postgres():
        c.execute(f'''
            INSERT INTO ml_artifacts (name, artifact, trained_at, metadata)
            VALUES ({ph}, {ph}, {ph}, {ph})
            ON CONFLICT (name) DO UPDATE SET
                artifact = EXCLUDED.artifact,
                trained_at = EXCLUDED.trained_at,
                metadata = EXCLUDED.metadata
        ''', (name, psycopg2.Binary(artifact_bytes), trained_at, metadata_json))
    else:
        c.execute(f'''
            INSERT OR REPLACE INTO ml_artifacts (name, artifact, trained_at, metadata)
            VALUES ({ph}, {ph}, {ph}, {ph})
        ''', (name, artifact_bytes, trained_at, metadata_json))
    conn.commit()
    conn.close()
    return trained_at


def load_ml_artifact(name):
    ensure_ml_artifacts_table()
    conn = get_connection()
    df = pd.read_sql_query("SELECT artifact, trained_at, metadata FROM ml_artifacts WHERE name = %s" if is_postgres() else "SELECT artifact, trained_at, metadata FROM ml_artifacts WHERE name = ?", conn, params=(name,))
    conn.close()
    if df.empty:
        return None
    row = df.iloc[0]
    artifact = row['artifact']
    if isinstance(artifact, memoryview):
        artifact = artifact.tobytes()
    return {
        'artifact': artifact,
        'trained_at': row['trained_at'],
        'metadata': row['metadata']
    }
