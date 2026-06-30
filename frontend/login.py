import sys
import os
import streamlit as st
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frontend.api_client import api_get,api_post

def show_login_page():
    st.title("Sales Pipeline Dashboard")
    st.markdown("### Welcome! Please login or register to continue")
    st.markdown("---")
    
    #Two tabs one for login(existing user) and one for register(new user)
    tab_login, tab_register = st.tabs(["Login","Register"])
    
    with tab_login:
        st.subheader("Login to your account")
        with st.form("login_form", clear_on_submit=False):
            login_username = st.text_input(
                "Username",
                key="login_username_input",
                placeholder="Enter your username"
            )
            
            login_password = st.text_input(
                "Password",
                type="password",
                key="login_password_input",
                placeholder="Enter your password"
            )
            
            login_submit = st.form_submit_button("Login",use_container_width=True)
            if login_submit:
                if not login_username or not login_password:
                    st.error("Please enter both username and password.")
                else:
                    with st.spinner("Logging in.."):
                        success, response_data, status_code = api_post(
                            "/auth/login",
                            data={
                                "username":login_username,
                                "password":login_password
                            }
                        )
                    if success:
                        token = response_data["access_token"]
                        me_success, me_data, me_status = api_post.__wrapped__ if False else(None,None,None)
                        
                        me_success, me_data, me_status = api_get("/auth/me",token=token)
                        
                        if me_success:
                            st.session_state["token"]=token
                            st.session_state["username"]=me_data["username"]
                            st.session_state["role"]=me_data["role"]
                            
                            st.success(f"Welcome back, {me_data['username']}!")
                            st.rerun()
                            
                        else:
                            st.error("Login succeeded but could not fetch user info. Try again.")
                            
                    else:
                        if status_code==401:
                            st.error("Invalid username or password.")
                        elif status_code==0:
                            st.error(f"{response_data}")
                        else:
                            st.error(f"{response_data}")
                            
    with tab_register:
        st.subheader("Create a new account.")
        
        with st.form("register_form", clear_on_submit=True):
            reg_username = st.text_input(
                "Choose a username",
                key="reg_username_input",
                placeholder="Atleast 3 characters"
            )
            reg_password = st.text_input(
                "Choose a password",
                type="password",
                key="reg_password_input",
                placeholder="Atleast 6 characters"
            )
            
            reg_confirm_password = st.text_input(
                "Confirm password",
                type="password",
                key="reg_confirm_password_input",
                placeholder="Re-enter your password"
            )
            reg_role = st.selectbox(
                "Account type",
                options=["viewer","admin"],
                key="reg_role_input",
                help="Admin can upload data, Viewer can only view the data"
            )
            
            register_submit = st.form_submit_button("Register",use_container_width=True)
            if register_submit:
                if not reg_username or not reg_password or not reg_confirm_password:
                    st.error("Please fill all the fields.")
                elif len(reg_username)<3:
                    st.error("Please enter an username of length more than 3 characters.")
                elif len(reg_password) < 6:
                    st.error("Password must be at least 6 characters long.")
                elif reg_password != reg_confirm_password:
                    st.error("Passwords do not match. Please try again.")
                else:
                    with st.spinner("Creating your account.."):
                        success, response_data, status_code = api_post(
                            "/auth/register",
                            data={
                                "username":reg_username,
                                "password":reg_password,
                                "role":reg_role
                            }
                        )
                    if success:
                        st.success(f"Account created succcessfully. You can now login to your account.")
                    else:
                        if status_code==400:
                            st.error(f"{response_data}")
                        elif status_code==0:
                            st.error(f"{response_data}")
                        else:
                            st.error(f"Registration failed: {response_data}")