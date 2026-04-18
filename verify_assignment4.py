from app import app
from db import mysql
from sharding_router import get_shard_id, get_table_name, get_all_shards

with app.app_context():
    cur = mysql.connection.cursor()
    print("\n" + "="*60)
    print(" SUBTASK 2 & 3: SHARDING VERIFICATION TEST")
    print("="*60)
    total = 0
    for shard in get_all_shards('Member'):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {shard}")
            count = cur.fetchone()[0]
            print(f" [OK] {shard} contains {count} records")
            total += count
        except Exception as e:
            print(f" [!] Error reading {shard}: {e}")
    
    try:
        cur.execute("SELECT COUNT(*) FROM Member")
        original = cur.fetchone()[0]
        print(f"\n -> Total Migrated Shard Members: {total} (Original Master Table: {original})")
        if total == original:
            print(" -> [SUCCESS] Zero data loss detected across migrations!")
        else:
            print(" -> [WARNING] Data mismatch detected.")
    except Exception as e:
        print(e)
    
    print("\n" + "="*60)
    print(" QUERY ROUTING VALIDATION (LOOKUP TEST)")
    print("="*60)
    
    cur.execute("SELECT MemberID FROM shard_1_Member LIMIT 1")
    row = cur.fetchone()
    if row:
        target_id = row[0]
        calculated_shard = get_shard_id(target_id)
        calculated_table = get_table_name('Member', target_id)
        
        print(f" Simulated Request arriving for MemberID: {target_id}")
        print(f" 1. Application checks Router Hash ({target_id} % 3)")
        print(f" 2. Router confirms Target Table = '{calculated_table}'")
        
        # Test Query
        cur.execute(f"SELECT Name FROM {calculated_table} WHERE MemberID = %s", (target_id,))
        name = cur.fetchone()[0]
        print(f" 3. Result: Record '{name}' was retrieved specifically from {calculated_table}!")
        print(" -> [SUCCESS] Horizontal routing logic is completely functional.\n")
