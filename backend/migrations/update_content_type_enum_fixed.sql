-- Migration to update content_type enum with all required values
-- This version handles views that depend on the enum

-- First, drop the dependent view
DROP VIEW IF EXISTS v_asset_details CASCADE;

-- Store any other views that might depend on assets table
DROP VIEW IF EXISTS v_asset_tags CASCADE;
DROP VIEW IF EXISTS v_schedule_details CASCADE;

-- Now rename the old enum type
ALTER TYPE content_type RENAME TO content_type_old;

-- Create new enum with all values (lowercase to match PostgreSQL convention)
CREATE TYPE content_type AS ENUM (
    'an',    -- Atlanta Now
    'bmp',   -- Bumps
    'imow',  -- In My Own Words
    'im',    -- Inclusion Months
    'ia',    -- Inside Atlanta
    'lm',    -- Legislative Minute
    'mtg',   -- Meetings
    'maf',   -- Moving Atlanta Forward
    'pkg',   -- Packages
    'pmo',   -- Promos
    'psa',   -- PSAs
    'szl',   -- Sizzles
    'spp',   -- Special Projects
    'meeting', -- Keep for backward compatibility
    'announcement', -- Keep for backward compatibility
    'documentary', -- Keep for backward compatibility
    'other'  -- Other
);

-- Update the column to use the new enum
-- First, temporarily change column to text
ALTER TABLE assets ALTER COLUMN content_type TYPE text USING content_type::text;

-- Map old values to new values where needed (already lowercase, so just ensure valid values)
UPDATE assets SET content_type = 'other' WHERE content_type IS NOT NULL AND content_type NOT IN (
    'an', 'bmp', 'imow', 'im', 'ia', 'lm', 'mtg', 'maf', 
    'pkg', 'pmo', 'psa', 'szl', 'spp', 'meeting', 'announcement', 'documentary', 'other'
);

-- Change column back to enum
ALTER TABLE assets ALTER COLUMN content_type TYPE content_type USING content_type::content_type;

-- Drop the old enum
DROP TYPE content_type_old;

-- Recreate the views
CREATE VIEW v_asset_details AS
SELECT 
    a.*,
    i.file_name,
    i.file_path,
    i.file_size,
    i.storage_location,
    i.encoded_date,
    sm.available_for_scheduling,
    sm.content_expiry_date,
    sm.last_scheduled_date,
    sm.total_airings,
    sm.priority_score
FROM assets a
LEFT JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id;

CREATE VIEW v_schedule_details AS
SELECT 
    s.*,
    COUNT(si.id) as item_count,
    SUM(si.scheduled_duration_seconds) as total_scheduled_duration
FROM schedules s
LEFT JOIN scheduled_items si ON s.id = si.schedule_id
GROUP BY s.id;

CREATE VIEW v_asset_tags AS
SELECT 
    a.id as asset_id,
    a.guid,
    a.content_title,
    tt.type_name,
    t.tag_name,
    t.tag_value
FROM assets a
JOIN asset_tags at ON a.id = at.asset_id
JOIN tags t ON at.tag_id = t.id
JOIN tag_types tt ON t.tag_type_id = tt.id;

-- Add a comment to document the mapping
COMMENT ON TYPE content_type IS 'Content types for ATL26: an=Atlanta Now, bmp=Bumps, imow=In My Own Words, im=Inclusion Months, ia=Inside Atlanta, lm=Legislative Minute, mtg=Meetings, maf=Moving Atlanta Forward, pkg=Packages, pmo=Promos, psa=PSAs, szl=Sizzles, spp=Special Projects, other=Other';