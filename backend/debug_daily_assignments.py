#!/usr/bin/env python3
"""Debug daily assignments issue"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', '')
)
cursor = conn.cursor(cursor_factory=RealDictCursor)

# Test the exact query being used
test_date = datetime(2025, 12, 21).date()
print(f"\nTesting query for date: {test_date}")

# First the count query
cursor.execute("""
    SELECT COUNT(*) as count
    FROM holiday_greetings_days hgd
    JOIN assets a ON hgd.asset_id = a.id
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE hgd.start_date <= %s AND hgd.end_date > %s
""", (test_date, test_date))

count_result = cursor.fetchone()
print(f"Count result: {count_result['count']}")

# Now the main query
cursor.execute("""
    SELECT DISTINCT
        hgd.asset_id,
        a.id,
        a.content_title,
        i.file_name,
        i.file_path,
        a.duration_seconds,
        a.duration_category,
        a.content_type,
        i.id as instance_id,
        a.engagement_score,
        a.created_at,
        a.updated_at,
        json_build_object(
            'content_expiry_date', sm.content_expiry_date::text,
            'featured', COALESCE(sm.featured, false),
            'available_for_scheduling', COALESCE(sm.available_for_scheduling, true)
        ) as scheduling
    FROM holiday_greetings_days hgd
    JOIN assets a ON hgd.asset_id = a.id
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE hgd.start_date <= %s 
    AND hgd.end_date > %s
    ORDER BY hgd.asset_id
""", (test_date, test_date))

results = cursor.fetchall()
print(f"Main query results: {len(results)} rows")

if results:
    for r in results:
        print(f"  - {r['file_name']} (ID: {r['asset_id']})")
else:
    # Check what's in holiday_greetings_days
    cursor.execute("""
        SELECT hgd.*, a.id, i.is_primary
        FROM holiday_greetings_days hgd
        LEFT JOIN assets a ON hgd.asset_id = a.id
        LEFT JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
        WHERE hgd.start_date <= %s AND hgd.end_date > %s
    """, (test_date, test_date))
    
    debug_results = cursor.fetchall()
    print("\nDebug: All assignments for this date:")
    for d in debug_results:
        print(f"  Asset ID: {d['asset_id']}, Has Asset: {d['id'] is not None}, Has Primary Instance: {d['is_primary']}")

cursor.close()
conn.close()