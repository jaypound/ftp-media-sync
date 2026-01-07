#!/usr/bin/env python3
"""
Check the alternating pattern of holiday greetings
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ftp_media_sync'),
        user=os.getenv('DB_USER', os.environ.get('USER')),
        password=os.getenv('DB_PASSWORD', '')
    )

conn = get_db_connection()
cursor = conn.cursor(cursor_factory=RealDictCursor)

try:
    # Get recent schedule
    # Check for schedule by name pattern first
    cursor.execute("""
        SELECT id, schedule_name, created_date
        FROM schedules
        WHERE schedule_name LIKE '%12_20_13_56%'
        ORDER BY created_date DESC
        LIMIT 1
    """)
    
    schedule = cursor.fetchone()
    if not schedule:
        print("Schedule not found")
        cursor.close()
        conn.close()
        exit()
        
    print(f"Analyzing: {schedule['schedule_name']} (ID: {schedule['id']})")
    print(f"Created: {schedule['created_date']}")
    print("="*60)
    
    # Get all items with holiday greeting detection
    cursor.execute("""
        SELECT 
            si.sequence_number as seq,
            a.duration_category as cat,
            i.file_name,
            a.theme
        FROM scheduled_items si
        JOIN assets a ON si.asset_id = a.id
        JOIN instances i ON si.instance_id = i.id
        WHERE si.schedule_id = %(sid)s
        ORDER BY si.sequence_number
        LIMIT 500
    """, {'sid': schedule['id']})
    
    items = cursor.fetchall()
    
    # Analyze the pattern
    prev_is_hg = False
    back_to_back = []
    holiday_positions = []
    
    for i, item in enumerate(items):
        file_lower = item['file_name'].lower()
        is_hg = 'holiday' in file_lower and 'greeting' in file_lower
        
        if is_hg:
            holiday_positions.append(item['seq'])
        
        # Mark if back-to-back
        if i > 0 and is_hg and prev_is_hg:
            back_to_back.append(item['seq'])
        
        prev_is_hg = is_hg
    
    print(f"Total holiday greetings found: {len(holiday_positions)}")
    print(f"Back-to-back occurrences: {len(back_to_back)}")
    print(f"Back-to-back at sequences: {back_to_back[:20]}")
    
    # Check if there's a pattern in the sequence numbers
    if len(back_to_back) > 5:
        gaps = [back_to_back[i+1] - back_to_back[i] for i in range(len(back_to_back)-1)]
        print(f"\nGaps between back-to-back occurrences: {gaps[:20]}")
        
        # Check for regularity
        unique_gaps = set(gaps)
        if len(unique_gaps) == 1:
            print(f"PATTERN DETECTED: Consistent gap of {gaps[0]} positions!")
        else:
            print(f"Unique gaps: {sorted(unique_gaps)}")
    
    # Analyze holiday greeting positions
    print(f"\nHoliday greeting positions: {holiday_positions[:30]}")
    
    # Check the pattern of holiday greetings
    if len(holiday_positions) > 10:
        hg_gaps = [holiday_positions[i+1] - holiday_positions[i] for i in range(len(holiday_positions)-1)]
        print(f"\nGaps between all holiday greetings: {hg_gaps[:20]}")
        
        # Group consecutive greetings
        groups = []
        current_group = [holiday_positions[0]]
        for i in range(1, len(holiday_positions)):
            if holiday_positions[i] - holiday_positions[i-1] == 1:
                current_group.append(holiday_positions[i])
            else:
                groups.append(current_group)
                current_group = [holiday_positions[i]]
        groups.append(current_group)
        
        print(f"\nGrouping analysis:")
        print(f"Number of groups: {len(groups)}")
        for i, group in enumerate(groups[:10]):
            print(f"  Group {i+1}: {len(group)} items at positions {group}")
        
finally:
    cursor.close()
    conn.close()