#!/usr/bin/env python3
"""Test if holiday greetings honor go-live dates for future schedules"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from holiday_greeting_integration import HolidayGreetingIntegration
from datetime import datetime, timedelta
import pytz
import psycopg2
from dotenv import load_dotenv

load_dotenv()

print("=== Testing Holiday Greeting Go-Live Date Handling ===\n")

# Connect to database
db_manager.connect()

# Test dates
eastern = pytz.timezone('US/Eastern')
now = datetime.now(eastern)
future_schedule_date = (now + timedelta(days=14)).strftime('%Y-%m-%d')  # 2 weeks from now
go_live_date_between = now + timedelta(days=7)  # 1 week from now

print(f"Current date: {now.strftime('%Y-%m-%d')}")
print(f"Go-live date for test greeting: {go_live_date_between.strftime('%Y-%m-%d')}")
print(f"Future schedule date: {future_schedule_date}\n")

# Direct database connection for testing
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', ''),
    port=os.getenv('DB_PORT', '5432')
)
cursor = conn.cursor()

# Find a test greeting to set go-live date on (Clay greeting which doesn't expire until Jan 14)
cursor.execute("""
    SELECT a.id, i.file_name
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    WHERE i.file_name ILIKE '%%clay holiday greeting%%'
    AND a.duration_category = 'spots'
    LIMIT 1
""")

test_asset = cursor.fetchone()
if test_asset:
    test_asset_id, test_file_name = test_asset
    print(f"Test greeting: {test_file_name}")
    
    # Set the go-live date to 1 week from now
    cursor.execute("""
        UPDATE scheduling_metadata
        SET go_live_date = %s
        WHERE asset_id = %s
    """, (go_live_date_between, test_asset_id))
    conn.commit()
    print(f"Set go-live date to {go_live_date_between.strftime('%Y-%m-%d')}\n")
else:
    print("No test greeting found!")
    cursor.close()
    conn.close()
    exit(1)

# Test 1: Check if greeting is available for current date (should NOT be)
print("=== Test 1: Check availability for CURRENT date ===")
integration = HolidayGreetingIntegration(db_manager)
integration.enabled = True

current_available = integration._get_all_holiday_greetings('spots', now.strftime('%Y-%m-%d'))
test_greeting_in_current = any(g['asset_id'] == test_asset_id for g in current_available)
print(f"Test greeting available for current date: {test_greeting_in_current}")
print(f"Total greetings available for current date: {len(current_available)}")

# Test 2: Check if greeting is available for future date (should be)
print("\n=== Test 2: Check availability for FUTURE schedule date ===")
future_available = integration._get_all_holiday_greetings('spots', future_schedule_date)
test_greeting_in_future = any(g['asset_id'] == test_asset_id for g in future_available)
print(f"Test greeting available for future date: {test_greeting_in_future}")
print(f"Total greetings available for future date: {len(future_available)}")

# Test 3: Check through the full scheduler
print("\n=== Test 3: Test through full scheduler ===")
scheduler = PostgreSQLScheduler()

# Get content for current date
current_content = scheduler.get_available_content(
    'spots',
    exclude_ids=[],
    schedule_date=now.strftime('%Y-%m-%d')
)
current_holidays = [c for c in current_content if 'holiday' in c['file_name'].lower() and 'greeting' in c['file_name'].lower()]
test_in_current_scheduler = any(c['asset_id'] == test_asset_id for c in current_holidays)

print(f"Through scheduler - test greeting in current date: {test_in_current_scheduler}")
print(f"Total holiday greetings for current date: {len(current_holidays)}")

# Get content for future date
future_content = scheduler.get_available_content(
    'spots',
    exclude_ids=[],
    schedule_date=future_schedule_date
)
future_holidays = [c for c in future_content if 'holiday' in c['file_name'].lower() and 'greeting' in c['file_name'].lower()]
test_in_future_scheduler = any(c['asset_id'] == test_asset_id for c in future_holidays)

print(f"Through scheduler - test greeting in future date: {test_in_future_scheduler}")
print(f"Total holiday greetings for future date: {len(future_holidays)}")

# Clean up - reset the go-live date
print("\n=== Cleanup ===")
cursor.execute("""
    UPDATE scheduling_metadata
    SET go_live_date = NULL
    WHERE asset_id = %s
""", (test_asset_id,))
conn.commit()
print("Reset go-live date to NULL")

cursor.close()
conn.close()

# Summary
print("\n=== SUMMARY ===")
if not test_greeting_in_current and test_greeting_in_future:
    print("✅ SUCCESS: Go-live dates are being honored correctly!")
    print("   - Greeting is NOT available before go-live date")
    print("   - Greeting IS available after go-live date")
else:
    print("❌ FAILURE: Go-live dates are not working correctly")
    print(f"   - Available for current date: {test_greeting_in_current} (should be False)")
    print(f"   - Available for future date: {test_greeting_in_future} (should be True)")