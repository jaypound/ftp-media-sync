-- Check current content type enum values
SELECT enumlabel 
FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'content_type')
ORDER BY enumsortorder;

-- Check what content types are actually in use
SELECT DISTINCT content_type, COUNT(*) 
FROM assets 
WHERE content_type IS NOT NULL 
GROUP BY content_type 
ORDER BY content_type;