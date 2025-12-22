#!/usr/bin/env python3
"""
Populate holiday_greetings_days table by date range (without requiring a schedule)
This allows pre-population before schedules are created
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

load_dotenv()

def populate_holiday_days_by_date():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ftp_media_sync'),
        user=os.getenv('DB_USER', os.environ.get('USER')),
        password=os.getenv('DB_PASSWORD', '')
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=== Holiday Greeting Daily Assignment Population by Date ===")
    print("=== For Week 51: Dec 21-27, 2025 ===\n")
    
    # Week 51 starts on Sunday, Dec 21, 2025
    week_51_start = datetime(2025, 12, 21).date()
    num_days = 7
    greetings_per_day = 4
    
    # Check if assignments already exist for these dates
    cursor.execute("""
        SELECT COUNT(*) as count, MIN(schedule_id) as min_schedule_id
        FROM holiday_greetings_days 
        WHERE start_date >= %s AND start_date < %s
    """, (week_51_start, week_51_start + timedelta(days=num_days)))
    
    result = cursor.fetchone()
    existing = result['count']
    existing_schedule_id = result['min_schedule_id']
    
    if existing > 0:
        print(f"WARNING: {existing} assignments already exist for these dates")
        print(f"Existing schedule_id: {existing_schedule_id}")
        response = input("Delete existing and recreate? (y/n): ")
        if response.lower() != 'y':
            return
        
        cursor.execute("""
            DELETE FROM holiday_greetings_days 
            WHERE start_date >= %s AND start_date < %s
        """, (week_51_start, week_51_start + timedelta(days=num_days)))
        conn.commit()
        print("Existing assignments deleted")
    
    # Get all available holiday greetings
    cursor.execute("""
        SELECT DISTINCT 
            a.id as asset_id,
            i.file_name,
            a.content_title,
            a.duration_category
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
        JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.duration_category = 'spots'
        AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
        AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
        AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
        ORDER BY i.file_name
    """, (week_51_start + timedelta(days=7), week_51_start))
    
    all_greetings = cursor.fetchall()
    print(f"\nFound {len(all_greetings)} available holiday greetings:")
    for i, g in enumerate(all_greetings):
        print(f"  {i+1}. {g['file_name']}")
    
    if len(all_greetings) < 4:
        print(f"\nWARNING: Only {len(all_greetings)} greetings available, need at least 4 for good diversity")
    
    # For now, we'll use schedule_id = NULL since no schedule exists yet
    # This will need to be updated when the schedule is created
    schedule_id = None
    print(f"\nCreating assignments with NULL schedule_id (will be updated when schedule is created)")
    
    # Track usage to ensure fair distribution
    usage_count = {g['asset_id']: 0 for g in all_greetings}
    
    # Create assignments for each day
    for day_num in range(num_days):
        day_date = week_51_start + timedelta(days=day_num)
        day_end = day_date + timedelta(days=1)
        
        # Sort greetings by usage count (least used first)
        available_for_day = sorted(
            all_greetings, 
            key=lambda x: (usage_count[x['asset_id']], random.random())
        )
        
        # Take the least-used greetings for this day
        greetings_for_today = available_for_day[:greetings_per_day]
        
        print(f"\nDay {day_num + 1} ({day_date.strftime('%Y-%m-%d %A')}):")
        for greeting in greetings_for_today:
            # Insert with NULL schedule_id
            cursor.execute("""
                INSERT INTO holiday_greetings_days 
                (schedule_id, asset_id, day_number, start_date, end_date)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                schedule_id,  # NULL for now
                greeting['asset_id'],
                day_num + 1,
                day_date,
                day_end
            ))
            usage_count[greeting['asset_id']] += 1
            print(f"  - {greeting['file_name']}")
    
    conn.commit()
    
    # Show summary
    print(f"\n=== Summary ===")
    print(f"Total assignments created: {num_days * greetings_per_day}")
    print(f"\nUsage count by greeting:")
    for g in all_greetings:
        if usage_count[g['asset_id']] > 0:
            print(f"  {g['file_name']}: {usage_count[g['asset_id']]} times")
    
    # Verify in database
    cursor.execute("""
        SELECT 
            start_date,
            COUNT(DISTINCT asset_id) as unique_greetings,
            COUNT(*) as total_assignments
        FROM holiday_greetings_days
        WHERE start_date >= %s AND start_date < %s
        GROUP BY start_date
        ORDER BY start_date
    """, (week_51_start, week_51_start + timedelta(days=num_days)))
    
    print(f"\n=== Database Verification ===")
    for row in cursor.fetchall():
        print(f"{row['start_date']}: {row['unique_greetings']} unique greetings, {row['total_assignments']} total")
    
    cursor.close()
    conn.close()
    print("\nDone! Daily assignments have been populated with NULL schedule_id.")
    print("\nNOTE: The holiday greeting integration needs to be updated to use these assignments!")
    print("Currently it uses its own rotation logic and ignores the holiday_greetings_days table.")

if __name__ == "__main__":
    populate_holiday_days_by_date()