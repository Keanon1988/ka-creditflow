# 🏦 KA CreditFlow v3.0
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
| 🔐 Authentication | Secure login with hashed passwords, role-based access |
| 📊 Dashboard | Comprehensive portfolio overview with 15+ KPIs |
| ➕ Add Client | Full client/debtor registration with financial data |
| 📁 View Clients | Search, filter, and view all clients |
| ⚡ Credit Engine | 5-factor credit scoring (0-100), auto-recommendations |
| 📜 Audit Trail | Complete decision history — who, when, why |
| 👥 User Management | Add/manage users (admin only) |
| 🔑 Change Password | Secure password updates |

### Phase 2 — Invoicing & AR Management
| Module | Description |
|--------|-------------|
| 🧾 Create Invoice | Full invoicing with line items, 15% SA VAT, auto-numbering |
| 📋 Invoice Register | View all invoices with search, filter, sort, detail view |
| 💵 Record Payment | Record payments (EFT, Cash, Card, Cheque), auto-status update |
| 📊 AR Aging Analysis | 6 aging buckets (Current → 120+ days), DSO tracking |
| 🔥 Top Debtors | Ranked list of highest-risk overdue debtors |

### Phase 3 — Collections & Follow-Up 🆕
| Module | Description |
|--------|-------------|
| 📞 Collections Center | Full collections command center — your daily workspace |
| 📱 WhatsApp Integration | One-click WhatsApp messages with pre-filled templates |
| 📧 Email Templates | Professional escalating email templates (copy & paste) |
| 💬 SMS Templates | Short SMS templates for each escalation tier |
| ⚡ Auto-Escalation | Invoices auto-escalate: Friendly → Firm → Final Demand → Pre-Legal → Legal |
| 🤝 Promise-to-Pay | Record, track, and monitor PTPs — auto-flag broken promises |
| 🚨 Contact Me Queue | Urgent queue for clients who can't pay (WhatsApp option 3) |
| 📋 Action Logging | Every call, email, WhatsApp logged with outcomes |
| ⬆️ Manual Escalation | Override escalation tiers when needed |

---

## 📞 WhatsApp Response Options

When a client receives a WhatsApp collection message, they can reply:

| Reply | Meaning | System Action |
|-------|---------|---------------|
| 1️⃣ | I will pay by [date] | Log as Promise-to-Pay |
| 2️⃣ | I need to discuss | Log call request |
| 3️⃣ | I cannot pay — contact me | 🚨 Added to urgent Contact Me queue |
| 4️⃣ | I dispute this invoice | Log dispute |

---

## ⚡ Escalation Tiers

| Tier | Days Overdue | Tone | Action |
|------|-------------|------|--------|
| 🟢 Friendly | 1-30 | Kind, professional | Gentle reminder |
| 🟡 Firm | 31-60 | Urgent | Warn of credit impact |
| 🟠 Final Demand | 61-90 | Formal | 7-day deadline, legal warning |
| 🔴 Pre-Legal | 91-120 | Legal notice | Section 129 NCA reference |
| ⚫ Legal | 120+ | Attorney handover | Legal costs + court action |

---

## 📊 Credit Scoring Model

| Factor | Weight | Description |
|--------|--------|-------------|
| Years in Business | 15% | Longer = more stable |
| Annual Revenue | 25% | Higher = more capacity |
| Debt-to-Revenue | 20% | Lower ratio = healthier |
| Payment History | 30% | Past behaviour predicts future |
| Industry Risk | 10% | Some industries are riskier |

**Decision Thresholds:** 70+ = ✅ Approve | 40-69 = 🟡 Conditional | <40 = ❌ Decline

---

## 🗄️ Database Tables (9 Total)

| Table | Purpose |
|-------|---------|
| users | Authentication & roles |
| clients | Client/debtor master data |
| credit_decisions | Credit decision audit trail |
| invoices | Invoice headers |
| invoice_items | Invoice line items |
| payments | Payment records |
| collection_actions | 🆕 Collection activity log |
| promises_to_pay | 🆕 Promise-to-pay tracker |
| contact_me_queue | 🆕 Urgent contact requests |

---

## 🔮 Coming in Phase 4-5
- Advanced Dashboard Visualizations (Charts & Graphs)
- PDF Report Generation & Export
- Automated email sending (SMTP integration)
- WhatsApp Business API integration
- Multi-tenant SaaS Deployment
- PayFast Payment Gateway Integration
- Client self-service portal

---

© 2026 KA Legacy (PTY) LTD. All rights reserved.
