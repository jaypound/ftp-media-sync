#!/usr/bin/env python3
"""Test script to check metadata in schedule items"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
import json

def test_schedule_metadata(schedule_id=452):
    """Check metadata for schedule items"""
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    conn = db._get_connection()
    cursor = conn.cursor()
    
    try:
        # Get schedule info
        cursor.execute("""
            SELECT schedule_name, air_date, total_duration_seconds
            FROM schedules 
            WHERE id = %s
        """, (schedule_id,))
        
        result = cursor.fetchone()
        if not result:
            print(f"Schedule {schedule_id} not found")
            return
        
        # Handle RealDictCursor
        schedule_name = result['schedule_name']
        air_date = result['air_date']
        total_duration = result['total_duration_seconds']
            
        print(f"Schedule: {schedule_name}")
        print(f"Air Date: {air_date}")
        total_duration = float(total_duration or 0)
        print(f"Total Duration: {total_duration / 3600:.1f} hours")
        print(f"Is Weekly: {total_duration > 86400}")
        print("\n" + "="*80 + "\n")
        
        # Get items with AIM Podcast
        cursor.execute("""
            SELECT 
                si.id,
                i.file_name,
                si.scheduled_start_time,
                si.scheduled_duration_seconds,
                si.metadata,
                si.sequence_number
            FROM scheduled_items si
            JOIN assets a ON si.asset_id = a.id
            LEFT JOIN instances i ON si.instance_id = i.id OR (si.instance_id IS NULL AND i.asset_id = si.asset_id AND i.is_primary = true)
            WHERE si.schedule_id = %s
            AND LOWER(i.file_name) LIKE '%aim podcast%'
            ORDER BY si.sequence_number
            LIMIT 10
        """, (schedule_id,))
        
        items = cursor.fetchall()
        print(f"Found {len(items)} items with 'AIM Podcast' in filename\n")
        
        cumulative_seconds = 0
        
        for item in items:
            item_id, filename, start_time, duration, metadata, seq = item
            
            # Calculate day based on cumulative time
            day_offset_calc = int(cumulative_seconds // 86400)
            
            # Check metadata
            metadata_str = "None"
            metadata_day_offset = None
            if metadata:
                try:
                    if isinstance(metadata, str):
                        metadata_dict = json.loads(metadata)
                    else:
                        metadata_dict = metadata
                    metadata_day_offset = metadata_dict.get('day_offset')
                    metadata_str = json.dumps(metadata_dict)
                except:
                    metadata_str = str(metadata)
            
            print(f"Sequence #{seq}:")
            print(f"  File: {filename}")
            print(f"  Start Time: {start_time}")
            print(f"  Duration: {duration}s")
            print(f"  Metadata: {metadata_str}")
            print(f"  Calculated Day Offset: {day_offset_calc}")
            print(f"  Metadata Day Offset: {metadata_day_offset}")
            print()
            
            cumulative_seconds += float(duration or 0)
        
    finally:
        cursor.close()
        db._put_connection(conn)

if __name__ == "__main__":
    import sys
    schedule_id = int(sys.argv[1]) if len(sys.argv) > 1 else 452
    test_schedule_metadata(schedule_id)