# 💰 Money Tracker

An advanced, personal finance dashboard built with **Streamlit** (Python).
It aggregates data from **SimpleFin** (Banks, Credit Cards) and provides powerful insights, net worth tracking, and cash flow analysis.

## ✨ Features

### 📊 Dashboard 2.0
*   **Time Travel**: Filter by "All Time", "Year to Date", "This Month", or "This Week".
*   **Net Worth Tracking**: Automated daily snapshots of all account balances.
    *   **Liquidity Analysis**: Split assets into "Liquid" (Cash/Checking) vs "Locked" (Retirement/Investments).
    *   **History Chart**: Visual timeline of your total net worth.
*   **Monthly Cash Flow**: Bar chart comparing Income vs Expenses over time (with chronological sorting).
*   **Category Breakdown**: Donut charts showing where your money goes.

### ☁️ Cloud Ready
*   **Hybrid Database**:
    *   **Local Dev**: Uses SQLite (`tracker.db`) for speed and privacy.
    *   **Production**: Seamlessly switches to **PostgreSQL** (Supabase) when `DB_CONNECTION_STRING` is detected.
*   **Deployment**: Ready for **Streamlit Cloud** deployment with custom domain support. (See [Deployment Guide](deploy_to_cloud.md))

### 🧹 Data Hygiene
*   **Auto-Categorization**: Rules-based engine to tag transactions.
*   **Noise Filtering**: Automatically ignores internal transfers and specific investment account noise.
*   **Inbox Workflow**: "Inbox Zero" style interface for categorizing pending transactions.
### 🔐 Authentication & Security
*   **Role-Based Access**:
    *   **Admin**: Full access (Sync, Approve, Edit, Upload).
    *   **Full Viewer**: Read-only access to all data (including Net Worth).
    *   **Expense Viewer**: "Privacy Mode" - Hides Net Worth, Income, and Investments (Expenses Only).
*   **Cloud Secrets**: Passwords and Keys managed securely via `st.secrets`.

### 📱 Venmo Integration
*   **CSV Import**: "Smart" uploader for Venmo CSVs.
    *   **Deduplication**: Matches against existing bank transactions to enrich data (merges "VENMO PAYMENT" with "Sushi with Friends").
    *   **Categorization**: Auto-tags Transfers and Reimbursements.
*   **Data Helper**: Generates dynamic download links for recent statement periods.

## 🚀 Getting Started

### Prerequisites
*   Python 3.10+
*   SimpleFin Bridge Account (for data syncing)

### Installation
1.  Clone the repo.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Set up secrets:
    *   Create `app_secrets.py` containing:
        ```python
        DB_CONNECTION_STRING = "..."
        SIMPLEFIN_ACCESS_URL = "..."
        ADMIN_PASSWORD = "..."
        VIEWER_PASSWORD = "..."
        EXPENSE_PASSWORD = "..."
        ```

### Running Locally
```bash
streamlit run app.py
```

### Syncing Data
Refreshes data from SimpleFin and saves to database:
```bash
python sync_simplefin.py
```

## 📂 Project Structure

*   `app.py`: Main Streamlit application.
*   `db.py`: Database abstraction layer (SQLite/Postgres).
*   `sync_simplefin.py`: Script to fetch and normalize bank data.
*   `scripts/`: Utility scripts for migration and maintenance.
    *   `migrate_to_postgres.py`: Move local data to Cloud DB.
    *   `cleanup_noise.py`: Remove unwanted transactions.

## 🔒 Security
*   **Bank Data**: Accessed strictly via read-only Token (SimpleFin).
*   **Credentials**: Stored in `app_secrets.py` (GitIgnored) or Cloud Secrets.
*   **Privacy**: Data is self-hosted (or on your private Supabase).

---
*Built with ❤️ by Antigravity*
