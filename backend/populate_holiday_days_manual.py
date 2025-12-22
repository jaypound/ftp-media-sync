#!/usr/bin/env python3
"""
Manually populate holiday_greetings_days table for Week 51: Dec 21-27, 2025
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

load_dotenv()

def populate_holiday_days():
    # Database connection
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ftp_media_sync'),
        user=os.getenv('DB_USER', os.environ.get('USER')),
        password=os.getenv('DB_PASSWORD', '')
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=== Manual Holiday Greeting Daily Assignment Population ===")
    print("=== For Week 51: Dec 21-27, 2025 ===\n")
    
    # Week 51 starts on Sunday, Dec 21, 2025
    week_51_start = datetime(2025, 12, 21).date()
    
    # Find schedule for this date
    cursor.execute("""
        SELECT id, air_date, schedule_name 
        FROM schedules 
        WHERE air_date = %s
        ORDER BY id DESC 
        LIMIT 1
    """, (week_51_start,))
    
    schedule = cursor.fetchone()
    
    if not schedule:
        # Try to find the most recent schedule that might be for Week 51
        cursor.execute("""
            SELECT id, air_date, schedule_name 
            FROM schedules 
            WHERE air_date >= %s AND air_date <= %s
            ORDER BY id DESC 
            LIMIT 1
        """, (week_51_start, week_51_start + timedelta(days=6)))
        schedule = cursor.fetchone()
    
    if not schedule:
        print(f"No schedule found for Week 51 (starting {week_51_start})")
        print("\nAvailable schedules:")
        cursor.execute("""
            SELECT id, air_date, schedule_name 
            FROM schedules 
            ORDER BY air_date DESC
            LIMIT 10
        """)
        for s in cursor.fetchall():
            print(f"  ID {s['id']}: {s['air_date']} - {s['schedule_name']}")
        
        schedule_id = input("\nEnter schedule ID manually: ").strip()
        if not schedule_id:
            return
        
        cursor.execute("""
            SELECT id, air_date, schedule_name 
            FROM schedules 
            WHERE id = %s
        """, (int(schedule_id),))
        schedule = cursor.fetchone()
        if not schedule:
            print(f"Schedule {schedule_id} not found!")
            return
    
    schedule_id = schedule['id']
    schedule_date = schedule['air_date']
    schedule_name = schedule['schedule_name']
    
    print(f"\nSchedule: {schedule_name} (ID: {schedule_id})")
    print(f"Schedule date: {schedule_date}")
    
    # Check if assignments already exist
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM holiday_greetings_days 
        WHERE schedule_id = %s
    """, (schedule_id,))
    
    existing = cursor.fetchone()['count']
    if existing > 0:
        print(f"\nWARNING: {existing} daily assignments already exist for this schedule")
        response = input("Delete existing and recreate? (y/n): ")
        if response.lower() != 'y':
            return
        
        cursor.execute("DELETE FROM holiday_greetings_days WHERE schedule_id = %s", (schedule_id,))
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
    """, (schedule_date + timedelta(days=7), schedule_date))
    
    all_greetings = cursor.fetchall()
    print(f"\nFound {len(all_greetings)} available holiday greetings:")
    for i, g in enumerate(all_greetings):
        print(f"  {i+1}. {g['file_name']}")
    
    if len(all_greetings) < 4:
        print(f"\nWARNING: Only {len(all_greetings)} greetings available, need at least 4 for good diversity")
    
    # Determine number of days
    is_weekly = 'weekly' in schedule_name.lower() or input("\nIs this a weekly schedule? (y/n): ").lower() == 'y'
    num_days = 7 if is_weekly else 1
    greetings_per_day = 4
    
    print(f"\nCreating assignments for {num_days} days with {greetings_per_day} greetings per day...")
    
    # Track usage to ensure fair distribution
    usage_count = {g['asset_id']: 0 for g in all_greetings}
    
    # Create assignments for each day
    for day_num in range(num_days):
        day_date = schedule_date + timedelta(days=day_num)
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
            cursor.execute("""
                INSERT INTO holiday_greetings_days 
                (schedule_id, asset_id, day_number, start_date, end_date)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                schedule_id,
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
        WHERE schedule_id = %s
        GROUP BY start_date
        ORDER BY start_date
    """, (schedule_id,))
    
    print(f"\n=== Database Verification ===")
    for row in cursor.fetchall():
        print(f"{row['start_date']}: {row['unique_greetings']} unique greetings, {row['total_assignments']} total")
    
    cursor.close()
    conn.close()
    print("\nDone! Daily assignments have been populated.")
    print("The next schedule creation should use these assignments for better diversity.")

if __name__ == "__main__":
    populate_holiday_days()