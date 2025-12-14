-- Migration: Add Metadata Audit Log Table
-- Purpose: Track all changes to content expiration and go-live dates
-- Date: 2024-12-12

-- Drop existing table if it exists to recreate with correct types
DROP TABLE IF EXISTS metadata_audit_log CASCADE;

-- Create the metadata audit log table with correct timestamp types
CREATE TABLE metadata_audit_log (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    instance_id INTEGER,
    field_name VARCHAR(50) NOT NULL CHECK (field_name IN ('content_expiry_date', 'go_live_date')),
    old_value TIMESTAMP WITH TIME ZONE,
    new_value TIMESTAMP WITH TIME ZONE,
    changed_by VARCHAR(255),
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    change_source VARCHAR(100),
    change_reason TEXT
);

-- Add foreign key constraint with cascade delete
-- This ensures audit logs are automatically deleted when assets are deleted
ALTER TABLE metadata_audit_log
    ADD CONSTRAINT fk_metadata_audit_asset
    FOREIGN KEY (asset_id)
    REFERENCES assets(id)
    ON DELETE CASCADE;

-- Add indexes for performance
CREATE INDEX idx_metadata_audit_asset_id ON metadata_audit_log(asset_id);
CREATE INDEX idx_metadata_audit_changed_at ON metadata_audit_log(changed_at);
CREATE INDEX idx_metadata_audit_field_name ON metadata_audit_log(field_name);

-- Composite index for common query patterns
CREATE INDEX idx_metadata_audit_asset_field_date 
    ON metadata_audit_log(asset_id, field_name, changed_at DESC);

-- Add comment to table
COMMENT ON TABLE metadata_audit_log IS 'Audit trail for metadata changes to assets';
COMMENT ON COLUMN metadata_audit_log.field_name IS 'Field that was changed: content_expiry_date or go_live_date';
COMMENT ON COLUMN metadata_audit_log.change_source IS 'Source of change: web_ui, api, bulk_operation, etc';

-- Create a view for easier querying with asset details
CREATE OR REPLACE VIEW v_metadata_audit_log AS
SELECT 
    mal.id,
    mal.asset_id,
    a.content_title,
    a.content_type,
    mal.field_name,
    mal.old_value,
    mal.new_value,
    mal.changed_by,
    mal.changed_at,
    mal.change_source,
    mal.change_reason,
    CASE 
        WHEN mal.old_value IS NULL THEN 'Added'
        WHEN mal.new_value IS NULL THEN 'Removed'
        ELSE 'Updated'
    END as change_type
FROM metadata_audit_log mal
LEFT JOIN assets a ON mal.asset_id = a.id
ORDER BY mal.changed_at DESC;

-- Drop and recreate function with correct timestamp types
DROP FUNCTION IF EXISTS log_metadata_change;

-- Create function to log metadata changes
CREATE OR REPLACE FUNCTION log_metadata_change(
    p_asset_id INTEGER,
    p_instance_id INTEGER,
    p_field_name VARCHAR(50),
    p_old_value TIMESTAMP WITH TIME ZONE,
    p_new_value TIMESTAMP WITH TIME ZONE,
    p_changed_by VARCHAR(255),
    p_change_source VARCHAR(100),
    p_change_reason TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_log_id INTEGER;
BEGIN
    -- Only log if there's an actual change
    IF p_old_value IS DISTINCT FROM p_new_value THEN
        INSERT INTO metadata_audit_log (
            asset_id, instance_id, field_name, old_value, new_value,
            changed_by, change_source, change_reason
        ) VALUES (
            p_asset_id, p_instance_id, p_field_name, p_old_value, p_new_value,
            p_changed_by, p_change_source, p_change_reason
        ) RETURNING id INTO v_log_id;
        
        RETURN v_log_id;
    END IF;
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create function to cleanup old audit logs
CREATE OR REPLACE FUNCTION cleanup_old_audit_logs(p_days_to_keep INTEGER DEFAULT 365) 
RETURNS INTEGER AS $$
DECLARE
    v_deleted_count INTEGER;
BEGIN
    DELETE FROM metadata_audit_log
    WHERE changed_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * p_days_to_keep;
    
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    
    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Grant appropriate permissions
GRANT SELECT ON metadata_audit_log TO PUBLIC;
GRANT INSERT ON metadata_audit_log TO PUBLIC;
-- No UPDATE or DELETE permissions - audit logs should be immutable

-- Add sample data for testing (commented out for production)
/*
INSERT INTO metadata_audit_log (asset_id, field_name, old_value, new_value, changed_by, change_source)
VALUES 
    ('123', 'content_expiry_date', '2024-12-31'::timestamp, '2025-01-15'::timestamp, 'admin', 'web_ui'),
    ('123', 'go_live_date', NULL, '2024-12-15'::timestamp, 'admin', 'api');
*/