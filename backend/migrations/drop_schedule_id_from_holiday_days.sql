-- Drop schedule_id column from holiday_greetings_days table
-- This makes daily assignments purely date-based, not tied to specific schedules

-- Drop the foreign key constraint first
ALTER TABLE holiday_greetings_days 
DROP CONSTRAINT IF EXISTS holiday_greetings_days_schedule_id_fkey;

-- Drop the column
ALTER TABLE holiday_greetings_days 
DROP COLUMN schedule_id;

-- Update the table comment
COMMENT ON TABLE holiday_greetings_days IS 'Pre-assigns holiday greetings to specific dates for fair rotation. Not tied to any specific schedule.';

-- The unique constraint on (start_date, asset_id) already exists from previous migration
-- This ensures we can't assign the same greeting multiple times on the same date