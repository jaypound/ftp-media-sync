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
import json

logger = logging.getLogger(__name__)


class PostgreSQLScheduler:
    def __init__(self):
        # Default rotation order
        self.duration_rotation = ['id', 'short_form', 'long_form', 'spots']
        self.rotation_index = 0
        self.target_duration_seconds = 24 * 60 * 60  # 24 hours in seconds
        self._config_loaded = False
    
    def _load_config_if_needed(self):
        """Load configuration on first use to avoid circular imports"""
        if not self._config_loaded:
            try:
                from config_manager import ConfigManager
                config_mgr = ConfigManager()
                scheduling_config = config_mgr.get_scheduling_settings()
                logger.info(f"Scheduling config loaded: {scheduling_config}")
                rotation_order = scheduling_config.get('rotation_order')
                if rotation_order:
                    self.duration_rotation = rotation_order
                    logger.info(f"Loaded rotation order from config: {rotation_order}")
                else:
                    logger.warning(f"No rotation_order in config, using default: {self.duration_rotation}")
                self._config_loaded = True
            except Exception as e:
                logger.warning(f"Could not load rotation config: {e}")
                self._config_loaded = True  # Don't try again
        
    def _get_next_duration_category(self) -> str:
        """Get the next duration category in rotation"""
        self._load_config_if_needed()
        category = self.duration_rotation[self.rotation_index]
        # Don't advance here - wait until content is actually scheduled
        return category
    
    def _advance_rotation(self):
        """Advance to the next category in rotation"""
        self.rotation_index = (self.rotation_index + 1) % len(self.duration_rotation)
    
    def _reset_rotation(self):
        """Reset the rotation index"""
        self.rotation_index = 0
    
    def _check_delay_constraint(self, asset_id: int, proposed_time: float, scheduled_times: dict, 
                               delay_hours: float) -> bool:
        """Check if scheduling an asset at proposed_time would violate delay constraints
        
        Args:
            asset_id: The asset to check
            proposed_time: When we want to schedule it (seconds from schedule start)
            scheduled_times: Dict of asset_id -> list of scheduled times
            delay_hours: Required delay between playbacks
            
        Returns:
            True if the asset can be scheduled, False if it would violate delay
        """
        if asset_id not in scheduled_times:
            return True  # Never scheduled, OK to use
        
        delay_seconds = delay_hours * 3600
        
        # Check each previous scheduling of this asset
        for scheduled_time in scheduled_times[asset_id]:
            time_diff = abs(proposed_time - scheduled_time)
            if time_diff < delay_seconds:
                logger.debug(f"Asset {asset_id} would violate delay: {time_diff/3600:.1f}h < {delay_hours}h")
                return False
        
        return True
    
    def update_rotation_order(self, rotation_order: List[str]):
        """Update the rotation order dynamically"""
        self.duration_rotation = rotation_order
        self.rotation_index = 0
        logger.info(f"Updated rotation order to: {rotation_order}")
    
    def get_available_content(self, duration_category: str, exclude_ids: List[int] = None, ignore_delays: bool = False, schedule_date: str = None) -> List[Dict[str, Any]]:
        """Get available content for a specific duration category or content type
        
        IMPORTANT: This method filters out expired content based on schedule date
        - If schedule_date is provided, only returns content where expiry_date > schedule_date
        - If no schedule_date, uses CURRENT_TIMESTAMP
        - Content with NULL expiry_date is treated as non-expiring
        
        Args:
            duration_category: The duration category (id, spots, short_form, long_form) or content type (AN, BMP, PSA, etc.) to filter by
            exclude_ids: List of asset IDs to exclude
            ignore_delays: If True, ignore replay delays (used as fallback)
            schedule_date: The date the content will be scheduled for (YYYY-MM-DD format)
        """
        # Ensure database is connected
        if hasattr(db_manager, 'connected') and not db_manager.connected:
            db_manager.connect()
        elif hasattr(db_manager, 'is_connected') and not db_manager.is_connected():
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get replay delay configuration - use defaults if config loading fails
            base_delay = 24  # Default 24 hours
            additional_delay = 2  # Default 2 hours per airing
            
            # If ignore_delays is True, set delays to 0
            if ignore_delays:
                logger.warning(f"No content available for {duration_category} with delays - retrying without delays")
                base_delay = 0
                additional_delay = 0
            else:
                try:
                    from config_manager import ConfigManager
                    config_mgr = ConfigManager()
                    scheduling_config = config_mgr.get_scheduling_settings()
                    replay_delays = scheduling_config.get('replay_delays', {})
                    additional_delays = scheduling_config.get('additional_delay_per_airing', {})
                    
                    # Get base delay and additional delay for this category
                    base_delay = replay_delays.get(duration_category, 24)
                    additional_delay = additional_delays.get(duration_category, 2)
                except Exception as e:
                    logger.warning(f"Could not load replay delay config, using defaults: {e}")
            
            # Determine if we're filtering by duration category or content type
            duration_categories = ['id', 'spots', 'short_form', 'long_form']
            is_duration_category = duration_category in duration_categories
            
            # Build the appropriate filter condition
            if is_duration_category:
                filter_condition = "a.duration_category = %(duration_category)s"
            else:
                filter_condition = "a.content_type = %(duration_category)s"
            
            # Build query to get available content
            query = f"""
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
                    i.encoded_date,
                    sm.last_scheduled_date,
                    sm.total_airings,
                    COALESCE(sm.content_expiry_date, CURRENT_TIMESTAMP + INTERVAL '1 year') as content_expiry_date,
                    -- Calculate required delay based on total airings
                    (%(base_delay)s + (COALESCE(sm.total_airings, 0) * %(additional_delay)s)) as required_delay_hours,
                    -- Calculate hours since last scheduled
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - COALESCE(sm.last_scheduled_date, '1970-01-01'::timestamp))) / 3600 as hours_since_last_scheduled
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE 
                    a.analysis_completed = TRUE
                    AND {filter_condition}
                    AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                    -- IMPORTANT: Filter out content that will be expired on the scheduled date
                    -- If no schedule_date provided, use current timestamp
                    -- Content with NULL expiry_date defaults to 1 year from schedule date (non-expiring)
                    AND COALESCE(sm.content_expiry_date, %(compare_date)s::timestamp + INTERVAL '1 year') > %(compare_date)s::timestamp
                    AND NOT (i.file_path LIKE %(fill_pattern)s)
                    -- Check replay delay: either never scheduled OR enough time has passed
                    -- Use scheduled date instead of current timestamp for accurate delay checking
                    AND (
                        sm.last_scheduled_date IS NULL 
                        OR EXTRACT(EPOCH FROM (%(compare_date)s::timestamp - sm.last_scheduled_date)) / 3600 >= (%(base_delay)s + (COALESCE(sm.total_airings, 0) * %(additional_delay)s))
                    )
                    -- Exclude assets that are disabled in any schedule
                    AND NOT EXISTS (
                        SELECT 1 FROM scheduled_items si
                        WHERE si.asset_id = a.id
                        AND si.available_for_scheduling = FALSE
                    )
            """
            
            # Determine the date to compare expiration against
            if schedule_date:
                # Parse the schedule date
                try:
                    compare_date = datetime.strptime(schedule_date, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid schedule_date format: {schedule_date}, using current time")
                    compare_date = datetime.now()
            else:
                compare_date = datetime.now()
            
            params = {
                'base_delay': base_delay,
                'additional_delay': additional_delay,
                'duration_category': duration_category,
                'fill_pattern': '%FILL%',
                'compare_date': compare_date
            }
            
            # Exclude already scheduled items
            if exclude_ids and len(exclude_ids) > 0:
                query += " AND a.id NOT IN %(exclude_ids)s"
                params['exclude_ids'] = tuple(exclude_ids)
            
            # Order by prioritizing newer content while respecting replay delays
            query += """
                ORDER BY 
                    -- First priority: Never scheduled content, newest first
                    CASE WHEN sm.last_scheduled_date IS NULL THEN 0 ELSE 1 END,
                    -- For never scheduled: newest encoded_date first
                    CASE WHEN sm.last_scheduled_date IS NULL THEN i.encoded_date END DESC NULLS LAST,
                    -- For scheduled content: least recently scheduled first
                    sm.last_scheduled_date ASC NULLS FIRST,
                    -- Then by fewest airings
                    sm.total_airings ASC NULLS FIRST,
                    -- Finally by engagement score
                    a.engagement_score DESC NULLS LAST
                LIMIT 50
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            
            # Return empty list if no results
            return results if results else []
            
        except Exception as e:
            logger.error(f"Error getting available content: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            if 'query' in locals():
                logger.error(f"Query: {query}")
            if 'params' in locals():
                logger.error(f"Params: {params}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
        finally:
            db_manager._put_connection(conn)
    
    def create_daily_schedule(self, schedule_date: str, schedule_name: str = None, max_errors: int = 100) -> Dict[str, Any]:
        """Create a daily schedule for the specified date"""
        try:
            # Force reload of configuration to ensure we have the latest rotation order
            self._config_loaded = False
            self._load_config_if_needed()
            
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
                schedule_name=schedule_name or f"Daily Schedule for {schedule_date}"
            )
            
            # Track all scheduled items with their air times to enforce delay logic
            # Key: asset_id, Value: list of scheduled timestamps (in seconds from start)
            scheduled_asset_times = {}
            
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
            
            # Error tracking
            consecutive_errors = 0
            total_errors = 0
            
            # Track which assets we've scheduled in this session
            # to update their last_scheduled_date in real-time
            scheduled_updates = {}
            
            while total_duration < self.target_duration_seconds:
                # Get next duration category
                duration_category = self._get_next_duration_category()
                
                # Get available content
                available_content = self.get_available_content(
                    duration_category, 
                    exclude_ids=scheduled_asset_ids,
                    schedule_date=schedule_date
                )
                
                # If no content available with delays, try without delays
                if not available_content:
                    logger.warning(f"No available content for category: {duration_category} with delays")
                    available_content = self.get_available_content(
                        duration_category, 
                        exclude_ids=scheduled_asset_ids,
                        ignore_delays=True,
                        schedule_date=schedule_date
                    )
                
                if not available_content:
                    logger.warning(f"No available content for category: {duration_category} even without delays")
                    consecutive_errors += 1
                    total_errors += 1
                    
                    # Check if we should abort
                    if consecutive_errors >= max_errors:
                        logger.error(f"Aborting schedule creation: {consecutive_errors} consecutive errors")
                        # Delete the partially created schedule
                        self.delete_schedule(schedule_id)
                        return {
                            'success': False,
                            'message': f'Schedule creation failed: No available content after {total_errors} attempts. Check content availability.',
                            'error_count': total_errors
                        }
                    continue
                
                # Select the best content (first in the list due to our ordering)
                content = available_content[0]
                consecutive_errors = 0  # Reset consecutive error counter
                
                # Get delay configuration for this content's duration category
                try:
                    from config_manager import ConfigManager
                    config_mgr = ConfigManager()
                    scheduling_config = config_mgr.get_scheduling_settings()
                    replay_delays = scheduling_config.get('replay_delays', {})
                    
                    # Get the delay for this content's duration category
                    content_duration_category = content.get('duration_category', 'long_form')
                    delay_hours = replay_delays.get(content_duration_category, 24)
                except:
                    delay_hours = 24  # Default to 24 hours if config fails
                
                # Check if this asset violates delay constraints
                if not self._check_delay_constraint(content['asset_id'], total_duration, 
                                                  scheduled_asset_times, delay_hours):
                    logger.info(f"Asset {content['asset_id']} would violate {delay_hours}h delay at {total_duration/3600:.1f}h")
                    # Try to find alternative content that respects delay
                    found_alternative = False
                    for alt_content in available_content[1:]:
                        # Check delay constraint for alternative
                        if self._check_delay_constraint(alt_content['asset_id'], total_duration,
                                                      scheduled_asset_times, delay_hours):
                            content = alt_content
                            logger.info(f"Using alternative content that respects delay")
                            found_alternative = True
                            break
                    
                    if not found_alternative:
                        # No suitable alternative found, skip this slot
                        logger.warning(f"No content available that respects delay constraints")
                        continue
                
                # Check if this content would cross midnight
                content_duration = float(content['duration_seconds'])
                remaining_seconds = self.target_duration_seconds - total_duration
                
                if content_duration > remaining_seconds:
                    # This item would exceed 24 hours
                    # Try to find shorter content that would fit
                    found_fitting_content = False
                    for alt_content in available_content[1:]:  # Skip the first item we already tried
                        alt_duration = float(alt_content['duration_seconds'])
                        if alt_duration <= remaining_seconds:
                            # Found content that fits!
                            content = alt_content
                            content_duration = alt_duration
                            found_fitting_content = True
                            logger.info(f"Found alternative content that fits in remaining {remaining_seconds/60:.1f} minutes")
                            break
                    
                    if not found_fitting_content:
                        # No content fits in remaining time
                        logger.info(f"No content fits in remaining {remaining_seconds/60:.1f} minutes, stopping at {total_duration/3600:.2f} hours")
                        break
                
                # Calculate scheduled time
                # For daily schedules, ensure time stays within 24 hours
                scheduled_start = self._seconds_to_time(total_duration % (24 * 60 * 60))
                
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
                
                # Track when this asset is scheduled (for delay enforcement)
                if content['asset_id'] not in scheduled_asset_times:
                    scheduled_asset_times[content['asset_id']] = []
                scheduled_asset_times[content['asset_id']].append(total_duration)
                
                # Update totals
                total_duration += content_duration
                
                # Add one frame gap between items (29.976 fps)
                frame_gap = 1.0 / 29.976  # approximately 0.033367 seconds
                total_duration += frame_gap
                
                sequence_number += 1
                
                # Advance rotation after successfully scheduling content
                self._advance_rotation()
                
                # Calculate actual air time for this item
                # The item starts at (total_duration - content_duration) seconds from schedule start
                actual_air_time = schedule_dt + timedelta(seconds=total_duration - content_duration)
                
                # Update the asset's last scheduled date with actual air time
                self._update_asset_last_scheduled(content['asset_id'], actual_air_time)
                
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
                           scheduled_start_time: str = '00:00:00', scheduled_duration_seconds: float = 0, 
                           metadata: Dict[str, Any] = None) -> bool:
        """Add a single item to an existing schedule"""
        logger.debug(f"add_item_to_schedule: scheduled_start_time='{scheduled_start_time}' (type: {type(scheduled_start_time)})")
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Special handling for live inputs (asset_id = 0 or None)
            if (str(asset_id) == '0' or asset_id is None) and metadata and metadata.get('is_live_input'):
                logger.info(f"Adding live input item: {metadata.get('title', 'Live Input')}")
                
                # First, ensure we have a placeholder asset for live inputs
                cursor.execute("""
                    SELECT id FROM assets WHERE guid = '00000000-0000-0000-0000-000000000000'
                """)
                placeholder = cursor.fetchone()
                
                if not placeholder:
                    # Create placeholder asset if it doesn't exist
                    cursor.execute("""
                        INSERT INTO assets (guid, content_title, content_type, duration_seconds, duration_category, created_at)
                        VALUES ('00000000-0000-0000-0000-000000000000', 'Live Input Placeholder', 'other', 0, 'spots', %s)
                        RETURNING id
                    """, (datetime.now(),))
                    placeholder = cursor.fetchone()
                    logger.info(f"Created placeholder asset for live inputs with id: {placeholder['id']}")
                
                live_input_asset_id = placeholder['id']
                logger.info(f"Using placeholder asset_id {live_input_asset_id} for live input")
                
                # Check if scheduled_items table has metadata column
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='scheduled_items' AND column_name='metadata'
                """)
                result = cursor.fetchone()
                has_metadata_column = result is not None
                
                if has_metadata_column:
                    # Insert live input with NULL asset_id to avoid foreign key constraint
                    cursor.execute("""
                        INSERT INTO scheduled_items (
                            schedule_id, asset_id, instance_id, sequence_number,
                            scheduled_start_time, scheduled_duration_seconds, metadata, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        schedule_id,
                        live_input_asset_id,  # Use placeholder asset_id for live inputs
                        None,  # No instance_id for live inputs
                        order_index + 1,  # sequence_number is 1-based
                        scheduled_start_time,
                        scheduled_duration_seconds or metadata.get('duration_seconds', 3600),  # Default 1 hour
                        json.dumps(metadata),
                        datetime.now()
                    ))
                else:
                    # Insert without metadata
                    cursor.execute("""
                        INSERT INTO scheduled_items (
                            schedule_id, asset_id, instance_id, sequence_number,
                            scheduled_start_time, scheduled_duration_seconds, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        schedule_id,
                        live_input_asset_id,  # Use placeholder asset_id for live inputs
                        None,  # No instance_id for live inputs
                        order_index + 1,  # sequence_number is 1-based
                        scheduled_start_time,
                        scheduled_duration_seconds or metadata.get('duration_seconds', 3600),  # Default 1 hour
                        datetime.now()
                    ))
                
                conn.commit()
                return True
            
            # Regular asset handling
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
            
            # Check if scheduled_items table has metadata column
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='scheduled_items' AND column_name='metadata'
            """)
            result = cursor.fetchone()
            has_metadata_column = result is not None
            
            if has_metadata_column and metadata:
                # Insert with metadata
                cursor.execute("""
                    INSERT INTO scheduled_items (
                        schedule_id, asset_id, instance_id, sequence_number,
                        scheduled_start_time, scheduled_duration_seconds, metadata, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    schedule_id,
                    asset['asset_id'],
                    asset['instance_id'],
                    order_index + 1,  # sequence_number is 1-based
                    scheduled_start_time,
                    scheduled_duration_seconds or asset['duration_seconds'],
                    json.dumps(metadata) if metadata else None,
                    datetime.now()
                ))
            else:
                # Insert without metadata (backward compatibility)
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
        """Recalculate start times for all items in a schedule with frame-accurate gaps"""
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
            
            # Update start times with frame-accurate gaps
            current_time = 0.0  # Start at midnight (0 seconds)
            fps = 29.976  # NTSC frame rate
            frame_duration = 1.0 / fps  # One frame duration in seconds (approximately 0.033367)
            
            for idx, item in enumerate(items):
                # Convert seconds to time string with microseconds
                hours = int(current_time // 3600)
                minutes = int((current_time % 3600) // 60)
                seconds_total = current_time % 60
                seconds = int(seconds_total)
                microseconds = int((seconds_total - seconds) * 1000000)
                
                # Format as HH:MM:SS.microseconds for PostgreSQL TIME type
                start_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}.{microseconds:06d}"
                
                # Update the item
                cursor.execute("""
                    UPDATE scheduled_items
                    SET scheduled_start_time = %s
                    WHERE id = %s
                """, (start_time, item['id']))
                
                # Add duration plus one frame gap for next item
                duration = float(item['scheduled_duration_seconds'])
                current_time += duration
                
                # Add one frame gap between items (except after the last item)
                if idx < len(items) - 1:
                    current_time += frame_duration
            
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
            
            # Note: Removed check for existing schedule to allow multiple schedules per day
            
            # Create schedule record
            schedule_id = self._create_schedule_record(
                schedule_date=schedule_dt.date(),
                schedule_name=schedule_name or f"Daily Schedule for {schedule_date}"
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
        """Convert seconds to HH:MM:SS.microseconds format"""
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        
        # For weekly schedules, don't wrap hours past 24
        # The calling code should handle day boundaries
        
        # Format with microsecond precision to avoid truncation
        whole_seconds = int(seconds)
        microseconds = int((seconds - whole_seconds) * 1000000)
        
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{microseconds:06d}"
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get list of active schedules"""
        if not db_manager.connected:
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get all schedules, not just active ones, for reporting purposes
            cursor.execute("""
                SELECT 
                    s.id,
                    s.schedule_name as name,
                    s.air_date,
                    s.created_date as created_at,
                    s.active,
                    s.total_duration_seconds,
                    COUNT(si.id) as total_items,
                    SUM(si.scheduled_duration_seconds) as total_duration
                FROM schedules s
                LEFT JOIN scheduled_items si ON s.id = si.schedule_id
                WHERE s.air_date >= CURRENT_DATE - INTERVAL '60 days'
                GROUP BY s.id, s.schedule_name, s.air_date, s.created_date, s.active, s.total_duration_seconds
                ORDER BY s.created_date DESC
                LIMIT 200
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
            
            # Check if scheduled_items table has metadata column
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='scheduled_items' AND column_name='metadata'
            """)
            result = cursor.fetchone()
            has_metadata_column = result is not None
            
            if has_metadata_column:
                cursor.execute("""
                    SELECT 
                        si.*,
                        a.content_type,
                        CASE 
                            WHEN a.guid = '00000000-0000-0000-0000-000000000000' AND si.metadata->>'title' IS NOT NULL 
                            THEN si.metadata->>'title'
                            ELSE a.content_title
                        END as content_title,
                        a.duration_category,
                        a.engagement_score,
                        a.summary,
                        a.theme,
                        COALESCE(i.file_name, si.metadata->>'file_name') as file_name,
                        COALESCE(i.file_path, si.metadata->>'file_path') as file_path,
                        i.encoded_date,
                        sm.last_scheduled_date,
                        sm.total_airings,
                        si.metadata,
                        a.guid
                    FROM scheduled_items si
                    LEFT JOIN assets a ON si.asset_id = a.id
                    LEFT JOIN instances i ON si.instance_id = i.id
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE si.schedule_id = %s
                    ORDER BY si.sequence_number
                """, (schedule_id,))
            else:
                cursor.execute("""
                    SELECT 
                        si.*,
                        a.content_type,
                        a.content_title,
                        a.duration_category,
                        a.engagement_score,
                        a.summary,
                        a.theme,
                        i.file_name,
                        i.file_path,
                        i.encoded_date,
                        sm.last_scheduled_date,
                        sm.total_airings,
                        a.guid
                    FROM scheduled_items si
                    LEFT JOIN assets a ON si.asset_id = a.id
                    LEFT JOIN instances i ON si.instance_id = i.id
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE si.schedule_id = %s
                    ORDER BY si.sequence_number
                """, (schedule_id,))
            
            results = cursor.fetchall()
            
            # Debug: Check what we're getting from DB
            if results and len(results) > 0:
                logger.debug(f"get_schedule_items - First 3 items from DB:")
                for i, r in enumerate(results[:3]):
                    st = r.get('scheduled_start_time')
                    logger.debug(f"  Item {i}: scheduled_start_time={st}, type={type(st)}, repr={repr(st)}")
                    if hasattr(st, 'microsecond'):
                        logger.debug(f"    microsecond={st.microsecond}")
                
                # Fetch topics for all items
                asset_ids = [r['asset_id'] for r in results if r.get('asset_id')]
                if asset_ids:
                    cursor.execute("""
                        SELECT 
                            at.asset_id,
                            t.tag_name
                        FROM asset_tags at
                        JOIN tags t ON at.tag_id = t.id
                        JOIN tag_types tt ON t.tag_type_id = tt.id
                        WHERE at.asset_id = ANY(%s) AND tt.type_name = 'topic'
                    """, (asset_ids,))
                    
                    topics_by_asset = {}
                    for tag_row in cursor.fetchall():
                        asset_id = tag_row['asset_id']
                        if asset_id not in topics_by_asset:
                            topics_by_asset[asset_id] = []
                        topics_by_asset[asset_id].append(tag_row['tag_name'])
                    
                    # Add topics to results
                    for result in results:
                        asset_id = result.get('asset_id')
                        if asset_id and asset_id in topics_by_asset:
                            result['topics'] = topics_by_asset[asset_id]
                        else:
                            result['topics'] = []
            
            cursor.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting schedule items: {str(e)}")
            return []
        finally:
            db_manager._put_connection(conn)
    
    def reorder_schedule_items(self, schedule_id: int, old_position: int, new_position: int) -> bool:
        """Reorder items in a schedule by updating sequence numbers"""
        if not db_manager.connected:
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # First get all items for this schedule ordered by sequence
            cursor.execute("""
                SELECT id, sequence_number 
                FROM scheduled_items 
                WHERE schedule_id = %s 
                ORDER BY sequence_number
            """, (schedule_id,))
            
            items = cursor.fetchall()
            if not items or old_position >= len(items) or new_position >= len(items):
                return False
            
            # Log items for debugging
            logger.info(f"Fetched {len(items)} items for schedule {schedule_id}")
            logger.debug(f"Items before reorder: {items[:5]}...")  # Log first 5 items
            
            # Reorder the items in memory
            item_to_move = items.pop(old_position)
            items.insert(new_position, item_to_move)
            
            # Update sequence numbers for all affected items
            for new_seq, item in enumerate(items):
                # Handle both dict and tuple formats since cursor might be RealDictCursor
                if isinstance(item, dict):
                    item_id = item['id']
                else:
                    item_id = item[0]
                
                cursor.execute("""
                    UPDATE scheduled_items 
                    SET sequence_number = %s 
                    WHERE id = %s
                """, (new_seq + 1, item_id))
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Successfully reordered items in schedule {schedule_id}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error reordering schedule items: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)
    
    def delete_schedule_item(self, schedule_id: int, item_id: int) -> bool:
        """Delete a single item from a schedule and resequence remaining items"""
        if not db_manager.connected:
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            # Use RealDictCursor for consistency
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # First get the asset_id of the item to be deleted
            cursor.execute("""
                SELECT asset_id 
                FROM scheduled_items 
                WHERE id = %s AND schedule_id = %s
            """, (item_id, schedule_id))
            
            result = cursor.fetchone()
            if not result:
                logger.warning(f"No item found with id {item_id} in schedule {schedule_id}")
                return False
            
            asset_id = result['asset_id']
            
            # Delete the item
            cursor.execute("""
                DELETE FROM scheduled_items 
                WHERE id = %s AND schedule_id = %s
            """, (item_id, schedule_id))
            
            # Decrement total_airings for this asset
            cursor.execute("""
                UPDATE scheduling_metadata
                SET total_airings = GREATEST(0, total_airings - 1)
                WHERE asset_id = %s
            """, (asset_id,))
            
            logger.info(f"Decremented total_airings for asset {asset_id}")
            
            # Resequence remaining items
            cursor.execute("""
                WITH numbered_items AS (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY sequence_number) as new_seq
                    FROM scheduled_items
                    WHERE schedule_id = %s
                )
                UPDATE scheduled_items si
                SET sequence_number = ni.new_seq
                FROM numbered_items ni
                WHERE si.id = ni.id AND si.schedule_id = %s
            """, (schedule_id, schedule_id))
            
            # Update schedule total duration
            cursor.execute("""
                UPDATE schedules 
                SET total_duration_seconds = (
                    SELECT COALESCE(SUM(scheduled_duration_seconds), 0)
                    FROM scheduled_items
                    WHERE schedule_id = %s
                )
                WHERE id = %s
            """, (schedule_id, schedule_id))
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Successfully deleted item {item_id} from schedule {schedule_id}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting schedule item: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)
    
    def toggle_item_availability(self, schedule_id: int, item_id: int, available: bool) -> bool:
        """Toggle the availability of a schedule item for future scheduling"""
        if not db_manager.connected:
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Update the availability field
            cursor.execute("""
                UPDATE scheduled_items 
                SET available_for_scheduling = %s
                WHERE id = %s AND schedule_id = %s
            """, (available, item_id, schedule_id))
            
            if cursor.rowcount == 0:
                logger.warning(f"No item found with id {item_id} in schedule {schedule_id}")
                return False
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Successfully updated availability for item {item_id} to {available}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error toggling item availability: {str(e)}")
            return False
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
            # Force reload of configuration to ensure we have the latest rotation order
            self._config_loaded = False
            self._load_config_if_needed()
            
            # Parse start date and ensure it's a Sunday
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            
            # Adjust to previous Sunday if not already Sunday
            if start_date_obj.weekday() != 6:  # 6 is Sunday in Python
                # Go back to the previous Sunday
                days_since_sunday = (start_date_obj.weekday() + 1) % 7
                start_date_obj = start_date_obj - timedelta(days=days_since_sunday)
                logger.info(f"Adjusted start date to Sunday: {start_date_obj.strftime('%Y-%m-%d')}")
            
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
        """Delete a schedule and all its items, decrementing total_airings for each scheduled asset"""
        conn = db_manager._get_connection()
        try:
            # Use RealDictCursor to get results as dictionaries
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # First, get all items in this schedule and count occurrences
            query = """
                SELECT asset_id, COUNT(*) as count
                FROM scheduled_items
                WHERE schedule_id = %s
                GROUP BY asset_id
            """
            logger.debug(f"Executing query: {query} with schedule_id={schedule_id}")
            cursor.execute(query, (schedule_id,))
            
            asset_counts = cursor.fetchall()
            logger.debug(f"Found {len(asset_counts)} unique assets in schedule {schedule_id}")
            
            # Decrement total_airings for each asset
            for i, row in enumerate(asset_counts):
                try:
                    # Access dictionary keys instead of numeric indices
                    asset_id = row['asset_id']
                    count = row['count']
                    
                    logger.debug(f"Row {i}: asset_id={asset_id} (type: {type(asset_id)}), count={count} (type: {type(count)})")
                    
                    if asset_id is None:
                        logger.warning(f"Skipping NULL asset_id with count {count}")
                        continue
                    
                    if not isinstance(asset_id, (int, float)):
                        logger.error(f"Invalid asset_id type: {type(asset_id)}, value: {asset_id}")
                        continue
                        
                    cursor.execute("""
                        UPDATE scheduling_metadata
                        SET total_airings = GREATEST(0, total_airings - %s)
                        WHERE asset_id = %s
                    """, (count, asset_id))
                    logger.info(f"Decremented total_airings by {count} for asset {asset_id}")
                except Exception as e:
                    logger.error(f"Error processing row {i}: {str(e)}, row data: {row}")
                    raise
            
            # Delete schedule (items will cascade)
            cursor.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Deleted schedule {schedule_id} and updated airings for {len(asset_counts)} assets")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting schedule: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)
    
    def create_single_weekly_schedule(self, start_date: str, schedule_name: str = None, max_errors: int = 100) -> Dict[str, Any]:
        """Create a single weekly schedule containing 7 days of content"""
        logger.info(f"Creating single weekly schedule starting {start_date}")
        
        try:
            # Parse start date and ensure it's a Sunday
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            
            # Adjust to Sunday if not already
            if start_date_obj.weekday() != 6:  # 6 is Sunday in Python
                days_until_sunday = (6 - start_date_obj.weekday()) % 7
                start_date_obj = start_date_obj + timedelta(days=days_until_sunday)
                logger.info(f"Adjusted start date to Sunday: {start_date_obj.strftime('%Y-%m-%d')}")
            
            # Check if schedule already exists for this week
            existing = self.get_schedule_by_date(start_date_obj.strftime('%Y-%m-%d'))
            if existing:
                return {
                    'success': False,
                    'message': f'Weekly schedule already exists for week starting {start_date_obj.strftime("%Y-%m-%d")}',
                    'schedule_id': existing['id']
                }
            
            # Create schedule record
            # Calculate end date (Saturday)
            end_date_obj = start_date_obj + timedelta(days=6)
            
            schedule_id = self._create_schedule_record(
                schedule_date=start_date_obj.date(),
                schedule_name=schedule_name or f"Weekly Schedule: {start_date_obj.strftime('%Y-%m-%d')} - {end_date_obj.strftime('%Y-%m-%d')}"
            )
            
            if not schedule_id:
                return {
                    'success': False,
                    'message': 'Failed to create schedule record'
                }
            
            # Build the weekly schedule (7 days of content)
            scheduled_items = []
            total_duration = 0
            sequence_number = 1
            scheduled_asset_ids = []
            
            # Error tracking
            consecutive_errors = 0
            total_errors = 0
            
            # Track all scheduled items with their air times to enforce delay logic
            # Key: asset_id, Value: list of scheduled timestamps (in seconds from start)
            scheduled_asset_times = {}
            
            # Generate content for each day
            for day_offset in range(7):
                current_day = start_date_obj + timedelta(days=day_offset)
                day_name = current_day.strftime('%A')
                logger.info(f"Generating content for {day_name}")
                
                # Reset rotation for each day
                self._reset_rotation()
                
                # Track assets scheduled on current day (for duplicate prevention within day)
                day_scheduled_asset_ids = []
                
                # Target 24 hours per day
                day_start_seconds = day_offset * 24 * 60 * 60
                day_target_seconds = (day_offset + 1) * 24 * 60 * 60
                
                while total_duration < day_target_seconds:
                    # Get next duration category
                    duration_category = self._get_next_duration_category()
                    
                    # Get available content
                    available_content = self.get_available_content(
                        duration_category, 
                        exclude_ids=day_scheduled_asset_ids,
                        schedule_date=current_day.strftime('%Y-%m-%d')
                    )
                    
                    # If no content available with delays, try without delays
                    if not available_content:
                        logger.warning(f"No available content for category: {duration_category} with delays")
                        available_content = self.get_available_content(
                            duration_category, 
                            exclude_ids=day_scheduled_asset_ids,
                            ignore_delays=True,
                            schedule_date=current_day.strftime('%Y-%m-%d')
                        )
                    
                    if not available_content:
                        logger.warning(f"No available content for category: {duration_category} even without delays")
                        consecutive_errors += 1
                        total_errors += 1
                        
                        # Check if we should abort
                        if consecutive_errors >= max_errors:
                            logger.error(f"Aborting schedule creation: {consecutive_errors} consecutive errors")
                            # Delete the partially created schedule
                            self.delete_schedule(schedule_id)
                            return {
                                'success': False,
                                'message': f'Schedule creation failed: No available content after {total_errors} attempts. Check content availability.',
                                'error_count': total_errors
                            }
                        continue
                    
                    # Select the best content
                    content = available_content[0]
                    consecutive_errors = 0  # Reset consecutive error counter
                    
                    # Check if this content would cross into the next day
                    content_duration = float(content['duration_seconds'])
                    remaining_seconds = day_target_seconds - total_duration
                    
                    if content_duration > remaining_seconds:
                        # This item would cross into the next day
                        # Try to find shorter content that would fit
                        found_fitting_content = False
                        for alt_content in available_content[1:]:  # Skip the first item we already tried
                            alt_duration = float(alt_content['duration_seconds'])
                            if alt_duration <= remaining_seconds:
                                # Found content that fits!
                                content = alt_content
                                content_duration = alt_duration
                                found_fitting_content = True
                                logger.info(f"Found alternative content that fits in remaining {remaining_seconds/60:.1f} minutes")
                                break
                        
                        if not found_fitting_content:
                            # No content fits in remaining time, move to next day
                            logger.info(f"No content fits in remaining {remaining_seconds/60:.1f} minutes on {day_name}, moving to next day")
                            # IMPORTANT: Advance total_duration to the start of the next day
                            # This ensures the next item starts at midnight, not in the gap
                            total_duration = day_target_seconds
                            break
                    
                    # Calculate scheduled time within the week
                    # For weekly schedules, we need to show the actual day/time
                    # Convert total_duration to the day of week and time
                    days_elapsed = int(total_duration // (24 * 60 * 60))
                    time_in_day = total_duration % (24 * 60 * 60)
                    scheduled_start = self._seconds_to_time(time_in_day)
                    
                    # Debug logging
                    logger.debug(f"Item {sequence_number}: total_duration={total_duration:.6f}, time_in_day={time_in_day:.6f}, scheduled_start={scheduled_start}, duration={content_duration:.6f}")
                    
                    # Track when this asset is scheduled (for delay enforcement)
                    if content['asset_id'] not in scheduled_asset_times:
                        scheduled_asset_times[content['asset_id']] = []
                    scheduled_asset_times[content['asset_id']].append(total_duration)
                    
                    # Log delay tracking info
                    if len(scheduled_asset_times[content['asset_id']]) > 1:
                        prev_time = scheduled_asset_times[content['asset_id']][-2]
                        time_since_last = (total_duration - prev_time) / 3600
                        logger.info(f"Asset {content['asset_id']} scheduled again after {time_since_last:.1f}h (delay requirement: {delay_hours}h)")
                    
                    # Add to schedule
                    item = {
                        'schedule_id': schedule_id,
                        'asset_id': content['asset_id'],
                        'instance_id': content['instance_id'],
                        'sequence_number': sequence_number,
                        'scheduled_start_time': scheduled_start,
                        'scheduled_duration_seconds': content_duration  # Use the exact duration we used for calculations
                    }
                    
                    scheduled_items.append(item)
                    scheduled_asset_ids.append(content['asset_id'])
                    day_scheduled_asset_ids.append(content['asset_id'])
                    
                    # Update totals
                    total_duration += content_duration
                    sequence_number += 1
                    
                    # Advance rotation after successfully scheduling content
                    self._advance_rotation()
                    
                    # Calculate actual air time for this item
                    # The item starts at (total_duration - content_duration) seconds from schedule start
                    actual_air_time = start_date_obj + timedelta(seconds=total_duration - content_duration)
                    
                    # Update the asset's last scheduled date with actual air time
                    self._update_asset_last_scheduled(content['asset_id'], actual_air_time)
                    
                    # Stop if we've filled the current day
                    if total_duration >= day_target_seconds:
                        break
                
                # Log day completion with info about content reuse
                day_items = len(day_scheduled_asset_ids)
                reused_items = day_items - len(set(day_scheduled_asset_ids))
                logger.info(f"Completed {day_name} with {day_items} items ({reused_items} repeated within day)")
                if day_offset > 0:
                    logger.info(f"Content can be reused from previous days for variety across the week")
            
            # Debug: Log first few items to check time format
            if scheduled_items:
                logger.debug("First 5 scheduled items before saving:")
                for i, item in enumerate(scheduled_items[:5]):
                    logger.debug(f"  Item {i+1}: start_time={item['scheduled_start_time']}, duration={item['scheduled_duration_seconds']:.6f}s, type={type(item['scheduled_start_time'])}")
            
            # Save all scheduled items
            saved_count = self._save_scheduled_items(scheduled_items)
            
            # Update schedule total duration
            self._update_schedule_duration(schedule_id, total_duration)
            
            logger.info(f"Created weekly schedule with {saved_count} items, total duration: {total_duration/3600:.2f} hours")
            
            return {
                'success': True,
                'message': f'Successfully created weekly schedule starting {start_date_obj.strftime("%Y-%m-%d")}',
                'schedule_id': schedule_id,
                'total_items': saved_count,
                'total_duration_hours': total_duration / 3600,
                'schedule_type': 'weekly'
            }
            
        except Exception as e:
            logger.error(f"Error creating single weekly schedule: {str(e)}")
            return {
                'success': False,
                'message': f'Error creating weekly schedule: {str(e)}'
            }
    
    def create_monthly_schedule(self, year: int, month: int, max_errors: int = 100) -> Dict[str, Any]:
        """Create a monthly schedule for the specified year and month"""
        logger.info(f"Creating monthly schedule for {year}-{month:02d}")
        
        try:
            # Force reload of configuration to ensure we have the latest rotation order
            self._config_loaded = False
            self._load_config_if_needed()
            
            # Calculate start and end dates for the month
            start_date = datetime(year, month, 1)
            
            # Calculate last day of the month
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            
            days_in_month = end_date.day
            
            # Check if schedule already exists for this month
            existing = self.get_schedule_by_date(start_date.strftime('%Y-%m-%d'))
            if existing:
                return {
                    'success': False,
                    'message': f'Monthly schedule already exists for {start_date.strftime("%B %Y")}',
                    'schedule_id': existing['id']
                }
            
            # Create schedule record
            schedule_name = f"Monthly Schedule for {start_date.strftime('%B %Y')}"
            schedule_id = self._create_schedule_record(
                schedule_date=start_date.date(),
                schedule_name=schedule_name
            )
            
            if not schedule_id:
                return {
                    'success': False,
                    'message': 'Failed to create schedule record'
                }
            
            # Build the monthly schedule
            scheduled_items = []
            total_duration = 0
            sequence_number = 1
            scheduled_asset_ids = []
            
            # Error tracking
            consecutive_errors = 0
            total_errors = 0
            
            # Generate content for each day of the month
            for day in range(1, days_in_month + 1):
                current_date = datetime(year, month, day)
                day_name = current_date.strftime('%A')
                logger.info(f"Generating content for {day_name}, {current_date.strftime('%B %d')}")
                
                # Reset rotation for each day
                self._reset_rotation()
                
                # Reset scheduled assets for each day
                day_scheduled_asset_ids = []
                
                # Target 24 hours per day
                day_start_seconds = (day - 1) * 24 * 60 * 60
                day_target_seconds = day * 24 * 60 * 60
                
                while total_duration < day_target_seconds:
                    # Get next duration category
                    duration_category = self._get_next_duration_category()
                    
                    # Get available content
                    available_content = self.get_available_content(
                        duration_category, 
                        exclude_ids=day_scheduled_asset_ids,
                        schedule_date=current_day.strftime('%Y-%m-%d')
                    )
                    
                    # If no content available with delays, try without delays
                    if not available_content:
                        logger.warning(f"No available content for category: {duration_category} with delays")
                        available_content = self.get_available_content(
                            duration_category, 
                            exclude_ids=day_scheduled_asset_ids,
                            ignore_delays=True,
                            schedule_date=current_day.strftime('%Y-%m-%d')
                        )
                    
                    if not available_content:
                        logger.warning(f"No available content for category: {duration_category} even without delays")
                        consecutive_errors += 1
                        total_errors += 1
                        
                        # Check if we should abort
                        if consecutive_errors >= max_errors:
                            logger.error(f"Aborting schedule creation: {consecutive_errors} consecutive errors")
                            # Delete the partially created schedule
                            self.delete_schedule(schedule_id)
                            return {
                                'success': False,
                                'message': f'Schedule creation failed: No available content after {total_errors} attempts. Check content availability.',
                                'error_count': total_errors
                            }
                        continue
                    
                    # Select the best content
                    content = available_content[0]
                    consecutive_errors = 0
                    
                    # Check if this content would cross into the next day
                    content_duration = float(content['duration_seconds'])
                    remaining_seconds = day_target_seconds - total_duration
                    
                    if content_duration > remaining_seconds:
                        # Try to find shorter content that would fit
                        found_fitting_content = False
                        for alt_content in available_content[1:]:
                            alt_duration = float(alt_content['duration_seconds'])
                            if alt_duration <= remaining_seconds:
                                content = alt_content
                                content_duration = alt_duration
                                found_fitting_content = True
                                logger.info(f"Found alternative content that fits in remaining {remaining_seconds/60:.1f} minutes")
                                break
                        
                        if not found_fitting_content:
                            # No content fits, advance to next day
                            logger.info(f"No content fits in remaining {remaining_seconds/60:.1f} minutes on day {day}, moving to next day")
                            total_duration = day_target_seconds
                            break
                    
                    # Calculate scheduled time
                    time_in_day = total_duration % (24 * 60 * 60)
                    scheduled_start = self._seconds_to_time(time_in_day)
                    
                    # Add to schedule
                    item = {
                        'schedule_id': schedule_id,
                        'asset_id': content['asset_id'],
                        'instance_id': content['instance_id'],
                        'sequence_number': sequence_number,
                        'scheduled_start_time': scheduled_start,
                        'scheduled_duration_seconds': content_duration
                    }
                    
                    scheduled_items.append(item)
                    scheduled_asset_ids.append(content['asset_id'])
                    day_scheduled_asset_ids.append(content['asset_id'])
                    
                    # Update totals
                    total_duration += content_duration
                    sequence_number += 1
                    
                    # Advance rotation after successfully scheduling content
                    self._advance_rotation()
                    
                    # Calculate actual air time for this item
                    # The item starts at (total_duration - content_duration) seconds from schedule start
                    actual_air_time = start_date + timedelta(seconds=total_duration - content_duration)
                    
                    # Update the asset's last scheduled date with actual air time
                    self._update_asset_last_scheduled(content['asset_id'], actual_air_time)
                    
                    # Stop if we've filled the current day
                    if total_duration >= day_target_seconds:
                        break
                
                # Log day completion
                day_items = len(day_scheduled_asset_ids)
                logger.info(f"Completed {current_date.strftime('%B %d')} with {day_items} items")
            
            # Save all scheduled items
            saved_count = self._save_scheduled_items(scheduled_items)
            
            # Update schedule total duration
            self._update_schedule_duration(schedule_id, total_duration)
            
            logger.info(f"Created monthly schedule with {saved_count} items, total duration: {total_duration/3600:.2f} hours")
            
            return {
                'success': True,
                'message': f'Successfully created monthly schedule for {start_date.strftime("%B %Y")}',
                'schedule_id': schedule_id,
                'total_items': saved_count,
                'total_duration_hours': total_duration / 3600,
                'days_count': days_in_month,
                'schedule_type': 'monthly'
            }
            
        except Exception as e:
            logger.error(f"Error creating monthly schedule: {str(e)}")
            return {
                'success': False,
                'message': f'Error creating monthly schedule: {str(e)}'
            }
    
    def update_schedule_metadata(self, schedule_id: int, metadata: Dict[str, Any]) -> bool:
        """Update schedule metadata"""
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Check if schedules table has metadata column
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='schedules' AND column_name='metadata'
            """)
            result = cursor.fetchone()
            has_metadata_column = result is not None
            
            if has_metadata_column:
                cursor.execute("""
                    UPDATE schedules 
                    SET metadata = %s
                    WHERE id = %s
                """, (json.dumps(metadata), schedule_id))
            else:
                # If no metadata column, we'll store the type in the name for now
                # Skip appending [WEEKLY] to the schedule name
                # The schedule name already indicates it's weekly
                pass
            
            conn.commit()
            cursor.close()
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating schedule metadata: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)


# Create global scheduler instance
scheduler_postgres = PostgreSQLScheduler()