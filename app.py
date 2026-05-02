import altair as alt
import streamlit as st
import pandas as pd
import db
import sync_simplefin
import account_classifier
import math
from datetime import datetime, timedelta
import time


def is_duplicate_connection(skip_reason):
    return str(skip_reason or "").startswith("duplicate_connection")


def has_balance(value):
    return pd.notna(value)


def used_in_net_worth(row):
    return not is_duplicate_connection(row.get("skip_reason")) and has_balance(row.get("balance"))


def connection_action(row):
    if is_duplicate_connection(row.get("skip_reason")):
        return "No action"
    if bool(row.get("possibly_stale")):
        return "Check SimpleFIN"
    if not has_balance(row.get("balance")) and int(row.get("transaction_count", 0) or 0) == 0:
        return "Check SimpleFIN"
    if bool(row.get("included")) and int(row.get("transaction_count", 0) or 0) == 0:
        return "Check if activity expected"
    return "No action"


def connection_health_label(row):
    if is_duplicate_connection(row.get("skip_reason")):
        return "Duplicate"
    if bool(row.get("possibly_stale")):
        return "Possibly stale"
    return row.get("health_status", "Needs review")


def balance_status_label(row):
    if is_duplicate_connection(row.get("skip_reason")):
        return "Duplicate"
    if pd.isna(row.get("balance")):
        return "No balance returned"
    if bool(row.get("possibly_stale")):
        return "Possibly stale"
    return "Balance returned"


def render_bank_sync_button(key="sync_with_banks"):
    if ROLE != 'admin':
        st.caption("Syncing disabled for Viewers")
        return
    if st.button("🔄 Sync with Banks", key=key):
        with st.spinner("Fetching latest data..."):
            try:
                report = sync_simplefin.sync()
                if report and report.get('status') == 'success':
                    st.success(
                        f"Sync complete: {report.get('transactions_inserted', 0)} new, "
                        f"{report.get('duplicates', 0)} duplicates."
                    )
                    st.session_state['last_sync_report'] = report
                else:
                    st.error(f"Sync failed: {(report or {}).get('error', 'unknown error')}")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")


# Secrets Management (Cloud vs Local)
# Secrets Management (Cloud vs Local)
SIMPLEFIN_ACCESS_URL = ""
ADMIN_PASSWORD = None
VIEWER_PASSWORD = None
EXPENSE_PASSWORD = None

# 1. Try Streamlit Secrets
try:
    if hasattr(st, 'secrets'):
        SIMPLEFIN_ACCESS_URL = st.secrets.get("SIMPLEFIN_ACCESS_URL", "")
        ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", None)
        VIEWER_PASSWORD = st.secrets.get("VIEWER_PASSWORD", None)
        EXPENSE_PASSWORD = st.secrets.get("EXPENSE_PASSWORD", None)
except:
    pass

# 2. Try Local app_secrets.py (Override if present, or fallback?)
# Usually Local takes precedence during dev, but let's stick to: if not found, check local.
try:
    import app_secrets as secrets
    if not SIMPLEFIN_ACCESS_URL:
        SIMPLEFIN_ACCESS_URL = getattr(secrets, 'SIMPLEFIN_ACCESS_URL', "")
    if not ADMIN_PASSWORD:
        ADMIN_PASSWORD = getattr(secrets, 'ADMIN_PASSWORD', None)
    if not VIEWER_PASSWORD:
        VIEWER_PASSWORD = getattr(secrets, 'VIEWER_PASSWORD', None)
    if not EXPENSE_PASSWORD:
        EXPENSE_PASSWORD = getattr(secrets, 'EXPENSE_PASSWORD', None)
except ImportError:
    pass

st.set_page_config(page_title="Money Tracker", layout="wide")

# ---------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------
def check_password():
    """Returns 'admin', 'full_viewer', 'expense_viewer', or None"""
    if 'role' not in st.session_state:
        st.session_state['role'] = None

    if st.session_state['role']:
        return st.session_state['role']

    # Login Form
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Login")
        pwd = st.text_input("Enter Password", type="password")
        
        if pwd:
            if ADMIN_PASSWORD and pwd == ADMIN_PASSWORD:
                st.session_state['role'] = 'admin'
                st.rerun()
            
            if VIEWER_PASSWORD and pwd == VIEWER_PASSWORD:
                st.session_state['role'] = 'full_viewer'
                st.rerun()
                
            if EXPENSE_PASSWORD and pwd == EXPENSE_PASSWORD:
                st.session_state['role'] = 'expense_viewer'
                st.rerun()
                
            st.error("Incorrect password")
            
    return None

ROLE = check_password()

if not ROLE:
    st.stop()

# Privacy Flag
SHOW_SENSITIVE = (ROLE in ['admin', 'full_viewer'])

# Sidebar Info
with st.sidebar:
    role_display = {
        'admin': 'Admin',
        'full_viewer': 'Full Viewer',
        'expense_viewer': 'Expense Viewer (Privacy Mode)'
    }
    st.write(f"Logged in as: **{role_display.get(ROLE, ROLE)}**")
    if st.button("Logout"):
        st.session_state['role'] = None
        st.rerun()

    st.divider()
    
    # Admin Features
    if ROLE == 'admin':
        if st.button("🧠 Train ML Model"):
            with st.spinner("Training model..."):
                import ml_utils
                report = ml_utils.classifier.train()
                if report.get('status') == 'success':
                    st.success("Training complete")
                else:
                    st.warning(f"Training status: {report.get('status')}")
                st.caption(
                    f"Category: {report.get('category_model')} "
                    f"({report.get('category_samples', 0)} samples) | "
                    f"Type: {report.get('type_model')} "
                    f"({report.get('type_samples', 0)} samples)"
                )
                st.caption(
                    f"Training data: {report.get('reviewed_samples', 0)} reviewed "
                    f"of {report.get('total_samples', 0)} total transactions"
                )
                st.caption(
                    f"Saved file: {report.get('model_saved_file')} | "
                    f"Saved DB: {report.get('model_saved_database')} | "
                    f"Trained at: {report.get('trained_at')}"
                )
                for warning in report.get('warnings', []):
                    st.warning(warning)
        try:
            import ml_utils
            ml_status = ml_utils.classifier.get_status()
            st.caption(
                f"ML loaded: {ml_status.get('category_model_loaded') or ml_status.get('type_model_loaded')} "
                f"from {ml_status.get('load_source') or 'none'}"
            )
        except Exception:
            pass
        with st.expander("📥 Import Data"):
            st.caption("1. Get CSV from Venmo")
            # Dynamic Link Generation
            today = datetime.now()
            thirty_days_ago = today - timedelta(days=30)
            
            s_str = thirty_days_ago.strftime('%Y-%m-%d')
            e_str = today.strftime('%Y-%m-%d')
            
            venmo_url = f"https://account.venmo.com/api/statement/download?startDate={s_str}&endDate={e_str}&csv=true"
            
            st.markdown(f"[Download Last 30 Days CSV]({venmo_url})")
            st.caption(f"({s_str} to {e_str})")
            
            st.caption("2. Upload Venmo CSV")
            uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
            
            if uploaded_file is not None:
                if st.button("Process Venmo CSV"):
                    try:
                        # 1. Read CSV (Skip first 2 rows usually, looking for Header)
                        # We'll try to find the header row dynamically or hardcode skiprows=2
                        # Based on inspection, header is on row 3 (index 2)
                        
                        df = pd.read_csv(uploaded_file, header=2)
                        
                        # Validate Columns
                        required_cols = ['ID', 'Datetime', 'Type', 'Status', 'Note', 'From', 'To', 'Amount (total)']
                        # Note: The file has a leading comma? So first column might be unnamed. 
                        # 'ID' is the 2nd column in the raw text, but pandas might handle it if delimiter matches.
                        # Let's clean column names just in case.
                        df.columns = df.columns.str.strip()
                        
                        if 'ID' not in df.columns:
                            # Try reloading with different header?
                            # Or maybe the first column was Unnamed?
                            # Let's inspect columns from a temp read
                            pass
                            
                        # If 'ID' missing, maybe it's 'Unnamed: 1' if there was a leading comma.
                        # Using user file: ",ID,..." -> Valid CSV usually ignores leading empty field, or makes it "Unnamed: 0"
                        
                        processed_txs = []
                        
                        for _, row in df.iterrows():
                            # Skip if ID is NaN (footer rows)
                            if pd.isna(row['ID']):
                                continue
                                
                            # Parse ID
                            v_id = str(row['ID'])
                            
                            # Parse Date
                            v_date = pd.to_datetime(row['Datetime']).strftime('%Y-%m-%d')
                            
                            # Parse Amount
                            raw_amt_str = str(row['Amount (total)']) \
                                .replace('$', '') \
                                .replace(',', '') \
                                .replace(' ', '')
                            
                            # Handle Sign
                            # Venmo CSV: "+ $6.00" or "- $135.00"
                            # If "+", it's Positive (Reimbursement per user rule)
                            # If "-", it's Negative (Expense)
                            
                            is_positive = '+' in raw_amt_str or (not '-' in raw_amt_str and float(raw_amt_str) > 0)
                             # Clean symbol
                            clean_amt = float(raw_amt_str.replace('+', '').replace('-', ''))
                            
                            # Default Values
                            tx_type = 'Expense'
                            category = 'Uncategorized'
                            
                            # Logic
                            v_type = row['Type']
                            note = str(row['Note']) if not pd.isna(row['Note']) else ""
                            
                            # Description Construction
                            # Requested Format: "Venmo - From / To"
                            desc = f"Venmo - {row['From']} / {row['To']}"
                            
                            # Note goes to User Notes? Or appended?
                            # User example: "Sushi" as Note. 
                            # Let's put Note in 'user_notes' (which maps to 'Notes' column in Inbox)
                            # And maybe details?
                            
                            user_note = row['Note'] if not pd.isna(row['Note']) else ""
                                
                            # 1. Standard Transfer
                            if v_type == 'Standard Transfer':
                                tx_type = 'Transfer'
                                category = 'Transfer'
                                # Transfers usually negative (to bank)
                            
                            # 2. Positive Amount -> Reimbursement
                            elif is_positive:
                                tx_type = 'Reimbursement'
                                
                            # 3. Negative -> Expense
                            else:
                                tx_type = 'Expense'
                                
                            # Add to list
                            processed_txs.append({
                                'id': v_id, # Deduplication Key!
                                'date': v_date,
                                'amount': abs(clean_amt),
                                'description': desc,
                                'category': category,
                                'type': tx_type,
                                'method': 'Venmo',
                                'tags': 'venmo_import',
                                'user_notes': user_note,
                                'status': 'PENDING',
                                'raw_data': str(row.to_dict()),
                                'account': 'Venmo',
                                'posted_date': v_date,
                                'details': f"Statement Period: {row.get('Statement Period Venmo Fees', '')}"
                            })
                            
                        # Upsert
                        if processed_txs:
                            new_df = pd.DataFrame(processed_txs)
                            count = db.upsert_transactions(new_df)
                            st.success(f"Imported {count} new Venmo transactions!")
                            st.balloons()
                            # st.rerun() # Refresh to show in Inbox
                        else:
                            st.warning("No valid transactions found in file.")
                            
                    except Exception as e:
                        st.error(f"Error processing CSV: {e}")

# ---------------------------------------------------------
# APP LOGIC
# ---------------------------------------------------------


# --- Helper Function for Monthly Chart ---
def render_monthly_flow(df):
    if df.empty:
        return
    
    # 1. Group by Month
    df = df.copy()
    df['period'] = df['date'].dt.to_period('M')
    
    # 2. Calculate Nets (as Series with PeriodIndex)
    inc_mask = (df['type'] == 'Income') & (~df['category'].isin(['Transfer', 'Credit Card Payment']))
    monthly_inc = df[inc_mask].groupby('period')['amount'].sum()
    
    non_expense_cats = ['Transfer', 'Brokerage', 'Roth IRA', 'Credit Card Payment']
    non_reimb_cats = ['Transfer', 'Credit Card Payment']
    
    exp_mask = (df['type'] == 'Expense') & (~df['category'].isin(non_expense_cats))
    monthly_gross_exp = df[exp_mask].groupby('period')['amount'].sum()
    
    reimb_mask = (df['type'] == 'Reimbursement') & (~df['category'].isin(non_reimb_cats))
    monthly_reimb = df[reimb_mask].groupby('period')['amount'].sum()
    
    # 3. Align everything into one DataFrame (Outer Join on Period)
    combined = pd.DataFrame({
        'Income': monthly_inc,
        'Gross_Expense': monthly_gross_exp,
        'Reimbursement': monthly_reimb
    }).fillna(0)
    
    # Calculate Net Expense
    combined['Expense'] = combined['Gross_Expense'] - combined['Reimbursement']
    
    # Extract Index (Period) to Columns
    combined.index.name = 'period'
    chart_data = combined.reset_index()
    
    # Generate Helper Columns
    chart_data['Period'] = chart_data['period'].dt.to_timestamp() # For sorting
    chart_data['Label'] = chart_data['period'].dt.strftime('%b %Y') # For display
    
    # Melt for Altair
    long_df = chart_data.melt(
        id_vars=['Period', 'Label'], 
        value_vars=['Income', 'Expense'], 
        var_name='Type', 
        value_name='Amount'
    )
    
    # 4. Render Altair Chart
    st.subheader("Monthly Cash Flow")
    
    c = alt.Chart(long_df).mark_bar().encode(
        x=alt.X('Label', sort=alt.EncodingSortField(field="Period", order="ascending"), axis=alt.Axis(title=None, labelAngle=-45)),
        y=alt.Y('Amount', axis=alt.Axis(format='$,f')),
        color=alt.Color('Type', scale=alt.Scale(domain=['Income', 'Expense'], range=['#2ecc71', '#e74c3c'])), # Green/Red
        tooltip=['Label', 'Type', alt.Tooltip('Amount', format='$,.2f')]
    ).properties(height=300)
    
    st.altair_chart(c, use_container_width=True)

st.title("💸 Continuous Money Tracker")

# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📥 Inbox", "🔌 Connections", "📈 Trends", "💰 Net Worth", "🔎 Search"])

# ---------------------------------------------------------
# TAB 1: INBOX
# ---------------------------------------------------------
with tab1:
    header_col, sync_col = st.columns([3, 1])
    with header_col:
        st.markdown("### Review Pending Transactions")
        st.caption("Categorize and approve new transactions here.")
    with sync_col:
        render_bank_sync_button("sync_with_banks_inbox")

    # Load Pending Data
    pending_df = db.get_pending_transactions()
    
    if not pending_df.empty:
        # We need a key to ensure state persists
        # We want users to edit 'Category' and 'User Notes'
        # And select rows to 'Approve'
        
        # Add a 'Approve' checkbox column for bulk action? 
        # Actually, st.data_editor supports row selection if we want, 
        # OR we can just have an "Approve All" or "Approve Edited".
        
        # Let's try: "Edit everything, then click 'Approve ALL Visible'" strategy for simplicity first.
        # Or even better: "Approve Selected"
        
        pending_df['date'] = pd.to_datetime(pending_df['date']) # Fix for DateColumn config
        pending_df['Approve'] = False # Checkbox column
        
        # Define desired column order
        # User Request: Date, Type, Amount, Category, Description, Notes, Tags, Approve
        column_order = [
            "date", "account", "type", "amount", "category", 
            "description", "user_notes", "tags", "Approve"
        ]
        
        edited_df = st.data_editor(
            pending_df,
            column_order=column_order,
            column_config={
                "Approve": st.column_config.CheckboxColumn(
                    "Done?",
                    help="Check to mark as Reviewed",
                    default=False,
                    width="small"
                ),
                "account": st.column_config.TextColumn(
                    "Account",
                    help="Source Account",
                    disabled=True,
                    width="small"
                ),
                "type": st.column_config.SelectboxColumn(
                    "Type",
                    options=["Expense", "Income", "Reimbursement", "Investment", "Transfer"],
                    required=True,
                    width="medium"
                ),
                "category": st.column_config.SelectboxColumn(
                    "Category",
                    options=[
                        "Salary", "Interest Income", "Gift Income", "Rewards",
                        "Restaurants", "Fast Food", "Groceries", "Health", "Entertainment", "Travel",
                        "Gift Expense", "Gas", "Commute", "Subscriptions", "Personal Care",
                        "Shopping", "Supplies", "Phone", "Misc Expense", "Pass-Through (Reimbursed)",
                        "Misc Income", "Transfer",
                        "Brokerage", "Roth IRA",
                        "Donation"
                    ],
                    required=False, # Allow blank/None
                    width="medium"
                ),
                "amount": st.column_config.NumberColumn(
                    "Amount", format="$%.2f", width="small"
                ),
                "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", width="small"),
                "description": st.column_config.TextColumn("Description", disabled=True), # Read-only description usually safer? Or editable?
                "user_notes": st.column_config.TextColumn("Notes"),
                "tags": st.column_config.TextColumn(
                    "Tags",
                    help="Comma-separated tags (e.g. 'vacation, tax-deductible')"
                ),
                "id": None, # Hide ID
                "raw_data": None, # Hide Raw
                "status": None, # Hide Status
                "reviewed_at": None,
                "reviewed_by": None,
                "review_source": None
            },
            hide_index=True,
            use_container_width=True,
            key="inbox_editor_v2" # Change key to force refresh
        )
        
        # Logic to save changes back to DB
        # User edits the dataframe. We need to look for changes.
        
        # Separate Actions:
        # 1. Save Changes (Updates text/category in DB but keeps PENDING)
        # 2. Approve Selected (Updates text/category AND sets status=REVIEWED)
        
        col_a, col_b = st.columns(2)
        
        # We need to detect which rows were marked 'Approve' = True
        to_approve = edited_df[edited_df['Approve'] == True]
        
        if not to_approve.empty:
            if ROLE == 'admin':
                if st.button(f"✅ Approve {len(to_approve)} Transactions"):
                    # 1. Update text/category for these rows
                    # Iterate and update? Or bulk update? 
                    # DB module needs an 'update_transaction_details' function.
                    # For now let's just do it manually via a loop or update query if we add it to db.py
                    
                    # Let's just assume we want to mark them REVIEWED.
                    # But we also want to save their category/notes changes!
                    
                    # Hack: Update ALL edited rows in DB first
                    # (We'll skip this optimization for now and just update the Approved ones)
                    
                    for idx, row in to_approve.iterrows():
                        # Sanitize tags: If list, join by comma. If None, empty string.
                        raw_tags = row.get('tags', '')
                        if isinstance(raw_tags, list):
                            tags_str = ", ".join([str(t) for t in raw_tags])
                        else:
                            tags_str = str(raw_tags) if raw_tags is not None else ''

                        db.review_transaction(
                            row['id'],
                            row['category'], 
                            row['user_notes'], 
                            tags_str,
                            row['type'],
                            reviewed_by=ROLE,
                            review_source='manual',
                        )
                    
                    st.success("Transactions approved!")
                    st.rerun()
            else:
                 st.info("Log in as Admin to approve transactions.")

    else:
        st.info("🎉 All caught up! No pending transactions.")
        st.balloons()

    if ROLE == 'admin':
        st.divider()
        st.markdown("### Admin Tools")

        # --- Salary Reminder ---
        # Check last 6 months for missing salary
        missing_months = []
        conn = db.get_connection()
        try:
            # Check previous 6 months (excluding current)
            for i in range(1, 7):
                check_date = pd.Timestamp.now() - pd.DateOffset(months=i)
                m_str = check_date.strftime('%Y-%m')
                m_nice = check_date.strftime('%B %Y')

                # Query: Check for Income from E*Trade in that month
                q = f"SELECT date FROM transactions WHERE (account LIKE '%E*Trade%' OR method LIKE '%E*Trade%') AND type = 'Income' AND date LIKE '{m_str}%'"
                check_df = pd.read_sql_query(q, conn)

                if check_df.empty:
                    missing_months.append(m_nice)

            if missing_months:
                st.warning(f"⚠️ Missing E*Trade salary entries for: {', '.join(missing_months)}")
        except Exception as e:
            # st.error(e)
            pass
        finally:
            conn.close()

        # --- Manual Entry Form ---
        with st.expander("➕ Add Manual / E*Trade Transaction"):
            # REMOVED st.form to allow dynamic updates
            c1, c2 = st.columns(2)
            with c1:
                m_date = st.date_input("Date", value=datetime.now().date())
                m_desc = st.text_input("Description", value="E*Trade Income - Stock Plan")
            with c2:
                m_price = st.number_input("Purchase Price ($)", min_value=0.0, step=0.01, format="%.2f")
                m_qty = st.number_input("Quantity", min_value=0.0, step=0.001, format="%.3f")

            m_amount = m_price * m_qty
            st.info(f"Total Amount: **${m_amount:,.2f}**")

            if st.button("Add Transaction"):
                if m_amount > 0:
                    # Construct description to match historical format
                    # Format: "E*Trade Income (Manual: {qty} @ ${price})"
                    formatted_desc = f"E*Trade Income (Manual: {m_qty:.3f} @ ${m_price:.2f})"

                    new_tx = {
                        'date': m_date.strftime('%Y-%m-%d'),
                        'description': formatted_desc,
                        'amount': m_amount,
                        'category': 'Salary',
                        'type': 'Income',
                        'method': 'E*Trade - Manual', # Matches historical 'E*Trade - Manual'
                        'account': 'E*Trade',
                        'posted_date': m_date.strftime('%Y-%m-%d'),
                        'status': 'REVIEWED',
                        'user_notes': "Historical Salary/RSU/ESPP", # Matches historical notes
                        'tags': 'aspp', # Matches historical 'aspp' tag
                        'reviewed_by': ROLE,
                        'review_source': 'manual_etrade'
                    }

                    db.upsert_transactions(pd.DataFrame([new_tx]))
                    st.success("Transaction added!")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Amount must be greater than 0")

# ---------------------------------------------------------
# TAB 2: CONNECTIONS
# ---------------------------------------------------------
with tab2:
    st.header("🔌 SimpleFIN Connections")
    top_col, action_col = st.columns([3, 1])
    with top_col:
        st.caption("Connection health across Inbox and Net Worth.")
    with action_col:
        render_bank_sync_button("sync_with_banks_connections")

    try:
        latest_run, account_results = db.get_latest_sync_account_results()
        if latest_run.empty:
            st.info("No sync runs recorded yet.")
        else:
            run = latest_run.iloc[0]
            st.caption(
                f"Last sync: {run['status']} at {run['finished_at']} | "
                f"{run['transactions_inserted']} new, {run['duplicates']} duplicates | "
                f"{run.get('balance_accounts_seen', 0)} balances"
            )
            if run.get('sync_start_date') and run.get('sync_end_date'):
                st.caption(f"Transaction window: {run['sync_start_date']} to {run['sync_end_date']}")

            if not account_results.empty:
                display_sync = account_results.copy()
                display_sync['included'] = display_sync['included'].astype(bool)
                display_sync["Used in Inbox"] = display_sync["included"].map(lambda value: "Yes" if value else "No")
                display_sync["Used in Net Worth"] = display_sync.apply(
                    lambda row: "Yes" if used_in_net_worth(row) else "No",
                    axis=1,
                )
                freshness = db.get_balance_freshness()
                if not freshness.empty:
                    display_sync = display_sync.merge(
                        freshness,
                        on=["bank", "account"],
                        how="left",
                    )
                else:
                    display_sync["balance_unchanged_since"] = ""
                    display_sync["days_balance_unchanged"] = 0
                display_sync["Classification"] = display_sync.apply(
                    lambda row: account_classifier.classify_account(row["bank"], row["account"], row.get("balance")),
                    axis=1,
                )
                stale_classes = {
                    account_classifier.TAXABLE_INVESTMENTS,
                    account_classifier.RETIREMENT_RESTRICTED,
                }
                display_sync["possibly_stale"] = (
                    display_sync["Classification"].isin(stale_classes)
                    & display_sync["balance"].notna()
                    & (display_sync["days_balance_unchanged"].fillna(0) >= 30)
                    & ~display_sync["skip_reason"].fillna("").str.startswith("duplicate_connection")
                )
                display_sync["Connection Health"] = display_sync.apply(connection_health_label, axis=1)
                display_sync["Balance Status"] = display_sync.apply(balance_status_label, axis=1)
                display_sync["Action"] = display_sync.apply(connection_action, axis=1)

                show_duplicate_connections = st.checkbox(
                    "Show duplicate connection rows",
                    value=False,
                    help="Duplicate rows are still stored for audit, but the app prefers one connection for syncing.",
                )
                visible_sync = display_sync
                if not show_duplicate_connections:
                    visible_sync = display_sync[
                        ~display_sync["skip_reason"].fillna("").str.startswith("duplicate_connection")
                    ]

                needs_review_count = int((visible_sync["Action"] == "Check SimpleFIN").sum())
                healthy_count = int((visible_sync["Action"] == "No action").sum())
                data_count = int(
                    ((visible_sync["transaction_count"].fillna(0) > 0) | visible_sync["balance"].notna()).sum()
                )
                balance_count = int(visible_sync["balance"].notna().sum())
                inbox_count = int(visible_sync["included"].sum())
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Healthy", healthy_count, help="Visible connections with no action needed")
                m2.metric("Needs Review", needs_review_count, help="Visible connections that likely need a SimpleFIN check")
                m3.metric("Returning Data", data_count, help="Visible connections with a balance or transactions")
                m4.metric("Used in Inbox", inbox_count)
                m5.metric("Balances", balance_count, help="Visible connections with a balance returned by the latest sync")

                visible_sync = visible_sync.rename(columns={
                    "bank": "Bank",
                    "account": "Account",
                    "transaction_count": "Tx Seen",
                    "latest_transaction_date": "Latest Tx",
                    "balance": "Balance",
                    "currency": "Currency",
                    "balance_unchanged_since": "Balance Unchanged Since",
                    "days_balance_unchanged": "Days Unchanged",
                    "inserted_count": "New",
                    "duplicate_count": "Duplicates",
                    "error": "Error",
                })
                visible_sync = visible_sync[[
                    "Bank", "Account", "Connection Health", "Balance Status", "Used in Inbox", "Used in Net Worth",
                    "Tx Seen", "Latest Tx", "Balance", "Currency", "Balance Unchanged Since",
                    "Days Unchanged", "Action", "New", "Duplicates", "Error"
                ]]
                st.dataframe(visible_sync, use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption(f"Connection status unavailable: {e}")

# ---------------------------------------------------------
# TAB 3: TRENDS (The Payoff)
# ---------------------------------------------------------
# ---------------------------------------------------------
# TAB 3: DASHBOARD (Formerly Trends)
# ---------------------------------------------------------
with tab3:
    st.header("📊 Dashboard")
    
    all_df = db.get_all_transactions()
    
    if not all_df.empty:
        all_df['date'] = pd.to_datetime(all_df['date'], format='mixed')
        
        # --- Helper Function to Render Stats ---
        def render_dashboard_view(df, show_monthly_flow=False):
            if df.empty:
                st.info("No transactions in this period.")
                return

            # Filter Logic (Same as before)
            
            # Privacy Mode Filter
            if not SHOW_SENSITIVE:
                # Exclude Income and Investment from DataFrame
                df = df[~df['type'].isin(['Income', 'Investment'])]
            
            non_expense_cats = ['Transfer', 'Brokerage', 'Roth IRA', 'Credit Card Payment']
            non_reimb_cats = ['Transfer', 'Credit Card Payment']
            
            # Income
            inc_mask = (df['type'] == 'Income') & (~df['category'].isin(['Transfer', 'Credit Card Payment']))
            inc = df[inc_mask]['amount'].sum()
            
            # Expenses
            exp_mask = (df['type'] == 'Expense') & (~df['category'].isin(non_expense_cats))
            exp_df = df[exp_mask]
            gross_exp = exp_df['amount'].sum()
            
            # Reimbursements
            reimb_mask = (df['type'] == 'Reimbursement') & (~df['category'].isin(non_reimb_cats))
            reimbursements = df[reimb_mask]['amount'].sum()
            
            exp = gross_exp - reimbursements
            sav = inc - exp
            
            # Metrics
            k1, k2, k3 = st.columns(3)
            
            if not SHOW_SENSITIVE:
                 k1.metric("Total Income", "---")
                 k3.metric("Net Savings", "---")
            else:
                k1.metric("Total Income", f"${inc:,.0f}")
                k3.metric("Net Savings", f"${sav:,.0f}")
                
            k2.metric("Total Spent", f"${exp:,.0f}")
            
            # Charts
            st.subheader("Category Breakdown")
            
            # 1. Gross Expenses by Category
            gross_exp_by_cat = exp_df.groupby('category')['amount'].sum()
            
            # 2. Reimbursements by Category
            reimb_df = df[reimb_mask]
            reimb_by_cat = reimb_df.groupby('category')['amount'].sum()
            
            # 3. Net Expenses (Gross - Reimbursements)
            # Use .sub with fill_value=0 to handle categories that exist in one but not the other
            net_exp_by_cat = gross_exp_by_cat.sub(reimb_by_cat, fill_value=0)
            
            # 4. Sort and Display
            # We filter out <= 0 to keep the chart focused on "Expenses", 
            # unless user wants to see "Net Profit" categories? 
            # Standard breakdown usually implies "Where did I spend money?". 
            # If I made money on a category (Net < 0), it shouldn't be in expense breakdown.
            # But let's just show everything for transparency first.
            
            cat_df = net_exp_by_cat.sort_values(ascending=False)
            st.bar_chart(cat_df)
            
            # --- Monthly Cash Flow (Optional) ---
            if show_monthly_flow:
                render_monthly_flow(df)
            
            st.subheader("Transaction Log")
            display_df = df[['date', 'type', 'category', 'description', 'amount', 'status']].copy()
            st.dataframe(display_df, use_container_width=True)

        # --- Sub-Tabs ---
        sub1, sub2, sub3, sub4, sub5 = st.tabs(["All Time", "Year to Date", "This Month", "This Week", "Custom"])
        
        with sub1:
            st.caption("All transactions history")
            render_dashboard_view(all_df, show_monthly_flow=True)
            
        with sub2:
            current_year = pd.Timestamp.now().year
            st.caption(f"Activity for {current_year}")
            
            year_mask = all_df['date'].dt.year == current_year
            year_df = all_df[year_mask]
            render_dashboard_view(year_df, show_monthly_flow=True)
            
        with sub3:
            current_period = pd.Timestamp.now().to_period('M')
            st.caption(f"Activity for {current_period.strftime('%B %Y')}")
            
            # Filter for current month
            month_mask = all_df['date'].dt.to_period('M') == current_period
            month_df = all_df[month_mask]
            render_dashboard_view(month_df)
            
        with sub4:
            # Filter for current week (Monday start)
            now = pd.Timestamp.now()
            start_of_week = (now - pd.Timedelta(days=now.weekday())).normalize()
            st.caption(f"Activity since Monday, {start_of_week.strftime('%b %d')}")
            
            week_mask = all_df['date'] >= start_of_week
            week_df = all_df[week_mask]
            render_dashboard_view(week_df)
            
        with sub5:
            st.caption("Select a custom date range")
            
            # Date Picker
            today = pd.Timestamp.now().date()
            start_of_month = today.replace(day=1)
            
            c1, c2 = st.columns(2)
            with c1:
                custom_start = st.date_input("Start Date", value=start_of_month)
            with c2:
                custom_end = st.date_input("End Date", value=today)
            
            if custom_start <= custom_end:
                # Filter
                # Convert to Timestamp for comparison (since all_df['date'] is datetime)
                start_ts = pd.Timestamp(custom_start)
                end_ts = pd.Timestamp(custom_end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1) # End of day
                
                custom_mask = (all_df['date'] >= start_ts) & (all_df['date'] <= end_ts)
                custom_df = all_df[custom_mask]
                
                render_dashboard_view(custom_df, show_monthly_flow=True)
            else:
                st.error("Start Date must be before End Date.")
            
    else:
        st.write("No data yet.")

# ---------------------------------------------------------
# TAB 4: NET WORTH
# ---------------------------------------------------------
with tab4:
    st.header("Net Worth & Balances")
    
    col_r1, col_r2 = st.columns([3, 1])
    with col_r2:
        render_bank_sync_button("sync_with_banks_net_worth")
    
    if not SHOW_SENSITIVE:
        st.warning("🔒 Privacy Mode Enabled. Net Worth Hidden.")
        st.metric("Total Net Worth", "****")
    else:
        balance_context = db.get_latest_balance_context()
        latest_sync = balance_context["latest_sync"]
        nw_df = balance_context["balances"]
        if nw_df.empty:
            if balance_context["latest_sync_returned_no_balances"]:
                sync_time = latest_sync.iloc[0]["finished_at"] if not latest_sync.empty else ""
                st.warning(
                    f"Latest successful sync at {sync_time} returned no usable balances. "
                    "Net Worth is hidden instead of falling back to older balances."
                )
            else:
                st.info("No balance snapshot yet. Use Sync with Banks to refresh account balances.")
        else:
            latest_date = balance_context["snapshot_date"] or nw_df["date"].iloc[0]
            if not latest_sync.empty:
                sync = latest_sync.iloc[0]
                st.caption(
                    f"Latest successful sync: {sync['finished_at']} | "
                    f"Snapshot date: {latest_date} | "
                    f"{balance_context['balance_accounts_seen']} balance accounts returned"
                )
            else:
                st.caption(f"Latest stored snapshot: {latest_date}. Use Sync with Banks to refresh.")
            nw_df = nw_df.copy()
            nw_df["classification"] = nw_df["classification"].fillna(account_classifier.CASH)
            nw_df["balance"] = pd.to_numeric(nw_df["balance"], errors="coerce").fillna(0.0)

            cash_nw = nw_df[nw_df["classification"] == account_classifier.CASH]["balance"].sum()
            taxable_investments_nw = nw_df[
                nw_df["classification"] == account_classifier.TAXABLE_INVESTMENTS
            ]["balance"].sum()
            retirement_restricted_nw = nw_df[
                nw_df["classification"] == account_classifier.RETIREMENT_RESTRICTED
            ]["balance"].sum()
            liabilities = nw_df[nw_df["classification"] == account_classifier.LIABILITY]["balance"].sum()
            
            total_nw = cash_nw + taxable_investments_nw + retirement_restricted_nw + liabilities

            # 1. Metrics
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Net Worth", f"${total_nw:,.2f}")
            m2.metric("Cash", f"${cash_nw:,.2f}", help="Checking, savings, and cash-like accounts")
            m3.metric("Taxable Investments", f"${taxable_investments_nw:,.2f}", help="Brokerage, stock plan, crypto, and other non-retirement investments")
            m4.metric("Retirement / Restricted", f"${retirement_restricted_nw:,.2f}", help="401k, IRA, Roth IRA, HSA, and retirement-style accounts")
            m5.metric("Liabilities", f"${liabilities:,.2f}", help="Credit cards and debt balances")
            
            # 2. History Chart
            st.subheader("History")
            hist_df = db.get_net_worth_history()
            if not hist_df.empty:
                hist_df['date'] = pd.to_datetime(hist_df['date'])
                st.line_chart(hist_df.set_index('date')['total_nw'])
            else:
                st.write("No history yet.")

            # 3. Details Table
            st.subheader("Asset Breakdown")
            display_nw = nw_df.rename(columns={
                "bank": "Bank",
                "account": "Account",
                "balance": "Balance",
                "classification": "Classification",
            })[["Bank", "Account", "Balance", "Classification"]]
            display_nw = display_nw.sort_values(by=['Classification', 'Bank', 'Account'])

            def color_balance(val):
                color = 'red' if val < 0 else 'green'
                return f'color: {color}'

            st.dataframe(
                display_nw.style.map(color_balance, subset=['Balance']).format({"Balance": "${:,.2f}"}),
                use_container_width=True,
                height=500
            )

# ---------------------------------------------------------
# TAB 5: SEARCH
# ---------------------------------------------------------
with tab5:
    st.header("🔍 Transaction Search")
    
    all_df = db.get_all_transactions()
    if not all_df.empty:
        # Ensure dates are datetime
        all_df['date'] = pd.to_datetime(all_df['date'], format='mixed')
        
        # Search Filters
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            search_term = st.text_input("Search Description/Notes", "")
        with col2:
            search_cat = st.multiselect("Filter by Category", all_df['category'].unique())
        with col3:
            search_type = st.multiselect("Filter by Type", all_df['type'].unique())
        with col4:
            min_date = all_df['date'].min()
            max_date = all_df['date'].max()
            date_range = st.date_input("Date Range", [min_date, max_date])

        # Apply Filters
        filtered_df = all_df.copy()
        
        if not SHOW_SENSITIVE:
            filtered_df = filtered_df[~filtered_df['type'].isin(['Income', 'Investment'])]
        
        if search_term:
            filtered_df = filtered_df[
                filtered_df['description'].str.contains(search_term, case=False, na=False) | 
                filtered_df['user_notes'].str.contains(search_term, case=False, na=False)
            ]
            
        if search_cat:
            filtered_df = filtered_df[filtered_df['category'].isin(search_cat)]
            
        if search_type:
            filtered_df = filtered_df[filtered_df['type'].isin(search_type)]
            
        if len(date_range) == 2:
            start_d, end_d = date_range
            filtered_df = filtered_df[
                (filtered_df['date'].dt.date >= start_d) & 
                (filtered_df['date'].dt.date <= end_d)
            ]

        # Summary of Selection
        # Calculate Expense Total (Net of Reimbursements)
        non_expense_cats = ['Transfer', 'Brokerage', 'Roth IRA', 'Credit Card Payment']
        gross_search_exp = filtered_df[
            (filtered_df['type'] == 'Expense') & 
            (~filtered_df['category'].isin(non_expense_cats))
        ]['amount'].sum()
        
        search_reimb = filtered_df[
            (filtered_df['type'] == 'Reimbursement') & 
            (~filtered_df['category'].isin(non_expense_cats))
        ]['amount'].sum()
        
        expense_total = gross_search_exp - search_reimb
        
        st.caption(f"Showing {len(filtered_df)} transactions. Total Spending (Net Expenses): **${expense_total:,.2f}**")

        # ---------------------------------------------------------
        # DATA EDITOR (The "Update Data" Section)
        # ---------------------------------------------------------
        st.info("💡 You can edit transactions directly below. Click 'Save Updates' to apply changes.")
        
        # We use a key based on filters to reset state if filters change (optional, but safer)
        # Actually, let's keep it persistent so they don't lose edits.
        
        if ROLE == 'admin':
            edited_search_df = st.data_editor(
                filtered_df,
                column_config={
                    "category": st.column_config.SelectboxColumn(
                        "Category",
                        options=[
                            "Salary", "Interest Income", "Gift Income", "Rewards",
                            "Restaurants", "Fast Food", "Groceries", "Health", "Entertainment", "Travel",
                            "Gift Expense", "Gas", "Commute", "Subscriptions", "Personal Care",
                            "Shopping", "Supplies", "Phone", "Misc Expense", "Pass-Through (Reimbursed)",
                            "Misc Income", "Transfer",
                            "Brokerage", "Roth IRA",
                            "Donation"
                        ],
                        required=True
                    ),
                    "type": st.column_config.SelectboxColumn(
                        "Type",
                        options=["Expense", "Income", "Reimbursement", "Investment", "Transfer"],
                        required=True
                    ),
                    "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
                    "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
                    "user_notes": st.column_config.TextColumn("Notes"),
                    "tags": st.column_config.TextColumn("Tags"),
                    "id": None, 
                    "raw_data": None,
                    "status": None
                },
                hide_index=True,
                use_container_width=True,
                num_rows="fixed", # Don't allow adding rows here, only editing
                key="search_editor"
            )
            
            if st.button("💾 Save Updates"):
                # Detect changes.
                conn = db.get_connection()
                c = conn.cursor()
                count = 0
                
                # We iterate over the EDITED dataframe
                for idx, row in edited_search_df.iterrows():
                    # We need the ID to match
                    tx_id = row['id']
                    
                    # Sanitize tags
                    raw_tags = row.get('tags', '')
                    tags_str = str(raw_tags) if raw_tags is not None else ''

                    ph = '%s' if db.is_postgres() else '?'
                    c.execute(f'''
                        UPDATE transactions 
                        SET category = {ph}, user_notes = {ph}, tags = {ph}, type = {ph}, date = {ph}, amount = {ph}
                        WHERE id = {ph}
                    ''', (
                        row['category'], 
                        row['user_notes'], 
                        tags_str,
                        row['type'],
                        row['date'].strftime('%Y-%m-%d'), 
                        row['amount'],
                        tx_id
                    ))
                    count += 1
                    
                conn.commit()
                conn.close()
                st.success(f"Updated {count} transactions!")
                st.rerun()
        else:
            # Read Only for Viewers
            st.dataframe(
                filtered_df,
                column_config={
                    "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
                    "id": None,
                    "raw_data": None
                },
                use_container_width=True,
                hide_index=True
            )
