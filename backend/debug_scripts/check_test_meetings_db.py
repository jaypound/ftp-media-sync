#!/usr/bin/env python3
"""Check how the test meetings are stored in the database"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager

db = PostgreSQLDatabaseManager()
db.connect()

conn = db._get_connection()
try:
    cursor = conn.cursor()
    
    print("Checking test meetings in database:")
    print("="*80)
    
    cursor.execute("""
        SELECT 
            id,
            meeting_name,
            meeting_date,
            start_time,
            end_time,
            duration_hours,
            room,
            TO_CHAR(start_time, 'HH24:MI:SS') as start_24h,
            TO_CHAR(end_time, 'HH24:MI:SS') as end_24h,
            TO_CHAR(start_time, 'HH12:MI AM') as start_12h,
            TO_CHAR(end_time, 'HH12:MI AM') as end_12h
        FROM meetings
        WHERE meeting_name IN ('TEST1', 'TEST2', 'TEST3', 'Office of Inspector General')
        ORDER BY meeting_name
    """)
    
    meetings = cursor.fetchall()
    
    for meeting in meetings:
        print(f"\nMeeting: {meeting['meeting_name']}")
        print(f"  Date: {meeting['meeting_date']}")
        print(f"  Room: {meeting['room']}")
        print(f"  Start time (raw): {meeting['start_time']} (type: {type(meeting['start_time'])})")
        print(f"  End time (raw): {meeting['end_time']} (type: {type(meeting['end_time'])})")
        print(f"  Start (24h): {meeting['start_24h']}")
        print(f"  End (24h): {meeting['end_24h']}")
        print(f"  Start (12h): {meeting['start_12h']}")
        print(f"  End (12h): {meeting['end_12h']}")
        print(f"  Duration hours: {meeting['duration_hours']}")
        
        # Calculate expected duration
        from datetime import datetime, date
        base_date = date(2000, 1, 1)
        start_dt = datetime.combine(base_date, meeting['start_time'])
        end_dt = datetime.combine(base_date, meeting['end_time'])
        
        # Handle day boundary
        if end_dt < start_dt:
            end_dt = datetime.combine(date(2000, 1, 2), meeting['end_time'])
        
        calc_duration_hours = (end_dt - start_dt).total_seconds() / 3600
        calc_duration_minutes = (end_dt - start_dt).total_seconds() / 60
        
        print(f"  Calculated duration: {calc_duration_hours:.2f} hours ({calc_duration_minutes:.0f} minutes)")
        
        if abs(calc_duration_hours - float(meeting['duration_hours'])) > 0.01:
            print(f"  *** DURATION MISMATCH: Stored={meeting['duration_hours']}, Calculated={calc_duration_hours:.3f}")

finally:
    cursor.close()
    db._put_connection(conn)