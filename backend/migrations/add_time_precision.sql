-- Add millisecond precision to TIME columns
-- This migration updates the scheduled_start_time and actual_start_time columns
-- to support millisecond precision (3 fractional digits)

ALTER TABLE scheduled_items 
ALTER COLUMN scheduled_start_time TYPE TIME(3);

ALTER TABLE scheduled_items 
ALTER COLUMN actual_start_time TYPE TIME(3);