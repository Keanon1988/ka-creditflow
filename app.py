#!/usr/bin/env python3
"""
KA CREDITFLOW v4.0 — Complete Credit Management & Collections Platform
Built for KA Legacy (PTY) LTD — Keanon Apollos
"From Invoice to Cash — Faster."
"""
import streamlit as st
import sqlite3, hashlib, math, io, zipfile
from datetime import datetime, date, timedelta
from contextlib import contextmanager
from urllib.parse import quote
from collections import OrderedDict

DB_PATH = "ka_creditflow.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; conn.execute("PRAGMA foreign_keys = ON")
    try: yield conn; conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def init_database():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT DEFAULT 'user', is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now','localtime')), last_login TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, company_name TEXT NOT NULL, registration_number TEXT, contact_person TEXT NOT NULL, email TEXT, phone TEXT, physical_address TEXT, industry TEXT, years_in_business INTEGER DEFAULT 0, annual_revenue REAL DEFAULT 0.0, existing_debt REAL DEFAULT 0.0, payment_history_score INTEGER DEFAULT 50, credit_limit_requested REAL DEFAULT 0.0, credit_limit_approved REAL DEFAULT 0.0, payment_terms TEXT DEFAULT '30 days', risk_classification TEXT DEFAULT 'Pending', credit_score INTEGER DEFAULT 0, status TEXT DEFAULT 'Active', notes TEXT, created_by TEXT, created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT DEFAULT (datetime('now','localtime')), is_credit_agreement TEXT DEFAULT 'No', debtor_entity_type TEXT DEFAULT 'Company', annual_turnover_above_1m TEXT DEFAULT 'Unknown', at_arms_length TEXT DEFAULT 'Yes', has_surety TEXT DEFAULT 'No', surety_name TEXT DEFAULT '', surety_id TEXT DEFAULT '', surety_address TEXT DEFAULT '', domicilium_address TEXT DEFAULT '', letter_type_required TEXT DEFAULT 'Letter of Demand')""")
        c.execute("""CREATE TABLE IF NOT EXISTS credit_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, decision_type TEXT NOT NULL, credit_score INTEGER, auto_recommendation TEXT, final_decision TEXT NOT NULL, credit_limit_approved REAL DEFAULT 0.0, conditions TEXT, reason TEXT, decided_by TEXT NOT NULL, decided_at TEXT DEFAULT (datetime('now','localtime')), FOREIGN KEY (client_id) REFERENCES clients(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, invoice_number TEXT UNIQUE NOT NULL, invoice_date TEXT NOT NULL, due_date TEXT NOT NULL, subtotal REAL DEFAULT 0.0, vat_rate REAL DEFAULT 15.0, vat_amount REAL DEFAULT 0.0, total_amount REAL DEFAULT 0.0, amount_paid REAL DEFAULT 0.0, balance REAL DEFAULT 0.0, status TEXT DEFAULT 'Draft', escalation_tier TEXT DEFAULT 'None', notes TEXT, created_by TEXT, created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT DEFAULT (datetime('now','localtime')), FOREIGN KEY (client_id) REFERENCES clients(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS invoice_items (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, description TEXT NOT NULL, quantity REAL DEFAULT 1.0, unit_price REAL DEFAULT 0.0, line_total REAL DEFAULT 0.0, FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, payment_date TEXT NOT NULL, amount REAL NOT NULL, method TEXT DEFAULT 'EFT', reference TEXT, notes TEXT, recorded_by TEXT, recorded_at TEXT DEFAULT (datetime('now','localtime')), FOREIGN KEY (invoice_id) REFERENCES invoices(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS collection_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER, client_id INTEGER NOT NULL, action_type TEXT NOT NULL, escalation_tier TEXT, message_sent TEXT, outcome TEXT, notes TEXT, performed_by TEXT, performed_at TEXT DEFAULT (datetime('now','localtime')), FOREIGN KEY (client_id) REFERENCES clients(id), FOREIGN KEY (invoice_id) REFERENCES invoices(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS promises_to_pay (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, client_id INTEGER NOT NULL, promised_amount REAL NOT NULL, promised_date TEXT NOT NULL, status TEXT DEFAULT 'Pending', actual_amount_paid REAL DEFAULT 0.0, notes TEXT, created_by TEXT, created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT DEFAULT (datetime('now','localtime')), FOREIGN KEY (invoice_id) REFERENCES invoices(id), FOREIGN KEY (client_id) REFERENCES clients(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS contact_me_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER, client_id INTEGER NOT NULL, source TEXT DEFAULT 'WhatsApp', response_type TEXT DEFAULT 'cant_pay', urgency TEXT DEFAULT 'High', status TEXT DEFAULT 'New', notes TEXT, created_by TEXT, created_at TEXT DEFAULT (datetime('now','localtime')), resolved_by TEXT, resolved_at TEXT, FOREIGN KEY (invoice_id) REFERENCES invoices(id), FOREIGN KEY (client_id) REFERENCES clients(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS client_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, invoice_id INTEGER, doc_category TEXT NOT NULL, doc_name TEXT NOT NULL, original_filename TEXT NOT NULL, file_data BLOB NOT NULL, file_size INTEGER, file_type TEXT, uploaded_by TEXT, uploaded_at TEXT DEFAULT (datetime('now','localtime')), notes TEXT, FOREIGN KEY (client_id) REFERENCES clients(id), FOREIGN KEY (invoice_id) REFERENCES invoices(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS scheduled_reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, invoice_id INTEGER, channel TEXT NOT NULL DEFAULT 'WhatsApp', scheduled_date TEXT NOT NULL, scheduled_time_slot TEXT NOT NULL, status TEXT DEFAULT 'Pending', notes TEXT, created_by TEXT, created_at TEXT DEFAULT (datetime('now','localtime')), completed_at TEXT, FOREIGN KEY (client_id) REFERENCES clients(id), FOREIGN KEY (invoice_id) REFERENCES invoices(id))""")
        for col in ["escalation_tier TEXT DEFAULT 'None'","is_credit_agreement TEXT DEFAULT 'No'","debtor_entity_type TEXT DEFAULT 'Company'","annual_turnover_above_1m TEXT DEFAULT 'Unknown'","at_arms_length TEXT DEFAULT 'Yes'","has_surety TEXT DEFAULT 'No'","surety_name TEXT DEFAULT ''","surety_id TEXT DEFAULT ''","surety_address TEXT DEFAULT ''","domicilium_address TEXT DEFAULT ''","letter_type_required TEXT DEFAULT 'Letter of Demand'"]:
            try: c.execute(f"ALTER TABLE clients ADD COLUMN {col}")
            except sqlite3.OperationalError: pass
        try: c.execute("ALTER TABLE invoices ADD COLUMN escalation_tier TEXT DEFAULT 'None'")
        except sqlite3.OperationalError: pass
        c.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
        if c.fetchone()[0]==0: c.execute("INSERT INTO users (username,password_hash,full_name,role) VALUES (?,?,?,?)",("admin",hash_password("admin123"),"Keanon Apollos","admin"))

def hash_password(pw):
    return hashlib.sha256(f"KA_CreditFlow_2024_Salt{pw}".encode()).hexdigest()

def authenticate_user(username,password):
    with get_db() as conn:
        c=conn.cursor(); c.execute("SELECT * FROM users WHERE username=? AND password_hash=? AND is_active=1",(username,hash_password(password)))
        user=c.fetchone()
        if user: c.execute("UPDATE users SET last_login=datetime('now','localtime') WHERE id=?",(user["id"],))
        return user

def login_page():
    st.set_page_config(page_title="KA CreditFlow",page_icon="\U0001f510",layout="centered")
    st.markdown('<div style="text-align:center;padding:2rem"><h1 style="color:#1B4F72">\U0001f3e6 KA CreditFlow</h1><p><em>From Invoice to Cash — Faster.</em></p></div>',unsafe_allow_html=True)
    st.markdown("---")
    _,col,_=st.columns([1,2,1])
    with col:
        st.subheader("\U0001f510 Sign In"); u=st.text_input("Username"); p=st.text_input("Password",type="password")
        if st.button("Sign In",type="primary"):
            if not u or not p: st.error("Please enter both fields.")
            else:
                user=authenticate_user(u,p)
                if user: st.session_state.update({"authenticated":True,"user_id":user["id"],"username":user["username"],"full_name":user["full_name"],"role":user["role"]}); st.rerun()
                else: st.error("Invalid credentials.")
        st.caption("Default: **admin** / **admin123**")

def calculate_credit_score(yib,rev,debt,phs,ind):
    s1=15 if yib>=10 else 12 if yib>=5 else 9 if yib>=3 else 5 if yib>=1 else 2
    s2=25 if rev>=10e6 else 20 if rev>=5e6 else 15 if rev>=1e6 else 10 if rev>=5e5 else 6 if rev>=1e5 else 3
    dtr=debt/rev if rev>0 else 1.0
    s3=20 if dtr<=.1 else 16 if dtr<=.3 else 12 if dtr<=.5 else 8 if dtr<=.7 else 4 if dtr<=.9 else 1
    s4=round((phs/100)*30)
    lr=["Financial Services","Healthcare","Government","Utilities","Insurance","Telecommunications"]
    mr=["Manufacturing","Retail","Technology","Education","Professional Services","Property Management"]
    s5=10 if ind in lr else 7 if ind in mr else 4
    total=min(100,max(0,s1+s2+s3+s4+s5))
    rec="APPROVE" if total>=70 else "CONDITIONAL" if total>=40 else "DECLINE"
    bd={"Years in Business":{"score":s1,"max":15},"Annual Revenue":{"score":s2,"max":25},"Debt-to-Revenue":{"score":s3,"max":20},"Payment History":{"score":s4,"max":30},"Industry Risk":{"score":s5,"max":10}}
    return total,rec,bd

def get_risk_classification(s): return "Low" if s>=70 else "Medium" if s>=40 else "High"
def risk_badge(r): return {"Low":"\U0001f7e2 Low Risk","Medium":"\U0001f7e1 Medium Risk","High":"\U0001f534 High Risk","Pending":"\u26aa Pending"}.get(r,"\u26aa Unknown")
def decision_badge(d): return {"APPROVE":"\u2705 APPROVED","CONDITIONAL":"\U0001f7e1 CONDITIONAL","DECLINE":"\u274c DECLINED"}.get(d,d)

VAT_RATE=15.0
PAYMENT_METHODS=["EFT","Cash","Card","Cheque","Other"]
INVOICE_STATUSES=["Draft","Sent","Partially Paid","Paid","Overdue","Written Off"]

def get_next_invoice_number():
    with get_db() as conn:
        r=conn.cursor().execute("SELECT invoice_number FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
        return f"INV-{int(r['invoice_number'].replace('INV-',''))+1:04d}" if r else "INV-0001"

def parse_payment_terms_days(t): return {"Cash on Delivery":0,"7 days":7,"14 days":14,"30 days":30,"45 days":45,"60 days":60,"90 days":90}.get(t,30)

def calculate_aging_bucket(d):
    days=(date.today()-datetime.strptime(d,"%Y-%m-%d").date()).days
    return "Current" if days<=0 else "1-30 days" if days<=30 else "31-60 days" if days<=60 else "61-90 days" if days<=90 else "91-120 days" if days<=120 else "120+ days"

def get_days_overdue(d): return (date.today()-datetime.strptime(d,"%Y-%m-%d").date()).days

def auto_update_overdue_invoices():
    with get_db() as conn: conn.cursor().execute("UPDATE invoices SET status='Overdue',updated_at=datetime('now','localtime') WHERE due_date<? AND status IN ('Sent','Partially Paid') AND balance>0",(date.today().strftime("%Y-%m-%d"),))

def get_ar_aging_data():
    with get_db() as conn:
        rows=conn.cursor().execute("SELECT i.*,c.company_name,c.phone,c.email,c.contact_person FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.status NOT IN ('Paid','Draft','Written Off') AND i.balance>0 ORDER BY i.due_date").fetchall()
    buckets={"Current":[],"1-30 days":[],"31-60 days":[],"61-90 days":[],"91-120 days":[],"120+ days":[]}
    for r in rows: buckets[calculate_aging_bucket(r["due_date"])].append(dict(r))
    return buckets

def calculate_dso():
    with get_db() as conn:
        c=conn.cursor()
        ar=c.execute("SELECT COALESCE(SUM(balance),0) FROM invoices WHERE status NOT IN ('Paid','Draft','Written Off')").fetchone()[0]
        inv90=c.execute("SELECT COALESCE(SUM(total_amount),0) FROM invoices WHERE invoice_date>=? AND status!='Draft'",((date.today()-timedelta(days=90)).strftime("%Y-%m-%d"),)).fetchone()[0]
    return (round((ar/inv90)*90,1) if inv90>0 else 0),ar

ESCALATION_TIERS=["None","Friendly","Firm","Final Demand","Pre-Legal","Legal"]
def get_escalation_tier(d): return "None" if d<=0 else "Friendly" if d<=30 else "Firm" if d<=60 else "Final Demand" if d<=90 else "Pre-Legal" if d<=120 else "Legal"
def escalation_badge(t): return {"None":"\u26aa No Action","Friendly":"\U0001f7e2 Friendly","Firm":"\U0001f7e1 Firm","Final Demand":"\U0001f7e0 Final Demand","Pre-Legal":"\U0001f534 Pre-Legal","Legal":"\u26ab Legal"}.get(t,"\u26aa Unknown")

def auto_update_escalation_tiers():
    with get_db() as conn:
        c=conn.cursor()
        for inv in c.execute("SELECT id,due_date FROM invoices WHERE status NOT IN ('Paid','Draft','Written Off') AND balance>0").fetchall():
            c.execute("UPDATE invoices SET escalation_tier=? WHERE id=?",(get_escalation_tier(get_days_overdue(inv["due_date"])),inv["id"]))

def auto_flag_broken_ptps():
    with get_db() as conn: conn.cursor().execute("UPDATE promises_to_pay SET status='Broken',updated_at=datetime('now','localtime') WHERE promised_date<? AND status='Pending'",(date.today().strftime("%Y-%m-%d"),))

def format_phone_international(ph):
    if not ph: return ""
    cl=ph.replace(" ","").replace("-","").replace("(","").replace(")","")
    if cl.startswith("0") and len(cl)>=10: cl="27"+cl[1:]
    return cl.lstrip("+")

def generate_whatsapp_link(ph,msg):
    cp=format_phone_international(ph)
    return f"https://wa.me/{cp}?text={quote(msg)}" if cp else None

COLLECTION_TEMPLATES={
    "Friendly":{"email_subject":"Friendly Reminder — Invoice {invoice_number}","email_body":"Dear {contact_person},\n\nFriendly reminder: Invoice {invoice_number} for R {amount_due} was due {due_date} ({days_overdue} days overdue). Kindly arrange payment.\n\nKA Legacy (PTY) LTD","sms":"Hi {contact_person}, reminder: Invoice {invoice_number} (R {amount_due}) due {due_date}. Kindly pay. — KA Legacy","whatsapp":"Hi {contact_person} \U0001f44b\n\nFriendly reminder from *KA Legacy*:\n\n\U0001f4c4 *Invoice:* {invoice_number}\n\U0001f4b0 *Amount:* R {amount_due}\n\U0001f4c5 *Due:* {due_date}\n\u23f0 *Overdue:* {days_overdue} days\n\nKindly arrange payment.\n\n*Reply:*\n1\ufe0f\u20e3 I will pay by [date]\n2\ufe0f\u20e3 I need to discuss\n3\ufe0f\u20e3 I cannot pay \u2014 contact me\n4\ufe0f\u20e3 I dispute this\n\nThank you \U0001f64f"},
    "Firm":{"email_subject":"URGENT: Overdue — Invoice {invoice_number} ({days_overdue} Days)","email_body":"Dear {contact_person},\n\nInvoice {invoice_number} (R {amount_due}) is {days_overdue} days overdue. Pay within 7 days or face credit suspension and escalation.\n\nKA Legacy (PTY) LTD","sms":"URGENT: Invoice {invoice_number} R {amount_due} — {days_overdue} days overdue. Pay in 7 days. — KA Legacy","whatsapp":"\u26a0\ufe0f *OVERDUE NOTICE*\n\nDear {contact_person},\n\n\U0001f4c4 *Invoice:* {invoice_number}\n\U0001f4b0 *Amount:* R {amount_due}\n\U0001f534 *Overdue:* {days_overdue} days\n\nPay within *7 days* or face escalation.\n\n*Reply:*\n1\ufe0f\u20e3 I will pay by [date]\n2\ufe0f\u20e3 I need to discuss\n3\ufe0f\u20e3 I cannot pay \u2014 contact me\n4\ufe0f\u20e3 I dispute this\n\nKA Legacy"},
    "Final Demand":{"email_subject":"FINAL DEMAND — Invoice {invoice_number}","email_body":"FINAL DEMAND: Invoice {invoice_number} R {amount_due} — {days_overdue} days overdue. Pay in 7 CALENDAR DAYS or face legal action, credit bureau reporting, and legal costs.\n\nKA Legacy (PTY) LTD","sms":"FINAL DEMAND: {invoice_number} R {amount_due}. Pay in 7 days or legal action. — KA Legacy","whatsapp":"\U0001f6a8 *FINAL DEMAND*\n\n\U0001f4c4 *Invoice:* {invoice_number}\n\U0001f4b0 *Amount:* R {amount_due}\n\U0001f534 *Overdue:* {days_overdue} days\n\nPay in *7 DAYS* or:\n\u274c Credit bureau\n\u274c Legal action\n\n*Reply:*\n1\ufe0f\u20e3 I will pay by [date]\n2\ufe0f\u20e3 I need to discuss\n3\ufe0f\u20e3 I cannot pay \u2014 contact me\n4\ufe0f\u20e3 I dispute this\n\nKA Legacy"},
    "Pre-Legal":{"email_subject":"PRE-LEGAL NOTICE — Invoice {invoice_number}","email_body":"PRE-LEGAL: Invoice {invoice_number} R {amount_due} — {days_overdue} days. Attorney handover in 7 days. Contact us IMMEDIATELY.\n\nKA Legacy (PTY) LTD","sms":"PRE-LEGAL: {invoice_number} R {amount_due}. Attorney handover in 7 days. — KA Legacy","whatsapp":"\U0001f6d1 *PRE-LEGAL NOTICE*\n\n\U0001f4c4 *Invoice:* {invoice_number}\n\U0001f4b0 *Amount:* R {amount_due}\n\U0001f534 *Overdue:* {days_overdue} days\n\n*ATTORNEY HANDOVER in 7 DAYS*\n\nLiable for legal costs + interest.\n\n*Reply:*\n1\ufe0f\u20e3 I will pay by [date]\n2\ufe0f\u20e3 I need to discuss\n3\ufe0f\u20e3 I cannot pay \u2014 contact me\n4\ufe0f\u20e3 I dispute this\n\nKA Legacy"},
    "Legal":{"email_subject":"LEGAL HANDOVER — Invoice {invoice_number}","email_body":"LEGAL HANDOVER: Invoice {invoice_number} R {amount_due} is with attorneys. Pay immediately.\n\nKA Legacy (PTY) LTD","sms":"LEGAL: {invoice_number} R {amount_due} with attorneys. Pay now. — KA Legacy","whatsapp":"\u26ab *LEGAL HANDOVER*\n\n\U0001f4c4 *Invoice:* {invoice_number}\n\U0001f4b0 *Amount:* R {amount_due}\n\U0001f534 *Overdue:* {days_overdue} days\n\n*Account with ATTORNEYS.*\n\nLiable for legal + court costs.\n\n*Reply:*\n1\ufe0f\u20e3 I will pay by [date]\n2\ufe0f\u20e3 I need to discuss\n3\ufe0f\u20e3 I cannot pay \u2014 contact me\n4\ufe0f\u20e3 I dispute this\n\nKA Legacy"},
}

def render_template(t,**kw):
    r=t
    for k,v in kw.items(): r=r.replace("{"+k+"}",str(v))
    return r

INDUSTRIES=["Financial Services","Healthcare","Government","Utilities","Insurance","Telecommunications","Manufacturing","Retail","Technology","Education","Professional Services","Property Management","Construction","Agriculture","Hospitality","Transport & Logistics","Mining","Entertainment & Media","Other"]
PAYMENT_TERMS=["Cash on Delivery","7 days","14 days","30 days","45 days","60 days","90 days"]
DOC_CATEGORIES=["Credit Application / Agreement","Company Registration (CIPC)","ID / Director ID Copy","Proof of Domicile / Physical Address","Tax Clearance Certificate","Bank Statements","Financial Statements","Proof of Delivery / Service","Signed Invoice","Purchase Order","Statement of Account","Section 129 Notice","Letter of Demand","Acknowledgement of Debt (AOD)","Email Correspondence","WhatsApp Communication Trail","SMS Communication Trail","Promise-to-Pay Agreement","Dispute Documentation","Settlement Agreement","Registered Mail Tracking Slip","Other"]
REQUIRED_LEGAL_DOCS=["Credit Application / Agreement","Company Registration (CIPC)","ID / Director ID Copy","Proof of Domicile / Physical Address","Statement of Account","Proof of Delivery / Service","Section 129 Notice","Letter of Demand"]
DEBTOR_ENTITY_TYPES=["Natural Person (Individual)","Company (PTY) LTD","Close Corporation (CC)","Trust","Partnership","Sole Proprietor","Other"]
CAPACITY_OPTIONS=["Principal Debtor / Borrower","Surety / Co-Principal Debtor","Guarantor"]
DEFAULT_INTEREST_RATE=11.5
BANK_DETAILS_TEMPLATE={"account_name":"[Your Company]","bank":"[Bank]","account_number":"[Acc No]","branch_code":"[Branch]","reference":"[Ref]"}

def determine_letter_type(is_ca,entity,above_1m,arms):
    if is_ca!="Yes": return ("Letter of Demand","Not a credit agreement.")
    if entity not in ["Natural Person (Individual)","Sole Proprietor"] and above_1m=="Yes": return ("Letter of Demand","Juristic person above R1M. NCA excluded.")
    if arms!="Yes": return ("Letter of Demand","Not at arm's length. NCA excluded.")
    return ("Section 129 Notice","NCA applies. S129 required.")



# ============================================================
# PAGES
# ============================================================

def page_dashboard():
    st.title("\U0001f4ca Dashboard"); st.markdown(f"Welcome, **{st.session_state.get('full_name','')}**!"); st.markdown("---")
    auto_update_overdue_invoices(); auto_update_escalation_tiers(); auto_flag_broken_ptps()
    with get_db() as conn:
        c=conn.cursor(); tc=c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]; ac=c.execute("SELECT COUNT(*) FROM clients WHERE status='Active'").fetchone()[0]
        te=c.execute("SELECT COALESCE(SUM(credit_limit_approved),0) FROM clients").fetchone()[0]
        rd={r["risk_classification"]:r["cnt"] for r in c.execute("SELECT risk_classification,COUNT(*) as cnt FROM clients GROUP BY risk_classification")}
        ti=c.execute("SELECT COALESCE(SUM(total_amount),0) FROM invoices WHERE status!='Draft'").fetchone()[0]
        tar=c.execute("SELECT COALESCE(SUM(balance),0) FROM invoices WHERE status NOT IN ('Paid','Draft','Written Off')").fetchone()[0]
        tod=c.execute("SELECT COALESCE(SUM(balance),0) FROM invoices WHERE status='Overdue'").fetchone()[0]
        tco=c.execute("SELECT COALESCE(SUM(amount_paid),0) FROM invoices WHERE status!='Draft'").fetchone()[0]
        acl=c.execute("SELECT COUNT(*) FROM invoices WHERE escalation_tier!='None' AND balance>0").fetchone()[0]
        pd_=c.execute("SELECT COUNT(*) FROM promises_to_pay WHERE promised_date=? AND status='Pending'",(date.today().strftime("%Y-%m-%d"),)).fetchone()[0]
        bp=c.execute("SELECT COUNT(*) FROM promises_to_pay WHERE status='Broken'").fetchone()[0]
        cq=c.execute("SELECT COUNT(*) FROM contact_me_queue WHERE status='New'").fetchone()[0]
        aw=c.execute("SELECT COUNT(*) FROM collection_actions WHERE performed_at>=?",((date.today()-timedelta(days=7)).strftime("%Y-%m-%d"),)).fetchone()[0]
    cr=(tco/ti*100) if ti>0 else 0; dso,_=calculate_dso()
    st.subheader("\U0001f465 Clients")
    c1,c2,c3,c4=st.columns(4); c1.metric("Total",tc); c2.metric("Active",ac); c3.metric("Exposure",f"R {te:,.0f}"); c4.metric("Risk",f"\U0001f7e2{rd.get('Low',0)} \U0001f7e1{rd.get('Medium',0)} \U0001f534{rd.get('High',0)}")
    st.markdown("---"); st.subheader("\U0001f9fe Accounts Receivable")
    c1,c2,c3,c4=st.columns(4); c1.metric("Invoiced",f"R {ti:,.0f}"); c2.metric("AR",f"R {tar:,.0f}"); c3.metric("Overdue",f"R {tod:,.0f}"); c4.metric("Collection",f"{cr:.1f}%")
    c1,c2,c3,c4=st.columns(4); c1.metric("DSO",f"{dso}d"); c2.metric("Collected",f"R {tco:,.0f}"); c3.metric("",""); c4.metric("","")
    st.markdown("---"); st.subheader("\U0001f4de Collections")
    c1,c2,c3,c4,c5=st.columns(5); c1.metric("Active",acl); c2.metric("PTP Today",pd_); c3.metric("Broken PTP",bp); c4.metric("\U0001f6a8 Queue",cq); c5.metric("Actions/Wk",aw)

def page_add_client():
    st.title("\u2795 Add Client"); st.markdown("---")
    with st.form("ac",clear_on_submit=True):
        c1,c2=st.columns(2)
        with c1: cn=st.text_input("Company *"); rn=st.text_input("Reg #"); ind=st.selectbox("Industry",INDUSTRIES); yib=st.number_input("Years",0,200,1)
        with c2: cp=st.text_input("Contact *"); em=st.text_input("Email"); ph=st.text_input("Phone"); pa=st.text_input("Address")
        c1,c2,c3=st.columns(3)
        with c1: ar=st.number_input("Revenue (R)",0.0,step=10000.0,format="%.2f")
        with c2: ed=st.number_input("Debt (R)",0.0,step=10000.0,format="%.2f")
        with c3: phs=st.slider("Payment History",0,100,50)
        c1,c2=st.columns(2)
        with c1: clr=st.number_input("Credit Limit (R)",0.0,step=5000.0,format="%.2f")
        with c2: pt=st.selectbox("Terms",PAYMENT_TERMS,index=3)
        st.subheader("NCA & Surety")
        c1,c2=st.columns(2)
        with c1: ica=st.selectbox("Credit agreement?",["No","Yes"]); det=st.selectbox("Entity",DEBTOR_ENTITY_TYPES)
        with c2: ata=st.selectbox("Above R1M?",["Unknown","Yes","No"]); aal=st.selectbox("Arms length?",["Yes","No"])
        c1,c2=st.columns(2)
        with c1: hs=st.selectbox("Has surety?",["No","Yes"]); sn=st.text_input("Surety Name")
        with c2: si=st.text_input("Surety ID"); sa=st.text_input("Surety Address")
        da=st.text_input("Domicilium",value=""); notes=st.text_area("Notes")
        if st.form_submit_button("\U0001f4be Save",type="primary"):
            if not cn or not cp: st.error("Required fields missing."); return
            sc,rec,_=calculate_credit_score(yib,ar,ed,phs,ind); rk=get_risk_classification(sc); lt,_=determine_letter_type(ica,det,ata,aal)
            with get_db() as conn:
                conn.cursor().execute("INSERT INTO clients (company_name,registration_number,contact_person,email,phone,physical_address,industry,years_in_business,annual_revenue,existing_debt,payment_history_score,credit_limit_requested,payment_terms,risk_classification,credit_score,notes,created_by,is_credit_agreement,debtor_entity_type,annual_turnover_above_1m,at_arms_length,has_surety,surety_name,surety_id,surety_address,domicilium_address,letter_type_required) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cn,rn,cp,em,ph,pa,ind,yib,ar,ed,phs,clr,pt,rk,sc,notes,st.session_state.get("username","system"),ica,det,ata,aal,hs,sn,si,sa,da or pa,lt))
            st.success(f"\u2705 **{cn}** — Score:{sc} | {rk} | {lt}")

def page_view_clients():
    st.title("\U0001f4c1 Clients"); st.markdown("---")
    se=st.text_input("Search"); q="SELECT * FROM clients WHERE 1=1"; p=[]
    if se: q+=" AND company_name LIKE ?"; p.append(f"%{se}%")
    with get_db() as conn: cls=conn.cursor().execute(q+" ORDER BY company_name",p).fetchall()
    for cl in cls:
        r=cl['risk_classification']; ic='\U0001f7e2' if r=='Low' else '\U0001f7e1' if r=='Medium' else '\U0001f534' if r=='High' else '\u26aa'
        with st.expander(f"{ic} {cl['company_name']} — {cl['credit_score']}/100"):
            st.markdown(f"**Contact:** {cl['contact_person']} | **Phone:** {cl['phone'] or '-'} | **Email:** {cl['email'] or '-'} | **Terms:** {cl['payment_terms']} | **Limit:** R {cl['credit_limit_approved']:,.0f}")

def page_credit_engine():
    st.title("\u26a1 Credit Engine"); st.markdown("---")
    with get_db() as conn: cls=conn.cursor().execute("SELECT id,company_name FROM clients ORDER BY company_name").fetchall()
    if not cls: st.info("No clients."); return
    opts={c['company_name']:c['id'] for c in cls}; cid=opts[st.selectbox("Client",list(opts.keys()),key="ce")]
    if st.button("Assess",type="primary"):
        with get_db() as conn: cl=dict(conn.cursor().execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone())
        sc,rec,bd=calculate_credit_score(cl["years_in_business"],cl["annual_revenue"],cl["existing_debt"],cl["payment_history_score"],cl["industry"])
        st.session_state["asr"]=(cl,sc,rec,bd,get_risk_classification(sc))
    if "asr" in st.session_state:
        cl,sc,rec,bd,rk=st.session_state["asr"]
        c1,c2,c3=st.columns(3); c1.metric("Score",f"{sc}/100"); c2.metric("Risk",rk); c3.metric("Rec",rec)
        for f,d in bd.items(): st.progress(d['score']/d['max'],text=f"{f}: {d['score']}/{d['max']}")
        with st.form("dec"):
            fd=st.selectbox("Decision",["APPROVE","CONDITIONAL","DECLINE"],index=["APPROVE","CONDITIONAL","DECLINE"].index(rec))
            al=st.number_input("Limit (R)",0.0,value=cl["credit_limit_requested"] if rec=="APPROVE" else 0.0,format="%.2f"); rsn=st.text_area("Reason *")
            if st.form_submit_button("Submit",type="primary") and rsn:
                with get_db() as conn:
                    c=conn.cursor(); c.execute("INSERT INTO credit_decisions (client_id,decision_type,credit_score,auto_recommendation,final_decision,credit_limit_approved,reason,decided_by) VALUES (?,?,?,?,?,?,?,?)",(cl["id"],"Assessment",sc,rec,fd,al,rsn,st.session_state.get("username")))
                    c.execute("UPDATE clients SET credit_score=?,risk_classification=?,credit_limit_approved=? WHERE id=?",(sc,rk,al,cl["id"]))
                st.success(f"\u2705 {decision_badge(fd)}"); del st.session_state["asr"]

def page_create_invoice():
    st.title("\U0001f9fe Create Invoice"); st.markdown("---")
    with get_db() as conn: cls=conn.cursor().execute("SELECT id,company_name,payment_terms FROM clients WHERE status='Active' ORDER BY company_name").fetchall()
    if not cls: return
    opts={c['company_name']:c for c in cls}; cl=opts[st.selectbox("Client",list(opts.keys()),key="ci")]
    inv_num=get_next_invoice_number(); st.info(f"**{inv_num}**")
    c1,c2=st.columns(2)
    with c1: inv_date=st.date_input("Date",date.today())
    with c2: due=st.date_input("Due",date.today()+timedelta(days=parse_payment_terms_days(cl["payment_terms"])))
    st.subheader("VAT Treatment")
    vat_option=st.selectbox("VAT",[" Standard (15% SA VAT)","Zero-rated (Export/International)","VAT Exempt","Not VAT Registered","Custom Rate"])
    if "Standard" in vat_option: vat_rate=15.0
    elif "Zero" in vat_option: vat_rate=0.0; st.info("No VAT — international/export client")
    elif "Exempt" in vat_option: vat_rate=0.0; st.info("VAT exempt supply")
    elif "Not VAT" in vat_option: vat_rate=0.0; st.info("Business not VAT registered")
    else: vat_rate=st.number_input("Custom VAT %",0.0,100.0,15.0,format="%.1f")
    if "li" not in st.session_state: st.session_state["li"]=[{"d":"","q":1.0,"p":0.0}]
    for i,item in enumerate(st.session_state["li"]):
        c1,c2,c3=st.columns([4,2,2])
        with c1: st.session_state["li"][i]["d"]=st.text_input("Desc",item["d"],key=f"d{i}")
        with c2: st.session_state["li"][i]["q"]=st.number_input("Qty",0.01,value=item["q"],key=f"q{i}",format="%.2f")
        with c3: st.session_state["li"][i]["p"]=st.number_input("Price",0.0,value=item["p"],key=f"p{i}",step=100.0,format="%.2f")
    if st.button("\u2795 Item"): st.session_state["li"].append({"d":"","q":1.0,"p":0.0}); st.rerun()
    sub=sum(i["q"]*i["p"] for i in st.session_state["li"]); vat=sub*(vat_rate/100); tot=sub+vat
    c1,c2,c3=st.columns(3); c1.metric("Sub",f"R {sub:,.2f}"); c2.metric(f"VAT ({vat_rate}%)",f"R {vat:,.2f}"); c3.metric("Total",f"R {tot:,.2f}")
    notes=st.text_area("Notes",placeholder="Bank details, terms...")
    if st.button("\U0001f4be Save",type="primary"):
        vi=[i for i in st.session_state["li"] if i["d"].strip() and i["p"]>0]
        if not vi: st.error("Add items."); return
        with get_db() as conn:
            c=conn.cursor(); c.execute("INSERT INTO invoices (client_id,invoice_number,invoice_date,due_date,subtotal,vat_rate,vat_amount,total_amount,amount_paid,balance,status,escalation_tier,notes,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cl["id"],inv_num,inv_date.strftime("%Y-%m-%d"),due.strftime("%Y-%m-%d"),round(sub,2),vat_rate,round(vat,2),round(tot,2),0.0,round(tot,2),"Sent","None",notes or "",st.session_state.get("username")))
            iid=c.lastrowid
            for item in vi: c.execute("INSERT INTO invoice_items (invoice_id,description,quantity,unit_price,line_total) VALUES (?,?,?,?,?)",(iid,item["d"],item["q"],item["p"],round(item["q"]*item["p"],2)))
        st.success(f"\u2705 {inv_num} — R {tot:,.2f} (VAT: {vat_rate}%)"); st.session_state["li"]=[{"d":"","q":1.0,"p":0.0}]

def page_view_invoices():
    st.title("\U0001f4cb Invoices"); auto_update_overdue_invoices(); st.markdown("---")
    sf=st.selectbox("Status",["All"]+INVOICE_STATUSES)
    q="SELECT i.*,c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id WHERE 1=1"; p=[]
    if sf!="All": q+=" AND i.status=?"; p.append(sf)
    with get_db() as conn: invs=conn.cursor().execute(q+" ORDER BY i.invoice_date DESC",p).fetchall()
    for inv in invs:
        s=inv["status"]; ic="\u2705" if s=="Paid" else "\U0001f534" if s=="Overdue" else "\U0001f7e1" if s=="Partially Paid" else "\U0001f4c4"
        with st.expander(f"{ic} {inv['invoice_number']} — {inv['company_name']} — R {inv['total_amount']:,.2f}"):
            vr=inv.get('vat_rate',15.0) or 15.0; vl=f"{vr:.0f}% VAT" if vr>0 else "No VAT"
            st.markdown(f"Due: {inv['due_date']} | Bal: R {inv['balance']:,.2f} | {vl} | {escalation_badge(inv.get('escalation_tier','None') or 'None')}")

def page_record_payment():
    st.title("\U0001f4b5 Payment"); st.markdown("---")
    with get_db() as conn: invs=conn.cursor().execute("SELECT i.*,c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.balance>0 AND i.status NOT IN ('Paid','Draft','Written Off') ORDER BY i.due_date").fetchall()
    if not invs: st.success("All settled!"); return
    opts={f"{i['invoice_number']} — {i['company_name']} — R {i['balance']:,.2f}":i for i in invs}; inv=opts[st.selectbox("Invoice",list(opts.keys()))]
    with st.form("pay",clear_on_submit=True):
        c1,c2=st.columns(2)
        with c1: pd=st.date_input("Date",date.today()); amt=st.number_input("Amount",0.01,float(inv["balance"]),float(inv["balance"]),format="%.2f")
        with c2: meth=st.selectbox("Method",PAYMENT_METHODS); ref=st.text_input("Reference")
        if st.form_submit_button("\U0001f4b0 Record",type="primary"):
            with get_db() as conn:
                c=conn.cursor(); c.execute("INSERT INTO payments (invoice_id,payment_date,amount,method,reference,recorded_by) VALUES (?,?,?,?,?,?)",(inv["id"],pd.strftime("%Y-%m-%d"),round(amt,2),meth,ref,st.session_state.get("username")))
                nb=max(0,round(inv["balance"]-amt,2)); np_=round(inv["total_amount"]-nb,2); ns="Paid" if nb<=0 else "Partially Paid"
                c.execute("UPDATE invoices SET amount_paid=?,balance=?,status=? WHERE id=?",(np_,nb,ns,inv["id"]))
                if ns=="Paid": c.execute("UPDATE promises_to_pay SET status='Honoured' WHERE invoice_id=? AND status IN ('Pending','Broken')",(inv["id"],))
            st.success(f"\u2705 R {amt:,.2f}")
            if ns=="Paid": st.balloons()

def page_ar_aging():
    st.title("\U0001f4ca AR Aging"); auto_update_overdue_invoices(); st.markdown("---")
    aging=get_ar_aging_data(); dso,tar=calculate_dso()
    c1,c2,c3=st.columns(3); c1.metric("Total AR",f"R {tar:,.0f}"); c2.metric("DSO",f"{dso}d"); c3.metric("Overdue %",f"{(sum(sum(i['balance'] for i in aging[b]) for b in ['1-30 days','31-60 days','61-90 days','91-120 days','120+ days'])/tar*100 if tar>0 else 0):.0f}%")
    colors={"Current":"\U0001f7e2","1-30 days":"\U0001f7e1","31-60 days":"\U0001f7e0","61-90 days":"\U0001f534","91-120 days":"\U0001f534","120+ days":"\u26ab"}
    for bn,invs in aging.items():
        bt=sum(i["balance"] for i in invs)
        with st.expander(f"{colors[bn]} {bn} — R {bt:,.0f} — {len(invs)} inv"):
            for i in invs: st.markdown(f"* {i['invoice_number']} — {i['company_name']} — R {i['balance']:,.2f}")

def page_collections_workflow():
    st.title("\U0001f4de Collections"); auto_update_overdue_invoices(); auto_update_escalation_tiers(); auto_flag_broken_ptps(); st.markdown("---")
    with get_db() as conn: qi=conn.cursor().execute("SELECT q.*,c.company_name,c.phone,c.contact_person FROM contact_me_queue q JOIN clients c ON q.client_id=c.id WHERE q.status='New'").fetchall()
    if qi:
        st.error(f"\U0001f6a8 **{len(qi)} urgent contact request(s)!**")
        for q in qi:
            st.markdown(f"\U0001f6a8 **{q['company_name']}** — {q['contact_person']} — {q['phone'] or '-'}")
            if st.button(f"\u2705 Contacted",key=f"rq{q['id']}"):
                with get_db() as conn: conn.cursor().execute("UPDATE contact_me_queue SET status='Contacted',resolved_by=? WHERE id=?",(st.session_state.get("username"),q["id"])); st.rerun()
        st.markdown("---")
    cs=st.text_input("Search",key="cs2"); tf=st.selectbox("Tier",["All"]+ESCALATION_TIERS[1:],key="tf2")
    q="SELECT i.*,c.company_name,c.phone,c.email,c.contact_person,c.id as cid FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.status NOT IN ('Paid','Draft','Written Off') AND i.balance>0"; p=[]
    if cs: q+=" AND (c.company_name LIKE ? OR i.invoice_number LIKE ?)"; p+=[f"%{cs}%"]*2
    if tf!="All": q+=" AND i.escalation_tier=?"; p.append(tf)
    with get_db() as conn: invs=[dict(r) for r in conn.cursor().execute(q+" ORDER BY i.due_date",p).fetchall()]
    if not invs: st.success("All clear!"); return
    st.markdown(f"**{len(invs)} invoice(s)**")
    for inv in invs:
        do=get_days_overdue(inv["due_date"]); tier=inv.get("escalation_tier","None") or "None"; at=tier if tier in COLLECTION_TEMPLATES else "Friendly"
        td={"company_name":inv["company_name"],"contact_person":inv["contact_person"],"invoice_number":inv["invoice_number"],"amount_due":f"{inv['balance']:,.2f}","due_date":inv["due_date"],"days_overdue":str(do)}
        with st.expander(f"{escalation_badge(tier)} {inv['invoice_number']} — {inv['company_name']} — R {inv['balance']:,.2f} — {do}d"):
            st.markdown(f"**{inv['contact_person']}** | {inv['phone'] or '-'} | {inv['email'] or '-'}")
            wm=render_template(COLLECTION_TEMPLATES[at]["whatsapp"],**td); wl=generate_whatsapp_link(inv["phone"],wm)
            if wl: st.markdown(f'<a href="{wl}" target="_blank"><button style="background:#25D366;color:white;padding:8px 16px;border:none;border-radius:6px;cursor:pointer">\U0001f4f1 WhatsApp</button></a>',unsafe_allow_html=True)
            with st.form(f"a{inv['id']}"):
                c1,c2=st.columns(2)
                with c1: atype=st.selectbox("Type",["WhatsApp","Email","SMS","Call","Letter"],key=f"at{inv['id']}"); oc=st.selectbox("Outcome",["Message Sent","No Answer","Spoke to Contact","Promise to Pay","Dispute"],key=f"oc{inv['id']}")
                with c2: an=st.text_area("Notes",key=f"an{inv['id']}")
                if st.form_submit_button("Log"):
                    with get_db() as conn: conn.cursor().execute("INSERT INTO collection_actions (invoice_id,client_id,action_type,escalation_tier,outcome,notes,performed_by) VALUES (?,?,?,?,?,?,?)",(inv["id"],inv["cid"],atype,tier,oc,an,st.session_state.get("username")))
                    st.success("\u2705")
            with st.form(f"p{inv['id']}"):
                c1,c2=st.columns(2)
                with c1: pa=st.number_input("PTP R",0.01,value=float(inv["balance"]),format="%.2f",key=f"pa{inv['id']}")
                with c2: ppd=st.date_input("By",date.today()+timedelta(days=7),key=f"pd{inv['id']}")
                if st.form_submit_button("\U0001f91d PTP"):
                    with get_db() as conn: conn.cursor().execute("INSERT INTO promises_to_pay (invoice_id,client_id,promised_amount,promised_date,created_by) VALUES (?,?,?,?,?)",(inv["id"],inv["cid"],pa,ppd.strftime("%Y-%m-%d"),st.session_state.get("username")))
                    st.success("\u2705 PTP!")

def page_ptp_tracker():
    st.title("\U0001f91d PTPs"); auto_flag_broken_ptps(); st.markdown("---")
    ts=date.today().strftime("%Y-%m-%d")
    with get_db() as conn:
        c=conn.cursor()
        due=c.execute("SELECT p.*,c.company_name,i.invoice_number FROM promises_to_pay p JOIN clients c ON p.client_id=c.id JOIN invoices i ON p.invoice_id=i.id WHERE p.promised_date<=? AND p.status IN ('Pending','Broken') ORDER BY p.promised_date",(ts,)).fetchall()
        up=c.execute("SELECT p.*,c.company_name,i.invoice_number FROM promises_to_pay p JOIN clients c ON p.client_id=c.id JOIN invoices i ON p.invoice_id=i.id WHERE p.promised_date>? AND p.status='Pending' ORDER BY p.promised_date",(ts,)).fetchall()
    t1,t2=st.tabs(["Due/Overdue","Upcoming"])
    with t1:
        for p in due:
            ic="\U0001f534" if p["status"]=="Broken" else "\U0001f7e1"
            st.markdown(f"{ic} **{p['company_name']}** — {p['invoice_number']} — R {p['promised_amount']:,.2f} — {p['status']}")
            if st.button("\U0001f7e2 Honoured",key=f"h{p['id']}"):
                with get_db() as conn: conn.cursor().execute("UPDATE promises_to_pay SET status='Honoured' WHERE id=?",(p["id"],)); st.rerun()
        if not due: st.success("None due!")
    with t2:
        for p in up:
            d=(datetime.strptime(p["promised_date"],"%Y-%m-%d").date()-date.today()).days
            st.markdown(f"\U0001f7e1 **{p['company_name']}** — R {p['promised_amount']:,.2f} — in {d}d")
        if not up: st.info("None upcoming.")

def page_document_manager():
    st.title("\U0001f4c1 Documents"); st.markdown("---")
    with get_db() as conn: cls=conn.cursor().execute("SELECT id,company_name FROM clients ORDER BY company_name").fetchall()
    if not cls: return
    opts={c['company_name']:c['id'] for c in cls}; cid=opts[st.selectbox("Client",list(opts.keys()),key="dm")]
    with st.form("upl",clear_on_submit=True):
        dc=st.selectbox("Category",DOC_CATEGORIES); dn=st.text_input("Name *"); uf=st.file_uploader("File",type=["pdf","jpg","png","doc","docx","xls","xlsx","txt","eml","csv","zip"])
        if st.form_submit_button("Upload",type="primary") and dn and uf:
            fb=uf.read()
            with get_db() as conn: conn.cursor().execute("INSERT INTO client_documents (client_id,doc_category,doc_name,original_filename,file_data,file_size,file_type,uploaded_by) VALUES (?,?,?,?,?,?,?,?)",(cid,dc,dn,uf.name,fb,len(fb),uf.type,st.session_state.get("username")))
            st.success(f"\u2705 {dn}")
    with get_db() as conn: docs=conn.cursor().execute("SELECT * FROM client_documents WHERE client_id=? ORDER BY doc_category",(cid,)).fetchall()
    for d in docs:
        c1,c2=st.columns([4,1])
        with c1: st.markdown(f"**{d['doc_category']}** — {d['doc_name']} — `{d['original_filename']}`")
        with c2: st.download_button("\u2b07",d['file_data'],d['original_filename'],key=f"dl{d['id']}")

def page_legal_pack():
    st.title("\u2696\ufe0f Legal Pack"); st.markdown("---")
    with get_db() as conn: cls=conn.cursor().execute("SELECT id,company_name FROM clients ORDER BY company_name").fetchall()
    if not cls: return
    opts={c['company_name']:c['id'] for c in cls}; cid=opts[st.selectbox("Client",list(opts.keys()),key="lp")]
    with get_db() as conn:
        c=conn.cursor(); cd=dict(c.execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone())
        dc={r["doc_category"]:r["cnt"] for r in c.execute("SELECT doc_category,COUNT(*) as cnt FROM client_documents WHERE client_id=? GROUP BY doc_category",(cid,))}
        invs=[dict(r) for r in c.execute("SELECT * FROM invoices WHERE client_id=? ORDER BY invoice_date",(cid,))]
        acts=[dict(r) for r in c.execute("SELECT * FROM collection_actions WHERE client_id=? ORDER BY performed_at",(cid,))]
        ptps=[dict(r) for r in c.execute("SELECT * FROM promises_to_pay WHERE client_id=? ORDER BY created_at",(cid,))]
        docs=c.execute("SELECT * FROM client_documents WHERE client_id=?",(cid,)).fetchall()
    tot=sum(i["balance"] for i in invs if i["status"] not in ("Paid","Draft","Written Off"))
    for rd in REQUIRED_LEGAL_DOCS: st.markdown(f"{'\u2705' if rd in dc else '\u274c'} **{rd}**")
    if st.button("\U0001f4e6 Generate ZIP",type="primary"):
        buf=io.BytesIO(); s=cd["company_name"].replace(" ","_")
        with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("01_Client.txt",f"Company: {cd['company_name']}\nReg: {cd.get('registration_number','')}\nContact: {cd['contact_person']}\nPhone: {cd.get('phone','')}\nEmail: {cd.get('email','')}\nAddress: {cd.get('physical_address','')}\nDomicilium: {cd.get('domicilium_address','')}\nOutstanding: R {tot:,.2f}")
            stmt="STATEMENT\n"+"="*60+"\n"
            for i in invs: stmt+=f"{i['invoice_number']:<15} {i['due_date']:<12} R {i['total_amount']:>10,.2f} R {i['balance']:>10,.2f} {i['status']}\n"
            z.writestr("02_Statement.txt",stmt)
            al="ACTION LOG\n"+"="*60+"\n"
            for a in acts: al+=f"{a.get('performed_at','')}: {a.get('action_type','')} — {a.get('outcome','')} — {a.get('notes','')}\n"
            z.writestr("03_Actions.txt",al)
            wt="COMMS TRAIL\n"+"="*60+"\n"
            for a in acts:
                if a.get("action_type") in ("WhatsApp","SMS"): wt+=f"{a.get('performed_at','')}: {a.get('action_type','')} — {a.get('notes','')}\n"
            z.writestr("04_Comms.txt",wt)
            pl="PTPs\n"+"="*60+"\n"
            for p in ptps: pl+=f"R {p['promised_amount']:,.2f} by {p['promised_date']} — {p['status']}\n"
            z.writestr("05_PTPs.txt",pl)
            for d in docs: z.writestr(f"06_Docs/{d['doc_category'].replace('/','_')}/{d['original_filename']}",d["file_data"])
        buf.seek(0); st.download_button("\U0001f4e5 Download",buf.getvalue(),f"{s}_Legal_Pack_{date.today()}.zip","application/zip",type="primary")

def page_letter_generator():
    st.title("\u2696\ufe0f Letter Generator"); st.markdown("---")
    with get_db() as conn: cls=conn.cursor().execute("SELECT id,company_name FROM clients ORDER BY company_name").fetchall()
    if not cls: return
    opts={c['company_name']:c['id'] for c in cls}; cid=opts[st.selectbox("Client",list(opts.keys()),key="lg")]
    with get_db() as conn:
        c=conn.cursor(); cl=dict(c.execute("SELECT * FROM clients WHERE id=?",(cid,)).fetchone())
        uinv=[dict(r) for r in c.execute("SELECT * FROM invoices WHERE client_id=? AND balance>0 AND status NOT IN ('Paid','Draft','Written Off') ORDER BY due_date",(cid,))]
    lt,rsn=determine_letter_type(cl.get("is_credit_agreement","No") or "No",cl.get("debtor_entity_type","Company") or "Company",cl.get("annual_turnover_above_1m","Unknown") or "Unknown",cl.get("at_arms_length","Yes") or "Yes")
    st.info(f"**{lt}** — {rsn}")
    c1,c2=st.columns(2)
    with c1: dn=st.text_input("Debtor Name",cl["company_name"]); fka=st.text_input("Formerly Known As"); cap=st.radio("Capacity",CAPACITY_OPTIONS)
    with c2: ld=st.date_input("Date",date.today()); dom=st.text_area("Domicilium",cl.get("domicilium_address","") or cl.get("physical_address","") or "",height=80)
    if not uinv: st.warning("No unpaid invoices."); return
    sinv=[i for i in uinv if st.checkbox(f"{i['invoice_number']} R {i['balance']:,.2f}",True,key=f"s{i['id']}")]
    if not sinv: return
    sub=sum(i["balance"] for i in sinv); avg_do=sum(get_days_overdue(i["due_date"]) for i in sinv)/len(sinv)
    c1,c2,c3=st.columns(3)
    with c1: ir=st.number_input("Interest %",value=DEFAULT_INTEREST_RATE,format="%.1f"); ia=st.number_input("Interest R",value=round(sub*(ir/100)*(avg_do/365),2),format="%.2f")
    with c2: cc=st.number_input("Costs R",0.0,format="%.2f")
    tot=sub+ia+cc; c3.metric("TOTAL",f"R {tot:,.2f}")
    if st.button("Generate",type="primary"):
        nm=f"{dn} (formerly {fka})" if fka else dn; il="\n".join(f"  {i['invoice_number']:<16} {i['due_date']:<12} R {i['balance']:>10,.2f}" for i in sinv)
        dl="7 CALENDAR DAYS" if lt=="Letter of Demand" else "10 BUSINESS DAYS"
        header=f"{'LETTER OF DEMAND' if lt=='Letter of Demand' else 'SECTION 129(1)(a) NOTICE'}\nDate: {ld.strftime('%d %B %Y')}\n\nTO: {nm}\nDomicilium: {dom}\nCapacity: {cap}\n\n{'='*50}\n"
        body=f"Amounts outstanding:\n{il}\n{'='*50}\nSubtotal: R {sub:,.2f}\nInterest: R {ia:,.2f}\nCosts:    R {cc:,.2f}\nTOTAL:    R {tot:,.2f}\n\nDEMAND: Pay R {tot:,.2f} within {dl}.\n"
        if lt=="Section 129 Notice": body+="\nYOUR RIGHTS (NCA):\n(a) Debt counsellor — NCR: 0860 627 627\n(b) Resolve directly with us\n(c) Consumer Tribunal: (012) 683 8140\n"
        body+=f"\nFailure to pay: legal action, credit bureau, legal costs.\n{'Surety/guarantor: jointly liable.' if 'Surety' in cap or 'Guarantor' in cap else ''}\n\nKA Legacy (PTY) LTD"
        letter=header+body
        st.text_area("Preview",letter,height=400)
        st.download_button("\U0001f4e5 Download",letter,f"{cl['company_name'].replace(' ','_')}_{lt.replace(' ','_')}_{ld}.txt")
        if lt=="Section 129 Notice": st.error("**MANDATORY:** PRINT \u2192 REGISTERED MAIL to domicilium \u2192 EMAIL \u2192 Upload tracking slip \u2192 WAIT 10 BUSINESS DAYS")
        else: st.warning("**RECOMMENDED:** PRINT \u2192 REGISTERED MAIL \u2192 EMAIL \u2192 Upload tracking slip \u2192 WAIT 7 DAYS")

def page_early_warning():
    st.title("\U0001f514 Early Warning"); auto_update_overdue_invoices(); auto_flag_broken_ptps(); st.markdown("---")
    w=[]; ts=date.today().strftime("%Y-%m-%d"); ts7=(date.today()+timedelta(days=7)).strftime("%Y-%m-%d")
    with get_db() as conn:
        c=conn.cursor()
        for r in c.execute("SELECT i.*,c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.due_date BETWEEN ? AND ? AND i.balance>0 AND i.status IN ('Sent','Partially Paid')",(ts,ts7)):
            d=(datetime.strptime(r["due_date"],"%Y-%m-%d").date()-date.today()).days
            w.append({"cl":r["company_name"],"t":"\u23f0 Due Soon","s":"Medium" if d>3 else "High","d":f"{r['invoice_number']} R {r['balance']:,.0f} in {d}d","a":"Send reminder."})
        for r in c.execute("SELECT p.*,c.company_name,i.invoice_number FROM promises_to_pay p JOIN clients c ON p.client_id=c.id JOIN invoices i ON p.invoice_id=i.id WHERE p.status='Broken'"):
            w.append({"cl":r["company_name"],"t":"\u274c Broken PTP","s":"High","d":f"{r['invoice_number']} R {r['promised_amount']:,.0f}","a":"Call immediately."})
        for r in c.execute("SELECT c.company_name,SUM(i.balance) as t FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.balance>0 AND julianday('now')-julianday(i.due_date)>60 AND i.status NOT IN ('Paid','Draft','Written Off') GROUP BY c.id"):
            w.append({"cl":r["company_name"],"t":"\U0001f534 60+ Days","s":"High","d":f"R {r['t']:,.0f} overdue","a":"Issue demand letter."})
        for r in c.execute("SELECT c.*,COALESCE(SUM(i.balance),0) as t FROM clients c LEFT JOIN invoices i ON c.id=i.client_id AND i.balance>0 AND i.status NOT IN ('Paid','Draft','Written Off') WHERE c.credit_limit_approved>0 GROUP BY c.id HAVING t>=c.credit_limit_approved*0.8"):
            w.append({"cl":r["company_name"],"t":"\u26a0\ufe0f Near Limit","s":"High","d":f"{r['t']/r['credit_limit_approved']*100:.0f}% used","a":"Stop credit."})
    w.sort(key=lambda x:{"High":0,"Medium":1}.get(x["s"],2))
    hi=sum(1 for x in w if x["s"]=="High")
    c1,c2,c3=st.columns(3); c1.metric("Warnings",len(w)); c2.metric("High",hi); c3.metric("Medium",len(w)-hi)
    if not w: st.success("All clear!"); return
    for i,x in enumerate(w):
        ic="\U0001f534" if x["s"]=="High" else "\U0001f7e1"
        with st.expander(f"{ic} {x['t']} — {x['cl']}"): st.markdown(f"**{x['d']}**\n\n**Action:** {x['a']}")

def page_audit_trail():
    st.title("\U0001f4dc Audit Trail"); st.markdown("---")
    with get_db() as conn: ds=conn.cursor().execute("SELECT cd.*,c.company_name FROM credit_decisions cd JOIN clients c ON cd.client_id=c.id ORDER BY cd.decided_at DESC").fetchall()
    for d in ds:
        with st.expander(f"{decision_badge(d['final_decision'])} — {d['company_name']} — {d['decided_at']}"):
            st.markdown(f"Score: {d['credit_score']}/100 | {d['final_decision']} | Limit: R {d['credit_limit_approved']:,.0f}\n\n**Reason:** {d['reason']}")

def page_user_management():
    st.title("\U0001f465 Users"); st.markdown("---")
    if st.session_state.get("role")!="admin": st.error("Admin only."); return
    with get_db() as conn:
        for u in conn.cursor().execute("SELECT * FROM users ORDER BY id").fetchall(): st.markdown(f"**{u['full_name']}** ({u['username']}) — {u['role']}")
    with st.form("au",clear_on_submit=True):
        c1,c2=st.columns(2)
        with c1: nf=st.text_input("Name *"); nu=st.text_input("Username *")
        with c2: np=st.text_input("Password *",type="password"); nr=st.selectbox("Role",["user","admin"])
        if st.form_submit_button("Create",type="primary") and nf and nu and np:
            try:
                with get_db() as conn: conn.cursor().execute("INSERT INTO users (username,password_hash,full_name,role) VALUES (?,?,?,?)",(nu,hash_password(np),nf,nr))
                st.success(f"\u2705 {nf}")
            except: st.error("Username exists.")

def page_change_password():
    st.title("\U0001f511 Password"); st.markdown("---")
    with st.form("cp"):
        cp=st.text_input("Current",type="password"); np=st.text_input("New",type="password"); cnp=st.text_input("Confirm",type="password")
        if st.form_submit_button("Update",type="primary"):
            if np!=cnp: st.error("Mismatch.")
            elif len(np)<6: st.error("Min 6 chars.")
            elif not authenticate_user(st.session_state["username"],cp): st.error("Wrong password.")
            else:
                with get_db() as conn: conn.cursor().execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(np),st.session_state["user_id"]))
                st.success("\u2705 Updated!")

def main_app():
    st.set_page_config(page_title="KA CreditFlow",page_icon="\U0001f3e6",layout="wide",initial_sidebar_state="expanded")
    st.markdown("""<style>[data-testid="stSidebar"]{background:#1B4F72}[data-testid="stSidebar"] *{color:white !important}.stMetric{background:#F8F9FA;padding:1rem;border-radius:10px;border-left:4px solid #1B4F72}</style>""",unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("## \U0001f3e6 KA CreditFlow")
        st.markdown(f"**{st.session_state.get('full_name','')}** | {st.session_state.get('role','').title()}")
        st.markdown("---")
        page=st.radio("",[ "\U0001f4ca Dashboard","\u2795 Add Client","\U0001f4c1 Clients","\u26a1 Credit Engine","---","\U0001f9fe Invoice","\U0001f4cb Invoices","\U0001f4b5 Payment","\U0001f4ca AR Aging","----","\U0001f4de Collections","\U0001f91d PTPs","\U0001f4c1 Documents","\u2696\ufe0f Legal Pack","\u2696\ufe0f Letters","\U0001f514 Warnings","-----","\U0001f4dc Audit","\U0001f465 Users","\U0001f511 Password"],label_visibility="collapsed")
        st.markdown("---")
        if st.button("\U0001f6aa Sign Out"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
        st.caption("v4.0 | \u00a9 2026 KA Legacy")
    R={"\U0001f4ca Dashboard":page_dashboard,"\u2795 Add Client":page_add_client,"\U0001f4c1 Clients":page_view_clients,"\u26a1 Credit Engine":page_credit_engine,"\U0001f9fe Invoice":page_create_invoice,"\U0001f4cb Invoices":page_view_invoices,"\U0001f4b5 Payment":page_record_payment,"\U0001f4ca AR Aging":page_ar_aging,"\U0001f4de Collections":page_collections_workflow,"\U0001f91d PTPs":page_ptp_tracker,"\U0001f4c1 Documents":page_document_manager,"\u2696\ufe0f Legal Pack":page_legal_pack,"\u2696\ufe0f Letters":page_letter_generator,"\U0001f514 Warnings":page_early_warning,"\U0001f4dc Audit":page_audit_trail,"\U0001f465 Users":page_user_management,"\U0001f511 Password":page_change_password}
    fn=R.get(page)
    if fn: fn()

init_database()
if st.session_state.get("authenticated",False): main_app()
else: login_page()
