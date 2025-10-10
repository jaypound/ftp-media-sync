-- Add sync_jobs table for tracking automated sync operations
-- This table ensures only one instance runs scheduled jobs at a time

CREATE TABLE IF NOT EXISTS sync_jobs (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) UNIQUE NOT NULL,
    last_run_at TIMESTAMP WITH TIME ZONE,
    last_run_by VARCHAR(255), -- hostname or process identifier
    last_run_status VARCHAR(50), -- 'running', 'completed', 'failed'
    last_run_details TEXT, -- JSON with results/errors
    lock_acquired_at TIMESTAMP WITH TIME ZONE,
    lock_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for efficient querying
CREATE INDEX idx_sync_jobs_name ON sync_jobs(job_name);

-- Insert default job entries
INSERT INTO sync_jobs (job_name, last_run_status) VALUES 
    ('castus_expiration_sync_all', 'idle')
ON CONFLICT (job_name) DO NOTHING;

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_sync_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
CREATE TRIGGER sync_jobs_updated_at_trigger
BEFORE UPDATE ON sync_jobs
FOR EACH ROW
EXECUTE FUNCTION update_sync_jobs_updated_at();