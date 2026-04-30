import argparse
import ast

import pandas as pd

import db


RECOVERABLE_FIELDS = ["account", "posted_date", "details"]


def parse_raw_payload(raw_data):
    if not raw_data:
        return {}
    if isinstance(raw_data, dict):
        return raw_data
    try:
        parsed = ast.literal_eval(str(raw_data))
        return parsed if isinstance(parsed, dict) else {}
    except (SyntaxError, ValueError):
        return {}


def recover_transaction_fields(row):
    payload = parse_raw_payload(row.get("raw_data"))
    recovered = {}
    for field in RECOVERABLE_FIELDS:
        current = row.get(field)
        if current not in (None, ""):
            continue
        value = payload.get(field)
        if value not in (None, ""):
            recovered[field] = value
    return recovered


def backfill_transaction_fields(apply=False, limit=None):
    conn = db.get_connection()
    where = " OR ".join([f"{field} IS NULL OR {field} = ''" for field in RECOVERABLE_FIELDS])
    q = f"SELECT id, raw_data, account, posted_date, details FROM transactions WHERE {where}"
    if limit:
        q += f" LIMIT {int(limit)}"
    df = pd.read_sql_query(q, conn)

    candidates = []
    skipped = 0
    for _, row in df.iterrows():
        recovered = recover_transaction_fields(row)
        if recovered:
            candidates.append((row["id"], recovered))
        else:
            skipped += 1

    if apply and candidates:
        c = conn.cursor()
        ph = "%s" if db.is_postgres() else "?"
        for tx_id, recovered in candidates:
            assignments = []
            params = []
            for field, value in recovered.items():
                assignments.append(f"{field} = {ph}")
                params.append(value)
            params.append(tx_id)
            c.execute(
                f"UPDATE transactions SET {', '.join(assignments)} WHERE id = {ph}",
                params,
            )
        conn.commit()

    conn.close()
    return {
        "apply": apply,
        "candidate_rows": len(df),
        "recoverable_rows": len(candidates),
        "skipped_rows": skipped,
        "examples": candidates[:5],
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill missing transaction fields from raw_data.")
    parser.add_argument("--apply", action="store_true", help="Write recovered fields to the database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit candidate rows for inspection.")
    args = parser.parse_args()

    result = backfill_transaction_fields(apply=args.apply, limit=args.limit)
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Mode: {mode}")
    print(f"Candidate rows: {result['candidate_rows']}")
    print(f"Recoverable rows: {result['recoverable_rows']}")
    print(f"Skipped rows: {result['skipped_rows']}")
    print("Examples:")
    for tx_id, fields in result["examples"]:
        print(f"  {tx_id}: {fields}")
    if not args.apply:
        print("No changes written. Re-run with --apply to update recoverable rows.")


if __name__ == "__main__":
    main()
