"""
locustfile.py
-------------
Stress / load test for the Mess Management Flask API.
Simulates three types of users hitting the system under load.

Install: pip install locust
Run:     locust -f locustfile.py --host=http://localhost:5000

Then open http://localhost:8089 in your browser,
set number of users (e.g. 50) and spawn rate (e.g. 10/s), and start.

For headless (no browser) run:
  locust -f locustfile.py --host=http://localhost:5000 \
         --users 50 --spawn-rate 10 --run-time 60s --headless \
         --csv=stress_results
"""

from locust import HttpUser, task, between
import random
import json


# ---------------------------------------------------------------------------
# Shared login helper
# ---------------------------------------------------------------------------

USERS = [
    ("admin",  "123"),
    ("user1",  "123"),
    ("riya",   "123"),
    ("karan",  "123"),
]


def do_login(client, username, password):
    """Login via JSON and store JWT token in client headers."""
    with client.post(
        "/login",
        json={"user": username, "password": password},
        catch_response=True,
        name="[auth] login"
    ) as resp:
        if resp.status_code == 200:
            token = resp.json().get("token")
            if token:
                client.headers.update({"Authorization": f"Bearer {token}"})
                return token
        resp.failure(f"Login failed: {resp.status_code}")
    return None


# ---------------------------------------------------------------------------
# Admin User — reads tables, updates billing/inventory, checks logs
# ---------------------------------------------------------------------------

class AdminUser(HttpUser):
    weight = 1                        # 1 admin per ~5 students
    wait_time = between(0.5, 2)       # think time between requests

    def on_start(self):
        do_login(self.client, "admin", "123")

    @task(3)
    def view_dashboard(self):
        self.client.get("/dashboard", name="[admin] dashboard")

    @task(2)
    def view_all_tables(self):
        self.client.get("/all_tables", name="[admin] all_tables page")

    @task(2)
    def read_inventory(self):
        self.client.get("/inventory", name="[admin] inventory page")

    @task(2)
    def read_table_member(self):
        self.client.get("/table/Member", name="[admin] table Member")

    @task(2)
    def read_table_meallog(self):
        self.client.get("/table/MealLog", name="[admin] table MealLog")

    @task(1)
    def update_billing_status(self):
        payment_id = random.randint(1, 5)
        status = random.choice(["Paid", "Pending"])
        self.client.post(
            "/billing/update_status",
            data={"payment_id": payment_id, "status": status},
            name="[admin] billing update"
        )

    @task(1)
    def update_inventory(self):
        self.client.post(
            "/inventory/update",
            data={
                "ingredient_id":   "1",
                "stock_qty":       str(random.randint(50, 500)),
                "min_stock_level": "10",
                "reorder_level":   "50"
            },
            name="[admin] inventory update"
        )

    @task(1)
    def read_suppliers(self):
        self.client.get("/suppliers", name="[admin] suppliers")

    @task(1)
    def read_waste(self):
        self.client.get("/waste", name="[admin] waste")

    @task(1)
    def check_logs(self):
        self.client.get("/logs", name="[admin] audit logs")

    @task(1)
    def check_auth(self):
        self.client.get("/isAuth", name="[admin] isAuth")


# ---------------------------------------------------------------------------
# Student User — views menu, attendance, billing, submits ratings
# ---------------------------------------------------------------------------

class StudentUser(HttpUser):
    weight = 5                        # most traffic comes from students
    wait_time = between(1, 3)

    def on_start(self):
        username, password = random.choice([
            ("user1", "123"),
            ("riya",  "123"),
            ("karan", "123"),
        ])
        do_login(self.client, username, password)

    @task(5)
    def view_dashboard(self):
        self.client.get("/dashboard", name="[student] dashboard")

    @task(4)
    def view_menu(self):
        # vary the date to avoid caching
        dates = ["2026-01-10", "2026-01-11", "2026-01-12", "2026-01-13"]
        self.client.get(
            f"/menu?date={random.choice(dates)}",
            name="[student] menu"
        )

    @task(3)
    def view_attendance(self):
        self.client.get("/meal_attendance", name="[student] attendance")

    @task(3)
    def view_billing(self):
        self.client.get("/billing", name="[student] billing")

    @task(2)
    def view_ratings(self):
        self.client.get("/ratings", name="[student] ratings")

    @task(2)
    def submit_rating(self):
        schedule_id = random.randint(1, 10)
        rating = random.randint(1, 5)
        self.client.post(
            "/ratings/add",
            data={"schedule_id": schedule_id, "rating": rating},
            name="[student] submit rating"
        )

    @task(1)
    def check_auth(self):
        self.client.get("/isAuth", name="[student] isAuth")


# ---------------------------------------------------------------------------
# Staff User — views menu, ratings; lighter load
# ---------------------------------------------------------------------------

class StaffUser(HttpUser):
    weight = 2
    wait_time = between(2, 5)

    def on_start(self):
        username = random.choice(["verma", "suresh"])
        do_login(self.client, username, "123")

    @task(4)
    def view_dashboard(self):
        self.client.get("/dashboard", name="[staff] dashboard")

    @task(3)
    def view_menu(self):
        self.client.get("/menu", name="[staff] menu")

    @task(2)
    def view_ratings(self):
        self.client.get("/ratings", name="[staff] ratings")

    @task(1)
    def check_auth(self):
        self.client.get("/isAuth", name="[staff] isAuth")