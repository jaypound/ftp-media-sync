#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import DatabaseManager
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def main():
    db_manager = DatabaseManager()
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    
    # Get latest schedule
    cursor.execute('SELECT id, schedule_date FROM schedules ORDER BY id DESC LIMIT 1')
    schedule = cursor.fetchone()
    if not schedule:
        print("No schedules found")
        return
        
    schedule_id, schedule_date = schedule
    print(f"\nLatest schedule: ID={schedule_id}, Date={schedule_date}")
    
    # Check if daily assignments exist
    cursor.execute('SELECT COUNT(*) FROM holiday_greetings_days WHERE schedule_id = %s', (schedule_id,))
    count = cursor.fetchone()[0]
    print(f"Daily assignments for this schedule: {count}")
    
    if count > 0:
        # Show some assignments
        cursor.execute('''
            SELECT schedule_date, asset_id, file_name, duration_category 
            FROM holiday_greetings_days 
            WHERE schedule_id = %s 
            ORDER BY schedule_date, duration_category 
            LIMIT 20
        ''', (schedule_id,))
        
        print("\nFirst 20 daily assignments:")
        for row in cursor.fetchall():
            print(f"  {row[0]} [{row[3]}]: {row[1]} - {row[2]}")
    
    # Check if holiday greeting is enabled
    cursor.execute("SELECT value FROM config WHERE key = 'holiday_greeting_enabled'")
    enabled = cursor.fetchone()
    print(f"\nHoliday greeting enabled in config: {enabled[0] if enabled else 'Not found'}")
    
    # Check actual scheduled holiday greetings
    cursor.execute('''
        SELECT COUNT(*) 
        FROM schedule_items si
        JOIN assets a ON si.asset_id = a.id
        WHERE si.schedule_id = %s
        AND a.file_name LIKE '%Holiday Greeting%'
    ''', (schedule_id,))
    actual_count = cursor.fetchone()[0]
    print(f"\nActual holiday greetings in schedule: {actual_count}")
    
    conn.close()

if __name__ == "__main__":
    main()