import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
from frontend.api_client import api_get

def show_dashboard_page():
    "Sales Dashboard- shows charts and insights from processed Data."
    
    st.title("Sales Dashboard")
    st.markdown("Visual insights from the Processed Sales Data")
    st.markdown("---")
    
    success, data, status_code = api_get(
        "/sales/processed",
        token=st.session_state.get("token")
    )
    
    if success and len(data) > 0:
        import pandas as pd
        df = pd.DataFrame(data)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sales", len(df))
        with col2:
            st.metric("Total Revenue", f"Rs. {df['final_amount'].sum():,.2f}")
        with col3:
            st.metric("Avg Sale", f"Rs. {df['final_amount'].mean():,.2f}")
        with col4:
            st.metric("Total Tax", f"Rs. {df['tax'].sum():,.2f}")

        st.markdown("---")
        st.info(
            "Full charts (revenue trends, top products, category breakdown)."
            "The data pipeline is working correctly."
            f"**{len(df)} processed records** are ready to visualize."
        )

    elif success and len(data) == 0:
        st.info(
            "No processed records yet. "
            "Go to the **Upload** page to add sales data, "
            "then run the **Pipeline** to process it."
        )

    else:
        if status_code == 0:
            st.error(
                "Cannot connect to the backend server. "
                "Make sure it is running."
            )
        else:
            st.error(f"Failed to load data: {data}")