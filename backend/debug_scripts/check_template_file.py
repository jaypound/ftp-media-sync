#!/usr/bin/env python3
"""Check what's in the template file for debugging"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Sample template content that would be generated for the meeting
print("Expected template content for Office of Inspector General meeting:")
print("(6:00 PM to 9:05 PM on Thursday)")
print("-" * 60)

template_lines = [
    '{',
    '\titem=/mnt/main/tv/inputs/2-SDI in',
    '\tloop=0',
    '\tguid={a5ef6aeb-7ee9-416e-b3e2-52c105b8370d}',
    '\tstart=thu 06:00:00 pm',
    '\tend=thu 09:05:00 pm',
    '}'
]

for line in template_lines:
    print(line)

print("\n" + "="*60)
print("Testing what end time would produce 4:58 duration:")

# Calculate what end time gives us 4:58
# 6:00 PM + 4:58 = 10:58 PM
print("\nIf start=thu 06:00:00 pm")
print("And duration should be 04:58:00")
print("Then end time would be: thu 10:58:00 pm")

print("\n" + "="*60)
print("Possible causes:")
print("1. The meeting end time in the database might be wrong")
print("2. The template generation might have a bug")  
print("3. The template file might have been manually edited")
print("4. There might be a parsing issue with '9:05 PM' being read as '10:58 PM'")

# Check if '9:05' could be misread as '10:58'
print("\nVisual similarity check:")
print("  9:05 PM  - correct end time")
print("  10:58 PM - what would give 4:58 duration")
print("\nNote: '9:05' and '10:58' are quite different, unlikely to be OCR error")

# But let's check the database query
from database_postgres import PostgreSQLDatabaseManager

db = PostgreSQLDatabaseManager()
db.connect()

conn = db._get_connection()
try:
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("Checking the actual database values for meeting ID 60:")
    
    cursor.execute("""
        SELECT 
            id,
            meeting_name,
            start_time,
            end_time,
            duration_hours,
            room,
            TO_CHAR(start_time, 'HH24:MI:SS') as start_24h,
            TO_CHAR(end_time, 'HH24:MI:SS') as end_24h
        FROM meetings
        WHERE id = 60
    """)
    
    meeting = cursor.fetchone()
    if meeting:
        print(f"Meeting: {meeting['meeting_name']}")
        print(f"  Start time (raw): {meeting['start_time']}")
        print(f"  End time (raw): {meeting['end_time']}")
        print(f"  Start time (24h): {meeting['start_24h']}")
        print(f"  End time (24h): {meeting['end_24h']}")
        print(f"  Duration hours: {meeting['duration_hours']}")
        
        # Calculate what the actual duration should be
        from datetime import datetime
        start = datetime.strptime(meeting['start_24h'], '%H:%M:%S')
        end = datetime.strptime(meeting['end_24h'], '%H:%M:%S') 
        
        # Handle day boundary
        if end < start:
            from datetime import timedelta
            end = end + timedelta(days=1)
            
        duration_seconds = (end - start).total_seconds()
        duration_hours = duration_seconds / 3600
        duration_minutes = duration_seconds / 60
        
        print(f"\n  Calculated duration: {duration_hours:.2f} hours ({duration_minutes:.0f} minutes)")
        print(f"  Expected display: {int(duration_hours):02d}:{int((duration_seconds % 3600) / 60):02d}:{int(duration_seconds % 60):02d}")
        
finally:
    cursor.close()
    db._put_connection(conn)