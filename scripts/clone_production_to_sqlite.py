import argparse
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from urllib.parse import urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TABLES = [
    "transactions",
    "balance_history",
    "sync_runs",
    "sync_account_results",
    "ml_artifacts",
]


def get_production_dsn():
    dsn = (
        os.getenv("MONEY_TRACKER_PRODUCTION_DB_URL")
        or os.getenv("DB_CONNECTION_STRING")
        or os.getenv("DIRECT_CONNECTION")
    )
    if dsn:
        return dsn

    try:
        import app_secrets

        return (
            getattr(app_secrets, "DB_CONNECTION_STRING", None)
            or getattr(app_secrets, "DIRECT_CONNECTION", None)
        )
    except ImportError:
        return None


def prepare_postgres_dsn(dsn):
    if "sslmode" not in dsn and "localhost" not in dsn:
        dsn += "&sslmode=require" if "?" in dsn else "?sslmode=require"

    try:
        import socket

        parsed = urlparse(dsn)
        hostname = parsed.hostname
        if hostname and "supabase.co" in hostname:
            ipv4 = socket.gethostbyname(hostname)
            parsed = parsed._replace(netloc=parsed.netloc.replace(hostname, ipv4))
            return urlunparse(parsed)
    except Exception:
        return dsn

    return dsn


def normalize_dataframe(df):
    for column in df.columns:
        df[column] = df[column].map(lambda value: value.tobytes() if isinstance(value, memoryview) else value)
    return df


def clone_production_to_sqlite(output_path, overwrite=False):
    dsn = get_production_dsn()
    if not dsn:
        raise RuntimeError(
            "Production DB URL not found. Set MONEY_TRACKER_PRODUCTION_DB_URL "
            "or provide DB_CONNECTION_STRING in app_secrets.py."
        )

    output = Path(output_path)
    if output.exists():
        if not overwrite:
            raise RuntimeError(f"{output} already exists. Re-run with --overwrite to replace it.")
        output.unlink()

    os.environ["MONEY_TRACKER_ENV"] = "qa"
    os.environ["MONEY_TRACKER_DB_FILE"] = str(output)

    import db

    db.init_db()
    source = psycopg2.connect(prepare_postgres_dsn(dsn))
    target = sqlite3.connect(output)

    counts = {}
    try:
        for table in TABLES:
            df = pd.read_sql_query(f"SELECT * FROM {table}", source)
            df = normalize_dataframe(df)
            df.to_sql(table, target, if_exists="append", index=False)
            counts[table] = len(df)
        target.commit()
    finally:
        source.close()
        target.close()

    return {"output": str(output), "counts": counts}


def main():
    parser = argparse.ArgumentParser(description="Clone production Supabase data into a local SQLite QA database.")
    parser.add_argument("--output", default="tracker_qa.db", help="Destination SQLite file.")
    parser.add_argument("--overwrite", action="store_true", help="Replace the destination file if it exists.")
    args = parser.parse_args()

    result = clone_production_to_sqlite(args.output, overwrite=args.overwrite)
    print(f"Cloned production data to {result['output']}")
    for table, count in result["counts"].items():
        print(f"  {table}: {count} rows")


if __name__ == "__main__":
    main()
