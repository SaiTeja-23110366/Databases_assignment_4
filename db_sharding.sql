USE mess_management;
-- Create sharded tables for Member and its dependencies
-- Shard 0
CREATE TABLE shard_0_Member LIKE Member;
CREATE TABLE shard_0_Student LIKE Student;
CREATE TABLE shard_0_Staff LIKE Staff;
CREATE TABLE shard_0_StaffShiftLog LIKE StaffShiftLog;
CREATE TABLE shard_0_MealLog LIKE MealLog;
CREATE TABLE shard_0_MonthlyMessPayment LIKE MonthlyMessPayment;
CREATE TABLE shard_0_MealPayment LIKE MealPayment;
CREATE TABLE shard_0_MessRating LIKE MessRating;
-- Shard 1
CREATE TABLE shard_1_Member LIKE Member;
CREATE TABLE shard_1_Student LIKE Student;
CREATE TABLE shard_1_Staff LIKE Staff;
CREATE TABLE shard_1_StaffShiftLog LIKE StaffShiftLog;
CREATE TABLE shard_1_MealLog LIKE MealLog;
CREATE TABLE shard_1_MonthlyMessPayment LIKE MonthlyMessPayment;
CREATE TABLE shard_1_MealPayment LIKE MealPayment;
CREATE TABLE shard_1_MessRating LIKE MessRating;
-- Shard 2
CREATE TABLE shard_2_Member LIKE Member;
CREATE TABLE shard_2_Student LIKE Student;
CREATE TABLE shard_2_Staff LIKE Staff;
CREATE TABLE shard_2_StaffShiftLog LIKE StaffShiftLog;
CREATE TABLE shard_2_MealLog LIKE MealLog;
CREATE TABLE shard_2_MonthlyMessPayment LIKE MonthlyMessPayment;
CREATE TABLE shard_2_MealPayment LIKE MealPayment;
CREATE TABLE shard_2_MessRating LIKE MessRating;
-- Migrate Data: Member based
INSERT INTO shard_0_Member SELECT * FROM Member WHERE MemberID % 3 = 0;
INSERT INTO shard_1_Member SELECT * FROM Member WHERE MemberID % 3 = 1;
INSERT INTO shard_2_Member SELECT * FROM Member WHERE MemberID % 3 = 2;
-- Migrate Data: Student
INSERT INTO shard_0_Student SELECT * FROM Student WHERE MemberID % 3 = 0;
INSERT INTO shard_1_Student SELECT * FROM Student WHERE MemberID % 3 = 1;
INSERT INTO shard_2_Student SELECT * FROM Student WHERE MemberID % 3 = 2;
-- Migrate Data: Staff
INSERT INTO shard_0_Staff SELECT * FROM Staff WHERE MemberID % 3 = 0;
INSERT INTO shard_1_Staff SELECT * FROM Staff WHERE MemberID % 3 = 1;
INSERT INTO shard_2_Staff SELECT * FROM Staff WHERE MemberID % 3 = 2;
-- Migrate Data: StaffShiftLog (requires joining Staff to get MemberID)
INSERT INTO shard_0_StaffShiftLog 
SELECT sl.* FROM StaffShiftLog sl JOIN Staff s ON sl.StaffID = s.StaffID WHERE s.MemberID % 3 = 0;
INSERT INTO shard_1_StaffShiftLog 
SELECT sl.* FROM StaffShiftLog sl JOIN Staff s ON sl.StaffID = s.StaffID WHERE s.MemberID % 3 = 1;
INSERT INTO shard_2_StaffShiftLog 
SELECT sl.* FROM StaffShiftLog sl JOIN Staff s ON sl.StaffID = s.StaffID WHERE s.MemberID % 3 = 2;
-- Migrate Data: MealLog
INSERT INTO shard_0_MealLog SELECT * FROM MealLog WHERE MemberID % 3 = 0;
INSERT INTO shard_1_MealLog SELECT * FROM MealLog WHERE MemberID % 3 = 1;
INSERT INTO shard_2_MealLog SELECT * FROM MealLog WHERE MemberID % 3 = 2;
-- Migrate Data: MonthlyMessPayment
INSERT INTO shard_0_MonthlyMessPayment SELECT * FROM MonthlyMessPayment WHERE MemberID % 3 = 0;
INSERT INTO shard_1_MonthlyMessPayment SELECT * FROM MonthlyMessPayment WHERE MemberID % 3 = 1;
INSERT INTO shard_2_MonthlyMessPayment SELECT * FROM MonthlyMessPayment WHERE MemberID % 3 = 2;
-- Migrate Data: MealPayment
INSERT INTO shard_0_MealPayment SELECT * FROM MealPayment WHERE MemberID % 3 = 0;
INSERT INTO shard_1_MealPayment SELECT * FROM MealPayment WHERE MemberID % 3 = 1;
INSERT INTO shard_2_MealPayment SELECT * FROM MealPayment WHERE MemberID % 3 = 2;
-- Migrate Data: MessRating
INSERT INTO shard_0_MessRating SELECT * FROM MessRating WHERE MemberID % 3 = 0;
INSERT INTO shard_1_MessRating SELECT * FROM MessRating WHERE MemberID % 3 = 1;
INSERT INTO shard_2_MessRating SELECT * FROM MessRating WHERE MemberID % 3 = 2;