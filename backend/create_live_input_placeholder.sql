-- Create a placeholder asset for live inputs
-- This asset will be referenced by all live input scheduled items

-- Check if placeholder already exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM assets WHERE guid = '00000000-0000-0000-0000-000000000000') THEN
        INSERT INTO assets (
            guid, 
            content_title, 
            content_type, 
            duration_seconds, 
            duration_category,
            engagement_score,
            created_at,
            updated_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000000',
            'Live Input Placeholder',
            'other',
            0,
            'spots',
            0,
            NOW(),
            NOW()
        );
        
        RAISE NOTICE 'Created placeholder asset for live inputs';
    ELSE
        RAISE NOTICE 'Placeholder asset already exists';
    END IF;
END $$;

-- Show the placeholder asset
SELECT id, guid, content_title, content_type FROM assets WHERE guid = '00000000-0000-0000-0000-000000000000';