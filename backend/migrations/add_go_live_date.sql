-- Add go_live_date column to scheduling_metadata table
-- This column stores the "content window open" date from Castus metadata
-- representing when content first becomes available for scheduling

ALTER TABLE scheduling_metadata 
ADD COLUMN IF NOT EXISTS go_live_date TIMESTAMP WITH TIME ZONE;

-- Create index for efficient queries on go live dates
CREATE INDEX IF NOT EXISTS idx_scheduling_metadata_go_live_date 
ON scheduling_metadata(go_live_date);

-- Add comment explaining the column purpose
COMMENT ON COLUMN scheduling_metadata.go_live_date IS 
'Go live date (content window open) from Castus metadata - when content first becomes available for scheduling';