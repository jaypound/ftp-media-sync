#!/usr/bin/env python3
"""Check AIM Podcast items throughout the week"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
import json
def check_aim_podcast(schedule_id=452):
    """Check AIM Podcast items with different day offsets"""
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    conn = db._get_connection()
    cursor = conn.cursor()
    
    try:
        # Get AIM Podcast items - use subquery to avoid join issues
        cursor.execute("""
            SELECT 
                si.id,
                si.scheduled_start_time,
                si.scheduled_duration_seconds,
                si.metadata,
                si.sequence_number,
                (SELECT file_name FROM instances WHERE asset_id = si.asset_id AND is_primary = true LIMIT 1) as file_name
            FROM scheduled_items si
            WHERE si.schedule_id = %s
            AND EXISTS (
                SELECT 1 FROM instances i 
                WHERE i.asset_id = si.asset_id 
                AND i.is_primary = true 
                AND LOWER(i.file_name) LIKE '%aim podcast%'
            )
            ORDER BY si.sequence_number
        """, (schedule_id,))
        
        items = cursor.fetchall()
        print(f"Found {len(items)} AIM Podcast items\n")
        
        # Group by day_offset
        by_day = {}
        for item in items:
            # item is tuple: (id, start_time, duration, metadata, sequence, file_name)
            metadata = item[3] or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            
            day_offset = metadata.get('day_offset', 0)
            if day_offset not in by_day:
                by_day[day_offset] = []
            by_day[day_offset].append({
                'id': item[0],
                'scheduled_start_time': item[1],
                'scheduled_duration_seconds': item[2],
                'metadata': metadata,
                'sequence_number': item[4],
                'file_name': item[5]
            })
        
        # Show summary
        print("Items by day:")
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        for day_offset in sorted(by_day.keys()):
            day_name = days[day_offset] if day_offset < len(days) else f"Day {day_offset}"
            print(f"  {day_name}: {len(by_day[day_offset])} items")
        
        print("\n" + "="*80 + "\n")
        
        # Show first 3 items from each day
        for day_offset in sorted(by_day.keys()):
            day_name = days[day_offset] if day_offset < len(days) else f"Day {day_offset}"
            print(f"{day_name} items:")
            
            for i, item in enumerate(by_day[day_offset][:3]):
                metadata = item.get('metadata', {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                
                print(f"  Sequence #{item['sequence_number']}:")
                print(f"    File: {item['file_name']}")
                print(f"    Start Time: {item['scheduled_start_time']}")
                print(f"    Metadata: {metadata}")
            
            if len(by_day[day_offset]) > 3:
                print(f"  ... and {len(by_day[day_offset]) - 3} more")
            print()
        
    finally:
        cursor.close()
        db._put_connection(conn)

if __name__ == "__main__":
    schedule_id = int(sys.argv[1]) if len(sys.argv) > 1 else 452
    check_aim_podcast(schedule_id)