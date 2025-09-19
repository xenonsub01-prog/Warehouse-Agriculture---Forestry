
import os
import pandas as pd
import streamlit as st
from datetime import datetime

# ---------------- CONFIG -----------------
DATA_DIR = "data"
ORDERS_FILE = os.path.join(DATA_DIR, "orders.csv")
LOOKUPS_FILE = os.path.join(DATA_DIR, "lookups.csv")
LOG_FILE = os.path.join(DATA_DIR, "log.csv")

# OWNER KEY (change in Streamlit secrets or here for local runs)
OWNER_KEY = st.secrets.get("OWNER_KEY", "admin12345")

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
    import csv
    exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Timestamp","User","Warehouse","OrderID","FromStatus","ToStatus","FromInvoice","ToInvoice"])
        if not exists:
            w.writeheader()
        w.writerow(row)

def kpi_block(df: pd.DataFrame):
    c1,c2,c3,c4 = st.columns(4)
    open_cnt = int((df["Status"] != "Invoiced").sum())
    overdue_cnt = int(((pd.Timestamp("today").normalize() - df["OrderDate"]).dt.days > 7).sum())
    today_cnt = int((df["OrderDate"].dt.date == pd.Timestamp("today").date()).sum())
    invoiced_cnt = int((df["Status"] == "Invoiced").sum())
    c1.metric("Open", open_cnt)
    c2.metric("Overdue (>7d)", overdue_cnt)
    c3.metric("Today", today_cnt)
    c4.metric("Invoiced", invoiced_cnt)

# ---------------- AUTH -----------------
qs = st.query_params
admin_key = qs.get("admin", None)

if admin_key != OWNER_KEY:
    st.sidebar.error("Access denied. Invalid or expired token.")
    st.info("Open with ?admin=YOUR_OWNER_KEY to access the demo as owner.")
    st.stop()

st.sidebar.success("Authorized: owner")
st.title("Owner — Warehouse Orders (Demo)")

# ---------------- MAIN -----------------
df = load_orders()
lk = load_lookups()
statuses = lk[lk["Type"]=="Status"]["Value"].tolist()

warehouses = sorted(df["Warehouse"].unique())
tabs = st.tabs(warehouses)

for i, wh in enumerate(warehouses):
    with tabs[i]:
        sub = df[df["Warehouse"]==wh].copy()
        kpi_block(sub)
        st.subheader(f"{wh} Orders")
        st.dataframe(sub.sort_values("OrderDate", ascending=False), use_container_width=True, height=320)

        with st.form(f"upd_{wh}"):
            order_ids = sub["OrderID"].tolist()
            order_id = st.selectbox("OrderID", order_ids, key=f"oid_{wh}")
            cur_status = sub.loc[sub["OrderID"]==order_id, "Status"].iloc[0] if order_id else statuses[0]
            new_status = st.selectbox("New Status", statuses, index=statuses.index(cur_status))
            new_invoice = st.text_input("Invoice No (optional)", value=str(sub.loc[sub["OrderID"]==order_id, "InvoiceNo"].iloc[0]) if order_id else "")
            ok = st.form_submit_button("Update")
        if ok and order_id:
            idx = df.index[df["OrderID"]==order_id]
            if len(idx)==0:
                st.error("Order not found.")
            else:
                i0 = idx[0]
                old_status = df.at[i0, "Status"]
                old_invoice = str(df.at[i0, "InvoiceNo"])
                df.at[i0, "Status"] = new_status
                df.at[i0, "InvoiceNo"] = new_invoice
                df.at[i0, "UpdatedBy"] = "owner"
                df.at[i0, "UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds")+"Z"
                save_orders(df)
                append_log({
                    "Timestamp": datetime.utcnow().isoformat(timespec="seconds")+"Z",
                    "User": "owner",
                    "Warehouse": wh,
                    "OrderID": order_id,
                    "FromStatus": old_status,
                    "ToStatus": new_status,
                    "FromInvoice": old_invoice,
                    "ToInvoice": new_invoice,
                })
                st.success(f"Order {order_id} updated.")
                st.cache_data.clear()
