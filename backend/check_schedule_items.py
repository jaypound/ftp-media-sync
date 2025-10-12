#!/usr/bin/env python3
"""Simple check of schedule items"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
import psycopg2
import json

schedule_id = int(sys.argv[1]) if len(sys.argv) > 1 else 452

db = PostgreSQLDatabaseManager()
db.connect()

conn = db._get_connection()
cursor = conn.cursor()

print(f"Checking schedule {schedule_id}...")

# Get total items
cursor.execute("SELECT COUNT(*) FROM scheduled_items WHERE schedule_id = %s", (schedule_id,))
total_count = cursor.fetchone()[0]
print(f"Total items in schedule: {total_count}")

# Check for metadata column
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'scheduled_items' 
    AND column_name = 'metadata'
""")
has_metadata = cursor.fetchone() is not None
print(f"Has metadata column: {has_metadata}")

# Get first 5 items
print("\nFirst 5 items:")
cursor.execute("""
    SELECT si.id, si.sequence_number, si.scheduled_start_time, si.scheduled_duration_seconds, si.metadata
    FROM scheduled_items si
    WHERE si.schedule_id = %s
    ORDER BY si.sequence_number
    LIMIT 5
""", (schedule_id,))

for row in cursor.fetchall():
    print(f"\nItem {row[1]}:")
    print(f"  ID: {row[0]}")
    print(f"  Start time: {row[2]}")
    print(f"  Duration: {row[3]}s")
    print(f"  Metadata: {row[4]}")
    if row[4]:
        try:
            if isinstance(row[4], str):
                meta = json.loads(row[4])
            else:
                meta = row[4]
            print(f"  Parsed metadata: {meta}")
        except:
            print(f"  Could not parse metadata")

cursor.close()
db._put_connection(conn)