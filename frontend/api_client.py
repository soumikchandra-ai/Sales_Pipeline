import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL","http://127.0.0.1:8000")

def _build_headers(token: str | None=None)->dict:
    "Builds the HTTP headers for a request."
    
    headers={}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def api_get(endpoint:str, token:str | None=None, params: dict| None=None):
    "Sends a get request to the FastAPI backend."
    
    url = f"{API_BASE_URL}{endpoint}"
    headers = _build_headers(token)
    try:
        response = httpx.get(url,headers=headers, params=params, timeout=10.0)
        if response.status_code in (200,201):
            return True, response.json(), response.status_code
        else:
            try:
                error_detail = response.json().get("detail", "Unknown error occured")
            except Exception:
                error_detail = f"Server returned status {response.status_code}"
                
                return False, error_detail, response.status_code
        
    except httpx.ConnectError:
        return False, "Could not connect to the sserver.", 0
    
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", 0
    
def api_post(endpoint:str, data:dict | None=None, token:str | None= None, files=None):
    "Send a post request to the FastAPI Backend."
    url = f"{API_BASE_URL}{endpoint}"
    headers = _build_headers(token)
    
    try:
        if files:
            response = httpx.post(url, headers=headers, files=files, timeout=30.0)
        else:
            response = httpx.post(url, headers=headers, json=data, timeout=10.0)
        
        if response.status_code in (200,201):
            return True, response.json(), response.status_code
        else:
            try:
                error_detail = response.json().get("detail", "Unknown error occurred")
            except Exception:
                error_detail = f"Server returned status {response.status_code}"

            return False, error_detail, response.status_code
    
    except httpx.ConnectError:
        return False, "Could not connect to the server.", 0
    except httpx.TimeoutException:
        return False, "Request timed out. Please try again", 0
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", 0
    
    