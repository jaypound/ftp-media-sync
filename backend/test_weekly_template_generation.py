#!/usr/bin/env python3
"""Test the weekly template generation to debug the issue"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager

# Initialize database
db = PostgreSQLDatabaseManager()
db.connect()

# Get test meetings
test_meeting_names = ['TEST1', 'TEST2', 'TEST3', 'Office of Inspector General']

conn = db._get_connection()
try:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM meetings 
        WHERE meeting_name IN %s
        ORDER BY meeting_name
    """, (tuple(test_meeting_names),))
    
    meeting_ids = [row['id'] for row in cursor.fetchall()]
    cursor.close()
finally:
    db._put_connection(conn)

print(f"Found meeting IDs: {meeting_ids}")

# Now test get_meetings_by_ids
meetings = db.get_meetings_by_ids(meeting_ids)

print("\nMeetings returned by get_meetings_by_ids:")
print("="*80)

for meeting in meetings:
    print(f"\nMeeting: {meeting['meeting_name']}")
    print(f"  ID: {meeting['id']}")
    print(f"  Date: {meeting['meeting_date']}")
    print(f"  Start time: '{meeting['start_time']}' (type: {type(meeting['start_time'])})")
    print(f"  End time: '{meeting.get('end_time', 'MISSING')}' (type: {type(meeting.get('end_time', 'N/A'))})")
    print(f"  Duration hours: {meeting['duration_hours']}")
    print(f"  Room: {meeting['room']}")
    
    # Check what happens with the template generation logic
    start_time = meeting['start_time']
    end_time = meeting.get('end_time', '')
    
    print(f"\n  Template generation test:")
    print(f"    start_time: '{start_time}'")
    print(f"    end_time: '{end_time}'")
    
    if end_time:
        try:
            # This is what the template generation code does
            if hasattr(end_time, 'count'):
                count_result = end_time.count(':')
                print(f"    end_time.count(':'): {count_result}")
            else:
                print(f"    end_time doesn't have count method")
        except Exception as e:
            print(f"    Error checking count: {e}")

print("\n" + "="*80)
print("Testing what the template generation code sees:")

# Simulate the template generation endpoint
from datetime import datetime, timedelta

for meeting in meetings:
    print(f"\nProcessing {meeting['meeting_name']}:")
    
    meeting_date = datetime.strptime(meeting['meeting_date'], '%Y-%m-%d')
    day_name = meeting_date.strftime('%a').lower()
    
    start_time = meeting['start_time']
    
    # This is the problematic code from app.py
    if 'end_time' in meeting and meeting['end_time']:
        end_time = meeting['end_time']
        print(f"  Has end_time: '{end_time}'")
        
        # The bug is here - it tries to count colons
        try:
            if end_time.count(':') == 1:  # Only HH:MM format
                print(f"  Would add seconds to end_time")
                dt = datetime.strptime(end_time, '%I:%M %p')
                end_time = dt.strftime('%I:%M:%S %p')
            else:
                print(f"  End time already has seconds (or error occurred)")
        except AttributeError as e:
            print(f"  ERROR: {e}")
            print(f"  This is causing the bug!")
    else:
        print(f"  No end_time, would calculate from duration")