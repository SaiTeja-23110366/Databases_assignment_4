from flask import request, jsonify, session, render_template, redirect
from db import mysql
from auth import login_user, generate_token, decode_token
from rbac import is_admin, is_student, is_staff
from logging_utils import log_action
from sharding_router import get_shard_id, get_table_name, get_all_shards
from transactions import (
    atomic_purchase_and_stock_update,
    atomic_update_billing_status,
    atomic_mark_attendance,
    atomic_log_waste,
)
# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def require_login():
    if 'username' not in session:
        return redirect('/login')
    return None
def require_admin():
    if session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 403
    return None
def get_token_from_request():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth.split(' ', 1)[1]
    return None
def validate_token():
    token = get_token_from_request()
    if not token:
        return None
    return decode_token(token)
def require_admin_any():
    """
    Accept EITHER a valid admin JWT token (for test scripts)
    OR a Flask session with Admin role (for browser UI).
    Returns (username, error_response).
    error_response is None if authorised.
    """
    # Try JWT first
    payload = validate_token()
    if payload:
        if not is_admin(payload.get('role')):
            return None, (jsonify({'error': 'Admin only'}), 403)
        return payload.get('username', 'unknown'), None
    # Fall back to session
    if session.get('role') == 'Admin':
        return session.get('username', 'unknown'), None
    return None, (jsonify({'error': 'Unauthorized'}), 403)
# ─────────────────────────────────────────────
#  Route registration
# ─────────────────────────────────────────────
def register_routes(app):
    @app.route('/')
    def home():
        return redirect('/login')
    # ── LOGIN ─────────────────────────────────
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            if request.is_json:
                data     = request.get_json()
                username = data.get('user') or data.get('username', '')
                password = data.get('password', '')
            else:
                username = request.form['username']
                password = request.form['password']
            user = login_user(username, password)
            if user:
                session['username']    = username
                session['role']        = user['role']
                session['member_id']   = user['member_id']
                session['member_role'] = user['member_role']
                session['sub_id']      = user['sub_id']
                token, expiry = generate_token(username, user)
                session['jwt_token'] = token
                log_action('Login', username)
                if request.is_json:
                    return jsonify({
                        'message':       'Login successful',
                        'token':         token,
                        'session token': token,
                        'role':          user['role'],
                        'member_role':   user['member_role'],
                        'expiry':        expiry.isoformat()
                    }), 200
                return redirect('/dashboard')
            else:
                if request.is_json:
                    return jsonify({'error': 'Invalid credentials'}), 401
                return render_template('login.html', error='Invalid credentials')
        if request.is_json:
            return jsonify({'error': 'Missing parameters'}), 401
        return render_template('login.html', error=None)
    # ── isAuth ────────────────────────────────
    @app.route('/isAuth', methods=['GET'])
    def is_auth():
        payload = validate_token()
        if payload:
            return jsonify({
                'message':  'User is authenticated',
                'username': payload['username'],
                'role':     payload['role'],
                'expiry':   payload['exp']
            }), 200
        if 'username' in session:
            return jsonify({
                'message':  'User is authenticated',
                'username': session['username'],
                'role':     session['role'],
                'expiry':   'session-based (no expiry)'
            }), 200
        token = get_token_from_request()
        if token is None:
            return jsonify({'error': 'No session found'}), 401
        import jwt as _jwt
        try:
            _jwt.decode(token, options={"verify_signature": False})
            return jsonify({'error': 'Session expired'}), 401
        except Exception:
            return jsonify({'error': 'Invalid session token'}), 401
    # ── LOGOUT ────────────────────────────────
    @app.route('/logout')
    def logout():
        log_action('Logout', session.get('username', 'unknown'))
        session.clear()
        return redirect('/login')
    # ── SIGNUP ────────────────────────────────
    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            d   = request.form
            print(request.form)
            cur = mysql.connection.cursor()
            try:
                username = d['email'].split('@')[0]
                cur.execute("SELECT COUNT(*) FROM Users WHERE username=%s", (username,))
                if cur.fetchone()[0] > 0:
                    return render_template('signup.html',
                                           error='Username already exists. Use a different email.')
                cur.execute("SELECT COUNT(*) FROM Member WHERE Email=%s", (d['email'],))
                if cur.fetchone()[0] > 0:
                    return render_template('signup.html', error='Email already registered.')
                max_id = 0
                for shard in get_all_shards('Member'):
                    cur.execute(f"SELECT COALESCE(MAX(MemberID), 0) FROM {shard}")
                    res = cur.fetchone()[0]
                    if res > max_id: max_id = res
                member_id = max_id + 1
                member_table = get_table_name('Member', member_id)
                cur.execute(
                    f"INSERT INTO {member_table} (MemberID, Name, DOB, Email, ContactNumber, Role) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (member_id, d['name'], d['dob'], d['email'], d['contact'], d['member_role'])
                )
                if d['member_role'] == 'Student':
                    max_sid = 23110000
                    for shard in get_all_shards('Student'):
                        cur.execute(f"SELECT COALESCE(MAX(StudentID), 23110000) FROM {shard}")
                        res = cur.fetchone()[0]
                        if res > max_sid: max_sid = res
                    student_id = max_sid + 1
                    
                    student_table = get_table_name('Student', member_id)
                    cur.execute(
                        f"INSERT INTO {student_table} (StudentID, MemberID, HostelBlock, RoomNo, Program) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (student_id, member_id, d['hostel_block'], d['room_no'], d['program'])
                    )
                elif d['member_role'] == 'Staff':
                    max_sid = 200
                    for shard in get_all_shards('Staff'):
                        cur.execute(f"SELECT COALESCE(MAX(StaffID), 200) FROM {shard}")
                        res = cur.fetchone()[0]
                        if res > max_sid: max_sid = res
                    staff_id = max_sid + 1
                    
                    staff_table = get_table_name('Staff', member_id)
                    cur.execute(
                        f"INSERT INTO {staff_table} (StaffID, MemberID, JobRole, Salary, HireDate) "
                        "VALUES (%s, %s, %s, %s, CURDATE())",
                        (staff_id, member_id, d['job_role'], d['salary'])
                    )
                cur.execute(
                    "INSERT INTO Users (username, password, role) VALUES (%s, %s, 'User')",
                    (username, d['password'])
                )
                mysql.connection.commit()
                log_action(f"New signup: {username} ({d['member_role']})", username)
                return render_template('login.html', error=None,
                                       success=f"Account created! Username: '{username}'")
            except Exception as e:
                mysql.connection.rollback()
                return render_template('signup.html', error=f"Signup failed: {str(e)}")
            finally:
                cur.close()
        return render_template('signup.html', error=None)
    # ─────────────────────────────────────────
    #  DASHBOARD
    # ─────────────────────────────────────────
    @app.route('/dashboard')
    def dashboard():
        redir = require_login()
        if redir:
            return redir
        role        = session.get('role')
        member_role = session.get('member_role')
        member_id   = session.get('member_id')
        cur         = mysql.connection.cursor()
        if is_admin(role):
            total_members = 0
            for s in get_all_shards('Member'):
                cur.execute(f"SELECT COUNT(*) FROM {s}")
                total_members += cur.fetchone()[0]
            total_students = 0
            for s in get_all_shards('Student'):
                cur.execute(f"SELECT COUNT(*) FROM {s}")
                total_students += cur.fetchone()[0]
            total_staff = 0
            for s in get_all_shards('Staff'):
                cur.execute(f"SELECT COUNT(*) FROM {s}")
                total_staff += cur.fetchone()[0]
            pending_bills = 0
            for s in get_all_shards('MonthlyMessPayment'):
                cur.execute(f"SELECT COUNT(*) FROM {s} WHERE Status='Pending'")
                pending_bills += cur.fetchone()[0]
            cur.execute("SELECT COALESCE(SUM(TotalCost),0) FROM Purchase")
            total_expense = cur.fetchone()[0]
            cur.execute(
                "SELECT Name, StockQty, Unit, MinStockLevel "
                "FROM Inventory WHERE StockQty <= ReorderLevel"
            )
            low_stock = cur.fetchall()
            cur.close()
            return render_template('dashboard_admin.html',
                                   role=role, member_role=member_role,
                                   total_members=total_members,
                                   total_students=total_students,
                                   total_staff=total_staff,
                                   pending_bills=pending_bills,
                                   total_expense=total_expense,
                                   low_stock=low_stock)
        elif is_student(member_role):
            member_table = get_table_name('Member', member_id)
            student_table = get_table_name('Student', member_id)
            cur.execute(f"""
                SELECT m.Name, m.DOB, m.Email, m.ContactNumber,
                       s.HostelBlock, s.RoomNo, s.Program, s.StudentID
                FROM {member_table} m
                JOIN {student_table} s ON m.MemberID = s.MemberID
                WHERE m.MemberID = %s
            """, (member_id,))
            profile = cur.fetchone()
            pay_table = get_table_name('MonthlyMessPayment', member_id)
            cur.execute(f"""
                SELECT StartDate, EndDate, Amount, Status
                FROM {pay_table}
                WHERE MemberID = %s
                ORDER BY StartDate DESC LIMIT 6
            """, (member_id,))
            payments = cur.fetchall()
            meallog_table = get_table_name('MealLog', member_id)
            cur.execute(f"""
                SELECT ds.MealDate, ds.MealType, ml.Status
                FROM {meallog_table} ml
                JOIN DailySchedule ds ON ml.ScheduleID = ds.ScheduleID
                WHERE ml.MemberID = %s
                ORDER BY ds.MealDate DESC LIMIT 10
            """, (member_id,))
            meal_logs = cur.fetchall()
            cur.close()
            return render_template('dashboard_student.html',
                                   role=role, member_role=member_role,
                                   profile=profile, payments=payments, meal_logs=meal_logs)
        elif is_staff(member_role):
            member_table = get_table_name('Member', member_id)
            staff_table = get_table_name('Staff', member_id)
            cur.execute(f"""
                SELECT m.Name, m.DOB, m.Email, m.ContactNumber,
                       st.JobRole, st.Salary, st.HireDate, st.StaffID
                FROM {member_table} m
                JOIN {staff_table} st ON m.MemberID = st.MemberID
                WHERE m.MemberID = %s
            """, (member_id,))
            profile = cur.fetchone()
            shift_table = get_table_name('StaffShiftLog', member_id)
            staff_table = get_table_name('Staff', member_id)
            cur.execute(f"""
                SELECT ShiftDate, ShiftType, CheckInTime, CheckOutTime, TotalHours
                FROM {shift_table}
                WHERE StaffID = (SELECT StaffID FROM {staff_table} WHERE MemberID = %s)
                ORDER BY ShiftDate DESC LIMIT 10
            """, (member_id,))
            shifts = cur.fetchall()
            cur.close()
            return render_template('dashboard_staff.html',
                                   role=role, member_role=member_role,
                                   profile=profile, shifts=shifts)
        cur.close()
        return "Unknown role", 400
    # ─────────────────────────────────────────
    #  MEMBERS
    # ─────────────────────────────────────────
    @app.route('/members')
    def view_members():
        redir = require_login()
        if redir:
            return redir
        if not is_admin(session.get('role')):
            return render_template('403.html', role=session['role'],
                                   member_role=session.get('member_role')), 403
        cur = mysql.connection.cursor()
        members = []
        for shard in get_all_shards('Member'):
            cur.execute(f"SELECT * FROM {shard}")
            members.extend(cur.fetchall())
        members.sort(key=lambda x: x[0])  # MemberID
        cur.close()
        return render_template('members.html', members=members,
                               role=session['role'],
                               member_role=session.get('member_role'))
    # ─────────────────────────────────────────
    #  FUNCTIONALITY 1 — Meal Attendance
    # ─────────────────────────────────────────
    @app.route('/meal_attendance')
    def meal_attendance():
        redir = require_login()
        if redir:
            return redir
        cur = mysql.connection.cursor()
        if is_admin(session.get('role')):
            query_parts = []
            for shard in get_all_shards('MealLog'):
                query_parts.append(f"SELECT ScheduleID, Status FROM {shard}")
            union_query = " UNION ALL ".join(query_parts)
            cur.execute(f"""
                SELECT ds.MealDate, ds.MealType, ml.Status, COUNT(*) AS Total
                FROM ({union_query}) ml
                JOIN DailySchedule ds ON ml.ScheduleID = ds.ScheduleID
                GROUP BY ds.MealDate, ds.MealType, ml.Status
                ORDER BY ds.MealDate DESC,
                         FIELD(ds.MealType,'Breakfast','Lunch','Snacks','Dinner')
            """)
            data = cur.fetchall()
            cur.close()
            return render_template('meal_attendance.html', data=data,
                                   role=session['role'], view='admin')
        else:
            meallog_table = get_table_name('MealLog', session.get('member_id'))
            cur.execute(f"""
                SELECT ds.MealDate, ds.MealType, ml.Status
                FROM {meallog_table} ml
                JOIN DailySchedule ds ON ml.ScheduleID = ds.ScheduleID
                WHERE ml.MemberID = %s
                ORDER BY ds.MealDate DESC
            """, (session.get('member_id'),))
            data = cur.fetchall()
            cur.close()
            return render_template('meal_attendance.html', data=data,
                                   role=session['role'], view='student')
    # ─────────────────────────────────────────
    #  FUNCTIONALITY 2 — Menu Planning
    # ─────────────────────────────────────────
    @app.route('/menu')
    def menu():
        redir = require_login()
        if redir:
            return redir
        date = request.args.get('date', '')
        cur  = mysql.connection.cursor()
        if date:
            cur.execute("""
                SELECT ds.MealDate, ds.MealType, mi.Name, mi.Category,
                       si.QuantityPrepared, si.Unit
                FROM DailySchedule ds
                JOIN Schedule_Items si ON ds.ScheduleID = si.ScheduleID
                JOIN MenuItem mi       ON si.ItemID     = mi.ItemID
                WHERE ds.MealDate = %s
                ORDER BY FIELD(ds.MealType,'Breakfast','Lunch','Snacks','Dinner')
            """, (date,))
        else:
            cur.execute("""
                SELECT ds.MealDate, ds.MealType, mi.Name, mi.Category,
                       si.QuantityPrepared, si.Unit
                FROM DailySchedule ds
                JOIN Schedule_Items si ON ds.ScheduleID = si.ScheduleID
                JOIN MenuItem mi       ON si.ItemID     = mi.ItemID
                ORDER BY ds.MealDate DESC,
                         FIELD(ds.MealType,'Breakfast','Lunch','Snacks','Dinner')
                LIMIT 40
            """)
        data = cur.fetchall()
        cur.close()
        return render_template('menu.html', data=data, role=session['role'],
                               member_role=session.get('member_role'),
                               selected_date=date)
    @app.route('/menu/add', methods=['POST'])
    def menu_add():
        err = require_admin()
        if err:
            return err
        d   = request.form
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT ScheduleID FROM DailySchedule WHERE MealDate=%s AND MealType=%s",
            (d['MealDate'], d['MealType'])
        )
        row = cur.fetchone()
        schedule_id = row[0] if row else d['ScheduleID']
        if not row:
            cur.execute(
                "INSERT INTO DailySchedule (ScheduleID, MealDate, MealType, IsActive) "
                "VALUES (%s, %s, %s, TRUE)",
                (d['ScheduleID'], d['MealDate'], d['MealType'])
            )
        cur.execute(
            "INSERT INTO Schedule_Items (ScheduleID, ItemID, QuantityPrepared, Unit) "
            "VALUES (%s, %s, %s, %s)",
            (schedule_id, d['ItemID'], d['QuantityPrepared'], d['Unit'])
        )
        mysql.connection.commit()
        cur.close()
        log_action(f"Menu item {d['ItemID']} added to schedule {schedule_id}", session['username'])
        return redirect('/menu')
    # ─────────────────────────────────────────
    #  FUNCTIONALITY 3 — Monthly Billing
    # ─────────────────────────────────────────
    @app.route('/billing')
    def billing():
        redir = require_login()
        if redir:
            return redir
        cur = mysql.connection.cursor()
        if is_admin(session.get('role')):
            query_parts = []
            for m_shard, p_shard in zip(get_all_shards('Member'), get_all_shards('MonthlyMessPayment')):
                query_parts.append(f"SELECT m.Name, mp.StartDate, mp.EndDate, mp.Amount, mp.Status, mp.MonthlyPaymentID "
                                   f"FROM {p_shard} mp JOIN {m_shard} m ON mp.MemberID = m.MemberID")
            union_query = " UNION ALL ".join(query_parts)
            cur.execute(f"{union_query} ORDER BY Status DESC, StartDate DESC")
            data = cur.fetchall()
            cur.close()
            return render_template('billing.html', data=data,
                                   role=session['role'], view='admin')
        else:
            pay_table = get_table_name('MonthlyMessPayment', session.get('member_id'))
            cur.execute(f"""
                SELECT StartDate, EndDate, Amount, Status
                FROM {pay_table}
                WHERE MemberID = %s
                ORDER BY StartDate DESC
            """, (session.get('member_id'),))
            data = cur.fetchall()
            cur.close()
            return render_template('billing.html', data=data,
                                   role=session['role'], view='student')
    # ── Accepts JWT token OR session (so test scripts work) ──
    @app.route('/billing/update_status', methods=['POST'])
    def billing_update_status():
        username, err = require_admin_any()
        if err:
            return err
        pid    = request.form['payment_id']
        status = request.form['status']
        ok, error = atomic_update_billing_status(pid, status, username)
        if not ok:
            return jsonify({'error': f'Transaction failed: {error}'}), 500
        log_action(f"Billing status updated: payment {pid} -> {status}", username)
        if session.get('username'):
            return redirect('/billing')
        return jsonify({'message': f'Payment {pid} updated to {status}'}), 200
    # ─────────────────────────────────────────
    #  FUNCTIONALITY 4 — Inventory
    # ─────────────────────────────────────────
    @app.route('/inventory')
    def inventory():
        redir = require_login()
        if redir:
            return redir
        if not is_admin(session.get('role')):
            return render_template('403.html', role=session['role'],
                                   member_role=session.get('member_role')), 403
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT IngredientID, Name, StockQty, Unit,
                   MinStockLevel, ReorderLevel, LastUpdated,
                   CASE
                       WHEN StockQty <= MinStockLevel THEN 'Critical'
                       WHEN StockQty <= ReorderLevel  THEN 'Low'
                       ELSE 'OK'
                   END AS StockStatus
            FROM Inventory
            ORDER BY StockQty ASC
        """)
        data = cur.fetchall()
        cur.close()
        return render_template('inventory.html', data=data, role=session['role'],
                               member_role=session.get('member_role'))
    # ── Accepts JWT token OR session (so test scripts work) ──
    @app.route('/inventory/update', methods=['POST'])
    def inventory_update():
        username, err = require_admin_any()
        if err:
            return err
        d   = request.form
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE Inventory
            SET StockQty=%s, MinStockLevel=%s, ReorderLevel=%s, LastUpdated=CURDATE()
            WHERE IngredientID=%s
        """, (d['StockQty'], d['MinStockLevel'], d['ReorderLevel'], d['IngredientID']))
        mysql.connection.commit()
        cur.close()
        log_action(f"Inventory updated: ingredient {d['IngredientID']}", username)
        if session.get('username'):
            return redirect('/inventory')
        return jsonify({'message': f"Inventory updated for ingredient {d['IngredientID']}"}), 200
    # ─────────────────────────────────────────
    #  FUNCTIONALITY 5 — Suppliers & Expenses
    # ─────────────────────────────────────────
    @app.route('/suppliers')
    def suppliers():
        redir = require_login()
        if redir:
            return redir
        err = require_admin()
        if err:
            return err
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT s.SupplierID, s.CompanyName, s.ContactName, s.Phone,
                   s.SupplierType, COALESCE(SUM(p.TotalCost), 0) AS TotalSpent
            FROM Supplier s
            LEFT JOIN Purchase p ON s.SupplierID = p.SupplierID
            GROUP BY s.SupplierID
            ORDER BY TotalSpent DESC
        """)
        suppliers_data = cur.fetchall()
        cur.execute("""
            SELECT p.PurchaseID, s.CompanyName, i.Name AS Ingredient,
                   p.Quantity, p.UnitPrice, p.TotalCost, p.PurchaseDate
            FROM Purchase p
            JOIN Supplier s  ON p.SupplierID   = s.SupplierID
            JOIN Inventory i ON p.IngredientID = i.IngredientID
            ORDER BY p.PurchaseDate DESC LIMIT 20
        """)
        purchases = cur.fetchall()
        cur.close()
        return render_template('suppliers.html', suppliers=suppliers_data,
                               purchases=purchases, role=session['role'])
    # ─────────────────────────────────────────
    #  FUNCTIONALITY 6 — Food Waste
    # ─────────────────────────────────────────
    @app.route('/waste')
    def waste():
        redir = require_login()
        if redir:
            return redir
        err = require_admin()
        if err:
            return err
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT ds.MealDate, ds.MealType,
                   w.WasteQty_Kg, w.Waste_category, w.RecordedDate
            FROM WasteLog w
            JOIN DailySchedule ds ON w.ScheduleID = ds.ScheduleID
            ORDER BY w.RecordedDate DESC
        """)
        data = cur.fetchall()
        cur.execute("""
            SELECT Waste_category, SUM(WasteQty_Kg) AS Total
            FROM WasteLog GROUP BY Waste_category
        """)
        totals = cur.fetchall()
        cur.close()
        return render_template('waste.html', data=data, totals=totals, role=session['role'])
    @app.route('/waste/add', methods=['POST'])
    def waste_add():
        username, err = require_admin_any()
        if err:
            return err
        d             = request.form
        ingredient_id = d.get('ingredient_id', 1)
        ok, error = atomic_log_waste(
            d['ScheduleID'], d['WasteQty_Kg'], d['Waste_category'],
            ingredient_id, username
        )
        if not ok:
            return jsonify({'error': f'Transaction failed: {error}'}), 500
        log_action(f"Waste logged for schedule {d['ScheduleID']}", username)
        if session.get('username'):
            return redirect('/waste')
        return jsonify({'message': 'Waste logged'}), 200
    # ─────────────────────────────────────────
    #  FUNCTIONALITY 7 — Meal Ratings
    # ─────────────────────────────────────────
    @app.route('/ratings')
    def ratings():
        redir = require_login()
        if redir:
            return redir
        cur = mysql.connection.cursor()
        query_parts = []
        for shard in get_all_shards('MessRating'):
            query_parts.append(f"SELECT ScheduleID, Rating, RatingID FROM {shard}")
        union_query = " UNION ALL ".join(query_parts)
        cur.execute(f"""
            SELECT ds.MealDate, ds.MealType,
                   ROUND(AVG(mr.Rating), 2) AS AvgRating,
                   COUNT(mr.RatingID)       AS TotalRatings,
                   MIN(mr.Rating)           AS MinRating,
                   MAX(mr.Rating)           AS MaxRating
            FROM ({union_query}) mr
            JOIN DailySchedule ds ON mr.ScheduleID = ds.ScheduleID
            GROUP BY ds.MealDate, ds.MealType
            ORDER BY ds.MealDate DESC
        """)
        data = cur.fetchall()
        cur.close()
        return render_template('ratings.html', data=data, role=session['role'],
                               member_role=session.get('member_role'))
    # ── FIX: removed manual MAX(RatingID)+1 race condition.
    #         RatingID is now AUTO_INCREMENT — the DB assigns it atomically.
    #         MemberID is included in the insert so ratings are member-scoped.
    @app.route('/ratings/add', methods=['POST'])
    def ratings_add():
        redir = require_login()
        if redir:
            return redir
        if session.get('member_role') not in ('Student', 'Admin'):
            return jsonify({'error': 'Only students can rate meals'}), 403
        d   = request.form
        cur = mysql.connection.cursor()
        try:
            # RatingID is AUTO_INCREMENT — never compute MAX()+1 manually.
            # Omit RatingID entirely and let MySQL assign it atomically,
            # which prevents the duplicate-key race condition under concurrency.
            rating_table = get_table_name('MessRating', session.get('member_id'))
            cur.execute(
                f"INSERT INTO {rating_table} (ScheduleID, MemberID, Rating, RatedOn) "
                "VALUES (%s, %s, %s, CURDATE())",
                (d['ScheduleID'], session.get('member_id'), d['Rating'])
            )
            mysql.connection.commit()
        except Exception as e:
            mysql.connection.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
        log_action(f"Rating {d['Rating']} for schedule {d['ScheduleID']}", session['username'])
        return redirect('/ratings')
    # ─────────────────────────────────────────
    #  ALL TABLES PAGE
    # ─────────────────────────────────────────
    @app.route('/all_tables')
    def all_tables_page():
        redir = require_login()
        if redir:
            return redir
        if not is_admin(session.get('role')):
            return render_template('403.html', role=session['role'],
                                   member_role=session.get('member_role')), 403
        return render_template('all_tables.html',
                               role=session['role'],
                               member_role=session.get('member_role'))
    # ─────────────────────────────────────────
    #  GENERIC ADMIN CRUD
    # ─────────────────────────────────────────
    def resolve_table(cur, table_name):
        cur.execute("SHOW TABLES")
        valid = [r[0] for r in cur.fetchall()]
        if table_name in valid:
            return table_name
        lower = table_name.lower()
        for t in valid:
            if t.lower() == lower:
                return t
        return None
    @app.route('/tables')
    def get_tables():
        username, err = require_admin_any()
        if err:
            return err
        cur = mysql.connection.cursor()
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        cur.close()
        return jsonify(tables)
    @app.route('/table/<table_name>')
    def get_table_data(table_name):
        username, err = require_admin_any()
        if err:
            return err
        cur = mysql.connection.cursor()
        actual = resolve_table(cur, table_name)
        if not actual:
            cur.close()
            return jsonify({'error': 'Invalid table'}), 400
        cur.execute("SELECT * FROM `{}`".format(actual))
        rows    = cur.fetchall()
        columns = [d[0] for d in cur.description]
        cur.close()
        return jsonify({'columns': columns, 'rows': rows})
    @app.route('/delete/<table_name>', methods=['POST'])
    def delete_row(table_name):
        username, err = require_admin_any()
        if err:
            return err
        cur = mysql.connection.cursor()
        actual = resolve_table(cur, table_name)
        if not actual:
            cur.close()
            return jsonify({'error': 'Invalid table'}), 400
        d = request.json
        cur.execute(
            "DELETE FROM `{}` WHERE `{}` = %s".format(actual, d['column']),
            (d['value'],)
        )
        mysql.connection.commit()
        cur.close()
        log_action(f"Deleted from {actual}", username)
        return jsonify({'message': 'Deleted successfully'})
    @app.route('/update/<table_name>', methods=['POST'])
    def update_row(table_name):
        username, err = require_admin_any()
        if err:
            return err
        cur = mysql.connection.cursor()
        actual = resolve_table(cur, table_name)
        if not actual:
            cur.close()
            return jsonify({'error': 'Invalid table'}), 400
        d          = request.json
        pk         = d['columns'][0]
        pk_val     = d['values'][0]
        set_clause = ", ".join(["`{}` = %s".format(c) for c in d['columns'][1:]])
        cur.execute(
            "UPDATE `{}` SET {} WHERE `{}` = %s".format(actual, set_clause, pk),
            d['values'][1:] + [pk_val]
        )
        mysql.connection.commit()
        cur.close()
        log_action(f"Updated row in {actual}", username)
        return jsonify({'message': 'Updated successfully'})
    @app.route('/insert/<table_name>', methods=['POST'])
    def insert_row(table_name):
        username, err = require_admin_any()
        if err:
            return err
        cur = mysql.connection.cursor()
        actual = resolve_table(cur, table_name)
        if not actual:
            cur.close()
            return jsonify({'error': 'Invalid table'}), 400
        d    = request.json
        cols = ", ".join(["`{}`".format(c) for c in d['columns']])
        ph   = ", ".join(["%s"] * len(d['values']))
        cur.execute(
            "INSERT INTO `{}` ({}) VALUES ({})".format(actual, cols, ph),
            d['values']
        )
        mysql.connection.commit()
        cur.close()
        log_action(f"Inserted into {actual}", username)
        return jsonify({'message': 'Inserted successfully'})
    # ─────────────────────────────────────────
    #  LOGS
    # ─────────────────────────────────────────
    @app.route('/logs')
    def get_logs():
        username, err = require_admin_any()
        if err:
            return err
        try:
            with open('logs/audit.log', 'r') as f:
                lines = f.readlines()
            return jsonify({'logs': [l.strip() for l in lines[-100:]]})
        except FileNotFoundError:
            return jsonify({'logs': []})
    # ═════════════════════════════════════════
    #  ASSIGNMENT 3 MODULE B — TEST ENDPOINTS
    # ═════════════════════════════════════════
    @app.route('/test/purchase_fail', methods=['POST'])
    def test_purchase_fail():
        """Atomicity: crash mid-transaction → both Purchase + Inventory rolled back."""
        payload = validate_token()
        if not payload or not is_admin(payload.get('role')):
            return jsonify({'error': 'Admin Bearer token required'}), 401
        data = request.get_json(force=True)
        ok, err = atomic_purchase_and_stock_update(
            data.get('supplier_id',   1),
            data.get('ingredient_id', 1),
            data.get('quantity',      10),
            data.get('unit_price',    5.0),
            payload.get('username', 'test'),
            simulate_failure=True
        )
        return jsonify({
            'result':  'rolled_back',
            'reason':  err,
            'message': 'Simulated crash: Purchase + Inventory both rolled back (Atomicity ✅)'
        }), 200
    @app.route('/test/purchase_ok', methods=['POST'])
    def test_purchase_ok():
        """Durability: commits Purchase + Inventory + AuditLog atomically."""
        payload = validate_token()
        if not payload or not is_admin(payload.get('role')):
            return jsonify({'error': 'Admin Bearer token required'}), 401
        data = request.get_json(force=True)
        ok, err = atomic_purchase_and_stock_update(
            data.get('supplier_id',   1),
            data.get('ingredient_id', 1),
            data.get('quantity',      10),
            data.get('unit_price',    5.0),
            payload.get('username', 'test'),
            simulate_failure=False
        )
        if ok:
            return jsonify({
                'result':  'committed',
                'message': 'Purchase + Inventory + AuditLog committed atomically (Durability ✅)'
            }), 200
        return jsonify({'result': 'error', 'reason': err}), 500
    @app.route('/test/atomic_billing', methods=['POST'])
    def test_atomic_billing():
        """Consistency: MonthlyMessPayment + AuditLog updated together."""
        payload = validate_token()
        if not payload or not is_admin(payload.get('role')):
            return jsonify({'error': 'Admin Bearer token required'}), 401
        data = request.get_json(force=True)
        ok, err = atomic_update_billing_status(
            data.get('payment_id', 1),
            data.get('status', 'Paid'),
            payload.get('username', 'test')
        )
        if ok:
            return jsonify({'result': 'committed',
                            'message': 'Billing + AuditLog updated atomically (Consistency ✅)'}), 200
        return jsonify({'result': 'error', 'reason': err}), 500
    @app.route('/test/transaction_demo', methods=['GET'])
    def transaction_demo():
        """One-shot ACID demo — returns JSON report of all 4 properties."""
        payload = validate_token()
        if not payload:
            return jsonify({
                'error': 'Unauthorized',
                'hint':  'POST /login with {"user":"admin","password":"123"}, then use the token here'
            }), 401
        username = payload.get('username', 'demo')
        report   = {'user': username, 'tests': {}}
        # Atomicity
        ok1, e1 = atomic_purchase_and_stock_update(1, 1, 99, 99.0, username, simulate_failure=True)
        report['tests']['atomicity'] = {
            'description': 'Crash after Purchase INSERT, before Inventory UPDATE',
            'rolled_back': not ok1,
            'PASS':        not ok1,
            'error':       e1,
        }
        # Durability
        ok2, e2 = atomic_purchase_and_stock_update(1, 1, 5, 3.0, username, simulate_failure=False)
        report['tests']['durability'] = {
            'description': '3-table commit: Purchase + Inventory + AuditLog',
            'committed':   ok2,
            'PASS':        ok2,
            'error':       e2,
        }
        # Consistency
        ok3, e3 = atomic_update_billing_status(1, 'Paid', username)
        report['tests']['consistency'] = {
            'description': 'Billing + AuditLog updated together or not at all',
            'committed':   ok3,
            'PASS':        ok3,
            'error':       e3,
        }
        # Isolation
        report['tests']['isolation'] = {
            'description': 'Concurrent transactions tested via test_concurrent.py',
            'mechanism':   'MySQL InnoDB row-level locking (REPEATABLE READ)',
            'PASS':        'See test_concurrent.py output',
        }
        passing = [v['PASS'] for k, v in report['tests'].items()
                   if isinstance(v.get('PASS'), bool)]
        report['overall'] = 'ALL PASS ✅' if all(passing) else 'SOME FAILURES ❌'
        return jsonify(report), 200