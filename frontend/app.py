import sys
import os
import streamlit as st
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frontend.login import show_login_page
from frontend.upload import show_upload_page
from frontend.pipeline import show_pipeline_page
from frontend.dashboard import show_dashboard_page

st.set_page_config(
    page_title="Sales Pipeline Dashboard",
    layout="wide"
)

def init_session_state():
    if "token" not in st.session_state:
        st.session_state["token"]=None
    if "username" not in st.session_state:
        st.session_state["username"]=None
    if "role" not in st.session_state:
        st.session_state["role"]=None
        
init_session_state()

def logout():
    st.session_state["token"]=None
    st.session_state["username"]=None
    st.session_state["role"]=None
    st.rerun()
    
if st.session_state["token"] is None:
    show_login_page()

else:
    with st.sidebar:
        st.title("Sales Pipeline")
        st.markdown("---")
        
        st.markdown(f"**User:** {st.session_state['username']}")
        st.markdown(f"**Role:** {st.session_state['role']}")
        st.markdown("---")
        
        st.subheader("Navigation")
        if st.session_state["role"]=="admin":
            nav_options=["Dashboard","Upload","Pipeline"]
        else:
            nav_options=["Dashboard"]
        page = st.radio(
            "Go to:",
            options=nav_options,
            label_visibility="collapsed"
        )
        st.markdown("---")
        
        if st.button("Logout ",use_container_width=True):
            logout()
    if page =="Upload":
        show_upload_page()
        
    elif page =="Pipeline":
        show_pipeline_page()
    
    elif page == "Dashboard":
        show_dashboard_page()
        