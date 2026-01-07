#!/usr/bin/env python3
"""Simple test to check metadata in schedule items"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
import json
from psycopg2.extras import RealDictCursor

def test_metadata(schedule_id=452):
    """Check metadata for schedule items"""
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
        print(f"Total Duration: {schedule.get('total_duration_seconds')} seconds")
        print("\n" + "="*80 + "\n")
        
        # First check if we have any items
        cursor.execute("SELECT COUNT(*) as count FROM scheduled_items WHERE schedule_id = %s", (schedule_id,))
        count = cursor.fetchone()
        print(f"Total items in schedule: {count['count']}")
        
        # Get items with metadata
        cursor.execute("""
            SELECT 
                si.id,
                si.scheduled_start_time,
                si.metadata,
                si.sequence_number,
                si.asset_id
            FROM scheduled_items si
            WHERE si.schedule_id = %s
            AND si.metadata IS NOT NULL
            ORDER BY si.sequence_number
            LIMIT 10
        """, (schedule_id,))
        
        items = cursor.fetchall()
        print(f"Found {len(items)} items with metadata\n")
        
        for item in items:
            print(f"Sequence #{item['sequence_number']}:")
            print(f"  Asset ID: {item['asset_id']}")
            print(f"  Start Time: {item['scheduled_start_time']}")
            print(f"  Metadata raw: {item['metadata']}")
            print(f"  Metadata type: {type(item['metadata'])}")
            
            if item['metadata']:
                try:
                    if isinstance(item['metadata'], str):
                        metadata_dict = json.loads(item['metadata'])
                    else:
                        metadata_dict = item['metadata']
                    print(f"  Parsed metadata: {metadata_dict}")
                    print(f"  Day offset: {metadata_dict.get('day_offset', 'NOT FOUND')}")
                except Exception as e:
                    print(f"  Error parsing metadata: {e}")
            print()
        
    finally:
        cursor.close()
        db._put_connection(conn)

if __name__ == "__main__":
    schedule_id = int(sys.argv[1]) if len(sys.argv) > 1 else 452
    test_metadata(schedule_id)