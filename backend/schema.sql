-- PostgreSQL Schema for FTP Media Sync Application
-- This schema normalizes the MongoDB data while maintaining flexibility

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create custom types for categorization
CREATE TYPE duration_category AS ENUM ('spots', 'short', 'medium', 'long', 'id', 'short_form', 'long_form');
CREATE TYPE shelf_life_rating AS ENUM ('low', 'medium', 'high');
CREATE TYPE content_type AS ENUM ('psa', 'meeting', 'announcement', 'documentary', 'pkg', 'ia', 'mtg', 'other');

-- ASSETS table: Core metadata for each content asset
CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    guid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    content_type content_type,
    content_title VARCHAR(500),
    language VARCHAR(10) DEFAULT 'en',
    transcript TEXT,
    summary TEXT,
    duration_seconds NUMERIC(10,3),
    duration_category duration_category,
    engagement_score INTEGER CHECK (engagement_score >= 0 AND engagement_score <= 100),
    engagement_score_reasons TEXT,
    shelf_life_score shelf_life_rating,
    shelf_life_reasons TEXT,
    analysis_completed BOOLEAN DEFAULT FALSE,
    ai_analysis_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- MongoDB migration fields
    mongo_id VARCHAR(24) UNIQUE, -- Store original MongoDB ObjectId as string
    CONSTRAINT valid_duration CHECK (duration_seconds >= 0)
);

-- INSTANCES table: Physical file copies of assets
CREATE TABLE instances (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    file_name VARCHAR(500) NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,
    file_duration NUMERIC(10,3),
    storage_location VARCHAR(255), -- e.g., 'primary_server', 'backup_drive', 'cloud_storage'
    encoded_date TIMESTAMP WITH TIME ZONE,
    is_primary BOOLEAN DEFAULT FALSE, -- Mark primary instance
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_file_size CHECK (file_size >= 0),
    CONSTRAINT unique_file_path UNIQUE (file_path, storage_location)
);

-- TAG_TYPES table: Define categories of tags
CREATE TABLE tag_types (
    id SERIAL PRIMARY KEY,
    type_name VARCHAR(50) UNIQUE NOT NULL, -- 'topic', 'person', 'event', 'location', 'workflow'
    description TEXT
);

-- TAGS table: Reusable tags
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    tag_type_id INTEGER NOT NULL REFERENCES tag_types(id),
    tag_name VARCHAR(255) NOT NULL,
    tag_value VARCHAR(255), -- Optional value for key-value pairs
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_tag UNIQUE (tag_type_id, tag_name)
);

-- ASSET_TAGS junction table: Many-to-many relationship
CREATE TABLE asset_tags (
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asset_id, tag_id)
);

-- METADATA_TYPES table: Define metadata categories
CREATE TABLE metadata_types (
    id SERIAL PRIMARY KEY,
    type_name VARCHAR(50) UNIQUE NOT NULL,
    data_type VARCHAR(20) NOT NULL, -- 'string', 'number', 'date', 'boolean', 'json'
    description TEXT
);

-- METADATA table: Flexible key-value metadata
CREATE TABLE metadata (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    metadata_type_id INTEGER NOT NULL REFERENCES metadata_types(id),
    meta_key VARCHAR(255) NOT NULL,
    meta_value TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_asset_metadata UNIQUE (asset_id, metadata_type_id, meta_key)
);

-- SCHEDULES table: Daily broadcast schedules
CREATE TABLE schedules (
    id SERIAL PRIMARY KEY,
    schedule_name VARCHAR(255),
    air_date DATE NOT NULL,
    channel VARCHAR(50) DEFAULT 'Comcast Channel 26',
    total_duration_seconds NUMERIC(10,3),
    active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    approved_by VARCHAR(255),
    approved_date TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    CONSTRAINT unique_schedule_date UNIQUE (air_date, channel)
);

-- SCHEDULED_ITEMS table: Items within a schedule
CREATE TABLE scheduled_items (
    id SERIAL PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    instance_id INTEGER REFERENCES instances(id), -- Specific file instance to use
    sequence_number INTEGER NOT NULL,
    scheduled_start_time TIME,
    scheduled_duration_seconds NUMERIC(10,3),
    actual_start_time TIME,
    actual_duration_seconds NUMERIC(10,3),
    status VARCHAR(50) DEFAULT 'scheduled', -- 'scheduled', 'aired', 'skipped', 'error'
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_schedule_sequence UNIQUE (schedule_id, sequence_number)
);

-- SCHEDULING_METADATA table: Track scheduling history and metrics
CREATE TABLE scheduling_metadata (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    available_for_scheduling BOOLEAN DEFAULT TRUE,
    content_expiry_date TIMESTAMP WITH TIME ZONE,
    last_scheduled_date TIMESTAMP WITH TIME ZONE,
    total_airings INTEGER DEFAULT 0,
    created_for_scheduling TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Timeslot scheduling tracking
    last_scheduled_in_overnight TIMESTAMP WITH TIME ZONE,
    last_scheduled_in_early_morning TIMESTAMP WITH TIME ZONE,
    last_scheduled_in_morning TIMESTAMP WITH TIME ZONE,
    last_scheduled_in_afternoon TIMESTAMP WITH TIME ZONE,
    last_scheduled_in_prime_time TIMESTAMP WITH TIME ZONE,
    last_scheduled_in_evening TIMESTAMP WITH TIME ZONE,
    
    -- Replay count tracking per timeslot
    replay_count_for_overnight INTEGER DEFAULT 0,
    replay_count_for_early_morning INTEGER DEFAULT 0,
    replay_count_for_morning INTEGER DEFAULT 0,
    replay_count_for_afternoon INTEGER DEFAULT 0,
    replay_count_for_prime_time INTEGER DEFAULT 0,
    replay_count_for_evening INTEGER DEFAULT 0,
    
    -- Engagement and priority scoring
    priority_score NUMERIC(5,2),
    optimal_timeslots TEXT[], -- Array of optimal timeslots
    
    CONSTRAINT unique_asset_scheduling UNIQUE (asset_id)
);

-- Indexes for better query performance
CREATE INDEX idx_assets_guid ON assets(guid);
CREATE INDEX idx_assets_content_type ON assets(content_type);
CREATE INDEX idx_assets_created_at ON assets(created_at);
CREATE INDEX idx_assets_mongo_id ON assets(mongo_id);
CREATE INDEX idx_instances_asset_id ON instances(asset_id);
CREATE INDEX idx_instances_file_name ON instances(file_name);
CREATE INDEX idx_asset_tags_asset_id ON asset_tags(asset_id);
CREATE INDEX idx_asset_tags_tag_id ON asset_tags(tag_id);
CREATE INDEX idx_metadata_asset_id ON metadata(asset_id);
CREATE INDEX idx_schedules_air_date ON schedules(air_date);
CREATE INDEX idx_schedules_active ON schedules(active);
CREATE INDEX idx_scheduled_items_schedule_id ON scheduled_items(schedule_id);
CREATE INDEX idx_scheduled_items_asset_id ON scheduled_items(asset_id);
CREATE INDEX idx_scheduling_metadata_asset_id ON scheduling_metadata(asset_id);

-- Full-text search indexes
CREATE INDEX idx_assets_transcript_fts ON assets USING gin(to_tsvector('english', transcript));
CREATE INDEX idx_assets_summary_fts ON assets USING gin(to_tsvector('english', summary));
CREATE INDEX idx_assets_title_fts ON assets USING gin(to_tsvector('english', content_title));

-- Triggers to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_assets_updated_at BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_instances_updated_at BEFORE UPDATE ON instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Views for common queries
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

-- Insert initial tag types
INSERT INTO tag_types (type_name, description) VALUES
    ('topic', 'Subject matter or theme'),
    ('person', 'People mentioned or featured'),
    ('event', 'Events referenced'),
    ('location', 'Geographic locations'),
    ('workflow', 'Workflow status tags');

-- Insert initial metadata types
INSERT INTO metadata_types (type_name, data_type, description) VALUES
    ('technical', 'json', 'Technical specifications'),
    ('administrative', 'string', 'Administrative metadata'),
    ('descriptive', 'string', 'Descriptive metadata'),
    ('rights', 'string', 'Rights and licensing information'),
    ('scheduling', 'json', 'Scheduling-specific metadata');

-- Add example workflow tags
INSERT INTO tags (tag_type_id, tag_name, description) 
SELECT id, 'Approved', 'Content approved for broadcast' FROM tag_types WHERE type_name = 'workflow';
INSERT INTO tags (tag_type_id, tag_name, description) 
SELECT id, 'Needs Review', 'Content requires review' FROM tag_types WHERE type_name = 'workflow';
INSERT INTO tags (tag_type_id, tag_name, description) 
SELECT id, 'Archived', 'Content archived' FROM tag_types WHERE type_name = 'workflow';