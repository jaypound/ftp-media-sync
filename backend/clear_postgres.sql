-- Clear all data from PostgreSQL tables before re-running migration
-- This maintains the schema but removes all data

TRUNCATE TABLE scheduled_items CASCADE;
TRUNCATE TABLE schedules CASCADE;
TRUNCATE TABLE scheduling_metadata CASCADE;
TRUNCATE TABLE metadata CASCADE;
TRUNCATE TABLE asset_tags CASCADE;
TRUNCATE TABLE tags CASCADE;
TRUNCATE TABLE instances CASCADE;
TRUNCATE TABLE assets CASCADE;

-- Reset sequences
ALTER SEQUENCE assets_id_seq RESTART WITH 1;
ALTER SEQUENCE instances_id_seq RESTART WITH 1;
ALTER SEQUENCE tags_id_seq RESTART WITH 1;
ALTER SEQUENCE metadata_id_seq RESTART WITH 1;
ALTER SEQUENCE schedules_id_seq RESTART WITH 1;
ALTER SEQUENCE scheduled_items_id_seq RESTART WITH 1;
ALTER SEQUENCE scheduling_metadata_id_seq RESTART WITH 1;

-- Re-insert tag types (they were not truncated)
-- No need, tag_types table wasn't truncated

-- Verify counts
SELECT 'assets' as table_name, COUNT(*) as count FROM assets
UNION ALL
SELECT 'instances', COUNT(*) FROM instances
UNION ALL
SELECT 'tags', COUNT(*) FROM tags
UNION ALL
SELECT 'asset_tags', COUNT(*) FROM asset_tags;