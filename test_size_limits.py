import httpx

BASE_URL = "https://paribus-hospital-bulk-processing.onrender.com"

def generate_csv(filename, count):
    with open(filename, "w", encoding="utf-8") as f:
        f.write("name,address,phone\n")
        for i in range(1, count + 1):
            f.write(f"Hospital {i},Address {i},555-{i:04d}\n")
    print(f"Generated {filename} with {count} hospital rows.")

def main():
    print(f"Testing size limit constraints against: {BASE_URL}\n")
    client = httpx.Client(timeout=30.0)

    # Generate the test CSV files
    generate_csv("test_30.csv", 30)
    generate_csv("test_15.csv", 15)
    print("-" * 60)

    # 1. Test 30 entries (Should be REJECTED - exceeds limit of 20)
    print("\n--- Test 1: Uploading 30 entries CSV (Limit is 20) ---")
    with open("test_30.csv", "rb") as f:
        files = {"file": ("test_30.csv", f, "text/csv")}
        r = client.post(f"{BASE_URL}/hospitals/bulk/validate", files=files)
    print(f"Status Code: {r.status_code}")
    try:
        print(f"Response: {r.json()}")
    except Exception:
        print(f"Response text: {r.text}")

    # 2. Test 15 entries (Should be ACCEPTED - within limit of 20)
    print("\n--- Test 2: Uploading 15 entries CSV (Within Limit) ---")
    with open("test_15.csv", "rb") as f:
        files = {"file": ("test_15.csv", f, "text/csv")}
        r = client.post(f"{BASE_URL}/hospitals/bulk/validate", files=files)
    print(f"Status Code: {r.status_code}")
    try:
        res = r.json()
        print(f"Response (Valid status): {res.get('valid')}")
        print(f"Response (Total hospitals parsed): {res.get('total_hospitals')}")
        print(f"Response (Errors): {res.get('errors')}")
    except Exception:
        print(f"Response text: {r.text}")

if __name__ == "__main__":
    main()
