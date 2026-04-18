# Assignment 4: Database Sharding Walkthrough

I have fully implemented the Hash-Based Sharding strategy you selected (using `MemberID % 3`). Here is a summary of all the modifications added to your existing codebase:

## 1. Database SQL Splitting
- **Created** [db_sharding.sql](file:///C:/Users/Acer/AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState/sessions/38A4DCA861984965BFFB318B3E4817B2021298FC/transfers/2026-16/Database_project/Database_project/db_sharding.sql) which contains SQL commands you can execute directly into your MySQL server to simulate the 3 different shard partition tables (`shard_0_<tablename>`) and dynamically migrate/copy data exactly mimicking your existing records.

## 2. Dynamic Routing Logic
- **Created** [sharding_router.py](file:///C:/Users/Acer/AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState/sessions/38A4DCA861984965BFFB318B3E4817B2021298FC/transfers/2026-16/Database_project/Database_project/sharding_router.py) which contains the core Hash calculation ensuring all tables are routed effectively using the central `MemberID`.

## 3. Core Refactoring
We patched the application logic globally to replace singular table queries into dynamic shard calls:
- **Modified** [auth.py](file:///C:/Users/Acer/AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState/sessions/38A4DCA861984965BFFB318B3E4817B2021298FC/transfers/2026-16/Database_project/Database_project/auth.py): Updated user login loops to point directly into that specific users shard rather than a generalized lookup.
- **Modified** [transactions.py](file:///C:/Users/Acer/AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState/sessions/38A4DCA861984965BFFB318B3E4817B2021298FC/transfers/2026-16/Database_project/Database_project/transactions.py): `atomic_mark_attendance` and `atomic_update_billing_status` have been completely decoupled, allowing database locks and transactional queries to run isolated on their respective shard.
- **Modified** [routes.py](file:///C:/Users/Acer/AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState/sessions/38A4DCA861984965BFFB318B3E4817B2021298FC/transfers/2026-16/Database_project/Database_project/routes.py): Over 20 distinct `cur.execute` commands were rewritten:
    - **Single queries:** Converted simple `SELECT * FROM Member` to exact hash destinations.
    - **Admin Queries:** Applied the **Scatter-Gather** approach using consecutive scans across `shard_X` arrays internally looping data or utilizing `UNION ALL` calls for high-performing aggregate datasets.

## 4. Assessment Deliverable Report
- **Created** [scalability_analysis.md](file:///C:/Users/Acer/AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState/sessions/38A4DCA861984965BFFB318B3E4817B2021298FC/transfers/2026-16/Database_project/Database_project/scalability_analysis.md) mapping exactly to your Assignment's SubTask 4. It comprehensively justifies Horizontal Scaling limits, Eventual vs. Strong Consistency, Availability improvements under partial node outages, and CAP Theorem Partition boundaries. You can easily copy and paste everything from here for your `group_name_report.pdf`.

> [!TIP]
> **To Finalize Deployment:** 
> 1. Run the `db_sharding.sql` file in your MySQL environment manually via command line (`source db_sharding.sql`) or UI tool.
> 2. Run your application tests. To show query routing works in the video, highlight the print outputs/responses when students interact from independent environments.
