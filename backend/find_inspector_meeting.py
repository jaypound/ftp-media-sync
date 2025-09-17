#!/usr/bin/env python3
"""Find the specific Office of Inspector General meeting"""

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
    
    print("Looking for Office of Inspector General meeting:")
    cursor.execute("""
        SELECT 
            id,
            meeting_name, 
            meeting_date,
            start_time,
            end_time,
            duration_hours,
            room,
            created_at
        FROM meetings
        WHERE 
            meeting_name LIKE '%Office of Inspector General%'
            OR meeting_name LIKE '%Inspector%General%'
        ORDER BY created_at DESC
        LIMIT 20
    """)
    
    meetings = cursor.fetchall()
    
    if not meetings:
        print("No Inspector General meetings found. Let's check all meetings on Sept 18, 2025:")
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
            WHERE meeting_date = '2025-09-18'
            ORDER BY start_time
        """)
        meetings = cursor.fetchall()
    
    print(f"\nFound {len(meetings)} meetings:")
    for meeting in meetings:
        print(f"\nMeeting ID: {meeting['id']}")
        print(f"  Name: {meeting['meeting_name']}")
        print(f"  Date: {meeting['meeting_date']}")
        print(f"  Start: {meeting['start_time']} (type: {type(meeting['start_time'])})")
        print(f"  End: {meeting.get('end_time', 'N/A')} (type: {type(meeting.get('end_time'))})")
        print(f"  Duration (hours): {meeting['duration_hours']}")
        print(f"  Room: {meeting['room']}")
        
        # If we have both times as time objects, calculate duration
        if meeting.get('end_time') and meeting['start_time']:
            try:
                start_time = meeting['start_time']
                end_time = meeting['end_time']
                
                # Convert time objects to datetime for calculation
                from datetime import datetime, date
                base_date = date(2000, 1, 1)
                start_dt = datetime.combine(base_date, start_time)
                end_dt = datetime.combine(base_date, end_time)
                
                # Handle day boundary
                if end_dt < start_dt:
                    end_dt = datetime.combine(date(2000, 1, 2), end_time)
                
                actual_duration_hours = (end_dt - start_dt).total_seconds() / 3600
                actual_duration_minutes = (end_dt - start_dt).total_seconds() / 60
                
                print(f"  Calculated duration: {actual_duration_hours:.2f} hours ({actual_duration_minutes:.0f} minutes)")
                
                if abs(actual_duration_hours - float(meeting['duration_hours'])) > 0.1:
                    print(f"  WARNING: Duration mismatch!")
                    print(f"    Stored: {meeting['duration_hours']} hours")
                    print(f"    Calculated: {actual_duration_hours:.2f} hours")
                    
                # Check if this could be our problem meeting (6pm start, ~5 hour duration)
                if start_time.hour == 18 and 4.9 < float(meeting['duration_hours']) < 5.1:
                    print("\n  *** POSSIBLE PROBLEM MEETING ***")
                    print(f"  This meeting starts at 6PM and has ~5 hour duration")
                    
            except Exception as e:
                print(f"  Error calculating duration: {e}")
    
    # Also search for meetings with Committee Room 1 on Thursday
    print("\n" + "="*60)
    print("Searching for Committee Room 1 meetings on Thursdays with long durations:")
    cursor.execute("""
        SELECT 
            id,
            meeting_name,
            meeting_date,
            start_time,
            end_time,
            duration_hours,
            room,
            EXTRACT(DOW FROM meeting_date) as day_of_week
        FROM meetings
        WHERE 
            room LIKE '%Committee Room 1%'
            AND EXTRACT(DOW FROM meeting_date) = 4  -- Thursday
            AND start_time::time = '18:00:00'  -- 6 PM
        ORDER BY meeting_date DESC
        LIMIT 10
    """)
    
    committee_meetings = cursor.fetchall()
    for meeting in committee_meetings:
        print(f"\nMeeting: {meeting['meeting_name']}")
        print(f"  Date: {meeting['meeting_date']} (Thursday)")
        print(f"  Start: {meeting['start_time']}")
        print(f"  End: {meeting.get('end_time', 'N/A')}")
        print(f"  Duration: {meeting['duration_hours']} hours")
        
finally:
    cursor.close()
    db_manager._put_connection(conn)