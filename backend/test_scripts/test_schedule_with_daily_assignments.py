#!/usr/bin/env python3
"""Test creating a schedule with daily assignments"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from scheduler_postgres import PostgreSQLScheduler
from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
from database import db_manager
from datetime import datetime
import pytz

print("=== Testing Schedule Creation with Daily Assignments ===\n")

# Connect to database
db_manager.connect()

# Create scheduler instance
scheduler = PostgreSQLScheduler()

# Check if holiday integration is enabled
if hasattr(scheduler, 'holiday_integration') and scheduler.holiday_integration:
    print(f"Holiday integration enabled: {scheduler.holiday_integration.enabled}")
else:
    print("Holiday integration not found!")

# Create a test weekly schedule for a test date
eastern = pytz.timezone('US/Eastern')
start_date = "2026-03-01"  # Use a future date for testing

print(f"\nCreating weekly schedule for {start_date}...")

# Create the schedule
result = scheduler.create_weekly_schedule(start_date)

if result['success']:
    schedule_id = result['schedule_id']
    print(f"✅ Schedule created successfully! ID: {schedule_id}")
    
    # Check if daily assignments were created
    daily_assignments = HolidayGreetingDailyAssignments(db_manager)
    all_assignments = daily_assignments.get_all_assignments(schedule_id)
    
    print(f"\nDaily assignments created: {len(all_assignments)} total")
    
    # Group by day
    assignments_by_day = {}
    for assignment in all_assignments:
        day = assignment['day_number']
        if day not in assignments_by_day:
            assignments_by_day[day] = []
        assignments_by_day[day].append(assignment)
    
    # Show summary
    print("\n=== Daily Assignment Summary ===")
    for day in sorted(assignments_by_day.keys()):
        day_assignments = assignments_by_day[day]
        print(f"\nDay {day} ({day_assignments[0]['start_date']}):")
        for assignment in day_assignments:
            short_name = assignment['file_name'].replace('251210_SSP_', '').replace('.mp4', '')[:35]
            print(f"  - {short_name}")
    
    # Export the schedule to check what was actually scheduled
    print("\n\nExporting holiday greetings from schedule...")
    
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            i.file_name,
            TO_CHAR(s.air_date + si.scheduled_start_time, 'Day') as day_name,
            s.air_date + si.scheduled_start_time as full_datetime
        FROM scheduled_items si
        JOIN schedules s ON si.schedule_id = s.id
        JOIN instances i ON si.instance_id = i.id
        WHERE si.schedule_id = %s
        AND i.file_name ILIKE '%%holiday%%greeting%%'
        ORDER BY si.sequence_number
        LIMIT 30
    """, (schedule_id,))
    
    results = cursor.fetchall()
    print(f"\nFound {cursor.rowcount} holiday greetings in the actual schedule (showing first 30):")
    
    current_day = None
    for row in results:
        file_name = row['file_name']
        day_name = row['day_name'].strip()
        datetime_val = row['full_datetime']
        
        if day_name != current_day:
            current_day = day_name
            print(f"\n{day_name}:")
        
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:35]
        print(f"  {datetime_val.strftime('%H:%M')} - {short_name}")
    
    cursor.close()
    db_manager._put_connection(conn)
    
    # Clean up test schedule
    print("\n\n=== Cleanup ===")
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM holiday_greetings_days WHERE schedule_id = %s", (schedule_id,))
    cursor.execute("DELETE FROM scheduled_items WHERE schedule_id = %s", (schedule_id,))
    cursor.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))
    conn.commit()
    cursor.close()
    db_manager._put_connection(conn)
    print("✅ Test schedule cleaned up")
    
else:
    print(f"❌ Failed to create schedule: {result['message']}")