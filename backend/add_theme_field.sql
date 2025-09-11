-- Add theme field to assets table
-- This field will store the overall theme/message of the content for PSA grouping
ALTER TABLE assets ADD COLUMN IF NOT EXISTS theme VARCHAR(255);

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_assets_theme ON assets(theme);

-- Add comment for documentation
COMMENT ON COLUMN assets.theme IS 'Overall theme or message of the content (e.g. public safety, community health, education) - helps identify similar PSAs to avoid back-to-back scheduling';