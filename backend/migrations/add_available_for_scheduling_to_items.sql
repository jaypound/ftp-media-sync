-- Add available_for_scheduling field to scheduled_items table
-- This allows individual items in a schedule to be disabled from future scheduling

ALTER TABLE scheduled_items 
ADD COLUMN available_for_scheduling BOOLEAN DEFAULT TRUE;

-- Add index for performance when filtering available items
CREATE INDEX idx_scheduled_items_available 
ON scheduled_items(schedule_id, available_for_scheduling) 
WHERE available_for_scheduling = TRUE;

-- Add comment to document the field
COMMENT ON COLUMN scheduled_items.available_for_scheduling IS 
'Controls whether this item can be selected for future scheduling. Set to FALSE to disable the item.';