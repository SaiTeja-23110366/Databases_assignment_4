import jwt
from datetime import datetime, timedelta, timezone
from db import mysql, JWT_SECRET, JWT_EXPIRY_HOURS


# ─────────────────────────────────────────────
#  Verify credentials → return user dict or None
# ─────────────────────────────────────────────
from sharding_router import get_all_shard_connections

def login_user(username, password):
    connections = get_all_shard_connections()
    user_data = None
    
    try:
        # Check each shard to find the user
        for conn in connections:
            cur = conn.cursor()
            try:
                cur.execute("SELECT user_id, role, MemberID FROM Users WHERE username=%s AND password=%s", (username, password))
                user = cur.fetchone()
                
                if user:
                    user_id, role, member_id = user
                    
                    # If Admin, log them in immediately
                    if role == 'Admin':
                        user_data = {'role': 'Admin', 'member_id': None, 'member_role': 'Admin', 'sub_id': None}
                        break
                    
                    # If regular user, get their details from the Member table on this same shard
                    if member_id:
                        cur.execute("SELECT Role FROM Member WHERE MemberID = %s", (member_id,))
                        member = cur.fetchone()
                        member_role = member[0] if member else 'Unknown'
                        user_data = {'role': role, 'member_id': member_id, 'member_role': member_role, 'sub_id': None}
                        break
            finally:
                cur.close()
    finally:
        for conn in connections:
            try: conn.close()
            except: pass
        
    return user_data # User dictionary or None
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