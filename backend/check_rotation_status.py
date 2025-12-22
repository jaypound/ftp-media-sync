#!/usr/bin/env python3
"""Check holiday greeting rotation status"""

import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

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

print("=== Holiday Greeting Play Count Distribution ===\n")

# Get top played
cursor.execute("""
    SELECT file_name, scheduled_count, last_scheduled
    FROM holiday_greeting_rotation
    WHERE scheduled_count > 0
    ORDER BY scheduled_count DESC
    LIMIT 10
""")

results = cursor.fetchall()
if results:
    print("Top played greetings:")
    for file_name, count, last_sched in results:
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')
        print(f"  {short_name[:35]:35} | {count:3} plays")
else:
    print("No greetings have been played yet.")

# Get never played
cursor.execute("""
    SELECT file_name
    FROM holiday_greeting_rotation
    WHERE scheduled_count = 0
    ORDER BY file_name
""")

never_played = cursor.fetchall()
print(f"\nNever played: {len(never_played)} greetings")
if never_played and len(never_played) <= 15:
    for (file_name,) in never_played:
        short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '')
        print(f"  - {short_name}")

# Check recent log
log_file = f"logs/holiday_greeting_{datetime.now().strftime('%Y%m%d')}.log"
if os.path.exists(log_file):
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    # Look for recent activity
    recent_selections = []
    for line in reversed(lines):  # Read from end
        if "SELECTED greeting:" in line and len(recent_selections) < 5:
            recent_selections.append(line.strip())
    
    if recent_selections:
        print("\nMost recent selections from log:")
        for sel in reversed(recent_selections):
            print(f"  {sel}")
    else:
        print("\nNo recent selections found in log.")

cursor.close()
conn.close()