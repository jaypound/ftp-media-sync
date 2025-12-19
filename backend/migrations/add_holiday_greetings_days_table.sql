-- Create HOLIDAY_GREETINGS_DAYS table for controlled daily holiday greeting assignments
-- This table assigns specific holiday greetings to specific days of the schedule
-- ensuring variety and preventing the same greetings from repeating

CREATE TABLE IF NOT EXISTS holiday_greetings_days (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER REFERENCES schedules(id) ON DELETE CASCADE,
    day_number INTEGER NOT NULL,  -- Day 1, 2, 3, etc. of the schedule
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,      -- Start of the day (inclusive)
    end_date DATE NOT NULL,        -- End of the day (exclusive, typically start_date + 1)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique assignment per schedule/day/asset combination
    CONSTRAINT unique_schedule_day_asset UNIQUE (schedule_id, day_number, asset_id),
    
    -- Ensure day_number is positive
    CONSTRAINT positive_day_number CHECK (day_number > 0),
    
    -- Ensure end_date is after start_date
    CONSTRAINT valid_date_range CHECK (end_date > start_date)
);

-- Index for quick lookups by schedule and date
CREATE INDEX idx_holiday_greetings_days_schedule_dates 
    ON holiday_greetings_days(schedule_id, start_date, end_date);

-- Index for asset lookups
CREATE INDEX idx_holiday_greetings_days_asset 
    ON holiday_greetings_days(asset_id);

-- Comment on the table
COMMENT ON TABLE holiday_greetings_days IS 'Controls which holiday greetings are available on specific days of a schedule';
COMMENT ON COLUMN holiday_greetings_days.day_number IS 'Sequential day number within the schedule (1, 2, 3, etc.)';
COMMENT ON COLUMN holiday_greetings_days.start_date IS 'First date this greeting is available (inclusive)';
COMMENT ON COLUMN holiday_greetings_days.end_date IS 'Last date this greeting is available (exclusive)';

-- Sample query to check assignments for a specific date
-- SELECT asset_id FROM holiday_greetings_days 
-- WHERE schedule_id = ? 
-- AND '2025-12-25' >= start_date 
-- AND '2025-12-25' < end_date;