import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
from frontend.api_client import api_get, api_post

def show_pipeline_page():
    """
    Renders the Pipeline page with real ETL metrics after a run.
    """
    st.title("ETL Pipeline")
    st.markdown(
        "Run the pipeline to process pending sales data. "
        "Each run **extracts** pending records, **cleans** them, "
        "**calculates** financials, and **loads** them into processed_sales."
    )
    st.markdown("---")
    st.header("Current Status")

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

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        pending_count = len(pending_data) if pending_success else 0
        st.metric(
            "Pending",
            pending_count,
            help="Records uploaded but not yet processed"
        )

    with col2:
        processed_count = len(processed_data) if processed_success else 0
        st.metric(
            "Processed",
            processed_count,
            help="Records successfully through the pipeline"
        )

    with col3:
        failed_count = len(failed_data) if failed_success else 0
        st.metric(
            "Failed",
            failed_count,
            help="Records rejected during validation"
        )

    with col4:
        if processed_success and processed_data:
            df_proc = pd.DataFrame(processed_data)
            total_rev = df_proc["final_amount"].sum()
            st.metric(
                "Total Revenue",
                f"Rs.{total_rev:,.2f}",
                help="Sum of all final_amount in processed_sales"
            )
        else:
            st.metric("Total Revenue", "₹0.00")

    st.markdown("---")

    st.header("Run Pipeline")

    is_admin = st.session_state.get("role") == "admin"

    if not is_admin:
        st.warning(
            "Admin access required to run the pipeline."
        )
        st.button("Run ETL Pipeline", disabled=True)

    elif pending_count == 0:
        st.info(
            "No pending records. "
            "Upload data on the Upload page first."
        )
        st.button("Run ETL Pipeline", disabled=True)

    else:
        st.markdown(
            f"**{pending_count}** pending record(s) ready to process."
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
                success, response_data, status_code = api_post(
                    "/pipeline/run",
                    token=st.session_state.get("token")
                )

            if success:
                st.success(f"{response_data.get('message', 'Pipeline complete!')}")
                st.markdown("---")
                st.subheader("Pipeline Run Results")

                m1, m2, m3, m4, m5, m6 = st.columns(6)

                with m1:
                    st.metric(
                        "Total Loaded",
                        response_data.get("total_loaded", 0),
                        help="Pending records found in DB"
                    )
                with m2:
                    st.metric(
                        "Processed",
                        response_data.get("processed", 0),
                        help="Records successfully written to processed_sales"
                    )
                with m3:
                    st.metric(
                        "Failed",
                        response_data.get("failed", 0),
                        help="Records rejected during cleaning"
                    )
                with m4:
                    st.metric(
                        "Duplicates",
                        response_data.get("skipped_duplicates", 0),
                        help="Records skipped — already processed before"
                    )
                with m5:
                    revenue = response_data.get("total_revenue", 0)
                    st.metric(
                        "Revenue",
                        f"Rs.{revenue:,.2f}",
                        help="Sum of final_amount for this run"
                    )
                with m6:
                    tax = response_data.get("tax_collected", 0)
                    st.metric(
                        "Tax",
                        f"Rs.{tax:,.2f}",
                        help="Total GST collected in this run"
                    )

                # ── Refresh processed table ───────────────────
                st.markdown("---")
                st.subheader("Newly Processed Records")

                fresh_success, fresh_data, _ = api_get(
                    "/sales/processed",
                    token=st.session_state.get("token")
                )

                if fresh_success and fresh_data:
                    _render_processed_table(fresh_data)
                else:
                    st.info("No processed records to display yet.")

            else:
                if status_code == 403:
                    st.error("Admin access required.")
                elif status_code == 0:
                    st.error(
                        f"Cannot connect to backend server.\n{response_data}"
                    )
                elif status_code == 500:
                    st.error(f"Pipeline crashed: {response_data}")
                else:
                    st.error(f"Pipeline failed: {response_data}")

    st.markdown("---")

    st.header("All Processed Records")

    ref_col, _ = st.columns([1, 6])
    with ref_col:
        st.button("Refresh", key="refresh_processed_main")

    if processed_success:
        if not processed_data:
            st.info(
                "No processed records yet. "
                "Run the pipeline above to process pending records."
            )
        else:
            _render_processed_table(processed_data)
    else:
        st.error("Failed to load processed records.")

    if failed_success and failed_data:
        st.markdown("---")
        st.header("Failed Records (Audit Trail)")
        st.markdown(
            "These records were rejected by the pipeline. "
            "The **Fail Reason** column explains why."
        )

        df_failed = pd.DataFrame(failed_data)

        display_cols = {
            "id" : "ID",
            "date" : "Date",
            "product" : "Product",
            "category" : "Category",
            "qty" : "Qty",
            "price" : "Price (₹)",
            "fail_reason" : "Fail Reason"
        }
        available = [c for c in display_cols if c in df_failed.columns]
        df_show = df_failed[available].rename(columns=display_cols)

        if "Date" in df_show.columns:
            df_show["Date"] = pd.to_datetime(
                df_show["Date"], errors="coerce"
            ).dt.strftime("%d %b %Y")

        st.dataframe(df_show, use_container_width=True, hide_index=True)


def _render_processed_table(processed_data: list):
    """
    Helper to render the processed sales table with formatting.
    Extracted as a function because we use it in two places.
    """
    df = pd.DataFrame(processed_data)

    display_cols = {
        "id" : "ID",
        "raw_id" : "Raw ID",
        "total" : "Subtotal (₹)",
        "tax" : "Tax (₹)",
        "discount" : "Discount (₹)",
        "final_amount" : "Final Amount (₹)",
        "processed_at" : "Processed At"
    }

    available = [c for c in display_cols if c in df.columns]
    df_show = df[available].rename(columns=display_cols)

    for col in ["Subtotal (Rs.)", "Tax (Rs.)", "Discount (Rs.)", "Final Amount (Rs.)"]:
        if col in df_show.columns:
            df_show[col] = df_show[col].apply(
                lambda x: f"Rs.{x:,.2f}" if pd.notna(x) else "Rs.0.00"
            )

    if "Processed At" in df_show.columns:
        df_show["Processed At"] = pd.to_datetime(
            df_show["Processed At"], errors="coerce"
        ).dt.strftime("%d %b %Y, %H:%M")

    if "final_amount" in df.columns:
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric("Records", len(df))
        with s2:
            st.metric(
                "Total Revenue",
                f"Rs.{df['final_amount'].sum():,.2f}"
            )
        with s3:
            st.metric(
                "Total Tax",
                f"Rs.{df['tax'].sum():,.2f}"
            )
        with s4:
            st.metric(
                "Total Discount",
                f"Rs.{df['discount'].sum():,.2f}"
            )

    st.dataframe(df_show, use_container_width=True, hide_index=True)