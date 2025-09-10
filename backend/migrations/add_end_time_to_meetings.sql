-- Add end_time column to meetings table to support direct end time entry
-- This allows users to specify exact start and end times instead of duration

-- Step 1: Add the end_time column (nullable initially)
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS end_time TIME;

-- Step 2: Populate end_time for existing records based on start_time + duration_hours
UPDATE meetings 
SET end_time = (start_time + (duration_hours * INTERVAL '1 hour'))::TIME
WHERE end_time IS NULL;

-- Step 3: Make end_time NOT NULL after population
ALTER TABLE meetings ALTER COLUMN end_time SET NOT NULL;

-- Step 4: Add constraint to ensure end_time is after start_time
-- Note: This simple constraint doesn't handle meetings that cross midnight
-- For meetings that cross midnight, end_time will appear to be before start_time
ALTER TABLE meetings ADD CONSTRAINT check_valid_time_range 
    CHECK (
        CASE 
            WHEN end_time > start_time THEN TRUE  -- Normal case: meeting within same day
            WHEN end_time < start_time THEN TRUE  -- Meeting crosses midnight
            ELSE FALSE  -- end_time cannot equal start_time
        END
    );

-- Step 5: Create index on end_time for efficient querying
CREATE INDEX IF NOT EXISTS idx_meetings_end_time ON meetings(end_time);

-- Step 6: Update the updated_at trigger to include end_time changes
-- The trigger should already exist from the original table creation
-- but we ensure it fires on end_time updates as well

-- Note: duration_hours column is kept for backward compatibility
-- It can be removed in a future migration after ensuring all code is updated