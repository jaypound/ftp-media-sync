-- Add metadata_synced_at column to scheduling_metadata table
-- This column tracks when content expiration metadata was last synced from Castus servers

ALTER TABLE scheduling_metadata 
ADD COLUMN IF NOT EXISTS metadata_synced_at TIMESTAMP WITH TIME ZONE;

-- Create index for efficient queries on sync status
CREATE INDEX IF NOT EXISTS idx_scheduling_metadata_synced_at 
ON scheduling_metadata(metadata_synced_at);

-- Add comment explaining the column purpose
COMMENT ON COLUMN scheduling_metadata.metadata_synced_at IS 
'Timestamp of when content expiration metadata was last synchronized from Castus server metadata files';