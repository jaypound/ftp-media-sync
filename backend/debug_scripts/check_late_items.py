#!/usr/bin/env python3
"""Check for items later in the schedule"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
import json
from psycopg2.extras import RealDictCursor

def check_late_items(schedule_id=452):
    """Check metadata for items later in schedule"""
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    conn = db._get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get items with higher sequence numbers
        cursor.execute("""
            SELECT 
                si.id,
                si.scheduled_start_time,
                si.scheduled_duration_seconds,
                si.metadata,
                si.sequence_number,
                i.file_name
            FROM scheduled_items si
            JOIN instances i ON i.asset_id = si.asset_id AND i.is_primary = true
            WHERE si.schedule_id = %s
            AND si.sequence_number > 200
            ORDER BY si.sequence_number
            LIMIT 20
        """, (schedule_id,))
        
        items = cursor.fetchall()
        print(f"Checking {len(items)} items with sequence > 200\n")
        
        cumulative_seconds = 0
        # Calculate cumulative time for first 200 items
        cursor.execute("""
            SELECT SUM(scheduled_duration_seconds) as total
            FROM scheduled_items
            WHERE schedule_id = %s
            AND sequence_number < 201
        """, (schedule_id,))
        
        result = cursor.fetchone()
        if result and result['total']:
            cumulative_seconds = float(result['total'])
        
        print(f"Cumulative seconds for first 200 items: {cumulative_seconds} ({cumulative_seconds/3600:.1f} hours)")
        print(f"Expected day: {int(cumulative_seconds/86400)}")
        print("\n" + "="*80 + "\n")
        
        for item in items:
            duration = float(item['scheduled_duration_seconds'] or 0)
            expected_day = int(cumulative_seconds / 86400)
            
            metadata = item.get('metadata', {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            
            print(f"Sequence #{item['sequence_number']}:")
            print(f"  File: {item['file_name']}")
            print(f"  Start Time: {item['scheduled_start_time']}")
            print(f"  Duration: {duration}s")
            print(f"  Cumulative time: {cumulative_seconds}s ({cumulative_seconds/3600:.1f}h)")
            print(f"  Expected day: {expected_day}")
            print(f"  Metadata: {metadata}")
            print(f"  Actual day_offset: {metadata.get('day_offset', 'NONE')}")
            print()
            
            cumulative_seconds += duration
        
    finally:
        cursor.close()
        db._put_connection(conn)

if __name__ == "__main__":
    schedule_id = int(sys.argv[1]) if len(sys.argv) > 1 else 452
    check_late_items(schedule_id)