# Scalability & Trade-offs Analysis (Assignment 4)

## Horizontal vs. Vertical Scaling
Sharding provides **Horizontal Scaling** (scaling out) by distributing the data and query load across multiple independent nodes or tables instead of relying on a single large database server (**Vertical Scaling** / scaling up). Vertical scaling is inherently limited by hardware constraints (maximum RAM, CPU, or storage a single machine can handle). With this `MemberID`-based sharding model, as the student and staff population grows, the university can seamlessly add `shard_3`, `shard_4`, etc., enabling essentially limitless linear scaling of storage and concurrent query handling.

## Consistency
In a sharded architecture, achieving **Consistency** becomes more complex. 
- **Strong Consistency within Shards:** Our implementation maintains strong consistency for any single-member transaction, because operations (like deducting balance from a `MonthlyMessPayment` or adding a `MealLog` entry) are entirely contained within a single shard locally. 
- **Eventual/Reduced Consistency across Shards:** Global operations, such as an Admin requesting total `MealLogs` from the whole system, require "Scatter-Gather" queries. Since these queries hit different shards asynchronously in the background, a scattered query might read `shard_0` at one microsecond and `shard_1` at another, potentially missing a transaction that occurred in between. Therefore, multi-shard operations are generally eventually consistent.

## Availability
Sharding isolates failure domains, directly improving overall system **Availability**.
If a traditional database goes down, the entire system is disabled. However, if `shard_1_Member` goes offline (for example, simulating a specific Docker Node failure), only the 33% of students and staff residing on that shard are impacted. The users mapped to `shard_0` and `shard_2` will be perfectly unaffected, allowing the majority of the application to run smoothly during a partial outage.

## Partition Tolerance
Under the CAP theorem, **Partition Tolerance** guarantees that the system continues to operate despite network partitions or communication breaks between nodes.
Since our designated Shard Key (`MemberID`) allows self-contained logic without needing shards to communicate with each other, our design is natively partition tolerant. If a simulated shard failure occurs, the routing logic in `sharding_router.py` can capture the timeout/error for that specific node block and gracefully display a "Node Offline" warning for that subset of data, while letting all other traffic through unhindered.
