# Money Tracker

A personal finance dashboard built with Streamlit. It ingests account and
transaction data from SimpleFIN, stores reviewed transactions, tracks net worth,
and exposes connection health so stale or duplicate institution links are easier
to diagnose.

This project intentionally stays on Streamlit for now. The current priority is
data correctness, local QA safety, sync observability, and maintainable backend
modules before considering a React rewrite.

## What The App Does

### Inbox

The Inbox is the review queue for new transaction activity.

- SimpleFIN transaction sync inserts only accounts that should be reviewed in
  the Inbox, such as checking and card accounts.
- Investment, retirement, restricted, and savings-style accounts are excluded
  from Inbox transaction review to avoid noisy brokerage activity.
- New rows are inserted with `status='PENDING'`.
- Approving a row moves it to `REVIEWED` and records review audit fields:
  `reviewed_at`, `reviewed_by`, and `review_source`.
- Transaction source fields from SimpleFIN are persisted when available:
  `account`, `posted_date`, `details`, and `raw_data`.
- Duplicate protection uses SimpleFIN IDs when present and preserves a legacy
  hash guard so old reviewed rows do not reappear just because their IDs changed.
  That guard is narrowed by account or method when possible so unrelated
  same-amount transactions are not suppressed.

Admin tools in the Inbox also include the manual E*Trade stock income form and a
missing E*Trade salary warning for recent months.

### Connections

Connections is the operational SimpleFIN health view.

It shows the latest sync run and account-level results:

- bank and account name
- whether the account is used in the Inbox
- whether the account is used in Net Worth
- transaction count seen in the latest sync window
- inserted and duplicate transaction counts
- latest transaction date returned by SimpleFIN
- latest returned balance and currency
- connection health
- balance staleness and recommended action

Health is intentionally practical rather than overly clever:

- `Healthy`: SimpleFIN returned transactions or a balance and no app action is
  needed.
- `Healthy, no activity`: SimpleFIN returned a balance but no transactions in
  the current transaction window.
- `Possibly stale`: investment or retirement-style balance has not changed for
  30 or more days.
- `Needs review`: SimpleFIN returned neither balance nor transaction activity.
- `Duplicate`: the app detected a duplicate SimpleFIN connection row and is
  ignoring it for app behavior.

Duplicate connection rows are hidden by default but can be shown for audit.
The Fidelity duplicate rule is intentionally account-level and prefers
`Fidelity Investments` over `Fidelity 401k` for matching account names. If a
preferred Fidelity account appears stale, the intended fix is to reconnect that
preferred SimpleFIN institution rather than switch back and forth between
duplicate sources.

### Unified Bank Sync

Every `Sync with Banks` button calls the same `sync_simplefin.sync()` function.
There are no separate sync semantics per tab.

A successful sync:

1. Fetches SimpleFIN accounts once.
2. Detects duplicate connections.
3. Saves a structured sync run and per-account sync results.
4. Replaces today's canonical balance snapshot from the fetched accounts.
5. Inserts only Inbox-eligible transactions.
6. Records inserted and duplicate transaction counts.

This means Inbox, Connections, and Net Worth all reflect the same SimpleFIN
refresh. The Net Worth tab no longer calls SimpleFIN directly.

If a successful sync returns zero balance rows, today's balance snapshot is
cleared. Net Worth is anchored to the latest successful sync date, so it will not
silently fall back to older balances and pretend they are current.

### Net Worth

Net Worth is a read-only view of the latest saved canonical balance snapshot.

It shows:

- Total Net Worth
- Cash
- Taxable Investments
- Retirement / Restricted
- Liabilities
- historical total net worth chart
- account-level Asset Breakdown

Asset classification lives in `account_classifier.py` and is based on durable
account characteristics instead of exact suffixes like `(0072)`.

Current classes:

- `Cash`: checking, savings, and cash-like accounts.
- `Taxable Investments`: brokerage, stock plan, crypto, Robinhood individual,
  E*Trade individual brokerage, and similar non-retirement investments.
- `Retirement / Restricted`: 401k, IRA, Roth IRA, HSA brokerage, and retirement
  or restricted accounts.
- `Liability`: credit cards and debt balances.

E*Trade Stock Plan is classified as `Taxable Investments`.

### ML Assistant

The ML model is an assistant, not an authority.

- SimpleFIN sync may propose category/type values for new pending transactions.
- Low-confidence predictions are marked in user notes for review.
- Training uses reviewed transactions only, not pending predictions.
- Training feedback reports category/type model status, sample counts, reviewed
  sample counts, save status, warnings, and timestamp.
- Model artifacts can be saved to the database through `ml_artifacts`, so
  Streamlit Cloud filesystem resets do not make model persistence disappear.

## Environment Modes

The app uses explicit environment modes from `config.py`.

Valid modes:

- `local`
- `qa`
- `test`
- `production`

Default mode is `local`.

Database behavior:

- `local`: SQLite, default `tracker.db`
- `qa`: SQLite, default `tracker_qa.db`
- `test`: SQLite, default `tracker_test.db`
- `production`: Supabase/Postgres from Streamlit secrets or `app_secrets.py`

The app only uses the production database when:

- `MONEY_TRACKER_ENV=production`, or
- `MONEY_TRACKER_USE_PRODUCTION_DB=1`

This is deliberate. A local app run should not mutate production unless you
explicitly opt in.

## Local Development

Create a virtual environment and install dependencies:

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install -r requirements-dev.txt
```

Run the app locally:

```bash
MONEY_TRACKER_ENV=local ./venv/bin/streamlit run app.py
```

Open:

```text
http://localhost:8501
```

Local SimpleFIN sync defaults to a recent 30-day transaction window so a fresh
SQLite DB does not reopen months of already-reviewed transactions. Override it
with:

```bash
MONEY_TRACKER_LOCAL_SYNC_DAYS=90 ./venv/bin/streamlit run app.py
MONEY_TRACKER_SIMPLEFIN_START_DATE=2025-12-01 ./venv/bin/streamlit run app.py
```

## QA With Production-Like Data

QA mode is the preferred way to test real data without production side effects.

Clone production into a local SQLite QA database:

```bash
MONEY_TRACKER_ENV=production ./venv/bin/python scripts/clone_production_to_sqlite.py --output tracker_qa.db
```

Run the app against that QA database:

```bash
MONEY_TRACKER_ENV=qa MONEY_TRACKER_DB_FILE=tracker_qa.db ./venv/bin/streamlit run app.py
```

QA sync still uses SimpleFIN credentials for fetching current bank data, but it
writes transactions, sync runs, sync account results, ML artifacts, and balance
history to the local SQLite QA file.

## Production

For Streamlit Cloud, configure secrets including:

```toml
MONEY_TRACKER_ENV = "production"
DB_CONNECTION_STRING = "..."
SIMPLEFIN_ACCESS_URL = "..."
ADMIN_PASSWORD = "..."
VIEWER_PASSWORD = "..."
EXPENSE_PASSWORD = "..."
```

Production uses Supabase/Postgres only when production mode is explicit.

## Data Repair

### Backfill Transaction Source Fields

Use the backfill script to recover `account`, `posted_date`, and `details` from
existing `raw_data`.

Dry run:

```bash
./venv/bin/python scripts/backfill_transaction_fields.py
```

Apply:

```bash
./venv/bin/python scripts/backfill_transaction_fields.py --apply
```

The script:

- defaults to dry-run mode
- prints total candidate rows
- prints recoverable rows
- prints skipped rows
- shows example changes
- only updates null or empty destination fields

Use production mode intentionally if repairing production:

```bash
MONEY_TRACKER_ENV=production ./venv/bin/python scripts/backfill_transaction_fields.py --apply
```

## Tests

Run tests with an isolated test SQLite database:

```bash
MONEY_TRACKER_ENV=test PYTHONPYCACHEPREFIX=/private/tmp/money_tracker_pycache ./venv/bin/python -m pytest tests
```

The test suite covers:

- environment/config behavior
- SQLite transaction integrity
- reviewed audit fields
- legacy duplicate guards
- account classification
- SimpleFIN sync reports
- duplicate Fidelity connection handling
- canonical balance snapshots
- empty successful syncs
- data repair backfill behavior
- ML training status and reviewed-only training

## Project Structure

- `app.py`: Streamlit UI and tab layout.
- `db.py`: SQLite/Postgres database abstraction, migrations, sync history,
  balance snapshots, transaction review, and ML artifact persistence.
- `sync_simplefin.py`: SimpleFIN fetch, normalization, duplicate connection
  handling, Inbox transaction insertion, sync reports, and canonical balance
  snapshot writes.
- `account_classifier.py`: Account classification and Inbox inclusion rules.
- `config.py`: Environment mode and database selection.
- `ml_utils.py`: Training, prediction, status reporting, and durable artifact
  save/load.
- `data_repair.py`: Backfill helpers for repairing transaction fields.
- `scripts/backfill_transaction_fields.py`: CLI for transaction source-field
  backfill.
- `scripts/clone_production_to_sqlite.py`: Production-to-local SQLite clone for
  QA.
- `tests/`: Focused pytest coverage using isolated SQLite databases.

## Security Notes

- Do not commit `app_secrets.py`, local SQLite databases, or Streamlit secrets.
- SimpleFIN is read-only from the app perspective.
- QA mode is for real-data testing without Supabase writes.
- Production database writes should happen only through explicit production
  mode.

