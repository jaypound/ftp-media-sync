-- Add tables for tracking default graphics with pull dates
-- Created: 2025-11-06

-- Table to track individual graphics files
CREATE TABLE IF NOT EXISTS default_graphics (
    id SERIAL PRIMARY KEY,
    file_name VARCHAR(500) UNIQUE NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,
    file_modified TIMESTAMP WITH TIME ZONE,  -- File modification time from FTP
    creation_date TIMESTAMP WITH TIME ZONE,   -- When file was created on FTP
    scan_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,  -- When added to DB
    start_date DATE DEFAULT CURRENT_DATE,     -- When to start including in rotation
    end_date DATE,                            -- Pull date - when to stop including
    duration_seconds NUMERIC(10,1) DEFAULT 5.0,  -- How long to display this graphic
    sort_order INTEGER DEFAULT 0,             -- Manual sort order (0 = use creation date)
    status VARCHAR(20) DEFAULT 'active',      -- active, expired, disabled, pending
    metadata JSONB,                           -- Store additional info like dimensions, etc.
    notes TEXT,                               -- User notes about the graphic
    last_included TIMESTAMP WITH TIME ZONE,   -- Last time included in a video
    include_count INTEGER DEFAULT 0,          -- Times included in videos
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_file_size CHECK (file_size >= 0),
    CONSTRAINT valid_duration CHECK (duration_seconds > 0),
    CONSTRAINT valid_dates CHECK (end_date IS NULL OR end_date >= start_date),
    CONSTRAINT valid_status CHECK (status IN ('active', 'expired', 'disabled', 'pending'))
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_default_graphics_status ON default_graphics(status);
CREATE INDEX IF NOT EXISTS idx_default_graphics_dates ON default_graphics(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_default_graphics_file_name ON default_graphics(file_name);

-- Table to track generated default videos
CREATE TABLE IF NOT EXISTS generated_default_videos (
    id SERIAL PRIMARY KEY,
    file_name VARCHAR(500) NOT NULL,
    file_path TEXT NOT NULL,
    export_server VARCHAR(100),               -- Which server it was exported to
    generation_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    graphics_count INTEGER,                   -- Number of graphics included
    total_duration NUMERIC(10,1),            -- Total video duration in seconds
    video_format VARCHAR(20),                -- mp4, mov, etc.
    region2_file VARCHAR(500),               -- Lower third graphic used
    music_files JSONB,                       -- Array of music files used
    graphics_included JSONB,                 -- Array of graphic IDs and their details
    generation_params JSONB,                 -- Store generation parameters (sort order, etc.)
    created_by VARCHAR(100),                 -- User who triggered generation
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for finding videos by date
CREATE INDEX IF NOT EXISTS idx_generated_videos_date ON generated_default_videos(generation_date DESC);

-- Table to track graphic usage in generated videos (many-to-many)
CREATE TABLE IF NOT EXISTS default_graphics_usage (
    graphic_id INTEGER NOT NULL REFERENCES default_graphics(id) ON DELETE CASCADE,
    video_id INTEGER NOT NULL REFERENCES generated_default_videos(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,                -- Order in the video
    duration_seconds NUMERIC(10,1),           -- Duration in this specific video
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (graphic_id, video_id)
);

-- Function to automatically update status based on dates
CREATE OR REPLACE FUNCTION update_graphic_status() RETURNS TRIGGER AS $$
BEGIN
    -- Update status to expired if end_date has passed
    IF NEW.end_date IS NOT NULL AND NEW.end_date < CURRENT_DATE AND NEW.status = 'active' THEN
        NEW.status := 'expired';
    END IF;
    
    -- Update status to pending if start_date is in the future
    IF NEW.start_date > CURRENT_DATE AND NEW.status = 'active' THEN
        NEW.status := 'pending';
    END IF;
    
    -- Update status to active if dates are valid and status is pending
    IF NEW.start_date <= CURRENT_DATE AND 
       (NEW.end_date IS NULL OR NEW.end_date >= CURRENT_DATE) AND 
       NEW.status = 'pending' THEN
        NEW.status := 'active';
    END IF;
    
    -- Update the updated_at timestamp
    NEW.updated_at := CURRENT_TIMESTAMP;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update status
CREATE TRIGGER update_default_graphic_status
    BEFORE INSERT OR UPDATE ON default_graphics
    FOR EACH ROW
    EXECUTE FUNCTION update_graphic_status();

-- Add comments to document the tables
COMMENT ON TABLE default_graphics IS 'Tracks individual graphics files for default rotation videos';
COMMENT ON TABLE generated_default_videos IS 'History of generated default rotation videos';
COMMENT ON TABLE default_graphics_usage IS 'Tracks which graphics were used in which videos';

-- Sample data for testing (commented out)
-- INSERT INTO default_graphics (file_name, file_path, start_date, end_date) VALUES
-- ('City_Event_2024.jpg', '/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION/City_Event_2024.jpg', '2024-11-01', '2024-11-30'),
-- ('Holiday_Special.png', '/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION/Holiday_Special.png', '2024-12-01', '2024-12-31'),
-- ('Year_Round_Info.jpg', '/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION/Year_Round_Info.jpg', '2024-01-01', NULL);