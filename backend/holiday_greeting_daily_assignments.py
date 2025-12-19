"""
Holiday Greeting Daily Assignment System

This module manages the assignment of holiday greetings to specific days
of a schedule, ensuring variety and preventing repetition.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import random
from database import db_manager

logger = logging.getLogger(__name__)

class HolidayGreetingDailyAssignments:
    """Manages daily assignments of holiday greetings for schedules"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.greetings_per_day = 4  # Number of greetings assigned to each day
    
    def assign_greetings_for_schedule(self, schedule_id: int, start_date: datetime, 
                                    num_days: int = 14) -> bool:
        """
        Assign holiday greetings to each day of a schedule
        
        Args:
            schedule_id: The schedule ID
            start_date: First day of the schedule
            num_days: Number of days to assign (default 14)
            
        Returns:
            True if successful, False otherwise
        """
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            
            # Ensure database is connected before attempting to get connection
            if not hasattr(self.db_manager, '_pool') or self.db_manager._pool is None:
                logger.error("Database pool not initialized, attempting to connect")
                self.db_manager.connect()
            
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get all available holiday greetings from the holiday_greeting_rotation table
            cursor.execute("""
                SELECT DISTINCT hgr.asset_id
                FROM holiday_greeting_rotation hgr
                JOIN assets a ON hgr.asset_id = a.id
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE a.duration_category = 'spots'
                AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
                AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
                ORDER BY 1
            """, (start_date + timedelta(days=num_days), start_date))
            
            results = cursor.fetchall()
            all_greetings = [row['asset_id'] for row in results]
            
            if not all_greetings:
                logger.error("No holiday greetings available for assignment")
                return False
            
            logger.info(f"Found {len(all_greetings)} holiday greetings for assignment")
            
            # Clear any existing assignments for this schedule
            cursor.execute("""
                DELETE FROM holiday_greetings_days 
                WHERE schedule_id = %s
            """, (schedule_id,))
            
            # If we have fewer greetings than needed, we'll need to repeat some
            total_slots = num_days * self.greetings_per_day
            
            # Shuffle all greetings for initial randomization
            shuffled_greetings = all_greetings.copy()
            random.shuffle(shuffled_greetings)
            
            # Track which greetings have been used across all days
            used_greetings_count = {greeting_id: 0 for greeting_id in all_greetings}
            
            # Assign greetings to days
            for day_num in range(num_days):
                day_start = start_date + timedelta(days=day_num)
                day_end = day_start + timedelta(days=1)
                
                # Sort greetings by usage count (least used first)
                available_for_day = sorted(
                    all_greetings, 
                    key=lambda x: (used_greetings_count[x], random.random())
                )
                
                # Take the first N least-used greetings for this day
                greetings_for_today = available_for_day[:self.greetings_per_day]
                
                # Insert assignments for this day
                for asset_id in greetings_for_today:
                    cursor.execute("""
                        INSERT INTO holiday_greetings_days 
                        (schedule_id, day_number, asset_id, start_date, end_date)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (schedule_id, day_num + 1, asset_id, day_start, day_end))
                    
                    # Update usage count
                    used_greetings_count[asset_id] += 1
                
                logger.info(f"Day {day_num + 1} ({day_start.strftime('%Y-%m-%d')}): "
                          f"Assigned {len(greetings_for_today)} greetings")
            
            conn.commit()
            logger.info(f"Successfully assigned {sum(used_greetings_count.values())} greeting slots across {num_days} days")
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error assigning holiday greetings: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            if conn:
                cursor.close()
                self.db_manager._put_connection(conn)
    
    def get_greetings_for_date(self, schedule_id: int, date: datetime) -> List[int]:
        """
        Get the holiday greeting asset IDs available for a specific date
        
        Args:
            schedule_id: The schedule ID
            date: The date to check
            
        Returns:
            List of asset IDs available for that date
        """
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT asset_id
                FROM holiday_greetings_days
                WHERE schedule_id = %s
                AND %s >= start_date
                AND %s < end_date
                ORDER BY asset_id
            """, (schedule_id, date, date))
            
            results = cursor.fetchall()
            return [row['asset_id'] for row in results]
            
        except Exception as e:
            logger.error(f"Error getting greetings for date: {e}")
            return []
        finally:
            if conn:
                cursor.close()
                self.db_manager._put_connection(conn)
    
    def get_all_assignments(self, schedule_id: int) -> List[Dict[str, Any]]:
        """
        Get all daily assignments for a schedule
        
        Args:
            schedule_id: The schedule ID
            
        Returns:
            List of assignment dictionaries with day info and greeting details
        """
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    hgd.*,
                    i.file_name,
                    a.content_title
                FROM holiday_greetings_days hgd
                JOIN assets a ON hgd.asset_id = a.id
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                WHERE hgd.schedule_id = %s
                ORDER BY hgd.day_number, i.file_name
            """, (schedule_id,))
            
            return [dict(row) for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting all assignments: {e}")
            return []
        finally:
            if conn:
                cursor.close()
                self.db_manager._put_connection(conn)
    
    def print_assignment_summary(self, schedule_id: int):
        """Print a summary of daily assignments for debugging"""
        assignments = self.get_all_assignments(schedule_id)
        
        if not assignments:
            print(f"No assignments found for schedule {schedule_id}")
            return
        
        current_day = None
        for assignment in assignments:
            if assignment['day_number'] != current_day:
                current_day = assignment['day_number']
                print(f"\nDay {current_day} ({assignment['start_date']}):")
            
            short_name = assignment['file_name'].replace('251210_SSP_', '').replace('.mp4', '')[:35]
            print(f"  - {short_name}")