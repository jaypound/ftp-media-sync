#!/usr/bin/env python3
"""Check schedule duration"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
from psycopg2.extras import RealDictCursor

def check_schedule_duration(schedule_id=452):
    """Check schedule duration"""
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    conn = db._get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get schedule info
        cursor.execute("SELECT * FROM schedules WHERE id = %s", (schedule_id,))
        schedule = cursor.fetchone()
        
        if not schedule:
            print(f"Schedule {schedule_id} not found")
            return
        
        print(f"Schedule: {schedule.get('schedule_name')}")
        print(f"Air Date: {schedule.get('air_date')}")
        print(f"Total Duration Seconds: {schedule.get('total_duration_seconds')}")
        print(f"Total Duration Hours: {schedule.get('total_duration_hours')}")
        
        # Calculate actual duration from items
        cursor.execute("""
            SELECT SUM(scheduled_duration_seconds) as total
            FROM scheduled_items
            WHERE schedule_id = %s
        """, (schedule_id,))
        
        result = cursor.fetchone()
        actual_total = result['total'] if result else 0
        
        print(f"\nActual total from items: {actual_total} seconds")
        print(f"That's {actual_total/3600:.1f} hours")
        print(f"That's {actual_total/86400:.1f} days")
        
        # Update the schedule if needed
        if actual_total and actual_total != schedule.get('total_duration_seconds'):
            print("\nUpdating schedule with correct duration...")
            cursor.execute("""
                UPDATE schedules
                SET total_duration_seconds = %s
                WHERE id = %s
            """, (actual_total, schedule_id))
            conn.commit()
            print("Updated!")
        
    finally:
        cursor.close()
        db._put_connection(conn)

if __name__ == "__main__":
    schedule_id = int(sys.argv[1]) if len(sys.argv) > 1 else 452
    check_schedule_duration(schedule_id)