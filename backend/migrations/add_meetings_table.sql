-- Add meetings table for Atlanta City Council meetings schedule

CREATE TABLE IF NOT EXISTS meetings (
    id SERIAL PRIMARY KEY,
    meeting_name VARCHAR(500) NOT NULL,
    meeting_date DATE NOT NULL,
    start_time TIME NOT NULL,
    duration_hours NUMERIC(3,1) NOT NULL DEFAULT 2.0,
    atl26_broadcast BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Add constraint to ensure reasonable meeting duration
    CONSTRAINT valid_duration CHECK (duration_hours > 0 AND duration_hours <= 8)
);

-- Create index on date for efficient querying
CREATE INDEX idx_meetings_date ON meetings(meeting_date);

-- Create index on broadcast flag for filtering
CREATE INDEX idx_meetings_broadcast ON meetings(atl26_broadcast);

-- Add a unique constraint to prevent duplicate meetings at the same date/time
CREATE UNIQUE INDEX idx_meetings_unique ON meetings(meeting_date, start_time, meeting_name);