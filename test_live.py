import httpx
import sys

BASE_URL = "https://paribus-hospital-bulk-processing.onrender.com"

def log_section(title):
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "="))
    print("=" * 60)

def main():
    print(f"Starting live API testing against: {BASE_URL}\n")
    client = httpx.Client(timeout=30.0)
    
    # 1. Test Root Endpoint
    log_section("1. GET / (Root)")
    r = client.get(f"{BASE_URL}/")
    print(f"Status Code: {r.status_code}")
    print(f"Response: {r.json()}\n")
    
    # 2. Test Health Endpoint
    log_section("2. GET /health (Health)")
    r = client.get(f"{BASE_URL}/health")
    print(f"Status Code: {r.status_code}")
    print(f"Response: {r.json()}\n")
    
    # 3. Test Validate CSV
    log_section("3. POST /hospitals/bulk/validate (Valid CSV)")
    with open("test.csv", "rb") as f:
        files = {"file": ("test.csv", f, "text/csv")}
        r = client.post(f"{BASE_URL}/hospitals/bulk/validate", files=files)
    print(f"Status Code: {r.status_code}")
    print(f"Response (truncated preview):")
    res_data = r.json()
    preview = res_data.get("preview", [])
    print(f"  Valid: {res_data.get('valid')}")
    print(f"  Total Hospitals: {res_data.get('total_hospitals')}")
    print(f"  Preview rows count: {len(preview)}")
    print(f"  Errors: {res_data.get('errors')}\n")

    # 4. Test Bulk Create (Success Case)
    log_section("4. POST /hospitals/bulk (Valid Ingestion - Expect Success)")
    with open("test_single.csv", "rb") as f:
        files = {"file": ("test_single.csv", f, "text/csv")}
        r = client.post(f"{BASE_URL}/hospitals/bulk", files=files)
    print(f"Status Code: {r.status_code}")
    res_success = r.json()
    batch_id = res_success.get("batch_id")
    print(f"  Batch ID: {batch_id}")
    print(f"  Total: {res_success.get('total_hospitals')}")
    print(f"  Processed: {res_success.get('processed_hospitals')}")
    print(f"  Failed: {res_success.get('failed_hospitals')}")
    print(f"  Activated: {res_success.get('batch_activated')}")
    print("  First hospital row status:")
    if res_success.get("hospitals"):
        print(f"    {res_success['hospitals'][0]}\n")

    # 5. Test Get Status (Success Case)
    if batch_id:
        log_section(f"5. GET /hospitals/bulk/{batch_id} (Check Batch Status)")
        r = client.get(f"{BASE_URL}/hospitals/bulk/{batch_id}")
        print(f"Status Code: {r.status_code}")
        status_res = r.json()
        print(f"  Status: {status_res.get('status')}")
        print(f"  Total: {status_res.get('total_hospitals')}")
        print(f"  Processed: {status_res.get('processed_hospitals')}")
        print(f"  Failed: {status_res.get('failed_hospitals')}")
        print(f"  Completed At: {status_res.get('completed_at')}\n")

    # 6. Test Bulk Create with FAIL_ rows (Partial Failure Case)
    log_section("6. POST /hospitals/bulk (CSV with FAIL_ trigger - Expect Partial Fail)")
    with open("testwithfailor.csv", "rb") as f:
        files = {"file": ("testwithfailor.csv", f, "text/csv")}
        r = client.post(f"{BASE_URL}/hospitals/bulk", files=files)
    print(f"Status Code: {r.status_code}")
    res_fail = r.json()
    fail_batch_id = res_fail.get("batch_id")
    print(f"  Batch ID: {fail_batch_id}")
    print(f"  Total: {res_fail.get('total_hospitals')}")
    print(f"  Processed: {res_fail.get('processed_hospitals')}")
    print(f"  Failed: {res_fail.get('failed_hospitals')}")
    print(f"  Activated: {res_fail.get('batch_activated')}")
    print("  Rows status summary:")
    for row in res_fail.get("hospitals", []):
        print(f"    Row {row['row']}: {row['name']} -> status={row['status']}, error={row['error']}")
    print("")

    # 7. Test Get Status (Partial Failure Case)
    if fail_batch_id:
        log_section(f"7. GET /hospitals/bulk/{fail_batch_id} (Check Failed Batch Status)")
        r = client.get(f"{BASE_URL}/hospitals/bulk/{fail_batch_id}")
        print(f"Status Code: {r.status_code}")
        status_fail_res = r.json()
        print(f"  Status: {status_fail_res.get('status')}")
        print(f"  Total: {status_fail_res.get('total_hospitals')}")
        print(f"  Processed: {status_fail_res.get('processed_hospitals')}")
        print(f"  Failed: {status_fail_res.get('failed_hospitals')}")
        print(f"  Activation Error: {status_fail_res.get('activation_error')}\n")

    # 8. Test Custom Request Validation Error Formatting (422)
    log_section("8. POST /hospitals/bulk (No File - Expect Custom 422)")
    r = client.post(f"{BASE_URL}/hospitals/bulk")
    print(f"Status Code: {r.status_code}")
    err_res = r.json()
    print("Response JSON:")
    print(f"  detail: {err_res.get('detail')}")
    print(f"  error_type: {err_res.get('error_type')}")
    print(f"  message: {err_res.get('message')}")
    print("  First nested error location & details:")
    if err_res.get("errors"):
        print(f"    {err_res['errors'][0]}\n")

    print("=" * 60)
    print(" Live Testing Completed Successfully! ".center(60, "="))
    print("=" * 60)

if __name__ == "__main__":
    main()
