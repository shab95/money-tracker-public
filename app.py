import altair as alt
import streamlit as st
import pandas as pd
import db
import sync_simplefin
import math
from datetime import datetime, timedelta
import requests
import time

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
tab1, tab2, tab3, tab4 = st.tabs(["📥 Inbox", "📈 Trends", "💰 Net Worth", "🔎 Search"])

# ---------------------------------------------------------
# TAB 1: INBOX
# ---------------------------------------------------------
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### Review Pending Transactions")
        st.caption("Categorize and approve new transactions here.")
    
    with col2:
        if ROLE == 'admin':
            if st.button("🔄 Sync with Banks"):
                with st.spinner("Fetching latest data..."):
                    # Run the sync
                    try:
                        # Capture stdout? For now just run it.
                        sync_simplefin.sync()
                        st.success("Sync complete!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Sync failed: {e}")
        else:
            st.caption("Syncing disabled for Viewers")

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
            "date", "type", "amount", "category", 
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
                "status": None # Hide Status
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
                    
                    conn = db.get_connection()
                    c = conn.cursor()
                    for idx, row in to_approve.iterrows():
                        # Sanitize tags: If list, join by comma. If None, empty string.
                        raw_tags = row.get('tags', '')
                        if isinstance(raw_tags, list):
                            tags_str = ", ".join([str(t) for t in raw_tags])
                        else:
                            tags_str = str(raw_tags) if raw_tags is not None else ''

                        ph = '%s' if db.is_postgres() else '?'
                        c.execute(f'''
                            UPDATE transactions 
                            SET category = {ph}, user_notes = {ph}, tags = {ph}, type = {ph}, status = 'REVIEWED'
                            WHERE id = {ph}
                        ''', (
                            row['category'], 
                            row['user_notes'], 
                            tags_str,
                            row['type'],
                            row['id']
                        ))
                    conn.commit()
                    conn.close()
                    
                    st.success("Transactions approved!")
                    st.rerun()
            else:
                 st.info("Log in as Admin to approve transactions.")

    else:
        st.info("🎉 All caught up! No pending transactions.")
        st.balloons()

# ---------------------------------------------------------
# TAB 2: TRENDS (The Payoff)
# ---------------------------------------------------------
# ---------------------------------------------------------
# TAB 2: DASHBOARD (Formerly Trends)
# ---------------------------------------------------------
with tab2:
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
            cat_df = exp_df.groupby('category')['amount'].sum().sort_values(ascending=False)
            st.bar_chart(cat_df)
            
            # --- Monthly Cash Flow (Optional) ---
            if show_monthly_flow:
                render_monthly_flow(df)
            
            st.subheader("Transaction Log")
            display_df = df[['date', 'type', 'category', 'description', 'amount', 'status']].copy()
            st.dataframe(display_df, use_container_width=True)

        # --- Sub-Tabs ---
        sub1, sub2, sub3, sub4 = st.tabs(["All Time", "Year to Date", "This Month", "This Week"])
        
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
            
    else:
        st.write("No data yet.")

# ---------------------------------------------------------
# TAB 3: NET WORTH
# ---------------------------------------------------------
with tab3:
    st.header("Net Worth & Balances")
    
    col_r1, col_r2 = st.columns([3, 1])
    if ROLE == 'admin':
        if col_r2.button("🔄 Refresh Balances"):
            st.cache_data.clear()
            st.rerun()

    @st.cache_data(ttl=3600) # Cache for 1 hour
    def fetch_balances():
        if not SIMPLEFIN_ACCESS_URL:
            return None, "Missing API URL"
        
        try:
            res = requests.get(SIMPLEFIN_ACCESS_URL + "/accounts")
            res.raise_for_status()
            return res.json(), None
        except Exception as e:
            return None, str(e)

    data, error = fetch_balances()
    
    if not SHOW_SENSITIVE:
        st.warning("🔒 Privacy Mode Enabled. Net Worth Hidden.")
        st.metric("Total Net Worth", "****")
    elif error:
        st.error(f"Error fetching balances: {error}")
    elif data:
        accounts = data.get('accounts', [])
        
        rows = []
        
        # Locked Accounts (Retirement/Penalty)
        LOCKED_ACCOUNTS = [
            "CAPITAL ONE 401K ASP",
            "Self-Directed Brokerage",
            "Robinhood Roth IRA",
            "Robinhood managed Roth IRA"
        ]
        
        liquid_nw = 0.0
        locked_nw = 0.0
        
        for acct in accounts:
            bank = acct.get('org', {}).get('name', 'Unknown Bank')
            name = acct.get('name', 'Unknown Acct')
            
            # Filter Duplicates
            if bank == "Fidelity 401k":
                continue
                
            bal_str = acct.get('balance', '0')
            currency = acct.get('currency', 'USD')
            try:
                balance = float(bal_str)
            except:
                balance = 0.0
            
            # Classify
            is_locked = False
            # Check if name is exactly in list or similar? User names seemed specific.
            # Using partial match might be safer or exact match.
            # User provided exact names in prev tool outputs, so exact match + case insensitive
            if name in LOCKED_ACCOUNTS:
                is_locked = True
                locked_nw += balance
            else:
                liquid_nw += balance
            
            rows.append({
                "Bank": bank,
                "Account": name,
                "Balance": balance,
                "Type": "🔒 Locked" if is_locked else "💧 Liquid"
            })
            
        total_nw = liquid_nw + locked_nw
        
        # 1. Snapshoting to DB (for History)
        if rows:
            nw_df = pd.DataFrame(rows)
            db.save_balance_snapshot(nw_df)

        # 2. Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Net Worth", f"${total_nw:,.2f}")
        m2.metric("💧 Liquid Assets", f"${liquid_nw:,.2f}", help="Available now")
        m3.metric("🔒 Retirement/Locked", f"${locked_nw:,.2f}", help="Can't touch 'til 60")
        
        # 3. History Chart
        st.subheader("History")
        hist_df = db.get_net_worth_history()
        if not hist_df.empty:
            hist_df['date'] = pd.to_datetime(hist_df['date'])
            st.area_chart(hist_df.set_index('date')['total_nw'])
        else:
            st.write("No history yet.")

        # 4. Details Table
        st.subheader("Asset Breakdown")
        if rows:
            # Sort
            nw_df = nw_df.sort_values(by=['Type', 'Bank', 'Account'])
            
            # Color code debts?
            def color_balance(val):
                color = 'red' if val < 0 else 'green'
                return f'color: {color}'
            
            st.dataframe(
                nw_df.style.map(color_balance, subset=['Balance']).format({"Balance": "${:,.2f}"}),
                use_container_width=True,
                height=500
            )

    else:
        st.info("No account data found.")

# ---------------------------------------------------------
# TAB 4: SEARCH (Formerly Tab 3)
# ---------------------------------------------------------
with tab4:
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
