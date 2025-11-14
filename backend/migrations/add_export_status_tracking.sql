-- Add export status tracking to generated_default_videos table
-- This tracks whether exports to source and target servers succeeded

-- Add columns to track export success/failure
ALTER TABLE generated_default_videos 
ADD COLUMN IF NOT EXISTS source_export_status VARCHAR(20) DEFAULT 'pending' CHECK (source_export_status IN ('pending', 'success', 'failed', 'skipped')),
ADD COLUMN IF NOT EXISTS source_export_error TEXT,
ADD COLUMN IF NOT EXISTS source_export_timestamp TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS target_export_status VARCHAR(20) DEFAULT 'pending' CHECK (target_export_status IN ('pending', 'success', 'failed', 'skipped')),
ADD COLUMN IF NOT EXISTS target_export_error TEXT,
ADD COLUMN IF NOT EXISTS target_export_timestamp TIMESTAMP WITH TIME ZONE;

-- Add indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_generated_videos_source_export 
ON generated_default_videos(source_export_status, generation_date);

CREATE INDEX IF NOT EXISTS idx_generated_videos_target_export 
ON generated_default_videos(target_export_status, generation_date);

-- Update existing records based on export_server value
UPDATE generated_default_videos 
SET source_export_status = CASE 
    WHEN export_server IN ('source', 'both') THEN 'success'
    ELSE 'skipped'
END,
target_export_status = CASE 
    WHEN export_server IN ('target', 'both') THEN 'success'
    ELSE 'skipped'
END
WHERE source_export_status = 'pending' 
AND generation_status = 'completed';