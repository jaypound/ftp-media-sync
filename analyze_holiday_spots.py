#!/usr/bin/env python3
"""Analyze holiday greeting spots rotation issue"""

import os
import psycopg2
from datetime import datetime, timedelta
from collections import Counter

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://jay:macmini@localhost:5432/ftp_sync')

def analyze_holiday_spots():
    """Analyze holiday greeting spots and their scheduling patterns"""
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Find all holiday greeting spots
    print("=== ANALYZING HOLIDAY GREETING SPOTS ===\n")
    
    cursor.execute("""
        SELECT 
            a.id,
            a.content_title,
            i.file_name,
            a.duration_seconds,
            a.duration_category,
            sm.last_scheduled_date,
            sm.total_airings,
            sm.content_expiry_date,
            sm.available_for_scheduling
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE i.file_name LIKE '%Holiday Greeting%'
           OR i.file_name LIKE '%holiday greeting%'
        ORDER BY i.file_name
    """)
    
    all_spots = cursor.fetchall()
    print(f"Total holiday greeting spots found: {len(all_spots)}\n")
    
    # Separate by scheduling status
    scheduled_spots = []
    never_scheduled = []
    
    for spot in all_spots:
        if spot[5]:  # has last_scheduled_date
            scheduled_spots.append(spot)
        else:
            never_scheduled.append(spot)
    
    print(f"Spots that have been scheduled: {len(scheduled_spots)}")
    print(f"Spots never scheduled: {len(never_scheduled)}\n")
    
    # Show the frequently scheduled ones
    print("=== FREQUENTLY SCHEDULED SPOTS ===")
    for spot in scheduled_spots:
        id, title, filename, duration, category, last_scheduled, airings, expiry, available = spot
        print(f"File: {filename}")
        print(f"  Title: {title}")
        print(f"  Category: {category}, Duration: {duration}s")
        print(f"  Total Airings: {airings}")
        print(f"  Last Scheduled: {last_scheduled}")
        print(f"  Available for Scheduling: {available}")
        print(f"  Expires: {expiry}\n")
    
    # Show never scheduled ones
    print("\n=== SPOTS NEVER SCHEDULED ===")
    for spot in never_scheduled:
        id, title, filename, duration, category, last_scheduled, airings, expiry, available = spot
        print(f"File: {filename}")
        print(f"  Title: {title}")
        print(f"  Category: {category}, Duration: {duration}s")
        print(f"  Available for Scheduling: {available}")
        print(f"  Expires: {expiry}")
    
    # Check replay delays configuration
    print("\n\n=== CHECKING REPLAY DELAY CONFIGURATION ===")
    cursor.execute("""
        SELECT content_type, base_hours, additional_hours_per_airing 
        FROM replay_delays 
        WHERE content_type = 'spp'
    """)
    delays = cursor.fetchone()
    if delays:
        print(f"SPP Replay Delays: Base={delays[1]}h, Additional per airing={delays[2]}h")
    
    # Get recent schedule to analyze pattern
    print("\n\n=== RECENT SCHEDULE PATTERN ===")
    cursor.execute("""
        SELECT 
            i.file_name,
            COUNT(*) as times_scheduled
        FROM scheduled_items si
        JOIN assets a ON si.asset_id = a.id
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        JOIN schedules s ON si.schedule_id = s.id
        WHERE i.file_name LIKE '%Holiday Greeting%'
           OR i.file_name LIKE '%holiday greeting%'
        AND s.air_date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY i.file_name
        ORDER BY times_scheduled DESC
    """)
    
    recent_pattern = cursor.fetchall()
    print("Holiday spots scheduled in last 7 days:")
    for filename, count in recent_pattern:
        print(f"  {filename}: {count} times")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    analyze_holiday_spots()