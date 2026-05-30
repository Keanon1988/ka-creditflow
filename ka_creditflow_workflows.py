"""
KA CreditFlow v6.0b - Automated Workflow Engine
"""
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta, date

SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"
SA_HOLIDAYS_2026 = [date(2026,1,1),date(2026,3,21),date(2026,4,3),date(2026,4,6),date(2026,4,27),date(2026,5,1),date(2026,6,16),date(2026,8,9),date(2026,8,10),date(2026,9,24),date(2026,12,16),date(2026,12,25),date(2026,12,26)]

def get_sast_now():
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")
def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn
def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()))
    conn.commit(); conn.close()
def is_nca_compliant():
    now = datetime.now(SAST)
    if now.date() in SA_HOLIDAYS_2026: return False
    if now.weekday() >= 5: return False
    if now.hour < 8 or now.hour >= 20: return False
    return True

CHANNEL_ICONS = {"SMS":"\U0001f4f1","Email":"\U0001f4e7","WhatsApp":"\U0001f4ac","Call":"\U0001f4de","S129Notice":"\u2696\ufe0f","LOD":"\U0001f4dc","Escalate":"\U0001f6a8","Note":"\U0001f4dd"}
ESC_COLOURS = {"Friendly":"#198754","Formal":"#ffc107","Urgent":"#fd7e14","Final":"#dc3545","Legal":"#842029"}

def init_workflows_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS workflow_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT,
        industry_type TEXT DEFAULT 'B2B', total_steps INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1, created_by TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS workflow_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, template_id INTEGER NOT NULL,
        step_order INTEGER NOT NULL, days_from_due INTEGER NOT NULL,
        action_type TEXT NOT NULL, channel TEXT, subject TEXT, template_text TEXT,
        escalation_level TEXT DEFAULT 'Friendly', auto_execute INTEGER DEFAULT 1,
        requires_approval INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS workflow_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL,
        invoice_id INTEGER, template_id INTEGER NOT NULL, status TEXT DEFAULT 'Active',
        current_step INTEGER DEFAULT 0, started_at TEXT, last_executed_step INTEGER DEFAULT 0,
        last_executed_at TEXT, next_execution_date TEXT, completed_at TEXT,
        assigned_by TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS workflow_execution_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, assignment_id INTEGER NOT NULL,
        step_id INTEGER, executed_at TEXT, channel TEXT, action_type TEXT,
        status TEXT DEFAULT 'Success', message_sent TEXT, recipient TEXT, notes TEXT)""")
    c.execute("SELECT COUNT(*) FROM workflow_templates")
    if c.fetchone()[0] == 0:
        now = get_sast_now()
        c.execute("INSERT INTO workflow_templates (name,description,industry_type,total_steps,created_by,created_at) VALUES (?,?,?,?,?,?)",
            ("Standard B2B Collection","Full 7-step escalation from pre-due to legal.","B2B",7,DEFAULT_USER,now))
        t1 = c.lastrowid
        s1 = [
            (t1,1,-7,"SMS","SMS","Payment Reminder","Dear {client}, invoice {ref} for {amount} is due on {due_date}. Please arrange payment. - KA Legacy","Friendly",1,0),
            (t1,2,1,"Email","Email","Overdue Notice - {ref}","Dear {client}, invoice {ref} for {amount} was due on {due_date} and is now overdue. Please arrange payment. Regards, KA Legacy","Friendly",1,0),
            (t1,3,14,"SMS","SMS","14-Day Overdue","{client}: Invoice {ref} ({amount}) is 14 days overdue. Immediate payment required. - KA Legacy","Formal",1,0),
            (t1,4,30,"Email","Email","30-Day Formal Notice","Dear {client}, invoice {ref} for {amount} is now 30 days past due. Please arrange payment or contact us. Regards, KA Legacy","Formal",1,0),
            (t1,5,60,"WhatsApp","WhatsApp","60-Day Final Warning","URGENT: {client}, invoice {ref} for {amount} is 60 days overdue. Final warning before legal escalation. - KA Legacy","Urgent",1,0),
            (t1,6,75,"S129Notice","Email","Section 129 NCA Notice","Section 129(1)(a) notice for {client} - {ref} ({amount}). Consumer in default 75+ days.","Final",0,1),
            (t1,7,90,"LOD","Email","Letter of Demand / Attorney Referral","Letter of Demand for {client} - {ref} ({amount}). Refer to attorney if no response.","Legal",0,1),
        ]
        c.executemany("INSERT INTO workflow_steps (template_id,step_order,days_from_due,action_type,channel,subject,template_text,escalation_level,auto_execute,requires_approval) VALUES (?,?,?,?,?,?,?,?,?,?)", s1)
        c.execute("INSERT INTO workflow_templates (name,description,industry_type,total_steps,created_by,created_at) VALUES (?,?,?,?,?,?)",
            ("Property Levy Collection","6-step sequence for body corporate levies.","Property",6,DEFAULT_USER,now))
        t2 = c.lastrowid
        s2 = [
            (t2,1,1,"SMS","SMS","Levy Reminder","{client}: Levy of {amount} was due {due_date}. Please pay. - KA Legacy","Friendly",1,0),
            (t2,2,7,"Email","Email","7-Day Overdue","Dear {client}, your account is 7 days overdue ({amount}). Please settle. Regards, KA Legacy","Friendly",1,0),
            (t2,3,30,"Email","Email","30-Day Formal","Dear {client}, your account of {amount} is 30 days overdue. Immediate payment required. Regards, KA Legacy","Formal",1,0),
            (t2,4,60,"WhatsApp","WhatsApp","60-Day Final","FINAL DEMAND: {client}, {amount} is 60 days overdue. Legal action will follow. - KA Legacy","Final",1,0),
            (t2,5,75,"S129Notice","Email","Section 129","S129 notice for {client} - {amount}.","Final",0,1),
            (t2,6,90,"Escalate","Email","Legal Escalation","Escalate {client} ({amount}) to legal.","Legal",0,1),
        ]
        c.executemany("INSERT INTO workflow_steps (template_id,step_order,days_from_due,action_type,channel,subject,template_text,escalation_level,auto_execute,requires_approval) VALUES (?,?,?,?,?,?,?,?,?,?)", s2)
        c.execute("INSERT INTO workflow_templates (name,description,industry_type,total_steps,created_by,created_at) VALUES (?,?,?,?,?,?)",
            ("Gentle Reminder - Low Risk","3-step soft touch for reliable clients.","B2B",3,DEFAULT_USER,now))
        t3 = c.lastrowid
        s3 = [
            (t3,1,-3,"SMS","SMS","Friendly Reminder","Hi {client}, reminder that {ref} ({amount}) is due {due_date}. - KA Legacy","Friendly",1,0),
            (t3,2,7,"Email","Email","Friendly Follow-Up","Dear {client}, invoice {ref} for {amount} is 7 days past due. If paid, please disregard. Regards, KA Legacy","Friendly",1,0),
            (t3,3,30,"Call","Call","Follow-Up Call","Schedule call with {client} re: {ref} ({amount}) - 30 days overdue.","Formal",0,0),
        ]
        c.executemany("INSERT INTO workflow_steps (template_id,step_order,days_from_due,action_type,channel,subject,template_text,escalation_level,auto_execute,requires_approval) VALUES (?,?,?,?,?,?,?,?,?,?)", s3)
    conn.commit(); conn.close()

def run_workflow_engine(db_path=DB_PATH):
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
    today = date.today(); today_str = str(today); nca_ok = is_nca_compliant()
    summary = {"checked":0,"executed":0,"skipped_nca":0,"completed":0,"details":[]}
    assignments = conn.execute(
        "SELECT wa.*, c.company_name, c.email, c.phone, i.invoice_number, i.due_date, i.total_amount, i.amount_paid "
        "FROM workflow_assignments wa JOIN clients c ON wa.client_id=c.id "
        "LEFT JOIN invoices i ON wa.invoice_id=i.id WHERE wa.status='Active'").fetchall()
    for assign in assignments:
        summary["checked"] += 1
        if not assign["next_execution_date"] or assign["next_execution_date"] > today_str: continue
        next_order = assign["last_executed_step"] + 1
        step = conn.execute("SELECT * FROM workflow_steps WHERE template_id=? AND step_order=?",
            (assign["template_id"], next_order)).fetchone()
        if not step:
            conn.execute("UPDATE workflow_assignments SET status='Completed', completed_at=? WHERE id=?", (get_sast_now(), assign["id"]))
            summary["completed"] += 1; continue
        outstanding = (assign["total_amount"] or 0) - (assign["amount_paid"] or 0)
        if outstanding <= 0:
            conn.execute("UPDATE workflow_assignments SET status='Completed', completed_at=? WHERE id=?", (get_sast_now(), assign["id"]))
            summary["completed"] += 1; continue
        if step["action_type"] in ("SMS","Email","WhatsApp") and not nca_ok:
            summary["skipped_nca"] += 1; continue
        if step["requires_approval"]:
            conn.execute("INSERT INTO workflow_execution_log (assignment_id,step_id,executed_at,channel,action_type,status,message_sent,recipient,notes) VALUES (?,?,?,?,?,?,?,?,?)",
                (assign["id"],step["id"],get_sast_now(),step["channel"],step["action_type"],"PendingApproval",step["template_text"],"","Requires approval"))
            continue
        msg = (step["template_text"] or "").replace("{client}",assign["company_name"] or "").replace("{ref}",assign["invoice_number"] or "").replace("{amount}",f"R {outstanding:,.2f}").replace("{due_date}",assign["due_date"] or "")
        recipient = assign["email"] if step["channel"] == "Email" else (assign["phone"] or "")
        if step["action_type"] in ("SMS","Email","WhatsApp"):
            conn.execute("INSERT INTO communication_log (client_id,channel,message_subject,message_body,recipient_contact,sent_by,sent_at,status,nca_compliant,reminder_type,linked_invoice_id,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (assign["client_id"],step["channel"],step["subject"] or "",msg,recipient,"Workflow Engine",get_sast_now(),"Sent",1 if nca_ok else 0,step["escalation_level"],assign["invoice_number"] or "",f"Auto: step {next_order}"))
        if step["action_type"] in ("Call","Note"):
            conn.execute("INSERT INTO collection_notes (client_id,note_type,note_text,created_by,created_at) VALUES (?,?,?,?,?)",
                (assign["client_id"],"Client Call" if step["action_type"]=="Call" else "Internal Note",f"[AUTO] {msg}","Workflow Engine",get_sast_now()))
        conn.execute("INSERT INTO workflow_execution_log (assignment_id,step_id,executed_at,channel,action_type,status,message_sent,recipient,notes) VALUES (?,?,?,?,?,?,?,?,?)",
            (assign["id"],step["id"],get_sast_now(),step["channel"],step["action_type"],"Success",msg,recipient,f"Step {next_order} executed"))
        nxt = conn.execute("SELECT * FROM workflow_steps WHERE template_id=? AND step_order=?", (assign["template_id"], next_order+1)).fetchone()
        nxt_str = None
        if nxt:
            due = datetime.strptime(assign["due_date"],"%Y-%m-%d").date()
            nx = due + timedelta(days=nxt["days_from_due"])
            if nx < today: nx = today + timedelta(days=1)
            nxt_str = str(nx)
        conn.execute("UPDATE workflow_assignments SET current_step=?, last_executed_step=?, last_executed_at=?, next_execution_date=? WHERE id=?",
            (next_order, next_order, get_sast_now(), nxt_str, assign["id"]))
        summary["executed"] += 1
        summary["details"].append(f"{assign['company_name']} - step {next_order}: {step['action_type']}")
    log_audit("WORKFLOW","Workflow Engine",f"Engine: {summary['checked']} checked, {summary['executed']} executed")
    conn.commit(); conn.close()
    return summary

def render_workflows():
    init_workflows_db()
    st.markdown("## Automated Workflows")
    st.markdown("_Set it and forget it. Multi-step, timed, multi-channel collection sequences._")
    tab = st.radio("", ["Templates","Active Workflows","Run Engine","Execution Log"], horizontal=True, key="wf_tab")
    conn = get_db(); today = date.today()
    if tab == "Templates":
        st.markdown("### Workflow Templates")
        templates = pd.read_sql("SELECT * FROM workflow_templates WHERE is_active=1 ORDER BY name", conn)
        if len(templates) == 0: st.info("No templates."); conn.close(); return
        for _, t in templates.iterrows():
            steps = pd.read_sql("SELECT * FROM workflow_steps WHERE template_id=? ORDER BY step_order", conn, params=(t["id"],))
            colour = {"B2B":"#0d6efd","Property":"#198754","School":"#6f42c1"}.get(t["industry_type"],"#6c757d")
            st.markdown(f'<div style="background:#f8f9fa;border-radius:8px;padding:16px;margin-bottom:12px;border-left:5px solid {colour};"><strong>{t["name"]}</strong> <span style="background:{colour};color:white;padding:2px 12px;border-radius:10px;font-size:0.8em;">{t["industry_type"]}</span><div style="font-size:0.9em;color:#666;margin-top:4px;">{t["description"]}</div></div>', unsafe_allow_html=True)
            if len(steps) > 0:
                cols = st.columns(len(steps))
                for i, (_, s) in enumerate(steps.iterrows()):
                    ec = ESC_COLOURS.get(s["escalation_level"],"#6c757d")
                    icon = CHANNEL_ICONS.get(s["action_type"],"")
                    appr = " [Approval]" if s["requires_approval"] else ""
                    with cols[i]:
                        st.markdown(f'<div style="text-align:center;padding:8px;background:white;border:2px solid {ec};border-radius:8px;font-size:0.75em;"><div style="font-size:1.4em;">{icon}</div><div style="font-weight:bold;color:{ec};">Day {s["days_from_due"]}</div><div>{s["action_type"]}{appr}</div></div>', unsafe_allow_html=True)
                st.markdown("---")
    elif tab == "Active Workflows":
        st.markdown("### Active Assignments")
        asgn = pd.read_sql("SELECT wa.*, c.company_name, i.invoice_number, wt.name as tname, wt.total_steps FROM workflow_assignments wa JOIN clients c ON wa.client_id=c.id LEFT JOIN invoices i ON wa.invoice_id=i.id JOIN workflow_templates wt ON wa.template_id=wt.id ORDER BY wa.status, wa.next_execution_date", conn)
        if len(asgn) > 0:
            for _, a in asgn.iterrows():
                tot = a["total_steps"] or 7; prog = a["last_executed_step"]/tot if tot>0 else 0
                sc = {"Active":"#198754","Paused":"#ffc107","Completed":"#0d6efd","Cancelled":"#dc3545"}.get(a["status"],"#6c757d")
                st.markdown(f'<div style="border-left:4px solid {sc};padding:12px 16px;margin-bottom:8px;background:#f9f9f9;border-radius:6px;"><strong>{a["company_name"]}</strong> - {a["invoice_number"] or "General"} <span style="background:{sc};color:white;padding:2px 10px;border-radius:10px;font-size:0.8em;">{a["status"]}</span><div style="font-size:0.9em;color:#666;margin-top:4px;">Template: {a["tname"]} | Step: {a["last_executed_step"]}/{tot} | Next: {a["next_execution_date"] or "N/A"}</div><div style="background:#e9ecef;border-radius:4px;height:8px;margin-top:6px;"><div style="background:{sc};width:{prog*100:.0f}%;height:100%;border-radius:4px;"></div></div></div>', unsafe_allow_html=True)
        else: st.info("No assignments yet.")
        st.divider(); st.markdown("### Assign Workflow")
        clients = pd.read_sql("SELECT id, company_name FROM clients WHERE status='Active' ORDER BY company_name", conn)
        tpls = pd.read_sql("SELECT id, name FROM workflow_templates WHERE is_active=1", conn)
        if len(clients)>0 and len(tpls)>0:
            with st.form("assign_wf"):
                c1,c2 = st.columns(2)
                with c1:
                    acl = st.selectbox("Client", clients["company_name"].tolist(), key="wf_acl")
                    acid = int(clients[clients["company_name"]==acl]["id"].values[0])
                    invs = pd.read_sql("SELECT id, invoice_number FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid')", conn, params=(acid,))
                    iopts = ["All Open"] + (invs["invoice_number"].tolist() if len(invs)>0 else [])
                    ainv = st.selectbox("Invoice", iopts, key="wf_ainv")
                with c2:
                    atpl = st.selectbox("Template", tpls["name"].tolist(), key="wf_atpl")
                    atid = int(tpls[tpls["name"]==atpl]["id"].values[0])
                if st.form_submit_button("Assign & Start", type="primary"):
                    iid = None
                    if ainv not in ("All Open","") and len(invs)>0:
                        iid = int(invs[invs["invoice_number"]==ainv]["id"].values[0])
                    fs = conn.execute("SELECT * FROM workflow_steps WHERE template_id=? ORDER BY step_order LIMIT 1",(atid,)).fetchone()
                    if iid:
                        ir = conn.execute("SELECT due_date FROM invoices WHERE id=?",(iid,)).fetchone()
                        due = datetime.strptime(ir["due_date"],"%Y-%m-%d").date()
                    else: due = today
                    ne = due + timedelta(days=fs["days_from_due"]) if fs else today
                    if ne < today: ne = today
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute("INSERT INTO workflow_assignments (client_id,invoice_id,template_id,status,current_step,started_at,next_execution_date,assigned_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (acid,iid,atid,"Active",0,get_sast_now(),str(ne),DEFAULT_USER,get_sast_now()))
                    conn2.commit(); conn2.close()
                    log_audit("WORKFLOW","Workflows",f"Workflow '{atpl}' assigned to {acl}")
                    st.success(f"Workflow assigned! First action: {str(ne)}")
                    st.rerun()
    elif tab == "Run Engine":
        st.markdown("### Workflow Engine")
        active = conn.execute("SELECT COUNT(*) FROM workflow_assignments WHERE status='Active'").fetchone()[0]
        due_t = conn.execute("SELECT COUNT(*) FROM workflow_assignments WHERE status='Active' AND next_execution_date<=?",(str(today),)).fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM workflow_assignments WHERE status='Completed'").fetchone()[0]
        k1,k2,k3 = st.columns(3); k1.metric("Active",active); k2.metric("Due Today",due_t); k3.metric("Completed",done)
        if is_nca_compliant(): st.success("NCA Compliant - messaging allowed")
        else: st.warning("Outside NCA hours - messaging steps skipped")
        if st.button("Run Workflow Engine Now", type="primary", use_container_width=True, key="run_wf"):
            r = run_workflow_engine()
            st.markdown(f"**Checked:** {r['checked']} | **Executed:** {r['executed']} | **Completed:** {r['completed']}")
            for d in r["details"]: st.markdown(f"- {d}")
            if r["executed"]==0 and r["completed"]==0: st.info("No actions due.")
    else:
        st.markdown("### Execution Log")
        logs = pd.read_sql("SELECT wel.*, c.company_name FROM workflow_execution_log wel JOIN workflow_assignments wa ON wel.assignment_id=wa.id JOIN clients c ON wa.client_id=c.id ORDER BY wel.executed_at DESC", conn)
        if len(logs)==0: st.info("No executions yet.")
        else:
            for _, l in logs.iterrows():
                sc = {"Success":"#198754","Failed":"#dc3545","Skipped":"#ffc107","PendingApproval":"#0d6efd"}.get(l["status"],"#6c757d")
                st.markdown(f'<div style="border-left:3px solid {sc};padding:8px 14px;margin-bottom:4px;background:#f8f9fa;border-radius:4px;font-size:0.9em;"><span style="background:{sc};color:white;padding:1px 8px;border-radius:8px;font-size:0.8em;">{l["status"]}</span> <strong>{l["company_name"]}</strong> - {l["action_type"]} via {l["channel"]} <span style="float:right;color:#888;font-size:0.85em;">{l["executed_at"]}</span></div>', unsafe_allow_html=True)
    conn.close()
