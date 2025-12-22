#!/usr/bin/env python3
"""Debug why go-live date test is failing"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timedelta
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

# Test dates
eastern = pytz.timezone('US/Eastern')
now = datetime.now(eastern)
future_date = now + timedelta(days=14)  # 2026-01-02

print("=== Debug Go-Live Date Issue ===\n")
print(f"Current date: {now}")
print(f"Future schedule date: {future_date}\n")

# Check the test asset
cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        sm.go_live_date,
        sm.content_expiry_date,
        sm.available_for_scheduling
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE i.file_name = '251210_SSP_ATLDOT Holiday Greetings_15_v1.mp4'
""")

result = cursor.fetchone()
if result:
    asset_id, file_name, go_live, expiry, available = result
    print(f"Test asset: {file_name}")
    print(f"  Go-live date: {go_live}")
    print(f"  Expiry date: {expiry}")
    print(f"  Available for scheduling: {available}")
    print()

# Check which greetings ARE available for the future date
print("=== Greetings available for future date ===")
cursor.execute("""
    SELECT 
        i.file_name,
        sm.go_live_date,
        sm.content_expiry_date
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE a.duration_category = 'spots'
      AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
      AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
      AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
    ORDER BY hgr.scheduled_count ASC
""", (future_date, future_date))

available = cursor.fetchall()
print(f"Found {len(available)} greetings available for {future_date.strftime('%Y-%m-%d')}:\n")

for file_name, go_live, expiry in available[:5]:
    short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:35]
    print(f"{short_name}")
    print(f"  Go-live: {go_live if go_live else 'None'}")
    print(f"  Expiry: {expiry if expiry else 'None'}")
    print()

# Check greetings that are NOT available due to dates
print("=== Greetings blocked by date constraints ===")
cursor.execute("""
    SELECT 
        i.file_name,
        sm.go_live_date,
        sm.content_expiry_date,
        CASE 
            WHEN sm.content_expiry_date IS NOT NULL AND sm.content_expiry_date <= %s THEN 'EXPIRED'
            WHEN sm.go_live_date IS NOT NULL AND sm.go_live_date > %s THEN 'NOT LIVE YET'
            ELSE 'OTHER'
        END as reason
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE a.duration_category = 'spots'
      AND (
        (sm.content_expiry_date IS NOT NULL AND sm.content_expiry_date <= %s)
        OR (sm.go_live_date IS NOT NULL AND sm.go_live_date > %s)
      )
    ORDER BY reason, i.file_name
""", (future_date, future_date, future_date, future_date))

blocked = cursor.fetchall()
print(f"\nFound {len(blocked)} greetings blocked for {future_date.strftime('%Y-%m-%d')}:\n")

expired_count = 0
not_live_count = 0

for file_name, go_live, expiry, reason in blocked:
    if reason == 'EXPIRED':
        expired_count += 1
        if expired_count <= 3:
            short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:35]
            print(f"{short_name} - {reason}")
            print(f"  Expiry: {expiry}")
    elif reason == 'NOT LIVE YET':
        not_live_count += 1
        if not_live_count <= 3:
            short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:35]
            print(f"{short_name} - {reason}")
            print(f"  Go-live: {go_live}")

print(f"\nSummary:")
print(f"  Expired: {expired_count}")
print(f"  Not live yet: {not_live_count}")

cursor.close()
conn.close()