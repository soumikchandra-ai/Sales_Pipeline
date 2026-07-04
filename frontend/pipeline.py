import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
from frontend.api_client import api_get, api_post

def show_pipeline_page():
    "Renders the full pipeline page."
    
    st.title("ETL Pipeline")
    st.markdown(
        "This page shows the status of your sales data pipeline."
        "**Pending** records have been uploaded but not yet processed."
        "Running the pipeline calculates totals, tax, and discounts."
    )
    st.markdown("---")
    
    st.header("Pipeline Status")
    
    #Fetch pending records to show the count
    pending_success, pending_data, pending_status = api_get(
        "/sales/raw",
        token=st.session_state.get("token"),
        params={"status":"pending"}
    )
    
    #Fetch processed records to show that count also
    processed_success, processed_data, processed_status = api_get(
        "/sales/processed",
        token=st.session_state.get("token")
    )
    
    #Status metric cards
    col1, col2, col3 = st.columns(3)
    
    with col1:
        pending_count = len(pending_data) if pending_success else 0
        st.metric(
            label="Pending Records",
            value=pending_count,
            help="Raw sales uploaded but not yet processed by the pipeline"
        )
        
    with col2:
        processed_count = len(processed_data) if processed_success else 0
        st.metric(
            label="Processed Records",
            value=processed_count,
            help="Raw that have been through the ETL pipeline"
        )
        
    with col3:
        if processed_success and len(processed_data)>0:
            df_proc=pd.DataFrame(processed_data)
            total_revenue=df_proc["final_amount"].sum()
            st.metric(
                label="Total Revenue",
                value=f"Rs. {total_revenue:,.2f}",
                help="Sum of all final_amount from processed sales"
            )
        else:
            st.metric(
                label="Total Revenue",
                value="Rs. 0.0",
                help="No sales processed yet."
            )
    st.markdown("---")
    
    st.header("Run Pipeline")
    is_admin = st.session_state.get("role")=="admin"
    
    if not is_admin:
        st.warning("You need **admin** access to run the pipeline.")
        
        st.button(
            "Run ETL Pipeline",
            disabled=True,
            use_container_width=False
        )
        
    else:
        if pending_count==0:
            st.info("No pending records to process.")
            st.button(
                "Run ETL Pipeline",
                disabled=True,
                help="No pending records to process",
                use_container_width=False
            )
            
        else:
            st.markdown(
                f"Ready to process **{pending_count} pending record(s)** "
                "Click below to run the ETL Pipeline."
            )
            
            run_col,_ = st.columns([2,5])
            with run_col:
                run_clicked = st.button(
                    f"Run ETL Pipeline({pending_count} records)",
                    type="primary",
                    use_container_width=True,
                    key="run_pipeline_btn"
                )
            if run_clicked:
                with st.spinner("Running pipeline.... please wait.."):
                    success, response_data, status_code = api_post(
                        "/pipeline/run",
                        token=st.session_state.get("token")
                    )
                if success:
                    processed_now = response_data.get("processed",0)
                    found = response_data.get("pending_records_found",0)
                    msg = response_data.get("message","Pipeline COmplete")
                    st.success(f"{msg}")
                    
                    result_col1, result_col2 = st.columns(2)
                    with result_col1:
                        st.metric("Records Found",found)
                    with result_col2:
                        st.metric("Records Processed",processed_now)
                    
                    if processed_now ==0:
                        st.info("The pipeline endpoint is connected and responding")
                
                else:
                    if status_code == 403:
                        st.error("Admin access required to run the pipeline.")
                    elif status_code == 0:
                        st.error(
                            f"Cannot connect to the backend server.\n\n"
                            f"Details: {response_data}"
                        )
                    else:
                        st.error(f"Pipeline failed: {response_data}") 
    
    st.markdown("---")
    
    st.header("Processed Records")
    
    refresh_col, _ = st.columns([1,6])
    with refresh_col:
        st.button("Refresh",key="refresh_processed")
        
        if processed_success:
            if len(processed_data)==0:
                st.info("No processed records yet. Run the pipeline to process pending records.")
                
            else:
                df=pd.DataFrame(processed_data)
                display_columns = {
                    "id": "ID",
                    "raw_id": "Raw Sale ID",
                    "total": "Subtotal (Rs.)",
                    "tax": "Tax (Rs.)",
                    "discount": "Discount (Rs.)",
                    "final_amount": "Final Amount (Rs.)",
                    "processed_at": "Processed At"
                }
                available_cols = [c for c in display_columns.key() if c in df.columns]
                df_display = df[available_cols].rename(columns=display_columns)
                
                currency_cols = ["Subtotal (Rs.)", "Tax (Rs.)", "Discount (Rs.)", "Final Amount (Rs.)"]
                for col in currency_cols:
                    if col in df_display.columns:
                        df_display[col] = df_display[col].apply(
                            lambda x: f"₹{x:,.2f}" if pd.notna(x) else "₹0.00"
                        )

                if "Processed At" in df_display.columns:
                    df_display["Processed At"] = pd.to_datetime(
                        df_display["Processed At"]
                    ).dt.strftime("%d %b %Y, %H:%M")

                if "final_amount" in df.columns:
                    total_rev = df["final_amount"].sum()
                    avg_sale = df["final_amount"].mean()
                    
                    
                    sum_col1, sum_col2, sum_col3 = st.columns(3)
                    with sum_col1:
                        st.metric("Total Records", len(df))
                    with sum_col2:
                        st.metric("Total Revenue", f"₹{total_rev:,.2f}")
                    with sum_col3:
                        st.metric("Avg Sale Value", f"₹{avg_sale:,.2f}")

                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True
                )

        else:
            if processed_status == 0:
                st.error(
                    f"Cannot connect to the backend server. "
                    f"Is it running at {os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')}?"
                )
            else:
                st.error(f"Failed to load processed records: {processed_data}")