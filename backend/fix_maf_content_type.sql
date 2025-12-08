-- Fix MAF content that was incorrectly categorized as 'other'
-- This script updates content that should be MAF based on file naming patterns

-- First, let's see what we're going to update
SELECT 
    COUNT(*) as count,
    content_type,
    string_agg(DISTINCT substring(file_name from 1 for 50), ', ') as sample_files
FROM assets a
JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
WHERE content_type = 'other'
AND (
    UPPER(file_name) LIKE '%MAF%' 
    OR UPPER(file_name) LIKE '%MOVING ATLANTA FORWARD%'
    OR UPPER(content_title) LIKE '%MAF%'
    OR UPPER(content_title) LIKE '%MOVING ATLANTA FORWARD%'
)
GROUP BY content_type;

-- Update the content type for MAF content
UPDATE assets
SET content_type = 'maf',
    updated_at = NOW()
WHERE id IN (
    SELECT DISTINCT a.id
    FROM assets a
    JOIN instances i ON a.id = i.asset_id
    WHERE a.content_type = 'other'
    AND (
        UPPER(i.file_name) LIKE '%MAF%' 
        OR UPPER(i.file_name) LIKE '%MOVING ATLANTA FORWARD%'
        OR UPPER(a.content_title) LIKE '%MAF%'
        OR UPPER(a.content_title) LIKE '%MOVING ATLANTA FORWARD%'
    )
);

-- Also check for other content types that might be miscategorized
-- This query shows a summary of 'other' content that might need reclassification
SELECT 
    COUNT(*) as count,
    CASE 
        WHEN UPPER(file_name) LIKE '%AN_%' OR UPPER(file_name) LIKE '%ATLANTA NOW%' THEN 'Should be AN'
        WHEN UPPER(file_name) LIKE '%ATLD%' OR UPPER(file_name) LIKE '%ATLANTA DIRECT%' THEN 'Should be ATLD'
        WHEN UPPER(file_name) LIKE '%BMP%' OR UPPER(file_name) LIKE '%BUMP%' THEN 'Should be BMP'
        WHEN UPPER(file_name) LIKE '%IMOW%' OR UPPER(file_name) LIKE '%IN MY OWN WORDS%' THEN 'Should be IMOW'
        WHEN UPPER(file_name) LIKE '%_IM_%' OR UPPER(file_name) LIKE '%INCLUSION MONTH%' THEN 'Should be IM'
        WHEN UPPER(file_name) LIKE '%_LM_%' OR UPPER(file_name) LIKE '%LEGISLATIVE MINUTE%' THEN 'Should be LM'
        WHEN UPPER(file_name) LIKE '%PMO%' OR UPPER(file_name) LIKE '%PROMO%' THEN 'Should be PMO'
        WHEN UPPER(file_name) LIKE '%SZL%' OR UPPER(file_name) LIKE '%SIZZLE%' THEN 'Should be SZL'
        WHEN UPPER(file_name) LIKE '%SPP%' OR UPPER(file_name) LIKE '%SPECIAL PROJECT%' THEN 'Should be SPP'
        ELSE 'Correctly OTHER'
    END as suggested_type,
    string_agg(DISTINCT substring(file_name from 1 for 50), ', ') as sample_files
FROM assets a
JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
WHERE content_type = 'other'
GROUP BY suggested_type
ORDER BY count DESC;