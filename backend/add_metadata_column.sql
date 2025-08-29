-- Add metadata column to scheduled_items table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'scheduled_items' 
        AND column_name = 'metadata'
    ) THEN
        ALTER TABLE scheduled_items ADD COLUMN metadata JSONB;
        RAISE NOTICE 'Added metadata column to scheduled_items table';
    ELSE
        RAISE NOTICE 'metadata column already exists in scheduled_items table';
    END IF;
END $$;