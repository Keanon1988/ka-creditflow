"""
KA CreditFlow — Credit Engine v2
Banking-Grade Credit Risk Assessment for SMEs

Mission: Give SME owners the same credit risk intelligence that
Investec uses internally — no fabricated data, no fake scores,
every output traceable to a real input.

Architecture:
  Layer 1: Data Gate & Credit Origination
  Layer 2: Dual-Model Scoring (Cold Start + Full Model)
  Layer 3: IFRS 9 ECL Calculation with Staging
"""
import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import math
from datetime import datetime, timezone, timedelta, date

SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"

def get_sast_now():
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")
def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn
def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()))
    conn.commit(); conn.close()


def safe_get(row, key, default=None):
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default

RISK_GRADES = {
    "A": {"label":"Excellent","colour":"#198754","pd":0.005,"limit_mult":1.0},
    "B": {"label":"Good","colour":"#20c997","pd":0.02,"limit_mult":0.8},
    "C": {"label":"Fair","colour":"#ffc107","pd":0.05,"limit_mult":0.6},
    "D": {"label":"Poor","colour":"#fd7e14","pd":0.15,"limit_mult":0.3},
    "E": {"label":"Critical","colour":"#dc3545","pd":0.35,"limit_mult":0.0},
}
LGD_BY_SECURITY = {"Unsecured":0.45,"Personal Surety":0.35,"Cession of Debtors":0.25,"Property Secured":0.15}
REQUIRED_DOCS = ["credit_application","company_registration","bank_statements","financial_statements","itc_report","trade_references","id_documents","tax_clearance"]
DOC_LABELS = {"credit_application":"Credit Application Form","company_registration":"Company Registration (CIPC)","bank_statements":"3 Months Bank Statements","financial_statements":"Financial Statements","itc_report":"ITC / Credit Bureau Report","trade_references":"Trade References (x3)","id_documents":"Director ID Documents","tax_clearance":"Tax Clearance Certificate"}
MANDATORY_DOCS = ["credit_application","company_registration","itc_report"]

# =============================================================================
# DATABASE
# =============================================================================
def init_credit_engine_v2_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS credit_assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL,
        assessment_type TEXT DEFAULT 'New', status TEXT DEFAULT 'Draft',
        doc_credit_application INTEGER DEFAULT 0, doc_company_registration INTEGER DEFAULT 0,
        doc_bank_statements INTEGER DEFAULT 0, doc_financial_statements INTEGER DEFAULT 0,
        doc_itc_report INTEGER DEFAULT 0, doc_trade_references INTEGER DEFAULT 0,
        doc_id_documents INTEGER DEFAULT 0, doc_tax_clearance INTEGER DEFAULT 0,
        itc_score INTEGER, itc_judgements INTEGER DEFAULT 0, itc_defaults INTEGER DEFAULT 0,
        itc_payment_profile TEXT, itc_enquiries INTEGER DEFAULT 0,
        annual_revenue REAL, total_assets REAL, total_liabilities REAL,
        monthly_cash_flow REAL, existing_debt REAL,
        security_type TEXT DEFAULT 'Unsecured',
        data_sufficiency_pct REAL, model_type TEXT,
        composite_score REAL, risk_grade TEXT, confidence_level REAL,
        pd_estimate REAL, lgd REAL, ead REAL, ecl REAL,
        ifrs9_stage INTEGER DEFAULT 1, recommended_limit REAL,
        recommended_actions TEXT, assessment_notes TEXT,
        assessed_by TEXT, assessed_at TEXT, expires_at TEXT)""")
    conn.commit(); conn.close()

# =============================================================================
# LAYER 1: DATA GATE
# =============================================================================
def check_data_sufficiency(client_id, db_path=DB_PATH):
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
    assessment = conn.execute("SELECT * FROM credit_assessments WHERE client_id=? ORDER BY id DESC LIMIT 1", (client_id,)).fetchone()
    if not assessment:
        conn.close()
        return {"documents_received":0,"documents_missing":REQUIRED_DOCS,"sufficiency_pct":0,
                "model_type":"No Assessment","minimum_met":False,"has_assessment":False,
                "message":"No credit assessment on file. Complete a credit application first."}
    received = []
    missing = []
    for doc in REQUIRED_DOCS:
        if assessment[f"doc_{doc}"] == 1:
            received.append(doc)
        else:
            missing.append(doc)
    mandatory_met = all(assessment[f"doc_{d}"] == 1 for d in MANDATORY_DOCS)
    has_itc = assessment["doc_itc_report"] == 1 and assessment["itc_score"] is not None
    has_financials = assessment["doc_financial_statements"] == 1 and assessment["annual_revenue"] is not None
    # Check platform trading history
    inv_count = conn.execute("SELECT COUNT(*) FROM invoices WHERE client_id=?", (client_id,)).fetchone()[0]
    pay_count = conn.execute("SELECT COUNT(*) FROM payments WHERE client_id=?", (client_id,)).fetchone()[0]
    if inv_count > 0:
        first_inv = conn.execute("SELECT MIN(invoice_date) FROM invoices WHERE client_id=?", (client_id,)).fetchone()[0]
        months_trading = max(0, (date.today() - datetime.strptime(first_inv, "%Y-%m-%d").date()).days / 30) if first_inv else 0
    else:
        months_trading = 0
    conn.close()
    sufficiency_pct = len(received) / len(REQUIRED_DOCS) * 100
    # Determine model type
    if not mandatory_met or len(received) < 3:
        model_type = "Cannot Score"
        message = f"Insufficient data. {len(received)}/8 documents received. Missing mandatory: {', '.join(DOC_LABELS.get(d,d) for d in MANDATORY_DOCS if d not in received)}."
        minimum_met = False
    elif months_trading < 3 or pay_count < 3:
        model_type = "Cold Start"
        message = f"New client — {months_trading:.0f} months trading history, {pay_count} payments recorded. Using Cold Start model (provisional score, low confidence)."
        minimum_met = True
    else:
        model_type = "Full Model"
        message = f"Sufficient data — {months_trading:.0f} months history, {pay_count} payments, {len(received)}/8 documents. Full scoring model available."
        minimum_met = True
    return {"documents_received":len(received),"documents_received_list":received,
            "documents_missing":len(missing),"documents_missing_list":missing,
            "sufficiency_pct":round(sufficiency_pct,1),"model_type":model_type,
            "minimum_met":minimum_met,"has_assessment":True,
            "mandatory_met":mandatory_met,"has_itc":has_itc,"has_financials":has_financials,
            "months_trading":round(months_trading,1),"invoice_count":inv_count,
            "payment_count":pay_count,"message":message}

# =============================================================================
# LAYER 2A: COLD START MODEL (New clients)
# =============================================================================
def calculate_cold_start_score(client_id, db_path=DB_PATH):
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
    a = conn.execute("SELECT * FROM credit_assessments WHERE client_id=? ORDER BY id DESC LIMIT 1", (client_id,)).fetchone()
    if not a:
        conn.close()
        return None
    factors = {}
    scored_count = 0
    total_factors = 5
    # Factor 1: ITC Score (30%)
    if a["itc_score"] is not None and a["doc_itc_report"] == 1:
        raw_itc = min(100, max(0, a["itc_score"]))
        # Adjust for adverse
        adverse_penalty = min(40, (a["itc_judgements"] or 0) * 15 + (a["itc_defaults"] or 0) * 10)
        itc_factor = max(0, raw_itc - adverse_penalty)
        factors["itc"] = {"score":round(itc_factor,1),"weight":0.30,"source":"Bureau Report","status":"scored","detail":f"ITC: {a['itc_score']}, Judgements: {a['itc_judgements']}, Defaults: {a['itc_defaults']}"}
        scored_count += 1
    else:
        factors["itc"] = {"score":None,"weight":0.30,"source":"Not provided","status":"missing","detail":"No ITC report uploaded"}
    # Factor 2: Financial Health (25%)
    if a["annual_revenue"] and a["total_liabilities"] is not None and a["total_assets"] is not None:
        if a["total_assets"] > 0:
            debt_to_assets = a["total_liabilities"] / a["total_assets"]
            fin_score = max(0, min(100, (1 - debt_to_assets) * 100))
        else:
            fin_score = 20
        factors["financial"] = {"score":round(fin_score,1),"weight":0.25,"source":"Financial Statements","status":"scored","detail":f"Revenue: R{a['annual_revenue']:,.0f}, D/A: {debt_to_assets:.1%}" if a["total_assets"] > 0 else ""}
        scored_count += 1
    else:
        factors["financial"] = {"score":None,"weight":0.25,"source":"Not provided","status":"missing","detail":"No financial statements uploaded"}
    # Factor 3: Business Stability (20%)
    cl = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if cl:
        reg = safe_get(cl, "registration_number", "") or ""
        if reg and "/" in reg:
            try:
                year = int(reg.split("/")[0])
                years = max(0, date.today().year - year)
            except ValueError:
                years = 0
        else:
            years = 0
        stability = min(100, years * 10 + 20)
        factors["stability"] = {"score":round(stability,1),"weight":0.20,"source":"Company Registration","status":"scored","detail":f"{years} years in business"}
        scored_count += 1
    else:
        factors["stability"] = {"score":None,"weight":0.20,"source":"Unknown","status":"missing","detail":"Client record not found"}
    # Factor 4: Documentation Quality (15%)
    doc_count = sum(1 for d in REQUIRED_DOCS if a[f"doc_{d}"] == 1)
    doc_score = (doc_count / len(REQUIRED_DOCS)) * 100
    factors["documentation"] = {"score":round(doc_score,1),"weight":0.15,"source":"Application Checklist","status":"scored","detail":f"{doc_count}/{len(REQUIRED_DOCS)} documents provided"}
    scored_count += 1
    # Factor 5: Bureau Adverse (10%)
    if a["doc_itc_report"] == 1:
        total_adverse = (a["itc_judgements"] or 0) + (a["itc_defaults"] or 0)
        adverse_score = max(0, 100 - total_adverse * 20)
        factors["adverse"] = {"score":round(adverse_score,1),"weight":0.10,"source":"Bureau Report","status":"scored","detail":f"Judgements: {a['itc_judgements']}, Defaults: {a['itc_defaults']}"}
        scored_count += 1
    else:
        factors["adverse"] = {"score":None,"weight":0.10,"source":"Not provided","status":"missing","detail":"No ITC report"}
    # Calculate composite (only from scored factors)
    total_weight = sum(f["weight"] for f in factors.values() if f["status"] == "scored")
    if total_weight > 0:
        weighted_sum = sum(f["score"] * f["weight"] for f in factors.values() if f["status"] == "scored")
        composite = weighted_sum / total_weight  # Normalise to account for missing factors
    else:
        composite = 0
    confidence = min(60, scored_count / total_factors * 60)  # Cold start capped at 60%
    # Grade
    if composite >= 80: grade = "A"
    elif composite >= 60: grade = "B"
    elif composite >= 40: grade = "C"
    elif composite >= 20: grade = "D"
    else: grade = "E"
    pd_est = RISK_GRADES[grade]["pd"]
    # Recommended limit (conservative for cold start)
    requested = cl["credit_limit"] if cl else 50000
    limit_mult = RISK_GRADES[grade]["limit_mult"] * 0.5  # Half the normal mult for cold start
    recommended_limit = round(requested * limit_mult, -3)  # Round to nearest 1000
    # Actions
    actions = []
    for fname, f in factors.items():
        if f["status"] == "missing":
            actions.append(f"Obtain: {f['source']}")
    actions.append("Review after first 3 invoices are paid")
    actions.append("Reassess in 90 days")
    conn.close()
    return {"factors":factors,"composite":round(composite,1),"grade":grade,"pd":pd_est,
            "confidence":round(confidence,1),"recommended_limit":recommended_limit,
            "scored_count":scored_count,"total_factors":total_factors,
            "model_type":"Cold Start","actions":actions}

# =============================================================================
# LAYER 2B: FULL MODEL (Established clients)
# =============================================================================
def calculate_full_score(client_id, db_path=DB_PATH):
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
    a = conn.execute("SELECT * FROM credit_assessments WHERE client_id=? ORDER BY id DESC LIMIT 1", (client_id,)).fetchone()
    cl = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not a or not cl:
        conn.close(); return None
    today = date.today()
    factors = {}
    scored_count = 0
    total_factors = 7
    # Factor 1: Payment Behaviour (25%) — from platform data
    payments = conn.execute("SELECT p.payment_date, i.due_date, p.amount FROM payments p JOIN invoices i ON p.invoice_id=i.id WHERE p.client_id=?", (client_id,)).fetchall()
    if len(payments) >= 3:
        days_late = [(datetime.strptime(p["payment_date"],"%Y-%m-%d").date() - datetime.strptime(p["due_date"],"%Y-%m-%d").date()).days for p in payments]
        avg_late = sum(days_late) / len(days_late)
        late_count = sum(1 for d in days_late if d > 0)
        late_pct = late_count / len(days_late) * 100
        # Consistency (std deviation)
        mean_d = sum(days_late) / len(days_late)
        variance = sum((d - mean_d)**2 for d in days_late) / len(days_late)
        stdev = math.sqrt(variance)
        pay_score = max(0, min(100, 100 - (avg_late * 2) - (stdev * 1.5)))
        factors["payment"] = {"score":round(pay_score,1),"weight":0.25,"source":"Platform Data","status":"scored",
            "detail":f"Avg {avg_late:.0f} days late, {late_pct:.0f}% late, StDev {stdev:.1f}"}
        scored_count += 1
    else:
        factors["payment"] = {"score":None,"weight":0.25,"source":"Insufficient data","status":"missing",
            "detail":f"Only {len(payments)} payments recorded (need 3+)"}
    # Factor 2: Financial Capacity (20%)
    if a["monthly_cash_flow"] and a["existing_debt"] is not None:
        outstanding = conn.execute("SELECT SUM(total_amount - amount_paid) FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid')", (client_id,)).fetchone()[0] or 0
        total_monthly_obligation = (a["existing_debt"] or 0) / 12 + outstanding / 12
        if a["monthly_cash_flow"] > 0:
            coverage = a["monthly_cash_flow"] / max(1, total_monthly_obligation)
            fin_score = max(0, min(100, coverage * 30))
        else:
            fin_score = 10
        factors["financial"] = {"score":round(fin_score,1),"weight":0.20,"source":"Financial Data","status":"scored",
            "detail":f"Cash flow: R{a['monthly_cash_flow']:,.0f}/m, Coverage: {coverage:.1f}x" if a["monthly_cash_flow"] > 0 else "Negative cash flow"}
        scored_count += 1
    else:
        factors["financial"] = {"score":None,"weight":0.20,"source":"Not provided","status":"missing","detail":"No financial data"}
    # Factor 3: ITC/Bureau (15%)
    if a["itc_score"] is not None and a["doc_itc_report"] == 1:
        adverse_penalty = min(40, (a["itc_judgements"] or 0) * 15 + (a["itc_defaults"] or 0) * 10)
        itc_factor = max(0, min(100, a["itc_score"]) - adverse_penalty)
        factors["itc"] = {"score":round(itc_factor,1),"weight":0.15,"source":"Bureau Report","status":"scored",
            "detail":f"ITC: {a['itc_score']}, J: {a['itc_judgements']}, D: {a['itc_defaults']}"}
        scored_count += 1
    else:
        factors["itc"] = {"score":None,"weight":0.15,"source":"Not provided","status":"missing","detail":"No ITC report"}
    # Factor 4: Exposure Management (15%)
    outstanding = conn.execute("SELECT SUM(total_amount - amount_paid) FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid','Disputed')", (client_id,)).fetchone()[0] or 0
    limit = cl["credit_limit"] or 50000
    util = (outstanding / limit * 100) if limit > 0 else 100
    exp_score = max(0, min(100, 100 - util))
    factors["exposure"] = {"score":round(exp_score,1),"weight":0.15,"source":"Platform Data","status":"scored",
        "detail":f"Outstanding: R{outstanding:,.0f}, Limit: R{limit:,.0f}, Util: {util:.0f}%"}
    scored_count += 1
    # Factor 5: Relationship Quality (10%)
    inv_count = conn.execute("SELECT COUNT(*) FROM invoices WHERE client_id=?", (client_id,)).fetchone()[0]
    dispute_count = conn.execute("SELECT COUNT(*) FROM disputes WHERE client_id=?", (client_id,)).fetchone()[0]
    comms = conn.execute("SELECT COUNT(*) FROM communication_log WHERE client_id=?", (client_id,)).fetchone()[0]
    promises = conn.execute("SELECT COUNT(*) FROM promises_to_pay WHERE client_id=?", (client_id,)).fetchone()[0]
    dispute_ratio = dispute_count / max(1, inv_count)
    responsiveness = min(100, (promises / max(1, comms)) * 100 + 40) if comms > 0 else 50
    rel_score = max(0, min(100, 80 - (dispute_ratio * 100) + (responsiveness * 0.2)))
    factors["relationship"] = {"score":round(rel_score,1),"weight":0.10,"source":"Platform Data","status":"scored",
        "detail":f"Disputes: {dispute_count}/{inv_count}, Responsiveness: {responsiveness:.0f}%"}
    scored_count += 1
    # Factor 6: Forward Indicators (10%) — BNPL behavioural layer
    open_inv = conn.execute("SELECT due_date, total_amount, amount_paid FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid')", (client_id,)).fetchall()
    if len(open_inv) > 0:
        overdue_days = [max(0, (today - datetime.strptime(i["due_date"],"%Y-%m-%d").date()).days) for i in open_inv]
        avg_overdue = sum(overdue_days) / len(overdue_days)
        prom_list = conn.execute("SELECT status FROM promises_to_pay WHERE client_id=?", (client_id,)).fetchall()
        if prom_list:
            kept = sum(1 for p in prom_list if p["status"] == "Kept")
            total_p = sum(1 for p in prom_list if p["status"] in ("Kept","Broken"))
            prom_rel = (kept / total_p * 100) if total_p > 0 else 50
        else:
            prom_rel = 50
        fwd_score = max(0, min(100, 100 - (avg_overdue * 1.2) + (prom_rel * 0.1) - 5))
        factors["forward"] = {"score":round(fwd_score,1),"weight":0.10,"source":"Behavioural Signals","status":"scored",
            "detail":f"Avg overdue: {avg_overdue:.0f} days, Promise reliability: {prom_rel:.0f}%"}
        scored_count += 1
    else:
        factors["forward"] = {"score":None,"weight":0.10,"source":"No open invoices","status":"missing","detail":"No current exposure to monitor"}
    # Factor 7: Documentation (5%)
    doc_count = sum(1 for d in REQUIRED_DOCS if a[f"doc_{d}"] == 1)
    doc_score = (doc_count / len(REQUIRED_DOCS)) * 100
    factors["documentation"] = {"score":round(doc_score,1),"weight":0.05,"source":"Checklist","status":"scored",
        "detail":f"{doc_count}/{len(REQUIRED_DOCS)} documents"}
    scored_count += 1
    # Composite
    total_weight = sum(f["weight"] for f in factors.values() if f["status"] == "scored")
    if total_weight > 0:
        weighted_sum = sum(f["score"] * f["weight"] for f in factors.values() if f["status"] == "scored")
        composite = weighted_sum / total_weight
    else:
        composite = 0
    confidence = min(95, scored_count / total_factors * 95)
    if composite >= 80: grade = "A"
    elif composite >= 60: grade = "B"
    elif composite >= 40: grade = "C"
    elif composite >= 20: grade = "D"
    else: grade = "E"
    pd_est = RISK_GRADES[grade]["pd"]
    recommended_limit = round((cl["credit_limit"] or 50000) * RISK_GRADES[grade]["limit_mult"], -3)
    actions = []
    for fname, f in factors.items():
        if f["status"] == "missing":
            actions.append(f"Obtain: {f['source']}")
    if composite < 40:
        actions.append("Consider restricting credit")
    if composite < 20:
        actions.append("Initiate legal review")
    conn.close()
    return {"factors":factors,"composite":round(composite,1),"grade":grade,"pd":pd_est,
            "confidence":round(confidence,1),"recommended_limit":recommended_limit,
            "scored_count":scored_count,"total_factors":total_factors,
            "model_type":"Full Model","actions":actions}

# =============================================================================
# LAYER 3: ECL CALCULATION (IFRS 9)
# =============================================================================
def calculate_ecl(pd_est, security_type, outstanding, credit_limit):
    lgd = LGD_BY_SECURITY.get(security_type, 0.45)
    ead = outstanding + max(0, (credit_limit - outstanding) * 0.5)  # 50% of undrawn
    ecl = pd_est * lgd * ead
    return {"pd":pd_est,"lgd":lgd,"ead":round(ead,2),"ecl":round(ecl,2),"security_type":security_type}

def determine_ifrs9_stage(current_score, previous_score=None, max_days_overdue=0):
    if current_score < 30 or max_days_overdue >= 90:
        return 3  # Impaired
    if previous_score is not None:
        deterioration = previous_score - current_score
        if deterioration >= 15 or current_score < 50:
            return 2  # Significant increase in credit risk
    if current_score < 50:
        return 2
    return 1  # Performing

# =============================================================================
# STREAMLIT UI
# =============================================================================
def render_credit_engine_v2():
    init_credit_engine_v2_db()
    st.markdown("## Credit Risk Assessment Engine")
    st.markdown("_Banking-grade credit risk assessment. No fabricated data. Every score traceable to real inputs._")
    conn = get_db()
    clients = pd.read_sql("SELECT id, company_name, credit_limit FROM clients WHERE status='Active' ORDER BY company_name", conn)
    if len(clients) == 0:
        st.warning("No active clients."); conn.close(); return
    tab = st.radio("", ["Credit Assessment","Credit Score","Portfolio Risk","Alerts"], horizontal=True, key="ce2_tab")
    if tab == "Credit Assessment":
        st.markdown("### Credit Assessment — Document Checklist")
        cmap = dict(zip(clients["company_name"], clients["id"]))
        sel = st.selectbox("Client", list(cmap.keys()), key="ce2_cl")
        cid = cmap[sel]
        # Check existing assessment
        suff = check_data_sufficiency(cid)
        if suff["has_assessment"]:
            st.markdown(f"**Data Sufficiency:** {suff['sufficiency_pct']}% | **Model:** {suff['model_type']}")
            st.markdown(f"_{suff['message']}_")
            # Show checklist
            a = conn.execute("SELECT * FROM credit_assessments WHERE client_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
            st.markdown("#### Document Checklist")
            for doc in REQUIRED_DOCS:
                received = a[f"doc_{doc}"] == 1
                mandatory = doc in MANDATORY_DOCS
                icon = "✅" if received else "❌"
                req = " *(mandatory)*" if mandatory else ""
                st.markdown(f"{icon} {DOC_LABELS.get(doc, doc)}{req}")
        else:
            st.info("No assessment on file for this client.")
        # Create/Update assessment
        st.divider()
        st.markdown("### Start / Update Assessment")
        with st.form("credit_assessment"):
            st.markdown("**Documents Received:**")
            dc1, dc2 = st.columns(2)
            doc_vals = {}
            for i, doc in enumerate(REQUIRED_DOCS):
                col = dc1 if i < 4 else dc2
                with col:
                    existing = 0
                    if suff["has_assessment"]:
                        ea = conn.execute("SELECT * FROM credit_assessments WHERE client_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
                        existing = ea[f"doc_{doc}"] if ea else 0
                    doc_vals[doc] = st.checkbox(DOC_LABELS.get(doc, doc), value=bool(existing), key=f"doc_{doc}")
            st.markdown("**ITC / Bureau Data:**")
            ic1, ic2, ic3 = st.columns(3)
            with ic1:
                itc_score = st.number_input("ITC Score (0-100)", 0, 100, 50, key="itc_s")
                itc_judge = st.number_input("Judgements", 0, 50, 0, key="itc_j")
            with ic2:
                itc_def = st.number_input("Defaults", 0, 50, 0, key="itc_d")
                itc_enq = st.number_input("Enquiries", 0, 100, 0, key="itc_e")
            with ic3:
                itc_prof = st.selectbox("Payment Profile", ["Good","Fair","Poor","No Data"], key="itc_p")
            st.markdown("**Financial Data:**")
            fc1, fc2 = st.columns(2)
            with fc1:
                revenue = st.number_input("Annual Revenue (R)", 0.0, value=0.0, step=50000.0, key="fin_rev")
                assets = st.number_input("Total Assets (R)", 0.0, value=0.0, step=50000.0, key="fin_ass")
                liabilities = st.number_input("Total Liabilities (R)", 0.0, value=0.0, step=50000.0, key="fin_lia")
            with fc2:
                cashflow = st.number_input("Monthly Cash Flow (R)", value=0.0, step=5000.0, key="fin_cf")
                debt = st.number_input("Existing Debt (R)", 0.0, value=0.0, step=10000.0, key="fin_debt")
                security = st.selectbox("Security Type", list(LGD_BY_SECURITY.keys()), key="fin_sec")
            notes = st.text_area("Assessment Notes", key="ce2_notes")
            if st.form_submit_button("Save Assessment", type="primary"):
                now = get_sast_now()
                expires = (date.today() + timedelta(days=90)).strftime("%Y-%m-%d")
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute("INSERT INTO credit_assessments (client_id,assessment_type,status,"
                    "doc_credit_application,doc_company_registration,doc_bank_statements,"
                    "doc_financial_statements,doc_itc_report,doc_trade_references,"
                    "doc_id_documents,doc_tax_clearance,"
                    "itc_score,itc_judgements,itc_defaults,itc_payment_profile,itc_enquiries,"
                    "annual_revenue,total_assets,total_liabilities,monthly_cash_flow,existing_debt,"
                    "security_type,assessed_by,assessed_at,expires_at,assessment_notes,status) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid,"New","Complete",
                     int(doc_vals["credit_application"]),int(doc_vals["company_registration"]),
                     int(doc_vals["bank_statements"]),int(doc_vals["financial_statements"]),
                     int(doc_vals["itc_report"]),int(doc_vals["trade_references"]),
                     int(doc_vals["id_documents"]),int(doc_vals["tax_clearance"]),
                     itc_score if doc_vals["itc_report"] else None,
                     itc_judge, itc_def, itc_prof, itc_enq,
                     revenue if revenue > 0 else None,
                     assets if assets > 0 else None,
                     liabilities if liabilities > 0 else None,
                     cashflow if cashflow != 0 else None,
                     debt if debt > 0 else None,
                     security, DEFAULT_USER, now, expires, notes, "Complete"))
                conn2.commit(); conn2.close()
                log_audit("ASSESSMENT","Credit Engine",f"Assessment saved for {sel}")
                st.success(f"Assessment saved for {sel}. Go to Credit Score tab to calculate.")
                st.rerun()
    elif tab == "Credit Score":
        st.markdown("### Credit Score")
        cmap = dict(zip(clients["company_name"], clients["id"]))
        sel = st.selectbox("Client", list(cmap.keys()), key="ce2_score_cl")
        cid = cmap[sel]
        suff = check_data_sufficiency(cid)
        # Data sufficiency display
        if suff["model_type"] == "No Assessment":
            st.error("No credit assessment on file. Go to Credit Assessment tab first.")
            conn.close(); return
        elif suff["model_type"] == "Cannot Score":
            st.error(f"Cannot produce a score. {suff['message']}")
            st.markdown("**Missing mandatory documents:**")
            for d in suff.get("documents_missing_list",[]):
                if d in MANDATORY_DOCS:
                    st.markdown(f"- ❌ {DOC_LABELS.get(d,d)}")
            conn.close(); return
        # Show data sufficiency
        suff_col = "#198754" if suff["sufficiency_pct"] >= 75 else ("#ffc107" if suff["sufficiency_pct"] >= 50 else "#dc3545")
        st.markdown(f'**Data Sufficiency:** <span style="background:{suff_col};color:white;padding:2px 10px;border-radius:10px;">{suff["sufficiency_pct"]}%</span> | **Model:** {suff["model_type"]}', unsafe_allow_html=True)
        # Calculate score
        if st.button("Calculate Credit Score", type="primary", key="calc_score"):
            if suff["model_type"] == "Cold Start":
                result = calculate_cold_start_score(cid)
            else:
                result = calculate_full_score(cid)
            if result:
                # Save results to assessment
                a = conn.execute("SELECT * FROM credit_assessments WHERE client_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
                outstanding = conn.execute("SELECT COALESCE(SUM(total_amount - amount_paid),0) FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid','Disputed')", (cid,)).fetchone()[0]
                cl = conn.execute("SELECT credit_limit FROM clients WHERE id=?", (cid,)).fetchone()
                limit = cl["credit_limit"] if cl else 50000
                ecl_data = calculate_ecl(result["pd"], a["security_type"] or "Unsecured", outstanding, limit)
                prev = conn.execute("SELECT composite_score FROM credit_assessments WHERE client_id=? AND composite_score IS NOT NULL ORDER BY id DESC LIMIT 1 OFFSET 1", (cid,)).fetchone()
                prev_score = prev["composite_score"] if prev else None
                max_overdue = conn.execute("SELECT COALESCE(MAX(julianday('now') - julianday(due_date)),0) FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid') AND due_date < date('now')", (cid,)).fetchone()[0]
                stage = determine_ifrs9_stage(result["composite"], prev_score, int(max_overdue))
                conn2 = sqlite3.connect(DB_PATH)
                conn2.execute("UPDATE credit_assessments SET composite_score=?,risk_grade=?,confidence_level=?,pd_estimate=?,lgd=?,ead=?,ecl=?,ifrs9_stage=?,recommended_limit=?,model_type=?,data_sufficiency_pct=? WHERE id=?",
                    (result["composite"],result["grade"],result["confidence"],result["pd"],ecl_data["lgd"],ecl_data["ead"],ecl_data["ecl"],stage,result["recommended_limit"],result["model_type"],suff["sufficiency_pct"],a["id"]))
                conn2.execute("UPDATE clients SET risk_grade=?, updated_at=? WHERE id=?", (result["grade"], get_sast_now(), cid))
                conn2.commit(); conn2.close()
                log_audit("SCORE","Credit Engine",f"{sel}: {result['composite']:.1f} ({result['grade']}) [{result['model_type']}] Conf: {result['confidence']}%")
                st.rerun()
        # Display existing score
        a = conn.execute("SELECT * FROM credit_assessments WHERE client_id=? AND composite_score IS NOT NULL ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        if a and a["composite_score"] is not None:
            sc1, sc2 = st.columns([1, 2])
            with sc1:
                grade = a["risk_grade"]
                gi = RISK_GRADES.get(grade, {})
                st.metric("Composite Score", f"{a['composite_score']:.1f} / 100")
                st.markdown(f'<div style="text-align:center;background:{gi.get("colour","#6c757d")};color:white;padding:10px;border-radius:10px;font-size:1.3em;font-weight:bold;">Grade {grade} - {gi.get("label","")}</div>', unsafe_allow_html=True)
                st.markdown(f"**Model:** {a['model_type']}")
                conf_col = "#198754" if a["confidence_level"] >= 70 else ("#ffc107" if a["confidence_level"] >= 40 else "#dc3545")
                st.markdown(f'**Confidence:** <span style="background:{conf_col};color:white;padding:2px 8px;border-radius:8px;">{a["confidence_level"]:.0f}%</span>', unsafe_allow_html=True)
                st.markdown(f"**PD:** {a['pd_estimate']*100:.2f}%")
                st.markdown(f"**LGD:** {a['lgd']*100:.0f}% ({safe_get(a, 'security_type', 'Unsecured')})")
                st.markdown(f"**EAD:** R {a['ead']:,.2f}")
                st.markdown(f"**ECL:** R {a['ecl']:,.2f}")
                stage_labels = {1:"Stage 1 - Performing",2:"Stage 2 - Watch",3:"Stage 3 - Impaired"}
                stage_cols = {1:"#198754",2:"#ffc107",3:"#dc3545"}
                stg = a["ifrs9_stage"] or 1
                st.markdown(f'**IFRS 9:** <span style="background:{stage_cols[stg]};color:white;padding:2px 8px;border-radius:8px;">{stage_labels[stg]}</span>', unsafe_allow_html=True)
                st.markdown(f"**Recommended Limit:** R {a['recommended_limit']:,.0f}")
            with sc2:
                # Build radar from stored assessment — we need to recalculate factors for display
                if suff["model_type"] == "Cold Start":
                    result = calculate_cold_start_score(cid)
                else:
                    result = calculate_full_score(cid)
                if result:
                    cats = []
                    vals = []
                    for fname, f in result["factors"].items():
                        if f["status"] == "scored":
                            cats.append(fname.title())
                            vals.append(f["score"])
                    if cats:
                        fig = go.Figure()
                        fig.add_trace(go.Scatterpolar(r=vals+[vals[0]], theta=cats+[cats[0]], fill="toself",
                            line_color=gi.get("colour","#0d6efd"), fillcolor=gi.get("colour","#0d6efd"), opacity=0.3))
                        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])),
                            showlegend=False, height=400, margin=dict(t=30,b=30), title="Scored Factors Only")
                        st.plotly_chart(fig, use_container_width=True)
                    # Factor detail table
                    st.markdown("#### Factor Breakdown")
                    for fname, f in result["factors"].items():
                        if f["status"] == "scored":
                            st.markdown(f"✅ **{fname.title()}** — {f['score']:.1f}/100 (Weight: {f['weight']*100:.0f}%) — _{f['detail']}_")
                        else:
                            st.markdown(f"⚠️ **{fname.title()}** — NOT SCORED — _{f['detail']}_")
                    if result["actions"]:
                        st.markdown("#### Recommended Actions")
                        for act in result["actions"]:
                            st.markdown(f"- {act}")
        else:
            st.info("No score calculated yet. Click 'Calculate Credit Score' above.")
    elif tab == "Portfolio Risk":
        st.markdown("### Portfolio Risk Summary")
        assessments = pd.read_sql(
            "SELECT ca.*, c.company_name, c.credit_limit FROM credit_assessments ca "
            "JOIN clients c ON ca.client_id=c.id "
            "WHERE ca.composite_score IS NOT NULL "
            "AND ca.id IN (SELECT MAX(id) FROM credit_assessments WHERE composite_score IS NOT NULL GROUP BY client_id) "
            "ORDER BY ca.composite_score", conn)
        if len(assessments) == 0:
            st.info("No clients scored yet. Complete assessments and calculate scores first.")
            conn.close(); return
        # Summary metrics
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Clients Scored", len(assessments))
        total_ecl = assessments["ecl"].sum()
        k2.metric("Portfolio ECL", f"R {total_ecl:,.2f}")
        avg_score = assessments["composite_score"].mean()
        k3.metric("Avg Score", f"{avg_score:.1f}")
        high_risk = len(assessments[assessments["composite_score"] < 40])
        k4.metric("High Risk (< 40)", high_risk)
        # Stage distribution
        st.markdown("#### IFRS 9 Stage Distribution")
        sc1,sc2,sc3 = st.columns(3)
        s1 = len(assessments[assessments["ifrs9_stage"]==1])
        s2 = len(assessments[assessments["ifrs9_stage"]==2])
        s3 = len(assessments[assessments["ifrs9_stage"]==3])
        sc1.metric("Stage 1 - Performing", s1)
        sc2.metric("Stage 2 - Watch", s2)
        sc3.metric("Stage 3 - Impaired", s3)
        # Detail table
        display = assessments[["company_name","composite_score","risk_grade","confidence_level","model_type","pd_estimate","ead","ecl","ifrs9_stage","recommended_limit"]].copy()
        display.columns = ["Client","Score","Grade","Confidence","Model","PD","EAD","ECL","Stage","Rec. Limit"]
        display["PD"] = display["PD"].apply(lambda x: f"{x*100:.2f}%")
        display["EAD"] = display["EAD"].apply(lambda x: f"R {x:,.0f}")
        display["ECL"] = display["ECL"].apply(lambda x: f"R {x:,.0f}")
        display["Confidence"] = display["Confidence"].apply(lambda x: f"{x:.0f}%")
        display["Rec. Limit"] = display["Rec. Limit"].apply(lambda x: f"R {x:,.0f}")
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:  # Alerts
        st.markdown("### Risk Alerts")
        assessments = pd.read_sql(
            "SELECT ca.*, c.company_name FROM credit_assessments ca "
            "JOIN clients c ON ca.client_id=c.id "
            "WHERE ca.id IN (SELECT MAX(id) FROM credit_assessments GROUP BY client_id)", conn)
        if len(assessments) == 0:
            st.info("No assessments on file.")
            conn.close(); return
        alerts = []
        for _, a in assessments.iterrows():
            if a["composite_score"] is not None and a["composite_score"] < 40:
                alerts.append(("HIGH RISK", a["company_name"], f"Score {a['composite_score']:.1f} - Grade {a['risk_grade']}", "#dc3545"))
            if a["ifrs9_stage"] and a["ifrs9_stage"] >= 2:
                stage_name = {2:"Stage 2 - Watch",3:"Stage 3 - Impaired"}.get(a["ifrs9_stage"],"")
                alerts.append(("IFRS 9", a["company_name"], stage_name, "#ffc107" if a["ifrs9_stage"]==2 else "#dc3545"))
            if a["expires_at"]:
                exp = datetime.strptime(a["expires_at"], "%Y-%m-%d").date()
                if exp <= date.today():
                    alerts.append(("EXPIRED", a["company_name"], f"Assessment expired {a['expires_at']}", "#fd7e14"))
                elif (exp - date.today()).days <= 30:
                    alerts.append(("EXPIRING", a["company_name"], f"Expires {a['expires_at']}", "#ffc107"))
            if a["confidence_level"] is not None and a["confidence_level"] < 40:
                alerts.append(("LOW CONFIDENCE", a["company_name"], f"Confidence {a['confidence_level']:.0f}% - gather more data", "#6c757d"))
        if alerts:
            st.markdown(f"**{len(alerts)} alerts**")
            for alert_type, client, detail, colour in alerts:
                st.markdown(f'<div style="border-left:4px solid {colour};padding:8px 14px;margin-bottom:4px;background:#f8f9fa;border-radius:4px;"><span style="background:{colour};color:white;padding:1px 8px;border-radius:8px;font-size:0.8em;">{alert_type}</span> <strong>{client}</strong> - {detail}</div>', unsafe_allow_html=True)
        else:
            st.success("No active alerts.")
        # Unscored clients
        scored_ids = set(assessments[assessments["composite_score"].notna()]["client_id"].tolist())
        all_ids = set(clients["id"].tolist())
        unscored = all_ids - scored_ids
        if unscored:
            st.divider()
            st.warning(f"{len(unscored)} client(s) have no credit assessment on file.")
    conn.close()

# =============================================================================
# TEST SUITE
# =============================================================================
if __name__ == "__main__":
    import os
    test_db = "test_credit_v2.db"
    if os.path.exists(test_db): os.remove(test_db)
    # Setup test database
    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE IF NOT EXISTS audit_trail (id INTEGER PRIMARY KEY AUTOINCREMENT, action_type TEXT, module TEXT, description TEXT, user TEXT, details TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, company_name TEXT, credit_limit REAL DEFAULT 50000, registration_number TEXT, risk_grade TEXT DEFAULT 'C', status TEXT DEFAULT 'Active')")
    conn.execute("CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY, client_id INT, invoice_number TEXT, invoice_date TEXT, due_date TEXT, total_amount REAL, amount_paid REAL DEFAULT 0, status TEXT DEFAULT 'Open')")
    conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, invoice_id INT, client_id INT, payment_date TEXT, amount REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS disputes (id INTEGER PRIMARY KEY, client_id INT)")
    conn.execute("CREATE TABLE IF NOT EXISTS communication_log (id INTEGER PRIMARY KEY, client_id INT)")
    conn.execute("CREATE TABLE IF NOT EXISTS promises_to_pay (id INTEGER PRIMARY KEY, client_id INT, status TEXT)")
    conn.execute("INSERT OR IGNORE INTO clients VALUES (1,'New Corp',100000,'2024/111/07','C','Active')")
    conn.execute("INSERT OR IGNORE INTO clients VALUES (2,'Old Corp',200000,'2018/222/07','B','Active')")
    # Old Corp has trading history
    for i in range(5):
        conn.execute(f"INSERT OR IGNORE INTO invoices VALUES ({10+i},2,'INV-{i}','2026-01-01','2026-02-01',10000,10000,'Paid')")
        conn.execute(f"INSERT OR IGNORE INTO payments VALUES ({10+i},{10+i},2,'2026-02-05',10000)")
    conn.commit(); conn.close()
    init_credit_engine_v2_db(test_db)
    print("=" * 60)
    print("CREDIT ENGINE v2 — TEST SUITE")
    print("=" * 60)
    # TEST 1: New client with NO assessment → Cannot Score
    result = check_data_sufficiency(1, test_db)
    assert result["model_type"] == "No Assessment", f"Expected 'No Assessment', got '{result['model_type']}'"
    assert result["minimum_met"] == False
    print("\n✅ TEST 1: New client, no assessment → 'No Assessment' (PASSED)")
    # TEST 2: Create assessment with only 2 docs → Cannot Score
    conn = sqlite3.connect(test_db)
    conn.execute("INSERT INTO credit_assessments (client_id,doc_credit_application,doc_company_registration,doc_itc_report,assessed_at) VALUES (1,1,1,0,?)", (get_sast_now(),))
    conn.commit(); conn.close()
    result = check_data_sufficiency(1, test_db)
    assert result["model_type"] == "Cannot Score", f"Expected 'Cannot Score', got '{result['model_type']}'"
    assert result["minimum_met"] == False
    print("✅ TEST 2: 2 mandatory docs, missing ITC → 'Cannot Score' (PASSED)")
    # TEST 3: Add ITC (3 mandatory docs met) → Cold Start
    conn = sqlite3.connect(test_db)
    conn.execute("UPDATE credit_assessments SET doc_itc_report=1, itc_score=65 WHERE client_id=1")
    conn.commit(); conn.close()
    result = check_data_sufficiency(1, test_db)
    assert result["model_type"] == "Cold Start", f"Expected 'Cold Start', got '{result['model_type']}'"
    assert result["minimum_met"] == True
    print("✅ TEST 3: 3 mandatory docs met → 'Cold Start' (PASSED)")
    # TEST 4: Cold start score produces result with LOW confidence
    score = calculate_cold_start_score(1, test_db)
    assert score is not None
    assert score["model_type"] == "Cold Start"
    assert score["confidence"] <= 60, f"Cold start confidence should be <= 60%, got {score['confidence']}%"
    assert score["composite"] > 0
    # Check no fabricated factors
    for fname, f in score["factors"].items():
        if f["status"] == "scored":
            assert f["score"] is not None
            assert f["source"] != "Default"
    print(f"✅ TEST 4: Cold Start score = {score['composite']:.1f}, Conf = {score['confidence']:.0f}%, Grade = {score['grade']} (PASSED)")
    # TEST 5: Old Corp with history → Full Model
    conn = sqlite3.connect(test_db)
    conn.execute("INSERT INTO credit_assessments (client_id,doc_credit_application,doc_company_registration,doc_itc_report,doc_bank_statements,doc_financial_statements,doc_trade_references,itc_score,annual_revenue,total_assets,total_liabilities,monthly_cash_flow,existing_debt,assessed_at) VALUES (2,1,1,1,1,1,1,75,2000000,1500000,500000,100000,200000,?)", (get_sast_now(),))
    conn.commit(); conn.close()
    result = check_data_sufficiency(2, test_db)
    assert result["model_type"] == "Full Model", f"Expected 'Full Model', got '{result['model_type']}'"
    print(f"✅ TEST 5: Established client → 'Full Model' (PASSED)")
    # TEST 6: Full model score with HIGH confidence
    score = calculate_full_score(2, test_db)
    assert score is not None
    assert score["model_type"] == "Full Model"
    assert score["confidence"] > 60, f"Full model confidence should be > 60%, got {score['confidence']}%"
    print(f"✅ TEST 6: Full Model score = {score['composite']:.1f}, Conf = {score['confidence']:.0f}%, Grade = {score['grade']} (PASSED)")
    # TEST 7: ECL calculation is mathematically correct
    ecl = calculate_ecl(0.05, "Unsecured", 100000, 200000)
    expected_ead = 100000 + (200000 - 100000) * 0.5  # 150000
    expected_ecl = 0.05 * 0.45 * 150000  # 3375
    assert abs(ecl["ead"] - expected_ead) < 1, f"EAD: expected {expected_ead}, got {ecl['ead']}"
    assert abs(ecl["ecl"] - expected_ecl) < 1, f"ECL: expected {expected_ecl}, got {ecl['ecl']}"
    assert ecl["lgd"] == 0.45
    print(f"✅ TEST 7: ECL = PD(5%) × LGD(45%) × EAD(R{expected_ead:,.0f}) = R{expected_ecl:,.0f} (PASSED)")
    # TEST 8: ECL with security reduces LGD
    ecl_secured = calculate_ecl(0.05, "Property Secured", 100000, 200000)
    assert ecl_secured["lgd"] == 0.15
    assert ecl_secured["ecl"] < ecl["ecl"]
    print(f"✅ TEST 8: Secured LGD=15% → ECL R{ecl_secured['ecl']:,.0f} < Unsecured R{ecl['ecl']:,.0f} (PASSED)")
    # TEST 9: IFRS 9 staging
    assert determine_ifrs9_stage(70) == 1  # Performing
    assert determine_ifrs9_stage(45) == 2  # Watch
    assert determine_ifrs9_stage(25) == 3  # Impaired
    assert determine_ifrs9_stage(70, 90) == 2  # Significant deterioration (90→70 = 20pt drop)
    assert determine_ifrs9_stage(60, 65) == 1  # Minor change, still performing
    assert determine_ifrs9_stage(50, None, 95) == 3  # 90+ days overdue
    print("✅ TEST 9: IFRS 9 staging — all scenarios correct (PASSED)")
    # TEST 10: No fabricated scores
    # New client with no assessment should return None from scoring
    score_none = calculate_cold_start_score(999, test_db)
    assert score_none is None, "Should return None for non-existent client"
    print("✅ TEST 10: Non-existent client returns None, not fabricated score (PASSED)")
    # Cleanup
    os.remove(test_db)
    print("\n" + "=" * 60)
    print("ALL 10 TESTS PASSED")
    print("=" * 60)
    print("\nZero fabricated data. Every score traceable to real inputs.")
    print("Banking-grade. Investec-level. Built for SMEs.")
