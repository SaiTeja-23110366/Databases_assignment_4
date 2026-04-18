# Assignment 4: Sharding of the Developed Application
**Course:** CS 432 – Databases  
**Group Name:** [Your Group Name Here]

---

### **Submission Links**
*   **GitHub Repository Link:** [Insert your GitHub URL here]
*   **Video Demonstration Link:** [Insert your Video URL here]

---

## **1. Shard Key Selection & Justification**

For our application, we have chosen **`MemberID`** as our primary Shard Key. This decision was based on the following three critical properties:
1.  **High Cardinality:** There will be a large and continuously growing number of unique `MemberID` entries (students, faculty, etc.). This ensures our data will be distributed evenly across the partitioned shards, avoiding "hot spots."
2.  **Query-Aligned:** A vast majority of our application's critical APIs (e.g., retrieving balances, marking attendance, executing transactions) are heavily dependent on `MemberID` in their `WHERE` clauses. By keeping Member records localized to their respective shards, we avoid broadcasting the majority of queries across all nodes.
3.  **Stability:** Once a `MemberID` is created for a student or staff member, it represents a permanent immutable identifier during their institution tenure. It never changes, ensuring we won't need to perform expensive redistributions of rows.

## **2. Partitioning Strategy**

We employed a **Hash-Based Partitioning Strategy**. 
*   **Formula:** `Shard_ID = Hash(MemberID) % 3` 
*   **Why this strategy?** A hash-based strategy was selected over a Range-Based strategy because Member IDs are sequentially or randomly generated and can lead to uneven load over time (e.g., all new active students landing on the highest range shard). Hash partitioning mathematically guarantees a statistically uniform distribution of data regardless of the sequence of incoming new registrations.
*   **Expected Data Distribution:** With 3 simulated shards, we expect exactly ~33.3% of the data to reside on each partition with a negligible risk of data skew.

## **3. Implementation of Data Partitioning & Migration**

To achieve database partitioning, we utilized the **Multiple Databases/Tables on the Same Server** approach.

*   **Shard Isolation Approach:** The assignment provided two approaches to simulate shards: Docker instances or multiple databases on the same server. While the assignment noted Docker instances could be provided after April 11th, we opted to build our sharding infrastructure using the **Multiple Databases/Tables on the Same Server** approach. This ensured immediate local testability, lower operational overhead, and solid logic isolation without relying on external container network configurations. We provisioned three logical partition spaces: `shard_0_`, `shard_1_`, and `shard_2_` directly within the SQL environment, representing independent mock-nodes.
*   **Migration Details:** Data was segregated dynamically using intermediate SQL scripts (`db_sharding.sql`). These scripts used `INSERT INTO ... SELECT` statements coupled with the `MOD(MemberID, 3)` calculation to correctly route pre-existing system rows (such as `Member`, `Transactions`, `Attendance`, etc.) into each distinct shard bucket. 
*   **Migration Verification (No Data Loss/Duplication):** To strictly verify that no records were lost or duplicated after migration, we performed analytical validation on the database. We cross-checked the baseline `COUNT(*)` of the original unpartitioned tables (like `Member`) against the sum of the rows (`COUNT(*)`) across `shard_0_Member` + `shard_1_Member` + `shard_2_Member`. The original and partitioned row counts matched precisely. Furthermore, running aggregation queries (e.g., `GROUP BY MemberID HAVING COUNT(*) > 1` on a `UNION ALL` of the shards) returned 0 rows, confirming absolutely no ID duplicates were created across shard boundaries.

## **4. Query Routing Implementation**

Application logic (`sharding_router.py`, `routes.py`, and `transactions.py`) was entirely refactored to perform dynamic query routing.
*   **Lookup & Insert Queries:** Application endpoints extract the `MemberID` from the incoming request (JWT Token or JSON body). It immediately calculates the correct target shard dynamically string-formatting the table names (e.g., `execute("SELECT * FROM {shard}_Member")`) reducing overhead.
*   **Range/Aggregate Queries:** For administrative queries requiring data across all members, our router leverages a **Scatter-Gather** approach. It iterates over the array of active shards, issues queries concurrently, and logically merges them in backend memory (or via SQL `UNION ALL`) before returning a unified payload to the client.

## **5. Scalability & Trade-offs Analysis**

### Horizontal vs. Vertical Scaling
Sharding provides **Horizontal Scaling** (scaling out) by distributing the data and query load across multiple independent nodes or tables instead of relying on a single large database server (**Vertical Scaling** / scaling up). Vertical scaling is inherently limited by hardware constraints (maximum RAM, CPU, or storage a single machine can handle). With this `MemberID`-based sharding model, as the student and staff population grows, the university can seamlessly add `shard_3`, `shard_4`, etc., enabling essentially limitless linear scaling of storage and concurrent query handling.

### Consistency
In a sharded architecture, achieving Consistency becomes more complex.
*   **Strong Consistency within Shards:** Our implementation maintains strong consistency for any single-member transaction, because operations (like deducting balance or adding an attendance entry) are entirely contained within a single shard locally.
*   **Eventual/Reduced Consistency across Shards:** Global operations, such as an Admin requesting total logs from the whole system, require "Scatter-Gather" queries. Since these queries hit different shards asynchronously, a scattered query might read `shard_0` at one microsecond and `shard_1` at another, potentially missing a transaction that occurred in between. Therefore, multi-shard operations are generally eventually consistent.

### Availability
Sharding isolates failure domains, directly improving overall system Availability.
If a traditional database goes down, the entire system is disabled. However, if `shard_1` goes offline, only the 33% of students and staff residing on that shard are impacted. The users mapped to `shard_0` and `shard_2` will be unaffected, allowing the majority of the application to run smoothly during a partial outage.

### Partition Tolerance
Under the CAP theorem, Partition Tolerance guarantees that the system continues to operate despite communication breaks between nodes. Because our `MemberID` Shard Key isolates user logic specifically, the shards do not need synchronous communication to fulfill standard requests. If a simulated node failure occurs, the router gracefully catches the time-out for that subset of data without crashing the entire infrastructure.

## **6. Observations and Limitations**
*   **Limitations of Scatter-Gather:** While simple queries execute much faster, global `ORDER BY` or complex `JOIN` operations across multiple shards are inherently difficult and require higher CPU RAM usage strictly on the backend web server for manual merging.
*   **Re-Sharding Complexity:** Currently, if a 4th shard was introduced, the modulus calculation `MemberID % 4` would drastically change the expected location for pre-existing users, requiring a heavily orchestrated background data migration. Consistent Hashing could be explored in future builds to mitigate this limitation.
