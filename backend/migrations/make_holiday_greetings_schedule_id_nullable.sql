-- Make schedule_id nullable in holiday_greetings_days table
-- This allows pre-populating assignments by date before schedules exist

-- Drop the foreign key constraint
ALTER TABLE holiday_greetings_days 
DROP CONSTRAINT holiday_greetings_days_schedule_id_fkey;

-- Make schedule_id nullable
ALTER TABLE holiday_greetings_days 
ALTER COLUMN schedule_id DROP NOT NULL;

-- Add back the foreign key constraint but allow NULL
ALTER TABLE holiday_greetings_days 
ADD CONSTRAINT holiday_greetings_days_schedule_id_fkey 
FOREIGN KEY (schedule_id) 
REFERENCES schedules(id) 
ON DELETE CASCADE;

-- Drop the unique constraint that includes schedule_id
ALTER TABLE holiday_greetings_days 
DROP CONSTRAINT unique_schedule_day_asset;

-- Add a new unique constraint that works with NULL schedule_id
-- This ensures we don't have duplicate assignments for the same date/asset
ALTER TABLE holiday_greetings_days 
ADD CONSTRAINT unique_date_asset UNIQUE (start_date, asset_id);

-- Add index for date-based lookups
CREATE INDEX IF NOT EXISTS idx_holiday_greetings_days_dates 
ON holiday_greetings_days(start_date, end_date);

-- Update table comment
COMMENT ON TABLE holiday_greetings_days IS 'Controls which holiday greetings are available on specific days. Can be pre-populated by date before schedules exist.';
COMMENT ON COLUMN holiday_greetings_days.schedule_id IS 'Optional reference to a specific schedule. NULL for date-based assignments.';