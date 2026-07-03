import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
from datetime import datetime,date
from frontend.api_client import api_post, api_get

CATEGORIES = [
    "Groceries",
    "Electronics",
    "Clothing",
    "Kitchen",
    "Stationery",
    "Home & Living",
    "Spices",
    "Beverages",
    "Personal Care",
    "Sports & Fitness",
    "Other"
]

def show_upload_page():
    "Renders the full upload page."
    if st.session_state.get("role")!="admin":
        st.error("You do not have permission to access this page.")
        st.stop()
        
    st.title("Upload Sales Data")
    st.markdown("Use this page to add sales record to the pipeline")
    
    st.markdown("---")
    
    st.header("Upload CSV File")
    
    with st.expander("Required CSV Format- click to expand",expanded=True):
        st.markdown("""
                   Your CSV file must contain these **exact column names**:

                    | Column     | Type    | Example          | Rules              |
                    |------------|---------|------------------|--------------------|
                    | `date`     | Date    | `2024-01-15`     | Cannot be future   |
                    | `product`  | Text    | `Basmati Rice 5kg` | Required, non-empty |
                    | `category` | Text    | `Groceries`      | Required, non-empty |
                    | `qty`      | Integer | `10`             | Must be > 0        |
                    | `price`    | Float   | `250.00`         | Must be > 0        |
                   """)
    st.markdown(" ")
    
    uploaded_file = st.file_uploader(
        "Choose a CSV FIle to upload",
        type=["csv"],
        help="Upload a .csv file with sales data. Max Size: 200MB",
        key="csv_file_uploader"
    )
    
    if uploaded_file is not None:
        try:
            preview_df = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Could not read the CSV file: {str(e)}. Please make sure it's a valid CSV file.")
            st.stop()

        total_rows = len(preview_df)
        st.markdown(f"**File:** {uploaded_file.name} - **{total_rows}** rows found")
        st.subheader("Preview (first 5 rows):")
        st.dataframe(preview_df.head(5),use_container_width=True)

        required_cols = {"date","product","category","qty","price"}
        actual_cols = set(preview_df.columns.str.strip().str.lower())
        missing_cols = required_cols - actual_cols

        if missing_cols:
            st.error(f"This CSV File has missing columns {missing_cols}")
        else:
            st.success("All required columns found")

            upload_col,_ = st.columns([1,3])

            with upload_col:
                upload_clicked = st.button("Upload to database",type="primary",use_container_width=True,key="csv_upload_btn")

            if upload_clicked:
                with st.spinner("Uploading to database"):
                    file_bytes = uploaded_file.getvalue()
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
                if success:
                    inserted = response_data.get("inserted",0)
                    skipped = response_data.get("skipped",0)

                    st.success(f"Upload complete: inserted **{inserted} rows** and skipped **{skipped} rows**")
                    st.balloons()
                else:
                    if status_code == 401:
                        st.error("Session expired. Please log out and log in again.")
                    elif status_code == 403:
                        st.error("Admin access required to upload data.")
                    elif status_code == 400:
                        st.error(f"Upload failed: {response_data}")
                    elif status_code == 0:
                        st.error(f"Connection error: {response_data}")
                    else:
                        st.error(f"Upload failed (status {status_code}): {response_data}")

    st.markdown("---")
    
    st.header("Add a Single Sale Manually")
    st.markdown("Use this form to add one sale record at a time")
    
    with st.form("manual_entry_form",clear_on_submit=True):
        col1,col2 = st.columns(2)
    
        with col1:
            sale_date = st.date_input(
                "Sale Date",
                value=date.today(),
                max_value=date.today(),
                help="Date the sale occured",
                key="manual_date"
            )
            sale_qty = st.number_input(
                "Quantity",
                min_value=1,
                max_value=10000,
                value=1,
                step=1,
                help="Number of units sold",
                key="manual_qty"
            )
            sale_category=st.selectbox(
                "Category",
                options=CATEGORIES,
                index=0,
                help="Product Category",
                key="manual_category"
            )
            
        with col2:
            sale_product = st.text_input(
                "Product Name",
                placeholder="e.g., Basmati RIce 5kg",
                max_chars=200,
                help="Full product name",
                key="manual_product"
            )
            sale_price = st.number_input(
                "Price per unit",
                min_value=0.01,
                value=1.0,
                step=0.50,
                format="%.2f",
                help="Price per single unit per rupees",
                key="manual_price"
            )
            estimated_total = sale_qty*sale_price
            st.metric(label="Estimated Total",value=f"Rs. {estimated_total}")
            submit_manual = st.form_submit_button("Save Sale Record",type="primary",use_container_width=True)
            
            if submit_manual:
                if not sale_product.strip():
                    st.error("Product name cannot be empty")
                else:
                    with st.spinner("Saving Sale Record..."):
                        success, response_data, status_code = api_post(
                            "/sales/upload-manual",
                            token=st.session_state["token"],
                            data={
                                "date":sale_date.strftime("%Y-%m-%d"),
                                "product":sale_product.strip(),
                                "category":sale_category,
                                "qty":int(sale_qty),
                                "price":float(sale_price)
                            }
                        )
                    if success:
                        st.success(f"Sale record saved for **{sale_product.strip()}** of quantity: **{sale_qty}** with an estimated total of: **{estimated_total}**")
                    else:
                        if status_code == 401:
                            st.error("Session expired. Please log out and log in again.")
                        elif status_code == 403:
                            st.error("Admin access required.")
                        elif status_code == 422:
                            st.error(f"Validation error: {response_data}")
                            # 422 = Pydantic validation failed on the backend
                        elif status_code == 0:
                            st.error(f"Connection error: {response_data}")
                        else:
                            st.error(f"Failed to save: {response_data}")
    
    st.markdown("---")
    
#Recent Uploads Table:
    
    st.header("Recent Uploads")
    st.markdown("Records waiting to be processed by the pipeline (status: 'pending').")
    
    refresh_col, _ = st.columns([1,5])
    with refresh_col:
        refresh_clicked = st.button(
            "Refresh",
            key="refresh_recent",
            help="Reload the latest records from the database"
        )
    
    with st.spinner("Loading Recent Uploads..."):
        success, raw_data, status_code = api_get(
            "/sales/raw",
            token=st.session_state["token"],
            params={"status":"pending"}
        )
    
    if success:
        if len(raw_data) ==0:
            st.info("""No pending records found.
                    Upload a CSV or add a manual entry above to get started""")
        else:
            df=pd.DataFrame(raw_data)
            display_columns={
                "id":"ID",
                "date":"Sale Date",
                "product":"Product",
                "category":"Category",
                "qty":"Quantity",
                "price":"Price(in Rupees)",
                "status":"Status",
                "uploaded_by":"Uploaded by (User ID)"
            }
            available_cols = [c for c in display_columns.keys() if c in df.columns]
            df_display = df[available_cols].rename(columns=display_columns)
            
            if "Sale Date" in df_display.columns:
                df_display["Sale Date"] = pd.to_datetime(
                    df_display["Sale Date"]
                ).dt.strftime("%d %b %Y")
            if "Price(in Rupees)" in df_display.columns:
                df_display["Price(in Rupees)"] = df_display["Price(in Rupees)"].apply(
                    lambda x:f"Rs.{x:,.2f}"
                )
            
            stat_col1, stat_col2, stat_col3 = st.columns(3)
            with stat_col1:
                st.metric("Total Pending Records", len(df))
            with stat_col2:
                if "Qty" in df_display.columns:
                    st.metric("Total Units", int(df["qty"].sum()))
            with stat_col3:
                if "price" in df.columns and "qty" in df.columns:
                    total_value = (df["price"] * df["qty"]).sum()
                    st.metric("Total Value", f"₹{total_value:,.2f}")
            st.dataframe(df_display,use_container_width=True,hide_index=True)
    
    else:
        if status_code == 401:
            st.error("Session expired. Please log out and log in again.")
        elif status_code == 0:
            st.error(f"Cannot connect to server: {raw_data}")
        else:
            st.error(f"Failed to load records: {raw_data}")