#!/usr/bin/env python3
"""Check holiday greetings daily assignments"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', '')
)
cursor = conn.cursor(cursor_factory=RealDictCursor)

# Check assignments for Week 51
print("Holiday Greeting Daily Assignments for Week 51 (Dec 21-27, 2025):")
print("=" * 80)

cursor.execute("""
    SELECT 
        hgd.day_number,
        hgd.start_date,
        hgd.asset_id,
        i.file_name,
        a.content_title
    FROM holiday_greetings_days hgd
    JOIN assets a ON hgd.asset_id = a.id
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    WHERE hgd.start_date >= '2025-12-21' AND hgd.start_date <= '2025-12-27'
    ORDER BY hgd.start_date, hgd.asset_id
""")

current_date = None
for row in cursor.fetchall():
    if row['start_date'] != current_date:
        current_date = row['start_date']
        print(f"\n{current_date.strftime('%Y-%m-%d %A')}:")
    print(f"  - {row['file_name']} (ID: {row['asset_id']})")

cursor.close()
conn.close()