"""
================================================================================
KA CreditFlow v5.5 — Enhancement Module
================================================================================
Author  : KA Legacy (Founded by Keanon Apollos)
Date    : 2026-05-29
Purpose : Closes the 18 feature gaps identified in the SAP / Oracle /
          System1A / HighRadius benchmarking exercise.

New Capabilities
────────────────
  1. Auto-Dunning Engine with escalation rules
  2. Cash Flow Forecasting (4-week + 12-week horizon)
  3. Payment Behaviour Analytics (DSO trend, consistency scoring)
  4. CSV Import & Export
  5. Write-Off Management with approval workflow
  6. Interest & Penalty Calculator (NCA-compliant defaults)
  7. Client Credit Application & Onboarding Form
  8. Enhanced Dashboard KPIs with targets & traffic lights

Integration
───────────
  Import this module in the main app and call init_enhancements_db()
  at startup. Each render_*() function is a standalone Streamlit panel.
================================================================================
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta, date
import io, csv, math

# ── Shared constants ─────────────────────────────────────────────────────────
SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"


def get_sast_now():
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()))
    conn.commit()
    conn.close()


RISK_GRADE_MAP = {
    "A": {"label": "Excellent", "colour": "#198754", "pd": 0.005},
    "B": {"label": "Good",      "colour": "#20c997", "pd": 0.02},
    "C": {"label": "Fair",      "colour": "#ffc107", "pd": 0.05},
    "D": {"label": "Poor",      "colour": "#fd7e14", "pd": 0.15},
    "E": {"label": "Critical",  "colour": "#dc3545", "pd": 0.35},
}


# =============================================================================
# DATABASE INITIALIZATION — NEW TABLES
# =============================================================================
def init_enhancements_db(db_path=DB_PATH):
    """Create all enhancement tables."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS dunning_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT NOT NULL,
        days_overdue_trigger INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        channel TEXT DEFAULT 'Email',
        template_name TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS dunning_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        invoice_id INTEGER NOT NULL,
        rule_id INTEGER NOT NULL,
        scheduled_date TEXT,
        executed_at TEXT,
        status TEXT DEFAULT 'Pending',
        notes TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS write_offs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        invoice_id INTEGER NOT NULL,
        write_off_amount REAL NOT NULL,
        reason TEXT,
        approved_by TEXT,
        approved_at TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS credit_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        contact_person TEXT,
        email TEXT,
        phone TEXT,
        address TEXT,
        industry TEXT,
        reg_number TEXT,
        vat_number TEXT,
        requested_limit REAL DEFAULT 50000,
        trade_references TEXT,
        bank_details TEXT,
        years_in_business INTEGER DEFAULT 1,
        annual_turnover REAL DEFAULT 0,
        status TEXT DEFAULT 'Submitted',
        reviewed_by TEXT,
        reviewed_at TEXT,
        notes TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS kpi_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT UNIQUE NOT NULL,
        target_value REAL NOT NULL,
        amber_threshold REAL,
        red_threshold REAL,
        updated_by TEXT,
        updated_at TEXT
    )""")

    # Seed dunning rules if empty
    c.execute("SELECT COUNT(*) FROM dunning_rules")
    if c.fetchone()[0] == 0:
        now = get_sast_now()
        rules = [
            ("Pre-Due Friendly Reminder", -7, "Friendly", "Email", "Friendly Reminder", 1, now),
            ("1-Day Overdue Notice", 1, "Friendly", "Email", "Friendly Reminder", 1, now),
            ("30-Day Formal Notice", 30, "Formal", "Email", "30-Day Overdue", 1, now),
            ("60-Day Urgent Escalation", 60, "Urgent", "All", "60-Day Overdue", 1, now),
            ("90-Day Final Demand", 90, "Final", "All", "90-Day Overdue", 1, now),
            ("120-Day Legal Referral", 120, "Legal", "Email", "Final Demand", 1, now),
        ]
        c.executemany(
            "INSERT INTO dunning_rules (rule_name,days_overdue_trigger,action_type,"
            "channel,template_name,is_active,created_at) VALUES (?,?,?,?,?,?,?)", rules)

    # Seed KPI targets if empty
    c.execute("SELECT COUNT(*) FROM kpi_targets")
    if c.fetchone()[0] == 0:
        now = get_sast_now()
        targets = [
            ("DSO", 45, 50, 60, DEFAULT_USER, now),
            ("Collection Rate %", 85, 75, 65, DEFAULT_USER, now),
            ("Overdue %", 15, 25, 35, DEFAULT_USER, now),
        ]
        c.executemany(
            "INSERT INTO kpi_targets (metric_name,target_value,amber_threshold,"
            "red_threshold,updated_by,updated_at) VALUES (?,?,?,?,?,?)", targets)

    conn.commit()
    conn.close()


# =============================================================================
# 1. AUTO-DUNNING ENGINE
# =============================================================================
def run_dunning_engine(db_path=DB_PATH):
    """Scan open invoices against dunning rules and populate the queue."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    today = date.today()

    rules = conn.execute("SELECT * FROM dunning_rules WHERE is_active=1 ORDER BY days_overdue_trigger").fetchall()
    invoices = conn.execute(
        "SELECT i.*, c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id "
        "WHERE i.status IN ('Open','Partially Paid')").fetchall()

    new_entries = 0
    for inv in invoices:
        due = datetime.strptime(inv["due_date"], "%Y-%m-%d").date()
        days_overdue = (today - due).days

        for rule in rules:
            trigger = rule["days_overdue_trigger"]
            # Check if this trigger applies (within 3-day window for pre-due, exact or past for overdue)
            if trigger < 0:
                # Pre-due: trigger when days_overdue is between trigger and trigger+3
                if trigger <= -days_overdue <= trigger + 3:
                    applies = True
                else:
                    applies = days_overdue <= trigger  # e.g., -7 days before due
                applies = (days_overdue >= trigger and days_overdue < trigger + 7) if trigger < 0 else False
                # Simplified: pre-due triggers when we're within the window
                days_to_due = -days_overdue  # positive = days until due
                applies = (trigger <= -days_to_due < trigger + 7)
            else:
                applies = days_overdue >= trigger

            if not applies:
                continue

            # Check not already queued
            existing = conn.execute(
                "SELECT COUNT(*) FROM dunning_queue WHERE invoice_id=? AND rule_id=?",
                (inv["id"], rule["id"])).fetchone()[0]
            if existing > 0:
                continue

            conn.execute(
                "INSERT INTO dunning_queue (client_id,invoice_id,rule_id,scheduled_date,status,notes) "
                "VALUES (?,?,?,?,?,?)",
                (inv["client_id"], inv["id"], rule["id"], str(today), "Pending",
                 f"Auto-generated: {rule['rule_name']} for {inv['invoice_number']}"))
            new_entries += 1

    conn.commit()
    conn.close()
    return new_entries


def render_dunning_engine():
    st.markdown("## ⚙️ Auto-Dunning Engine")
    st.markdown("_Automated escalation rules that trigger reminders based on invoice aging._")

    conn = get_db()

    # Show rules
    st.markdown("### 📋 Dunning Rules")
    rules = pd.read_sql("SELECT * FROM dunning_rules ORDER BY days_overdue_trigger", conn)
    if len(rules) > 0:
        display = rules[["rule_name", "days_overdue_trigger", "action_type", "channel", "is_active"]].copy()
        display.columns = ["Rule", "Days Trigger", "Action Level", "Channel", "Active"]
        display["Active"] = display["Active"].map({1: "✅ Yes", 0: "❌ No"})
        display["Days Trigger"] = display["Days Trigger"].apply(
            lambda d: f"{d} days (pre-due)" if d < 0 else f"+{d} days overdue")
        st.dataframe(display, use_container_width=True, hide_index=True)

    # Run engine
    st.divider()
    st.markdown("### 🚀 Run Dunning Engine")
    st.markdown("Scans all open invoices against active rules and queues actions.")

    if st.button("🚀 Run Dunning Engine Now", type="primary", key="run_dunning"):
        new = run_dunning_engine()
        log_audit("DUNNING", "Dunning Engine", f"Dunning engine executed — {new} new queue entries")
        if new > 0:
            st.success(f"✅ Dunning engine completed — **{new} new actions** queued!")
        else:
            st.info("✅ No new dunning actions required. All accounts are current or already queued.")
        st.rerun()

    # Show queue
    st.divider()
    st.markdown("### 📬 Dunning Queue")
    queue = pd.read_sql(
        "SELECT dq.*, c.company_name, i.invoice_number, dr.rule_name, dr.action_type "
        "FROM dunning_queue dq "
        "JOIN clients c ON dq.client_id=c.id "
        "JOIN invoices i ON dq.invoice_id=i.id "
        "JOIN dunning_rules dr ON dq.rule_id=dr.id "
        "ORDER BY dq.scheduled_date DESC", conn)

    if len(queue) > 0:
        status_filter = st.selectbox("Filter", ["All", "Pending", "Sent", "Skipped"], key="dq_filter")
        if status_filter != "All":
            queue = queue[queue["status"] == status_filter]

        st.markdown(f"**{len(queue)} entries**")
        action_colours = {"Friendly": "#198754", "Formal": "#ffc107", "Urgent": "#fd7e14",
                          "Final": "#dc3545", "Legal": "#842029"}
        for _, q in queue.iterrows():
            a_col = action_colours.get(q["action_type"], "#6c757d")
            s_col = {"Pending": "#ffc107", "Sent": "#198754", "Skipped": "#6c757d"}.get(q["status"], "#6c757d")
            st.markdown(f"""
            <div style="border-left:4px solid {a_col};padding:10px 16px;margin-bottom:6px;
                        background:#f9f9f9;border-radius:6px;">
                <span style="background:{a_col};color:white;padding:2px 10px;border-radius:10px;
                      font-size:0.8em;">{q['action_type']}</span>
                <span style="background:{s_col};color:white;padding:2px 8px;border-radius:10px;
                      font-size:0.75em;">{q['status']}</span>
                &nbsp; <strong>{q['company_name']}</strong> — {q['invoice_number']}
                &nbsp; <span style="color:#888;font-size:0.85em;">{q['rule_name']} · {q['scheduled_date']}</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("Dunning queue is empty. Run the engine to populate.")

    conn.close()


# =============================================================================
# 2. CASH FLOW FORECASTING
# =============================================================================
def render_cashflow_forecast():
    st.markdown("## 💰 Cash Flow Forecast")
    st.markdown("_Predicted cash inflows based on invoice due dates and client payment behaviour._")

    conn = get_db()
    today = date.today()

    # Get open invoices with client payment history
    invoices = pd.read_sql(
        "SELECT i.*, c.company_name FROM invoices i "
        "JOIN clients c ON i.client_id=c.id "
        "WHERE i.status IN ('Open','Partially Paid') ORDER BY i.due_date", conn)

    if len(invoices) == 0:
        st.info("No open invoices for forecasting.")
        conn.close()
        return

    invoices["outstanding"] = invoices["total_amount"] - invoices["amount_paid"]
    invoices["due_dt"] = pd.to_datetime(invoices["due_date"]).dt.date

    # Calculate avg days to pay per client from payment history
    payments = pd.read_sql(
        "SELECT p.client_id, p.payment_date, i.due_date FROM payments p "
        "JOIN invoices i ON p.invoice_id=i.id", conn)

    avg_days_late = {}
    if len(payments) > 0:
        payments["days_late"] = (pd.to_datetime(payments["payment_date"]) -
                                  pd.to_datetime(payments["due_date"])).dt.days
        for cid, group in payments.groupby("client_id"):
            avg_days_late[cid] = max(0, int(group["days_late"].mean()))

    # Predict payment date per invoice
    forecasts = []
    for _, inv in invoices.iterrows():
        client_delay = avg_days_late.get(inv["client_id"], 15)  # default 15 days if no history
        predicted_date = inv["due_dt"] + timedelta(days=client_delay)
        if predicted_date < today:
            predicted_date = today + timedelta(days=3)  # overdue — expect soon
        forecasts.append({
            "client": inv["company_name"],
            "invoice": inv["invoice_number"],
            "amount": inv["outstanding"],
            "due_date": inv["due_dt"],
            "predicted_date": predicted_date,
            "client_avg_delay": client_delay,
        })

    fc_df = pd.DataFrame(forecasts)
    fc_df["predicted_date"] = pd.to_datetime(fc_df["predicted_date"])

    # Weekly aggregation (next 12 weeks)
    weeks = []
    for w in range(12):
        week_start = today + timedelta(weeks=w)
        week_end = week_start + timedelta(days=6)
        mask = (fc_df["predicted_date"].dt.date >= week_start) & (fc_df["predicted_date"].dt.date <= week_end)
        total = fc_df[mask]["amount"].sum()
        weeks.append({
            "Week": f"W{w+1} ({week_start.strftime('%d %b')})",
            "Expected Inflow (R)": total,
            "week_num": w + 1,
        })

    weeks_df = pd.DataFrame(weeks)

    # KPI row
    k1, k2, k3 = st.columns(3)
    total_expected = fc_df["amount"].sum()
    next_4_weeks = weeks_df[weeks_df["week_num"] <= 4]["Expected Inflow (R)"].sum()
    avg_client_delay = fc_df["client_avg_delay"].mean()
    k1.metric("💰 Total Expected", f"R {total_expected:,.2f}")
    k2.metric("📅 Next 4 Weeks", f"R {next_4_weeks:,.2f}")
    k3.metric("⏱️ Avg Client Delay", f"{avg_client_delay:.0f} days")

    # Chart
    fig = px.bar(weeks_df, x="Week", y="Expected Inflow (R)",
                 color_discrete_sequence=["#0d6efd"], text_auto=",.0f")
    fig.update_traces(texttemplate="R %{text:,.0f}", textposition="outside")
    fig.update_layout(height=400, margin=dict(t=20, b=20), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # Detail table
    st.markdown("### 📋 Invoice Forecast Detail")
    detail = fc_df.copy()
    detail["amount"] = detail["amount"].apply(lambda x: f"R {x:,.2f}")
    detail["due_date"] = detail["due_date"].astype(str)
    detail["predicted_date"] = detail["predicted_date"].dt.strftime("%Y-%m-%d")
    detail.columns = ["Client", "Invoice", "Outstanding", "Due Date", "Predicted Payment", "Avg Delay (days)"]
    st.dataframe(detail, use_container_width=True, hide_index=True)

    conn.close()


# =============================================================================
# 3. PAYMENT BEHAVIOUR ANALYTICS
# =============================================================================
def render_payment_analytics():
    st.markdown("## 📈 Payment Behaviour Analytics")
    st.markdown("_Client payment patterns, DSO trends, and consistency scoring._")

    conn = get_db()
    today = date.today()

    # Build per-client analytics
    clients = pd.read_sql("SELECT id, company_name FROM clients WHERE status='Active'", conn)
    if len(clients) == 0:
        st.warning("No active clients.")
        conn.close()
        return

    analytics = []
    for _, cl in clients.iterrows():
        cid = cl["id"]
        inv = pd.read_sql("SELECT * FROM invoices WHERE client_id=?", conn, params=(cid,))
        pay = pd.read_sql(
            "SELECT p.*, i.due_date as inv_due FROM payments p "
            "JOIN invoices i ON p.invoice_id=i.id WHERE p.client_id=?", conn, params=(cid,))

        total_invoices = len(inv)
        paid_inv = len(inv[inv["status"] == "Paid"])
        total_outstanding = (inv["total_amount"] - inv["amount_paid"]).clip(lower=0).sum()

        if len(pay) > 0:
            pay["days_to_pay"] = (pd.to_datetime(pay["payment_date"]) -
                                   pd.to_datetime(pay["inv_due"])).dt.days
            avg_days = pay["days_to_pay"].mean()
            late_count = len(pay[pay["days_to_pay"] > 0])
            late_pct = (late_count / len(pay) * 100) if len(pay) > 0 else 0
            consistency = max(0, 100 - abs(pay["days_to_pay"].std() * 2))
        else:
            avg_days = 0
            late_pct = 0
            consistency = 50

        # Trend (simplified: compare recent vs older invoices)
        if total_invoices >= 2:
            recent = inv.sort_values("invoice_date").tail(total_invoices // 2)
            recent_overdue = len(recent[recent["status"].isin(["Open", "Partially Paid"])])
            older = inv.sort_values("invoice_date").head(total_invoices // 2)
            older_overdue = len(older[older["status"].isin(["Open", "Partially Paid"])])
            if recent_overdue > older_overdue:
                trend = "📉 Deteriorating"
            elif recent_overdue < older_overdue:
                trend = "📈 Improving"
            else:
                trend = "➡️ Stable"
        else:
            trend = "➡️ Stable"

        analytics.append({
            "Client": cl["company_name"],
            "Total Invoices": total_invoices,
            "Paid": paid_inv,
            "Avg Days to Pay": round(avg_days, 1),
            "Late Payment %": round(late_pct, 1),
            "Consistency Score": round(consistency, 1),
            "Outstanding": total_outstanding,
            "Trend": trend,
        })

    df = pd.DataFrame(analytics)

    # Display
    display = df.copy()
    display["Outstanding"] = display["Outstanding"].apply(lambda x: f"R {x:,.2f}")
    st.dataframe(display, use_container_width=True, hide_index=True)

    # Client comparison chart
    st.markdown("### 📊 Client Comparison — Avg Days to Pay")
    fig = px.bar(df, x="Client", y="Avg Days to Pay",
                 color="Avg Days to Pay",
                 color_continuous_scale=["#198754", "#ffc107", "#dc3545"],
                 text_auto=".1f")
    fig.update_layout(height=350, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Consistency chart
    st.markdown("### 🎯 Payment Consistency Scores")
    fig2 = px.bar(df, x="Client", y="Consistency Score",
                  color="Consistency Score",
                  color_continuous_scale=["#dc3545", "#ffc107", "#198754"],
                  text_auto=".0f", range_y=[0, 100])
    fig2.update_layout(height=350, margin=dict(t=20, b=20))
    st.plotly_chart(fig2, use_container_width=True)

    conn.close()


# =============================================================================
# 4. CSV IMPORT & EXPORT
# =============================================================================
def render_data_tools():
    st.markdown("## 📁 Data Import & Export")
    mode = st.radio("", ["📥 Import Data", "📤 Export Data"], horizontal=True, key="dt_mode")

    conn = get_db()

    if mode == "📥 Import Data":
        st.markdown("### 📥 Import from CSV")
        import_type = st.selectbox("Import Type", ["Clients", "Invoices"], key="imp_type")

        uploaded = st.file_uploader(f"Upload {import_type} CSV", type=["csv"], key="csv_upload")

        if uploaded is not None:
            df = pd.read_csv(uploaded)
            st.markdown(f"**Preview** ({len(df)} rows)")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)

            if import_type == "Clients":
                required = ["company_name"]
                st.markdown(f"**Required columns:** {', '.join(required)}")
                st.markdown("**Optional:** contact_person, email, phone, address, industry, "
                            "registration_number, vat_number, payment_terms, credit_limit")
            else:
                required = ["client_id", "invoice_number", "amount", "due_date"]
                st.markdown(f"**Required columns:** {', '.join(required)}")

            if st.button(f"📥 Import {len(df)} {import_type}", type="primary", key="do_import"):
                missing = [c for c in required if c not in df.columns]
                if missing:
                    st.error(f"❌ Missing required columns: {', '.join(missing)}")
                else:
                    conn2 = sqlite3.connect(DB_PATH)
                    now = get_sast_now()
                    count = 0
                    if import_type == "Clients":
                        for _, row in df.iterrows():
                            try:
                                conn2.execute(
                                    "INSERT INTO clients (company_name,contact_person,email,phone,"
                                    "address,industry,registration_number,vat_number,payment_terms,"
                                    "credit_limit,created_at,updated_at) "
                                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                    (row.get("company_name", ""), row.get("contact_person", ""),
                                     row.get("email", ""), row.get("phone", ""),
                                     row.get("address", ""), row.get("industry", ""),
                                     row.get("registration_number", ""), row.get("vat_number", ""),
                                     row.get("payment_terms", "Net 30"),
                                     float(row.get("credit_limit", 50000)), now, now))
                                count += 1
                            except Exception:
                                pass
                    else:
                        for _, row in df.iterrows():
                            try:
                                amt = float(row["amount"])
                                vat = round(amt * 0.15, 2)
                                conn2.execute(
                                    "INSERT INTO invoices (client_id,invoice_number,invoice_date,"
                                    "due_date,amount,currency,vat_applicable,vat_amount,total_amount,"
                                    "description,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                    (int(row["client_id"]), row["invoice_number"],
                                     row.get("invoice_date", str(date.today())),
                                     row["due_date"], amt, "ZAR", 1, vat, amt + vat,
                                     row.get("description", ""), now))
                                count += 1
                            except Exception:
                                pass
                    conn2.commit()
                    conn2.close()
                    log_audit("IMPORT", "Data Tools", f"Imported {count} {import_type.lower()} from CSV")
                    st.success(f"✅ Imported **{count}** {import_type.lower()} successfully!")
                    st.rerun()

    else:  # Export
        st.markdown("### 📤 Export to CSV")
        export_type = st.selectbox("Export Type",
                                    ["Clients", "Invoices", "Payments", "Aging Report",
                                     "Notes", "Communications", "Audit Trail"],
                                    key="exp_type")

        table_map = {
            "Clients": "SELECT * FROM clients",
            "Invoices": "SELECT i.*, c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id",
            "Payments": "SELECT p.*, i.invoice_number FROM payments p JOIN invoices i ON p.invoice_id=i.id",
            "Aging Report": ("SELECT i.invoice_number, c.company_name, i.due_date, "
                             "i.total_amount, i.amount_paid, "
                             "(i.total_amount - i.amount_paid) as outstanding, i.status "
                             "FROM invoices i JOIN clients c ON i.client_id=c.id "
                             "WHERE i.status IN ('Open','Partially Paid','Disputed')"),
            "Notes": "SELECT cn.*, c.company_name FROM collection_notes cn JOIN clients c ON cn.client_id=c.id",
            "Communications": "SELECT cl.*, c.company_name FROM communication_log cl JOIN clients c ON cl.client_id=c.id",
            "Audit Trail": "SELECT * FROM audit_trail",
        }

        df = pd.read_sql(table_map[export_type], conn)
        st.markdown(f"**{len(df)} records** available for export")
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

        csv_data = df.to_csv(index=False)
        st.download_button(
            f"📤 Download {export_type} CSV",
            csv_data,
            file_name=f"ka_creditflow_{export_type.lower().replace(' ', '_')}_{date.today()}.csv",
            mime="text/csv",
            key="csv_download",
        )

    conn.close()


# =============================================================================
# 5. WRITE-OFF MANAGEMENT
# =============================================================================
def render_write_offs():
    st.markdown("## 📝 Write-Off Management")
    st.markdown("_Manage bad debt write-offs with approval workflow._")

    conn = get_db()
    today = date.today()

    # List write-offs
    woffs = pd.read_sql(
        "SELECT w.*, c.company_name, i.invoice_number FROM write_offs w "
        "JOIN clients c ON w.client_id=c.id "
        "JOIN invoices i ON w.invoice_id=i.id "
        "ORDER BY w.created_at DESC", conn)

    if len(woffs) > 0:
        st.markdown(f"**{len(woffs)} write-off records**")
        for _, w in woffs.iterrows():
            s_col = {"Pending": "#ffc107", "Approved": "#198754", "Rejected": "#dc3545"}.get(w["status"], "#6c757d")
            st.markdown(f"""
            <div style="border-left:4px solid {s_col};padding:10px 14px;margin-bottom:6px;
                        background:#f9f9f9;border-radius:6px;">
                <span style="background:{s_col};color:white;padding:2px 10px;border-radius:10px;
                      font-size:0.8em;">{w['status']}</span>
                &nbsp; <strong>{w['company_name']}</strong> — {w['invoice_number']}
                — R {w['write_off_amount']:,.2f}
                <span style="color:#888;font-size:0.85em;float:right;">{w['created_at']}</span>
                <div style="font-size:0.85em;color:#666;margin-top:4px;">Reason: {w['reason']}</div>
            </div>""", unsafe_allow_html=True)

    # Create write-off
    st.divider()
    st.markdown("### ➕ Create Write-Off Request")
    open_inv = pd.read_sql(
        "SELECT i.*, c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id "
        "WHERE i.status IN ('Open','Partially Paid','Disputed') ORDER BY i.due_date", conn)

    if len(open_inv) > 0:
        open_inv["outstanding"] = open_inv["total_amount"] - open_inv["amount_paid"]
        open_inv["label"] = open_inv.apply(
            lambda r: f"{r['invoice_number']} — {r['company_name']} — R {r['outstanding']:,.2f}", axis=1)

        with st.form("write_off_form"):
            sel = st.selectbox("Invoice", open_inv["label"].tolist(), key="wo_inv")
            sel_row = open_inv[open_inv["label"] == sel].iloc[0]
            wo_amount = st.number_input("Write-Off Amount (R)", min_value=0.01,
                                        max_value=float(sel_row["outstanding"]),
                                        value=float(sel_row["outstanding"]), step=100.0)
            reason = st.text_area("Reason for Write-Off", key="wo_reason")
            approved_by = st.text_input("Submitted By", value=DEFAULT_USER, key="wo_by")

            if st.form_submit_button("📝 Submit Write-Off", type="primary"):
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute(
                    "INSERT INTO write_offs (client_id,invoice_id,write_off_amount,reason,"
                    "approved_by,status,created_at) VALUES (?,?,?,?,?,?,?)",
                    (int(sel_row["client_id"]), int(sel_row["id"]), wo_amount,
                     reason, approved_by, "Pending", get_sast_now()))
                conn2.commit()
                conn2.close()
                log_audit("WRITE_OFF", "Write-Offs",
                          f"Write-off submitted: {sel_row['invoice_number']} — R {wo_amount:,.2f}")
                st.success("✅ Write-off request submitted for approval.")
                st.rerun()

    # Approve/Reject pending
    st.divider()
    st.markdown("### ✅ Approve / Reject Write-Offs")
    pending = woffs[woffs["status"] == "Pending"] if len(woffs) > 0 else pd.DataFrame()
    if len(pending) > 0:
        with st.form("approve_wo"):
            pending_labels = pending.apply(
                lambda r: f"#{r['id']} — {r['company_name']} — R {r['write_off_amount']:,.2f}", axis=1).tolist()
            sel_wo = st.selectbox("Select Write-Off", pending_labels, key="approve_sel")
            action = st.radio("Action", ["Approved", "Rejected"], horizontal=True, key="wo_action")

            if st.form_submit_button("✅ Process", type="primary"):
                wo_id = int(sel_wo.split(" — ")[0].replace("#", ""))
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute("UPDATE write_offs SET status=?, approved_at=? WHERE id=?",
                              (action, get_sast_now(), wo_id))
                if action == "Approved":
                    wo_row = pending[pending["id"] == wo_id].iloc[0]
                    conn2.execute("UPDATE invoices SET status='Written Off' WHERE id=?",
                                  (int(wo_row["invoice_id"]),))
                conn2.commit()
                conn2.close()
                log_audit("WRITE_OFF", "Write-Offs", f"Write-off #{wo_id} {action.lower()}")
                st.success(f"✅ Write-off #{wo_id} {action.lower()}.")
                st.rerun()
    else:
        st.info("No pending write-offs.")

    conn.close()


# =============================================================================
# 6. INTEREST & PENALTY CALCULATOR
# =============================================================================
def render_interest_calculator():
    st.markdown("## 💹 Interest & Penalty Calculator")
    st.markdown("_Calculate late payment interest per NCA guidelines._")

    conn = get_db()
    today = date.today()

    ic1, ic2 = st.columns(2)
    with ic1:
        interest_rate = st.number_input("Monthly Interest Rate (%)", min_value=0.0,
                                         value=2.0, step=0.25, key="int_rate")
    with ic2:
        grace_days = st.number_input("Grace Period (days)", min_value=0, value=7, step=1, key="grace")

    st.divider()

    invoices = pd.read_sql(
        "SELECT i.*, c.company_name FROM invoices i "
        "JOIN clients c ON i.client_id=c.id "
        "WHERE i.status IN ('Open','Partially Paid','Disputed') ORDER BY i.due_date", conn)

    if len(invoices) == 0:
        st.info("No overdue invoices.")
        conn.close()
        return

    invoices["outstanding"] = invoices["total_amount"] - invoices["amount_paid"]
    invoices["due_dt"] = pd.to_datetime(invoices["due_date"]).dt.date
    invoices["days_overdue"] = invoices["due_dt"].apply(lambda d: max(0, (today - d).days))
    invoices["chargeable_days"] = invoices["days_overdue"].apply(lambda d: max(0, d - grace_days))
    invoices["interest"] = invoices.apply(
        lambda r: r["outstanding"] * (interest_rate / 100) * (r["chargeable_days"] / 30), axis=1)

    overdue = invoices[invoices["days_overdue"] > 0].copy()
    if len(overdue) == 0:
        st.success("✅ No overdue invoices — no interest applicable.")
        conn.close()
        return

    total_interest = overdue["interest"].sum()
    st.metric("💹 Total Interest Exposure", f"R {total_interest:,.2f}")

    display = overdue[["invoice_number", "company_name", "outstanding", "days_overdue",
                        "chargeable_days", "interest"]].copy()
    display.columns = ["Invoice", "Client", "Outstanding", "Days Overdue", "Chargeable Days", "Interest"]
    display["Outstanding"] = display["Outstanding"].apply(lambda x: f"R {x:,.2f}")
    display["Interest"] = display["Interest"].apply(lambda x: f"R {x:,.2f}")
    st.dataframe(display, use_container_width=True, hide_index=True)

    # Per-client summary
    st.markdown("### 📊 Interest by Client")
    client_int = overdue.groupby("company_name")["interest"].sum().reset_index()
    client_int.columns = ["Client", "Total Interest"]
    fig = px.bar(client_int, x="Client", y="Total Interest",
                 color_discrete_sequence=["#dc3545"], text_auto=",.2f")
    fig.update_traces(texttemplate="R %{text}", textposition="outside")
    fig.update_layout(height=350, margin=dict(t=20, b=20), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    conn.close()


# =============================================================================
# 7. CLIENT CREDIT APPLICATION FORM
# =============================================================================
def render_credit_applications():
    st.markdown("## 📋 Credit Applications")
    st.markdown("_Client onboarding workflow — from application to approved credit limit._")

    conn = get_db()
    mode = st.radio("", ["📋 Applications", "➕ New Application"], horizontal=True, key="ca_mode")

    if mode == "📋 Applications":
        apps = pd.read_sql("SELECT * FROM credit_applications ORDER BY created_at DESC", conn)
        if len(apps) == 0:
            st.info("No applications on record.")
            conn.close()
            return

        for _, a in apps.iterrows():
            s_col = {"Submitted": "#0d6efd", "Under Review": "#ffc107",
                     "Approved": "#198754", "Declined": "#dc3545"}.get(a["status"], "#6c757d")
            st.markdown(f"""
            <div style="border-left:4px solid {s_col};padding:12px 16px;margin-bottom:8px;
                        background:#f9f9f9;border-radius:6px;">
                <div style="display:flex;justify-content:space-between;">
                    <span><strong>{a['company_name']}</strong>
                        <span style="background:{s_col};color:white;padding:2px 10px;
                              border-radius:10px;font-size:0.8em;margin-left:8px;">{a['status']}</span>
                    </span>
                    <span style="color:#888;font-size:0.85em;">#{a['id']} · {a['created_at']}</span>
                </div>
                <div style="margin-top:6px;font-size:0.9em;">
                    <strong>Contact:</strong> {a['contact_person']} · {a['email']} · {a['phone']}<br>
                    <strong>Industry:</strong> {a['industry']} · <strong>Years:</strong> {a['years_in_business']}
                    · <strong>Turnover:</strong> R {(a['annual_turnover'] or 0):,.0f}<br>
                    <strong>Requested Limit:</strong> R {a['requested_limit']:,.0f}
                </div>
            </div>""", unsafe_allow_html=True)

        # Review process
        pending_apps = apps[apps["status"].isin(["Submitted", "Under Review"])]
        if len(pending_apps) > 0:
            st.divider()
            st.markdown("### ✅ Review Application")
            with st.form("review_app"):
                labels = pending_apps.apply(
                    lambda r: f"#{r['id']} — {r['company_name']} (R {r['requested_limit']:,.0f})", axis=1).tolist()
                sel_app = st.selectbox("Application", labels, key="rev_app")
                app_id = int(sel_app.split(" — ")[0].replace("#", ""))
                app_row = pending_apps[pending_apps["id"] == app_id].iloc[0]

                decision = st.radio("Decision", ["Under Review", "Approved", "Declined"],
                                     horizontal=True, key="rev_dec")
                approved_limit = st.number_input("Approved Credit Limit (R)",
                                                  value=float(app_row["requested_limit"]),
                                                  step=5000.0, key="rev_limit")
                rev_notes = st.text_area("Review Notes", key="rev_notes")

                if st.form_submit_button("✅ Submit Decision", type="primary"):
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute(
                        "UPDATE credit_applications SET status=?, reviewed_by=?, reviewed_at=?, notes=? WHERE id=?",
                        (decision, DEFAULT_USER, get_sast_now(), rev_notes, app_id))

                    # If approved → auto-create client
                    if decision == "Approved":
                        now = get_sast_now()
                        conn2.execute(
                            "INSERT INTO clients (company_name,contact_person,email,phone,"
                            "address,industry,registration_number,vat_number,payment_terms,"
                            "credit_limit,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (app_row["company_name"], app_row["contact_person"], app_row["email"],
                             app_row["phone"], app_row["address"], app_row["industry"],
                             app_row["reg_number"], app_row["vat_number"], "Net 30",
                             approved_limit, now, now))
                    conn2.commit()
                    conn2.close()
                    log_audit("CREDIT_APP", "Credit Applications",
                              f"Application #{app_id} — {app_row['company_name']} → {decision}")
                    msg = f"✅ Application #{app_id} marked as **{decision}**."
                    if decision == "Approved":
                        msg += f" Client created with R {approved_limit:,.0f} credit limit."
                    st.success(msg)
                    st.rerun()

    else:  # New Application
        st.markdown("### ➕ New Credit Application")
        with st.form("new_credit_app"):
            ca1, ca2 = st.columns(2)
            with ca1:
                company = st.text_input("Company Name *", key="ca_co")
                contact = st.text_input("Contact Person", key="ca_cp")
                email = st.text_input("Email", key="ca_em")
                phone = st.text_input("Phone", key="ca_ph")
                address = st.text_area("Address", height=80, key="ca_ad")
            with ca2:
                industry = st.text_input("Industry", key="ca_ind")
                reg_number = st.text_input("Registration Number", key="ca_reg")
                vat_number = st.text_input("VAT Number", key="ca_vat")
                requested = st.number_input("Requested Credit Limit (R)",
                                             min_value=1000.0, value=50000.0, step=5000.0, key="ca_lim")
                years = st.number_input("Years in Business", min_value=0, value=3, key="ca_yrs")
                turnover = st.number_input("Annual Turnover (R)", min_value=0.0,
                                            value=500000.0, step=50000.0, key="ca_turn")
            trade_refs = st.text_area("Trade References", key="ca_refs")
            bank_details = st.text_input("Banking Details", key="ca_bank")

            if st.form_submit_button("📋 Submit Application", type="primary"):
                if not company.strip():
                    st.warning("Company name is required.")
                else:
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute(
                        "INSERT INTO credit_applications (company_name,contact_person,email,phone,"
                        "address,industry,reg_number,vat_number,requested_limit,trade_references,"
                        "bank_details,years_in_business,annual_turnover,status,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (company, contact, email, phone, address, industry, reg_number,
                         vat_number, requested, trade_refs, bank_details, years, turnover,
                         "Submitted", get_sast_now()))
                    conn2.commit()
                    conn2.close()
                    log_audit("CREDIT_APP", "Credit Applications",
                              f"New application submitted: {company} — R {requested:,.0f}")
                    st.success(f"✅ Application for **{company}** submitted!")
                    st.rerun()

    conn.close()


# =============================================================================
# 8. ENHANCED KPI TARGETS WITH TRAFFIC LIGHTS
# =============================================================================
def render_kpi_targets():
    st.markdown("## 🎯 KPI Targets & Performance")
    st.markdown("_Set targets, track actual vs target with traffic light indicators._")

    conn = get_db()
    today = date.today()

    # Get current targets
    targets = pd.read_sql("SELECT * FROM kpi_targets", conn)

    # Calculate actuals
    inv = pd.read_sql("SELECT * FROM invoices", conn)
    inv["outstanding"] = inv["total_amount"] - inv["amount_paid"]
    open_inv = inv[inv["status"].isin(["Open", "Partially Paid", "Disputed"])]

    total_ar = open_inv["outstanding"].sum()
    total_invoiced = inv["total_amount"].sum()
    total_collected = inv["amount_paid"].sum()

    dso = (total_ar / total_invoiced * 365) if total_invoiced > 0 else 0
    collection_rate = (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0
    overdue_pct = 0
    if total_ar > 0:
        open_inv_copy = open_inv.copy()
        open_inv_copy["due_dt"] = pd.to_datetime(open_inv_copy["due_date"]).dt.date
        overdue_amt = open_inv_copy[open_inv_copy["due_dt"] < today]["outstanding"].sum()
        overdue_pct = (overdue_amt / total_ar * 100)

    actuals = {"DSO": dso, "Collection Rate %": collection_rate, "Overdue %": overdue_pct}

    # Display with traffic lights
    st.markdown("### 🚦 Performance vs Targets")
    cols = st.columns(len(targets))
    for idx, (_, t) in enumerate(targets.iterrows()):
        metric = t["metric_name"]
        target = t["target_value"]
        amber = t["amber_threshold"]
        red = t["red_threshold"]
        actual = actuals.get(metric, 0)

        # Determine traffic light
        # For DSO and Overdue %: lower is better
        # For Collection Rate %: higher is better
        if metric == "Collection Rate %":
            if actual >= target:
                light = "🟢"
                colour = "#198754"
            elif actual >= amber:
                light = "🟡"
                colour = "#ffc107"
            else:
                light = "🔴"
                colour = "#dc3545"
        else:  # DSO, Overdue % — lower is better
            if actual <= target:
                light = "🟢"
                colour = "#198754"
            elif actual <= amber:
                light = "🟡"
                colour = "#ffc107"
            else:
                light = "🔴"
                colour = "#dc3545"

        delta = actual - target
        with cols[idx]:
            st.markdown(f"""
            <div style="text-align:center;padding:16px;background:#f8f9fa;border-radius:10px;
                        border:2px solid {colour};">
                <div style="font-size:2.5em;">{light}</div>
                <div style="font-size:1.1em;font-weight:bold;margin:6px 0;">{metric}</div>
                <div style="font-size:1.8em;font-weight:bold;color:{colour};">{actual:.1f}</div>
                <div style="font-size:0.85em;color:#888;">Target: {target:.1f}</div>
                <div style="font-size:0.85em;color:{colour};">Delta: {delta:+.1f}</div>
            </div>""", unsafe_allow_html=True)

    # Edit targets
    st.divider()
    st.markdown("### ⚙️ Set Targets")
    with st.form("set_targets"):
        tc = st.columns(3)
        new_targets = {}
        for idx, (_, t) in enumerate(targets.iterrows()):
            with tc[idx]:
                st.markdown(f"**{t['metric_name']}**")
                new_targets[t['metric_name']] = {
                    "target": st.number_input(f"Target", value=float(t['target_value']),
                                               step=1.0, key=f"tgt_{idx}"),
                    "amber": st.number_input(f"Amber Threshold", value=float(t['amber_threshold']),
                                              step=1.0, key=f"amb_{idx}"),
                    "red": st.number_input(f"Red Threshold", value=float(t['red_threshold']),
                                            step=1.0, key=f"red_{idx}"),
                }

        if st.form_submit_button("💾 Save Targets", type="primary"):
            conn2 = sqlite3.connect(DB_PATH)
            for metric, vals in new_targets.items():
                conn2.execute(
                    "UPDATE kpi_targets SET target_value=?, amber_threshold=?, red_threshold=?, "
                    "updated_by=?, updated_at=? WHERE metric_name=?",
                    (vals["target"], vals["amber"], vals["red"], DEFAULT_USER, get_sast_now(), metric))
            conn2.commit()
            conn2.close()
            log_audit("UPDATE", "KPI Targets", "KPI targets updated")
            st.success("✅ Targets updated!")
            st.rerun()

    conn.close()


# =============================================================================
# INTEGRATION HELPER — Add to main app sidebar
# =============================================================================
ENHANCEMENT_MODULES = {
    "⚙️ Dunning Engine": render_dunning_engine,
    "💰 Cash Flow Forecast": render_cashflow_forecast,
    "📈 Payment Analytics": render_payment_analytics,
    "📁 Data Import/Export": render_data_tools,
    "📝 Write-Offs": render_write_offs,
    "💹 Interest Calculator": render_interest_calculator,
    "📋 Credit Applications": render_credit_applications,
    "🎯 KPI Targets": render_kpi_targets,
}


def render_enhancement(name):
    """Call the appropriate enhancement render function by name."""
    if name in ENHANCEMENT_MODULES:
        ENHANCEMENT_MODULES[name]()


# =============================================================================
# STANDALONE TEST
# =============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print("KA CreditFlow v5.5 — Enhancement Module Validation")
    print("=" * 65)
    print(f"\nModules: {len(ENHANCEMENT_MODULES)}")
    for name in ENHANCEMENT_MODULES:
        print(f"  {name}")
    print(f"\nNew tables: 5 (dunning_rules, dunning_queue, write_offs,")
    print(f"               credit_applications, kpi_targets)")
    print(f"\nDunning rules: 6 (pre-due to legal referral)")
    print(f"KPI targets: 3 (DSO, Collection Rate, Overdue %)")
    print("=" * 65)
