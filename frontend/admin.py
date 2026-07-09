import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
from datetime import datetime
from frontend.api_client import api_get, api_patch

def show_admin_page():
    """
    Renders the Admin User Management page.
    Called from app.py when admin selects "Admin Panel".
    """

    if st.session_state.get("role") != "admin":
        st.error("Admin access required.")
        st.stop()

    st.title("Admin Panel")
    st.caption("Manage user accounts and roles for the Sales Pipeline app.")
    st.divider()

    st.header("👤 Registered Users")

    with st.spinner("Loading users..."):
        success, users_data, status_code = api_get(
            "/admin/users",
            token=st.session_state.get("token")
        )

    if not success:
        st.error(
            f"Failed to load users: {users_data}"
            if status_code != 0
            else "Cannot connect to server."
        )
        st.stop()

    if not users_data or not users_data.get("users"):
        st.info("No users found.")
        st.stop()

    df_users = pd.DataFrame(users_data["users"])

    if "created_at" in df_users.columns:
        df_users["created_at"] = pd.to_datetime(
            df_users["created_at"], errors="coerce"
        ).dt.strftime("%d %b %Y, %H:%M")

    display_cols = {
        "id": "ID",
        "username": "Username",
        "role": "Role",
        "created_at": "Registered At"
    }
    available = [c for c in display_cols if c in df_users.columns]
    df_show   = df_users[available].rename(columns=display_cols)

    total_users = len(df_users)
    total_admins = int((df_users["role"] == "admin").sum())  if "role" in df_users.columns else 0
    total_viewers = int((df_users["role"] == "viewer").sum()) if "role" in df_users.columns else 0

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("Total Users", total_users)
    with mc2:
        st.metric("Admins", total_admins)
    with mc3:
        st.metric("Viewers", total_viewers)

    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Role": st.column_config.TextColumn(
                "Role",
                help="admin = full access | viewer = read-only"
            )
        }
    )

    st.divider()

    st.header("Change User Role")
    st.markdown(
        "Select a user and assign them a new role. "
        "**You cannot change your own role.**"
    )

    current_username = st.session_state.get("username", "")
    other_users = [
        u for u in users_data["users"]
        if u["username"] != current_username
    ]

    if not other_users:
        st.info("No other users to manage. Register more users first.")
    else:
        with st.form("change_role_form", clear_on_submit=False):

            usernames = [u["username"] for u in other_users]
            selected_username = st.selectbox(
                "Select User",
                options=usernames,
                key="role_change_username",
                help="Choose the user whose role you want to change"
            )

            selected_user = next(
                (u for u in other_users if u["username"] == selected_username),
                None
            )

            if selected_user:
                st.info(
                    f"Current role of **{selected_username}**: "
                    f"`{selected_user.get('role', 'unknown')}`"
                )

            new_role = st.radio(
                "New Role",
                options=["viewer", "admin"],
                index=0,
                key="role_change_new_role",
                help="admin = full access | viewer = read-only"
            )

            if new_role == "admin":
                st.warning(
                    "Admins can upload data, run the pipeline, "
                    "and manage other users. Grant this role carefully."
                )

            submit_role = st.form_submit_button(
                "Update Role",
                type="primary",
                use_container_width=False
            )

            if submit_role:
                if not selected_user:
                    st.error("Selected user not found.")

                elif selected_user.get("role") == new_role:
                    st.warning(
                        f"**{selected_username}** already has role "
                        f"'{new_role}'. No change needed."
                    )

                else:
                    user_id = selected_user["id"]
            
                    with st.spinner(f"Updating role for {selected_username}..."):
                        success, response, status_code = api_patch(
                            f"/admin/users/{user_id}/role",
                            data={"role": new_role},
                            token=st.session_state.get("token")
                        )

                    if success:
                        st.success(
                            f"{response.get('message', 'Role updated successfully!')}"
                        )
                        st.rerun()
                    else:
                        if status_code == 403:
                            st.error(f"{response}")
                        elif status_code == 400:
                            st.error(f"Invalid role: {response}")
                        elif status_code == 404:
                            st.error(f"User not found: {response}")
                        elif status_code == 0:
                            st.error(f"Cannot connect to server: {response}")
                        else:
                            st.error(f"Failed to update role: {response}")