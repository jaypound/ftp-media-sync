-- Migration to update content_type enum with all required values
-- This script updates the enum to include all content types used by ATL26

-- First, rename the old enum type
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
    'other'  -- Other
);

-- Update the column to use the new enum
-- First, temporarily change column to text
ALTER TABLE assets ALTER COLUMN content_type TYPE text USING content_type::text;

-- Map old values to new values where needed
UPDATE assets SET content_type = LOWER(content_type) WHERE content_type IS NOT NULL;
UPDATE assets SET content_type = 'other' WHERE content_type NOT IN (
    'an', 'bmp', 'imow', 'im', 'ia', 'lm', 'mtg', 'maf', 
    'pkg', 'pmo', 'psa', 'szl', 'spp', 'other'
);

-- Change column back to enum
ALTER TABLE assets ALTER COLUMN content_type TYPE content_type USING content_type::content_type;

-- Drop the old enum
DROP TYPE content_type_old;

-- Add a comment to document the mapping
COMMENT ON TYPE content_type IS 'Content types for ATL26: an=Atlanta Now, bmp=Bumps, imow=In My Own Words, im=Inclusion Months, ia=Inside Atlanta, lm=Legislative Minute, mtg=Meetings, maf=Moving Atlanta Forward, pkg=Packages, pmo=Promos, psa=PSAs, szl=Sizzles, spp=Special Projects, other=Other';