-- Check content inventory
SELECT 
    duration_category,
    COUNT(*) as total_assets,
    COUNT(DISTINCT a.id) as unique_assets
FROM assets a
WHERE a.duration_category IS NOT NULL
GROUP BY duration_category
ORDER BY duration_category;

-- Check replay delays configuration
SELECT * FROM scheduling_config ORDER BY category;

-- Check how much content has been used recently
SELECT 
    a.duration_category,
    COUNT(*) as scheduled_items,
    COUNT(DISTINCT a.id) as unique_assets_used,
    AVG(sm.total_airings) as avg_airings
FROM assets a
JOIN scheduling_metadata sm ON a.id = sm.asset_id
WHERE sm.last_scheduled_date > CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY a.duration_category
ORDER BY a.duration_category;

-- Check content availability considering delays
-- For 'id' category with 9h base + 2h per airing
SELECT COUNT(*) as available_id_content
FROM assets a
LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
WHERE a.duration_category = 'id'
  AND a.analysis_completed = TRUE
  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
  AND (
      sm.last_scheduled_date IS NULL 
      OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sm.last_scheduled_date)) / 3600 >= (9 + (COALESCE(sm.total_airings, 0) * 2))
  );

-- Same for spots (12h + 3h)
SELECT COUNT(*) as available_spots_content
FROM assets a
LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
WHERE a.duration_category = 'spots'
  AND a.analysis_completed = TRUE
  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
  AND (
      sm.last_scheduled_date IS NULL 
      OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sm.last_scheduled_date)) / 3600 >= (12 + (COALESCE(sm.total_airings, 0) * 3))
  );

-- Same for short_form (24h + 6h)
SELECT COUNT(*) as available_short_form_content
FROM assets a
LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
WHERE a.duration_category = 'short_form'
  AND a.analysis_completed = TRUE
  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
  AND (
      sm.last_scheduled_date IS NULL 
      OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sm.last_scheduled_date)) / 3600 >= (24 + (COALESCE(sm.total_airings, 0) * 6))
  );

-- Same for long_form (96h + 24h)
SELECT COUNT(*) as available_long_form_content
FROM assets a
LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
WHERE a.duration_category = 'long_form'
  AND a.analysis_completed = TRUE
  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
  AND (
      sm.last_scheduled_date IS NULL 
      OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sm.last_scheduled_date)) / 3600 >= (96 + (COALESCE(sm.total_airings, 0) * 24))
  );