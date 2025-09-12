-- Check for assets with NULL or empty duration_category
SELECT 
    content_type,
    COUNT(*) as count,
    MIN(duration_seconds) as min_duration,
    MAX(duration_seconds) as max_duration,
    AVG(duration_seconds) as avg_duration
FROM assets
WHERE duration_category IS NULL
GROUP BY content_type
ORDER BY count DESC;

-- Check all possible values in duration_category for MTG content
SELECT DISTINCT duration_category, COUNT(*) as count
FROM assets
WHERE content_type = 'mtg'
GROUP BY duration_category
ORDER BY duration_category;

-- Look for any assets with duration_category that might be displaying as 'UNKNOWN'
SELECT 
    id,
    content_type,
    content_title,
    duration_seconds,
    duration_category,
    CASE 
        WHEN duration_category IS NULL THEN 'NULL'
        WHEN duration_category::text = '' THEN 'EMPTY'
        ELSE duration_category::text
    END as category_display
FROM assets
WHERE content_type = 'mtg'
AND (
    duration_category IS NULL 
    OR duration_category::text NOT IN ('id', 'spots', 'short_form', 'long_form')
)
LIMIT 20;