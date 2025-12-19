#!/usr/bin/env python3
"""
Holiday Greeting Integration for scheduler_postgres.py
This module provides safe integration hooks without modifying core scheduling logic
"""

import logging
import json
import os
from typing import List, Dict, Optional, Any
from holiday_greeting_scheduler import get_holiday_scheduler
from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
from datetime import datetime

# Set up dedicated holiday greeting logger
holiday_logger = logging.getLogger('holiday_greeting')
holiday_logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Create file handler for holiday greeting logs
log_file = os.path.join(log_dir, f'holiday_greeting_{datetime.now().strftime("%Y%m%d")}.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add handler to logger
holiday_logger.addHandler(file_handler)

# Also keep the regular logger
logger = logging.getLogger(__name__)

class HolidayGreetingIntegration:
    """Safe integration wrapper for holiday greeting scheduling"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.config_file = 'holiday_greeting_config.json'
        self.scheduler = None
        self.enabled = False
        self._load_config_and_init()
        # Track greetings used in current scheduling session
        self.session_used_greetings = {}  # {duration_category: [asset_ids]}
        self.session_greeting_index = {}  # {duration_category: current_index}
        # Daily assignments manager
        self.daily_assignments = HolidayGreetingDailyAssignments(db_manager)
        self.current_schedule_id = None
        
        holiday_logger.info("=== HOLIDAY GREETING INTEGRATION INITIALIZED ===")
        holiday_logger.info(f"Enabled: {self.enabled}")
        holiday_logger.info(f"Config file: {self.config_file}")
        
    def _load_config_and_init(self):
        """Load configuration and initialize scheduler if enabled"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.enabled = config.get('enabled', False)
                    
                    if self.enabled:
                        self.scheduler = get_holiday_scheduler(self.db_manager)
                        # Override with config file settings
                        self.scheduler.config.update(config)
                        # Explicitly set enabled in the scheduler config
                        self.scheduler.config['enabled'] = True
                        logger.info("Holiday Greeting Fair Rotation: ENABLED")
                        logger.info(f"Scheduler config after update: enabled={self.scheduler.config.get('enabled')}")
                    else:
                        logger.info("Holiday Greeting Fair Rotation: DISABLED (config file exists but enabled=false)")
            else:
                logger.info("Holiday Greeting Fair Rotation: DISABLED (no config file)")
        except Exception as e:
            logger.error(f"Error loading holiday greeting config: {e}")
            self.enabled = False
    
    def reset_session(self):
        """Reset session tracking for a new scheduling run"""
        self.session_used_greetings = {}
        self.session_greeting_index = {}
        logger.info("Holiday greeting session tracking reset")
    
    def set_current_schedule(self, schedule_id: int):
        """Set the current schedule ID for daily assignments lookup"""
        self.current_schedule_id = schedule_id
        logger.info(f"Set current schedule ID to {schedule_id}")
    
    def filter_available_content(self, available_content: List[Dict[str, Any]], 
                               duration_category: str, 
                               exclude_ids: List[int],
                               schedule_date: str = None) -> List[Dict[str, Any]]:
        """
        Filter available content to ensure fair holiday greeting rotation
        
        This is the MAIN INTEGRATION POINT. When enabled, it:
        1. Removes ALL holiday greetings from the normal selection
        2. Selects ONE greeting using rotation (different each time)
        3. Returns the fair selection + all non-greeting content
        
        Args:
            available_content: List of content items from normal selection
            duration_category: The duration category being filled
            exclude_ids: Asset IDs already scheduled
            
        Returns:
            Filtered/modified content list
        """
        holiday_logger.info(f"=== FILTER CONTENT CALLED ===")
        holiday_logger.info(f"Category: {duration_category}, Available content: {len(available_content)}, Excluded IDs: {len(exclude_ids)}")
        holiday_logger.debug(f"filter_available_content called: category={duration_category}, available={len(available_content)}, exclude={len(exclude_ids)}")
        
        # Check if this is a content type or duration category
        duration_categories = ['id', 'spots', 'short_form', 'long_form']
        if duration_category not in duration_categories:
            # This is a content type, not a duration category
            # Holiday greetings don't apply to content types
            return available_content
        
        if not self.enabled:
            holiday_logger.debug("Holiday greeting filtering DISABLED")
            return available_content
            
        if not self.scheduler:
            holiday_logger.warning("Holiday greeting filtering enabled but scheduler not initialized")
            return available_content
        
        try:
            # Step 1: Remove ALL holiday greetings from the list
            other_content = []
            removed_greetings = []
            
            holiday_logger.debug(f"Checking {len(available_content)} items for holiday greetings")
            
            for content in available_content:
                file_name = content.get('file_name', '')
                content_title = content.get('content_title', '')
                is_greeting = self.scheduler.is_holiday_greeting(file_name, content_title)
                
                if is_greeting:
                    removed_greetings.append(content)
                    holiday_logger.debug(f"  - HOLIDAY GREETING: {file_name}")
                else:
                    other_content.append(content)
                    # Log first few non-greeting files to verify what we're checking
                    if len(other_content) <= 3:
                        holiday_logger.debug(f"  - NOT greeting: {file_name}")
            
            holiday_logger.info(f"Found {len(removed_greetings)} holiday greetings, {len(other_content)} other content")
            
            if removed_greetings:
                logger.info(f"Found {len(removed_greetings)} holiday greetings in {duration_category}")
                logger.info(f"Session tracking: {len(self.session_used_greetings.get(duration_category, []))} greetings used so far")
                holiday_logger.info(f"Removed greetings: {[g.get('file_name', 'unknown') for g in removed_greetings[:5]]}")
                # Debug: Check structure of greetings
                if removed_greetings:
                    sample = removed_greetings[0]
                    holiday_logger.info(f"Sample greeting structure: {list(sample.keys())}")
                    holiday_logger.info(f"Sample greeting asset_id: {sample.get('asset_id', 'NO ASSET_ID')}")
            
            # Step 2: Get the NEXT holiday greeting
            # First check if we have daily assignments for this schedule
            next_greeting = None
            
            if self.current_schedule_id and schedule_date:
                # Try to use daily assignments
                try:
                    schedule_date_obj = datetime.strptime(schedule_date, '%Y-%m-%d')
                    daily_asset_ids = self.daily_assignments.get_greetings_for_date(
                        self.current_schedule_id, schedule_date_obj
                    )
                    
                    if daily_asset_ids:
                        holiday_logger.info(f"Using daily assignments: {len(daily_asset_ids)} greetings for {schedule_date}")
                        # Get greeting details for the allowed asset IDs
                        next_greeting = self._get_greeting_from_daily_assignments(
                            daily_asset_ids, duration_category, exclude_ids
                        )
                except Exception as e:
                    logger.warning(f"Error using daily assignments: {e}, falling back to rotation")
            
            if not next_greeting:
                # Fall back to rotation method
                holiday_logger.info("Using rotation method (no daily assignments or none available)")
                next_greeting = self.get_next_holiday_greeting_rotation(
                    duration_category, 
                    exclude_ids,
                    None,  # Pass None to force database lookup of ALL greetings
                    schedule_date
                )
            
            # Step 3: Return our selected greeting + all non-greeting content
            if next_greeting:
                logger.info(f"ENHANCED ROTATION: Selected holiday greeting: {next_greeting.get('file_name')} "
                          f"(asset_id: {next_greeting.get('asset_id')})")
                return [next_greeting] + other_content
            else:
                # No suitable holiday greeting found, just return non-greeting content
                if removed_greetings:
                    logger.warning(f"ENHANCED ROTATION: Could not find suitable holiday greeting to replace {len(removed_greetings)} removed items")
                return other_content
            
        except Exception as e:
            logger.error(f"Error in holiday greeting filtering: {e}")
            # On error, return original list unchanged
            return available_content
    
    def get_next_holiday_greeting_rotation(self, duration_category: str,
                                          exclude_ids: List[int],
                                          available_greetings: List[Dict[str, Any]] = None,
                                          schedule_date: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the next holiday greeting in rotation for this duration category.
        This ensures variety within a single scheduling session.
        
        Args:
            duration_category: The duration category needed
            exclude_ids: Asset IDs to exclude (already scheduled in this timeslot)
            available_greetings: Pre-filtered greetings available for selection
            
        Returns:
            The next greeting in rotation, or None if no suitable greeting found
        """
        logger.info("=== ROTATION METHOD CALLED ===")
        holiday_logger.info("=== get_next_holiday_greeting_rotation CALLED ===")
        holiday_logger.info(f"Duration category: {duration_category}")
        holiday_logger.info(f"Exclude IDs: {exclude_ids}")
        holiday_logger.info(f"Available greetings passed in: {len(available_greetings) if available_greetings else 'None'}")
        
        # Initialize session tracking for this category if needed
        if duration_category not in self.session_used_greetings:
            self.session_used_greetings[duration_category] = []
            self.session_greeting_index[duration_category] = 0
            logger.info(f"Initialized session tracking for {duration_category}")
            holiday_logger.info(f"Initialized session tracking for {duration_category}")
        
        # Get all available greetings for this category
        if available_greetings is None:
            available_greetings = self._get_all_holiday_greetings(duration_category, schedule_date)
        
        # Filter out recently used in this session
        # NOTE: We intentionally DO NOT filter by exclude_ids here because:
        # 1. exclude_ids contains ALL assets scheduled in the entire schedule
        # 2. This prevents any holiday greeting from appearing more than once
        # 3. We want fair rotation WITHIN the schedule, not just one appearance
        session_used = self.session_used_greetings[duration_category]
        
        # Debug logging
        holiday_logger.info(f"Available greetings: {len(available_greetings)}")
        holiday_logger.info(f"Session used in {duration_category}: {len(session_used)}")
        holiday_logger.info(f"Exclude IDs count (IGNORED): {len(exclude_ids)}")
        if available_greetings:
            holiday_logger.info(f"First few greeting IDs: {[g['asset_id'] for g in available_greetings[:5]]}")
        
        # Only filter by session history to ensure variety within category
        # Allow reuse across different duration categories
        candidates = available_greetings
        
        holiday_logger.info(f"Candidates after filtering: {len(candidates)}")
        
        if not candidates:
            logger.warning(f"No available holiday greetings for {duration_category}")
            # Log why they were filtered
            if available_greetings:
                filtered_out = [g for g in available_greetings if g['asset_id'] in exclude_ids]
                holiday_logger.warning(f"All {len(filtered_out)} greetings were in exclude list: {[g['file_name'] for g in filtered_out[:5]]}")
            return None
        
        # Sort candidates by play count and last scheduled to ensure fairness
        candidates_with_stats = []
        for greeting in candidates:
            stats = self._get_greeting_stats(greeting['asset_id'])
            # Count how many times used in this session (across all categories)
            session_count = sum(1 for cat in self.session_used_greetings.values() 
                              for aid in cat if aid == greeting['asset_id'])
            candidates_with_stats.append({
                'greeting': greeting,
                'play_count': stats.get('scheduled_count', 0),
                'last_scheduled': stats.get('last_scheduled'),
                'session_count': session_count,
                'recently_used_in_category': greeting['asset_id'] in session_used[-5:] if session_used else False
            })
        
        # Sort by: 
        # 1. Not recently used in this category (last 5)
        # 2. Lowest session count (times used in current schedule)
        # 3. Lowest total play count (historical)
        # 4. Oldest last scheduled
        candidates_with_stats.sort(key=lambda x: (
            x['recently_used_in_category'],  # False comes before True
            x['session_count'],              # Fewer uses in session first
            x['play_count'],                 # Fewer historical plays
            x['last_scheduled'] is not None,  # Never scheduled comes first
            x['last_scheduled'] if x['last_scheduled'] else ''
        ))
        
        # Select the best candidate
        if candidates_with_stats:
            winner = candidates_with_stats[0]
            selected = winner['greeting']
            
            holiday_logger.info(f"SELECTED greeting: {selected.get('file_name')} "
                              f"(asset_id: {selected.get('asset_id')}, "
                              f"session_count: {winner['session_count']}, "
                              f"total_plays: {winner['play_count']}, "
                              f"recently_used: {winner['recently_used_in_category']})")
            
            # Log top 3 candidates for transparency
            holiday_logger.debug("Top 3 candidates:")
            for i, cand in enumerate(candidates_with_stats[:3]):
                holiday_logger.debug(f"  {i+1}. {cand['greeting']['file_name']} - "
                                   f"session: {cand['session_count']}, "
                                   f"total: {cand['play_count']}")
            
            # Track this selection in the session
            self.session_used_greetings[duration_category].append(selected['asset_id'])
            
            # If we've used all available greetings, allow reuse but maintain order
            available_count = len(candidates)
            if len(self.session_used_greetings[duration_category]) >= available_count * 2:
                # Keep only recent history to prevent memory bloat
                self.session_used_greetings[duration_category] = \
                    self.session_used_greetings[duration_category][-available_count:]
            
            return selected
        
        return None
    
    def _get_greeting_stats(self, asset_id: int) -> Dict[str, Any]:
        """Get scheduling stats for a holiday greeting"""
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT scheduled_count, last_scheduled
                FROM holiday_greeting_rotation
                WHERE asset_id = %s
            """, (asset_id,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return dict(result)
            return {'scheduled_count': 0, 'last_scheduled': None}
            
        except Exception as e:
            logger.error(f"Error getting greeting stats: {e}")
            return {'scheduled_count': 0, 'last_scheduled': None}
        finally:
            if conn:
                self.db_manager._put_connection(conn)
    
    def _get_all_holiday_greetings(self, duration_category: str, schedule_date: str = None) -> List[Dict[str, Any]]:
        """Get all holiday greetings for a duration category"""
        # Check if this is a content type or duration category
        duration_categories = ['id', 'spots', 'short_form', 'long_form']
        if duration_category not in duration_categories:
            # This is a content type, not a duration category
            # Holiday greetings don't apply to content types
            return []
        
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Use schedule_date if provided, otherwise current timestamp
            from datetime import datetime
            if schedule_date:
                try:
                    compare_date = datetime.strptime(schedule_date, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid schedule_date format: {schedule_date}, using current time")
                    compare_date = datetime.now()
            else:
                compare_date = datetime.now()
            
            cursor.execute("""
                SELECT 
                    a.id as asset_id,
                    i.id as instance_id,
                    i.file_name,
                    a.content_title,
                    a.duration_seconds,
                    a.duration_category
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE a.duration_category = %s
                  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
                  AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
                  AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                ORDER BY hgr.scheduled_count ASC, hgr.last_scheduled ASC NULLS FIRST
            """, (duration_category, compare_date, compare_date))
            
            greetings = cursor.fetchall()
            cursor.close()
            
            return [dict(g) for g in greetings]
            
        except Exception as e:
            logger.error(f"Error getting all holiday greetings: {e}")
            return []
        finally:
            if conn:
                self.db_manager._put_connection(conn)
    
    def get_best_holiday_greeting(self, duration_category: str, 
                                exclude_ids: List[int],
                                available_greetings: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Get the best holiday greeting to schedule based on fair rotation.
        
        Args:
            duration_category: The duration category needed
            exclude_ids: Asset IDs to exclude (already scheduled)
            available_greetings: Optional list of pre-filtered greetings
            
        Returns:
            The best greeting to schedule, or None
        """
        try:
            conn = self.db_manager._get_connection()
            cursor = conn.cursor()
            
            # Build the query to get all holiday greetings with their rotation info
            query = """
                SELECT 
                    a.id as asset_id,
                    COALESCE(i.file_name, '') as file_name,
                    a.content_title,
                    a.duration_seconds,
                    a.duration_category,
                    COALESCE(hgr.scheduled_count, 0) as scheduled_count,
                    hgr.last_scheduled,
                    -- Calculate priority score
                    CASE 
                        WHEN COALESCE(hgr.scheduled_count, 0) = 0 THEN 10000
                        ELSE 1.0 / (COALESCE(hgr.scheduled_count, 0) + 1) * 
                             (EXTRACT(EPOCH FROM (NOW() - COALESCE(hgr.last_scheduled, '2020-01-01'::timestamp))) / 3600)
                    END as priority_score
                FROM holiday_greeting_rotation hgr
                JOIN assets a ON hgr.asset_id = a.id
                LEFT JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                WHERE a.duration_category = %s
                AND a.id NOT IN %s
                ORDER BY 
                    scheduled_count ASC,
                    hgr.last_scheduled ASC NULLS FIRST,
                    priority_score DESC
                LIMIT 10
            """
            
            cursor.execute(query, (duration_category, tuple(exclude_ids) if exclude_ids else (0,)))
            candidates = cursor.fetchall()
            
            if not candidates:
                logger.warning(f"No holiday greetings available for {duration_category} category")
                return None
            
            # Select the best candidate (first one due to our ORDER BY)
            best = candidates[0]
            
            # Format as content item dict to match expected structure
            result = {
                'id': best[0],  # asset_id
                'asset_id': best[0],
                'file_name': best[1],
                'content_title': best[2],
                'duration_seconds': float(best[3]) if best[3] else 0,
                'duration_category': best[4],
                'scheduled_count': best[5],
                'priority_score': float(best[7]) if best[7] else 0
            }
            
            logger.info(f"Selected greeting: {result['file_name']} "
                       f"(count: {result['scheduled_count']}, score: {result['priority_score']:.2f})")
            
            # If we were given available_greetings, find the full object
            if available_greetings:
                for greeting in available_greetings:
                    if greeting.get('asset_id') == result['asset_id'] or greeting.get('id') == result['asset_id']:
                        # Return the full greeting object with all its properties
                        return greeting
            
            cursor.close()
            self.db_manager._put_connection(conn)
            return result
            
        except Exception as e:
            logger.error(f"Error getting best holiday greeting: {e}")
            if 'conn' in locals():
                self.db_manager._put_connection(conn)
            
            # Fallback: if we have available_greetings, pick the first one
            if available_greetings:
                logger.info("Falling back to first available greeting")
                return available_greetings[0]
            
            return None
    
    def record_scheduled_item(self, asset_id: int, file_name: str):
        """Record that a holiday greeting was scheduled"""
        if not self.enabled or not self.scheduler:
            return
        
        try:
            if self.scheduler.is_holiday_greeting(file_name):
                self.scheduler.record_scheduling(asset_id, file_name)
                self._update_database_tracking(asset_id)
        except Exception as e:
            logger.error(f"Error recording holiday greeting schedule: {e}")
    
    def _get_greeting_from_daily_assignments(self, daily_asset_ids: List[int], 
                                            duration_category: str,
                                            exclude_ids: List[int]) -> Optional[Dict[str, Any]]:
        """
        Get a greeting from the daily assignments that hasn't been used yet
        
        Args:
            daily_asset_ids: List of asset IDs allowed for this day
            duration_category: Duration category to match
            exclude_ids: Asset IDs already scheduled
            
        Returns:
            Greeting details or None if no suitable greeting found
        """
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Filter out already scheduled assets
            available_ids = [aid for aid in daily_asset_ids if aid not in exclude_ids]
            
            if not available_ids:
                holiday_logger.info("All daily assigned greetings already used in this timeslot")
                return None
            
            # Check if this is a content type or duration category
            duration_categories = ['id', 'spots', 'short_form', 'long_form']
            if duration_category not in duration_categories:
                # This is a content type, not a duration category
                # Holiday greetings don't apply to content types
                return None
            
            # Get details for the first available greeting
            placeholders = ','.join(['%s'] * len(available_ids))
            cursor.execute(f"""
                SELECT 
                    a.id as asset_id,
                    i.id as instance_id,
                    i.file_name,
                    a.content_title,
                    a.duration_seconds,
                    a.duration_category
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                WHERE a.id IN ({placeholders})
                AND a.duration_category = %s
                ORDER BY a.id
                LIMIT 1
            """, available_ids + [duration_category])
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return dict(result)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting greeting from daily assignments: {e}")
            return None
        finally:
            if conn:
                self.db_manager._put_connection(conn)
    
    def _update_database_tracking(self, asset_id: int):
        """Update the database tracking for scheduled holiday greeting"""
        if not self.db_manager:
            return
            
        try:
            conn = self.db_manager._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE holiday_greeting_rotation
                SET scheduled_count = scheduled_count + 1,
                    last_scheduled = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE asset_id = %s
                RETURNING scheduled_count
            """, (asset_id,))
            
            result = cursor.fetchone()
            new_count = result[0] if result else 0
            
            conn.commit()
            cursor.close()
            self.db_manager._put_connection(conn)
            
            logger.info(f"Updated holiday greeting tracking for asset {asset_id}, new count: {new_count}")
            
        except Exception as e:
            logger.error(f"Error updating holiday greeting database tracking: {e}")
            if 'conn' in locals():
                conn.rollback()
                self.db_manager._put_connection(conn)
    
    def get_status_report(self) -> str:
        """Get current status of holiday greeting rotation"""
        if not self.enabled:
            return "Holiday Greeting Fair Rotation: DISABLED"
        
        if self.scheduler:
            return self.scheduler.generate_rotation_report()
        
        return "Holiday Greeting Fair Rotation: ENABLED but not initialized"
    
    def get_current_distribution(self) -> Dict[str, Any]:
        """Get current distribution of holiday greeting scheduling"""
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    file_name,
                    scheduled_count,
                    last_scheduled
                FROM holiday_greeting_rotation
                ORDER BY scheduled_count DESC, file_name
            """)
            
            rows = cursor.fetchall()
            distribution = {}
            total_plays = 0
            
            for row in rows:
                file_name = row['file_name'].replace('251210_SSP_', '').replace('251209_SPP_', '').replace('.mp4', '')
                count = row['scheduled_count']
                last_scheduled = row['last_scheduled']
                    
                distribution[file_name] = {
                    'count': count,
                    'last_scheduled': last_scheduled.isoformat() if last_scheduled else 'Never'
                }
                total_plays += count
            
            cursor.close()
            
            return {
                'distribution': distribution,
                'total_plays': total_plays,
                'unique_greetings': len(distribution),
                'average_plays': total_plays / len(distribution) if distribution else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting distribution: {str(e)}", exc_info=True)
            return {}
        finally:
            if conn:
                self.db_manager._put_connection(conn)


# Example of how to modify scheduler_postgres.py:
"""
# Add this import at the top:
from holiday_greeting_integration import HolidayGreetingIntegration

# Add this in __init__ method:
self.holiday_integration = HolidayGreetingIntegration(self.db_manager)

# Modify _get_content_with_progressive_delays method - add this right before returning:
# Around line 380, after getting available_content but before returning it:

if available_content and self.holiday_integration.enabled:
    available_content = self.holiday_integration.filter_available_content(
        available_content, 
        duration_category, 
        exclude_ids
    )

# Add this after successfully scheduling an item (in add_to_schedule or similar):
if hasattr(self, 'holiday_integration'):
    self.holiday_integration.record_scheduled_item(asset_id, file_name)
"""