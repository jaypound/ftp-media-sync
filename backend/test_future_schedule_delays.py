#!/usr/bin/env python3
"""Test if holiday greetings are properly scheduled for future dates"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from datetime import datetime, timedelta
import pytz

print("=== Testing Future Schedule Holiday Greeting Delays ===\n")

# Connect to database
db_manager.connect()

# Create scheduler instance
scheduler = PostgreSQLScheduler()

# Test dates
eastern = pytz.timezone('US/Eastern')
today = datetime.now(eastern).strftime('%Y-%m-%d')
future_date = (datetime.now(eastern) + timedelta(days=7)).strftime('%Y-%m-%d')

print(f"Today: {today}")
print(f"Future schedule date: {future_date}\n")

# Test 1: Get available content for today
print("=== Test 1: Available content for TODAY ===")
content_today = scheduler.get_available_content(
    'spots',
    exclude_ids=[],
    schedule_date=today
)

holiday_today = [c for c in content_today if 'holiday' in c['file_name'].lower() and 'greeting' in c['file_name'].lower()]
print(f"Total spots available: {len(content_today)}")
print(f"Holiday greetings available: {len(holiday_today)}")
if holiday_today:
    print("First few holiday greetings:")
    for hg in holiday_today[:3]:
        print(f"  - {hg['file_name']}")

# Test 2: Get available content for future date
print("\n=== Test 2: Available content for FUTURE DATE (1 week later) ===")
content_future = scheduler.get_available_content(
    'spots',
    exclude_ids=[],
    schedule_date=future_date
)

holiday_future = [c for c in content_future if 'holiday' in c['file_name'].lower() and 'greeting' in c['file_name'].lower()]
print(f"Total spots available: {len(content_future)}")
print(f"Holiday greetings available: {len(holiday_future)}")
if holiday_future:
    print("First few holiday greetings:")
    for hg in holiday_future[:3]:
        print(f"  - {hg['file_name']}")

# Test 3: Check a specific greeting's last scheduled date
print("\n=== Debug: Check all holiday greetings ===")
import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn2 = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', ''),
    port=os.getenv('DB_PORT', '5432')
)
cursor = conn2.cursor()

cursor.execute("""
    SELECT COUNT(*)
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
""")
result = cursor.fetchone()
total_greetings = result[0] if result else 0
print(f"Total holiday greetings in database: {total_greetings}")

cursor.execute("""
    SELECT COUNT(*)
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
    AND a.duration_category = 'spots'
""")
result = cursor.fetchone()
spots_greetings = result[0] if result else 0
print(f"Holiday greetings in 'spots' category: {spots_greetings}")

cursor.execute("""
    SELECT COUNT(*)
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
    AND a.duration_category = 'spots'
    AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > NOW())
""")
result = cursor.fetchone()
unexpired_greetings = result[0] if result else 0
print(f"Non-expired holiday greetings in 'spots': {unexpired_greetings}")

print("\n=== Test 3: Check specific greeting's scheduling metadata ===")

cursor.execute("""
    SELECT 
        a.id,
        i.file_name,
        sm.last_scheduled_date,
        EXTRACT(EPOCH FROM (NOW() - sm.last_scheduled_date)) / 3600 as hours_from_now,
        EXTRACT(EPOCH FROM (%s::timestamp - sm.last_scheduled_date)) / 3600 as hours_from_future
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE i.file_name ILIKE '%%violence reduction%%holiday%%greeting%%'
    LIMIT 1
""", (future_date,))

result = cursor.fetchone()
if result:
    asset_id, file_name, last_sched, hours_now, hours_future = result
    print(f"Violence Reduction greeting:")
    print(f"  Last scheduled: {last_sched}")
    print(f"  Hours from now: {hours_now:.1f}")
    print(f"  Hours from future date: {hours_future:.1f}")
    print(f"  Required delay: 48 hours (base)")

cursor.close()
conn2.close()

print("\n=== Test 4: Testing progressive delays for future date ===")
# Test with progressive delays
available_with_delays = scheduler._get_content_with_progressive_delays(
    'spots',
    exclude_ids=[],
    schedule_date=future_date
)

holiday_with_delays = [c for c in available_with_delays if 'holiday' in c['file_name'].lower() and 'greeting' in c['file_name'].lower()]
print(f"Total spots with progressive delays: {len(available_with_delays)}")
print(f"Holiday greetings with progressive delays: {len(holiday_with_delays)}")
if available_with_delays and '_delay_factor_used' in available_with_delays[0]:
    print(f"Delay factor used: {available_with_delays[0]['_delay_factor_used'] * 100}%")