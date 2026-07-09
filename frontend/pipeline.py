import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
from datetime import datetime
from frontend.api_client import api_get, api_post

def show_pipeline_page():
    """Renders the Pipeline page. Admin only for running pipeline."""

    if st.session_state.get("role") != "admin":
        st.warning("Admin access required to access this page.")
        st.stop()

    st.title("ETL Pipeline")
    st.caption(
        "Process pending sales records through the ETL pipeline — "
        "clean, validate, calculate financials, and store results."
    )
    st.divider()

    st.header("Current Status")

    with st.spinner("Loading pipeline status..."):
        pending_success, pending_data, _ = api_get(
            "/sales/raw",
            token=st.session_state.get("token"),
            params={"status": "pending"}
        )
        processed_success, processed_data, _ = api_get(
            "/sales/processed",
            token=st.session_state.get("token")
        )
        failed_success, failed_data, _ = api_get(
            "/sales/raw",
            token=st.session_state.get("token"),
            params={"status": "failed"}
        )

    pending_count = len(pending_data) if pending_success else 0
    processed_count = len(processed_data) if processed_success else 0
    failed_count = len(failed_data) if failed_success else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Pending", pending_count, help="Ready to be processed")
    with col2:
        st.metric("Processed", processed_count, help="Successfully through pipeline")
    with col3:
        st.metric("Failed", failed_count, help="Rejected during validation")
    with col4:
        if processed_success and processed_data:
            df_p = pd.DataFrame(processed_data)
            rev  = df_p["final_amount"].sum() if "final_amount" in df_p.columns else 0
            st.metric("Total Revenue", f"Rs.{rev:,.2f}")
        else:
            st.metric("Total Revenue", "Rs.0.00")

    st.divider()
    
    st.header("Run Pipeline")

    if pending_count == 0:
        st.info(
            "No pending records to process. "
            "Go to the **Upload** page to add sales data first."
        )
        st.button("Run ETL Pipeline", disabled=True, key="run_btn_disabled")

    else:
        st.markdown(
            f"**{pending_count}** pending record(s) ready. "
            f"Click below to run the full ETL pipeline."
        )

        run_col, _ = st.columns([2, 5])
        with run_col:
            run_clicked = st.button(
                f"Run ETL Pipeline ({pending_count} records)",
                type="primary",
                use_container_width=True,
                key="run_pipeline_btn"
            )

        if run_clicked:
            with st.spinner("Running ETL pipeline... please wait"):
                result = api_post(
                    "/pipeline/run",
                    token=st.session_state.get("token")
                )

            if result is None:
                st.error("Unexpected error: no response from server.")
            else:
                success, response_data, status_code = result

                if success:
                    st.success(
                        f"{response_data.get('message', 'Pipeline complete!')}"
                    )

                    st.subheader("This Run's Results")
                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("Loaded", response_data.get("total_loaded", 0))
                    m2.metric("Processed", response_data.get("processed", 0))
                    m3.metric("Failed", response_data.get("failed", 0))
                    m4.metric("Duplicates",response_data.get("skipped_duplicates", 0))
                    m5.metric("Revenue", f"Rs.{response_data.get('total_revenue', 0):,.2f}")
                    m6.metric("Tax", f"Rs.{response_data.get('tax_collected', 0):,.2f}")

                    with st.expander("View Run Details", expanded=False):
                        details = {
                            "Metric" : [
                                "Total Loaded", "Processed", "Failed",
                                "Duplicates Skipped", "Total Revenue", "Tax Collected"
                            ],
                            "Value"       : [
                                response_data.get("total_loaded", 0),
                                response_data.get("processed", 0),
                                response_data.get("failed", 0),
                                response_data.get("skipped_duplicates", 0),
                                f"Rs.{response_data.get('total_revenue', 0):,.2f}",
                                f"Rs.{response_data.get('tax_collected', 0):,.2f}"
                            ]
                        }
                        st.dataframe(
                            pd.DataFrame(details),
                            use_container_width=True,
                            hide_index=True
                        )

                        if response_data.get("failed", 0) > 0:
                            st.markdown("**Failed Record Reasons:**")
                            with st.spinner("Loading failed records..."):
                                fail_ok, fail_data, _ = api_get(
                                    "/sales/raw",
                                    token=st.session_state.get("token"),
                                    params={"status": "failed"}
                                )
                            if fail_ok and fail_data:
                                df_fail = pd.DataFrame(fail_data)
                                if "fail_reason" in df_fail.columns:
                                    reasons = (
                                        df_fail["fail_reason"]
                                        .dropna()
                                        .str.split(":").str[0]
                                        .value_counts()
                                        .reset_index()
                                    )
                                    reasons.columns = ["Reason Type", "Count"]
                                    st.dataframe(
                                        reasons,
                                        use_container_width=True,
                                        hide_index=True
                                    )

                else:
                    if status_code == 403:
                        st.error("Admin access required.")
                    elif status_code == 0:
                        st.error(f"Cannot connect to server: {response_data}")
                    elif status_code == 500:
                        st.error(f"Pipeline crashed: {response_data}")
                    else:
                        st.error(f"Pipeline failed: {response_data}")

    st.divider()

    st.header("Pipeline Run History")
    st.caption("Last 10 pipeline executions.")

    ref_col, _ = st.columns([1, 6])
    with ref_col:
        st.button("Refresh", key="refresh_history")

    with st.spinner("Loading run history..."):
        hist_success, hist_data, hist_status = api_get(
            "/pipeline/history",
            token=st.session_state.get("token"),
            params={"limit": 10}
        )

    if hist_success and hist_data:
        df_hist = pd.DataFrame(hist_data)

        if "run_at" in df_hist.columns:
            df_hist["run_at"] = pd.to_datetime(
                df_hist["run_at"], errors="coerce"
            ).dt.strftime("%d %b %Y, %H:%M")

        currency_cols = ["total_revenue", "tax_collected"]
        for col in currency_cols:
            if col in df_hist.columns:
                df_hist[col] = df_hist[col].apply(
                    lambda x: f"Rs.{x:,.2f}" if pd.notna(x) else "Rs.0.00"
                )

        col_map = {
            "id": "Run #",
            "run_at": "Run At",
            "triggered_by": "Triggered By",
            "total_loaded": "Loaded",
            "processed": "Processed",
            "failed": "Failed",
            "skipped_duplicates": "Duplicates",
            "total_revenue": "Revenue",
            "tax_collected": "Tax"
        }
        available = [c for c in col_map if c in df_hist.columns]
        df_display = df_hist[available].rename(columns=col_map)

        st.dataframe(df_display, use_container_width=True, hide_index=True)

    elif hist_success and not hist_data:
        st.info("No pipeline runs recorded yet. Run the pipeline above.")
    else:
        if hist_status == 0:
            st.error("Cannot connect to server.")
        else:
            st.error(f"Failed to load history: {hist_data}")

    st.divider()

    with st.expander("View All Processed Records", expanded=False):
        if processed_success and processed_data:
            df_proc = pd.DataFrame(processed_data)

            col_map_proc = {
                "id" : "ID",
                "raw_id" : "Raw ID",
                "total" : "Subtotal (Rs.)",
                "tax" : "Tax (Rs.)",
                "discount" : "Discount (Rs.)",
                "final_amount" : "Final (Rs.)",
                "processed_at" : "Processed At"
            }
            avail = [c for c in col_map_proc if c in df_proc.columns]
            df_p  = df_proc[avail].rename(columns=col_map_proc)

            for col in ["Subtotal (Rs.)", "Tax (Rs.)", "Discount (Rs.)", "Final (Rs.)"]:
                if col in df_p.columns:
                    df_p[col] = df_p[col].apply(
                        lambda x: f"Rs.{x:,.2f}" if pd.notna(x) else "Rs.0.00"
                    )
            if "Processed At" in df_p.columns:
                df_p["Processed At"] = pd.to_datetime(
                    df_p["Processed At"], errors="coerce"
                ).dt.strftime("%d %b %Y, %H:%M")

            st.dataframe(df_p, use_container_width=True, hide_index=True)
        else:
            st.info("No processed records yet.")