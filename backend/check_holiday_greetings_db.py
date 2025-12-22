#!/usr/bin/env python3
"""Check holiday greeting database contents"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Direct connection
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'), 
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', ''),
    port=os.getenv('DB_PORT', '5432')
)

cursor = conn.cursor()

print("=== Holiday Greeting Rotation Table ===")
cursor.execute("""
    SELECT 
        hgr.asset_id,
        hgr.file_name,
        hgr.scheduled_count,
        a.duration_category
    FROM holiday_greeting_rotation hgr
    LEFT JOIN assets a ON hgr.asset_id = a.id
    ORDER BY hgr.scheduled_count ASC
    LIMIT 10
""")

print(f"\nFirst 10 holiday greetings by play count:")
for row in cursor.fetchall():
    asset_id, file_name, count, category = row
    short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '') if file_name else 'Unknown'
    print(f"  {short_name[:30]:30} | {count:3} plays | {category}")

# Count by category
cursor.execute("""
    SELECT a.duration_category, COUNT(*)
    FROM holiday_greeting_rotation hgr
    JOIN assets a ON hgr.asset_id = a.id
    GROUP BY a.duration_category
""")

print(f"\n=== Holiday Greetings by Duration Category ===")
for row in cursor.fetchall():
    category, count = row
    print(f"  {category}: {count} greetings")

# Never scheduled
cursor.execute("""
    SELECT COUNT(*) FROM holiday_greeting_rotation WHERE scheduled_count = 0
""")
never = cursor.fetchone()[0]
print(f"\nNever scheduled: {never} greetings")

# Check if they're in the spots category
cursor.execute("""
    SELECT COUNT(*)
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    WHERE i.file_name ILIKE '%holiday%greeting%'
    AND a.duration_category = 'spots'
""")
spots_count = cursor.fetchone()[0]
print(f"Holiday greetings in 'spots' category: {spots_count}")

cursor.close()
conn.close()