import jwt
from datetime import datetime, timedelta, timezone
from db import mysql, JWT_SECRET, JWT_EXPIRY_HOURS
from sharding_router import get_table_name

# ─────────────────────────────────────────────
#  Verify credentials → return user dict or None
# ─────────────────────────────────────────────
def login_user(username, password):
    print("LOGIN STARTED")
    cur = mysql.connection.cursor()
    print("DB CONNECTED")

    # ✅ FIX 1: Fetch member_id also
    cur.execute(
    "SELECT user_id, role FROM Users WHERE username=%s AND password=%s",
    (username, password)
    )

    user = cur.fetchone()
    if not user:
        cur.close()
        return None

    # ✅ FIX 2: unpack member_id properly
    user_id, role = user
    member_id = user_id

    # Admin — no Member record needed
    if role == 'Admin':
        cur.close()
        return {
            'role':        'Admin',
            'member_id':   None,
            'member_role': 'Admin',
            'sub_id':      None
        }

    # If no member_id → invalid mapping
    if not member_id:
        cur.close()
        return {
            'role':        role,
            'member_id':   None,
            'member_role': 'Unknown',
            'sub_id':      None
        }

    # ✅ FIX 3: lowercase table names
    member_table = get_table_name('member', member_id)

    cur.execute(
        f"SELECT Role FROM {member_table} WHERE MemberID = %s",
        (member_id,)
    )
    print("QUERY EXECUTED:")
    member = cur.fetchone()
    if not member:
        cur.close()
        return {
            'role':        role,
            'member_id':   member_id,
            'member_role': 'Unknown',
            'sub_id':      None
        }

    member_role = member[0]   # 'Student' or 'Staff'
    sub_id = None

    if member_role == 'Student':
        student_table = get_table_name('student', member_id)
        cur.execute(
            f"SELECT StudentID FROM {student_table} WHERE MemberID=%s",
            (member_id,)
        )
        row = cur.fetchone()
        sub_id = row[0] if row else None

    elif member_role == 'Staff':
        staff_table = get_table_name('staff', member_id)
        cur.execute(
            f"SELECT StaffID FROM {staff_table} WHERE MemberID=%s",
            (member_id,)
        )
        row = cur.fetchone()
        sub_id = row[0] if row else None

    cur.close()

    return {
        'role':        role,
        'member_id':   member_id,
        'member_role': member_role,
        'sub_id':      sub_id
    }
    print("USER FETCHED:", user)  


# ─────────────────────────────────────────────
#  Generate a JWT token for a logged-in user
# ─────────────────────────────────────────────
def generate_token(username, user_dict):
    expiry = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)

    payload = {
        'username':    username,
        'role':        user_dict['role'],
        'member_role': user_dict['member_role'],
        'member_id':   user_dict['member_id'],
        'sub_id':      user_dict['sub_id'],
        'exp':         expiry
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
    return token, expiry


# ─────────────────────────────────────────────
#  Decode and validate a JWT token
# ─────────────────────────────────────────────
def decode_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None