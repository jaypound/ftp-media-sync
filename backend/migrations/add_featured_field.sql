-- Migration to add featured field for bumps that need heavy rotation
-- Run this migration with: psql -U your_username -d your_database -f add_featured_field.sql

-- Add featured boolean column to scheduling_metadata table
ALTER TABLE scheduling_metadata 
ADD COLUMN featured BOOLEAN DEFAULT FALSE;

-- Add index for efficient filtering of featured content
CREATE INDEX idx_scheduling_metadata_featured ON scheduling_metadata(featured) WHERE featured = TRUE;

-- Add comment to document the field
COMMENT ON COLUMN scheduling_metadata.featured IS 'Flag to indicate content that should be featured heavily in rotation with shorter replay delays';