#!/usr/bin/env python3
"""Debug why holiday greetings aren't selected for future schedules"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager
from datetime import datetime, timedelta
import pytz
import psycopg2
from dotenv import load_dotenv

load_dotenv()

print("=== Debug Holiday Greeting Future Schedule Delays ===\n")

# Direct database connection
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
future_date = now + timedelta(days=7)

print(f"Current time: {now}")
print(f"Future schedule date: {future_date}\n")

# Check all holiday greetings and their scheduling status
print("=== All Holiday Greetings Scheduling Status ===")
cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        sm.last_scheduled_date,
        EXTRACT(EPOCH FROM (%s::timestamp - COALESCE(sm.last_scheduled_date, '2020-01-01'::timestamp))) / 3600 as hours_from_future,
        48 as base_delay,
        COALESCE(sm.total_airings, 0) * 2 as additional_delay,
        48 + (COALESCE(sm.total_airings, 0) * 2) as total_required_delay,
        CASE 
            WHEN EXTRACT(EPOCH FROM (%s::timestamp - COALESCE(sm.last_scheduled_date, '2020-01-01'::timestamp))) / 3600 >= 
                 (48 + (COALESCE(sm.total_airings, 0) * 2))
            THEN 'AVAILABLE'
            ELSE 'BLOCKED'
        END as status,
        hgr.scheduled_count
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
    AND a.duration_category = 'spots'
    AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
    ORDER BY 
        COALESCE(hgr.scheduled_count, 0),
        sm.last_scheduled_date DESC NULLS LAST
""", (future_date, future_date, future_date))

results = cursor.fetchall()
print(f"Total holiday greetings checked: {len(results)}\n")

available_count = 0
blocked_count = 0
future_scheduled_count = 0

print("Status | Plays | Hours from Future | Required | Last Scheduled | File Name")
print("-" * 100)

for row in results:
    asset_id, file_name, last_scheduled, hours_from_future, base_delay, additional_delay, total_delay, status, scheduled_count = row
    
    if status == 'AVAILABLE':
        available_count += 1
    else:
        blocked_count += 1
    
    if last_scheduled and last_scheduled > now:
        future_scheduled_count += 1
        status += " (FUTURE)"
    
    # Show first few of each status
    if (status.startswith('AVAILABLE') and available_count <= 5) or (status.startswith('BLOCKED') and blocked_count <= 5):
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:35]
        last_sched_str = last_scheduled.strftime('%Y-%m-%d %H:%M') if last_scheduled else 'Never'
        print(f"{status:15} | {scheduled_count or 0:5} | {hours_from_future:7.1f} | {total_delay:8.0f} | {last_sched_str:16} | {short_name}")

print(f"\nSummary:")
print(f"  Available for future schedule: {available_count}")
print(f"  Blocked by replay delays: {blocked_count}")
print(f"  Scheduled in the future: {future_scheduled_count}")

# Check the specific issue with never-played greetings
print("\n=== Never-Played Greetings Check ===")
cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        sm.last_scheduled_date,
        sm.content_expiry_date,
        sm.go_live_date,
        sm.available_for_scheduling,
        a.analysis_completed
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
    AND a.duration_category = 'spots'
    AND COALESCE(hgr.scheduled_count, 0) = 0
    AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
""", (future_date,))

never_played = cursor.fetchall()
print(f"Found {len(never_played)} never-played greetings\n")

for asset_id, file_name, last_sched, expiry, go_live, available, analysis in never_played[:5]:
    short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:40]
    print(f"{short_name}")
    print(f"  Analysis completed: {analysis}")
    print(f"  Available for scheduling: {available if available is not None else 'None (defaults to True)'}")
    print(f"  Go live date: {go_live if go_live else 'None'}")
    print(f"  Expiry date: {expiry if expiry else 'None'}")
    print()

cursor.close()
conn.close()