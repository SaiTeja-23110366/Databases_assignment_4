NUM_SHARDS = 3
def get_shard_id(member_id):
    """Returns the shard index for a given MemberID."""
    if member_id is None:
        raise ValueError("Cannot determine shard without a MemberID")
    return int(member_id) % NUM_SHARDS
def get_table_name(base_table, member_id):
    """Returns the sharded table name, e.g., shard_0_Member."""
    shard_id = get_shard_id(member_id)
    return f"shard_{shard_id}_{base_table}"
def get_all_shards(base_table):
    """Returns a list of all sharded table names for scatter-gather operations."""
    return [f"shard_{i}_{base_table}" for i in range(NUM_SHARDS)]