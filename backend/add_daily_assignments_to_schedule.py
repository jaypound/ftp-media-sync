#!/usr/bin/env python3
"""Add daily assignments to an existing schedule"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
from database import db_manager
from datetime import datetime
import pytz
import sys

if len(sys.argv) != 2:
    print("Usage: python add_daily_assignments_to_schedule.py <schedule_id>")
    sys.exit(1)

schedule_id = int(sys.argv[1])

print(f"=== Adding Daily Assignments to Schedule {schedule_id} ===\n")

# Connect to database
db_manager.connect()

# Get schedule details
conn = db_manager._get_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT schedule_name, air_date
    FROM schedules
    WHERE id = %s
""", (schedule_id,))

result = cursor.fetchone()
if not result:
    print(f"Schedule {schedule_id} not found!")
    cursor.close()
    db_manager._put_connection(conn)
    sys.exit(1)

schedule_name = result['schedule_name']
air_date = result['air_date']

print(f"Schedule: {schedule_name}")
print(f"Air date: {air_date}\n")

# Check if it's a weekly schedule
is_weekly = '[WEEKLY]' in schedule_name or 'weekly' in schedule_name.lower()

if is_weekly:
    num_days = 7
    print("Detected as weekly schedule (7 days)")
else:
    num_days = 1
    print("Detected as daily schedule (1 day)")

cursor.close()
db_manager._put_connection(conn)

# Create daily assignments
daily_assignments = HolidayGreetingDailyAssignments(db_manager)

eastern = pytz.timezone('US/Eastern')
start_date = datetime.combine(air_date, datetime.min.time(), tzinfo=eastern)

print(f"\nCreating assignments for {num_days} days starting {start_date.strftime('%Y-%m-%d')}...")

success = daily_assignments.assign_greetings_for_schedule(
    schedule_id,
    start_date,
    num_days=num_days
)

if success:
    print("\n✅ Successfully created daily assignments!")
    
    # Show summary
    all_assignments = daily_assignments.get_all_assignments(schedule_id)
    
    # Group by day
    assignments_by_day = {}
    for assignment in all_assignments:
        day = assignment['day_number']
        if day not in assignments_by_day:
            assignments_by_day[day] = []
        assignments_by_day[day].append(assignment)
    
    print("\n=== Assignment Summary ===")
    for day in sorted(assignments_by_day.keys()):
        day_assignments = assignments_by_day[day]
        print(f"\nDay {day} ({day_assignments[0]['start_date']}):")
        for assignment in day_assignments:
            short_name = assignment['file_name'].replace('251210_SSP_', '').replace('.mp4', '')[:35]
            print(f"  - {short_name}")
else:
    print("\n❌ Failed to create daily assignments")