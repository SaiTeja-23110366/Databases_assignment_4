import MySQLdb

NUM_SHARDS = 3
DB_HOST = '10.0.116.184' # [cite: 4]
DB_USER = 'Interview_rejected' # [cite: 38]
DB_PASS = 'password@123' # [cite: 15]
DB_NAME = 'Interview_rejected' # [cite: 38]

# Shard Ports from provided documentation 
SHARD_PORTS = {0: 3307, 1: 3308, 2: 3309}

def get_shard_id(member_id):
    """Partitioning logic: Hash-based on MemberID[cite: 106]."""
    return int(member_id) % NUM_SHARDS

def get_shard_connection(shard_id):
    """Dynamic routing to the correct physical shard[cite: 109]."""
    return MySQLdb.connect(
        host=DB_HOST,
        port=SHARD_PORTS[shard_id],
        user=DB_USER,
        passwd=DB_PASS,
        db=DB_NAME
    )

def get_all_shard_connections():
    """Support for range queries across all shards."""
    return [get_shard_connection(i) for i in range(NUM_SHARDS)]