"""
KA CreditFlow v6.0 - Document Generation Module
"""
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta, date

SAST = timezone(timedelta(hours=2))
DB_PATH = "ka_creditflow_v5.db"
DEFAULT_USER = "Keanon Apollos"
VAT_RATE = 0.15

def get_sast_now():
    return datetime.now(SAST).strftime("%Y-%m-%d %H:%M:%S")
def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn
def log_audit(action_type, module, description, user=DEFAULT_USER, details=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO audit_trail (action_type,module,description,user,details,created_at) VALUES (?,?,?,?,?,?)",
        (action_type, module, description, user, details, get_sast_now()))
    conn.commit(); conn.close()

DEFAULT_CREDITOR = {"name":"KA Legacy (Pty) Ltd","address":"14 Rivonia Road, Sandton, 2196","phone":"+27 XX XXX XXXX","email":"accounts@kalegacy.co.za","vat_number":"4XXXXXXXXX","reg_number":"20XX/XXXXXX/07","bank_name":"[Bank Name]","bank_branch":"[Branch]","bank_account":"[Account Number]","bank_type":"Current/Cheque"}

DOC_CSS = """<style>@media print{body{margin:0;padding:0;}@page{margin:1.5cm;}}body{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;color:#333;line-height:1.5;max-width:800px;margin:0 auto;padding:30px;}.doc-header{display:flex;justify-content:space-between;border-bottom:3px solid #1a5276;padding-bottom:15px;margin-bottom:25px;}.company-name{font-size:24px;font-weight:bold;color:#1a5276;margin:0;}.company-details{font-size:11px;color:#666;text-align:right;}.doc-title{text-align:center;font-size:22px;font-weight:bold;color:#1a5276;margin:20px 0;text-transform:uppercase;letter-spacing:2px;}.info-grid{display:flex;justify-content:space-between;margin-bottom:25px;}.info-box{width:48%;}.info-box h4{font-size:12px;text-transform:uppercase;color:#888;margin:0 0 5px 0;}table{width:100%;border-collapse:collapse;margin:20px 0;}table th{background:#1a5276;color:white;padding:10px 12px;text-align:left;font-size:12px;}table td{padding:8px 12px;border-bottom:1px solid #e0e0e0;}.amount{text-align:right;font-family:'Courier New',monospace;}.totals-table{width:350px;margin-left:auto;}.totals-table td{padding:6px 12px;border:none;}.grand-total{font-size:16px;font-weight:bold;color:#1a5276;border-top:2px solid #1a5276;}.payment-box{background:#f0f4f8;border:1px solid #d0d8e0;border-radius:6px;padding:15px;margin:20px 0;}.payment-box h4{margin:0 0 8px 0;color:#1a5276;}.footer{text-align:center;margin-top:40px;padding-top:15px;border-top:1px solid #e0e0e0;font-size:11px;color:#888;}.overdue{color:#dc3545;font-weight:bold;}</style>"""

def generate_invoice_html(invoice, client, creditor=None):
    if creditor is None: creditor = DEFAULT_CREDITOR
    outstanding = invoice["total_amount"] - invoice["amount_paid"]
    today_str = date.today().strftime("%d %B %Y")
    vat_amt = invoice.get("vat_amount", invoice["amount"] * VAT_RATE)
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Invoice {invoice['invoice_number']}</title>{DOC_CSS}</head><body>
<div class="doc-header"><div><p class="company-name">{creditor['name']}</p><p style="font-size:11px;color:#666;">Credit Risk &amp; Collections Management</p></div>
<div class="company-details">{creditor['address']}<br>Tel: {creditor['phone']}<br>Email: {creditor['email']}<br>VAT: {creditor['vat_number']}<br>Reg: {creditor['reg_number']}</div></div>
<div class="doc-title">TAX INVOICE</div>
<div class="info-grid"><div class="info-box"><h4>Bill To</h4><p><strong>{client.get('company_name','')}</strong></p><p>{client.get('contact_person','')}</p><p>{client.get('address','')}</p><p>{client.get('email','')}</p><p>VAT: {client.get('vat_number','N/A')}</p></div>
<div class="info-box" style="text-align:right;"><h4>Invoice Details</h4><p><strong>Invoice #:</strong> {invoice['invoice_number']}</p><p><strong>Date:</strong> {invoice.get('invoice_date',today_str)}</p><p><strong>Due Date:</strong> {invoice['due_date']}</p><p><strong>Terms:</strong> {client.get('payment_terms','Net 30')}</p></div></div>
<table><thead><tr><th style="width:50%;">Description</th><th class="amount">Amount</th><th class="amount">VAT (15%)</th><th class="amount">Total</th></tr></thead>
<tbody><tr><td>{invoice.get('description','Professional services')}</td><td class="amount">R {invoice['amount']:,.2f}</td><td class="amount">R {vat_amt:,.2f}</td><td class="amount">R {invoice['total_amount']:,.2f}</td></tr></tbody></table>
<table class="totals-table"><tr><td><strong>Subtotal:</strong></td><td class="amount">R {invoice['amount']:,.2f}</td></tr>
<tr><td><strong>VAT (15%):</strong></td><td class="amount">R {vat_amt:,.2f}</td></tr>
<tr class="grand-total"><td><strong>TOTAL DUE:</strong></td><td class="amount"><strong>R {invoice['total_amount']:,.2f}</strong></td></tr>"""
    if invoice["amount_paid"] > 0:
        html += f"""<tr><td>Less: Payments</td><td class="amount">- R {invoice['amount_paid']:,.2f}</td></tr>
<tr class="grand-total"><td><strong>BALANCE DUE:</strong></td><td class="amount overdue"><strong>R {outstanding:,.2f}</strong></td></tr>"""
    html += f"""</table>
<div class="payment-box"><h4>Banking Details</h4><p><strong>Account Holder:</strong> {creditor['name']}</p><p><strong>Bank:</strong> {creditor['bank_name']}</p><p><strong>Account:</strong> {creditor['bank_account']}</p><p><strong>Reference:</strong> {invoice['invoice_number']}</p></div>
<div class="footer"><p><strong>Thank you for your business.</strong></p><p>Payment due by {invoice['due_date']}.</p><p>{creditor['name']} | {creditor['address']} | {creditor['email']}</p></div>
<div style="text-align:center;font-size:10px;color:#ccc;margin-top:20px;">Generated by KA CreditFlow | {today_str}</div></body></html>"""
    return html

def generate_statement_html(client, invoices_df, creditor=None):
    if creditor is None: creditor = DEFAULT_CREDITOR
    today = date.today(); today_str = today.strftime("%d %B %Y")
    df = invoices_df.copy()
    df["outstanding"] = df["total_amount"] - df["amount_paid"]
    df["due_dt"] = pd.to_datetime(df["due_date"]).dt.date
    df["days_overdue"] = df["due_dt"].apply(lambda d: max(0, (today - d).days))
    total = df["outstanding"].sum()
    def bkt(d):
        if d==0: return "Current"
        elif d<=30: return "1-30"
        elif d<=60: return "31-60"
        elif d<=90: return "61-90"
        elif d<=120: return "91-120"
        else: return "120+"
    df["bucket"] = df["days_overdue"].apply(bkt)
    buckets = ["Current","1-30","31-60","61-90","91-120","120+"]
    aging = {b: df[df["bucket"]==b]["outstanding"].sum() for b in buckets}
    rows = ""
    for _, inv in df.iterrows():
        rows += f'<tr><td>{inv["invoice_date"]}</td><td>{inv["invoice_number"]}</td><td>{inv.get("description","")}</td><td class="amount">R {inv["total_amount"]:,.2f}</td><td class="amount">R {inv["amount_paid"]:,.2f}</td><td class="amount">R {inv["outstanding"]:,.2f}</td><td style="text-align:center;">{inv["days_overdue"]}</td></tr>'
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Statement - {client.get('company_name','')}</title>{DOC_CSS}</head><body>
<div class="doc-header"><div><p class="company-name">{creditor['name']}</p></div><div class="company-details">{creditor['address']}<br>{creditor['phone']}</div></div>
<div class="doc-title">STATEMENT OF ACCOUNT</div>
<div class="info-grid"><div class="info-box"><h4>Account Holder</h4><p><strong>{client.get('company_name','')}</strong></p><p>{client.get('address','')}</p></div>
<div class="info-box" style="text-align:right;"><h4>Date</h4><p>{today_str}</p><p style="font-size:18px;font-weight:bold;color:#dc3545;">Balance: R {total:,.2f}</p></div></div>
<table><thead><tr><th>Date</th><th>Invoice</th><th>Description</th><th class="amount">Invoiced</th><th class="amount">Paid</th><th class="amount">Outstanding</th><th>Days</th></tr></thead><tbody>{rows}</tbody>
<tfoot><tr style="background:#1a5276;color:white;font-weight:bold;"><td colspan="5">TOTAL</td><td class="amount" style="color:white;">R {total:,.2f}</td><td></td></tr></tfoot></table>
<h4 style="color:#1a5276;">Aging Summary</h4>
<table><thead><tr>{"".join(f"<th>{b}</th>" for b in buckets)}<th>Total</th></tr></thead>
<tbody><tr>{"".join(f'<td class="amount">R {aging.get(b,0):,.2f}</td>' for b in buckets)}<td class="amount" style="font-weight:bold;">R {total:,.2f}</td></tr></tbody></table>
<div class="payment-box"><h4>Payment Instructions</h4><p><strong>Account:</strong> {creditor['name']}</p><p><strong>Bank:</strong> {creditor['bank_name']}</p><p><strong>Account No:</strong> {creditor['bank_account']}</p></div>
<div class="footer"><p>Statement as at {today_str}. Queries: {creditor['email']}</p></div></body></html>"""
    return html

def generate_aging_report_html(invoices_df, creditor=None):
    if creditor is None: creditor = DEFAULT_CREDITOR
    today = date.today(); today_str = today.strftime("%d %B %Y")
    df = invoices_df.copy()
    df["outstanding"] = df["total_amount"] - df["amount_paid"]
    df["due_dt"] = pd.to_datetime(df["due_date"]).dt.date
    df["days_overdue"] = df["due_dt"].apply(lambda d: max(0, (today - d).days))
    def bkt(d):
        if d==0: return "Current"
        elif d<=30: return "1-30"
        elif d<=60: return "31-60"
        elif d<=90: return "61-90"
        elif d<=120: return "91-120"
        else: return "120+"
    df["bucket"] = df["days_overdue"].apply(bkt)
    total = df["outstanding"].sum()
    buckets = ["Current","1-30","31-60","61-90","91-120","120+"]
    aging = {b: df[df["bucket"]==b]["outstanding"].sum() for b in buckets}
    rows = ""
    for _, inv in df.iterrows():
        rows += f'<tr><td>{inv.get("company_name","")}</td><td>{inv["invoice_number"]}</td><td>{inv["due_date"]}</td><td class="amount">R {inv["outstanding"]:,.2f}</td><td style="text-align:center;">{inv["days_overdue"]}</td><td style="text-align:center;">{inv["bucket"]}</td><td>{inv["status"]}</td></tr>'
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Aging Report</title>{DOC_CSS}</head><body>
<div class="doc-header"><div><p class="company-name">{creditor['name']}</p><p style="font-size:11px;color:#666;">Aging Report</p></div><div class="company-details">Date: {today_str}<br>Total: <strong>R {total:,.2f}</strong></div></div>
<div class="doc-title">ACCOUNTS RECEIVABLE AGING REPORT</div>
<h4 style="color:#1a5276;">Summary</h4>
<table><thead><tr>{"".join(f"<th>{b}</th>" for b in buckets)}<th>Total</th></tr></thead>
<tbody><tr>{"".join(f'<td class="amount">R {aging.get(b,0):,.2f}</td>' for b in buckets)}<td class="amount" style="font-weight:bold;">R {total:,.2f}</td></tr></tbody></table>
<h4 style="color:#1a5276;">Detail</h4>
<table><thead><tr><th>Client</th><th>Invoice</th><th>Due</th><th class="amount">Outstanding</th><th>Days</th><th>Bucket</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>
<div class="footer"><p>Generated {today_str} by KA CreditFlow | {creditor['name']}</p></div></body></html>"""
    return html

def render_document_center():
    st.markdown("## Document Center")
    st.markdown("_Generate downloadable invoices, statements, and legal documents._")
    tab = st.radio("", ["Invoice","Statement","Aging Report"], horizontal=True, key="doc_tab")
    conn = get_db(); today = date.today()
    if tab == "Invoice":
        st.markdown("### Generate Tax Invoice")
        clients = pd.read_sql("SELECT * FROM clients ORDER BY company_name", conn)
        if len(clients)==0: st.warning("No clients."); conn.close(); return
        cmap = dict(zip(clients["company_name"], clients["id"]))
        sel = st.selectbox("Client", list(cmap.keys()), key="dcl")
        cid = cmap[sel]; cl = clients[clients["id"]==cid].iloc[0].to_dict()
        invs = pd.read_sql("SELECT * FROM invoices WHERE client_id=? ORDER BY invoice_date DESC", conn, params=(cid,))
        if len(invs)==0: st.info("No invoices."); conn.close(); return
        labels = invs.apply(lambda r: f"{r['invoice_number']} - R {r['total_amount']:,.2f} ({r['status']})", axis=1).tolist()
        si = st.selectbox("Invoice", labels, key="dinv")
        inv = invs.iloc[labels.index(si)].to_dict()
        if st.button("Generate Invoice", type="primary", key="ginv"):
            html = generate_invoice_html(inv, cl)
            log_audit("DOCUMENT","Document Center",f"Invoice: {inv['invoice_number']}")
            st.success(f"Invoice generated: {inv['invoice_number']}")
            st.download_button("Download Invoice (HTML)", html, file_name=f"Invoice_{inv['invoice_number']}_{today}.html", mime="text/html", key="dlinv")
            st.components.v1.html(html, height=800, scrolling=True)
    elif tab == "Statement":
        st.markdown("### Generate Client Statement")
        clients = pd.read_sql("SELECT * FROM clients ORDER BY company_name", conn)
        if len(clients)==0: conn.close(); return
        cmap = dict(zip(clients["company_name"], clients["id"]))
        sel = st.selectbox("Client", list(cmap.keys()), key="scl")
        cid = cmap[sel]; cl = clients[clients["id"]==cid].iloc[0].to_dict()
        invs = pd.read_sql("SELECT * FROM invoices WHERE client_id=? AND status IN ('Open','Partially Paid','Disputed') ORDER BY due_date", conn, params=(cid,))
        if len(invs)==0: st.info("No open invoices."); conn.close(); return
        if st.button("Generate Statement", type="primary", key="gstmt"):
            html = generate_statement_html(cl, invs)
            log_audit("DOCUMENT","Document Center",f"Statement: {sel}")
            st.download_button("Download Statement (HTML)", html, file_name=f"Statement_{sel.replace(' ','_')}_{today}.html", mime="text/html", key="dlstmt")
            st.components.v1.html(html, height=800, scrolling=True)
    else:
        st.markdown("### Portfolio Aging Report")
        invs = pd.read_sql("SELECT i.*, c.company_name FROM invoices i JOIN clients c ON i.client_id=c.id WHERE i.status IN ('Open','Partially Paid','Disputed') ORDER BY c.company_name, i.due_date", conn)
        if len(invs)==0: st.info("No open invoices."); conn.close(); return
        if st.button("Generate Aging Report", type="primary", key="gage"):
            html = generate_aging_report_html(invs)
            log_audit("DOCUMENT","Document Center","Aging report generated")
            st.download_button("Download Aging Report (HTML)", html, file_name=f"Aging_Report_{today}.html", mime="text/html", key="dlage")
            st.components.v1.html(html, height=800, scrolling=True)
    conn.close()
