"""
KA CreditFlow v5.5 — Enterprise Edition
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import math
from datetime import datetime, timezone, timedelta, date

# Enhancement modules (v5.5)
try:
    from ka_creditflow_enhancements import (
        init_enhancements_db, render_dunning_engine, render_cashflow_forecast,
        render_payment_analytics, render_data_tools, render_write_offs,
        render_interest_calculator, render_credit_applications, render_kpi_targets
    )
    ENHANCEMENTS_AVAILABLE = True
except ImportError:
    ENHANCEMENTS_AVAILABLE = False

# v6.0 modules
try:
    from ka_creditflow_auth import (
        init_auth_db, render_login, render_user_management,
        render_sidebar_user_info, is_authenticated, get_current_user,
        get_allowed_modules, logout
    )
    from ka_creditflow_workflows import render_workflows, init_workflows_db
    from ka_creditflow_legal import render_legal_compliance, init_legal_db
    from ka_creditflow_pdf import render_document_center
    from ka_creditflow_popia_predictive import (
        render_popia_compliance, render_predictive_engine,
        init_popia_predictive_db
    )
    V6_AVAILABLE = True
except ImportError:
    V6_AVAILABLE = False
# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"
CURRENCY_DEFAULT = "ZAR"
VAT_RATE = 0.15

RISK_GRADE_MAP = {
    "A": {"label": "Excellent", "range": "80-100", "colour": "#198754", "pd": 0.005},
    "B": {"label": "Good",      "range": "60-79",  "colour": "#20c997", "pd": 0.02},
    "C": {"label": "Fair",      "range": "40-59",  "colour": "#ffc107", "pd": 0.05},
    "D": {"label": "Poor",      "range": "20-39",  "colour": "#fd7e14", "pd": 0.15},
    "E": {"label": "Critical",  "range": "0-19",   "colour": "#dc3545", "pd": 0.35},
}

NOTE_TYPES = [
    "Internal Note", "Client Call", "Email Sent", "SMS / WhatsApp Sent",
    "Promise to Pay", "Dispute", "Escalation", "Meeting", "Site Visit",
]

NOTE_TYPE_COLOURS = {
    "Internal Note": "#6c757d", "Client Call": "#0d6efd", "Email Sent": "#198754",
    "SMS / WhatsApp Sent": "#20c997", "Promise to Pay": "#ffc107",
    "Dispute": "#dc3545", "Escalation": "#e35d6a", "Meeting": "#6f42c1",
    "Site Visit": "#0dcaf0",
}

CHANNEL_ICONS = {"SMS": "📱", "Email": "📧", "WhatsApp": "💬"}
CHANNEL_COLOURS = {"SMS": "#0d6efd", "Email": "#198754", "WhatsApp": "#25D366"}

REMINDER_TYPES = [
    "Friendly Reminder", "30-Day Overdue", "60-Day Overdue", "90-Day Overdue",
    "Final Demand", "Promise to Pay Follow-Up", "Custom",
]

STATUS_COLOURS = {
    "Sent": "#198754", "Failed": "#dc3545", "Pending": "#ffc107", "Scheduled": "#0d6efd",
}

SA_PUBLIC_HOLIDAYS_2026 = [
    date(2026, 1, 1), date(2026, 3, 21), date(2026, 4, 3), date(2026, 4, 6),
    date(2026, 4, 27), date(2026, 5, 1), date(2026, 6, 16), date(2026, 8, 9),
    date(2026, 8, 10), date(2026, 9, 24), date(2026, 12, 16),
    date(2026, 12, 25), date(2026, 12, 26),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="KA CreditFlow v5.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
def get_sast_now():
    """Return current SAST datetime as formatted string."""
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    """Return a database connection with row_factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    """Insert an immutable record into the audit trail."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO audit_trail (action_type, module, description, user, details, created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()),
    )
    conn.commit()
    conn.close()


def check_nca_compliance(check_time=None):
    """Check if current SAST time falls within NCA-allowed contact hours."""
    now = check_time or datetime.now(SAST)
    day_name = now.strftime("%A")
    time_str = now.strftime("%H:%M")
    hour = now.hour
    result = {"compliant": True, "current_time": time_str, "current_day": day_name,
              "reason": "Within allowed contact hours.", "next_window": ""}
    if now.date() in SA_PUBLIC_HOLIDAYS_2026:
        result["compliant"] = False
        result["reason"] = f"Today ({now.strftime('%d %B %Y')}) is a SA public holiday."
        nxt = now + timedelta(days=1)
        while nxt.weekday() >= 5 or nxt.date() in SA_PUBLIC_HOLIDAYS_2026:
            nxt += timedelta(days=1)
        result["next_window"] = nxt.strftime("%A %d %B %Y") + " at 08:00 SAST"
        return result
    if now.weekday() >= 5:
        result["compliant"] = False
        result["reason"] = f"Today is {day_name}. No contact on weekends."
        days_to_mon = 7 - now.weekday()
        nxt = now + timedelta(days=days_to_mon)
        result["next_window"] = nxt.strftime("%A %d %B %Y") + " at 08:00 SAST"
        return result
    if hour < 8:
        result["compliant"] = False
        result["reason"] = f"Current time {time_str} SAST is before 08:00."
        result["next_window"] = f"Today ({day_name}) at 08:00 SAST"
        return result
    if hour >= 20:
        result["compliant"] = False
        result["reason"] = f"Current time {time_str} SAST is after 20:00."
        nxt = now + timedelta(days=1)
        while nxt.weekday() >= 5 or nxt.date() in SA_PUBLIC_HOLIDAYS_2026:
            nxt += timedelta(days=1)
        result["next_window"] = nxt.strftime("%A %d %B %Y") + " at 08:00 SAST"
        return result
    return result


def get_message_template(reminder_type, client_name="{Client}", amount="{Amount}",
                         invoice_ref="{Ref}", due_date="{Due Date}"):
    """Return subject and body for a reminder type."""
    templates = {
        "Friendly Reminder": {
            "subject": f"Friendly Payment Reminder — {invoice_ref}",
            "body": (f"Dear {client_name},\n\nThis is a friendly reminder that invoice "
                     f"{invoice_ref} for {amount} was due on {due_date}.\n\nIf payment has "
                     f"already been made, please disregard this message.\n\nKind regards,\n"
                     f"KA Legacy — Credit Management"),
        },
        "30-Day Overdue": {
            "subject": f"30-Day Overdue Notice — {invoice_ref}",
            "body": (f"Dear {client_name},\n\nInvoice {invoice_ref} for {amount} (due "
                     f"{due_date}) is now 30 days past due. Please arrange immediate payment "
                     f"or contact us to discuss a payment arrangement.\n\nRegards,\n"
                     f"KA Legacy — Credit Management"),
        },
        "60-Day Overdue": {
            "subject": f"60-Day Overdue — Urgent — {invoice_ref}",
            "body": (f"Dear {client_name},\n\nInvoice {invoice_ref} for {amount} is now 60 "
                     f"days past due. We strongly urge immediate settlement or contact within "
                     f"7 business days.\n\nFailure to respond may result in escalation.\n\n"
                     f"Regards,\nKA Legacy — Credit Management"),
        },
        "90-Day Overdue": {
            "subject": f"90-Day Overdue — Final Warning — {invoice_ref}",
            "body": (f"Dear {client_name},\n\nInvoice {invoice_ref} for {amount} is 90 days "
                     f"past due. This is a final warning before handover to external "
                     f"collections.\n\nPlease arrange payment within 5 business days.\n\n"
                     f"Regards,\nKA Legacy — Credit Management"),
        },
        "Final Demand": {
            "subject": f"FINAL DEMAND — {invoice_ref} — Legal Action Pending",
            "body": (f"Dear {client_name},\n\nFINAL DEMAND NOTICE\n\nInvoice {invoice_ref} "
                     f"for {amount} remains in default. If full settlement is not received "
                     f"within 48 hours:\n1. Credit bureau reporting\n2. Legal referral\n"
                     f"3. All costs pursued\n\nRegards,\nKA Legacy — Credit Management"),
        },
        "Promise to Pay Follow-Up": {
            "subject": f"Follow-Up: Promise to Pay — {invoice_ref}",
            "body": (f"Dear {client_name},\n\nWe are following up on your commitment to "
                     f"settle invoice {invoice_ref} for {amount} by {due_date}.\n\nPlease "
                     f"confirm payment status.\n\nRegards,\nKA Legacy — Credit Management"),
        },
        "Custom": {
            "subject": "",
            "body": (f"Dear {client_name},\n\n[Your message here]\n\nRegards,\n"
                     f"KA Legacy — Credit Management"),
        },
    }
    return templates.get(reminder_type, templates["Custom"])


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════
def init_db():
    """Create all tables if they do not exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        contact_person TEXT,
        email TEXT,
        phone TEXT,
        address TEXT,
        industry TEXT,
        registration_number TEXT,
        vat_number TEXT,
        payment_terms TEXT DEFAULT 'Net 30',
        credit_limit REAL DEFAULT 50000,
        risk_grade TEXT DEFAULT 'C',
        status TEXT DEFAULT 'Active',
        created_at TEXT,
        updated_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        invoice_number TEXT UNIQUE,
        invoice_date TEXT,
        due_date TEXT,
        amount REAL,
        currency TEXT DEFAULT 'ZAR',
        vat_applicable INTEGER DEFAULT 1,
        vat_amount REAL DEFAULT 0,
        total_amount REAL,
        description TEXT,
        status TEXT DEFAULT 'Open',
        amount_paid REAL DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        client_id INTEGER,
        payment_date TEXT,
        amount REAL,
        payment_method TEXT,
        reference TEXT,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS collection_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        note_type TEXT NOT NULL,
        note_text TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS communication_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        message_subject TEXT,
        message_body TEXT NOT NULL,
        recipient_contact TEXT NOT NULL,
        sent_by TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        status TEXT DEFAULT 'Sent',
        nca_compliant INTEGER DEFAULT 1,
        reminder_type TEXT NOT NULL,
        linked_invoice_id TEXT,
        notes TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS disputes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        invoice_id INTEGER,
        dispute_type TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'Open',
        resolution TEXT,
        raised_by TEXT,
        raised_at TEXT,
        resolved_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS promises_to_pay (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        invoice_id INTEGER,
        promised_amount REAL,
        promised_date TEXT,
        status TEXT DEFAULT 'Pending',
        notes TEXT,
        created_by TEXT,
        created_at TEXT,
        followed_up_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS credit_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        payment_history_score REAL,
        exposure_score REAL,
        aging_score REAL,
        relationship_score REAL,
        external_score REAL,
        composite_score REAL,
        risk_grade TEXT,
        pd_estimate REAL,
        lgd REAL DEFAULT 0.45,
        ead REAL,
        ecl REAL,
        scored_at TEXT,
        scored_by TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS audit_trail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT NOT NULL,
        module TEXT,
        description TEXT,
        user TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    )""")

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DATA
# ═══════════════════════════════════════════════════════════════════════════════
def seed_data():
    """Populate the database with sample data if clients table is empty."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM clients")
    if c.fetchone()[0] > 0:
        conn.close()
        return

    now = get_sast_now()
    today = date(2026, 5, 29)

    # ── Clients ──────────────────────────────────────────────────────────
    clients = [
        ("Talon Estates (Pty) Ltd", "John Mkhize", "john@talonestates.co.za",
         "+27 82 345 6789", "14 Rivonia Road, Sandton, 2196", "Property Management",
         "2018/123456/07", "4123456789", "Net 30", 500000, "B", "Active", now, now),
        ("Lambert Property Portfolio", "Sarah Lambert", "sarah@lambertprop.co.za",
         "+27 83 456 7890", "22 Oxford Road, Rosebank, 2196", "Real Estate",
         "2015/654321/07", "4987654321", "Net 60", 750000, "A", "Active", now, now),
        ("Greenfield Managing Agents", "Thabo Nkosi", "thabo@greenfield.co.za",
         "+27 84 567 8901", "8 Jan Smuts Ave, Westcliff, 2193", "Property Management",
         "2020/111222/07", "4111222333", "Net 30", 200000, "D", "Active", now, now),
        ("Horizon Sectional Title Managers", "Priya Naidoo", "priya@horizonstm.co.za",
         "+27 85 678 9012", "45 Sandton Drive, Sandton, 2196", "Sectional Title",
         "2019/333444/07", "4333444555", "Net 30", 300000, "C", "Active", now, now),
    ]
    c.executemany(
        "INSERT INTO clients (company_name,contact_person,email,phone,address,industry,"
        "registration_number,vat_number,payment_terms,credit_limit,risk_grade,status,"
        "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", clients
    )

    # ── Invoices ─────────────────────────────────────────────────────────
    invoices = [
        # Talon (id=1) — mix of current and overdue
        (1, "INV-2026-0401", "2026-03-01", "2026-03-31", 125000, "ZAR", 1, 18750, 143750,
         "Property management consulting — March 2026", "Open", 0, now),
        (1, "INV-2026-0402", "2026-04-01", "2026-04-30", 85000, "ZAR", 1, 12750, 97750,
         "Compliance audit — April 2026", "Partially Paid", 40000, now),
        (1, "INV-2026-0501", "2026-05-01", "2026-05-31", 95000, "ZAR", 1, 14250, 109250,
         "Risk assessment services — May 2026", "Open", 0, now),
        # Lambert (id=2) — good payer
        (2, "INV-2026-0201", "2026-02-01", "2026-04-01", 250000, "ZAR", 1, 37500, 287500,
         "Portfolio restructuring phase 1", "Paid", 287500, now),
        (2, "INV-2026-0403", "2026-04-15", "2026-06-14", 180000, "ZAR", 1, 27000, 207000,
         "Portfolio restructuring phase 2", "Open", 0, now),
        # Greenfield (id=3) — high risk, very overdue
        (3, "INV-2026-0101", "2026-01-15", "2026-02-14", 75000, "ZAR", 1, 11250, 86250,
         "Body corporate compliance review", "Open", 0, now),
        (3, "INV-2026-0301", "2026-02-15", "2026-03-17", 45000, "ZAR", 1, 6750, 51750,
         "Monthly management fee — Feb 2026", "Disputed", 0, now),
        (3, "INV-2026-0502", "2026-05-01", "2026-05-31", 55000, "ZAR", 1, 8250, 63250,
         "Ad-hoc advisory — May 2026", "Open", 0, now),
        # Horizon (id=4) — moderate
        (4, "INV-2026-0301H", "2026-03-01", "2026-03-31", 110000, "ZAR", 1, 16500, 126500,
         "Sectional title compliance — March 2026", "Partially Paid", 60000, now),
        (4, "INV-2026-0503", "2026-05-10", "2026-06-09", 65000, "ZAR", 1, 9750, 74750,
         "Managing agent services — May 2026", "Open", 0, now),
    ]
    c.executemany(
        "INSERT INTO invoices (client_id,invoice_number,invoice_date,due_date,amount,"
        "currency,vat_applicable,vat_amount,total_amount,description,status,amount_paid,"
        "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", invoices
    )

    # ── Payments ─────────────────────────────────────────────────────────
    payments = [
        (2, 1, "2026-03-28", 40000, "EFT", "REF-TLN-001", "Partial payment received", now),
        (4, 2, "2026-03-25", 287500, "EFT", "REF-LMB-001", "Full settlement", now),
        (9, 4, "2026-04-15", 60000, "EFT", "REF-HRZ-001", "Partial payment", now),
    ]
    c.executemany(
        "INSERT INTO payments (invoice_id,client_id,payment_date,amount,payment_method,"
        "reference,notes,created_at) VALUES (?,?,?,?,?,?,?,?)", payments
    )

    # ── Collection Notes ─────────────────────────────────────────────────
    notes = [
        (1, "Client Call", "Spoke with John re: overdue INV-2026-0401 (R143,750). He confirmed reviewing the invoice.", DEFAULT_USER, "2026-05-20 10:30:00"),
        (1, "Internal Note", "Flagged Talon for 60-day follow-up. Payment history deteriorating.", DEFAULT_USER, "2026-05-22 14:15:00"),
        (3, "Client Call", "Called Thabo at Greenfield. No answer — voicemail left.", DEFAULT_USER, "2026-05-15 09:00:00"),
        (3, "Escalation", "Greenfield account escalated — INV-2026-0101 now 100+ days overdue.", DEFAULT_USER, "2026-05-25 11:00:00"),
        (4, "Promise to Pay", "Priya committed to settling remaining R66,500 on INV-2026-0301H by 05 June.", DEFAULT_USER, "2026-05-27 16:00:00"),
        (2, "Email Sent", "Sent phase 2 invoice confirmation to Sarah at Lambert.", DEFAULT_USER, "2026-05-28 08:30:00"),
    ]
    c.executemany(
        "INSERT INTO collection_notes (client_id,note_type,note_text,created_by,created_at) VALUES (?,?,?,?,?)",
        notes
    )

    # ── Communication Log ────────────────────────────────────────────────
    comms = [
        (1, "Email", "30-Day Overdue Notice — INV-2026-0401", "Dear Talon Estates, invoice INV-2026-0401 for R143,750 is 30 days overdue...",
         "john@talonestates.co.za", DEFAULT_USER, "2026-05-01 09:00:00", "Sent", 1, "30-Day Overdue", "INV-2026-0401", "Auto-sent"),
        (3, "SMS", "Payment Reminder", "Greenfield: INV-2026-0101 for R86,250 is overdue. Please arrange payment. — KA Legacy",
         "+27 84 567 8901", DEFAULT_USER, "2026-05-15 09:15:00", "Sent", 1, "60-Day Overdue", "INV-2026-0101", ""),
        (3, "WhatsApp", "Payment Reminder", "Hi Thabo, please confirm payment status on INV-2026-0101 (R86,250). — KA Legacy",
         "+27 84 567 8901", DEFAULT_USER, "2026-05-20 10:00:00", "Sent", 1, "90-Day Overdue", "INV-2026-0101", ""),
    ]
    c.executemany(
        "INSERT INTO communication_log (client_id,channel,message_subject,message_body,"
        "recipient_contact,sent_by,sent_at,status,nca_compliant,reminder_type,"
        "linked_invoice_id,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", comms
    )

    # ── Disputes ─────────────────────────────────────────────────────────
    c.execute(
        "INSERT INTO disputes (client_id,invoice_id,dispute_type,description,status,"
        "raised_by,raised_at) VALUES (?,?,?,?,?,?,?)",
        (3, 7, "Pricing", "Client disputes hourly rate applied on Feb management fee. Claims agreed rate was lower.",
         "Open", "Thabo Nkosi", "2026-03-20 10:00:00"),
    )

    # ── Promises to Pay ──────────────────────────────────────────────────
    c.execute(
        "INSERT INTO promises_to_pay (client_id,invoice_id,promised_amount,promised_date,"
        "status,notes,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (4, 9, 66500, "2026-06-05", "Pending",
         "Priya committed verbally during call on 27 May", DEFAULT_USER, "2026-05-27 16:00:00"),
    )

    # ── Credit Scores ────────────────────────────────────────────────────
    scores = [
        (1, 55, 70, 45, 80, 65, 0, "C", 0, 0.45, 0, 0, now, DEFAULT_USER),
        (2, 95, 90, 95, 90, 85, 0, "A", 0, 0.45, 0, 0, now, DEFAULT_USER),
        (3, 20, 85, 15, 40, 35, 0, "D", 0, 0.45, 0, 0, now, DEFAULT_USER),
        (4, 60, 55, 50, 70, 55, 0, "C", 0, 0.45, 0, 0, now, DEFAULT_USER),
    ]
    # Calculate composite and derived values
    weights = {"payment_history": 0.30, "exposure": 0.20, "aging": 0.25,
               "relationship": 0.10, "external": 0.15}
    final_scores = []
    for s in scores:
        composite = (s[1]*weights["payment_history"] + s[2]*weights["exposure"] +
                     s[3]*weights["aging"] + s[4]*weights["relationship"] +
                     s[5]*weights["external"])
        if composite >= 80: grade = "A"
        elif composite >= 60: grade = "B"
        elif composite >= 40: grade = "C"
        elif composite >= 20: grade = "D"
        else: grade = "E"
        pd_est = RISK_GRADE_MAP[grade]["pd"]
        # EAD = total outstanding for client (simplified — use total_amount of open invoices)
        ead = 0  # Will be updated in the app
        ecl = pd_est * s[11] * ead
        final_scores.append((s[0], s[1], s[2], s[3], s[4], s[5], round(composite, 2),
                             grade, pd_est, s[11], ead, ecl, s[12], s[13]))

    c.executemany(
        "INSERT INTO credit_scores (client_id,payment_history_score,exposure_score,"
        "aging_score,relationship_score,external_score,composite_score,risk_grade,"
        "pd_estimate,lgd,ead,ecl,scored_at,scored_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        final_scores
    )

    # ── Audit Trail ──────────────────────────────────────────────────────
    audit_entries = [
        ("SYSTEM", "Database", "KA CreditFlow v5.0 database initialized with seed data", "System", "", now),
        ("CREATE", "Clients", "4 sample clients created", DEFAULT_USER, "", now),
        ("CREATE", "Invoices", "10 sample invoices created", DEFAULT_USER, "", now),
        ("CREATE", "Payments", "3 sample payments recorded", DEFAULT_USER, "", now),
        ("CREATE", "Credit Scores", "Initial credit scores calculated for all clients", DEFAULT_USER, "", now),
    ]
    c.executemany(
        "INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        audit_entries
    )

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 1 — EXECUTIVE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
def render_dashboard():
    st.markdown("## 📊 Executive Dashboard")
    st.caption(f"As at {get_sast_now()} SAST")
    conn = get_db()
    today = date.today()

    # ── KPI Queries ──────────────────────────────────────────────────────
    inv = pd.read_sql("SELECT * FROM invoices", conn)
    clients_df = pd.read_sql("SELECT * FROM clients", conn)
    disputes_df = pd.read_sql("SELECT * FROM disputes WHERE status='Open'", conn)

    inv["due"] = pd.to_datetime(inv["due_date"]).dt.date
    inv["outstanding"] = inv["total_amount"] - inv["amount_paid"]
    open_inv = inv[inv["status"].isin(["Open", "Partially Paid", "Disputed"])]

    total_ar = open_inv["outstanding"].sum()
    overdue_inv = open_inv[open_inv["due"] < today]
    total_overdue = overdue_inv["outstanding"].sum()
    total_collected = inv["amount_paid"].sum()
    total_invoiced = inv["total_amount"].sum()
    collection_rate = (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0
    active_clients = len(clients_df[clients_df["status"] == "Active"])
    open_disputes = len(disputes_df)

    # DSO = (AR / Total Credit Sales) * Days in Period
    dso = (total_ar / total_invoiced * 365) if total_invoiced > 0 else 0

    # ── KPI Row ──────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("💰 Total AR Outstanding", f"R {total_ar:,.2f}")
    k2.metric("🔴 Total Overdue", f"R {total_overdue:,.2f}")
    k3.metric("📅 DSO (Days)", f"{dso:.0f}")
    k4.metric("✅ Collection Rate", f"{collection_rate:.1f}%")
    k5.metric("👥 Active Clients", active_clients)
    k6.metric("⚠️ Open Disputes", open_disputes)

    st.divider()

    col_chart1, col_chart2 = st.columns(2)

    # ── Aging Bucket Chart ───────────────────────────────────────────────
    with col_chart1:
        st.markdown("### 📊 Aging Summary")
        if len(open_inv) > 0:
            open_inv = open_inv.copy()
            open_inv["days_overdue"] = open_inv["due"].apply(
                lambda d: max(0, (today - d).days)
            )
            def bucket(days):
                if days == 0: return "Current"
                elif days <= 30: return "1-30 Days"
                elif days <= 60: return "31-60 Days"
                elif days <= 90: return "61-90 Days"
                elif days <= 120: return "91-120 Days"
                else: return "120+ Days"
            open_inv["bucket"] = open_inv["days_overdue"].apply(bucket)
            bucket_order = ["Current", "1-30 Days", "31-60 Days", "61-90 Days", "91-120 Days", "120+ Days"]
            aging = open_inv.groupby("bucket")["outstanding"].sum().reindex(bucket_order, fill_value=0).reset_index()
            aging.columns = ["Aging Bucket", "Amount (R)"]
            colours = ["#198754", "#20c997", "#ffc107", "#fd7e14", "#dc3545", "#842029"]
            fig = px.bar(aging, x="Aging Bucket", y="Amount (R)",
                         color="Aging Bucket", color_discrete_sequence=colours,
                         text_auto=",.0f")
            fig.update_layout(showlegend=False, height=350, margin=dict(t=10, b=10))
            fig.update_traces(texttemplate="R %{text:,.0f}", textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No open invoices to display.")

    # ── Risk Distribution Donut ──────────────────────────────────────────
    with col_chart2:
        st.markdown("### 🛡️ Risk Distribution")
        scores = pd.read_sql(
            "SELECT cs.* FROM credit_scores cs INNER JOIN "
            "(SELECT client_id, MAX(id) as max_id FROM credit_scores GROUP BY client_id) latest "
            "ON cs.id = latest.max_id", conn)
        if len(scores) > 0:
            risk_counts = scores["risk_grade"].value_counts().reset_index()
            risk_counts.columns = ["Grade", "Count"]
            risk_counts["Label"] = risk_counts["Grade"].map(
                lambda g: f"{g} — {RISK_GRADE_MAP.get(g,{}).get('label','')}")
            colour_map = {row["Label"]: RISK_GRADE_MAP.get(row["Grade"],{}).get("colour","#6c757d")
                          for _, row in risk_counts.iterrows()}
            fig2 = px.pie(risk_counts, names="Label", values="Count", hole=0.5,
                          color="Label", color_discrete_map=colour_map)
            fig2.update_layout(height=350, margin=dict(t=10, b=10))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No credit scores calculated yet.")

    # ── Recent Activity Feed ─────────────────────────────────────────────
    st.divider()
    st.markdown("### 🕐 Recent Activity")
    audit = pd.read_sql("SELECT * FROM audit_trail ORDER BY created_at DESC LIMIT 10", conn)
    if len(audit) > 0:
        for _, row in audit.iterrows():
            st.markdown(
                f"<div style='padding:6px 12px;margin-bottom:4px;background:#f8f9fa;"
                f"border-left:3px solid #0d6efd;border-radius:4px;font-size:0.9em;'>"
                f"<strong>{row['action_type']}</strong> · {row['module']} · "
                f"{row['description']} "
                f"<span style='color:#888;font-size:0.8em;'>— {row['user']} at {row['created_at']}</span>"
                f"</div>", unsafe_allow_html=True)
    else:
        st.info("No activity recorded yet.")
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 2 — CLIENT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
def render_clients():
    st.markdown("## 🏢 Client Management")
    mode = st.radio("", ["📋 Client List", "➕ Add New Client"], horizontal=True, key="client_mode")

    conn = get_db()

    if mode == "📋 Client List":
        clients = pd.read_sql("SELECT * FROM clients ORDER BY company_name", conn)
        if len(clients) == 0:
            st.info("No clients found.")
            conn.close()
            return

        st.markdown(f"**{len(clients)} clients** registered")

        # Display table
        display_df = clients[["id", "company_name", "contact_person", "industry",
                              "payment_terms", "credit_limit", "risk_grade", "status"]].copy()
        display_df.columns = ["ID", "Company", "Contact", "Industry", "Terms",
                              "Credit Limit", "Risk Grade", "Status"]
        display_df["Credit Limit"] = display_df["Credit Limit"].apply(lambda x: f"R {x:,.0f}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # ── Client Profile ───────────────────────────────────────────────
        st.divider()
        st.markdown("### 👤 Client Profile")
        client_list = {row["company_name"]: row["id"] for _, row in clients.iterrows()}
        selected = st.selectbox("Select client to view profile", ["—"] + list(client_list.keys()), key="profile_sel")

        if selected != "—":
            cid = client_list[selected]
            cl = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()

            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                st.markdown(f"**Company:** {cl['company_name']}")
                st.markdown(f"**Contact:** {cl['contact_person']}")
                st.markdown(f"**Email:** {cl['email']}")
                st.markdown(f"**Phone:** {cl['phone']}")
            with pc2:
                st.markdown(f"**Industry:** {cl['industry']}")
                st.markdown(f"**Reg No:** {cl['registration_number']}")
                st.markdown(f"**VAT No:** {cl['vat_number']}")
                st.markdown(f"**Address:** {cl['address']}")
            with pc3:
                grade = cl["risk_grade"]
                grade_info = RISK_GRADE_MAP.get(grade, {})
                st.markdown(f"**Payment Terms:** {cl['payment_terms']}")
                st.markdown(f"**Credit Limit:** R {cl['credit_limit']:,.0f}")
                colour = grade_info.get("colour", "#6c757d")
                st.markdown(f"**Risk Grade:** <span style='background:{colour};color:white;"
                            f"padding:2px 10px;border-radius:10px;font-weight:bold;'>"
                            f"{grade} — {grade_info.get('label','')}</span>",
                            unsafe_allow_html=True)
                st.markdown(f"**Status:** {cl['status']}")

            # Client invoices
            st.markdown("#### 🧾 Invoices")
            inv = pd.read_sql("SELECT * FROM invoices WHERE client_id=? ORDER BY due_date DESC", conn, params=(cid,))
            if len(inv) > 0:
                inv["outstanding"] = inv["total_amount"] - inv["amount_paid"]
                inv_display = inv[["invoice_number", "invoice_date", "due_date", "total_amount",
                                   "amount_paid", "outstanding", "status"]].copy()
                inv_display.columns = ["Invoice #", "Date", "Due", "Total", "Paid", "Outstanding", "Status"]
                for col in ["Total", "Paid", "Outstanding"]:
                    inv_display[col] = inv_display[col].apply(lambda x: f"R {x:,.2f}")
                st.dataframe(inv_display, use_container_width=True, hide_index=True)
            else:
                st.info("No invoices for this client.")

            # Last note
            last_note = conn.execute(
                "SELECT * FROM collection_notes WHERE client_id=? ORDER BY created_at DESC LIMIT 1",
                (cid,)).fetchone()
            if last_note:
                st.markdown(f"#### 📝 Last Note")
                st.markdown(f"> **{last_note['note_type']}** ({last_note['created_at']}): {last_note['note_text']}")

            # Last communication
            last_comm = conn.execute(
                "SELECT * FROM communication_log WHERE client_id=? ORDER BY sent_at DESC LIMIT 1",
                (cid,)).fetchone()
            if last_comm:
                st.markdown(f"#### 📨 Last Communication")
                st.markdown(f"> **{last_comm['channel']}** — {last_comm['reminder_type']} ({last_comm['sent_at']})")

    else:  # Add New Client
        st.markdown("### ➕ Register New Client")
        with st.form("add_client_form"):
            ac1, ac2 = st.columns(2)
            with ac1:
                company = st.text_input("Company Name *")
                contact = st.text_input("Contact Person")
                email = st.text_input("Email")
                phone = st.text_input("Phone")
                address = st.text_area("Address", height=80)
            with ac2:
                industry = st.text_input("Industry")
                reg_no = st.text_input("Registration Number")
                vat_no = st.text_input("VAT Number")
                terms = st.selectbox("Payment Terms", ["Net 30", "Net 60", "Net 90", "COD"])
                credit_limit = st.number_input("Credit Limit (R)", min_value=0.0, value=50000.0, step=5000.0)

            submitted = st.form_submit_button("💾 Save Client", type="primary")
            if submitted:
                if not company.strip():
                    st.warning("Company name is required.")
                else:
                    now = get_sast_now()
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute(
                        "INSERT INTO clients (company_name,contact_person,email,phone,address,"
                        "industry,registration_number,vat_number,payment_terms,credit_limit,"
                        "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (company, contact, email, phone, address, industry, reg_no, vat_no,
                         terms, credit_limit, now, now))
                    conn2.commit()
                    conn2.close()
                    log_audit("CREATE", "Clients", f"New client registered: {company}")
                    st.success(f"✅ Client '{company}' registered successfully!")
                    st.rerun()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3 — INVOICE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
def render_invoices():
    st.markdown("## 🧾 Invoice Management")
    mode = st.radio("", ["📋 Invoice List", "➕ Create Invoice", "💰 Record Payment"],
                    horizontal=True, key="inv_mode")
    conn = get_db()
    today = date.today()

    if mode == "📋 Invoice List":
        inv = pd.read_sql(
            "SELECT i.*, c.company_name FROM invoices i "
            "JOIN clients c ON i.client_id = c.id ORDER BY i.due_date", conn)
        if len(inv) == 0:
            st.info("No invoices found.")
            conn.close()
            return
        inv["outstanding"] = inv["total_amount"] - inv["amount_paid"]
        inv["due"] = pd.to_datetime(inv["due_date"]).dt.date
        inv["days_overdue"] = inv["due"].apply(lambda d: max(0, (today - d).days))

        display = inv[["invoice_number", "company_name", "invoice_date", "due_date",
                        "amount", "vat_amount", "total_amount", "amount_paid",
                        "outstanding", "status", "days_overdue"]].copy()
        display.columns = ["Invoice #", "Client", "Date", "Due", "Amount", "VAT",
                           "Total", "Paid", "Outstanding", "Status", "Days Overdue"]
        for col in ["Amount", "VAT", "Total", "Paid", "Outstanding"]:
            display[col] = display[col].apply(lambda x: f"R {x:,.2f}")

        st.markdown(f"**{len(display)} invoices** · "
                    f"**Total Outstanding: R {inv['outstanding'].sum():,.2f}**")
        st.dataframe(display, use_container_width=True, hide_index=True)

    elif mode == "➕ Create Invoice":
        st.markdown("### ➕ Create New Invoice")
        clients = pd.read_sql("SELECT id, company_name FROM clients WHERE status='Active' ORDER BY company_name", conn)
        if len(clients) == 0:
            st.warning("No active clients. Please add a client first.")
            conn.close()
            return

        with st.form("create_invoice"):
            ci1, ci2 = st.columns(2)
            with ci1:
                client_sel = st.selectbox("Client *", clients["company_name"].tolist())
                client_id = int(clients[clients["company_name"] == client_sel]["id"].values[0])
                inv_num = st.text_input("Invoice Number *", value=f"INV-{datetime.now().strftime('%Y-%m%d')}-")
                inv_date = st.date_input("Invoice Date", value=today)
                due_date = st.date_input("Due Date", value=today + timedelta(days=30))
            with ci2:
                amount = st.number_input("Amount (excl. VAT) R", min_value=0.01, value=10000.0, step=500.0)
                currency = st.selectbox("Currency", ["ZAR", "USD", "EUR", "GBP"])
                vat_toggle = st.checkbox("VAT Applicable (15%)", value=True)
                vat_amt = round(amount * VAT_RATE, 2) if vat_toggle else 0
                total = amount + vat_amt
                st.markdown(f"**VAT:** R {vat_amt:,.2f}")
                st.markdown(f"**Total:** R {total:,.2f}")
                description = st.text_area("Description")

            if st.form_submit_button("💾 Create Invoice", type="primary"):
                if not inv_num.strip():
                    st.warning("Invoice number is required.")
                else:
                    now = get_sast_now()
                    try:
                        conn2 = sqlite3.connect(DB_PATH)
                        conn2.execute(
                            "INSERT INTO invoices (client_id,invoice_number,invoice_date,due_date,"
                            "amount,currency,vat_applicable,vat_amount,total_amount,description,"
                            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (client_id, inv_num, str(inv_date), str(due_date), amount, currency,
                             1 if vat_toggle else 0, vat_amt, total, description, now))
                        conn2.commit()
                        conn2.close()
                        log_audit("CREATE", "Invoices", f"Invoice {inv_num} created for {client_sel} — R {total:,.2f}")
                        st.success(f"✅ Invoice {inv_num} created successfully!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("❌ Invoice number already exists. Please use a unique number.")

    else:  # Record Payment
        st.markdown("### 💰 Record Payment")
        open_inv = pd.read_sql(
            "SELECT i.*, c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id "
            "WHERE i.status IN ('Open','Partially Paid','Disputed') ORDER BY i.due_date", conn)
        if len(open_inv) == 0:
            st.info("No open invoices to record payments against.")
            conn.close()
            return

        open_inv["outstanding"] = open_inv["total_amount"] - open_inv["amount_paid"]
        open_inv["label"] = open_inv.apply(
            lambda r: f"{r['invoice_number']} — {r['company_name']} — Outstanding: R {r['outstanding']:,.2f}", axis=1)

        with st.form("record_payment"):
            sel_label = st.selectbox("Select Invoice *", open_inv["label"].tolist())
            sel_row = open_inv[open_inv["label"] == sel_label].iloc[0]
            st.markdown(f"**Invoice:** {sel_row['invoice_number']} · **Total:** R {sel_row['total_amount']:,.2f} · "
                        f"**Paid:** R {sel_row['amount_paid']:,.2f} · "
                        f"**Outstanding:** R {sel_row['outstanding']:,.2f}")
            rp1, rp2 = st.columns(2)
            with rp1:
                pay_amount = st.number_input("Payment Amount (R)", min_value=0.01,
                                             max_value=float(sel_row["outstanding"]),
                                             value=float(sel_row["outstanding"]), step=100.0)
                pay_date = st.date_input("Payment Date", value=today, key="pay_date")
            with rp2:
                pay_method = st.selectbox("Payment Method", ["EFT", "Cash", "Credit Card", "Debit Order", "Other"])
                pay_ref = st.text_input("Reference")
                pay_notes = st.text_input("Notes")

            if st.form_submit_button("💾 Record Payment", type="primary"):
                new_paid = sel_row["amount_paid"] + pay_amount
                new_status = "Paid" if abs(new_paid - sel_row["total_amount"]) < 0.01 else "Partially Paid"
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute("UPDATE invoices SET amount_paid=?, status=? WHERE id=?",
                              (new_paid, new_status, int(sel_row["id"])))
                conn2.execute(
                    "INSERT INTO payments (invoice_id,client_id,payment_date,amount,payment_method,"
                    "reference,notes,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (int(sel_row["id"]), int(sel_row["client_id"]), str(pay_date), pay_amount,
                     pay_method, pay_ref, pay_notes, get_sast_now()))
                conn2.commit()
                conn2.close()
                log_audit("PAYMENT", "Invoices",
                          f"R {pay_amount:,.2f} recorded against {sel_row['invoice_number']} — Status: {new_status}")
                st.success(f"✅ Payment of R {pay_amount:,.2f} recorded. Invoice status: **{new_status}**")
                st.rerun()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 4 — CREDIT RISK ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
def render_credit_engine():
    st.markdown("## 🛡️ Credit Risk Engine")
    st.markdown("_Multi-factor scoring model with PD estimation, ECL calculation, and portfolio risk analysis._")
    conn = get_db()
    today = date.today()

    clients = pd.read_sql("SELECT id, company_name, credit_limit FROM clients WHERE status='Active' ORDER BY company_name", conn)
    if len(clients) == 0:
        st.warning("No active clients found.")
        conn.close()
        return

    # ── Weight configuration ─────────────────────────────────────────────
    st.markdown("### ⚖️ Scoring Weights")
    wc1, wc2, wc3, wc4, wc5 = st.columns(5)
    w_payment = wc1.number_input("Payment History %", 0, 100, 30, key="w_pay") / 100
    w_exposure = wc2.number_input("Exposure %", 0, 100, 20, key="w_exp") / 100
    w_aging = wc3.number_input("Aging Profile %", 0, 100, 25, key="w_age") / 100
    w_relationship = wc4.number_input("Relationship %", 0, 100, 10, key="w_rel") / 100
    w_external = wc5.number_input("External Score %", 0, 100, 15, key="w_ext") / 100
    total_weight = w_payment + w_exposure + w_aging + w_relationship + w_external
    if abs(total_weight - 1.0) > 0.01:
        st.warning(f"⚠️ Weights must sum to 100%. Currently: {total_weight*100:.0f}%")

    st.divider()

    # ── Client selector ──────────────────────────────────────────────────
    client_sel = st.selectbox("🏢 Select Client", clients["company_name"].tolist(), key="ce_client")
    cid = int(clients[clients["company_name"] == client_sel]["id"].values[0])
    credit_limit = float(clients[clients["company_name"] == client_sel]["credit_limit"].values[0])

    # Current score
    current_score = conn.execute(
        "SELECT * FROM credit_scores WHERE client_id=? ORDER BY id DESC LIMIT 1",
        (cid,)).fetchone()

    if current_score:
        sc1, sc2 = st.columns([1, 2])
        with sc1:
            composite = current_score["composite_score"]
            grade = current_score["risk_grade"]
            grade_info = RISK_GRADE_MAP.get(grade, {})
            st.metric("Composite Score", f"{composite:.1f} / 100")
            st.markdown(
                f"<div style='text-align:center;background:{grade_info.get('colour','#6c757d')};"
                f"color:white;padding:10px;border-radius:10px;font-size:1.5em;font-weight:bold;'>"
                f"Grade {grade} — {grade_info.get('label','')}</div>", unsafe_allow_html=True)
            st.markdown(f"**PD Estimate:** {current_score['pd_estimate']*100:.1f}%")
            st.markdown(f"**LGD:** {current_score['lgd']*100:.0f}%")
            st.markdown(f"**EAD:** R {current_score['ead']:,.2f}")
            st.markdown(f"**ECL:** R {current_score['ecl']:,.2f}")
            st.caption(f"Last scored: {current_score['scored_at']}")

        with sc2:
            # Radar chart
            categories = ["Payment History", "Exposure", "Aging Profile", "Relationship", "External"]
            values = [current_score["payment_history_score"], current_score["exposure_score"],
                      current_score["aging_score"], current_score["relationship_score"],
                      current_score["external_score"]]
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=values + [values[0]], theta=categories + [categories[0]],
                fill="toself", name=client_sel,
                line_color=grade_info.get("colour", "#0d6efd"),
                fillcolor=grade_info.get("colour", "#0d6efd"),
                opacity=0.4))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=False, height=350, margin=dict(t=30, b=30))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No credit score calculated for this client yet. Click recalculate below.")

    # ── Recalculate Button ───────────────────────────────────────────────
    st.divider()
    st.markdown("### 🔄 Recalculate Credit Score")
    ext_score = st.slider("External Bureau Score (manual input)", 0, 100,
                          int(current_score["external_score"]) if current_score else 50, key="ext_s")

    if st.button("🔄 Recalculate Now", type="primary"):
        # Query invoices
        inv = pd.read_sql("SELECT * FROM invoices WHERE client_id=?", conn, params=(cid,))
        inv["due"] = pd.to_datetime(inv["due_date"]).dt.date
        inv["outstanding"] = inv["total_amount"] - inv["amount_paid"]

        open_inv = inv[inv["status"].isin(["Open", "Partially Paid", "Disputed"])]
        total_outstanding = open_inv["outstanding"].sum()

        # Payment History Score
        paid_inv = inv[inv["status"] == "Paid"]
        if len(paid_inv) > 0:
            # Estimate: days late for paid invoices
            payments_df = pd.read_sql("SELECT * FROM payments WHERE client_id=?", conn, params=(cid,))
            if len(payments_df) > 0:
                avg_days_late = 15  # simplified estimate
            else:
                avg_days_late = 0
        else:
            avg_days_late = 30  # default penalty if never fully paid
        payment_score = max(0, min(100, 100 - avg_days_late * 2))

        # Exposure Score
        utilization = (total_outstanding / credit_limit * 100) if credit_limit > 0 else 100
        exposure_score = max(0, min(100, 100 - utilization))

        # Aging Score
        if len(open_inv) > 0:
            open_inv = open_inv.copy()
            open_inv["days_overdue"] = open_inv["due"].apply(lambda d: max(0, (today - d).days))
            total_open = open_inv["outstanding"].sum()
            over_60 = open_inv[open_inv["days_overdue"] > 60]["outstanding"].sum()
            pct_60 = (over_60 / total_open * 100) if total_open > 0 else 0
        else:
            pct_60 = 0
        aging_score = max(0, min(100, 100 - pct_60 * 1.5))

        # Relationship Score
        if len(inv) > 0:
            first_inv = pd.to_datetime(inv["invoice_date"]).min()
            tenure_months = max(1, (datetime.now() - first_inv).days / 30)
        else:
            tenure_months = 1
        disputes_count = conn.execute("SELECT COUNT(*) FROM disputes WHERE client_id=?", (cid,)).fetchone()[0]
        relationship_score = max(0, min(100, min(tenure_months * 5, 80) - disputes_count * 15 + 20))

        # Composite
        composite = (payment_score * w_payment + exposure_score * w_exposure +
                     aging_score * w_aging + relationship_score * w_relationship +
                     ext_score * w_external)
        composite = round(composite, 2)

        if composite >= 80: grade = "A"
        elif composite >= 60: grade = "B"
        elif composite >= 40: grade = "C"
        elif composite >= 20: grade = "D"
        else: grade = "E"

        pd_est = RISK_GRADE_MAP[grade]["pd"]
        lgd = 0.45
        ead = total_outstanding
        ecl = round(pd_est * lgd * ead, 2)

        # Save
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute(
            "INSERT INTO credit_scores (client_id,payment_history_score,exposure_score,"
            "aging_score,relationship_score,external_score,composite_score,risk_grade,"
            "pd_estimate,lgd,ead,ecl,scored_at,scored_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, round(payment_score, 2), round(exposure_score, 2), round(aging_score, 2),
             round(relationship_score, 2), ext_score, composite, grade, pd_est, lgd, ead, ecl,
             get_sast_now(), DEFAULT_USER))
        conn2.execute("UPDATE clients SET risk_grade=?, updated_at=? WHERE id=?",
                       (grade, get_sast_now(), cid))
        conn2.commit()
        conn2.close()
        log_audit("SCORE", "Credit Engine",
                  f"{client_sel} scored {composite:.1f} → Grade {grade} | ECL: R {ecl:,.2f}")
        st.success(f"✅ **{client_sel}** scored **{composite:.1f}** → Grade **{grade}** "
                   f"| PD: {pd_est*100:.1f}% | ECL: R {ecl:,.2f}")
        st.rerun()

    # ── Portfolio Summary ────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📊 Portfolio Risk Summary")
    portfolio = pd.read_sql(
        "SELECT c.company_name, c.credit_limit, cs.composite_score, cs.risk_grade, "
        "cs.pd_estimate, cs.ead, cs.ecl, cs.scored_at "
        "FROM credit_scores cs "
        "JOIN clients c ON cs.client_id = c.id "
        "INNER JOIN (SELECT client_id, MAX(id) as max_id FROM credit_scores GROUP BY client_id) latest "
        "ON cs.id = latest.max_id ORDER BY cs.composite_score", conn)

    if len(portfolio) > 0:
        portfolio.columns = ["Client", "Credit Limit", "Score", "Grade", "PD %", "EAD", "ECL", "Scored At"]
        portfolio["PD %"] = portfolio["PD %"].apply(lambda x: f"{x*100:.1f}%")
        portfolio["Credit Limit"] = portfolio["Credit Limit"].apply(lambda x: f"R {x:,.0f}")
        portfolio["EAD"] = portfolio["EAD"].apply(lambda x: f"R {x:,.2f}")
        portfolio["ECL"] = portfolio["ECL"].apply(lambda x: f"R {x:,.2f}")
        st.dataframe(portfolio, use_container_width=True, hide_index=True)

        total_ecl = pd.read_sql(
            "SELECT SUM(ecl) as total FROM credit_scores cs "
            "INNER JOIN (SELECT client_id, MAX(id) as max_id FROM credit_scores GROUP BY client_id) latest "
            "ON cs.id = latest.max_id", conn)["total"].values[0] or 0
        st.metric("📊 Total Portfolio ECL Reserve", f"R {total_ecl:,.2f}")

    # ── Credit Limit Breaches ────────────────────────────────────────────
    st.divider()
    st.markdown("### 🚨 Credit Limit Breach Alerts")
    breaches = pd.read_sql(
        "SELECT c.company_name, c.credit_limit, "
        "SUM(i.total_amount - i.amount_paid) as total_outstanding "
        "FROM clients c JOIN invoices i ON c.id = i.client_id "
        "WHERE i.status IN ('Open','Partially Paid','Disputed') "
        "GROUP BY c.id HAVING total_outstanding > c.credit_limit", conn)
    if len(breaches) > 0:
        for _, b in breaches.iterrows():
            overage = b["total_outstanding"] - b["credit_limit"]
            st.error(f"🚨 **{b['company_name']}** — Outstanding R {b['total_outstanding']:,.2f} "
                     f"exceeds credit limit R {b['credit_limit']:,.0f} by **R {overage:,.2f}**")
    else:
        st.success("✅ No credit limit breaches detected.")
    conn.close()



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 5 — COLLECTIONS WORKLIST
# ═══════════════════════════════════════════════════════════════════════════════
def render_worklist():
    st.markdown("## 📋 Collections Worklist")
    st.markdown("_Prioritised accounts sorted by risk × overdue amount. Highest priority first._")
    conn = get_db()
    today = date.today()

    # Build worklist data
    worklist_sql = """
        SELECT c.id, c.company_name, c.credit_limit,
               COALESCE(cs.composite_score, 50) as composite_score,
               COALESCE(cs.risk_grade, 'C') as risk_grade,
               SUM(CASE WHEN i.status IN ('Open','Partially Paid','Disputed')
                        AND i.due_date < ? THEN i.total_amount - i.amount_paid ELSE 0 END) as total_overdue,
               MAX(CASE WHEN i.status IN ('Open','Partially Paid','Disputed')
                        AND i.due_date < ? THEN julianday(?) - julianday(i.due_date) ELSE 0 END) as worst_days,
               SUM(CASE WHEN i.status IN ('Open','Partially Paid','Disputed')
                        THEN i.total_amount - i.amount_paid ELSE 0 END) as total_outstanding
        FROM clients c
        LEFT JOIN invoices i ON c.id = i.client_id
        LEFT JOIN credit_scores cs ON cs.id = (
            SELECT cs2.id FROM credit_scores cs2 WHERE cs2.client_id = c.id ORDER BY cs2.id DESC LIMIT 1
        )
        WHERE c.status = 'Active'
        GROUP BY c.id
        HAVING total_overdue > 0
        ORDER BY (100 - COALESCE(cs.composite_score, 50)) * total_overdue DESC
    """
    today_str = str(today)
    worklist = pd.read_sql(worklist_sql, conn, params=(today_str, today_str, today_str))

    if len(worklist) == 0:
        st.success("✅ No overdue accounts! All collections are current.")
        conn.close()
        return

    # Filters
    fc1, fc2 = st.columns(2)
    with fc1:
        grade_filter = st.multiselect("Filter by Risk Grade", ["A", "B", "C", "D", "E"],
                                       default=["A", "B", "C", "D", "E"], key="wl_grade")
    with fc2:
        bucket_filter = st.selectbox("Min Days Overdue", [0, 30, 60, 90], key="wl_bucket")

    filtered = worklist[worklist["risk_grade"].isin(grade_filter) & (worklist["worst_days"] >= bucket_filter)]

    st.markdown(f"**{len(filtered)} accounts** requiring attention")
    st.divider()

    for _, row in filtered.iterrows():
        cid = int(row["id"])
        grade = row["risk_grade"]
        grade_info = RISK_GRADE_MAP.get(grade, {})
        priority = (100 - row["composite_score"]) * row["total_overdue"] / 10000

        # Last note and communication
        last_note = conn.execute(
            "SELECT created_at FROM collection_notes WHERE client_id=? ORDER BY created_at DESC LIMIT 1",
            (cid,)).fetchone()
        last_comm = conn.execute(
            "SELECT sent_at FROM communication_log WHERE client_id=? ORDER BY sent_at DESC LIMIT 1",
            (cid,)).fetchone()

        last_note_str = last_note["created_at"] if last_note else "Never"
        last_comm_str = last_comm["sent_at"] if last_comm else "Never"

        colour = grade_info.get("colour", "#6c757d")

        st.markdown(f"""
        <div style="border-left:5px solid {colour};padding:16px 20px;margin-bottom:12px;
                    background:#f8f9fa;border-radius:8px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span style="font-size:1.2em;font-weight:bold;">{row['company_name']}</span>
                    &nbsp;
                    <span style="background:{colour};color:white;padding:3px 12px;
                          border-radius:12px;font-size:0.85em;font-weight:600;">
                        Grade {grade} — {grade_info.get('label','')}
                    </span>
                </div>
                <span style="background:#dc3545;color:white;padding:4px 14px;
                      border-radius:12px;font-weight:bold;">
                    Priority: {priority:.0f}
                </span>
            </div>
            <div style="display:flex;gap:40px;margin-top:10px;font-size:0.92em;">
                <div><strong>Total Overdue:</strong> <span style="color:#dc3545;font-weight:bold;">
                    R {row['total_overdue']:,.2f}</span></div>
                <div><strong>Worst Days:</strong> {int(row['worst_days'])} days</div>
                <div><strong>Total Outstanding:</strong> R {row['total_outstanding']:,.2f}</div>
                <div><strong>Credit Limit:</strong> R {row['credit_limit']:,.0f}</div>
            </div>
            <div style="display:flex;gap:40px;margin-top:6px;font-size:0.85em;color:#666;">
                <div>📝 Last Note: {last_note_str}</div>
                <div>📨 Last Communication: {last_comm_str}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 6 — NOTES & CONVERSATIONS
# ═══════════════════════════════════════════════════════════════════════════════
def render_notes():
    st.markdown("## 📝 Notes & Conversations")
    conn = get_db()

    clients = pd.read_sql("SELECT id, company_name FROM clients ORDER BY company_name", conn)
    if len(clients) == 0:
        st.warning("No clients found.")
        conn.close()
        return

    client_map = dict(zip(clients["company_name"], clients["id"]))
    selected = st.selectbox("🏢 Select Client", list(client_map.keys()), key="notes_client")
    cid = client_map[selected]

    # ── Add Note ─────────────────────────────────────────────────────────
    st.markdown("### ➕ Add New Note")
    nc1, nc2 = st.columns([3, 1])
    with nc1:
        note_type = st.selectbox("📌 Note Type", NOTE_TYPES, key="nt_type")
        note_text = st.text_area("💬 Note / Conversation Details", height=120,
                                 placeholder="Enter your note or conversation summary...", key="nt_text")
    with nc2:
        logged_by = st.text_input("👤 Logged By", value=DEFAULT_USER, key="nt_by")
        # Summary
        notes_count = conn.execute("SELECT COUNT(*) FROM collection_notes WHERE client_id=?", (cid,)).fetchone()[0]
        st.metric("Total Notes", notes_count)

    if st.button("💾 Save Note", type="primary", key="save_note"):
        if not note_text.strip():
            st.warning("⚠️ Please enter a note.")
        else:
            conn2 = sqlite3.connect(DB_PATH)
            conn2.execute(
                "INSERT INTO collection_notes (client_id,note_type,note_text,created_by,created_at) VALUES (?,?,?,?,?)",
                (cid, note_type, note_text, logged_by, get_sast_now()))
            conn2.commit()
            conn2.close()
            log_audit("NOTE", "Notes", f"{note_type} logged for {selected}")
            st.success(f"✅ Note saved for {selected}")
            st.rerun()

    st.divider()

    # ── Previous Notes ───────────────────────────────────────────────────
    st.markdown("### 📜 Previous Notes")
    type_filter = st.selectbox("🔍 Filter by Type", ["All"] + NOTE_TYPES, key="nt_filter")

    if type_filter == "All":
        notes = pd.read_sql(
            "SELECT * FROM collection_notes WHERE client_id=? ORDER BY created_at DESC", conn, params=(cid,))
    else:
        notes = pd.read_sql(
            "SELECT * FROM collection_notes WHERE client_id=? AND note_type=? ORDER BY created_at DESC",
            conn, params=(cid, type_filter))

    if len(notes) == 0:
        st.info("No notes found for this client.")
    else:
        st.caption(f"Showing {len(notes)} note(s)")
        for _, n in notes.iterrows():
            colour = NOTE_TYPE_COLOURS.get(n["note_type"], "#6c757d")
            st.markdown(f"""
            <div style="border-left:4px solid {colour};padding:10px 16px;margin-bottom:8px;
                        background:#f9f9f9;border-radius:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span>
                        <span style="background:{colour};color:white;padding:2px 10px;
                              border-radius:10px;font-size:0.8em;font-weight:600;">
                            {n['note_type']}</span>
                        &nbsp; <strong>{n['created_by']}</strong>
                    </span>
                    <span style="color:#888;font-size:0.85em;">🕐 {n['created_at']} SAST · #{n['id']}</span>
                </div>
                <div style="font-size:0.93em;color:#333;">{n['note_text']}</div>
            </div>
            """, unsafe_allow_html=True)
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 7 — COMMUNICATION CENTER
# ═══════════════════════════════════════════════════════════════════════════════
def render_communications():
    st.markdown("## 📨 Communication Center")
    conn = get_db()

    clients = pd.read_sql("SELECT id, company_name, email, phone FROM clients ORDER BY company_name", conn)
    if len(clients) == 0:
        st.warning("No clients found.")
        conn.close()
        return

    client_map = dict(zip(clients["company_name"], clients["id"]))
    selected = st.selectbox("🏢 Select Client", list(client_map.keys()), key="comm_client")
    cid = client_map[selected]
    cl_row = clients[clients["company_name"] == selected].iloc[0]

    # NCA compliance
    nca = check_nca_compliance()
    if nca["compliant"]:
        st.success(f"✅ **NCA Compliant** — {nca['current_time']} SAST ({nca['current_day']})")
    else:
        st.error(f"🚫 **Outside Contact Hours** — {nca['reason']} Next: **{nca['next_window']}**")

    st.divider()

    # ── Send Reminder ────────────────────────────────────────────────────
    st.markdown("### 📨 Send Reminder")
    sc1, sc2 = st.columns([2, 1])

    with sc2:
        st.markdown("#### 📇 Recipient")
        phone = st.text_input("📱 Phone", value=str(cl_row["phone"] or ""), key="comm_phone")
        email = st.text_input("📧 Email", value=str(cl_row["email"] or ""), key="comm_email")
        sent_by = st.text_input("👤 Sent By", value=DEFAULT_USER, key="comm_by")

    with sc1:
        channel = st.radio("📡 **How would you like to send this?**",
                           ["SMS", "Email", "WhatsApp", "All 3 (SMS + Email + WhatsApp)"],
                           horizontal=True, key="comm_ch")
        reminder_type = st.selectbox("📋 Reminder Type", REMINDER_TYPES, key="comm_rt")
        template = get_message_template(reminder_type, selected)
        subject = st.text_input("Subject", value=template["subject"], key="comm_subj")
        body = st.text_area("💬 Message (edit before sending)", value=template["body"], height=180, key="comm_body")

    bc1, bc2 = st.columns(2)
    with bc1:
         send_now = st.button("🚀 Send Now", type="primary", use_container_width=True, key="comm_send",                              disabled=not nca["compliant"])
    with bc2:
        schedule = st.button("📅 Schedule for Next Window", use_container_width=True,
                             key="comm_sched", disabled=nca["compliant"])

    if send_now or schedule:
        if not body.strip():
            st.warning("⚠️ Message cannot be empty.")
        else:
            channels = ["SMS", "Email", "WhatsApp"] if "All 3" in channel else [channel]
            status = "Scheduled" if schedule else "Sent"
            conn2 = sqlite3.connect(DB_PATH)
            ids = []
            for ch in channels:
                contact = email if ch == "Email" else phone
                cur = conn2.execute(
                    "INSERT INTO communication_log (client_id,channel,message_subject,message_body,"
                    "recipient_contact,sent_by,sent_at,status,nca_compliant,reminder_type,"
                    "linked_invoice_id,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, ch, subject, body, contact, sent_by, get_sast_now(), status,
                     1 if nca["compliant"] else 0, reminder_type, "", ""))
                ids.append(cur.lastrowid)
            conn2.commit()
            conn2.close()
            log_audit("COMMUNICATION", "Comms Center",
                      f"{status}: {', '.join(channels)} to {selected} ({reminder_type})")
            ch_str = ", ".join([f"{CHANNEL_ICONS.get(c,'')} {c}" for c in channels])
            st.success(f"✅ {status}! Channels: {ch_str} | IDs: {', '.join(map(str, ids))}")
            st.rerun()

    st.divider()

    # ── Audit Trail ──────────────────────────────────────────────────────
    st.markdown("### 📜 Communication History")
    ch_filter = st.selectbox("🔍 Filter Channel", ["All", "SMS", "Email", "WhatsApp"], key="comm_hist_f")

    if ch_filter == "All":
        history = pd.read_sql(
            "SELECT * FROM communication_log WHERE client_id=? ORDER BY sent_at DESC", conn, params=(cid,))
    else:
        history = pd.read_sql(
            "SELECT * FROM communication_log WHERE client_id=? AND channel=? ORDER BY sent_at DESC",
            conn, params=(cid, ch_filter))

    if len(history) == 0:
        st.info("No communications found.")
    else:
        # Summary
        mc = st.columns(4)
        mc[0].metric("📊 Total", len(history))
        for i, ch_name in enumerate(["SMS", "Email", "WhatsApp"]):
            count = len(history[history["channel"] == ch_name])
            mc[i + 1].metric(f"{CHANNEL_ICONS.get(ch_name, '')} {ch_name}", count)

        for _, r in history.iterrows():
            ch_col = CHANNEL_COLOURS.get(r["channel"], "#6c757d")
            st_col = STATUS_COLOURS.get(r["status"], "#6c757d")
            nca_badge = ("NCA ✓" if r["nca_compliant"] else "NCA ✗")
            nca_bg = ("#198754" if r["nca_compliant"] else "#dc3545")
            preview = str(r["message_body"])[:120] + ("..." if len(str(r["message_body"])) > 120 else "")

            st.markdown(f"""
            <div style="border-left:4px solid {ch_col};padding:10px 16px;margin-bottom:8px;
                        background:#f9f9f9;border-radius:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span>
                        <span style="background:{ch_col};color:white;padding:2px 10px;border-radius:10px;
                              font-size:0.8em;font-weight:600;">{CHANNEL_ICONS.get(r['channel'],'')} {r['channel']}</span>
                        <span style="background:#444;color:white;padding:2px 8px;border-radius:10px;
                              font-size:0.75em;">{r['reminder_type']}</span>
                        <span style="background:{st_col};color:white;padding:2px 8px;border-radius:10px;
                              font-size:0.75em;">{r['status']}</span>
                        <span style="background:{nca_bg};color:white;padding:1px 6px;border-radius:8px;
                              font-size:0.7em;">{nca_badge}</span>
                    </span>
                    <span style="color:#888;font-size:0.85em;">🕐 {r['sent_at']} · #{r['id']}</span>
                </div>
                <div style="font-size:0.85em;color:#666;">
                    <strong>To:</strong> {r['recipient_contact']} · <strong>By:</strong> {r['sent_by']}
                </div>
                <div style="font-size:0.9em;color:#333;margin-top:4px;">{preview}</div>
            </div>
            """, unsafe_allow_html=True)
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 8 — DISPUTES & PROMISES TO PAY
# ═══════════════════════════════════════════════════════════════════════════════
def render_disputes_promises():
    st.markdown("## ⚠️ Disputes & Promises to Pay")
    mode = st.radio("", ["⚠️ Disputes", "🤝 Promises to Pay"], horizontal=True, key="dp_mode")
    conn = get_db()
    today = date.today()

    if mode == "⚠️ Disputes":
        st.markdown("### ⚠️ Dispute Management")

        # List disputes
        disputes = pd.read_sql(
            "SELECT d.*, c.company_name, i.invoice_number FROM disputes d "
            "JOIN clients c ON d.client_id=c.id "
            "LEFT JOIN invoices i ON d.invoice_id=i.id "
            "ORDER BY d.raised_at DESC", conn)

        if len(disputes) > 0:
            st.markdown(f"**{len(disputes)} dispute(s)** on record")
            for _, d in disputes.iterrows():
                s_col = {"Open": "#ffc107", "Under Review": "#0d6efd",
                         "Resolved": "#198754", "Rejected": "#dc3545"}.get(d["status"], "#6c757d")
                st.markdown(f"""
                <div style="border-left:4px solid {s_col};padding:10px 16px;margin-bottom:8px;
                            background:#f9f9f9;border-radius:6px;">
                    <div style="display:flex;justify-content:space-between;">
                        <span><strong>{d['company_name']}</strong> — {d['invoice_number'] or 'N/A'}
                            <span style="background:{s_col};color:white;padding:2px 10px;
                                  border-radius:10px;font-size:0.8em;margin-left:10px;">{d['status']}</span>
                        </span>
                        <span style="color:#888;font-size:0.85em;">#{d['id']} · {d['raised_at']}</span>
                    </div>
                    <div style="margin-top:6px;font-size:0.9em;"><strong>Type:</strong> {d['dispute_type']}
                        · <strong>Raised by:</strong> {d['raised_by']}</div>
                    <div style="font-size:0.9em;color:#333;margin-top:4px;">{d['description']}</div>
                </div>""", unsafe_allow_html=True)
        else:
            st.success("✅ No disputes on record.")

        # Add dispute
        st.divider()
        st.markdown("### ➕ Raise New Dispute")
        clients = pd.read_sql("SELECT id, company_name FROM clients ORDER BY company_name", conn)
        with st.form("add_dispute"):
            d1, d2 = st.columns(2)
            with d1:
                d_client = st.selectbox("Client", clients["company_name"].tolist(), key="disp_cl")
                d_cid = int(clients[clients["company_name"] == d_client]["id"].values[0])
                invoices = pd.read_sql("SELECT id, invoice_number FROM invoices WHERE client_id=?",
                                        conn, params=(d_cid,))
                d_inv = st.selectbox("Invoice", invoices["invoice_number"].tolist() if len(invoices) > 0 else ["N/A"],
                                      key="disp_inv")
            with d2:
                d_type = st.selectbox("Dispute Type", ["Pricing", "Quality", "Delivery", "Duplicate", "Other"],
                                       key="disp_type")
                d_raised = st.text_input("Raised By", key="disp_rby")
            d_desc = st.text_area("Description", key="disp_desc")

            if st.form_submit_button("💾 Raise Dispute", type="primary"):
                inv_id = int(invoices[invoices["invoice_number"] == d_inv]["id"].values[0]) if d_inv != "N/A" else None
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute(
                    "INSERT INTO disputes (client_id,invoice_id,dispute_type,description,status,"
                    "raised_by,raised_at) VALUES (?,?,?,?,?,?,?)",
                    (d_cid, inv_id, d_type, d_desc, "Open", d_raised, get_sast_now()))
                if inv_id:
                    conn2.execute("UPDATE invoices SET status='Disputed' WHERE id=?", (inv_id,))
                conn2.commit()
                conn2.close()
                log_audit("DISPUTE", "Disputes", f"Dispute raised for {d_client} — {d_type}")
                st.success("✅ Dispute raised successfully.")
                st.rerun()

        # Resolve/Reject
        st.divider()
        st.markdown("### 🔄 Update Dispute Status")
        open_disputes = disputes[disputes["status"].isin(["Open", "Under Review"])] if len(disputes) > 0 else pd.DataFrame()
        if len(open_disputes) > 0:
            open_disputes = open_disputes.copy()
            open_disputes["label"] = open_disputes.apply(
                lambda r: f"#{r['id']} — {r['company_name']} — {r['dispute_type']}", axis=1)
            with st.form("update_dispute"):
                sel_disp = st.selectbox("Select Dispute", open_disputes["label"].tolist(), key="upd_disp")
                new_status = st.selectbox("New Status", ["Under Review", "Resolved", "Rejected"], key="upd_status")
                resolution = st.text_area("Resolution Notes", key="upd_res")
                if st.form_submit_button("💾 Update", type="primary"):
                    disp_id = int(sel_disp.split(" — ")[0].replace("#", ""))
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute("UPDATE disputes SET status=?, resolution=?, resolved_at=? WHERE id=?",
                                   (new_status, resolution, get_sast_now() if new_status in ["Resolved", "Rejected"] else None, disp_id))
                    conn2.commit()
                    conn2.close()
                    log_audit("UPDATE", "Disputes", f"Dispute #{disp_id} → {new_status}")
                    st.success(f"✅ Dispute #{disp_id} updated to {new_status}")
                    st.rerun()
        else:
            st.info("No open disputes to update.")

    else:  # Promises to Pay
        st.markdown("### 🤝 Promises to Pay")

        promises = pd.read_sql(
            "SELECT p.*, c.company_name, i.invoice_number FROM promises_to_pay p "
            "JOIN clients c ON p.client_id=c.id "
            "LEFT JOIN invoices i ON p.invoice_id=i.id "
            "ORDER BY p.promised_date", conn)

        # Auto-flag broken
        if len(promises) > 0:
            for _, p in promises.iterrows():
                if p["status"] == "Pending" and p["promised_date"]:
                    pdate = datetime.strptime(p["promised_date"], "%Y-%m-%d").date()
                    if pdate < today:
                        conn2 = sqlite3.connect(DB_PATH)
                        conn2.execute("UPDATE promises_to_pay SET status='Broken' WHERE id=?", (p["id"],))
                        conn2.commit()
                        conn2.close()
                        log_audit("ALERT", "Promises", f"Promise #{p['id']} auto-flagged as BROKEN — {p['company_name']}")

            # Refresh
            promises = pd.read_sql(
                "SELECT p.*, c.company_name, i.invoice_number FROM promises_to_pay p "
                "JOIN clients c ON p.client_id=c.id "
                "LEFT JOIN invoices i ON p.invoice_id=i.id "
                "ORDER BY p.promised_date", conn)

            for _, p in promises.iterrows():
                s_col = {"Pending": "#ffc107", "Kept": "#198754", "Broken": "#dc3545"}.get(p["status"], "#6c757d")
                st.markdown(f"""
                <div style="border-left:4px solid {s_col};padding:10px 16px;margin-bottom:8px;
                            background:#f9f9f9;border-radius:6px;">
                    <div style="display:flex;justify-content:space-between;">
                        <span><strong>{p['company_name']}</strong> — {p['invoice_number'] or 'General'}
                            <span style="background:{s_col};color:white;padding:2px 10px;
                                  border-radius:10px;font-size:0.8em;margin-left:10px;">{p['status']}</span>
                        </span>
                        <span style="color:#888;font-size:0.85em;">#{p['id']}</span>
                    </div>
                    <div style="margin-top:6px;font-size:0.9em;">
                        <strong>Amount:</strong> R {p['promised_amount']:,.2f} ·
                        <strong>Date:</strong> {p['promised_date']} ·
                        <strong>By:</strong> {p['created_by']}
                    </div>
                    <div style="font-size:0.9em;color:#333;margin-top:4px;">{p['notes'] or ''}</div>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("No promises to pay on record.")

        # Add promise
        st.divider()
        st.markdown("### ➕ Record Promise to Pay")
        clients = pd.read_sql("SELECT id, company_name FROM clients ORDER BY company_name", conn)
        with st.form("add_promise"):
            p1, p2 = st.columns(2)
            with p1:
                p_client = st.selectbox("Client", clients["company_name"].tolist(), key="prom_cl")
                p_cid = int(clients[clients["company_name"] == p_client]["id"].values[0])
                invoices = pd.read_sql("SELECT id, invoice_number FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid','Disputed')",
                                        conn, params=(p_cid,))
                p_inv = st.selectbox("Invoice", invoices["invoice_number"].tolist() if len(invoices) > 0 else ["General"],
                                      key="prom_inv")
            with p2:
                p_amount = st.number_input("Promised Amount (R)", min_value=0.01, value=10000.0, step=500.0, key="prom_amt")
                p_date = st.date_input("Promised Date", value=today + timedelta(days=7), key="prom_date")
            p_notes = st.text_input("Notes", key="prom_notes")

            if st.form_submit_button("💾 Record Promise", type="primary"):
                inv_id = int(invoices[invoices["invoice_number"] == p_inv]["id"].values[0]) if p_inv != "General" else None
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute(
                    "INSERT INTO promises_to_pay (client_id,invoice_id,promised_amount,promised_date,"
                    "status,notes,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (p_cid, inv_id, p_amount, str(p_date), "Pending", p_notes, DEFAULT_USER, get_sast_now()))
                conn2.commit()
                conn2.close()
                log_audit("PROMISE", "Promises", f"Promise recorded: {p_client} — R {p_amount:,.2f} by {p_date}")
                st.success("✅ Promise to pay recorded.")
                st.rerun()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 9 — REPORTING
# ═══════════════════════════════════════════════════════════════════════════════
def render_reporting():
    st.markdown("## 📊 Reporting")
    conn = get_db()
    today = date.today()

    report = st.selectbox("Select Report", [
        "📊 Aging Report", "📈 Collection Effectiveness", "🛡️ Risk Distribution",
    ], key="report_sel")

    if report == "📊 Aging Report":
        st.markdown("### 📊 Aging Report")
        inv = pd.read_sql(
            "SELECT i.*, c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id "
            "WHERE i.status IN ('Open','Partially Paid','Disputed') ORDER BY c.company_name, i.due_date", conn)
        if len(inv) == 0:
            st.info("No open invoices.")
            conn.close()
            return
        inv["outstanding"] = inv["total_amount"] - inv["amount_paid"]
        inv["due_dt"] = pd.to_datetime(inv["due_date"]).dt.date
        inv["days_overdue"] = inv["due_dt"].apply(lambda d: max(0, (today - d).days))

        def bucket(days):
            if days == 0: return "Current"
            elif days <= 30: return "1-30"
            elif days <= 60: return "31-60"
            elif days <= 90: return "61-90"
            elif days <= 120: return "91-120"
            else: return "120+"
        inv["bucket"] = inv["days_overdue"].apply(bucket)

        display = inv[["invoice_number", "company_name", "due_date", "outstanding", "days_overdue", "bucket", "status"]].copy()
        display.columns = ["Invoice #", "Client", "Due Date", "Outstanding", "Days Overdue", "Bucket", "Status"]
        display["Outstanding"] = display["Outstanding"].apply(lambda x: f"R {x:,.2f}")
        st.dataframe(display, use_container_width=True, hide_index=True)

        # Bucket totals
        st.markdown("#### Bucket Summary")
        bucket_order = ["Current", "1-30", "31-60", "61-90", "91-120", "120+"]
        summary = inv.groupby("bucket")["outstanding"].sum().reindex(bucket_order, fill_value=0)
        summary_df = summary.reset_index()
        summary_df.columns = ["Bucket", "Total"]
        summary_df["Total"] = summary_df["Total"].apply(lambda x: f"R {x:,.2f}")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    elif report == "📈 Collection Effectiveness":
        st.markdown("### 📈 Collection Effectiveness Index (CEI)")
        inv = pd.read_sql("SELECT * FROM invoices", conn)
        total_invoiced = inv["total_amount"].sum()
        total_collected = inv["amount_paid"].sum()
        open_outstanding = inv[inv["status"].isin(["Open", "Partially Paid", "Disputed"])]["total_amount"].sum() -                           inv[inv["status"].isin(["Open", "Partially Paid", "Disputed"])]["amount_paid"].sum()
        cei = (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Invoiced", f"R {total_invoiced:,.2f}")
        c2.metric("Total Collected", f"R {total_collected:,.2f}")
        c3.metric("CEI Score", f"{cei:.1f}%")

        # Gauge chart
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=cei,
            title={"text": "Collection Effectiveness Index"},
            delta={"reference": 80},
            gauge={"axis": {"range": [0, 100]},
                   "bar": {"color": "#0d6efd"},
                   "steps": [
                       {"range": [0, 40], "color": "#dc3545"},
                       {"range": [40, 70], "color": "#ffc107"},
                       {"range": [70, 100], "color": "#198754"}],
                   "threshold": {"line": {"color": "black", "width": 4}, "thickness": 0.75, "value": 80}}))
        fig.update_layout(height=300, margin=dict(t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

    else:  # Risk Distribution
        st.markdown("### 🛡️ Risk Distribution Report")
        portfolio = pd.read_sql(
            "SELECT c.company_name, c.credit_limit, cs.composite_score, cs.risk_grade, cs.ead, cs.ecl "
            "FROM credit_scores cs JOIN clients c ON cs.client_id = c.id "
            "INNER JOIN (SELECT client_id, MAX(id) as max_id FROM credit_scores GROUP BY client_id) latest "
            "ON cs.id = latest.max_id ORDER BY cs.risk_grade", conn)

        if len(portfolio) > 0:
            grade_summary = portfolio.groupby("risk_grade").agg(
                Clients=("company_name", "count"),
                Total_EAD=("ead", "sum"),
                Total_ECL=("ecl", "sum"),
                Avg_Score=("composite_score", "mean")
            ).reset_index()
            grade_summary.columns = ["Grade", "Clients", "Total EAD", "Total ECL", "Avg Score"]
            grade_summary["Total EAD"] = grade_summary["Total EAD"].apply(lambda x: f"R {x:,.2f}")
            grade_summary["Total ECL"] = grade_summary["Total ECL"].apply(lambda x: f"R {x:,.2f}")
            grade_summary["Avg Score"] = grade_summary["Avg Score"].apply(lambda x: f"{x:.1f}")
            st.dataframe(grade_summary, use_container_width=True, hide_index=True)

            # Detail
            detail = portfolio.copy()
            detail.columns = ["Client", "Credit Limit", "Score", "Grade", "EAD", "ECL"]
            detail["Credit Limit"] = detail["Credit Limit"].apply(lambda x: f"R {x:,.0f}")
            detail["EAD"] = detail["EAD"].apply(lambda x: f"R {x:,.2f}")
            detail["ECL"] = detail["ECL"].apply(lambda x: f"R {x:,.2f}")
            st.dataframe(detail, use_container_width=True, hide_index=True)
        else:
            st.info("No credit scores available.")
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 10 — AUDIT TRAIL
# ═══════════════════════════════════════════════════════════════════════════════
def render_audit_trail():
    st.markdown("## 📋 Audit Trail")
    st.markdown("_Immutable record of every action across the platform._")
    conn = get_db()

    audit = pd.read_sql("SELECT * FROM audit_trail ORDER BY created_at DESC", conn)

    if len(audit) == 0:
        st.info("No audit records.")
        conn.close()
        return

    # Filters
    f1, f2 = st.columns(2)
    with f1:
        modules = ["All"] + sorted(audit["module"].dropna().unique().tolist())
        mod_filter = st.selectbox("Filter by Module", modules, key="audit_mod")
    with f2:
        actions = ["All"] + sorted(audit["action_type"].dropna().unique().tolist())
        act_filter = st.selectbox("Filter by Action", actions, key="audit_act")

    filtered = audit.copy()
    if mod_filter != "All":
        filtered = filtered[filtered["module"] == mod_filter]
    if act_filter != "All":
        filtered = filtered[filtered["action_type"] == act_filter]

    st.markdown(f"**{len(filtered)} records** (of {len(audit)} total)")
    st.divider()

    action_colours = {
        "CREATE": "#198754", "UPDATE": "#0d6efd", "DELETE": "#dc3545",
        "PAYMENT": "#20c997", "NOTE": "#6f42c1", "SCORE": "#fd7e14",
        "COMMUNICATION": "#0dcaf0", "DISPUTE": "#ffc107", "PROMISE": "#e35d6a",
        "ALERT": "#dc3545", "SYSTEM": "#6c757d",
    }

    for _, row in filtered.iterrows():
        a_col = action_colours.get(row["action_type"], "#6c757d")
        st.markdown(f"""
        <div style="padding:8px 14px;margin-bottom:4px;background:#f8f9fa;
                    border-left:3px solid {a_col};border-radius:4px;font-size:0.9em;">
            <span style="background:{a_col};color:white;padding:1px 8px;border-radius:8px;
                  font-size:0.8em;font-weight:600;">{row['action_type']}</span>
            &nbsp; <strong>{row['module']}</strong> · {row['description']}
            <span style="float:right;color:#888;font-size:0.85em;">{row['user']} · {row['created_at']}</span>
        </div>""", unsafe_allow_html=True)
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    # Initialize
    init_db()
    seed_data()
    if ENHANCEMENTS_AVAILABLE:
        init_enhancements_db()
    if V6_AVAILABLE:
        init_auth_db()
        init_workflows_db()
        init_legal_db()
        init_popia_predictive_db()

    # ── Sidebar ──────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            "<div style='text-align:center;padding:10px 0;'>"
            "<h1 style='margin:0;font-size:1.8em;'>📊 KA CreditFlow</h1>"
            "<p style='margin:0;font-size:0.9em;color:#888;'>v5.5 — Enterprise Edition</p>"
            "<p style='margin:2px 0 0 0;font-size:0.75em;color:#aaa;'>by KA Legacy</p>"
            "</div>", unsafe_allow_html=True)
              

        st.markdown(f"👤 **{DEFAULT_USER}**")
        st.caption(f"🕐 {get_sast_now()} SAST")

        st.divider()

        # Core modules
        st.markdown("**CORE MODULES**")
        nav_options = [
            "📊 Dashboard",
            "🏢 Clients",
            "🧾 Invoices",
            "🛡️ Credit Engine",
            "📋 Worklist",
            "📝 Notes",
            "📨 Communications",
            "⚠️ Disputes & Promises",
            "📊 Reporting",
            "📋 Audit Trail",
        ]

     # Enhancement modules
      if ENHANCEMENTS_AVAILABLE:
        nav_options.append("─────────────")
        nav_options.extend([
          "⚙️ Dunning Engine",
          "💰 Cash Flow Forecast",
          "📈 Payment Analytics",
          "📁 Data Import/Export",
          "📝 Write-Offs",
          "💹 Interest Calculator",
          "📋 Credit Applications",
          "🎯 KPI Targets",
        ])

      if V6_AVAILABLE:
        nav_options.extend([
          "🔄 Automated Workflows",
          "⚖️ Legal Compliance",
          "📄 Document Center",
          "🔒 POPIA Compliance",
          "🔮 Predictive Engine",
          "👥 User Management",
        ])

        nav = st.radio("Navigation", nav_options, key="main_nav")

        st.divider()

        # NCA Status
        nca = check_nca_compliance()
        if nca["compliant"]:
            st.success(f"✅ NCA: OK ({nca['current_time']})")
        else:
            st.error(f"🚫 NCA: Restricted")

        st.divider()
        st.markdown(
            '<div style="text-align:center;font-size:0.75em;color:#aaa;">'
            'KA CreditFlow v5.5<br>'
            '&copy; 2026 KA Legacy<br>'
            'Founded on biblical principles<br>'
            'Stewarding resources toward<br>a land of milk and honey</div>',
            unsafe_allow_html=True)

    # ── Route ────────────────────────────────────────────────────────────
    if nav == "📊 Dashboard":
        render_dashboard()
    elif nav == "🏢 Clients":
        render_clients()
    elif nav == "🧾 Invoices":
        render_invoices()
    elif nav == "🛡️ Credit Engine":
        render_credit_engine()
    elif nav == "📋 Worklist":
        render_worklist()
    elif nav == "📝 Notes":
        render_notes()
    elif nav == "📨 Communications":
        render_communications()
    elif nav == "⚠️ Disputes & Promises":
        render_disputes_promises()
    elif nav == "📊 Reporting":
        render_reporting()
    elif nav == "📋 Audit Trail":
        render_audit_trail()
    # Enhancement modules
    elif nav == "⚙️ Dunning Engine" and ENHANCEMENTS_AVAILABLE:
        render_dunning_engine()
    elif nav == "💰 Cash Flow Forecast" and ENHANCEMENTS_AVAILABLE:
        render_cashflow_forecast()
    elif nav == "📈 Payment Analytics" and ENHANCEMENTS_AVAILABLE:
        render_payment_analytics()
    elif nav == "📁 Data Import/Export" and ENHANCEMENTS_AVAILABLE:
        render_data_tools()
    elif nav == "📝 Write-Offs" and ENHANCEMENTS_AVAILABLE:
        render_write_offs()
    elif nav == "💹 Interest Calculator" and ENHANCEMENTS_AVAILABLE:
        render_interest_calculator()
    elif nav == "📋 Credit Applications" and ENHANCEMENTS_AVAILABLE:
        render_credit_applications()
    elif nav == "🎯 KPI Targets" and ENHANCEMENTS_AVAILABLE:
        render_kpi_targets()
              elif nav == "🔄 Automated Workflows" and V6_AVAILABLE:
        render_workflows()
    elif nav == "⚖️ Legal Compliance" and V6_AVAILABLE:
        render_legal_compliance()
    elif nav == "📄 Document Center" and V6_AVAILABLE:
        render_document_center()
    elif nav == "🔒 POPIA Compliance" and V6_AVAILABLE:
        render_popia_compliance()
    elif nav == "🔮 Predictive Engine" and V6_AVAILABLE:
        render_predictive_engine()
    elif nav == "👥 User Management" and V6_AVAILABLE:
        render_user_management()
    elif nav == "─────────────":
        st.info("Please select a module from the sidebar.")


if __name__ == "__main__":
    main()
