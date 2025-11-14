-- Add tables for automatic video generation during meetings
-- This enables automatic creation of fill graphics videos 5 minutes after meetings start

-- Configuration table for auto generation settings
CREATE TABLE IF NOT EXISTS auto_generation_config (
    id SERIAL PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE,
    start_hour INTEGER DEFAULT 8 CHECK (start_hour >= 0 AND start_hour <= 23),
    end_hour INTEGER DEFAULT 18 CHECK (end_hour >= 0 AND end_hour <= 23),
    weekdays_only BOOLEAN DEFAULT TRUE,
    delay_minutes INTEGER DEFAULT 5 CHECK (delay_minutes > 0),
    min_duration_seconds INTEGER DEFAULT 360 CHECK (min_duration_seconds > 0),
    seconds_per_graphic INTEGER DEFAULT 10 CHECK (seconds_per_graphic > 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by VARCHAR(100)
);

-- Insert default configuration
INSERT INTO auto_generation_config (
    enabled, start_hour, end_hour, weekdays_only, 
    delay_minutes, min_duration_seconds, seconds_per_graphic
) VALUES (
    TRUE, 8, 18, TRUE, 2, 360, 10
) ON CONFLICT DO NOTHING;

-- Track generation attempts and status
CREATE TABLE IF NOT EXISTS meeting_video_generations (
    id SERIAL PRIMARY KEY,
    meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
    video_id INTEGER REFERENCES generated_default_videos(id) ON DELETE SET NULL,
    generation_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    generation_date DATE,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'generating', 'completed', 'failed')),
    error_message TEXT,
    generated_by_host VARCHAR(255),
    sort_order VARCHAR(20),
    duration_seconds INTEGER,
    graphics_count INTEGER
);

-- Add status field to track current state of video generation
ALTER TABLE generated_default_videos 
ADD COLUMN IF NOT EXISTS generation_status VARCHAR(20) DEFAULT 'completed',
ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL;

-- Create index for efficient queries
CREATE INDEX IF NOT EXISTS idx_meeting_video_generations_status 
ON meeting_video_generations(status, generation_timestamp);

CREATE INDEX IF NOT EXISTS idx_meeting_video_generations_meeting 
ON meeting_video_generations(meeting_id, generation_date);

CREATE INDEX IF NOT EXISTS idx_generated_videos_auto 
ON generated_default_videos(auto_generated, generation_date);

-- Create unique index to prevent multiple generations per meeting per day
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_meeting_generation_per_day 
ON meeting_video_generations(meeting_id, generation_date);

-- Function to set generation_date from generation_timestamp
CREATE OR REPLACE FUNCTION set_generation_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.generation_date = CAST(NEW.generation_timestamp AS DATE);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to update timestamp on config changes
CREATE OR REPLACE FUNCTION update_auto_generation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically set generation_date
DROP TRIGGER IF EXISTS set_generation_date_trigger ON meeting_video_generations;
CREATE TRIGGER set_generation_date_trigger
BEFORE INSERT OR UPDATE ON meeting_video_generations
FOR EACH ROW
EXECUTE FUNCTION set_generation_date();

-- Trigger to automatically update timestamp
DROP TRIGGER IF EXISTS update_auto_generation_config_timestamp ON auto_generation_config;
CREATE TRIGGER update_auto_generation_config_timestamp
BEFORE UPDATE ON auto_generation_config
FOR EACH ROW
EXECUTE FUNCTION update_auto_generation_timestamp();

-- Grant permissions
GRANT ALL ON auto_generation_config TO PUBLIC;
GRANT ALL ON meeting_video_generations TO PUBLIC;
GRANT ALL ON auto_generation_config_id_seq TO PUBLIC;
GRANT ALL ON meeting_video_generations_id_seq TO PUBLIC;