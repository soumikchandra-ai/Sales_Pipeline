import os
import httpx
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL","http://127.0.0.1:8000")

DEFAULT_TIMEOUT = 10.0

def _build_headers(token: str | None=None)->dict:
    "Builds the HTTP headers for a request."
    
    headers={}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def _parse_error(response: httpx.Response)->str:
    "Extracts a clean human readable error message from an HTTP response."
    try:
        body = response.json()
        detail = body.get("detail","")
        if isinstance(detail,list):
            messages=[]
            for err in detail:
                loc="->".join(str(x) for x in err.get("loc",[]))
                msg=err.get("msg","Unknown error")
                messages.append(f"{loc}: {msg}" if loc else msg)
            return " | ".join(messages)
        elif isinstance(detail,str) and detail:
            return detail
        else:
            return f"Server Error (HTTP {response.status_code})"
    except Exception:
        return f"Server returned status {response.status_code}"

def _handle_session_expiry():
    "Called when a 401 unauthorized response is recieved."
    st.session_state["token"]=None
    st.session_state["username"]=None
    st.session_state["role"]=None
    
    st.warning("Your Session has expired. Please log in again.")
    st.rerun()

def api_get(endpoint:str, token:str | None=None, params: dict| None=None)->tuple[bool,any,int]:
    "Sends a get request to the FastAPI backend."
    
    url = f"{BASE_URL}{endpoint}"
    headers = _build_headers(token)
    try:
        response = httpx.get(url,headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        if response.status_code==401:
            _handle_session_expiry()
            return False, "Session expired", 401
        
        if response.status_code in (200,201):
            return True, response.json(), response.status_code
        
        error_msg = _parse_error(response)
        return False, error_msg, response.status_code
    
    except httpx.ConnectError:
        return False, "Could not connect to the server.", 0
    
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", 0
    
def api_post(endpoint:str, data:dict | None=None, token:str | None= None, files=None)->tuple[bool,any,int]:
    "Send a post request to the FastAPI Backend."
    
    url = f"{BASE_URL}{endpoint}"
    headers = _build_headers(token)
    
    timeout = 30.0 if files else DEFAULT_TIMEOUT
    
    try:
        if files:
            response = httpx.post(url, headers=headers, files=files, timeout=timeout)
        else:
            response = httpx.post(url, headers=headers, json=data, timeout=timeout)
            
        if response.status_code == 401:
            if endpoint not in ("/auth/login","/auth/register"):
                _handle_session_expiry()
                return False, "Session expired", 401
            else:
                error_msg = _parse_error(response)
                return False, error_msg, 401
        
        if response.status_code in (200,201):
            return True, response.json(), response.status_code
        error_msg = _parse_error(response)
        return False, error_msg, response.status_code
        
    except httpx.ConnectError:
        return False, "Could not connect to the server.", 0
    except httpx.TimeoutException:
        return False, "Request timed out. Please try again", 0
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", 0
    
    