#!/usr/bin/env python3
"""Check why holiday greetings aren't appearing in spots category"""

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

print("=== Checking Holiday Greeting Availability ===\n")

# Check all holiday greetings with their metadata
cursor.execute("""
    SELECT 
        a.id,
        a.content_title,
        a.duration_category,
        i.file_name,
        sm.content_expiry_date,
        sm.go_live_date,
        sm.available_for_scheduling,
        sm.last_scheduled_date,
        hgr.scheduled_count
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE i.file_name ILIKE '%holiday%greeting%'
    ORDER BY a.duration_category, hgr.scheduled_count
""")

results = cursor.fetchall()
# Use timezone-aware datetime
eastern = pytz.timezone('US/Eastern')
now = datetime.now(eastern)

print(f"Found {len(results)} holiday greetings\n")

expired_count = 0
not_live_count = 0
unavailable_count = 0
available_count = 0

for row in results:
    asset_id, title, category, file_name, expiry, go_live, available, last_sched, count = row
    
    # Check availability
    is_expired = expiry and expiry < now
    not_live_yet = go_live and go_live > now
    not_available = available is False
    
    status = "AVAILABLE"
    if is_expired:
        status = "EXPIRED"
        expired_count += 1
    elif not_live_yet:
        status = "NOT LIVE YET"
        not_live_count += 1
    elif not_available:
        status = "DISABLED"
        unavailable_count += 1
    else:
        available_count += 1
    
    if status != "AVAILABLE":
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')
        print(f"{short_name[:35]:35} | {category:6} | {status:12} | Plays: {count or 0}")
        if is_expired and expiry:
            print(f"    Expired: {expiry}")
        if not_live_yet and go_live:
            print(f"    Go live: {go_live}")

print(f"\nSummary:")
print(f"  Available: {available_count}")
print(f"  Expired: {expired_count}")
print(f"  Not live yet: {not_live_count}")
print(f"  Disabled: {unavailable_count}")
print(f"  Total: {len(results)}")

# Check replay delays
print("\n=== Checking Replay Delays ===")
cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        sm.last_scheduled_date,
        EXTRACT(EPOCH FROM (NOW() - sm.last_scheduled_date))/3600 as hours_since
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE i.file_name ILIKE '%holiday%greeting%'
    AND sm.last_scheduled_date IS NOT NULL
    AND sm.last_scheduled_date > NOW() - INTERVAL '48 hours'
    ORDER BY sm.last_scheduled_date DESC
""")

recent = cursor.fetchall()
if recent:
    print(f"\nGreetings scheduled in last 48 hours:")
    for asset_id, file_name, last_sched, hours in recent:
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')
        print(f"  {short_name[:35]:35} | {hours:.1f} hours ago")

cursor.close()
conn.close()