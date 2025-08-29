#!/usr/bin/env python3
"""Check metadata in scheduled_items table."""

from database import db_manager
from datetime import datetime

# Connect to database
if hasattr(db_manager, 'connected') and not db_manager.connected:
    db_manager.connect()

conn = db_manager._get_connection()
cursor = conn.cursor()

# Check items with asset_id=300
cursor.execute("""
    SELECT 
        si.id,
        si.schedule_id,
        si.asset_id,
        si.scheduled_start_time,
        si.metadata,
        a.content_title
    FROM scheduled_items si
    LEFT JOIN assets a ON si.asset_id = a.id
    WHERE si.asset_id = 300
    ORDER BY si.created_at DESC
    LIMIT 10
""")

results = cursor.fetchall()
print(f"\nFound {len(results)} items with asset_id=300 (Live Input Placeholder):\n")

for row in results:
    print(f"ID: {row['id']}")
    print(f"  Schedule ID: {row['schedule_id']}")
    print(f"  Asset ID: {row['asset_id']}")
    print(f"  Start Time: {row['scheduled_start_time']}")
    print(f"  Content Title: {row['content_title']}")
    print(f"  Metadata: {row['metadata']}")
    print("  " + "-"*50)

cursor.close()
db_manager._put_connection(conn)