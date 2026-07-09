import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
from datetime import date, datetime
from frontend.api_client import api_post, api_get

CATEGORIES = [
    "Groceries", "Electronics", "Clothing", "Kitchen",
    "Stationery", "Home & Living", "Spices", "Beverages",
    "Personal Care", "Sports & Fitness", "Other"
]


def show_upload_page():
    """Renders the Upload Sales Data page. Admin only."""
    if st.session_state.get("role") != "admin":
        st.warning("You do not have permission to access this page.")
        st.stop()

    st.title("Upload Sales Data")
    st.caption("Add sales records to the pipeline via CSV upload or manual entry.")
    st.divider()

    st.header("Upload CSV File")

    with st.expander("Required CSV Format", expanded=True):
        st.markdown("""
        Your CSV must contain these **exact column names**:

        | Column | Type | Example | Rules |
        |---|---|---|---|
        | `date` | Date | `2024-01-15` | Cannot be future |
        | `product` | Text | `Basmati Rice 5kg` | Non-empty |
        | `category` | Text | `Groceries` | Non-empty |
        | `qty` | Integer | `10` | Must be > 0 |
        | `price` | Float | `250.00` | Must be > 0 |

        Extra columns are ignored.
        Rows with invalid values are skipped and counted.
        """)

    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=["csv"],
        help="Upload a .csv file with sales data",
        key="csv_file_uploader"
    )

    if uploaded_file is not None:
        try:
            preview_df = pd.read_csv(uploaded_file)
            total_rows = len(preview_df)

            st.markdown(
                f"**File:** `{uploaded_file.name}` — "
                f"**{total_rows} rows**, "
                f"**{len(preview_df.columns)} columns**"
            )

            required_cols = {"date", "product", "category", "qty", "price"}
            actual_cols   = set(preview_df.columns.str.strip().str.lower())
            missing_cols  = required_cols - actual_cols

            if missing_cols:
                st.error(
                    f"Missing required columns: **{sorted(missing_cols)}**. "
                    "Fix the file and re-upload."
                )
            else:
                st.success("All required columns found!")
                st.subheader("Preview (first 5 rows):")
                st.dataframe(preview_df.head(5), use_container_width=True)

                up_col, _ = st.columns([1, 3])
                with up_col:
                    upload_clicked = st.button(
                        "⬆Upload to Database",
                        type="primary",
                        use_container_width=True,
                        key="csv_upload_btn"
                    )

                if upload_clicked:
                    progress_bar = st.progress(0, text="Preparing upload...")
                    progress_bar.progress(20, text="Reading file...")

                    file_bytes = uploaded_file.getvalue()
                    progress_bar.progress(50, text="Sending to server...")

                    success, response_data, status_code = api_post(
                        "/sales/upload-csv",
                        token=st.session_state["token"],
                        files={
                            "file": (
                                uploaded_file.name,
                                file_bytes,
                                "text/csv"
                            )
                        }
                    )

                    progress_bar.progress(90, text="Saving to database...")

                    if success:
                        progress_bar.progress(100, text="Done!")
                        inserted = response_data.get("inserted", 0)
                        skipped  = response_data.get("skipped", 0)
                        st.success(
                            f"Upload complete! "
                            f"**{inserted} rows** inserted, "
                            f"**{skipped} rows** skipped."
                        )
                        st.balloons()
                    else:
                        progress_bar.empty()
                        if status_code == 401:
                            st.error("Session expired. Please log out and log in again.")
                        elif status_code == 403:
                            st.error("Admin access required.")
                        elif status_code == 400:
                            st.error(f"{response_data}")
                        elif status_code == 0:
                            st.error(f"Cannot connect to server: {response_data}")
                        else:
                            st.error(f"Upload failed: {response_data}")

        except Exception as e:
            st.error(f"Could not read the CSV file: {str(e)}")

    st.divider()

    st.header("Add Single Sale Manually")
    st.caption("Enter one sale record at a time using the form below.")

    with st.form("manual_entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            sale_date = st.date_input(
                "Sale Date",
                value=date.today(),
                max_value=date.today(),
                key="manual_date"
            )
            sale_qty = st.number_input(
                "Quantity",
                min_value=1, max_value=100000,
                value=1, step=1,
                key="manual_qty"
            )
            sale_category = st.selectbox(
                "Category",
                options=CATEGORIES,
                key="manual_category"
            )

        with col2:
            sale_product = st.text_input(
                "Product Name",
                placeholder="e.g., Basmati Rice 5kg",
                max_chars=200,
                key="manual_product"
            )
            sale_price = st.number_input(
                "Price per Unit (Rs.)",
                min_value=0.01, max_value=10000000.0,
                value=1.00, step=0.50,
                format="%.2f",
                key="manual_price"
            )
            estimated_total = sale_qty * sale_price
            st.metric("Estimated Total", f"Rs.{estimated_total:,.2f}")

        submit_manual = st.form_submit_button(
            "Save Sale Record",
            type="primary",
            use_container_width=True
        )

        if submit_manual:
            if not sale_product.strip():
                st.error("Product name cannot be empty.")
            else:
                with st.spinner("Saving sale record..."):
                    success, response_data, status_code = api_post(
                        "/sales/upload-manual",
                        token=st.session_state["token"],
                        data={
                            "date": sale_date.strftime("%Y-%m-%d"),
                            "product": sale_product.strip(),
                            "category": sale_category,
                            "qty": int(sale_qty),
                            "price": float(sale_price)
                        }
                    )

                if success:
                    st.success(
                        f"Saved! **{sale_product.strip()}** — "
                        f"Qty: {sale_qty} x Rs.{sale_price:.2f} = "
                        f"Rs.{estimated_total:,.2f}"
                    )
                else:
                    if status_code == 401:
                        st.error("Session expired.")
                    elif status_code == 422:
                        st.error(f"Validation error: {response_data}")
                    elif status_code == 0:
                        st.error(f"Cannot connect to server: {response_data}")
                    else:
                        st.error(f"Failed to save: {response_data}")

    st.divider()

    st.header("Recent Uploads")
    st.caption("Records currently in the system with status breakdown.")

    ref_col, _ = st.columns([1, 6])
    with ref_col:
        st.button("Refresh", key="refresh_recent")

    with st.spinner("Loading records..."):
        all_success, all_data, all_status = api_get(
            "/sales/raw",
            token=st.session_state.get("token")
        )

    if all_success and all_data:
        df_all = pd.DataFrame(all_data)

        with st.expander("View Upload History Summary", expanded=False):
            if "status" in df_all.columns:
                status_counts = (
                    df_all.groupby("status")
                    .size()
                    .reset_index(name="count")
                )
                
                status_counts.columns = ["Status", "Count"]

                def status_label(s):
                    icons = {
                        "pending": "pending",
                        "processed": "processed",
                        "failed": "failed"
                    }
                    return icons.get(s, s)

                status_counts["Status"] = status_counts["Status"].apply(status_label)

                sc1, sc2, sc3 = st.columns(3)
                for i, row in status_counts.iterrows():
                    if i == 0:
                        sc1.metric(row["Status"], row["Count"])
                    elif i == 1:
                        sc2.metric(row["Status"], row["Count"])
                    elif i == 2:
                        sc3.metric(row["Status"], row["Count"])

                st.dataframe(status_counts, use_container_width=True, hide_index=True)

        df_pending = df_all[df_all["status"] == "pending"].copy() \
            if "status" in df_all.columns else df_all

        if df_pending.empty:
            st.info("No pending records. All uploads have been processed.")
        else:
            st.markdown(f"**{len(df_pending)} pending record(s):**")

            display_cols = {
                "id": "ID",
                "date": "Sale Date",
                "product": "Product",
                "category": "Category",
                "qty": "Qty",
                "price": "Price (Rs.)",
                "status": "Status"
            }
            available  = [c for c in display_cols if c in df_pending.columns]
            df_display = df_pending[available].rename(columns=display_cols)

            if "Sale Date" in df_display.columns:
                df_display["Sale Date"] = pd.to_datetime(
                    df_display["Sale Date"], errors="coerce"
                ).dt.strftime("%d %b %Y")

            if "Price (Rs.)" in df_display.columns:
                df_display["Price (Rs.)"] = df_display["Price (Rs.)"].apply(
                    lambda x: f"Rs.{x:,.2f}" if pd.notna(x) else "Rs.0.00"
                )

            st1, st2, st3 = st.columns(3)
            st1.metric("Pending Records", len(df_pending))
            if "qty" in df_pending.columns:
                st2.metric("Total Units", int(df_pending["qty"].sum()))
            if "price" in df_pending.columns and "qty" in df_pending.columns:
                val = (df_pending["price"] * df_pending["qty"]).sum()
                st3.metric("Total Value", f"Rs.{val:,.2f}")

            st.dataframe(df_display, use_container_width=True, hide_index=True)

    elif not all_success:
        if all_status == 0:
            st.error("Cannot connect to server.")
        else:
            st.error(f"Failed to load records: {all_data}")
    else:
        st.info("No records uploaded yet.")