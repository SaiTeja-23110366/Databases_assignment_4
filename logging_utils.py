import os
from datetime import datetime

LOG_FILE = "logs/audit.log"

def log_action(action, username):
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()} | {username} | {action}\n")

    # Also persist to DB AuditLog table (best-effort)
    try:
        from db import mysql
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO AuditLog (action, username) VALUES (%s, %s)",
            (action, username)
        )
        mysql.connection.commit()
    except Exception:
        pass