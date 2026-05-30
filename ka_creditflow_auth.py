"""
KA CreditFlow v6.0a - Authentication & RBAC
"""
import streamlit as st
import sqlite3
import hashlib
import secrets
import pandas as pd
from datetime import datetime, timezone, timedelta

SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"
MAX_FAILED_ATTEMPTS = 5

def get_sast_now():
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()))
    conn.commit()
    conn.close()

def hash_password(password):
    salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{pw_hash}"

def verify_password(password, stored_hash):
    try:
        salt, pw_hash = stored_hash.split(":", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == pw_hash
    except (ValueError, AttributeError):
        return False

ROLES = ["Owner", "Manager", "Collector", "Auditor"]

MODULE_ACCESS = {
    "Dashboard": {"Owner","Manager","Collector","Auditor"},
    "Clients": {"Owner","Manager","Collector"},
    "Invoices": {"Owner","Manager","Collector","Auditor"},
    "Credit Engine": {"Owner","Manager"},
    "Worklist": {"Owner","Manager","Collector"},
    "Notes": {"Owner","Manager","Collector"},
    "Communications": {"Owner","Manager","Collector"},
    "Disputes & Promises": {"Owner","Manager","Collector"},
    "Reporting": {"Owner","Manager","Auditor"},
    "Audit Trail": {"Owner","Manager","Auditor"},
    "Dunning Engine": {"Owner","Manager"},
    "Cash Flow Forecast": {"Owner","Manager"},
    "Payment Analytics": {"Owner","Manager"},
    "Data Import/Export": {"Owner","Manager","Auditor"},
    "Write-Offs": {"Owner","Manager"},
    "Interest Calculator": {"Owner","Manager"},
    "Credit Applications": {"Owner","Manager"},
    "KPI Targets": {"Owner","Manager"},
    "User Management": {"Owner"},
    "Automated Workflows": {"Owner","Manager"},
    "Legal Compliance": {"Owner","Manager"},
    "Document Center": {"Owner","Manager","Collector","Auditor"},
    "POPIA Compliance": {"Owner","Manager"},
    "Predictive Engine": {"Owner","Manager"},
}

WRITE_ACCESS = {
    "Owner": {"create": True, "edit": True, "delete": True},
    "Manager": {"create": True, "edit": True, "delete": False},
    "Collector": {"create": True, "edit": False, "delete": False},
    "Auditor": {"create": False, "edit": False, "delete": False},
}

def get_current_user():
    return st.session_state.get("user", None)

def is_authenticated():
    return st.session_state.get("authenticated", False)

def has_permission(module_name):
    user = get_current_user()
    if not user: return False
    return user.get("role", "") in MODULE_ACCESS.get(module_name, set())

def is_owner():
    user = get_current_user()
    return user and user.get("role") == "Owner"

def is_auditor():
    user = get_current_user()
    return user and user.get("role") == "Auditor"

def can_create(module=""):
    user = get_current_user()
    if not user: return False
    return WRITE_ACCESS.get(user.get("role",""),{}).get("create", False)

def can_edit(module=""):
    user = get_current_user()
    if not user: return False
    return WRITE_ACCESS.get(user.get("role",""),{}).get("edit", False)

def can_delete(module=""):
    user = get_current_user()
    if not user: return False
    return WRITE_ACCESS.get(user.get("role",""),{}).get("delete", False)

def require_permission(module_name):
    if not has_permission(module_name):
        st.error(f"Access Denied. Your role does not have access to {module_name}.")
        return False
    return True

def get_allowed_modules(role):
    return [mod for mod, roles in MODULE_ACCESS.items() if role in roles]

def init_auth_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, display_name TEXT NOT NULL, email TEXT,
        role TEXT NOT NULL DEFAULT 'Collector', is_active INTEGER DEFAULT 1,
        failed_attempts INTEGER DEFAULT 0, last_login TEXT, created_at TEXT, created_by TEXT)""")
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        now = get_sast_now()
        users = [
            ("owner", hash_password("KALegacy2026!"), "Keanon Apollos", "keanon@kalegacy.co.za", "Owner", 1, 0, None, now, "System"),
            ("manager", hash_password("Manager2026!"), "Amy St Clair", "manager@kalegacy.co.za", "Manager", 1, 0, None, now, "System"),
            ("collector", hash_password("Collect2026!"), "Collections Team", "collections@kalegacy.co.za", "Collector", 1, 0, None, now, "System"),
            ("auditor", hash_password("Audit2026!"), "External Auditor", "auditor@kalegacy.co.za", "Auditor", 1, 0, None, now, "System"),
        ]
        c.executemany("INSERT INTO users (username,password_hash,display_name,email,role,is_active,failed_attempts,last_login,created_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?)", users)
    conn.commit()
    conn.close()

def render_login():
    if is_authenticated(): return True
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div style="text-align:center;padding:40px 0 20px 0;"><h1>KA CreditFlow</h1><p style="color:#888;">v6.0 Enterprise Edition</p></div>', unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In", type="primary", use_container_width=True)
            if submit:
                if not username or not password:
                    st.error("Enter both username and password.")
                    return False
                conn = get_db()
                user = conn.execute("SELECT * FROM users WHERE username=?", (username.lower().strip(),)).fetchone()
                conn.close()
                if not user:
                    st.error("Invalid username or password.")
                    return False
                if user["failed_attempts"] >= MAX_FAILED_ATTEMPTS:
                    st.error("Account Locked. Contact administrator.")
                    return False
                if not user["is_active"]:
                    st.error("Account deactivated.")
                    return False
                if verify_password(password, user["password_hash"]):
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute("UPDATE users SET failed_attempts=0, last_login=? WHERE id=?", (get_sast_now(), user["id"]))
                    conn2.commit()
                    conn2.close()
                    st.session_state["authenticated"] = True
                    st.session_state["user"] = {"id":user["id"],"username":user["username"],"display_name":user["display_name"],"email":user["email"],"role":user["role"]}
                    log_audit("AUTH_SUCCESS","Login",f"{user['display_name']} logged in",user=user["display_name"])
                    st.rerun()
                else:
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute("UPDATE users SET failed_attempts=failed_attempts+1 WHERE id=?", (user["id"],))
                    conn2.commit()
                    conn2.close()
                    remaining = MAX_FAILED_ATTEMPTS - user["failed_attempts"] - 1
                    st.error(f"Invalid password. {remaining} attempts remaining.")
                    return False
    return False

def logout():
    user = get_current_user()
    if user:
        log_audit("AUTH_LOGOUT","Login",f"{user['display_name']} logged out",user=user["display_name"])
    st.session_state["authenticated"] = False
    st.session_state["user"] = None
    st.rerun()

def render_sidebar_user_info():
    user = get_current_user()
    if not user: return
    colours = {"Owner":"#198754","Manager":"#0d6efd","Collector":"#ffc107","Auditor":"#6c757d"}
    c = colours.get(user["role"],"#6c757d")
    st.markdown(f"**{user['display_name']}**")
    st.markdown(f'<span style="background:{c};color:white;padding:2px 10px;border-radius:10px;font-size:0.8em;">{user["role"]}</span>', unsafe_allow_html=True)
    if st.button("Logout", use_container_width=True, key="logout_btn"):
        logout()

def render_user_management():
    if not is_owner():
        st.error("Owner access required.")
        return
    st.markdown("## User Management")
    conn = get_db()
    users = pd.read_sql("SELECT * FROM users ORDER BY role, display_name", conn)
    if len(users) > 0:
        d = users[["id","username","display_name","email","role","is_active","failed_attempts","last_login"]].copy()
        d.columns = ["ID","Username","Name","Email","Role","Active","Failed","Last Login"]
        d["Active"] = d["Active"].map({1:"Yes",0:"No"})
        st.dataframe(d, use_container_width=True, hide_index=True)
    with st.form("add_user"):
        c1, c2 = st.columns(2)
        with c1:
            nu = st.text_input("Username *")
            np = st.text_input("Password *", type="password")
            nn = st.text_input("Display Name *")
        with c2:
            ne = st.text_input("Email")
            nr = st.selectbox("Role", ROLES)
        if st.form_submit_button("Create User", type="primary"):
            if not nu or not np or not nn:
                st.warning("All fields required.")
            elif len(np) < 8:
                st.warning("Password must be 8+ characters.")
            else:
                try:
                    conn2 = sqlite3.connect(DB_PATH)
                    conn2.execute("INSERT INTO users (username,password_hash,display_name,email,role,is_active,created_at,created_by) VALUES (?,?,?,?,?,?,?,?)",
                        (nu.lower().strip(), hash_password(np), nn, ne, nr, 1, get_sast_now(), get_current_user()["display_name"]))
                    conn2.commit()
                    conn2.close()
                    st.success(f"User '{nu}' created.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Username exists.")
    conn.close()
