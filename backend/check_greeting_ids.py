#!/usr/bin/env python3
"""Check IDs for specific holiday greetings"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', '')
)
cursor = conn.cursor(cursor_factory=RealDictCursor)

# Check the greetings that are appearing in the schedule
print("Checking IDs for greetings appearing in schedule:")
print("=" * 80)

greetings_to_check = [
    'AFRD Holiday Greetings',
    'Ingram Holiday Greeting',
    'ATL311 Holiday Greetings',
    'ATL Housing Holiday Greeting'
]

cursor.execute("""
    SELECT 
        a.id as asset_id,
        a.content_title,
        i.file_name,
        hgr.asset_id as in_rotation
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE a.content_title = ANY(%s)
    OR i.file_name LIKE ANY(%s)
    ORDER BY a.content_title
""", (
    greetings_to_check,
    ['%AFRD Holiday Greetings%', '%Ingram Holiday Greeting%', '%ATL311 Holiday Greetings%', '%ATL Housing Holiday Greeting%']
))

for row in cursor.fetchall():
    print(f"\nTitle: {row['content_title']}")
    print(f"File: {row['file_name']}")
    print(f"Asset ID: {row['asset_id']}")
    print(f"In rotation table: {'Yes' if row['in_rotation'] else 'No'}")

cursor.close()
conn.close()