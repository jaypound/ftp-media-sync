#!/usr/bin/env python3
"""Update old live input items that have no metadata."""

from database import db_manager
import json

# Connect to database
if hasattr(db_manager, 'connected') and not db_manager.connected:
    db_manager.connect()

conn = db_manager._get_connection()
cursor = conn.cursor()

# Find items with asset_id=300 and no metadata
cursor.execute("""
    SELECT 
        si.id,
        si.scheduled_start_time,
        a.content_title
    FROM scheduled_items si
    LEFT JOIN assets a ON si.asset_id = a.id
    WHERE si.asset_id = 300 AND si.metadata IS NULL
""")

items_to_update = cursor.fetchall()
print(f"Found {len(items_to_update)} live input items without metadata")

if items_to_update:
    # Update each item with default metadata
    for item in items_to_update:
        # Determine which room based on time
        start_time = item['scheduled_start_time']
        hour = start_time.hour if hasattr(start_time, 'hour') else int(str(start_time).split(':')[0])
        
        # Default to Committee Room 1
        metadata = {
            'is_live_input': True,
            'file_path': '/mnt/main/tv/inputs/2-SDI in',
            'title': 'Live Input - Committee Room 1',
            'guid': '',
            'loop': '0'
        }
        
        # Update the item
        cursor.execute("""
            UPDATE scheduled_items 
            SET metadata = %s 
            WHERE id = %s
        """, (json.dumps(metadata), item['id']))
        
        print(f"Updated item {item['id']} at {item['scheduled_start_time']}")
    
    conn.commit()
    print(f"\nSuccessfully updated {len(items_to_update)} items")
else:
    print("All live input items already have metadata")

cursor.close()
db_manager._put_connection(conn)