"""
PostgreSQL-based Scheduler for FTP Media Sync
Creates daily schedules with duration category rotation
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from database import db_manager

logger = logging.getLogger(__name__)


class PostgreSQLScheduler:
    def __init__(self):
        self.duration_rotation = ['id', 'short_form', 'long_form', 'spots']
        self.rotation_index = 0
        self.target_duration_seconds = 24 * 60 * 60  # 24 hours in seconds
        
    def _get_next_duration_category(self) -> str:
        """Get the next duration category in rotation"""
        category = self.duration_rotation[self.rotation_index]
        self.rotation_index = (self.rotation_index + 1) % len(self.duration_rotation)
        return category
    
    def _reset_rotation(self):
        """Reset the rotation index"""
        self.rotation_index = 0
    
    def get_available_content(self, duration_category: str, exclude_ids: List[int] = None) -> List[Dict[str, Any]]:
        """Get available content for a specific duration category"""
        if not db_manager.connected:
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build query to get available content
            query = """
                SELECT 
                    a.id as asset_id,
                    a.guid,
                    a.content_type,
                    a.content_title,
                    a.duration_seconds,
                    a.duration_category,
                    a.engagement_score,
                    i.id as instance_id,
                    i.file_name,
                    i.file_path,
                    sm.last_scheduled_date,
                    sm.total_airings,
                    COALESCE(sm.content_expiry_date, CURRENT_TIMESTAMP + INTERVAL '1 year') as content_expiry_date
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE 
                    a.analysis_completed = TRUE
                    AND a.duration_category = %s
                    AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                    AND COALESCE(sm.content_expiry_date, CURRENT_TIMESTAMP + INTERVAL '1 year') > CURRENT_TIMESTAMP
            """
            
            params = [duration_category]
            
            # Exclude already scheduled items
            if exclude_ids:
                query += " AND a.id NOT IN %s"
                params.append(tuple(exclude_ids))
            
            # Order by last scheduled date (nulls first) and total airings
            query += """
                ORDER BY 
                    sm.last_scheduled_date ASC NULLS FIRST,
                    sm.total_airings ASC NULLS FIRST,
                    a.engagement_score DESC NULLS LAST
                LIMIT 50
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting available content: {str(e)}")
            return []
        finally:
            db_manager._put_connection(conn)
    
    def create_daily_schedule(self, schedule_date: str, schedule_name: str = None) -> Dict[str, Any]:
        """Create a daily schedule for the specified date"""
        try:
            # Parse date
            schedule_dt = datetime.strptime(schedule_date, '%Y-%m-%d')
            
            # Check if schedule already exists
            existing = self.get_schedule_by_date(schedule_date)
            if existing:
                return {
                    'success': False,
                    'message': f'Schedule already exists for {schedule_date}',
                    'schedule_id': existing['id']
                }
            
            # Reset rotation
            self._reset_rotation()
            
            # Create schedule record
            schedule_id = self._create_schedule_record(
                schedule_date=schedule_dt.date(),
                schedule_name=schedule_name or f"Daily Schedule - {schedule_date}"
            )
            
            if not schedule_id:
                return {
                    'success': False,
                    'message': 'Failed to create schedule record'
                }
            
            # Build the schedule
            scheduled_items = []
            total_duration = 0
            sequence_number = 1
            scheduled_asset_ids = []
            
            # Track which assets we've scheduled in this session
            # to update their last_scheduled_date in real-time
            scheduled_updates = {}
            
            while total_duration < self.target_duration_seconds:
                # Get next duration category
                duration_category = self._get_next_duration_category()
                
                # Get available content
                available_content = self.get_available_content(
                    duration_category, 
                    exclude_ids=scheduled_asset_ids
                )
                
                if not available_content:
                    logger.warning(f"No available content for category: {duration_category}")
                    continue
                
                # Select the best content (first in the list due to our ordering)
                content = available_content[0]
                
                # Calculate scheduled time
                scheduled_start = self._seconds_to_time(total_duration)
                
                # Add to schedule
                item = {
                    'schedule_id': schedule_id,
                    'asset_id': content['asset_id'],
                    'instance_id': content['instance_id'],
                    'sequence_number': sequence_number,
                    'scheduled_start_time': scheduled_start,
                    'scheduled_duration_seconds': content['duration_seconds']
                }
                
                scheduled_items.append(item)
                scheduled_asset_ids.append(content['asset_id'])
                scheduled_updates[content['asset_id']] = datetime.now()
                
                # Update totals
                total_duration += float(content['duration_seconds'])
                sequence_number += 1
                
                # Immediately update the last_scheduled_date for this asset
                self._update_asset_last_scheduled(content['asset_id'], datetime.now())
                
                # Log progress
                if sequence_number % 10 == 0:
                    logger.info(f"Scheduled {sequence_number} items, duration: {total_duration/3600:.2f} hours")
            
            # Save all scheduled items
            saved_count = self._save_scheduled_items(scheduled_items)
            
            # Update schedule total duration
            self._update_schedule_duration(schedule_id, total_duration)
            
            logger.info(f"Created schedule with {saved_count} items, total duration: {total_duration/3600:.2f} hours")
            
            return {
                'success': True,
                'message': f'Successfully created schedule for {schedule_date}',
                'schedule_id': schedule_id,
                'total_items': saved_count,
                'total_duration_hours': total_duration / 3600
            }
            
        except Exception as e:
            logger.error(f"Error creating daily schedule: {str(e)}")
            return {
                'success': False,
                'message': f'Error creating schedule: {str(e)}'
            }
    
    def add_item_to_schedule(self, schedule_id: int, asset_id: str, order_index: int = 0, 
                           scheduled_start_time: str = '00:00:00', scheduled_duration_seconds: float = 0) -> bool:
        """Add a single item to an existing schedule"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get asset information
            cursor.execute("""
                SELECT 
                    a.id as asset_id,
                    i.id as instance_id,
                    a.duration_seconds,
                    i.file_name
                FROM assets a
                JOIN instances i ON a.id = i.asset_id
                WHERE a.id = %s
                ORDER BY i.created_at DESC
                LIMIT 1
            """, (asset_id,))
            
            asset = cursor.fetchone()
            if not asset:
                logger.error(f"Asset not found: {asset_id}")
                return False
            
            # Insert schedule item
            cursor.execute("""
                INSERT INTO scheduled_items (
                    schedule_id, asset_id, instance_id, sequence_number,
                    scheduled_start_time, scheduled_duration_seconds, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                schedule_id,
                asset['asset_id'],
                asset['instance_id'],
                order_index + 1,  # sequence_number is 1-based
                scheduled_start_time,
                scheduled_duration_seconds or asset['duration_seconds'],
                datetime.now()
            ))
            
            conn.commit()
            cursor.close()
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding item to schedule: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)
    
    def recalculate_schedule_times(self, schedule_id: int) -> bool:
        """Recalculate start times for all items in a schedule"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get all items in the schedule ordered by sequence
            cursor.execute("""
                SELECT id, scheduled_duration_seconds
                FROM scheduled_items
                WHERE schedule_id = %s
                ORDER BY sequence_number
            """, (schedule_id,))
            
            items = cursor.fetchall()
            
            # Update start times
            current_time = 0  # Start at midnight (0 seconds)
            
            for item in items:
                # Convert seconds to time string
                hours = int(current_time // 3600)
                minutes = int((current_time % 3600) // 60)
                seconds = int(current_time % 60)
                start_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                # Update the item
                cursor.execute("""
                    UPDATE scheduled_items
                    SET scheduled_start_time = %s
                    WHERE id = %s
                """, (start_time, item['id']))
                
                # Add duration for next item
                current_time += float(item['scheduled_duration_seconds'])
            
            # Update total duration in schedule
            cursor.execute("""
                UPDATE schedules
                SET total_duration_seconds = %s
                WHERE id = %s
            """, (current_time, schedule_id))
            
            conn.commit()
            cursor.close()
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error recalculating schedule times: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)
    
    def create_empty_schedule(self, schedule_date: str, schedule_name: str = None) -> Dict[str, Any]:
        """Create an empty schedule without auto-filling content"""
        try:
            # Parse date
            schedule_dt = datetime.strptime(schedule_date, '%Y-%m-%d')
            
            # Check if schedule already exists
            existing = self.get_schedule_by_date(schedule_date)
            if existing:
                return {
                    'success': False,
                    'message': f'Schedule already exists for {schedule_date}',
                    'schedule_id': existing['id']
                }
            
            # Create schedule record
            schedule_id = self._create_schedule_record(
                schedule_date=schedule_dt.date(),
                schedule_name=schedule_name or f"Daily Schedule - {schedule_date}"
            )
            
            if not schedule_id:
                return {
                    'success': False,
                    'message': 'Failed to create schedule record'
                }
            
            return {
                'success': True,
                'schedule_id': schedule_id,
                'message': 'Empty schedule created successfully'
            }
            
        except Exception as e:
            logger.error(f"Error creating empty schedule: {str(e)}")
            return {
                'success': False,
                'message': str(e)
            }
    
    def _create_schedule_record(self, schedule_date, schedule_name: str) -> Optional[int]:
        """Create a schedule record in the database"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO schedules (
                    schedule_name, air_date, channel, active, created_date
                ) VALUES (
                    %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                schedule_name,
                schedule_date,
                'Comcast Channel 26',
                True,
                datetime.now()
            ))
            
            result = cursor.fetchone()
            schedule_id = result['id'] if result else None
            conn.commit()
            cursor.close()
            
            return schedule_id
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating schedule record: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
        finally:
            db_manager._put_connection(conn)
    
    def _save_scheduled_items(self, items: List[Dict[str, Any]]) -> int:
        """Save scheduled items to the database"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            saved_count = 0
            for item in items:
                cursor.execute("""
                    INSERT INTO scheduled_items (
                        schedule_id, asset_id, instance_id, sequence_number,
                        scheduled_start_time, scheduled_duration_seconds, status
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    item['schedule_id'],
                    item['asset_id'],
                    item['instance_id'],
                    item['sequence_number'],
                    item['scheduled_start_time'],
                    item['scheduled_duration_seconds'],
                    'scheduled'
                ))
                saved_count += 1
            
            conn.commit()
            cursor.close()
            
            return saved_count
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving scheduled items: {str(e)}")
            return 0
        finally:
            db_manager._put_connection(conn)
    
    def _update_asset_last_scheduled(self, asset_id: int, scheduled_date: datetime):
        """Update the last scheduled date for an asset"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Update or insert scheduling metadata
            cursor.execute("""
                INSERT INTO scheduling_metadata (asset_id, last_scheduled_date, total_airings)
                VALUES (%s, %s, 1)
                ON CONFLICT (asset_id) DO UPDATE SET
                    last_scheduled_date = EXCLUDED.last_scheduled_date,
                    total_airings = scheduling_metadata.total_airings + 1
            """, (asset_id, scheduled_date))
            
            conn.commit()
            cursor.close()
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating asset last scheduled: {str(e)}")
        finally:
            db_manager._put_connection(conn)
    
    def _update_schedule_duration(self, schedule_id: int, total_seconds: float):
        """Update the total duration of a schedule"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE schedules 
                SET total_duration_seconds = %s 
                WHERE id = %s
            """, (total_seconds, schedule_id))
            
            conn.commit()
            cursor.close()
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating schedule duration: {str(e)}")
        finally:
            db_manager._put_connection(conn)
    
    def _seconds_to_time(self, total_seconds: float) -> str:
        """Convert seconds to HH:MM:SS format"""
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        
        # Handle overflow past 24 hours
        hours = hours % 24
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get list of active schedules"""
        if not db_manager.connected:
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    s.*,
                    COUNT(si.id) as item_count,
                    SUM(si.scheduled_duration_seconds) as total_duration
                FROM schedules s
                LEFT JOIN scheduled_items si ON s.id = si.schedule_id
                WHERE s.active = TRUE
                GROUP BY s.id
                ORDER BY s.air_date DESC
                LIMIT 30
            """)
            
            results = cursor.fetchall()
            cursor.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting active schedules: {str(e)}")
            return []
        finally:
            db_manager._put_connection(conn)
    
    def get_schedule_by_date(self, schedule_date: str) -> Optional[Dict[str, Any]]:
        """Get schedule for a specific date"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM schedules 
                WHERE air_date = %s::date 
                AND channel = 'Comcast Channel 26'
                LIMIT 1
            """, (schedule_date,))
            
            result = cursor.fetchone()
            cursor.close()
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting schedule by date: {str(e)}")
            return None
        finally:
            db_manager._put_connection(conn)
    
    def get_schedule_items(self, schedule_id: int) -> List[Dict[str, Any]]:
        """Get all items in a schedule"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    si.*,
                    a.content_type,
                    a.content_title,
                    a.duration_category,
                    a.engagement_score,
                    i.file_name,
                    i.file_path,
                    sm.last_scheduled_date
                FROM scheduled_items si
                JOIN assets a ON si.asset_id = a.id
                JOIN instances i ON si.instance_id = i.id
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE si.schedule_id = %s
                ORDER BY si.sequence_number
            """, (schedule_id,))
            
            results = cursor.fetchall()
            cursor.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting schedule items: {str(e)}")
            return []
        finally:
            db_manager._put_connection(conn)
    
    def get_schedule_by_id(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        """Get schedule by ID with all items"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get schedule info
            cursor.execute("""
                SELECT 
                    s.id,
                    s.air_date,
                    s.schedule_name,
                    s.channel,
                    s.created_date,
                    s.notes,
                    COUNT(si.id) as total_items,
                    COALESCE(SUM(si.scheduled_duration_seconds), 0) as total_duration
                FROM schedules s
                LEFT JOIN scheduled_items si ON s.id = si.schedule_id
                WHERE s.id = %s
                GROUP BY s.id, s.air_date, s.schedule_name, s.channel, s.created_date, s.notes
            """, (schedule_id,))
            
            schedule_info = cursor.fetchone()
            
            if not schedule_info:
                cursor.close()
                return None
            
            # Get schedule items
            items = self.get_schedule_items(schedule_id)
            
            cursor.close()
            
            # Format response
            return {
                'id': schedule_info['id'],
                'air_date': schedule_info['air_date'],
                'schedule_name': schedule_info['schedule_name'],
                'channel': schedule_info['channel'],
                'total_items': int(schedule_info['total_items']),
                'total_duration': float(schedule_info['total_duration']),
                'created_date': schedule_info['created_date'],
                'notes': schedule_info['notes'],
                'items': items
            }
            
        except Exception as e:
            logger.error(f"Error getting schedule by ID: {str(e)}")
            return None
        finally:
            db_manager._put_connection(conn)
    
    def create_weekly_schedule(self, start_date: str) -> Dict[str, Any]:
        """Create schedules for an entire week (7 days)"""
        logger.info(f"Creating weekly schedule starting {start_date}")
        
        try:
            # Parse start date and ensure it's a Monday
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            
            created_schedules = []
            failed_days = []
            
            # Create schedules for 7 days
            for day_offset in range(7):
                current_date = start_date_obj + timedelta(days=day_offset)
                current_date_str = current_date.strftime('%Y-%m-%d')
                day_name = current_date.strftime('%A')
                
                logger.info(f"Creating schedule for {day_name} {current_date_str}")
                
                try:
                    # Create daily schedule
                    result = self.create_daily_schedule(current_date_str)
                    
                    if result['success']:
                        created_schedules.append({
                            'date': current_date_str,
                            'day_of_week': day_name,
                            'schedule_id': result.get('schedule_id'),
                            'total_items': result.get('schedule_details', {}).get('total_items', 0),
                            'total_duration': result.get('schedule_details', {}).get('total_duration', 0)
                        })
                        logger.info(f"✅ Created schedule for {day_name}")
                    else:
                        failed_days.append({
                            'date': current_date_str,
                            'day_of_week': day_name,
                            'error': result.get('message', 'Unknown error')
                        })
                        logger.warning(f"⚠️ Failed to create schedule for {day_name}: {result.get('message')}")
                        
                except Exception as e:
                    failed_days.append({
                        'date': current_date_str,
                        'day_of_week': day_name,
                        'error': str(e)
                    })
                    logger.error(f"Error creating schedule for {day_name}: {str(e)}")
            
            # Return results
            total_created = len(created_schedules)
            total_failed = len(failed_days)
            
            if total_created > 0:
                return {
                    'success': True,
                    'message': f'Created {total_created} schedule(s) for week starting {start_date}' + 
                              (f', {total_failed} failed' if total_failed > 0 else ''),
                    'created_schedules': created_schedules,
                    'failed_days': failed_days,
                    'total_created': total_created,
                    'total_failed': total_failed,
                    'week_start_date': start_date
                }
            else:
                return {
                    'success': False,
                    'message': f'Failed to create any schedules for week starting {start_date}',
                    'failed_days': failed_days
                }
                
        except Exception as e:
            error_msg = f"Error creating weekly schedule: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
    
    def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule and all its items"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Delete schedule (items will cascade)
            cursor.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))
            
            conn.commit()
            cursor.close()
            
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting schedule: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)


# Create global scheduler instance
scheduler_postgres = PostgreSQLScheduler()