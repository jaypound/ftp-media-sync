#!/usr/bin/env python3
"""Simple check for holiday greetings daily assignments"""
import os
import sys
import getpass
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

# Connection string
default_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
connection_string = os.getenv('DATABASE_URL', default_conn)

try:
    conn = psycopg2.connect(connection_string)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        print("=== HOLIDAY GREETINGS DAYS (Recent 20) ===")
        cursor.execute("""
            SELECT hgd.*, s.name as schedule_name
            FROM holiday_greetings_days hgd
            LEFT JOIN schedules s ON hgd.schedule_id = s.id
            ORDER BY hgd.schedule_day DESC
            LIMIT 20;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                print(f"Day: {row['schedule_day']}, Schedule: {row['schedule_name']} (ID: {row['schedule_id']}), "
                      f"Package: {row['package_id']}")
        else:
            print("No rows found in holiday_greetings_days table")
        
        print("\n=== RECENT SCHEDULES (Last 30 minutes) ===")
        cursor.execute("""
            SELECT id, name, created_at, schedule_type, start_date, end_date
            FROM schedules 
            WHERE created_at > NOW() - INTERVAL '30 minutes'
            ORDER BY created_at DESC;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                print(f"ID: {row['id']}, Name: {row['name']}, Type: {row['schedule_type']}, "
                      f"Start: {row['start_date']}, End: {row['end_date']}, Created: {row['created_at']}")
        else:
            print("No schedules created in the last 30 minutes")
        
        print("\n=== ALL SCHEDULES (Last 24 hours) ===")
        cursor.execute("""
            SELECT id, name, created_at, schedule_type, start_date, end_date
            FROM schedules 
            WHERE created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 20;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                print(f"ID: {row['id']}, Name: {row['name']}, Type: {row['schedule_type']}, "
                      f"Start: {row['start_date']}, End: {row['end_date']}, Created: {row['created_at']}")
        else:
            print("No schedules created in the last 24 hours")
        
        print("\n=== HOLIDAY GREETINGS DAYS COUNT BY SCHEDULE ===")
        cursor.execute("""
            SELECT s.id, s.name, s.created_at, COUNT(hgd.id) as assignment_count
            FROM schedules s
            LEFT JOIN holiday_greetings_days hgd ON s.id = hgd.schedule_id
            WHERE s.created_at > NOW() - INTERVAL '24 hours'
            GROUP BY s.id, s.name, s.created_at
            ORDER BY s.created_at DESC;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                print(f"Schedule ID: {row['id']}, Name: {row['name']}, "
                      f"Assignments: {row['assignment_count']}, Created: {row['created_at']}")
        else:
            print("No schedule assignment counts found")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    if 'conn' in locals() and conn:
        conn.close()