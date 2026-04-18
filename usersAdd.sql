-- Run this once to add member_id column to the Users table
-- so each login account links to a specific Member record.

USE mess_management;

-- Step 1: Add the column (nullable so existing rows don't break)
ALTER TABLE Users
    ADD COLUMN member_id INT DEFAULT NULL,
    ADD CONSTRAINT fk_users_member
        FOREIGN KEY (member_id) REFERENCES Member(MemberID)
        ON DELETE SET NULL;

-- Step 2: Link your demo users to their Member records
--   admin  -> no member record (pure admin), leave NULL
--   user1  -> MemberID 1 (Amit Shah, Student)
UPDATE Users SET member_id = 1 WHERE username = 'user1';

-- Step 3: add more user accounts for other members
--   e.g. a staff member login:
INSERT INTO Users (username, password, role, member_id) VALUES
('riya',   '123', 'User', 2),   -- Riya Patel   (Student)
('karan',  '123', 'User', 3),   -- Karan Mehta  (Student)
('verma',  '123', 'Staff', 7),   -- Mr. Verma    (Staff)
('suresh', '123', 'Staff', 8);   -- Suresh Cook  (Staff)