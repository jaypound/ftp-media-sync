-- Increase precision for meeting duration_hours to avoid rounding to 6-minute increments
-- This changes from NUMERIC(3,1) (0.1 hour = 6 minutes) to NUMERIC(5,3) (0.001 hour = 3.6 seconds)
-- This migration is safe because we're only increasing precision, not reducing it

-- Step 1: Remove the old constraint that limits duration to 8 hours
ALTER TABLE meetings DROP CONSTRAINT IF EXISTS valid_duration;

-- Step 2: Alter the column to have more precision
-- This preserves existing data - e.g., 2.5 becomes 2.500
ALTER TABLE meetings 
ALTER COLUMN duration_hours TYPE NUMERIC(5,3);

-- Step 3: Add back the constraint with updated precision
-- Now allows up to 99.999 hours (which is more than enough for any meeting)
ALTER TABLE meetings 
ADD CONSTRAINT valid_duration CHECK (duration_hours > 0 AND duration_hours <= 24);

-- Step 4: Add a comment explaining the column
COMMENT ON COLUMN meetings.duration_hours IS 'Meeting duration in hours with precision to 3.6 seconds (0.001 hours)';

-- Verification query (optional - run manually to check):
-- SELECT id, meeting_name, duration_hours, 
--        duration_hours * 60 as duration_minutes,
--        duration_hours * 3600 as duration_seconds
-- FROM meetings 
-- ORDER BY id DESC 
-- LIMIT 10;