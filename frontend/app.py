import sys
import os
import streamlit as st
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frontend.login import show_login_page
from frontend.upload import show_upload_page
from frontend.pipeline import show_pipeline_page
from frontend.dashboard import show_dashboard_page
from frontend.admin import show_admin_page

st.set_page_config(
    page_title="Sales Pipeline Dashboard",
    layout="wide"
)

def init_session_state():
    defaults={
        "token":None,
        "username":None,
        "role":None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key]=value
        
init_session_state()

def logout():
    for key in ["token","username","role"]:
        st.session_state[key]=None
    st.rerun()
    
if st.session_state["token"] is None:
    show_login_page()

else:
    role     = st.session_state.get("role", "viewer")
    username = st.session_state.get("username", "")

    with st.sidebar:
        st.title("Sales Pipeline")
        st.markdown("---")

        st.subheader("Navigation")

        if role == "admin":
            nav_options = [
                "Dashboard",
                "Upload",
                "Pipeline",
                "Admin Panel"
            ]
        else:
            nav_options = ["Dashboard"]

        page = st.radio(
            "Go to:",
            options=nav_options,
            label_visibility="collapsed"
        )

        st.markdown("<br>" * 6, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**Logged in as:**")

        if role == "admin":
            st.markdown(f"👤**{username}**  \n `ADMIN`")
        else:
            st.markdown(f"👤**{username}**  \n `VIEWER`")

        st.markdown("---")

        if st.button("🚪 Logout", use_container_width=True, type="secondary"):
            logout()

    if page == "Upload":
        show_upload_page()

    elif page == "Pipeline":
        show_pipeline_page()

    elif page == "Dashboard":
        show_dashboard_page()

    elif page == "Admin Panel":
        show_admin_page()