-- Fix duration_category for meeting content based on actual duration
-- This script updates assets with NULL or invalid duration_category values

-- Update duration_category based on duration_seconds using the same logic as file_analyzer.py
UPDATE assets
SET duration_category = CASE
    WHEN duration_seconds < 16 THEN 'id'::duration_category
    WHEN duration_seconds < 120 THEN 'spots'::duration_category
    WHEN duration_seconds < 1200 THEN 'short_form'::duration_category
    ELSE 'long_form'::duration_category
END
WHERE content_type = 'mtg' 
AND (duration_category IS NULL OR duration_category NOT IN ('id', 'spots', 'short_form', 'long_form'));

-- Show the results
SELECT 
    content_type,
    duration_category,
    COUNT(*) as count,
    AVG(duration_seconds) as avg_duration_seconds,
    MIN(duration_seconds) as min_duration_seconds,
    MAX(duration_seconds) as max_duration_seconds
FROM assets
WHERE content_type = 'mtg'
GROUP BY content_type, duration_category
ORDER BY duration_category;

-- Also update any other content types that might have invalid duration categories
UPDATE assets
SET duration_category = CASE
    WHEN duration_seconds < 16 THEN 'id'::duration_category
    WHEN duration_seconds < 120 THEN 'spots'::duration_category
    WHEN duration_seconds < 1200 THEN 'short_form'::duration_category
    ELSE 'long_form'::duration_category
END
WHERE duration_category IS NULL 
OR duration_category NOT IN ('id', 'spots', 'short_form', 'long_form');

-- Show summary of all content types after fix
SELECT 
    content_type,
    duration_category,
    COUNT(*) as count
FROM assets
GROUP BY content_type, duration_category
ORDER BY content_type, duration_category;