-- Migration: Add meeting promos management tables
-- Created: 2026-01-07
-- Purpose: Support automatic scheduling of promos before and after meetings

-- Create table for managing pre/post meeting promos
CREATE TABLE IF NOT EXISTS meeting_promos (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    promo_type VARCHAR(10) NOT NULL CHECK (promo_type IN ('pre', 'post')),
    duration_seconds INTEGER NOT NULL,
    go_live_date DATE,
    expiration_date DATE,
    is_active BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    notes TEXT
);

-- Create index for efficient queries
CREATE INDEX idx_meeting_promos_active ON meeting_promos(is_active, promo_type);
CREATE INDEX idx_meeting_promos_dates ON meeting_promos(go_live_date, expiration_date);

-- Create table for global promo settings
CREATE TABLE IF NOT EXISTS meeting_promo_settings (
    id SERIAL PRIMARY KEY,
    pre_meeting_enabled BOOLEAN DEFAULT false,
    post_meeting_enabled BOOLEAN DEFAULT false,
    pre_meeting_duration_limit INTEGER DEFAULT 300, -- 5 minutes max
    post_meeting_duration_limit INTEGER DEFAULT 300, -- 5 minutes max
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100)
);

-- Insert default settings
INSERT INTO meeting_promo_settings (pre_meeting_enabled, post_meeting_enabled)
VALUES (false, false)
ON CONFLICT (id) DO NOTHING;

-- Insert the initial promo
INSERT INTO meeting_promos (file_path, file_name, promo_type, duration_seconds, go_live_date, is_active)
VALUES (
    '/mnt/main/Promos/260107_PMO_ATL DIRECT.mp4',
    '260107_PMO_ATL DIRECT.mp4',
    'pre',
    30, -- Assuming 30 seconds, update with actual duration
    '2026-01-07',
    true
);

-- Add updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_meeting_promos_updated_at BEFORE UPDATE ON meeting_promos
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_meeting_promo_settings_updated_at BEFORE UPDATE ON meeting_promo_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();