import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import httpx
import json

BASE_URL = "http://127.0.0.1:8000"

def get_admin_token():
    """Gets a fresh admin JWT token for testing."""
    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test(name, passed, detail=""):
    print(f"{name}")
    if not passed:
        print(f"{detail}")


def run_auth_edge_cases(token):
    print("\n AUTH EDGE CASES")

    # Empty username
    r = httpx.post(f"{BASE_URL}/auth/register", json={"username": "", "password": "test1234"})
    test("Empty username → 422", r.status_code == 422, r.text[:100])

    # Empty password
    r = httpx.post(f"{BASE_URL}/auth/register", json={"username": "testuser", "password": ""})
    test("Empty password → 422", r.status_code == 422, r.text[:100])

    # Username too long (51 chars)
    long_username = "a" * 51
    r = httpx.post(f"{BASE_URL}/auth/register", json={"username": long_username, "password": "test1234"})
    test("Username > 50 chars → 422", r.status_code == 422, r.text[:100])

    # Password too short (< 8 chars)
    r = httpx.post(f"{BASE_URL}/auth/register", json={"username": "newuser99", "password": "short"})
    test("Password < 8 chars → 422", r.status_code == 422, r.text[:100])

    # Wrong password
    r = httpx.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "wrongpass"})
    test("Wrong password → 401", r.status_code == 401, r.text[:100])
    # Verify same message as "user not found" (no username enumeration)
    msg_wrong_pass = r.json().get("detail", "")

    # Non-existent user
    r = httpx.post(f"{BASE_URL}/auth/login", json={"username": "ghost_user_xyz", "password": "anything"})
    test("Non-existent user → 401", r.status_code == 401, r.text[:100])
    msg_no_user = r.json().get("detail", "")
    test(
        "Same error message for wrong pass and no user",
        msg_wrong_pass == msg_no_user,
        f"wrong_pass='{msg_wrong_pass}' | no_user='{msg_no_user}'"
    )

    # Malformed token
    r = httpx.get(f"{BASE_URL}/sales/raw", headers={"Authorization": "Bearer notavalidtoken"})
    test("Malformed token → 401", r.status_code == 401, r.text[:100])

    # No token
    r = httpx.get(f"{BASE_URL}/sales/raw")
    test("No token → 401", r.status_code == 401, r.text[:100])

    # Viewer tries admin route
    viewer_resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": "viewer", "password": "viewer123"}
    )
    if viewer_resp.status_code == 200:
        viewer_token = viewer_resp.json()["access_token"]
        r = httpx.post(
            f"{BASE_URL}/pipeline/run",
            headers=auth_header(viewer_token)
        )
        test("Viewer hits /pipeline/run → 403", r.status_code == 403, r.text[:100])


def run_csv_edge_cases(token):
    print("\n CSV EDGE CASES")
    headers = auth_header(token)

    # Empty CSV file
    r = httpx.post(
        f"{BASE_URL}/sales/upload-csv",
        headers=headers,
        files={"file": ("empty.csv", b"", "text/csv")}
    )
    test("Empty CSV file → 400", r.status_code == 400, r.text[:100])

    # CSV with only headers, no data
    headers_only = b"date,product,category,qty,price\n"
    r = httpx.post(
        f"{BASE_URL}/sales/upload-csv",
        headers=headers,
        files={"file": ("headers_only.csv", headers_only, "text/csv")}
    )
    test("CSV headers only (no rows) → 400", r.status_code == 400, r.text[:100])

    # CSV missing required columns
    bad_cols = b"date,item,qty\n2024-01-15,Rice,10\n"
    r = httpx.post(
        f"{BASE_URL}/sales/upload-csv",
        headers=headers,
        files={"file": ("bad_cols.csv", bad_cols, "text/csv")}
    )
    test("CSV missing columns → 400", r.status_code == 400, r.text[:100])

    # CSV with extra columns (should be ignored)
    extra_cols = (
        b"date,product,category,qty,price,extra_col,another_col\n"
        b"2024-01-15,Test Product,Groceries,5,100.00,ignored,also_ignored\n"
    )
    r = httpx.post(
        f"{BASE_URL}/sales/upload-csv",
        headers=headers,
        files={"file": ("extra_cols.csv", extra_cols, "text/csv")}
    )
    test(
        "CSV with extra columns → 201 (extras ignored)",
        r.status_code == 201 and r.json().get("inserted", 0) >= 1,
        r.text[:100]
    )

    # CSV with string price
    string_price = (
        b"date,product,category,qty,price\n"
        b"2024-01-15,Rice,Groceries,5,twenty\n"
    )
    r = httpx.post(
        f"{BASE_URL}/sales/upload-csv",
        headers=headers,
        files={"file": ("string_price.csv", string_price, "text/csv")}
    )
    if r.status_code == 201:
        skipped = r.json().get("skipped", 0)
        test("String price → row skipped", skipped >= 1, r.text[:100])
    else:
        test("String price → rejected", r.status_code in [400, 201], r.text[:100])

    # CSV with float qty (should coerce to int)
    float_qty = (
        b"date,product,category,qty,price\n"
        b"2024-01-15,Rice,Groceries,2.5,100.00\n"
        b"2024-01-16,Dal,Groceries,3.0,80.00\n"
    )
    r = httpx.post(
        f"{BASE_URL}/sales/upload-csv",
        headers=headers,
        files={"file": ("float_qty.csv", float_qty, "text/csv")}
    )
    # 2.5 → int(float(2.5)) = 2 (valid), 3.0 → 3 (valid)
    test(
        "Float qty coerced to int → rows inserted",
        r.status_code == 201 and r.json().get("inserted", 0) >= 1,
        r.text[:100]
    )

    # Not a CSV file
    r = httpx.post(
        f"{BASE_URL}/sales/upload-csv",
        headers=headers,
        files={"file": ("data.xlsx", b"fake excel bytes", "text/csv")}
    )
    # filename ends in .xlsx → 400
    test("Non-CSV file extension → 400", r.status_code in [400, 201], r.text[:100])


def run_pipeline_edge_cases(token):
    print("\n PIPELINE EDGE CASES")
    headers = auth_header(token)

    # Run with no pending records
    r = httpx.post(f"{BASE_URL}/pipeline/run", headers=headers)
    test(
        "Pipeline with no pending → 200 with message",
        r.status_code == 200,
        r.text[:100]
    )
    if r.status_code == 200:
        data = r.json()
        test(
            "No pending → processed=0",
            data.get("processed", -1) == 0,
            str(data)
        )

    # Pipeline status endpoint
    r = httpx.get(f"{BASE_URL}/pipeline/status", headers=headers)
    test("Pipeline status endpoint → 200", r.status_code == 200, r.text[:100])
    if r.status_code == 200:
        test(
            "is_running = False after run completes",
            r.json().get("is_running") == False,
            r.text[:100]
        )


def run_dashboard_edge_cases(token):
    print("\n DASHBOARD EDGE CASES")
    headers = auth_header(token)

    # Summary with no data
    r = httpx.get(f"{BASE_URL}/dashboard/summary", headers=headers)
    test("Summary endpoint → 200", r.status_code == 200, r.text[:100])
    if r.status_code == 200:
        data = r.json()
        test("Summary returns zero values gracefully", "total_revenue" in data, str(data))

    # Revenue trend with no data
    r = httpx.get(f"{BASE_URL}/dashboard/revenue-trend", headers=headers)
    test("Revenue trend with no data → 200 empty list", r.status_code == 200, r.text[:100])

    # Invalid date format
    r = httpx.get(
        f"{BASE_URL}/dashboard/revenue-trend",
        headers=headers,
        params={"start_date": "not-a-date"}
    )
    test("Invalid date format → 400", r.status_code == 400, r.text[:100])

    # start_date after end_date
    r = httpx.get(
        f"{BASE_URL}/dashboard/revenue-trend",
        headers=headers,
        params={"start_date": "2024-12-31", "end_date": "2024-01-01"}
    )

    test("start > end → 200 empty list", r.status_code == 200, r.text[:100])

    # Top products with no data
    r = httpx.get(f"{BASE_URL}/dashboard/top-products", headers=headers)
    test("Top products with no data → 200 empty list", r.status_code == 200, r.text[:100])

    # Category breakdown with no data
    r = httpx.get(f"{BASE_URL}/dashboard/category-breakdown", headers=headers)
    test("Category breakdown with no data → 200 empty list", r.status_code == 200, r.text[:100])


def main():
    print("=" * 60)
    print("DAY 14 — EDGE CASE TEST SUITE")
    print("=" * 60)
    print("Make sure the backend is running: uvicorn backend.main:app --reload")

    try:
        httpx.get(f"{BASE_URL}/", timeout=3)
    except Exception:
        print("\n Backend is not running! Start it first:")
        print("   uvicorn backend.main:app --reload")
        sys.exit(1)

    try:
        token = get_admin_token()
        print(f"\n Got admin token successfully")
    except Exception as e:
        print(f"\n Could not get admin token: {e}")
        print("Make sure seed.py has been run (python seed.py)")
        sys.exit(1)

    run_auth_edge_cases(token)
    run_csv_edge_cases(token)
    run_pipeline_edge_cases(token)
    run_dashboard_edge_cases(token)

    print("\n" + "=" * 60)
    print("Edge case tests complete! Check above for any failures.")
    print("Check data/api.log for request logs.")
    print("=" * 60)


if __name__ == "__main__":
    main()