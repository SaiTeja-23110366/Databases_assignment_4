"""
test_failure_simulation.py
--------------------------
Demonstrates ACID Atomicity + Rollback.

Run AFTER Flask app is running:  python app.py
Usage:  python test_failure_simulation.py
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"


def make_admin_session():
    """Login via HTML form → get a session cookie (for general routes)."""
    s = requests.Session()
    s.post(f"{BASE_URL}/login",
           data={"username": "admin", "password": "123"},
           timeout=10)
    return s


def get_admin_jwt():
    """Login via JSON → get JWT (for /test/* endpoints)."""
    resp = requests.post(
        f"{BASE_URL}/login",
        json={"user": "admin", "password": "123"},
        timeout=10
    )
    if resp.status_code == 200:
        return resp.json().get("token")
    print(f"  [!] JWT login failed: {resp.status_code} {resp.text}")
    return None


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def get_inventory_stock(session_obj, ingredient_id=1):
    resp = session_obj.get(f"{BASE_URL}/table/Inventory", timeout=10)
    if resp.status_code == 200:
        rows = resp.json().get("rows", [])
        for row in rows:
            if str(row[0]) == str(ingredient_id):
                return float(row[2])
    return None


def get_purchase_count(session_obj):
    resp = session_obj.get(f"{BASE_URL}/table/Purchase", timeout=10)
    if resp.status_code == 200:
        return len(resp.json().get("rows", []))
    return None


def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  FAILURE SIMULATION & ROLLBACK VERIFICATION")
    print("  CS 432 Assignment 3, Module B")
    print("="*60)

    admin_session = make_admin_session()
    jwt_token     = get_admin_jwt()

    if not jwt_token:
        print("[!] Could not get JWT. Is the Flask app running?")
        exit(1)

    # ── STEP 1: Baseline ────────────────────────────────────────────
    separator("STEP 1: Baseline State")
    stock_before     = get_inventory_stock(admin_session, ingredient_id=1)
    purchases_before = get_purchase_count(admin_session)
    print(f"  Inventory Ingredient#1 StockQty : {stock_before}")
    print(f"  Total Purchase rows             : {purchases_before}")

    # ── STEP 2: Simulated crash → should rollback ───────────────────
    separator("STEP 2: Simulated Crash — Atomicity Test")
    print("  Sending POST /test/purchase_fail  (simulate_failure=True)")
    print("  Expected: Purchase INSERT is rolled back, Inventory unchanged")

    resp = requests.post(
        f"{BASE_URL}/test/purchase_fail",
        json={"supplier_id": 1, "ingredient_id": 1, "quantity": 50, "unit_price": 10.0},
        headers=auth(jwt_token),
        timeout=10
    )
    print(f"  Response: {resp.status_code} [OK] {resp.text}")

    time.sleep(0.5)
    stock_after_fail     = get_inventory_stock(admin_session, ingredient_id=1)
    purchases_after_fail = get_purchase_count(admin_session)
    print(f"\n  Inventory StockQty after crash  : {stock_after_fail}")
    print(f"  Purchase row count after crash  : {purchases_after_fail}")

    atomicity_ok = (stock_after_fail == stock_before and
                    purchases_after_fail == purchases_before)
    print(f"\n  [*] Atomicity (rollback) test: {'PASS [OK]' if atomicity_ok else 'FAIL [ERROR]'}")

    # ── STEP 3: Successful commit → all 3 tables written ───────────
    separator("STEP 3: Successful Transaction — Durability Test")
    print("  Sending POST /test/purchase_ok  (simulate_failure=False)")
    print("  Expected: Purchase inserted, Inventory +25, AuditLog written")

    resp2 = requests.post(
        f"{BASE_URL}/test/purchase_ok",
        json={"supplier_id": 1, "ingredient_id": 1, "quantity": 25, "unit_price": 8.5},
        headers=auth(jwt_token),
        timeout=10
    )
    print(f"  Response: {resp2.status_code} [OK] {resp2.text}")

    time.sleep(0.5)
    stock_after_ok     = get_inventory_stock(admin_session, ingredient_id=1)
    purchases_after_ok = get_purchase_count(admin_session)
    print(f"\n  Inventory StockQty after commit : {stock_after_ok}")
    print(f"  Purchase row count after commit : {purchases_after_ok}")

    durability_ok = (
        purchases_after_ok  == purchases_before + 1 and
        stock_after_ok      is not None and
        stock_before        is not None and
        stock_after_ok      == stock_before + 25
    )
    print(f"\n  [*] Durability (commit) test: {'PASS [OK]' if durability_ok else 'FAIL [ERROR]'}")

    # ── STEP 4: Consistency — stock cannot go negative ──────────────
    separator("STEP 4: Consistency Check — Stock Cannot Go Negative")
    print("  Logging waste of 999999 kg — stock should floor at 0, not go negative")

    resp3 = admin_session.post(
        f"{BASE_URL}/waste/add",
        data={
            "ScheduleID":     "1",
            "WasteQty_Kg":    "999999",
            "Waste_category": "Leftover",
            "ingredient_id":  "1"
        },
        timeout=10
    )
    print(f"  Response: {resp3.status_code}")

    stock_after_waste = get_inventory_stock(admin_session, ingredient_id=1)
    print(f"  StockQty after massive waste deduction: {stock_after_waste}")
    consistency_ok = stock_after_waste is not None and stock_after_waste >= 0
    print(f"\n  [*] Consistency (non-negative stock) test: {'PASS [OK]' if consistency_ok else 'FAIL [ERROR]'}")

    # ── FINAL SUMMARY ───────────────────────────────────────────────
    separator("FINAL SUMMARY")
    print(f"  Atomicity  (rollback on crash)   : {'PASS [OK]' if atomicity_ok   else 'FAIL [ERROR]'}")
    print(f"  Durability (data persists)        : {'PASS [OK]' if durability_ok  else 'FAIL [ERROR]'}")
    print(f"  Consistency (no negative stock)   : {'PASS [OK]' if consistency_ok else 'FAIL [ERROR]'}")
    print()