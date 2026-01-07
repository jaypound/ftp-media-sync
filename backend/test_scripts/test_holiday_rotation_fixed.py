#!/usr/bin/env python3
"""Test if holiday greeting rotation works correctly after fix"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from datetime import datetime, timedelta
import pytz

print("=== Testing Holiday Greeting Rotation After Fix ===\n")

# Connect to database
db_manager.connect()

# Create scheduler instance
scheduler = PostgreSQLScheduler()

# Future date for testing
eastern = pytz.timezone('US/Eastern')
future_date = (datetime.now(eastern) + timedelta(days=7)).strftime('%Y-%m-%d')

print(f"Creating test schedule for: {future_date}\n")

# Test getting content with progressive delays
exclude_ids = []
for i in range(5):
    print(f"\n--- Round {i+1} ---")
    
    # Get content for spots category
    available_content = scheduler._get_content_with_progressive_delays(
        'spots',
        exclude_ids=exclude_ids,
        schedule_date=future_date
    )
    
    # Filter for holiday greetings
    holiday_greetings = [c for c in available_content if 'holiday' in c['file_name'].lower() and 'greeting' in c['file_name'].lower()]
    
    print(f"Total content available: {len(available_content)}")
    print(f"Holiday greetings available: {len(holiday_greetings)}")
    
    if holiday_greetings:
        # Show first holiday greeting
        first_greeting = holiday_greetings[0]
        print(f"Selected greeting: {first_greeting['file_name']}")
        
        # Add to exclude list to simulate scheduling
        exclude_ids.append(first_greeting['asset_id'])
    else:
        print("No holiday greetings available!")
        break

# Check rotation status
print("\n=== Checking Rotation Status ===")
import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    database=os.getenv('DB_NAME', 'ftp_media_sync'),
    user=os.getenv('DB_USER', os.environ.get('USER')),
    password=os.getenv('DB_PASSWORD', ''),
    port=os.getenv('DB_PORT', '5432')
)

cursor = conn.cursor()

cursor.execute("""
    SELECT 
        i.file_name,
        hgr.scheduled_count
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
    AND a.duration_category = 'spots'
    ORDER BY COALESCE(hgr.scheduled_count, 0)
    LIMIT 5
""")

print("\nLowest play count greetings:")
for file_name, count in cursor.fetchall():
    short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')[:40]
    print(f"  {short_name:40} | Plays: {count or 0}")

cursor.close()
conn.close()