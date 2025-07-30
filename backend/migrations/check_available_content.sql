-- Check what duration categories exist and how many are not in folders containing FILL
SELECT 
    a.duration_category,
    COUNT(*) as total_count,
    COUNT(CASE WHEN i.file_path NOT LIKE '%FILL%' 
          THEN 1 END) as non_fill_folder_count
FROM assets a
JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
WHERE a.analysis_completed = TRUE
GROUP BY a.duration_category
ORDER BY a.duration_category;

-- Check some sample file paths to see the pattern
SELECT DISTINCT 
    i.file_path,
    a.duration_category
FROM assets a
JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
WHERE a.analysis_completed = TRUE
LIMIT 20;