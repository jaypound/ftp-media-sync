#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import DatabaseManager
from psycopg2.extras import RealDictCursor

def main():
    db_manager = DatabaseManager()
    conn = db_manager._get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=== Checking Holiday Greeting Availability ===\n")
    
    # Check holiday greetings in assets table
    cursor.execute("""
        SELECT a.id, a.file_name, a.content_title, 
               sm.available_for_scheduling,
               sm.go_live_date,
               sm.content_expiry_date
        FROM assets a
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.file_name LIKE '%Holiday Greeting%'
        ORDER BY a.file_name
        LIMIT 20
    """)
    
    greetings = cursor.fetchall()
    print(f"Found {len(greetings)} holiday greetings:\n")
    
    for g in greetings:
        print(f"ID: {g['id']}")
        print(f"File: {g['file_name']}")
        print(f"Available for scheduling: {g['available_for_scheduling']}")
        print(f"Go live date: {g['go_live_date']}")
        print(f"Expiry date: {g['content_expiry_date']}")
        print("-" * 50)
    
    # Check if they're in the holiday_greeting_rotation table
    print("\n=== Holiday Greeting Rotation Table ===\n")
    cursor.execute("""
        SELECT COUNT(*) as count FROM holiday_greeting_rotation
    """)
    count = cursor.fetchone()
    print(f"Total entries in holiday_greeting_rotation: {count['count']}")
    
    # Check daily assignments for the latest schedule
    print("\n=== Daily Assignments ===\n")
    cursor.execute("""
        SELECT schedule_id, COUNT(*) as count 
        FROM holiday_greetings_days 
        GROUP BY schedule_id 
        ORDER BY schedule_id DESC 
        LIMIT 5
    """)
    assignments = cursor.fetchall()
    
    if assignments:
        print("Recent daily assignment counts by schedule:")
        for a in assignments:
            print(f"  Schedule {a['schedule_id']}: {a['count']} assignments")
    else:
        print("No daily assignments found!")
    
    conn.close()

if __name__ == "__main__":
    main()