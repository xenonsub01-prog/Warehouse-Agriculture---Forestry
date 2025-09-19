import os
import csv
import secrets
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# ---------------- CONFIG -----------------
DATA_DIR = "data"
ORDERS_FILE  = os.path.join(DATA_DIR, "orders.csv")
LOOKUPS_FILE = os.path.join(DATA_DIR, "lookups.csv")
LOG_FILE     = os.path.join(DATA_DIR, "log.csv")

TOKENS_DIR  = "tokens"
TOKENS_FILE = os.path.join(TOKENS_DIR, "tokens.csv")

# OWNER KEY (يمكن تغييره من Secrets على Streamlit Cloud)
OWNER_KEY = st.secrets.get("OWNER_KEY", "admin12345")
BASE_URL  = st.secrets.get("BASE_URL", "")  # اختياري لملء رابط التطبيق تلقائياً

st.set_page_config(page_title="Warehouse Dashboard Demo", layout="wide")

# ---------------- HELPERS -----------------
@st.cache_data(ttl=15)
def load_orders():
    df = pd.read_csv(ORDERS_FILE, dtype={"OrderID": str})
    if "OrderDate" in df.columns:
        df["OrderDate"] = pd.to_datetime(df["OrderDate"], errors="coerce")
    return df

@st.cache_data(ttl=60)
def load_lookups():
    return pd.read_csv(LOOKUPS_FILE)

def save_orders(df: pd.DataFrame):
    df.to_csv(ORDERS_FILE, index=False)

def append_log(row: dict):
    exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "Timestamp","User","Warehouse","OrderID",
                "FromStatus","ToStatus","FromInvoice","ToInvoice"
            ],
        )
        if not exists:
            w.writeheader()
        w.writerow(row)

def kpi_block(df: pd.DataFrame):
    c1, c2, c3, c4 = st.columns(4)
    open_cnt     = int((df["Status"] != "Invoiced").sum())
    overdue_cnt  = int(((pd.Timestamp("today").normalize() - df["OrderDate"]).dt.days > 7).sum())
    today_cnt    = int((df["OrderDate"].dt.date == pd.Timestamp("today").date()).sum())
    invoiced_cnt = int((df["Status"] == "Invoiced").sum())
    c1.metric("Open", open_cnt)
    c2.metric("Overdue (>7d)", overdue_cnt)
    c3.metric("Today", today_cnt)
    c4.metric("Invoiced", invoiced_cnt)

# ---------------- TOKEN UTILS -----------------
def ensure_tokens_file():
    os.makedirs(TOKENS_DIR, exist_ok=True)
    if not os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["token", "role", "company", "email", "expires_at", "created_at"])

def create_token(role: str, company: str, email: str, expires_at: datetime) -> str:
    """يولّد توكن قصير ويخزنه في tokens/tokens.csv"""
    ensure_tokens_file()
    token = secrets.token_hex(4)  # 8 حروف hex (قصير ولطيف للعميل)
    with open(TOKENS_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([token, role, company, email, expires_at.isoformat() + "Z", datetime.utcnow().isoformat() + "Z"])
    return token

def verify_token(token: str):
    """يرجع معلومات التوكن إذا كان صالحاً، وإلا يرجّع None"""
    if not token or not os.path.exists(TOKENS_FILE):
        return None
    try:
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["token"] == token:
                    exp = datetime.fromisoformat(row["expires_at"].replace("Z", ""))
                    if datetime.utcnow() <= exp:
                        return {"role": row["role"], "company": row["company"], "email": row["email"]}
    except Exception:
        return None
    return None

def token_manager_ui():
    st.sidebar.subheader("🔑 Token & Link (Owner)")
    base_url = st.sidebar.text_input("Base URL", BASE_URL)
    company  = st.sidebar.text_input("Company name", "Client Warehouse Co.")
    email    = st.sidebar.text_input("User email (optional)", "")
    expiry_unit   = st.sidebar.selectbox("Expiry unit", ["hours", "days"], index=0)
    expiry_amount = st.sidebar.number_input("Expiry amount", min_value=1, value=24, step=1)
    role = st.sidebar.selectbox("Role", ["editor", "viewer"], index=0)

    if st.sidebar.button("Generate Token & Link"):
        delta = timedelta(hours=expiry_amount) if expiry_unit == "hours" else timedelta(days=expiry_amount)
        tkn   = create_token(role, company, email, datetime.utcnow() + delta)
        url   = f"{base_url}?token={tkn}" if base_url else f"?token={tkn}"
        st.sidebar.success("✅ Token & link generated!")
        st.sidebar.code(f"Token: {tkn}", language="text")
        st.sidebar.code(f"URL: {url}", language="text")
        st.sidebar.download_button(
            ⬇️ Download token file",
            data=f"{company},{email},{role},{tkn}",
            file_name="token.txt"
        )

# ---------------- ACCESS CONTROL -----------------
qs        = st.query_params
admin_key = qs.get("admin")
token_q   = qs.get("token")

mode        = None   # "owner" | "client" | None
client_role = None

if admin_key == OWNER_KEY:
    mode = "owner"
elif token_q:
    info = verify_token(token_q)
    if info:
        mode        = "client"
        client_role = info["role"]

if mode is None:
    st.sidebar.error("Access denied. Invalid or expired token.")
    st.info("Open with ?admin=OWNER_KEY (owner) أو بـ ?token=CODE (client).")
    st.stop()

# ---------------- MAIN -----------------
if mode == "owner":
    st.sidebar.success("Authorized: owner")
    token_manager_ui()
else:
    st.sidebar.success(f"Authorized: {client_role or 'client'}")

st.title("Owner — Warehouse Orders (Demo)" if mode == "owner" else "Warehouse Orders")

df = load_orders()
lk = load_lookups()
statuses = lk[lk["Type"] == "Status"]["Value"].tolist()

warehouses = sorted(df["Warehouse"].unique())
tabs = st.tabs(warehouses)

for i, wh in enumerate(warehouses):
    with tabs[i]:
        sub = df[df["Warehouse"] == wh].copy()
        kpi_block(sub)
        st.subheader(f"{wh} Orders")
        st.dataframe(sub.sort_values("OrderDate", ascending=False), use_container_width=True, height=320)

        # تحديث الطلب (مقفول على viewer)
        with st.form(f"upd_{wh}"):
            order_ids  = sub["OrderID"].tolist()
            order_id   = st.selectbox("OrderID", order_ids, key=f"oid_{wh}")
            cur_status = sub.loc[sub["OrderID"] == order_id, "Status"].iloc[0] if order_id else statuses[0]
            new_status = st.selectbox("New Status", statuses, index=statuses.index(cur_status))
            new_invoice = st.text_input(
                "Invoice No (optional)",
                value=str(sub.loc[sub["OrderID"] == order_id, "InvoiceNo"].iloc[0]) if order_id else ""
            )
            disable_update = (mode == "client" and client_role == "viewer")
            ok = st.form_submit_button("Update", disabled=disable_update)

        if ok and order_id:
            idx = df.index[df["OrderID"] == order_id]
            if len(idx) == 0:
                st.error("Order not found.")
            else:
                i0          = idx[0]
                old_status  = df.at[i0, "Status"]
                old_invoice = str(df.at[i0, "InvoiceNo"])
                df.at[i0, "Status"]    = new_status
                df.at[i0, "InvoiceNo"] = new_invoice
                df.at[i0, "UpdatedBy"] = "owner" if mode == "owner" else client_role
                df.at[i0, "UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                save_orders(df)
                append_log({
                    "Timestamp":  datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "User":       "owner" if mode == "owner" else client_role,
                    "Warehouse":  wh,
                    "OrderID":    order_id,
                    "FromStatus": old_status,
                    "ToStatus":   new_status,
                    "FromInvoice": old_invoice,
                    "ToInvoice":   new_invoice,
                })
                st.success(f"Order {order_id} updated.")
                st.cache_data.clear()
