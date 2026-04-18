"""
transactions.py
---------------
MySQL transaction helpers for the Mess Management System.
Wraps multi-table operations in proper BEGIN / COMMIT / ROLLBACK blocks.
NOTE on AuditLog inserts:
  AuditLog.log_id is AUTO_INCREMENT in the schema, so we never compute
  MAX(log_id)+1 manually — that pattern races under concurrency just like
  the MessRating bug it mirrors. We omit log_id entirely and let MySQL
  assign it atomically.
"""
from db import mysql
from sharding_router import get_table_name, get_all_shards
def _next_id(cur, table, pk_col):
    """
    Get next available integer PK for tables that genuinely lack AUTO_INCREMENT
    (e.g. Purchase, WasteLog, MealLog).  Do NOT use this for AuditLog or
    MessRating — those columns are AUTO_INCREMENT.
    """
    cur.execute(f"SELECT COALESCE(MAX(`{pk_col}`), 0) + 1 FROM `{table}`")
    return cur.fetchone()[0]
# ---------------------------------------------------------------------------
# Atomic Operation 1: Mark Meal Attendance + deduct MealPayment
# ---------------------------------------------------------------------------
def atomic_mark_attendance(member_id, schedule_id, status, amount):
    conn = mysql.connection
    conn.autocommit(False)
    cur = conn.cursor()
    try:
        meallog_table = get_table_name('MealLog', member_id)
        log_id = _next_id(cur, meallog_table, 'LogID')
        cur.execute(f"""
            INSERT INTO {meallog_table} (LogID, MemberID, ScheduleID, Status)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE Status = VALUES(Status)
        """, (log_id, member_id, schedule_id, status))
        if status == 'Consumed':
            mealpay_table = get_table_name('MealPayment', member_id)
            meal_pay_id = _next_id(cur, mealpay_table, 'MealPaymentID')
            cur.execute(f"""
                INSERT INTO {mealpay_table} (MealPaymentID, MemberID, ScheduleID, Amount, PaymentDate)
                VALUES (%s, %s, %s, %s, CURDATE())
                ON DUPLICATE KEY UPDATE Amount = VALUES(Amount)
            """, (meal_pay_id, member_id, schedule_id, amount))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
# ---------------------------------------------------------------------------
# Atomic Operation 2: Update MonthlyMessPayment status + log in AuditLog
# ---------------------------------------------------------------------------
def atomic_update_billing_status(payment_id, new_status, username):
    conn = mysql.connection
    conn.autocommit(False)
    cur = conn.cursor()
    try:
        # Verify the payment exists BEFORE updating.
        # We cannot use `cur.rowcount == 0` after the UPDATE because MySQL
        # returns rowcount=0 when the new value equals the existing value
        # (e.g. setting Status='Paid' on a row already 'Paid'). Under concurrent
        # load this causes every thread after the first to raise a false ValueError
        # and roll back, producing ~97% errors even though the UPDATE succeeded.
        updated = False
        for shard in get_all_shards('MonthlyMessPayment'):
            cur.execute(f"SELECT COUNT(*) FROM {shard} WHERE MonthlyPaymentID = %s", (payment_id,))
            if cur.fetchone()[0] > 0:
                cur.execute(f"UPDATE {shard} SET Status = %s WHERE MonthlyPaymentID = %s", (new_status, payment_id))
                updated = True
                break
        if not updated:
            raise ValueError(f"Payment ID {payment_id} not found")
        # AuditLog.log_id is AUTO_INCREMENT — omit it, let MySQL assign atomically.
        cur.execute("""
            INSERT INTO AuditLog (action, username, timestamp)
            VALUES (%s, %s, NOW())
        """, (f"Updated MonthlyMessPayment #{payment_id} to {new_status}", username))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
# ---------------------------------------------------------------------------
# Atomic Operation 3: Purchase + Inventory + AuditLog  (3-table ACID demo)
# ---------------------------------------------------------------------------
def atomic_purchase_and_stock_update(supplier_id, ingredient_id, quantity,
                                     unit_price, username, simulate_failure=False):
    """
    Atomically:
      1. INSERT into Purchase
      2. UPDATE Inventory.StockQty += quantity
      3. INSERT into AuditLog
    simulate_failure=True crashes AFTER step 1 but BEFORE commit → rollback demo.
    Returns: (True, None) or (False, error_str)
    """
    conn = mysql.connection
    conn.autocommit(False)
    cur = conn.cursor()
    try:
        total_cost = round(float(quantity) * float(unit_price), 2)
        # Purchase lacks AUTO_INCREMENT in the schema — use _next_id safely here.
        purchase_id = _next_id(cur, 'Purchase', 'PurchaseID')
        # Step 1 — record purchase
        cur.execute("""
            INSERT INTO Purchase
                (PurchaseID, SupplierID, IngredientID, Quantity, UnitPrice, TotalCost, PurchaseDate)
            VALUES (%s, %s, %s, %s, %s, %s, CURDATE())
        """, (purchase_id, supplier_id, ingredient_id, quantity, unit_price, total_cost))
        # ← SIMULATED CRASH (atomicity demo)
        if simulate_failure:
            raise RuntimeError("Simulated crash after Purchase INSERT — rollback expected")
        # Step 2 — update stock
        cur.execute("""
            UPDATE Inventory
            SET StockQty = StockQty + %s, LastUpdated = CURDATE()
            WHERE IngredientID = %s
        """, (quantity, ingredient_id))
        if cur.rowcount == 0:
            raise ValueError(f"IngredientID {ingredient_id} not found in Inventory")
        # Step 3 — audit (AUTO_INCREMENT: omit log_id)
        cur.execute("""
            INSERT INTO AuditLog (action, username, timestamp)
            VALUES (%s, %s, NOW())
        """, (f"Purchase#{purchase_id}: +{quantity} units of Ingredient#{ingredient_id} "
              f"from Supplier#{supplier_id}", username))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
# ---------------------------------------------------------------------------
# Atomic Operation 4: WasteLog + Inventory deduction + AuditLog
# ---------------------------------------------------------------------------
def atomic_log_waste(schedule_id, waste_qty_kg, category, ingredient_id, username):
    conn = mysql.connection
    conn.autocommit(False)
    cur = conn.cursor()
    try:
        # WasteLog lacks AUTO_INCREMENT — use _next_id.
        waste_id = _next_id(cur, 'WasteLog', 'WasteID')
        cur.execute("""
            INSERT INTO WasteLog (WasteID, ScheduleID, WasteQty_Kg, Waste_category, RecordedDate)
            VALUES (%s, %s, %s, %s, CURDATE())
        """, (waste_id, schedule_id, waste_qty_kg, category))
        cur.execute("""
            UPDATE Inventory
            SET StockQty = GREATEST(0, StockQty - %s), LastUpdated = CURDATE()
            WHERE IngredientID = %s
        """, (waste_qty_kg, ingredient_id))
        # AuditLog.log_id is AUTO_INCREMENT — omit it, let MySQL assign atomically.
        cur.execute("""
            INSERT INTO AuditLog (action, username, timestamp)
            VALUES (%s, %s, NOW())
        """, (f"WasteLog#{waste_id}: {waste_qty_kg}kg '{category}' for Schedule#{schedule_id}",
              username))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()