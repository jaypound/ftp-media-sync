#!/usr/bin/env python3
"""Check analysis status of holiday greetings"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', ''),
    port=os.getenv('DB_PORT', '5432')
)

cursor = conn.cursor()

print("=== Holiday Greeting Analysis Status ===\n")

cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        a.analysis_completed,
        a.duration_category,
        hgr.scheduled_count
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE i.file_name ILIKE '%holiday%greeting%'
    ORDER BY a.analysis_completed, hgr.scheduled_count
""")

results = cursor.fetchall()
analyzed = 0
not_analyzed = 0

print("Not Analyzed Holiday Greetings:")
for asset_id, file_name, analyzed_flag, category, count in results:
    if not analyzed_flag:
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')
        print(f"  {short_name[:40]:40} | {category:6} | Plays: {count or 0}")
        not_analyzed += 1
    else:
        analyzed += 1

print(f"\nSummary:")
print(f"  Analyzed: {analyzed}")
print(f"  Not Analyzed: {not_analyzed}")
print(f"  Total: {len(results)}")

# Check what's actually available for spots
print("\n=== Checking Actual Query Results ===")
cursor.execute("""
    SELECT COUNT(*)
    FROM assets a
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE a.duration_category = 'spots'
      AND a.analysis_completed = TRUE
      AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
      AND (sm.go_live_date IS NULL OR sm.go_live_date <= CURRENT_TIMESTAMP)
""")

total_spots = cursor.fetchone()[0]
print(f"\nTotal spots content available (with analysis_completed): {total_spots}")

# Check how many are holiday greetings
cursor.execute("""
    SELECT COUNT(*)
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE a.duration_category = 'spots'
      AND a.analysis_completed = TRUE
      AND i.file_name ILIKE '%holiday%greeting%'
      AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
      AND (sm.go_live_date IS NULL OR sm.go_live_date <= CURRENT_TIMESTAMP)
""")

holiday_spots = cursor.fetchone()[0]
print(f"Holiday greetings in spots (with analysis_completed): {holiday_spots}")

cursor.close()
conn.close()