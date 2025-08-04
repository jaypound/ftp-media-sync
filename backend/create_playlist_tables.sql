-- Create PLAYLISTS table
CREATE TABLE IF NOT EXISTS playlists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    play_mode VARCHAR(50) DEFAULT 'sequential',
    auto_remove BOOLEAN DEFAULT true,
    aspect_ratio_n INTEGER DEFAULT 16,
    aspect_ratio_d INTEGER DEFAULT 9,
    timeline_rate_n INTEGER DEFAULT 30000,
    timeline_rate_d INTEGER DEFAULT 1001,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exported_path VARCHAR(500),
    is_active BOOLEAN DEFAULT true
);

-- Create PLAYLIST_ITEMS table
CREATE TABLE IF NOT EXISTS playlist_items (
    id SERIAL PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    start_frame INTEGER DEFAULT 0,
    end_frame INTEGER DEFAULT 0,
    offset_frame INTEGER,
    duration_frame INTEGER DEFAULT 0,
    duration NUMERIC(10,3) DEFAULT 0,
    item_duration NUMERIC(10,3) DEFAULT 0,
    is_selected BOOLEAN DEFAULT false,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(playlist_id, position)
);

-- Create indexes for better performance
CREATE INDEX idx_playlists_name ON playlists(name);
CREATE INDEX idx_playlists_created_date ON playlists(created_date);
CREATE INDEX idx_playlist_items_playlist_id ON playlist_items(playlist_id);
CREATE INDEX idx_playlist_items_position ON playlist_items(playlist_id, position);

-- Add comment to tables
COMMENT ON TABLE playlists IS 'Stores simple playlists for content sequencing';
COMMENT ON TABLE playlist_items IS 'Stores individual items in each playlist';