#!/usr/bin/env python3
"""Simulate the template generation for meeting ID 60 to find the bug"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
from datetime import datetime, timedelta

# Get the meeting data
db = PostgreSQLDatabaseManager()
db.connect()

conn = db._get_connection()
try:
    cursor = conn.cursor()
    
    # Get meeting ID 60 with all formats
    cursor.execute("""
        SELECT 
            id,
            meeting_name,
            meeting_date,
            start_time,
            end_time,
            duration_hours,
            room,
            TO_CHAR(start_time, 'HH12:MI AM') as start_formatted,
            TO_CHAR(end_time, 'HH12:MI AM') as end_formatted
        FROM meetings
        WHERE id = 60
    """)
    
    meeting_raw = cursor.fetchone()
    
    # Convert to dict format like the endpoint would receive
    meeting = {
        'id': meeting_raw['id'],
        'meeting_name': meeting_raw['meeting_name'],
        'meeting_date': str(meeting_raw['meeting_date']),
        'start_time': meeting_raw['start_formatted'].strip(),
        'end_time': meeting_raw['end_formatted'].strip() if meeting_raw['end_time'] else None,
        'duration_hours': float(meeting_raw['duration_hours']),
        'room': meeting_raw['room']
    }
    
finally:
    cursor.close()
    db._put_connection(conn)

print("Meeting data as it would be passed to template generation:")
print(f"  ID: {meeting['id']}")
print(f"  Name: {meeting['meeting_name']}")
print(f"  Date: {meeting['meeting_date']}")
print(f"  Start: '{meeting['start_time']}'")
print(f"  End: '{meeting['end_time']}'")
print(f"  Duration: {meeting['duration_hours']} hours")
print(f"  Room: {meeting['room']}")

print("\n" + "="*60)
print("Simulating generate_weekly_schedule_template logic:")

# Room to SDI mapping
room_to_sdi = {
    'Council Chambers': '/mnt/main/tv/inputs/1-SDI in',
    'Committee Room 1': '/mnt/main/tv/inputs/2-SDI in',
    'Committee Room 2': '/mnt/main/tv/inputs/3-SDI in'
}

room = meeting.get('room', '')
sdi_input = room_to_sdi.get(room, '/mnt/main/tv/inputs/1-SDI in')

# Parse meeting date to get day of week
meeting_date = datetime.strptime(meeting['meeting_date'], '%Y-%m-%d')
day_name = meeting_date.strftime('%a').lower()  # thu

# Parse start time and end time
start_time = meeting['start_time']
print(f"\nProcessing times:")
print(f"  Original start_time: '{start_time}'")

# Use end_time if available, otherwise calculate from duration
if 'end_time' in meeting and meeting['end_time']:
    end_time = meeting['end_time']
    print(f"  Original end_time: '{end_time}'")
    
    # Ensure time has seconds for precision
    if end_time.count(':') == 1:  # Only HH:MM format
        print(f"  Adding seconds to end_time...")
        # Add seconds for precision
        dt = datetime.strptime(end_time, '%I:%M %p')
        end_time = dt.strftime('%I:%M:%S %p')
        print(f"  New end_time: '{end_time}'")
else:
    # Fallback to calculating from duration for backward compatibility
    duration_hours = meeting.get('duration_hours', 2.0)
    start_dt = datetime.strptime(start_time, '%I:%M %p')
    end_dt = start_dt + timedelta(hours=duration_hours)
    end_time = end_dt.strftime('%I:%M:%S %p')
    print(f"  Calculated end_time from duration: '{end_time}'")

# Ensure start time also has seconds
if start_time.count(':') == 1:  # Only HH:MM format
    print(f"  Adding seconds to start_time...")
    dt = datetime.strptime(start_time, '%I:%M %p')
    start_time = dt.strftime('%I:%M:%S %p')
    print(f"  New start_time: '{start_time}'")

start_time_lower = start_time.lower()
end_time_lower = end_time.lower()

print(f"\nFinal template values:")
print(f"  start={day_name} {start_time_lower}")
print(f"  end={day_name} {end_time_lower}")

# Now calculate what duration this would give
print("\n" + "="*60)
print("Verifying duration calculation:")
from app import calculate_duration_from_times

duration_seconds = calculate_duration_from_times(f"{day_name} {start_time_lower}", f"{day_name} {end_time_lower}")
duration_hours = duration_seconds / 3600
duration_minutes = duration_seconds / 60

print(f"  Duration: {duration_seconds} seconds")
print(f"  Duration: {duration_minutes:.0f} minutes") 
print(f"  Duration: {duration_hours:.2f} hours")
print(f"  Display: {int(duration_hours):02d}:{int((duration_seconds % 3600) / 60):02d}:{int(duration_seconds % 60):02d}")

if abs(duration_hours - 4.97) < 0.1:
    print("\n*** ERROR: This produces the wrong duration! ***")
    print(f"Expected ~3.08 hours but got {duration_hours:.2f} hours")
else:
    print("\n✓ Duration calculation is correct")