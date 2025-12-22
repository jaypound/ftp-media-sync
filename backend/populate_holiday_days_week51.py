#!/usr/bin/env python3
"""
Populate holiday_greetings_days table for Week 51 without requiring a schedule
Now that schedule_id is nullable, we can pre-populate assignments by date
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

load_dotenv()

def populate_week51_assignments():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ftp_media_sync'),
        user=os.getenv('DB_USER', os.environ.get('USER')),
        password=os.getenv('DB_PASSWORD', '')
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=== Holiday Greeting Daily Assignment Population ===")
    print("=== Pre-populating for Week 51: Dec 21-27, 2025 ===\n")
    
    # Week 51 starts on Sunday, Dec 21, 2025
    week_51_start = datetime(2025, 12, 21).date()
    num_days = 7
    greetings_per_day = 4
    
    # First, clean up any existing assignments for Week 51
    cursor.execute("""
        DELETE FROM holiday_greetings_days 
        WHERE start_date >= %s AND start_date < %s
    """, (week_51_start, week_51_start + timedelta(days=num_days)))
    deleted = cursor.rowcount
    if deleted > 0:
        print(f"Removed {deleted} existing assignments for Week 51")
    
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
    print(f"Found {len(all_greetings)} available holiday greetings:")
    for i, g in enumerate(all_greetings):
        print(f"  {i+1:2}. {g['file_name']}")
    
    if len(all_greetings) < greetings_per_day:
        print(f"\nERROR: Need at least {greetings_per_day} greetings, only have {len(all_greetings)}")
        return
    
    print(f"\nCreating {num_days * greetings_per_day} assignments (NULL schedule_id)...")
    
    # Track usage to ensure fair distribution
    usage_count = {g['asset_id']: 0 for g in all_greetings}
    
    # Create assignments for each day
    for day_num in range(num_days):
        day_date = week_51_start + timedelta(days=day_num)
        day_end = day_date + timedelta(days=1)
        
        # Sort greetings by usage count (least used first) with random tiebreaker
        available_for_day = sorted(
            all_greetings, 
            key=lambda x: (usage_count[x['asset_id']], random.random())
        )
        
        # Take the least-used greetings for this day
        greetings_for_today = available_for_day[:greetings_per_day]
        
        print(f"\nDay {day_num + 1} ({day_date.strftime('%Y-%m-%d %A')}):")
        for greeting in greetings_for_today:
            cursor.execute("""
                INSERT INTO holiday_greetings_days 
                (asset_id, day_number, start_date, end_date)
                VALUES (%s, %s, %s, %s)
            """, (
                greeting['asset_id'],
                day_num + 1,
                day_date,
                day_end
            ))
            usage_count[greeting['asset_id']] += 1
            print(f"  - {greeting['file_name']}")
    
    conn.commit()
    
    # Show distribution summary
    print(f"\n=== Distribution Summary ===")
    print(f"Total assignments: {num_days * greetings_per_day}")
    print(f"\nUsage count by greeting:")
    
    # Sort by usage count
    usage_summary = [(g['file_name'], usage_count[g['asset_id']]) 
                     for g in all_greetings if usage_count[g['asset_id']] > 0]
    usage_summary.sort(key=lambda x: (-x[1], x[0]))
    
    for name, count in usage_summary:
        print(f"  {count}x - {name}")
    
    # Show unused greetings if any
    unused = [g['file_name'] for g in all_greetings if usage_count[g['asset_id']] == 0]
    if unused:
        print(f"\nUnused greetings ({len(unused)}):")
        for name in unused:
            print(f"  - {name}")
    
    # Verify in database
    cursor.execute("""
        SELECT 
            start_date,
            COUNT(DISTINCT hgd.asset_id) as unique_greetings,
            COUNT(*) as total_assignments,
            array_agg(DISTINCT substring(i.file_name from '251210_SSP_(.+)\.mp4') ORDER BY 1) as greeting_names
        FROM holiday_greetings_days hgd
        JOIN instances i ON hgd.asset_id = i.asset_id AND i.is_primary = true
        WHERE start_date >= %s AND start_date < %s
        GROUP BY start_date
        ORDER BY start_date
    """, (week_51_start, week_51_start + timedelta(days=num_days)))
    
    print(f"\n=== Database Verification ===")
    for row in cursor.fetchall():
        print(f"{row['start_date']}: {row['unique_greetings']} unique, {row['total_assignments']} total")
        if row['greeting_names']:
            print(f"  Greetings: {', '.join(row['greeting_names'][:3])}...")
    
    cursor.close()
    conn.close()
    
    print("\n✅ Week 51 assignments populated successfully!")
    print("\nNOTE: The updated holiday greeting integration will now use these pre-assigned")
    print("greetings when creating schedules for Dec 21-27, 2025.")

if __name__ == "__main__":
    populate_week51_assignments()