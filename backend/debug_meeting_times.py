#!/usr/bin/env python3
"""Debug meeting times to find why 6PM-9:05PM shows as 4:58 duration"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
from datetime import datetime

# Initialize database connection
db_manager = PostgreSQLDatabaseManager()
db_manager.connect()

# Get connection from pool
conn = db_manager._get_connection()
try:
    cursor = conn.cursor()
    
    # First, check if end_time column exists
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'meetings' 
        ORDER BY ordinal_position
    """)
    print("Meetings table columns:")
    for col in cursor.fetchall():
        print(f"  - {col['column_name']}: {col['data_type']}")
    print()
    
    # Check if end_time column exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'meetings' AND column_name = 'end_time'
        )
    """)
    has_end_time = cursor.fetchone()['exists']
    
    # Get meetings based on whether end_time exists
    if has_end_time:
        cursor.execute("""
            SELECT 
                id,
                meeting_name, 
                meeting_date,
                start_time,
                end_time,
                duration_hours,
                room
            FROM meetings
            WHERE 
                meeting_name LIKE '%Inspector General%'
                OR meeting_name LIKE '%Committee%'
                OR EXTRACT(DOW FROM meeting_date) = 4  -- Thursday
            ORDER BY meeting_date DESC, start_time DESC
            LIMIT 10
        """)
    else:
        cursor.execute("""
            SELECT 
                id,
                meeting_name, 
                meeting_date,
                start_time,
                NULL as end_time,
                duration_hours,
                room
            FROM meetings
            WHERE 
                meeting_name LIKE '%Inspector General%'
                OR meeting_name LIKE '%Committee%'
                OR EXTRACT(DOW FROM meeting_date) = 4  -- Thursday
            ORDER BY meeting_date DESC, start_time DESC
            LIMIT 10
        """)
    
    meetings = cursor.fetchall()
    
    print("Recent meetings:")
    for meeting in meetings:
        print(f"\nMeeting ID: {meeting['id']}")
        print(f"  Name: {meeting['meeting_name']}")
        print(f"  Date: {meeting['meeting_date']}")
        print(f"  Start: {meeting['start_time']}")
        print(f"  End: {meeting.get('end_time', 'N/A')}")
        print(f"  Duration (hours): {meeting['duration_hours']}")
        print(f"  Room: {meeting['room']}")
        
        # Calculate what the duration should be
        if meeting.get('end_time'):
            try:
                # Parse times
                start_str = meeting['start_time']
                end_str = meeting['end_time']
                
                # Parse start time
                start_dt = datetime.strptime(start_str, '%I:%M %p')
                
                # Try different formats for end time
                end_formats = ['%I:%M %p', '%I:%M:%S %p', '%H:%M:%S']
                end_dt = None
                for fmt in end_formats:
                    try:
                        end_dt = datetime.strptime(end_str, fmt)
                        break
                    except:
                        continue
                
                if end_dt:
                    # Handle day boundary
                    if end_dt < start_dt:
                        end_dt = end_dt.replace(day=end_dt.day + 1)
                    
                    actual_duration = (end_dt - start_dt).total_seconds() / 3600
                    print(f"  Calculated duration: {actual_duration:.2f} hours ({actual_duration*60:.0f} minutes)")
                    
                    if abs(actual_duration - (meeting['duration_hours'] or 0)) > 0.1:
                        print(f"  WARNING: Duration mismatch! Stored: {meeting['duration_hours']:.2f}h, Calculated: {actual_duration:.2f}h")
            except Exception as e:
                print(f"  Error calculating duration: {e}")

    # Now check for any meetings with ~4.97 hour durations
    print("\n" + "="*60)
    print("Looking for meetings with ~5 hour durations:")
    cursor.execute("""
        SELECT 
            id,
            meeting_name,
            meeting_date,
            start_time,
            duration_hours,
            room
        FROM meetings
        WHERE duration_hours BETWEEN 4.9 AND 5.1
        ORDER BY meeting_date DESC
        LIMIT 10
    """)
    
    long_meetings = cursor.fetchall()
    for meeting in long_meetings:
        print(f"\nMeeting: {meeting['meeting_name']}")
        print(f"  Date: {meeting['meeting_date']}, Start: {meeting['start_time']}")
        print(f"  Duration: {meeting['duration_hours']:.2f} hours ({meeting['duration_hours']*60:.0f} minutes)")
        print(f"  Room: {meeting['room']}")
        
finally:
    cursor.close()
    db_manager._put_connection(conn)