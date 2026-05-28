# 🏦 KA CreditFlow v2.0
## Credit Management & Collections Platform
### "From Invoice to Cash — Faster."

Built for **KA Legacy (PTY) LTD** — Keanon Apollos

---

## 🚀 Quick Start Guide

### Step 1: Install Python
Download and install Python 3.9+ from https://www.python.org/downloads/

### Step 2: Create a Project Folder
Create a folder called `KA_CreditFlow` and place `app.py` and `requirements.txt` inside it.

### Step 3: Open Terminal / Command Prompt
```
cd path/to/KA_CreditFlow
```

### Step 4: Install Dependencies
```
pip install -r requirements.txt
```

### Step 5: Run the App
```
streamlit run app.py
```

### Step 6: Open in Browser
The app will automatically open at: http://localhost:8501

### Step 7: Login
- **Username:** admin
- **Password:** admin123
- ⚠️ Change your password immediately after first login!

---

## 📱 Features

### Phase 1 — Credit Management
| Module | Description |
|--------|-------------|
| 🔐 Authentication | Secure login with hashed passwords |
| 📊 Dashboard | Portfolio overview with comprehensive KPIs |
| ➕ Add Client | Full client/debtor registration |
| 📁 View Clients | Search, filter, and view all clients |
| ⚡ Credit Engine | Auto credit scoring (0-100) with recommendations |
| 📜 Audit Trail | Complete decision history |
| 👥 User Management | Add/manage users (admin only) |
| 🔑 Change Password | Secure password updates |

### Phase 2 — Invoicing & AR Management
| Module | Description |
|--------|-------------|
| 🧾 Create Invoice | Full invoice creation with line items, VAT (15%) |
| 📋 Invoice Register | View all invoices with search, filter, sort |
| 💵 Record Payment | Record payments against invoices (EFT, Cash, Card, Cheque) |
| 📊 AR Aging Analysis | Current / 1-30 / 31-60 / 61-90 / 91-120 / 120+ day buckets |
| 📆 DSO Tracking | Days Sales Outstanding auto-calculation |
| 🔥 Top Overdue Debtors | Ranked list of highest-risk debtors |
| 👥 Aging by Client | Client-level AR breakdown |

---

## 📊 Credit Scoring Model

| Factor | Weight | Description |
|--------|--------|-------------|
| Years in Business | 15% | Longer = more stable |
| Annual Revenue | 25% | Higher = more capacity |
| Debt-to-Revenue | 20% | Lower ratio = healthier |
| Payment History | 30% | Past behaviour predicts future |
| Industry Risk | 10% | Some industries are riskier |

### Decision Thresholds:
- **70-100**: ✅ APPROVE
- **40-69**: 🟡 CONDITIONAL
- **0-39**: ❌ DECLINE

---

## 🧾 Invoice Features
- Auto-generated invoice numbers (INV-0001, INV-0002...)
- Line items with quantity, unit price, auto-calculated totals
- 15% SA VAT auto-calculated
- Due dates auto-set from client payment terms
- Status tracking: Draft → Sent → Partially Paid → Paid / Overdue / Written Off
- Auto-detection of overdue invoices

## 📊 AR Aging Buckets
- **Current**: Not yet due
- **1-30 days**: Mildly overdue
- **31-60 days**: Needs attention
- **61-90 days**: Escalation needed
- **91-120 days**: Critical
- **120+ days**: Collections / write-off consideration

---

## 🔮 Coming in Phase 3-5
- Automated Collections Workflow & Escalation Engine
- Email Notifications & Reminders (Friendly → Firm → Final Demand → Legal)
- Advanced Dashboard Visualizations (Charts & Graphs)
- PDF Report Generation
- Multi-tenant SaaS Deployment
- PayFast Payment Gateway Integration

---

© 2024 KA Legacy (PTY) LTD. All rights reserved.
