#!/usr/bin/env python3
"""
Auto-populate holiday_greetings_days table based on imported meeting dates
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ftp_media_sync'),
        user=os.getenv('DB_USER', os.environ.get('USER')),
        password=os.getenv('DB_PASSWORD', '')
    )

def auto_populate_holiday_days(schedule_id: int, days_to_populate: list = None):
    """
    Auto-populate holiday_greetings_days based on schedule dates
    
    Args:
        schedule_id: The schedule ID to populate for
        days_to_populate: Optional list of specific dates to populate. 
                         If None, will detect from schedule items
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get schedule info
        cursor.execute("""
            SELECT id, air_date, schedule_name, schedule_type
            FROM schedules
            WHERE id = %s
        """, (schedule_id,))
        
        schedule = cursor.fetchone()
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")
        
        logger.info(f"Auto-populating holiday days for: {schedule['schedule_name']}")
        
        # Determine which days to populate
        if days_to_populate is None:
            # Auto-detect days from schedule items
            if schedule['schedule_type'] == 'weekly':
                # For weekly schedules, populate all 7 days
                base_date = schedule['air_date']
                days_to_populate = []
                for i in range(7):
                    day_date = base_date + timedelta(days=i)
                    days_to_populate.append(day_date)
                logger.info(f"Weekly schedule: populating all 7 days starting from {base_date}")
            else:
                # For daily schedules, just populate the schedule date
                days_to_populate = [schedule['air_date']]
                logger.info(f"Daily schedule: populating {schedule['air_date']}")
        
        # Get all available holiday greetings
        cursor.execute("""
            SELECT DISTINCT 
                a.id as asset_id,
                i.file_name,
                a.content_title
            FROM assets a
            JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
            JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE a.duration_category = 'spots'
            AND (
                i.file_name ILIKE '%holiday%greeting%' 
                OR a.content_title ILIKE '%holiday%greeting%'
            )
            AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
            ORDER BY i.file_name
        """)
        
        all_greetings = cursor.fetchall()
        logger.info(f"Found {len(all_greetings)} available holiday greetings")
        
        if len(all_greetings) < 4:
            logger.warning(f"Only {len(all_greetings)} greetings available, need at least 4 for good diversity")
        
        # Clear existing assignments for these dates
        for day_date in days_to_populate:
            cursor.execute("""
                DELETE FROM holiday_greetings_days 
                WHERE start_date = %s
            """, (day_date,))
        
        # Distribute greetings evenly across days
        greetings_per_day = min(4, len(all_greetings))  # Use 4 or all available
        
        # Track usage to ensure fair distribution
        usage_count = {g['asset_id']: 0 for g in all_greetings}
        
        assignments_created = 0
        for day_num, day_date in enumerate(days_to_populate):
            day_end = day_date + timedelta(days=1)
            
            # Sort greetings by usage count (least used first)
            available_for_day = sorted(
                all_greetings, 
                key=lambda x: usage_count[x['asset_id']]
            )
            
            # Take the least-used greetings for this day
            greetings_for_today = available_for_day[:greetings_per_day]
            
            logger.info(f"\nDay {day_num + 1} ({day_date.strftime('%Y-%m-%d %A')}):")
            
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
                assignments_created += 1
                logger.info(f"  - {greeting['file_name']}")
        
        conn.commit()
        logger.info(f"\nCreated {assignments_created} holiday greeting assignments")
        
        # Show usage summary
        logger.info("\nUsage summary:")
        for greeting in all_greetings:
            count = usage_count[greeting['asset_id']]
            if count > 0:
                logger.info(f"  {greeting['file_name']}: {count} days")
        
        return assignments_created
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error auto-populating holiday days: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def auto_populate_from_meeting_dates(schedule_id: int):
    """
    Auto-populate based on actual meeting dates in the schedule
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get unique dates that have meetings
        cursor.execute("""
            SELECT DISTINCT DATE(start_datetime) as meeting_date
            FROM schedule_items
            WHERE schedule_id = %s
            AND content_title ILIKE '%meeting%'
            ORDER BY meeting_date
        """, (schedule_id,))
        
        meeting_dates = [row['meeting_date'] for row in cursor.fetchall()]
        
        if meeting_dates:
            logger.info(f"Found meetings on {len(meeting_dates)} dates")
            return auto_populate_holiday_days(schedule_id, meeting_dates)
        else:
            logger.warning("No meetings found in schedule")
            return 0
            
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python auto_populate_holiday_days.py <schedule_id> [--from-meetings]")
        print("Options:")
        print("  --from-meetings: Populate only for days that have meetings")
        sys.exit(1)
    
    schedule_id = int(sys.argv[1])
    from_meetings = "--from-meetings" in sys.argv
    
    if from_meetings:
        auto_populate_from_meeting_dates(schedule_id)
    else:
        auto_populate_holiday_days(schedule_id)