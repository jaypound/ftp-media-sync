#!/usr/bin/env python3
"""
Test if daily assignments are being created properly
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import DatabaseManager
from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
from datetime import datetime
import logging

logging.basicConfig(level=logging.DEBUG)

def main():
    db_manager = DatabaseManager()
    
    # Check if holiday_greeting_rotation has entries
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM holiday_greeting_rotation")
    rotation_count = cursor.fetchone()[0]
    print(f"Holiday greetings in rotation table: {rotation_count}")
    
    cursor.execute("SELECT COUNT(*) FROM holiday_greetings_days")
    days_count = cursor.fetchone()[0]
    print(f"Existing daily assignments: {days_count}")
    
    if rotation_count == 0:
        print("\nERROR: No holiday greetings in rotation table!")
        print("Run the migration or populate the table first.")
        return
    
    # Test creating daily assignments
    daily_assignments = HolidayGreetingDailyAssignments(db_manager)
    
    # Use a test schedule ID
    test_schedule_id = 99999
    start_date = datetime(2025, 12, 21)  # Sunday
    
    print(f"\nTesting daily assignment creation for schedule {test_schedule_id}...")
    print(f"Start date: {start_date}")
    
    try:
        success = daily_assignments.assign_greetings_for_schedule(
            test_schedule_id, 
            start_date,
            num_days=7
        )
        
        if success:
            print("SUCCESS: Daily assignments created!")
            
            # Check what was created
            cursor.execute("""
                SELECT COUNT(*) 
                FROM holiday_greetings_days 
                WHERE schedule_id = %s
            """, (test_schedule_id,))
            
            new_count = cursor.fetchone()[0]
            print(f"Created {new_count} daily assignments")
            
            # Clean up test data
            cursor.execute("""
                DELETE FROM holiday_greetings_days 
                WHERE schedule_id = %s
            """, (test_schedule_id,))
            conn.commit()
            print("Test data cleaned up")
        else:
            print("FAILED: Daily assignment creation failed")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()