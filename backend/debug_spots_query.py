#!/usr/bin/env python3
"""Debug why spots category returns so few items"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager
from datetime import datetime, timedelta
import pytz

db_manager.connect()

conn = db_manager._get_connection()
cursor = conn.cursor()

# Simulate the query with replay delays
eastern = pytz.timezone('US/Eastern')
schedule_date = datetime.now(eastern).strftime('%Y-%m-%d')
compare_date = datetime.now(eastern)

# Base delays for spots
base_delay = 48  # From config
additional_delay = 1

print("=== Debug Spots Query ===\n")
print(f"Schedule date: {schedule_date}")
print(f"Compare date: {compare_date}")
print(f"Base delay: {base_delay} hours")

# Run the query with delay calculations
cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        sm.last_scheduled_date,
        CASE 
            WHEN COALESCE(sm.featured, FALSE) = TRUE THEN 2
            ELSE (48 + (COALESCE(sm.total_airings, 0) * 1))
        END as required_delay_hours,
        EXTRACT(EPOCH FROM (%s - COALESCE(sm.last_scheduled_date, '2020-01-01'::timestamp))) / 3600 as hours_since_last_scheduled,
        CASE 
            WHEN EXTRACT(EPOCH FROM (%s - COALESCE(sm.last_scheduled_date, '2020-01-01'::timestamp))) / 3600 >= 
                 CASE 
                    WHEN COALESCE(sm.featured, FALSE) = TRUE THEN 2
                    ELSE (48 + (COALESCE(sm.total_airings, 0) * 1))
                 END 
            THEN 'AVAILABLE'
            ELSE 'BLOCKED'
        END as status
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE 
        a.analysis_completed = TRUE
        AND a.duration_category = 'spots'
        AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
        AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
        AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
    ORDER BY hours_since_last_scheduled DESC
    LIMIT 30
""", (compare_date, compare_date, schedule_date, schedule_date))

results = cursor.fetchall()
print(f"\nFound {cursor.rowcount} items (showing first 30):\n")

available_count = 0
blocked_count = 0

for asset_id, file_name, last_sched, req_delay, hours_since, status in results:
    is_greeting = 'holiday' in file_name.lower() and 'greeting' in file_name.lower()
    prefix = "GREETING: " if is_greeting else "          "
    
    short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:40]
    
    if status == 'AVAILABLE':
        available_count += 1
    else:
        blocked_count += 1
        
    if is_greeting or blocked_count <= 5:
        print(f"{prefix}{short_name:40} | Hours since: {hours_since:7.1f} | Required: {req_delay:3.0f} | {status}")
        if last_sched and hours_since < 0:
            print(f"          WARNING: Scheduled in future: {last_sched}")

print(f"\nSummary:")
print(f"  Available: {available_count}")
print(f"  Blocked by delay: {blocked_count}")

# Check specifically what would be returned without delays
print("\n=== Without Replay Delays ===")
cursor.execute("""
    SELECT COUNT(*)
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE 
        a.analysis_completed = TRUE
        AND a.duration_category = 'spots'
        AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
        AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
        AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
""", (schedule_date, schedule_date))

total = cursor.fetchone()[0]
print(f"\nTotal spots without delays: {total}")

cursor.close()
db_manager._put_connection(conn)