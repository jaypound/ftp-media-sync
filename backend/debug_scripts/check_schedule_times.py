#!/usr/bin/env python3
"""Check the actual scheduled_start_time values in the database"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import db_manager
from psycopg2.extras import RealDictCursor

def check_schedule_times(schedule_id):
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get a sample of items with their times and metadata
        cursor.execute("""
            SELECT 
                scheduled_start_time,
                EXTRACT(EPOCH FROM scheduled_start_time) as start_seconds,
                metadata,
                a.content_title
            FROM scheduled_items si
            LEFT JOIN assets a ON si.asset_id = a.id
            WHERE schedule_id = %s
            ORDER BY scheduled_start_time
            LIMIT 50
        """, (schedule_id,))
        
        items = cursor.fetchall()
        
        print(f"Sample scheduled items from schedule {schedule_id}:")
        print("-" * 80)
        
        for i, item in enumerate(items):
            start_time = item['scheduled_start_time']
            start_seconds = item['start_seconds']
            metadata = item['metadata']
            title = item['content_title'] or 'Unknown'
            
            # Calculate hours and minutes from start_seconds
            total_hours = int(start_seconds // 3600)
            minutes = int((start_seconds % 3600) // 60)
            seconds = int(start_seconds % 60)
            
            print(f"{i+1:3d}. Time: {start_time} | Hours: {total_hours:3d}:{minutes:02d}:{seconds:02d} | Metadata: {metadata}")
            print(f"     Title: {title[:50]}")
            print()
        
        cursor.close()
        
    finally:
        db_manager._put_connection(conn)

if __name__ == '__main__':
    db_manager.connect()
    try:
        check_schedule_times(459)
    finally:
        db_manager.disconnect()