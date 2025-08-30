-- Migration to add ATLD (ATL Direct) content type
-- Run this against your PostgreSQL database

-- Add new value to content_type enum
ALTER TYPE content_type ADD VALUE 'atld';

-- Verify the enum was updated
SELECT unnest(enum_range(NULL::content_type)) as content_types;