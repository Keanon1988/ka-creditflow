"""
KA CreditFlow v6.0c - Legal Compliance Module
"""
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta, date

SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"
PRESCRIPTION_YEARS = 3

def get_sast_now():
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")
def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn
def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()))
    conn.commit(); conn.close()

LEGAL_STAGES = ["Pre-Legal","S129 Sent","S129 Expired","LOD Sent","LOD Expired","Attorney Handover","Summons Issued","Judgement Obtained","Warrant of Execution"]
STAGE_COLOURS = {"Pre-Legal":"#6c757d","S129 Sent":"#0d6efd","S129 Expired":"#ffc107","LOD Sent":"#fd7e14","LOD Expired":"#dc3545","Attorney Handover":"#e35d6a","Summons Issued":"#842029","Judgement Obtained":"#dc3545","Warrant of Execution":"#000000"}

def init_legal_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS legal_notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, invoice_id INTEGER,
        notice_type TEXT NOT NULL, status TEXT DEFAULT 'Draft', default_amount REAL,
        default_start_date TEXT, notice_date TEXT, delivery_method TEXT, tracking_reference TEXT,
        response_deadline TEXT, notice_text TEXT, generated_by TEXT, generated_at TEXT, sent_at TEXT, delivered_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS legal_escalations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, invoice_id INTEGER,
        stage TEXT DEFAULT 'Pre-Legal', current_stage_date TEXT, next_action_date TEXT,
        attorney_reference TEXT, notes TEXT, status TEXT DEFAULT 'Active',
        created_by TEXT, created_at TEXT, updated_at TEXT)""")
    conn.commit(); conn.close()

def generate_section129_notice(creditor_name, creditor_address, consumer_name, consumer_address, agreement_ref, default_amount, default_date, notice_date=None):
    if notice_date is None: notice_date = date.today().strftime("%d %B %Y")
    return f"""NOTICE IN TERMS OF SECTION 129(1)(a) READ WITH SECTION 130
OF THE NATIONAL CREDIT ACT NO. 34 OF 2005

Date: {notice_date}
SENT BY REGISTERED MAIL

To:     {consumer_name}
        {consumer_address}
From:   {creditor_name}
        {creditor_address}

RE: NOTICE OF DEFAULT - AGREEMENT REF: {agreement_ref}

Dear {consumer_name},

1. We hereby notify you, in terms of Section 129(1)(a) of the National
   Credit Act No. 34 of 2005, that you are in DEFAULT.

2. DETAILS OF DEFAULT:
   Agreement Reference:    {agreement_ref}
   Default Amount:         R {default_amount:,.2f}
   Date of Default:        {default_date}

3. YOUR RIGHTS:
   (a) Refer to a DEBT COUNSELLOR;
   (b) Refer to an ALTERNATIVE DISPUTE RESOLUTION AGENT;
   (c) Refer to a CONSUMER COURT; or
   (d) Refer to the relevant OMBUD.
   Contact NCR: 0860 627 627 | www.ncr.org.za

4. You have TEN (10) BUSINESS DAYS to respond.

5. Non-response may result in court action, credit bureau reporting,
   legal costs recovery, and asset attachment.

6. You may remedy the default by paying R {default_amount:,.2f}.

DATED on this {notice_date}.

_______________________________
{creditor_name}
Credit Provider / Authorised Representative"""

def generate_letter_of_demand(creditor_name, creditor_address, debtor_name, debtor_address, debt_description, amount_owed, interest_amount, invoice_ref, original_due_date, deadline_days=14, notice_date=None):
    if notice_date is None: notice_date = date.today().strftime("%d %B %Y")
    deadline_date = (date.today() + timedelta(days=deadline_days)).strftime("%d %B %Y")
    total = amount_owed + interest_amount
    return f"""LETTER OF DEMAND
WITHOUT PREJUDICE

Date: {notice_date}
SENT BY REGISTERED MAIL / EMAIL WITH READ RECEIPT

To:     {debtor_name}
        {debtor_address}
From:   {creditor_name}
        {creditor_address}
Ref:    {invoice_ref}

RE: FORMAL DEMAND FOR PAYMENT

1. DETAILS OF DEBT:
   Description:     {debt_description}
   Invoice Ref:     {invoice_ref}
   Due Date:        {original_due_date}
   Capital:         R {amount_owed:,.2f}
   Interest:        R {interest_amount:,.2f}
   TOTAL DUE:       R {total:,.2f}

2. Pay R {total:,.2f} within {deadline_days} BUSINESS DAYS (by {deadline_date}).

3. Non-payment consequences:
   (a) Legal proceedings with attorney-client costs;
   (b) Credit bureau reporting;
   (c) Warrant of execution against property.

KINDLY GOVERN YOURSELF ACCORDINGLY.

DATED on this {notice_date}.

_______________________________
{creditor_name}
Authorised Representative"""

def check_prescription(last_payment_date, last_acknowledgment_date=None):
    today = date.today()
    ref = last_payment_date
    if last_acknowledgment_date and last_acknowledgment_date > last_payment_date: ref = last_acknowledgment_date
    presc_date = ref + timedelta(days=PRESCRIPTION_YEARS * 365)
    days_left = (presc_date - today).days
    prescribed = days_left <= 0
    if prescribed: status = "PRESCRIBED"
    elif days_left <= 90: status = "CRITICAL"
    elif days_left <= 180: status = "WARNING"
    else: status = "OK"
    return {"reference_date": ref, "prescription_date": presc_date, "days_remaining": days_left, "is_prescribed": prescribed, "status": status}

def render_legal_compliance():
    init_legal_db()
    st.markdown("## Legal Compliance & Notices")
    tab = st.radio("", ["Generate Notice","Legal Pipeline","Prescription Tracker","Notice History"], horizontal=True, key="legal_tab")
    conn = get_db(); today = date.today()
    if tab == "Generate Notice":
        st.markdown("### Generate Legal Notice")
        ntype = st.selectbox("Type", ["Section 129(1)(a) NCA Notice","Letter of Demand"], key="lnt")
        clients = pd.read_sql("SELECT id, company_name, contact_person, address FROM clients ORDER BY company_name", conn)
        if len(clients)==0: st.warning("No clients."); conn.close(); return
        cmap = dict(zip(clients["company_name"], clients["id"]))
        sel = st.selectbox("Client", list(cmap.keys()), key="lcl")
        cid = cmap[sel]; cl = clients[clients["id"]==cid].iloc[0]
        invs = pd.read_sql("SELECT * FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid','Disputed') ORDER BY due_date", conn, params=(cid,))
        if len(invs)==0: st.info("No open invoices."); conn.close(); return
        invs["outstanding"] = invs["total_amount"] - invs["amount_paid"]
        labels = invs.apply(lambda r: f"{r['invoice_number']} - R {r['outstanding']:,.2f}", axis=1).tolist()
        si = st.selectbox("Invoice", labels, key="linv")
        inv = invs.iloc[labels.index(si)]
        due_dt = datetime.strptime(inv["due_date"],"%Y-%m-%d").date()
        days_od = (today - due_dt).days; bdays = int(days_od * 5/7)
        if ntype.startswith("Section"):
            if bdays < 20: st.error(f"Cannot generate yet. ~{bdays} business days. Need 20+.")
            else: st.success(f"~{bdays} business days in default. Notice may be generated.")
            c1,c2 = st.columns(2)
            with c1:
                cn = st.text_input("Creditor", value="KA Legacy (Pty) Ltd", key="s129cn")
                ca = st.text_area("Creditor Address", value="14 Rivonia Road, Sandton, 2196", height=80, key="s129ca")
            with c2:
                dn = st.text_input("Consumer", value=str(cl["contact_person"] or cl["company_name"]), key="s129dn")
                da = st.text_area("Consumer Address", value=str(cl["address"] or ""), height=80, key="s129da")
            if st.button("Generate Section 129", type="primary", key="gs129", disabled=bdays<20):
                txt = generate_section129_notice(cn,ca,dn,da,inv["invoice_number"],float(inv["outstanding"]),inv["due_date"])
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute("INSERT INTO legal_notices (client_id,invoice_id,notice_type,status,default_amount,default_start_date,notice_date,notice_text,generated_by,generated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (cid,int(inv["id"]),"Section 129","Draft",float(inv["outstanding"]),inv["due_date"],str(today),txt,DEFAULT_USER,get_sast_now()))
                conn2.commit(); conn2.close()
                log_audit("LEGAL","Legal","S129 generated for "+sel)
                st.success("Section 129 notice generated!"); st.code(txt, language=None)
        else:
            c1,c2 = st.columns(2)
            with c1:
                cn = st.text_input("Creditor", value="KA Legacy (Pty) Ltd", key="lodcn")
                ca = st.text_area("Creditor Address", value="14 Rivonia Road, Sandton, 2196", height=80, key="lodca")
                dl = st.selectbox("Deadline (days)", [7,10,14,21,30], index=2, key="loddl")
            with c2:
                dn = st.text_input("Debtor", value=str(cl["contact_person"] or cl["company_name"]), key="loddn")
                da = st.text_area("Debtor Address", value=str(cl["address"] or ""), height=80, key="lodda")
                interest = st.number_input("Interest (R)", min_value=0.0, value=0.0, step=100.0, key="lodi")
            if st.button("Generate LOD", type="primary", key="glod"):
                txt = generate_letter_of_demand(cn,ca,dn,da,inv.get("description","") or "Outstanding invoice",float(inv["outstanding"]),interest,inv["invoice_number"],inv["due_date"],dl)
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute("INSERT INTO legal_notices (client_id,invoice_id,notice_type,status,default_amount,default_start_date,notice_date,notice_text,generated_by,generated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (cid,int(inv["id"]),"Letter of Demand","Draft",float(inv["outstanding"]),inv["due_date"],str(today),txt,DEFAULT_USER,get_sast_now()))
                conn2.commit(); conn2.close()
                log_audit("LEGAL","Legal","LOD generated for "+sel)
                st.success("Letter of Demand generated!"); st.code(txt, language=None)
    elif tab == "Legal Pipeline":
        st.markdown("### Legal Escalation Pipeline")
        escs = pd.read_sql("SELECT le.*, c.company_name FROM legal_escalations le JOIN clients c ON le.client_id=c.id WHERE le.status='Active' ORDER BY le.updated_at DESC", conn)
        cols = st.columns(len(LEGAL_STAGES))
        for i, s in enumerate(LEGAL_STAGES):
            cnt = len(escs[escs["stage"]==s]) if len(escs)>0 else 0
            c = STAGE_COLOURS.get(s,"#6c757d")
            with cols[i]:
                st.markdown(f'<div style="text-align:center;padding:6px 2px;background:{c};color:white;border-radius:4px;font-size:0.6em;font-weight:bold;">{s}<br>{cnt}</div>', unsafe_allow_html=True)
        if len(escs)>0:
            for _, e in escs.iterrows():
                c = STAGE_COLOURS.get(e["stage"],"#6c757d")
                st.markdown(f'<div style="border-left:4px solid {c};padding:8px 14px;margin-bottom:6px;background:#f9f9f9;border-radius:6px;"><span style="background:{c};color:white;padding:2px 10px;border-radius:10px;font-size:0.8em;">{e["stage"]}</span> <strong>{e["company_name"]}</strong> <span style="float:right;color:#888;font-size:0.85em;">Next: {e["next_action_date"] or "N/A"}</span></div>', unsafe_allow_html=True)
        st.divider(); st.markdown("### Create Escalation")
        cls = pd.read_sql("SELECT id, company_name FROM clients ORDER BY company_name", conn)
        with st.form("create_esc"):
            ec1,ec2 = st.columns(2)
            with ec1:
                ecl = st.selectbox("Client", cls["company_name"].tolist(), key="escl")
                ecid = int(cls[cls["company_name"]==ecl]["id"].values[0])
                est = st.selectbox("Stage", LEGAL_STAGES, key="esst")
            with ec2:
                enx = st.date_input("Next Action", value=today+timedelta(days=14), key="esnx")
                ent = st.text_input("Notes", key="esnt")
            if st.form_submit_button("Create", type="primary"):
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute("INSERT INTO legal_escalations (client_id,stage,current_stage_date,next_action_date,notes,status,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (ecid,est,str(today),str(enx),ent,"Active",DEFAULT_USER,get_sast_now(),get_sast_now()))
                conn2.commit(); conn2.close()
                log_audit("LEGAL","Legal Pipeline",f"Escalation: {ecl} at {est}")
                st.success(f"Escalation created for {ecl}"); st.rerun()
    elif tab == "Prescription Tracker":
        st.markdown("### Prescription Tracker")
        st.markdown("_Debts prescribe after 3 years (Act 68/1969)._")
        invs = pd.read_sql("SELECT i.*, c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.status IN ('Open','Partially Paid','Disputed') ORDER BY i.due_date", conn)
        if len(invs)==0: st.info("No open invoices."); conn.close(); return
        results = []
        for _, inv in invs.iterrows():
            dd = datetime.strptime(inv["due_date"],"%Y-%m-%d").date()
            p = check_prescription(dd)
            results.append({"Client":inv["company_name"],"Invoice":inv["invoice_number"],"Outstanding":inv["total_amount"]-inv["amount_paid"],"Due":inv["due_date"],"Prescribes":str(p["prescription_date"]),"Days Left":p["days_remaining"],"Status":p["status"]})
        df = pd.DataFrame(results)
        crit = df[df["Status"].isin(["PRESCRIBED","CRITICAL"])]
        if len(crit)>0: st.error(f"{len(crit)} debt(s) prescribed or critical!")
        df2 = df.copy(); df2["Outstanding"] = df2["Outstanding"].apply(lambda x: f"R {x:,.2f}")
        st.dataframe(df2, use_container_width=True, hide_index=True)
    else:
        st.markdown("### Notice History")
        notices = pd.read_sql("SELECT ln.*, c.company_name FROM legal_notices ln JOIN clients c ON ln.client_id=c.id ORDER BY ln.generated_at DESC", conn)
        if len(notices)==0: st.info("No notices yet.")
        else:
            for _, n in notices.iterrows():
                tc = {"Section 129":"#0d6efd","Letter of Demand":"#fd7e14"}.get(n["notice_type"],"#6c757d")
                sc = {"Draft":"#ffc107","Sent":"#0d6efd","Delivered":"#198754"}.get(n["status"],"#6c757d")
                st.markdown(f'<div style="border-left:4px solid {tc};padding:8px 14px;margin-bottom:6px;background:#f9f9f9;border-radius:6px;"><span style="background:{tc};color:white;padding:2px 10px;border-radius:10px;font-size:0.8em;">{n["notice_type"]}</span> <span style="background:{sc};color:white;padding:2px 8px;border-radius:10px;font-size:0.75em;">{n["status"]}</span> <strong>{n["company_name"]}</strong> - R {(n["default_amount"] or 0):,.2f} <span style="float:right;color:#888;font-size:0.85em;">{n["generated_at"]}</span></div>', unsafe_allow_html=True)
    conn.close()
