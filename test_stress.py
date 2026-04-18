"""
test_stress.py
--------------
Pure Python stress test — fires hundreds of requests using thread pools.
Measures: RPS, error rate, response time (min/avg/p95/max).

Run AFTER Flask app is running:  python app.py
Usage:  python test_stress.py
"""

import threading
import requests
import time
import statistics
import json

BASE_URL = "http://localhost:5000"


# ---------------------------------------------------------------------------
# Session pool — each worker gets its own pre-logged-in session
# ---------------------------------------------------------------------------

def make_session(username, password="123"):
    """HTML form login → session cookie for browser-style routes."""
    s = requests.Session()
    s.post(f"{BASE_URL}/login",
           data={"username": username, "password": password},
           timeout=10)
    return s


def get_jwt(username, password="123"):
    resp = requests.post(f"{BASE_URL}/login",
                         json={"user": username, "password": password},
                         timeout=10)
    if resp.status_code == 200:
        return resp.json().get("token")
    return None


# ---------------------------------------------------------------------------
# Single request worker
# ---------------------------------------------------------------------------

def fire_request(session_obj, url, method="GET", data=None, json_body=None):
    start = time.time()
    try:
        if method == "POST":
            if json_body:
                resp = session_obj.post(url, json=json_body, timeout=10)
            else:
                resp = session_obj.post(url, data=data, timeout=10)
        else:
            resp = session_obj.get(url, timeout=10)
        elapsed = time.time() - start
        return {"ok": resp.status_code in (200, 302), "ms": elapsed * 1000,
                "code": resp.status_code}
    except Exception as e:
        elapsed = time.time() - start
        return {"ok": False, "ms": elapsed * 1000, "code": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Stress scenario runner
# ---------------------------------------------------------------------------

def stress_scenario(name, url, method="GET", data=None, json_body=None,
                    username="admin", num_threads=20, requests_per_thread=5):
    total   = num_threads * requests_per_thread
    results = []
    lock    = threading.Lock()

    def worker():
        # Each thread gets its own session (realistic simulation)
        s = make_session(username)
        for _ in range(requests_per_thread):
            r = fire_request(s, url, method=method, data=data, json_body=json_body)
            with lock:
                results.append(r)

    print(f"\n{'-'*55}")
    print(f"  Scenario: {name}")
    print(f"  URL: {method} {url}")
    print(f"  Workers: {num_threads}  |  Req/worker: {requests_per_thread}  |  Total: {total}")
    print(f"{'-'*55}")

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    wall_start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_time = time.time() - wall_start

    times     = [r["ms"] for r in results]
    successes = sum(1 for r in results if r["ok"])
    errors    = total - successes

    print(f"  Total requests  : {total}")
    print(f"  Successful      : {successes}  ({100*successes/total:.1f}%)")
    print(f"  Errors          : {errors}  ({100*errors/total:.1f}%)")
    print(f"  Wall time       : {wall_time:.2f}s")
    print(f"  Throughput      : {total/wall_time:.1f} req/s")
    print(f"  Response time   :")
    print(f"    min  = {min(times):.1f} ms")
    print(f"    avg  = {statistics.mean(times):.1f} ms")
    print(f"    p95  = {sorted(times)[int(0.95*len(times))]:.1f} ms")
    print(f"    max  = {max(times):.1f} ms")

    return {
        "name":    name,
        "total":   total,
        "success": successes,
        "errors":  errors,
        "rps":     round(total / wall_time, 1),
        "avg_ms":  round(statistics.mean(times), 1),
        "p95_ms":  round(sorted(times)[int(0.95 * len(times))], 1),
        "max_ms":  round(max(times), 1),
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  MESS MANAGEMENT — STRESS TEST")
    print("  CS 432 Assignment 3, Module B")
    print("="*60)

    print("\n[*] Verifying app is reachable...")
    try:
        requests.get(f"{BASE_URL}/login", timeout=5)
        print("  Flask app is running [OK]")
    except Exception:
        print("  [!] Cannot reach http://localhost:5000 - start app.py first")
        exit(1)

    all_results = []

    # ── READ scenarios ──────────────────────────────────────────────

    all_results.append(stress_scenario(
        "Dashboard (admin) — READ",
        f"{BASE_URL}/dashboard",
        username="admin", num_threads=20, requests_per_thread=5,
    ))

    all_results.append(stress_scenario(
        "Menu page — READ",
        f"{BASE_URL}/menu",
        username="user1", num_threads=30, requests_per_thread=5,
    ))

    all_results.append(stress_scenario(
        "Inventory table API — READ",
        f"{BASE_URL}/table/Inventory",
        username="admin", num_threads=20, requests_per_thread=5,
    ))

    all_results.append(stress_scenario(
        "Audit Logs — READ",
        f"{BASE_URL}/logs",
        username="admin", num_threads=10, requests_per_thread=5,
    ))

    # ── WRITE scenarios ─────────────────────────────────────────────

    all_results.append(stress_scenario(
        "Ratings submit — WRITE (concurrent students)",
        f"{BASE_URL}/ratings/add",
        method="POST",
        data={"ScheduleID": "1", "Rating": "4"},
        username="user1", num_threads=20, requests_per_thread=3,
    ))

    all_results.append(stress_scenario(
        "Billing status update — WRITE (concurrent admins)",
        f"{BASE_URL}/billing/update_status",
        method="POST",
        data={"payment_id": "1", "status": "Paid"},
        username="admin", num_threads=15, requests_per_thread=3,
    ))

    all_results.append(stress_scenario(
        "Inventory update — WRITE (heavy concurrent)",
        f"{BASE_URL}/inventory/update",
        method="POST",
        data={
            "IngredientID":  "1",
            "StockQty":      "200",
            "MinStockLevel": "10",
            "ReorderLevel":  "50",
        },
        username="admin", num_threads=25, requests_per_thread=4,
    ))

    # ── HIGH LOAD ───────────────────────────────────────────────────

    all_results.append(stress_scenario(
        "HIGH LOAD — 500 concurrent menu reads",
        f"{BASE_URL}/menu",
        username="user1", num_threads=50, requests_per_thread=10,
    ))

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  STRESS TEST SUMMARY")
    print("="*60)
    print(f"  {'Scenario':<44} {'RPS':>6} {'Avg ms':>8} {'P95 ms':>8} {'Err%':>6}")
    print(f"  {'─'*44} {'─'*6} {'─'*8} {'─'*8} {'─'*6}")
    for r in all_results:
        err_pct = 100 * r["errors"] / r["total"] if r["total"] else 0
        name    = r["name"][:44]
        print(f"  {name:<44} {r['rps']:>6.1f} {r['avg_ms']:>8.1f} {r['p95_ms']:>8.1f} {err_pct:>5.1f}%")
    print()

    with open("stress_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("  Results saved to stress_results.json")
    print()