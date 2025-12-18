-- Holiday Greeting Fair Rotation System
-- Migration to add tracking table for holiday greeting scheduling
-- Created: December 2025
-- 
-- IMPORTANT: This migration is SAFE to run as it creates a NEW table
-- that does not interact with existing scheduling tables
--
-- To apply this migration:
-- psql -U ftp_sync_user -d ftp_media_sync -f add_holiday_greeting_rotation.sql

BEGIN;

-- Create the holiday greeting rotation tracking table
CREATE TABLE IF NOT EXISTS holiday_greeting_rotation (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    content_title VARCHAR(255),
    scheduled_count INTEGER DEFAULT 0,
    last_scheduled TIMESTAMP,
    total_duration_seconds NUMERIC(10,3) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_holiday_rotation_count 
    ON holiday_greeting_rotation(scheduled_count, last_scheduled);

CREATE INDEX IF NOT EXISTS idx_holiday_rotation_asset 
    ON holiday_greeting_rotation(asset_id);

CREATE INDEX IF NOT EXISTS idx_holiday_rotation_last_scheduled 
    ON holiday_greeting_rotation(last_scheduled);

-- Create update trigger for updated_at
CREATE OR REPLACE FUNCTION update_holiday_greeting_rotation_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER holiday_greeting_rotation_updated_at
    BEFORE UPDATE ON holiday_greeting_rotation
    FOR EACH ROW
    EXECUTE FUNCTION update_holiday_greeting_rotation_updated_at();

-- Populate initial data from existing assets (but with 0 scheduled_count)
-- This identifies all holiday greeting content currently in the system
INSERT INTO holiday_greeting_rotation (asset_id, file_name, content_title)
SELECT DISTINCT
    a.id,
    COALESCE(i.file_name, ''),
    a.content_title
FROM assets a
LEFT JOIN instances i ON i.asset_id = a.id AND i.is_primary = true
WHERE 
    (
        LOWER(COALESCE(i.file_name, '')) LIKE '%holiday%greeting%'
        OR LOWER(COALESCE(a.content_title, '')) LIKE '%holiday%greeting%'
    )
ON CONFLICT (asset_id) DO NOTHING;

-- Add a comment to the table
COMMENT ON TABLE holiday_greeting_rotation IS 
'Tracks holiday greeting content scheduling to ensure fair rotation. Created December 2025.';

-- Verify what was created/populated
DO $$
DECLARE
    greeting_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO greeting_count FROM holiday_greeting_rotation;
    RAISE NOTICE 'Holiday greeting rotation table created successfully';
    RAISE NOTICE 'Found % holiday greeting assets', greeting_count;
END $$;

COMMIT;

-- Query to verify the holiday greetings found (run separately if needed)
-- SELECT 
--     asset_id,
--     file_name,
--     content_title,
--     scheduled_count,
--     last_scheduled
-- FROM holiday_greeting_rotation
-- ORDER BY file_name;