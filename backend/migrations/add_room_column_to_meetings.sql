-- Add room column to meetings table

ALTER TABLE meetings 
ADD COLUMN IF NOT EXISTS room VARCHAR(100) DEFAULT NULL;