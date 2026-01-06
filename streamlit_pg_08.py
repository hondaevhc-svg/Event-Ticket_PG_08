import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# -------------------------------------------------
# BASIC CONFIG
# -------------------------------------------------
st.set_page_config(page_title="🎟️ Event Management System", layout="wide")

# --- CSS: center align table content ---
st.markdown("""
    <style>
    [data-testid="stTable"] td, [data-testid="stTable"] th {
        text-align: center !important;
    }
    div[data-testid="stDataFrame"] div[class^="st-"] {
        text-align: center !important;
    }
    .stDataFrame th {
        text-align: center !important;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
if "admin_pass" not in st.session_state:
    st.session_state.admin_pass = ""
if "menu_pass" not in st.session_state:
    st.session_state.menu_pass = ""

def clear_admin_pass():
    st.session_state.admin_pass = ""

def clear_menu_pass():
    st.session_state.menu_pass = ""

# -------------------------------------------------
# DB CONNECTION & CACHED LOAD
# -------------------------------------------------
def get_engine():
    db_url = st.secrets["connections"]["postgresql"]["url"]
    return create_engine(db_url)

@st.cache_data(ttl=60)
def load_all_data():
    engine = get_engine()
    tickets_df = pd.read_sql("SELECT * FROM tickets", engine)
    menu_df = pd.read_sql("SELECT * FROM menu", engine)

    tickets_df["Visitor_Seats"] = tickets_df["Visitor_Seats"].fillna(0)
    tickets_df["Sold"] = tickets_df["Sold"].fillna(False).astype(bool)
    tickets_df["Visited"] = tickets_df["Visited"].fillna(False).astype(bool)
    tickets_df["Customer"] = tickets_df["Customer"].fillna("")
    tickets_df["Admit"] = pd.to_numeric(tickets_df["Admit"], errors="coerce").fillna(1)
    tickets_df["Seq"] = pd.to_numeric(tickets_df["Seq"], errors="coerce")
    tickets_df["TicketID"] = tickets_df["TicketID"].astype(str).str.zfill(4)

    return tickets_df, menu_df

def save_tickets_df(tickets_df):
    engine = get_engine()
    tickets_df.to_sql("tickets", engine, if_exists="replace", index=False)
    st.cache_data.clear()

def save_menu_df(menu_df):
    engine = get_engine()
    menu_df.to_sql("menu", engine, if_exists="replace", index=False)
    st.cache_data.clear()

def save_both(tickets_df, menu_df):
    engine = get_engine()
    tickets_df.to_sql("tickets", engine, if_exists="replace", index=False)
    menu_df.to_sql("menu", engine, if_exists="replace", index=False)
    st.cache_data.clear()

def custom_sort(df: pd.DataFrame) -> pd.DataFrame:
    if "Seq" not in df.columns:
        return df
    return (
        df.assign(
            sort_key=df["Seq"].apply(
                lambda x: 10 if x in [0, "0", None] else int(x)
            )
        )
        .sort_values("sort_key")
        .drop(columns="sort_key")
    )

tickets, menu = load_all_data()

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("Admin Settings")

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    admin_pass_input = st.text_input(
        "Reset Database Password",
        type="password",
        key="admin_pass",
    )

    if st.button("🚨 Reset Database", use_container_width=True):
        if admin_pass_input == "admin123":
            tickets["Sold"] = False
            tickets["Visited"] = False
            tickets["Customer"] = ""
            tickets["Visitor_Seats"] = 0
            tickets["Timestamp"] = None
            save_tickets_df(tickets)
            clear_admin_pass()
            st.success("Database has been reset.")
            st.rerun()
        else:
            st.error("Incorrect Admin Password")

# -------------------------------------------------
# TABS
# -------------------------------------------------
tab_labels = ["📊 Dashboard", "💰 Sales", "🚶 Visitors", "⚙️ Edit Menu"]
tabs = st.tabs(tab_labels)

# -------------------------------------------------
# 1. DASHBOARD
# -------------------------------------------------
with tabs[0]:
    st.subheader("Inventory & Visitor Analytics")
    df = tickets.copy()

    summary = (
        df.groupby(["Seq", "Type", "Category", "Admit"])
        .agg(
            Total_Tickets=("TicketID", "count"),
            Tickets_Sold=("Sold", "sum"),
            Total_Visitors=("Visitor_Seats", "sum"),
        )
        .reset_index()
    )

    summary["Total_Seats"] = summary["Total_Tickets"] * summary["Admit"]
    summary["Seats_sold"] = summary["Tickets_Sold"] * summary["Admit"]
    summary["Balance_Tickets"] = summary["Total_Tickets"] - summary["Tickets_Sold"]
    summary["Balance_Seats"] = summary["Total_Seats"] - summary["Seats_sold"]
    summary["Balance_Visitors"] = summary["Seats_sold"] - summary["Total_Visitors"]

    column_order = [
        "Seq",
        "Type",
        "Category",
        "Admit",
        "Total_Tickets",
        "Tickets_Sold",
        "Total_Seats",
        "Seats_sold",
        "Total_Visitors",
        "Balance_Tickets",
        "Balance_Seats",
        "Balance_Visitors",
    ]

    summary = custom_sort(summary[column_order])
    totals = pd.DataFrame([summary.select_dtypes(include="number").sum()])
    totals["Seq"] = "Total"
    summary_final = pd.concat([summary, totals], ignore_index=True).dropna(how="all")

    st.dataframe(
        summary_final,
        hide_index=True,
        use_container_width=True,
        height=450,
    )

# -------------------------------------------------
# 2. SALES
# -------------------------------------------------
with tabs[1]:
    st.subheader("Sales Management")
    col_in, col_out = st.columns([1, 1.2])

    with col_in:
        sale_tab = st.radio(
            "Action",
            ["Manual", "Bulk Upload", "Reverse Sale"],
            horizontal=True,
        )

        # ---------- Manual Sale ----------
        if sale_tab == "Manual":
            s_type = st.radio("Type", ["Public", "Guest"], horizontal=True)
            s_cat = st.selectbox(
                "Category",
                menu[menu["Type"] == s_type]["Category"],
            )

            avail = tickets[
                (tickets["Type"] == s_type)
                & (tickets["Category"] == s_cat)
                & (~tickets["Sold"])
            ]["TicketID"].tolist()

            if avail:
                with st.form("sale_form", clear_on_submit=True):
                    tid = st.selectbox("Ticket ID", avail)
                    cust = st.text_input("Customer Name")
                    confirm = st.form_submit_button("Confirm Sale")

                    if confirm:
                        idx = tickets.index[tickets["TicketID"] == tid][0]
                        tickets.at[idx, "Sold"] = True
                        tickets.at[idx, "Customer"] = cust
                        tickets.at[idx, "Timestamp"] = str(pd.Timestamp.now())
                        save_tickets_df(tickets)
                        st.success(f"Ticket {tid} sold to {cust}.")
                        st.rerun()
            else:
                st.info("No available tickets in this category.")

        # ---------- Reverse Sale ----------
        elif sale_tab == "Reverse Sale":
            r_type = st.radio("Type", ["Public", "Guest"], horizontal=True, key="rs_type")
            r_cat = st.selectbox(
                "Category",
                menu[menu["Type"] == r_type]["Category"],
                key="rs_cat",
            )

            sold_tickets = tickets[
                (tickets["Type"] == r_type)
                & (tickets["Category"] == r_cat)
                & (tickets["Sold"])
            ]["TicketID"].tolist()

            if sold_tickets:
                with st.form("reverse_sale_form"):
                    tid = st.selectbox("Ticket ID to reverse", sold_tickets)
                    confirm = st.form_submit_button("Reverse Sale")

                    if confirm:
                        idx = tickets.index[tickets["TicketID"] == tid][0]
                        tickets.at[idx, "Sold"] = False
                        tickets.at[idx, "Customer"] = ""
                        tickets.at[idx, "Visited"] = False
                        tickets.at[idx, "Visitor_Seats"] = 0
                        tickets.at[idx, "Timestamp"] = None
                        save_tickets_df(tickets)
                        st.success(f"Sale reversed for Ticket {tid}.")
                        st.rerun()
            else:
                st.info("No sold tickets to reverse in this category.")

        else:
            st.info("Bulk Upload not implemented yet.")

    with col_out:
        st.write("**Recent Sales History**")
        recent_sales = tickets[tickets["Sold"]].sort_values(
            "Timestamp", ascending=False
        ).copy()

        if not recent_sales.empty:
            recent_sales.insert(0, "Sno", range(1, len(recent_sales) + 1))
            st.dataframe(
                recent_sales[["Sno", "TicketID", "Category", "Customer", "Timestamp"]],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No sales recorded yet.")

# -------------------------------------------------
# 3. VISITORS
# -------------------------------------------------
with tabs[2]:
    st.subheader("Visitor Entry Management")
    v_in, v_out = st.columns([1, 1.2])

    with 
