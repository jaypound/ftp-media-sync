-- Check for MAF content that might be categorized as OTHER
-- First, check what content_types exist in the database
SELECT content_type, COUNT(*) as count
FROM assets
GROUP BY content_type
ORDER BY count DESC;

-- Check for files with MAF in the filename but content_type as 'other'
SELECT file_name, file_path, content_type, content_title
FROM assets a
JOIN instances i ON a.id = i.asset_id
WHERE UPPER(i.file_name) LIKE '%MAF%'
AND a.content_type = 'other'
LIMIT 20;

-- Check for files with 'Moving Atlanta Forward' in path/name but content_type as 'other'
SELECT file_name, file_path, content_type, content_title
FROM assets a
JOIN instances i ON a.id = i.asset_id
WHERE (UPPER(i.file_path) LIKE '%MOVING%ATLANTA%FORWARD%' 
    OR UPPER(i.file_name) LIKE '%MOVING%ATLANTA%FORWARD%')
AND a.content_type = 'other'
LIMIT 20;

-- Check all MAF content regardless of content_type
SELECT file_name, file_path, content_type, content_title
FROM assets a
JOIN instances i ON a.id = i.asset_id
WHERE UPPER(i.file_name) LIKE '%MAF%'
   OR UPPER(i.file_path) LIKE '%MOVING%ATLANTA%FORWARD%'
ORDER BY a.created_at DESC
LIMIT 30;

-- Check if MAF is properly in the enum
SELECT enumlabel 
FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'content_type')
ORDER BY enumlabel;