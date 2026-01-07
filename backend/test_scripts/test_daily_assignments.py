#!/usr/bin/env python3
"""Test the holiday greeting daily assignment system"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager
from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
from datetime import datetime, timedelta
import pytz

print("=== Testing Holiday Greeting Daily Assignment System ===\n")

# Connect to database
db_manager.connect()

# Create daily assignments instance
daily_assignments = HolidayGreetingDailyAssignments(db_manager)

# Test parameters
eastern = pytz.timezone('US/Eastern')
# Test with Dec 21, 2025 as start date (7 days before most greetings expire)
start_date = datetime(2025, 12, 21, tzinfo=eastern)

# Create a test schedule first
conn = db_manager._get_connection()
cursor = conn.cursor()
cursor.execute("""
    INSERT INTO schedules (schedule_name, air_date, total_duration_seconds)
    VALUES ('Test Daily Assignments', %s, 0)
    RETURNING id
""", (start_date.date(),))
test_schedule_id = cursor.fetchone()['id']
conn.commit()
cursor.close()
db_manager._put_connection(conn)

print(f"Test schedule ID: {test_schedule_id}")
print(f"Start date: {start_date.strftime('%Y-%m-%d')}")
print(f"Number of days: 7\n")

# Assign greetings for the test schedule
print("=== Assigning greetings to days ===")
success = daily_assignments.assign_greetings_for_schedule(
    test_schedule_id,
    start_date,
    num_days=7
)

if success:
    print("✅ Successfully assigned greetings\n")
    
    # Print the assignment summary
    print("=== Assignment Summary ===")
    daily_assignments.print_assignment_summary(test_schedule_id)
    
    # Test retrieving greetings for specific dates
    print("\n=== Testing date lookups ===")
    for day_offset in [0, 2, 4, 6]:
        test_date = start_date + timedelta(days=day_offset)
        greetings = daily_assignments.get_greetings_for_date(test_schedule_id, test_date)
        print(f"\nDay {day_offset + 1} ({test_date.strftime('%Y-%m-%d')}): {len(greetings)} greetings")
        print(f"Asset IDs: {greetings}")
    
    # Check distribution
    print("\n=== Checking Distribution ===")
    all_assignments = daily_assignments.get_all_assignments(test_schedule_id)
    
    # Count how many times each greeting appears
    greeting_counts = {}
    for assignment in all_assignments:
        asset_id = assignment['asset_id']
        file_name = assignment['file_name']
        greeting_counts[file_name] = greeting_counts.get(file_name, 0) + 1
    
    # Sort by count
    sorted_counts = sorted(greeting_counts.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\nTotal assignments: {len(all_assignments)}")
    print(f"Unique greetings: {len(greeting_counts)}")
    print(f"\nTop 5 most assigned:")
    for file_name, count in sorted_counts[:5]:
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:35]
        print(f"  {short_name:35} : {count} times")
    
    print(f"\nBottom 5 least assigned:")
    for file_name, count in sorted_counts[-5:]:
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:35]
        print(f"  {short_name:35} : {count} times")
    
    # Clean up test data
    print("\n=== Cleanup ===")
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM holiday_greetings_days WHERE schedule_id = %s", (test_schedule_id,))
    cursor.execute("DELETE FROM schedules WHERE id = %s", (test_schedule_id,))
    conn.commit()
    cursor.close()
    db_manager._put_connection(conn)
    print("✅ Test data cleaned up")
    
else:
    print("❌ Failed to assign greetings")