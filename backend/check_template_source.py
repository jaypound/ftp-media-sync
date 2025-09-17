#!/usr/bin/env python3
"""Check where the template data is coming from"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager

# The template shows "weekly_meetings_week37_2025.sch"
# Week 37 of 2025 would be around September 8-14, 2025

print("Checking template source for weekly_meetings_week37_2025.sch")
print("="*60)

# Calculate week 37 of 2025
from datetime import datetime, timedelta

# January 1, 2025
jan1_2025 = datetime(2025, 1, 1)
# Find the first Monday of 2025
days_until_monday = (7 - jan1_2025.weekday()) % 7
if days_until_monday == 0:
    days_until_monday = 7
first_monday = jan1_2025 + timedelta(days=days_until_monday)

# Week 37 would be 36 weeks after the first Monday
week37_start = first_monday + timedelta(weeks=36)
week37_end = week37_start + timedelta(days=6)

print(f"Week 37 of 2025: {week37_start.date()} to {week37_end.date()}")
print(f"September 18, 2025 is a {datetime(2025, 9, 18).strftime('%A')}")

# Check meetings in that date range
db = PostgreSQLDatabaseManager()
db.connect()

conn = db._get_connection()
try:
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("Checking all meetings for Week 37 (and surrounding days):")
    
    cursor.execute("""
        SELECT 
            id,
            meeting_name,
            meeting_date,
            TO_CHAR(start_time, 'HH12:MI AM') as start_12,
            TO_CHAR(end_time, 'HH12:MI AM') as end_12,
            start_time,
            end_time,
            duration_hours,
            room,
            EXTRACT(DOW FROM meeting_date) as day_of_week
        FROM meetings
        WHERE meeting_date BETWEEN %s AND %s
        ORDER BY meeting_date, start_time
    """, (week37_start.date() - timedelta(days=7), week37_end.date() + timedelta(days=7)))
    
    meetings = cursor.fetchall()
    
    for meeting in meetings:
        day_name = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][int(meeting['day_of_week'])]
        print(f"\nMeeting: {meeting['meeting_name']}")
        print(f"  Date: {meeting['meeting_date']} ({day_name})")
        print(f"  Start: {meeting['start_12']} (raw: {meeting['start_time']})")
        print(f"  End: {meeting['end_12']} (raw: {meeting['end_time']})")
        print(f"  Duration: {meeting['duration_hours']} hours")
        print(f"  Room: {meeting['room']}")
        
        # Check if this is our problem meeting
        if (meeting['start_time'].hour == 18 and meeting['start_time'].minute == 0 and
            meeting['room'] == 'Committee Room 1'):
            print("  *** This matches the template item! ***")
            
            # Check if end time calculation is correct
            from datetime import datetime, date
            base_date = date(2000, 1, 1)
            start_dt = datetime.combine(base_date, meeting['start_time'])
            end_dt = datetime.combine(base_date, meeting['end_time'])
            
            if end_dt < start_dt:
                end_dt = datetime.combine(date(2000, 1, 2), meeting['end_time'])
            
            calc_duration = (end_dt - start_dt).total_seconds() / 3600
            print(f"  Calculated duration: {calc_duration:.2f} hours")
            
            if abs(calc_duration - 4.97) < 0.1:  # ~5 hours
                print("  ERROR: This meeting has the wrong duration!")
                print(f"  End time {meeting['end_12']} gives {calc_duration:.2f} hours instead of expected 3.08")

finally:
    cursor.close()
    db._put_connection(conn)

print("\n" + "="*60)
print("Summary:")
print("The template 'weekly_meetings_week37_2025.sch' should contain meetings from")
print(f"the week of {week37_start.date()} to {week37_end.date()}")
print("The Office of Inspector General meeting on Sept 18 (Thursday) is in this range")