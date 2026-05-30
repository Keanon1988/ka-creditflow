"""
KA CreditFlow v6.0 - POPIA Compliance & Predictive Risk Engine
"""
import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timezone, timedelta, date
import math

SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"
RISK_GRADE_MAP = {"A":{"pd_base":0.005},"B":{"pd_base":0.02},"C":{"pd_base":0.05},"D":{"pd_base":0.15},"E":{"pd_base":0.35}}
CONSENT_TYPES = ["Marketing","Data Processing","Credit Check","Third Party Sharing","Data Retention"]

def get_sast_now():
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")
def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn
def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()))
    conn.commit(); conn.close()

def init_popia_predictive_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS popia_consent (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL,
        consent_type TEXT NOT NULL, consent_given INTEGER DEFAULT 1,
        consent_date TEXT, consent_method TEXT DEFAULT 'Digital',
        withdrawn_date TEXT, notes TEXT, recorded_by TEXT, recorded_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS popia_data_retention (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data_type TEXT NOT NULL,
        retention_period_months INTEGER NOT NULL, legal_basis TEXT,
        review_date TEXT, last_purge_date TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS predictive_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, scored_at TEXT,
        payment_velocity_score REAL, payment_consistency_score REAL,
        exposure_trend_score REAL, dispute_frequency_score REAL,
        communication_responsiveness REAL, promise_reliability_score REAL,
        aging_trajectory_score REAL, composite_score REAL,
        forward_pd_90day REAL, forward_pd_180day REAL,
        risk_direction TEXT, recommended_action TEXT,
        confidence_level REAL, scored_by TEXT)""")
    c.execute("SELECT COUNT(*) FROM popia_data_retention")
    if c.fetchone()[0] == 0:
        policies = [("Client info",60,"NCA","2027-01-01",None),("Invoices/payments",60,"Companies Act","2027-01-01",None),
            ("Comms logs",36,"NCA","2027-01-01",None),("Credit scores",36,"Interest","2027-01-01",None),
            ("Audit trail",84,"Regulatory","2027-01-01",None),("Marketing consent",24,"POPIA","2027-01-01",None)]
        c.executemany("INSERT INTO popia_data_retention (data_type,retention_period_months,legal_basis,review_date,last_purge_date) VALUES (?,?,?,?,?)", policies)
    conn.commit(); conn.close()

def check_consent(client_id, consent_type, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT * FROM popia_consent WHERE client_id=? AND consent_type=? AND consent_given=1 AND withdrawn_date IS NULL ORDER BY id DESC LIMIT 1", (client_id, consent_type)).fetchone()
    conn.close(); return row is not None

def record_consent(client_id, consent_type, method="Digital", given=True, user=DEFAULT_USER, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO popia_consent (client_id,consent_type,consent_given,consent_date,consent_method,recorded_by,recorded_at) VALUES (?,?,?,?,?,?,?)",
        (client_id, consent_type, 1 if given else 0, str(date.today()), method, user, get_sast_now()))
    conn.commit(); conn.close()

def withdraw_consent(client_id, consent_type, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE popia_consent SET withdrawn_date=? WHERE client_id=? AND consent_type=? AND consent_given=1 AND withdrawn_date IS NULL",
        (get_sast_now(), client_id, consent_type))
    conn.commit(); conn.close()

def calculate_predictive_score(client_id, db_path=DB_PATH):
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row; today = date.today()
    payments = conn.execute("SELECT p.payment_date, i.due_date FROM payments p JOIN invoices i ON p.invoice_id=i.id WHERE p.client_id=?", (client_id,)).fetchall()
    if payments:
        dl = [(datetime.strptime(p["payment_date"],"%Y-%m-%d").date()-datetime.strptime(p["due_date"],"%Y-%m-%d").date()).days for p in payments]
        avg_late = sum(dl)/len(dl)
        velocity = max(0,min(100,100-(avg_late*3)))
        if len(dl)>1:
            m = sum(dl)/len(dl); v = sum((d-m)**2 for d in dl)/len(dl)
            consistency = max(0,min(100,100-(math.sqrt(v)*5)))
        else: consistency = 50
    else: velocity = 30; consistency = 30
    invs = conn.execute("SELECT total_amount, amount_paid FROM invoices WHERE client_id=?", (client_id,)).fetchall()
    outstanding = sum(max(0,i["total_amount"]-i["amount_paid"]) for i in invs)
    cl = conn.execute("SELECT credit_limit FROM clients WHERE id=?", (client_id,)).fetchone()
    limit = cl["credit_limit"] if cl else 50000
    util = (outstanding/limit*100) if limit>0 else 100
    exposure = max(0,min(100,100-util))
    ti = max(1,len(invs))
    dc = conn.execute("SELECT COUNT(*) FROM disputes WHERE client_id=?", (client_id,)).fetchone()[0]
    dispute = max(0,min(100,100-(dc/ti*200)))
    comms = conn.execute("SELECT COUNT(*) FROM communication_log WHERE client_id=?", (client_id,)).fetchone()[0]
    proms = conn.execute("SELECT COUNT(*) FROM promises_to_pay WHERE client_id=?", (client_id,)).fetchone()[0]
    responsiveness = min(100,(proms/comms*100+40)) if comms>0 else 50
    pl = conn.execute("SELECT status FROM promises_to_pay WHERE client_id=?", (client_id,)).fetchall()
    if pl:
        kept = sum(1 for p in pl if p["status"]=="Kept")
        broken = sum(1 for p in pl if p["status"]=="Broken")
        tp = kept+broken; promise = (kept/tp*100) if tp>0 else 50
    else: promise = 50
    oi = conn.execute("SELECT due_date FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid')", (client_id,)).fetchall()
    if oi:
        od = [max(0,(today-datetime.strptime(i["due_date"],"%Y-%m-%d").date()).days) for i in oi]
        trajectory = max(0,min(100,100-(sum(od)/len(od)*1.2)))
    else: trajectory = 80
    composite = velocity*0.25+consistency*0.15+exposure*0.20+dispute*0.10+responsiveness*0.10+promise*0.10+trajectory*0.10
    if composite>=80: grade="A"
    elif composite>=60: grade="B"
    elif composite>=40: grade="C"
    elif composite>=20: grade="D"
    else: grade="E"
    base = RISK_GRADE_MAP[grade]["pd_base"]
    mult = (100-composite)/50
    pd90 = min(0.99,base*mult); pd180 = min(0.99,pd90*1.8)
    prev = conn.execute("SELECT composite_score FROM predictive_scores WHERE client_id=? ORDER BY id DESC LIMIT 1", (client_id,)).fetchone()
    if prev:
        delta = composite-prev["composite_score"]
        direction = "Improving" if delta>5 else ("Deteriorating" if delta<-5 else "Stable")
    else: direction = "New"
    if composite>=80: action="Hold"
    elif composite>=60: action="Monitor"
    elif composite>=40: action="Restrict"
    elif composite>=20: action="Suspend"
    else: action="Legal"
    dp = len(payments or [])+comms+len(pl or [])+len(invs or [])
    confidence = min(95,max(20,dp*5))
    result = {"velocity":round(velocity,1),"consistency":round(consistency,1),"exposure":round(exposure,1),"dispute":round(dispute,1),"responsiveness":round(responsiveness,1),"promise":round(promise,1),"trajectory":round(trajectory,1),"composite":round(composite,1),"forward_pd_90":round(pd90,4),"forward_pd_180":round(pd180,4),"direction":direction,"action":action,"confidence":round(confidence,1)}
    conn2 = sqlite3.connect(db_path)
    conn2.execute("INSERT INTO predictive_scores (client_id,scored_at,payment_velocity_score,payment_consistency_score,exposure_trend_score,dispute_frequency_score,communication_responsiveness,promise_reliability_score,aging_trajectory_score,composite_score,forward_pd_90day,forward_pd_180day,risk_direction,recommended_action,confidence_level,scored_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (client_id,get_sast_now(),result["velocity"],result["consistency"],result["exposure"],result["dispute"],result["responsiveness"],result["promise"],result["trajectory"],result["composite"],result["forward_pd_90"],result["forward_pd_180"],result["direction"],result["action"],result["confidence"],DEFAULT_USER))
    conn2.commit(); conn2.close(); conn.close()
    return result

def render_popia_compliance():
    init_popia_predictive_db()
    st.markdown("## POPIA Compliance")
    tab = st.radio("", ["Consent Register","Data Retention","Compliance Audit"], horizontal=True, key="popia_tab")
    conn = get_db()
    if tab == "Consent Register":
        clients = pd.read_sql("SELECT id, company_name FROM clients ORDER BY company_name", conn)
        if len(clients)==0: conn.close(); return
        cmap = dict(zip(clients["company_name"], clients["id"]))
        sel = st.selectbox("Client", list(cmap.keys()), key="pcl")
        cid = cmap[sel]
        for ct in CONSENT_TYPES:
            has = check_consent(cid, ct)
            st.markdown(f"{'✅' if has else '❌'} **{ct}**")
        with st.form("rec_consent"):
            ctype = st.selectbox("Type", CONSENT_TYPES, key="rct")
            cmeth = st.selectbox("Method", ["Written","Digital","Verbal"], key="rcm")
            if st.form_submit_button("Record Consent", type="primary"):
                record_consent(cid, ctype, cmeth)
                log_audit("POPIA","POPIA",f"Consent: {ctype} for {sel}")
                st.success(f"Consent recorded."); st.rerun()
    elif tab == "Data Retention":
        policies = pd.read_sql("SELECT * FROM popia_data_retention", conn)
        if len(policies)>0: st.dataframe(policies[["data_type","retention_period_months","legal_basis","review_date"]], use_container_width=True, hide_index=True)
    else:
        clients = pd.read_sql("SELECT id, company_name FROM clients", conn)
        total = len(clients)
        consented = sum(1 for _, cl in clients.iterrows() if check_consent(cl["id"], "Data Processing"))
        k1,k2,k3 = st.columns(3)
        k1.metric("Total Clients", total)
        k2.metric("With Consent", consented)
        k3.metric("Rate", f"{consented/total*100:.0f}%" if total>0 else "0%")
    conn.close()

def render_predictive_engine():
    init_popia_predictive_db()
    st.markdown("## Predictive Risk Engine")
    st.markdown("_Forward-looking behavioural scoring. No credit bureau needed._")
    conn = get_db()
    clients = pd.read_sql("SELECT id, company_name FROM clients WHERE status='Active' ORDER BY company_name", conn)
    if len(clients)==0: conn.close(); return
    tab = st.radio("", ["Client Scoring","Portfolio Heat Map"], horizontal=True, key="pred_tab")
    if tab == "Client Scoring":
        cmap = dict(zip(clients["company_name"], clients["id"]))
        sel = st.selectbox("Client", list(cmap.keys()), key="pcl2")
        cid = cmap[sel]
        ex = conn.execute("SELECT * FROM predictive_scores WHERE client_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        if ex:
            s1,s2 = st.columns([1,2])
            with s1:
                acols = {"Hold":"#198754","Monitor":"#0d6efd","Restrict":"#ffc107","Suspend":"#fd7e14","Legal":"#dc3545"}
                ac = acols.get(ex["recommended_action"],"#6c757d")
                st.metric("Score", f"{ex['composite_score']:.1f}/100")
                st.markdown(f'<div style="text-align:center;background:{ac};color:white;padding:10px;border-radius:10px;font-size:1.3em;font-weight:bold;">{ex["recommended_action"]}</div>', unsafe_allow_html=True)
                st.markdown(f"**90-Day PD:** {ex['forward_pd_90day']*100:.2f}%")
                st.markdown(f"**180-Day PD:** {ex['forward_pd_180day']*100:.2f}%")
                st.markdown(f"**Direction:** {ex['risk_direction']}")
                st.markdown(f"**Confidence:** {ex['confidence_level']:.0f}%")
            with s2:
                cats = ["Pay Velocity","Consistency","Exposure","Disputes","Comm Response","Promises","Aging"]
                vals = [ex["payment_velocity_score"],ex["payment_consistency_score"],ex["exposure_trend_score"],ex["dispute_frequency_score"],ex["communication_responsiveness"],ex["promise_reliability_score"],ex["aging_trajectory_score"]]
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(r=vals+[vals[0]], theta=cats+[cats[0]], fill="toself", line_color=ac, fillcolor=ac, opacity=0.3))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])), showlegend=False, height=400, margin=dict(t=30,b=30), title="Behavioural Risk Profile")
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("No score yet.")
        st.divider()
        if st.button("Calculate Predictive Score", type="primary", key="cpred"):
            r = calculate_predictive_score(cid)
            log_audit("PREDICTIVE","Predictive",f"{sel}: {r['composite']:.1f}, PD90={r['forward_pd_90']*100:.2f}%")
            st.success(f"{sel} — Score: {r['composite']:.1f} | PD 90d: {r['forward_pd_90']*100:.2f}% | Action: {r['action']}")
            st.rerun()
    else:
        st.markdown("### Portfolio Heat Map")
        scores = pd.read_sql("SELECT ps.*, c.company_name FROM predictive_scores ps JOIN clients c ON ps.client_id=c.id INNER JOIN (SELECT client_id, MAX(id) as max_id FROM predictive_scores GROUP BY client_id) latest ON ps.id=latest.max_id ORDER BY ps.composite_score", conn)
        if len(scores)==0: st.info("No scores yet."); conn.close(); return
        d = scores[["company_name","composite_score","forward_pd_90day","forward_pd_180day","risk_direction","recommended_action","confidence_level"]].copy()
        d.columns = ["Client","Score","PD 90d","PD 180d","Direction","Action","Confidence"]
        d["PD 90d"] = d["PD 90d"].apply(lambda x: f"{x*100:.2f}%")
        d["PD 180d"] = d["PD 180d"].apply(lambda x: f"{x*100:.2f}%")
        d["Confidence"] = d["Confidence"].apply(lambda x: f"{x:.0f}%")
        st.dataframe(d, use_container_width=True, hide_index=True)
        fig = px.bar(scores, x="company_name", y="composite_score", color="recommended_action",
            color_discrete_map={"Hold":"#198754","Monitor":"#0d6efd","Restrict":"#ffc107","Suspend":"#fd7e14","Legal":"#dc3545"},
            text_auto=".0f", labels={"company_name":"Client","composite_score":"Score"})
        fig.update_layout(height=400, margin=dict(t=20,b=20))
        st.plotly_chart(fig, use_container_width=True)
    conn.close()
