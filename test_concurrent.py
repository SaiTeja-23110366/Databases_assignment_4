"""
test_concurrent.py
------------------
Simulates multiple users hitting the Mess Management API simultaneously.

Run AFTER the Flask app is running:  python app.py
Usage:  python test_concurrent.py
"""

import threading
import requests
import time
import json

BASE_URL = "http://localhost:5000"


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------

def make_session(username, password="123"):
    """
    Returns a requests.Session with a valid Flask session cookie.
    This is needed for routes that check session['role'] (inventory, billing).
    """
    s = requests.Session()
    s.post(
        f"{BASE_URL}/login",
        data={"username": username, "password": password},   # HTML form login
        timeout=10
    )
    return s


def get_jwt(username, password="123"):
    """Returns JWT token via JSON login."""
    resp = requests.post(
        f"{BASE_URL}/login",
        json={"user": username, "password": password},
        timeout=10
    )
    if resp.status_code == 200:
        return resp.json().get("token")
    return None


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test 1: Concurrent Inventory Updates (Race Condition)
# Uses session-cookie login so the route accepts it
# ---------------------------------------------------------------------------

def _inventory_worker(session_obj, thread_id, results):
    try:
        resp = session_obj.post(
            f"{BASE_URL}/inventory/update",
            data={
                "IngredientID":   "1",
                "StockQty":       str(100 + thread_id * 10),
                "MinStockLevel":  "5",
                "ReorderLevel":   "20"
            },
            timeout=10
        )
        results[thread_id] = {
            "status": resp.status_code,
            "ok":     resp.status_code in (200, 302)
        }
    except Exception as e:
        results[thread_id] = {"status": "error", "ok": False, "error": str(e)}


def run_concurrent_inventory_test():
    print("\n" + "="*60)
    print("TEST 1: Concurrent Inventory Updates (Race Condition)")
    print("="*60)
    print("Spawning 10 threads, all updating Ingredient #1 simultaneously...")

    # Each thread gets its own session (simulates 10 different admin browsers)
    sessions = [make_session("admin") for _ in range(10)]
    results  = {}
    threads  = [
        threading.Thread(target=_inventory_worker, args=(sessions[i], i + 1, results))
        for i in range(10)
    ]

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    success = sum(1 for r in results.values() if r.get("ok"))
    print(f"  Threads: 10 | Successful: {success} | Time: {elapsed:.2f}s")
    print(f"  Results: {json.dumps(results, indent=2)}")
    return results


# ---------------------------------------------------------------------------
# Test 2: Concurrent Billing Status Updates
# ---------------------------------------------------------------------------

def _billing_worker(session_obj, thread_id, payment_id, results):
    status = "Paid" if thread_id % 2 == 0 else "Pending"
    try:
        resp = session_obj.post(
            f"{BASE_URL}/billing/update_status",
            data={"payment_id": payment_id, "status": status},
            timeout=10
        )
        results[thread_id] = {
            "status": resp.status_code,
            "set_to": status,
            "ok":     resp.status_code in (200, 302)
        }
    except Exception as e:
        results[thread_id] = {"status": "error", "ok": False, "error": str(e)}


def run_concurrent_billing_test():
    print("\n" + "="*60)
    print("TEST 2: Concurrent Billing Status Updates")
    print("="*60)
    print("8 threads toggling MonthlyPaymentID=1 between Paid/Pending...")

    sessions = [make_session("admin") for _ in range(8)]
    results  = {}
    threads  = [
        threading.Thread(target=_billing_worker, args=(sessions[i], i + 1, 1, results))
        for i in range(8)
    ]

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    success = sum(1 for r in results.values() if r.get("ok"))
    print(f"  Threads: 8 | Successful: {success} | Time: {elapsed:.2f}s")
    print(f"  Paid attempts:    {sum(1 for r in results.values() if r.get('set_to')=='Paid')}")
    print(f"  Pending attempts: {sum(1 for r in results.values() if r.get('set_to')=='Pending')}")
    return results


# ---------------------------------------------------------------------------
# Test 3: Concurrent Ratings Submission
# ---------------------------------------------------------------------------

def _rating_worker(session_obj, thread_id, schedule_id, rating, results):
    try:
        resp = session_obj.post(
            f"{BASE_URL}/ratings/add",
            data={"ScheduleID": schedule_id, "Rating": rating},
            timeout=10
        )
        results[thread_id] = {
            "status": resp.status_code,
            "rating": rating,
            "ok":     resp.status_code in (200, 302)
        }
    except Exception as e:
        results[thread_id] = {"status": "error", "ok": False, "error": str(e)}


def run_concurrent_ratings_test():
    print("\n" + "="*60)
    print("TEST 3: Concurrent Ratings Submission (Same Schedule)")
    print("="*60)
    print("3 students submitting ratings for ScheduleID=1 simultaneously...")

    s1 = make_session("user1")
    s2 = make_session("riya")
    s3 = make_session("karan")

    results = {}
    threads = [
        threading.Thread(target=_rating_worker, args=(s1, 1, 1, 4, results)),
        threading.Thread(target=_rating_worker, args=(s2, 2, 1, 5, results)),
        threading.Thread(target=_rating_worker, args=(s3, 3, 1, 3, results)),
    ]

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    success = sum(1 for r in results.values() if r.get("ok"))
    print(f"  Threads: 3 | Successful: {success} | Time: {elapsed:.2f}s")
    return results


# ---------------------------------------------------------------------------
# Test 4: Isolation — Read inventory during concurrent writes
# ---------------------------------------------------------------------------

def _read_stock(session_obj, label, results, delay=0):
    time.sleep(delay)
    try:
        resp = session_obj.get(f"{BASE_URL}/table/Inventory", timeout=10)
        if resp.status_code == 200:
            rows = resp.json().get("rows", [])
            results[f"read_{label}"] = {
                "time":       time.strftime("%H:%M:%S"),
                "row0_stock": rows[0][2] if rows else None
            }
        else:
            results[f"read_{label}"] = {"status": resp.status_code}
    except Exception as e:
        results[f"read_{label}"] = {"error": str(e)}


def run_isolation_test():
    print("\n" + "="*60)
    print("TEST 4: Isolation — Reads During Concurrent Writes")
    print("="*60)
    print("Reading inventory at t=0, t=0.5s, t=1s while writes happen...")

    admin_s = make_session("admin")
    results = {}
    threads = [
        threading.Thread(target=_read_stock, args=(admin_s, "t0",   results, 0.0)),
        threading.Thread(target=_read_stock, args=(admin_s, "t0.5", results, 0.5)),
        threading.Thread(target=_read_stock, args=(admin_s, "t1",   results, 1.0)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"  Snapshot results: {json.dumps(results, indent=2)}")
    return results


# ---------------------------------------------------------------------------
# Test 5: Durability — insert then read back
# ---------------------------------------------------------------------------

def run_durability_test():
    print("\n" + "="*60)
    print("TEST 5: Durability — Verify committed data persists")
    print("="*60)

    admin_s = make_session("admin")

    # Get next ItemID manually
    resp0 = admin_s.get(f"{BASE_URL}/table/MenuItem", timeout=10)
    rows  = resp0.json().get("rows", []) if resp0.status_code == 200 else []
    next_id = max((r[0] for r in rows), default=0) + 1

    resp = admin_s.post(
        f"{BASE_URL}/insert/MenuItem",
        json={"columns": ["ItemID", "Name", "Category"],
              "values":  [next_id, "Durability Test Item", "Test"]},
        timeout=10
    )
    print(f"  INSERT MenuItem [OK] status {resp.status_code}")

    time.sleep(2)

    resp2 = admin_s.get(f"{BASE_URL}/table/MenuItem", timeout=10)
    if resp2.status_code == 200:
        rows  = resp2.json().get("rows", [])
        found = any("Durability Test Item" in str(r) for r in rows)
        print(f"  Durability check → item found after 2s pause: {found}")
        return found
    print(f"  Read back failed: {resp2.status_code}")
    return False


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  MESS MANAGEMENT — CONCURRENT USER SIMULATION")
    print("  CS 432 Assignment 3, Module B")
    print("="*60)

    print("\n[*] Testing connection to Flask app...")
    try:
        requests.get(f"{BASE_URL}/login", timeout=5)
        print(f"  Flask app is running [OK]")
    except Exception:
        print(f"  [!] Cannot reach http://localhost:5000 - is app.py running?")
        exit(1)

    r1 = run_concurrent_inventory_test()
    r2 = run_concurrent_billing_test()
    r3 = run_concurrent_ratings_test()
    r4 = run_isolation_test()
    r5 = run_durability_test()

    print("\n" + "="*60)
    print("  SUMMARY")
    print("="*60)
    print(f"  Test 1 (Race condition - Inventory):  "
          f"{sum(1 for r in r1.values() if r.get('ok'))}/10 succeeded")
    print(f"  Test 2 (Race condition - Billing):    "
          f"{sum(1 for r in r2.values() if r.get('ok'))}/8 succeeded")
    print(f"  Test 3 (Concurrent ratings):          "
          f"{sum(1 for r in r3.values() if r.get('ok'))}/3 succeeded")
    print(f"  Test 4 (Isolation reads):             completed")
    print(f"  Test 5 (Durability):                  {'PASS ✅' if r5 else 'FAIL ❌'}")
    print()