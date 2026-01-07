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
        # First check table structure
        print("=== SCHEDULES TABLE COLUMNS ===")
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'schedules'
            ORDER BY ordinal_position;
        """)
        cols = cursor.fetchall()
        for col in cols:
            print(f"  {col['column_name']} ({col['data_type']})")
        
        print("\n=== HOLIDAY GREETINGS DAYS (Recent 20) ===")
        cursor.execute("""
            SELECT hgd.*
            FROM holiday_greetings_days hgd
            ORDER BY hgd.schedule_day DESC
            LIMIT 20;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                print(f"Day: {row['schedule_day']}, Schedule ID: {row['schedule_id']}, "
                      f"Package: {row['package_id']}, Created: {row.get('created_at', 'N/A')}")
        else:
            print("No rows found in holiday_greetings_days table")
        
        print("\n=== RECENT SCHEDULES (Last 30 minutes) ===")
        cursor.execute("""
            SELECT *
            FROM schedules 
            WHERE created_at > NOW() - INTERVAL '30 minutes'
            ORDER BY created_at DESC;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                # Print all available fields
                print(f"ID: {row['id']}, Created: {row['created_at']}")
                for key, value in row.items():
                    if key not in ['id', 'created_at']:
                        print(f"  {key}: {value}")
        else:
            print("No schedules created in the last 30 minutes")
        
        print("\n=== ALL SCHEDULES (Last 24 hours) ===")
        cursor.execute("""
            SELECT *
            FROM schedules 
            WHERE created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 20;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                print(f"ID: {row['id']}, Created: {row['created_at']}")
                # Look for any name-like field
                for key in ['title', 'description', 'schedule_type', 'name']:
                    if key in row:
                        print(f"  {key}: {row[key]}")
        else:
            print("No schedules created in the last 24 hours")
        
        print("\n=== HOLIDAY GREETINGS DAYS COUNT BY SCHEDULE ===")
        cursor.execute("""
            SELECT s.id, s.created_at, COUNT(hgd.id) as assignment_count
            FROM schedules s
            LEFT JOIN holiday_greetings_days hgd ON s.id = hgd.schedule_id
            WHERE s.created_at > NOW() - INTERVAL '24 hours'
            GROUP BY s.id, s.created_at
            ORDER BY s.created_at DESC;
        """)
        
        results = cursor.fetchall()
        if results:
            for row in results:
                print(f"Schedule ID: {row['id']}, "
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