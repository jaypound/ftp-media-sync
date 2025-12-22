#!/usr/bin/env python3
"""Check which holiday greetings are available in spots category"""

import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', ''),
    port=os.getenv('DB_PORT', '5432')
)

cursor = conn.cursor()

print("=== Available Holiday Greetings in SPOTS Category ===\n")

# This is the query that the scheduler would use
cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        a.content_title,
        sm.content_expiry_date,
        sm.available_for_scheduling,
        hgr.scheduled_count
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE a.duration_category = 'spots'
    AND i.file_name ILIKE '%holiday%greeting%'
    AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
    AND (sm.go_live_date IS NULL OR sm.go_live_date <= CURRENT_TIMESTAMP)
    AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
    ORDER BY COALESCE(hgr.scheduled_count, 0), a.content_title
""")

available = cursor.fetchall()
print(f"Found {len(available)} available holiday greetings in spots category:\n")

for asset_id, file_name, title, expiry, avail, count in available:
    short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')
    print(f"{short_name[:40]:40} | Plays: {count or 0:3}")

# Get the never played ones
print("\n=== Never Played Holiday Greetings (Available) ===")
cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        a.duration_category
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE i.file_name ILIKE '%holiday%greeting%'
    AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
    AND (sm.go_live_date IS NULL OR sm.go_live_date <= CURRENT_TIMESTAMP)
    AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
    AND COALESCE(hgr.scheduled_count, 0) = 0
    ORDER BY a.duration_category, i.file_name
""")

never_played = cursor.fetchall()
print(f"\nFound {len(never_played)} never-played available greetings:")
for asset_id, file_name, category in never_played:
    short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')
    print(f"  {short_name[:40]:40} | {category}")

cursor.close()
conn.close()