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
from sharding_router import get_shard_connection, get_shard_id, get_all_shard_connections

def _next_id(cur, table, pk_col):
    """
    Get next available integer PK for tables that genuinely lack AUTO_INCREMENT
    (e.g. Purchase, WasteLog, MealLog).
    """
    cur.execute(f"SELECT COALESCE(MAX(`{pk_col}`), 0) + 1 FROM `{table}`")
    return cur.fetchone()[0]

# ---------------------------------------------------------------------------
# Atomic Operation 1: Mark Meal Attendance + deduct MealPayment
# ---------------------------------------------------------------------------
def atomic_mark_attendance(member_id, schedule_id, status, amount):
    shard_id = get_shard_id(member_id)
    conn = get_shard_connection(shard_id)
    cur = conn.cursor()
    try:
        # Use base table names now
        meallog_table = 'MealLog'
        log_id = _next_id(cur, meallog_table, 'LogID')
        cur.execute(f"""
            INSERT INTO {meallog_table} (LogID, MemberID, ScheduleID, Status)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE Status = VALUES(Status)
        """, (log_id, member_id, schedule_id, status))

        if status == 'Consumed':
            mealpay_table = 'MealPayment'
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
        conn.close()

# ---------------------------------------------------------------------------
# Atomic Operation 2: Update MonthlyMessPayment status + log in AuditLog
# ---------------------------------------------------------------------------
def atomic_update_billing_status(payment_id, new_status, username):
    connections = get_all_shard_connections()
    updated = False
    error = None

    for conn in connections:
        cur = conn.cursor()
        try:
            # Check if record exists on this shard
            cur.execute("SELECT COUNT(*) FROM MonthlyMessPayment WHERE MonthlyPaymentID = %s", (payment_id,))
            if cur.fetchone()[0] > 0:
                cur.execute("UPDATE MonthlyMessPayment SET Status = %s WHERE MonthlyPaymentID = %s", (new_status, payment_id))
                
                # Log to the same shard's AuditLog
                cur.execute("""
                    INSERT INTO AuditLog (action, username, timestamp)
                    VALUES (%s, %s, NOW())
                """, (f"Updated MonthlyMessPayment #{payment_id} to {new_status}", username))
                
                conn.commit()
                updated = True
                break
        except Exception as e:
            conn.rollback()
            error = str(e)
        finally:
            cur.close()
            if not updated: # Only close if we haven't found/updated yet
                conn.close()

    # Close remaining connections
    for c in connections:
        try:
            c.close()
        except:
            pass

    if updated:
        return True, None
    return False, error or f"Payment ID {payment_id} not found"

# ---------------------------------------------------------------------------
# Atomic Operation 3: Purchase + Inventory + AuditLog  (3-table ACID demo)
# ---------------------------------------------------------------------------
def atomic_purchase_and_stock_update(supplier_id, ingredient_id, quantity,
                                     unit_price, username, simulate_failure=False):
    """
    Since Inventory and Purchase might be global or duplicated, we apply to Shard 0 
    as the 'master' for inventory, or broadcast if necessary. 
    Assuming duplicated for now based on auth logic. Applying to Shard 0 for demo.
    """
    shard_id = 0 # Default to shard 0 for inventory operations
    conn = get_shard_connection(shard_id)
    cur = conn.cursor()
    try:
        total_cost = round(float(quantity) * float(unit_price), 2)
        purchase_id = _next_id(cur, 'Purchase', 'PurchaseID')

        cur.execute("""
            INSERT INTO Purchase
                (PurchaseID, SupplierID, IngredientID, Quantity, UnitPrice, TotalCost, PurchaseDate)
            VALUES (%s, %s, %s, %s, %s, %s, CURDATE())
        """, (purchase_id, supplier_id, ingredient_id, quantity, unit_price, total_cost))

        if simulate_failure:
            raise RuntimeError("Simulated crash after Purchase INSERT — rollback expected")

        cur.execute("""
            UPDATE Inventory
            SET StockQty = StockQty + %s, LastUpdated = CURDATE()
            WHERE IngredientID = %s
        """, (quantity, ingredient_id))

        if cur.rowcount == 0:
            raise ValueError(f"IngredientID {ingredient_id} not found in Inventory")

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
        conn.close()

# ---------------------------------------------------------------------------
# Atomic Operation 4: WasteLog + Inventory deduction + AuditLog
# ---------------------------------------------------------------------------
def atomic_log_waste(schedule_id, waste_qty_kg, category, ingredient_id, username):
    shard_id = 0
    conn = get_shard_connection(shard_id)
    cur = conn.cursor()
    try:
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
        conn.close()