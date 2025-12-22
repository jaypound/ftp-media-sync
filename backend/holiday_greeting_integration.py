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
from datetime import datetime, timedelta

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
        # Daily rotation pool - tracks which greetings to use for each date
        self.daily_rotation_pools = {}  # {date_str: [greeting_dicts]}
        self.daily_rotation_indexes = {}  # {date_str: current_index}
        # Daily assignments manager
        self.daily_assignments = HolidayGreetingDailyAssignments(db_manager)
        self.current_schedule_id = None
        
        holiday_logger.info("=== HOLIDAY GREETING INTEGRATION INITIALIZED ===")
        holiday_logger.info(f"Enabled: {self.enabled}")
        holiday_logger.info(f"Config file: {self.config_file}")
        
    def _load_config_and_init(self):
        """Load configuration and initialize scheduler if enabled"""
        try:
            logger.warning(f"[HOLIDAY DEBUG] Looking for config file: {self.config_file}")
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.enabled = config.get('enabled', False)
                    logger.warning(f"[HOLIDAY DEBUG] Config loaded, enabled={self.enabled}")
                    
                    if self.enabled:
                        self.scheduler = get_holiday_scheduler(self.db_manager)
                        # Override with config file settings
                        self.scheduler.config.update(config)
                        # Explicitly set enabled in the scheduler config
                        self.scheduler.config['enabled'] = True
                        logger.warning(f"[HOLIDAY DEBUG] Holiday Greeting Fair Rotation: ENABLED")
                        logger.info(f"Scheduler config after update: enabled={self.scheduler.config.get('enabled')}")
                    else:
                        logger.warning(f"[HOLIDAY DEBUG] Holiday Greeting Fair Rotation: DISABLED (config file exists but enabled=false)")
            else:
                logger.warning(f"[HOLIDAY DEBUG] Holiday Greeting Fair Rotation: DISABLED (no config file at {self.config_file})")
        except Exception as e:
            logger.error(f"[HOLIDAY DEBUG] Error loading holiday greeting config: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.enabled = False
    
    def reset_session(self):
        """Reset session tracking for a new scheduling run"""
        self.session_used_greetings = {}
        self.session_greeting_index = {}
        # Clear daily rotation pools to force reload with corrected logic
        self.daily_rotation_pools = {}
        self.daily_rotation_indexes = {}
        logger.info("Holiday greeting session tracking and daily pools reset")
    
    def auto_populate_daily_assignments(self, schedule_id: int, base_date, is_weekly: bool = False, meeting_dates_only: bool = False):
        """
        Auto-populate holiday_greetings_days table based on schedule
        
        Args:
            schedule_id: The schedule ID
            base_date: The start date of the schedule
            is_weekly: Whether this is a weekly schedule (7 days) or daily (1 day)
            meeting_dates_only: If True, only populate for days that have meetings
        """
        if not self.enabled or not self.db_manager:
            return
        
        logger.info(f"Auto-populating holiday greeting assignments for schedule {schedule_id}")
        logger.info(f"Base date: {base_date}, Is weekly: {is_weekly}, Meeting dates only: {meeting_dates_only}")
        
        conn = None
        try:
            conn = self.db_manager._get_connection()
            cursor = conn.cursor()
            
            # Determine date range
            days_to_populate = []
            
            if meeting_dates_only:
                # Get dates that have meetings in the schedule
                cursor.execute("""
                    SELECT DISTINCT DATE(start_datetime) as meeting_date
                    FROM schedule_items
                    WHERE schedule_id = %s
                    AND content_title ILIKE '%meeting%'
                    ORDER BY meeting_date
                """, (schedule_id,))
                
                meeting_rows = cursor.fetchall()
                days_to_populate = [row[0] for row in meeting_rows]
                
                if not days_to_populate:
                    logger.warning(f"No meetings found in schedule {schedule_id} for auto-population")
                    return
                    
                logger.info(f"Found meetings on {len(days_to_populate)} days")
            else:
                # Populate all days in the schedule range
                if is_weekly:
                    for i in range(7):
                        days_to_populate.append(base_date + timedelta(days=i))
                else:
                    days_to_populate = [base_date]
            
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
            if not all_greetings:
                logger.warning("No holiday greetings available for auto-population")
                return
            
            logger.info(f"Found {len(all_greetings)} holiday greetings for distribution")
            
            # Clear existing assignments for these dates
            for day_date in days_to_populate:
                cursor.execute("""
                    DELETE FROM holiday_greetings_days 
                    WHERE start_date = %s
                """, (day_date,))
            
            # Distribute greetings evenly
            greetings_per_day = min(4, len(all_greetings))
            usage_count = {g[0]: 0 for g in all_greetings}  # g[0] is asset_id
            
            for day_num, day_date in enumerate(days_to_populate):
                day_end = day_date + timedelta(days=1)
                
                # Sort by usage to ensure even distribution
                sorted_greetings = sorted(
                    all_greetings,
                    key=lambda x: usage_count[x[0]]
                )
                
                # Assign greetings for this day
                for i in range(greetings_per_day):
                    greeting = sorted_greetings[i]
                    cursor.execute("""
                        INSERT INTO holiday_greetings_days 
                        (asset_id, day_number, start_date, end_date)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        greeting[0],  # asset_id
                        day_num + 1,
                        day_date,
                        day_end
                    ))
                    usage_count[greeting[0]] += 1
            
            conn.commit()
            logger.info(f"Auto-populated holiday greetings for {len(days_to_populate)} days")
            logger.info(f"Days populated: {[d.strftime('%Y-%m-%d') for d in days_to_populate]}")
            
            # Clear cached pools to force reload
            self.daily_rotation_pools = {}
            self.daily_rotation_indexes = {}
            
        except Exception as e:
            logger.error(f"Error auto-populating holiday days: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                self.db_manager._put_connection(conn)
    
    def set_current_schedule(self, schedule_id: int):
        """Set the current schedule ID for daily assignments lookup"""
        self.current_schedule_id = schedule_id
        logger.info(f"Set current schedule ID to {schedule_id}")
    
    def filter_available_content(self, available_content: List[Dict[str, Any]], 
                               duration_category: str, 
                               exclude_ids: List[int],
                               schedule_date: str = None,
                               last_scheduled_theme: str = None) -> List[Dict[str, Any]]:
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
            schedule_date: The date being scheduled
            last_scheduled_theme: Theme of the last scheduled item (for conflict checking)
            
        Returns:
            Filtered/modified content list
        """
        holiday_logger.warning(f"=== FILTER CONTENT CALLED ===")
        holiday_logger.warning(f"Category: {duration_category}, Available content: {len(available_content)}, Excluded IDs: {len(exclude_ids)}")
        holiday_logger.warning(f"Schedule date passed: {schedule_date}")
        holiday_logger.warning(f"Current schedule_id: {getattr(self, 'current_schedule_id', 'NOT SET')}")
        holiday_logger.warning(f"Last scheduled theme: {last_scheduled_theme}")
        logger.warning(f"[HOLIDAY DEBUG] filter_available_content called with {len(available_content)} items")
        
        # Check if this is a content type or duration category
        duration_categories = ['id', 'spots', 'short_form', 'long_form']
        if duration_category not in duration_categories:
            # This is a content type, not a duration category
            # Holiday greetings don't apply to content types
            return available_content
        
        if not self.enabled:
            holiday_logger.warning("Holiday greeting filtering DISABLED - returning original content")
            logger.warning("[HOLIDAY DEBUG] Integration disabled, returning all content unchanged")
            return available_content
            
        if not self.scheduler:
            holiday_logger.warning("Holiday greeting filtering enabled but scheduler not initialized")
            logger.warning("[HOLIDAY DEBUG] No scheduler, returning all content unchanged")
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
                    # Normalize the content to ensure it has asset_id
                    if 'asset_id' not in content and 'id' in content:
                        content['asset_id'] = content['id']
                    removed_greetings.append(content)
                    holiday_logger.debug(f"  - HOLIDAY GREETING: {file_name}")
                else:
                    other_content.append(content)
                    # Log first few non-greeting files to verify what we're checking
                    if len(other_content) <= 3:
                        holiday_logger.debug(f"  - NOT greeting: {file_name}")
            
            holiday_logger.warning(f"[HOLIDAY DEBUG] Found {len(removed_greetings)} holiday greetings, {len(other_content)} other content")
            logger.warning(f"[HOLIDAY DEBUG] Removed {len(removed_greetings)} holiday greetings from pool")
            
            if removed_greetings:
                logger.info(f"Found {len(removed_greetings)} holiday greetings in {duration_category}")
                logger.info(f"Session tracking: {len(self.session_used_greetings.get(duration_category, []))} greetings used so far")
                holiday_logger.warning(f"[HOLIDAY DEBUG] Removed greetings: {[g.get('file_name', 'unknown') for g in removed_greetings[:5]]}")
                # Debug: Check structure of greetings
                if removed_greetings:
                    sample = removed_greetings[0]
                    holiday_logger.info(f"Sample greeting structure: {list(sample.keys())}")
                    holiday_logger.info(f"Sample greeting asset_id: {sample.get('asset_id', 'NO ASSET_ID')}")
            
            # Step 2: Get the NEXT holiday greeting
            next_greeting = None
            
            # For SPOTS category with a schedule date, use daily rotation pool
            if duration_category == 'spots' and schedule_date:
                holiday_logger.info(f"Checking daily rotation pool for {schedule_date}")
                next_greeting = self._get_next_from_daily_pool(schedule_date)
                
                if next_greeting:
                    holiday_logger.info(f"Selected from daily pool: {next_greeting.get('file_name')}")
                else:
                    holiday_logger.info("No daily pool available, falling back to standard rotation")
            
            # If no daily pool greeting, use standard rotation
            if not next_greeting:
                next_greeting = self.get_next_holiday_greeting_rotation(
                    duration_category, 
                    exclude_ids,
                    None,  # Pass None to force database lookup of ALL greetings
                    schedule_date,
                    last_scheduled_theme
                )
            
            # Step 3: Return ONLY our selected greeting (not all removed ones) + all non-greeting content
            if next_greeting:
                logger.warning(f"[HOLIDAY DEBUG] ENHANCED ROTATION: Selected holiday greeting: {next_greeting.get('file_name')} "
                          f"(asset_id: {next_greeting.get('asset_id')})")
                # IMPORTANT: Return ONLY the selected greeting, not all holiday greetings
                result = [next_greeting] + other_content
                logger.warning(f"[HOLIDAY DEBUG] Returning {len(result)} items: 1 selected greeting + {len(other_content)} non-greetings")
                holiday_logger.warning(f"[HOLIDAY DEBUG] Final result has {len(result)} items")
                return result
            else:
                # No suitable holiday greeting found, return non-greeting content only
                if removed_greetings:
                    logger.warning(f"[HOLIDAY DEBUG] ENHANCED ROTATION: Could not find suitable holiday greeting to replace {len(removed_greetings)} removed items")
                logger.warning(f"[HOLIDAY DEBUG] Returning {len(other_content)} non-greeting items (no greeting selected)")
                return other_content
            
        except Exception as e:
            logger.error(f"Error in holiday greeting filtering: {e}")
            # On error, return original list unchanged
            return available_content
    
    def get_next_holiday_greeting_rotation(self, duration_category: str,
                                          exclude_ids: List[int],
                                          available_greetings: List[Dict[str, Any]] = None,
                                          schedule_date: str = None,
                                          last_scheduled_theme: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the next holiday greeting in rotation for this duration category.
        This ensures variety within a single scheduling session.
        
        Args:
            duration_category: The duration category needed
            exclude_ids: Asset IDs to exclude (already scheduled in this timeslot)
            available_greetings: Pre-filtered greetings available for selection
            schedule_date: The date being scheduled (YYYY-MM-DD format)
            last_scheduled_theme: Theme of the last scheduled item (for conflict checking)
            
        Returns:
            The next greeting in rotation, or None if no suitable greeting found
        """
        logger.info("=== ROTATION METHOD CALLED ===")
        holiday_logger.info("=== get_next_holiday_greeting_rotation CALLED ===")
        holiday_logger.info(f"Duration category: {duration_category}")
        holiday_logger.info(f"Exclude IDs: {exclude_ids}")
        holiday_logger.info(f"Available greetings passed in: {len(available_greetings) if available_greetings else 'None'}")
        holiday_logger.info(f"Schedule date: {schedule_date}")
        
        # FIRST: Check daily rotation pool for this date
        if schedule_date and duration_category == 'spots':  # Daily assignments are only for spots
            next_greeting = self._get_next_from_daily_pool(schedule_date)
            if next_greeting:
                holiday_logger.info(f"Using daily rotation pool for {schedule_date}")
                return next_greeting
            else:
                holiday_logger.info(f"No daily assignments found for {schedule_date}, falling back to rotation")
        
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
        
        # Theme conflict check - only skip if the IMMEDIATELY PREVIOUS item has the same theme
        # AND it's a holiday greeting (not other content with same theme)
        if last_scheduled_theme and duration_category in ['spots', 'id', 'short_form']:
            # Check if last scheduled theme is "HolidayGreeting" - this means a holiday greeting was just placed
            if last_scheduled_theme.lower() == 'holidaygreeting':
                holiday_logger.warning(f"Last scheduled item was a holiday greeting (theme: {last_scheduled_theme})")
                holiday_logger.warning("Returning None to prevent back-to-back holiday greetings")
                return None
            
            # If last theme wasn't HolidayGreeting, we can place a holiday greeting
            holiday_logger.info(f"Last scheduled theme '{last_scheduled_theme}' is not a holiday greeting, OK to place one")
        
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
    
    def _get_or_init_daily_rotation_pool(self, schedule_date: str) -> List[Dict[str, Any]]:
        """
        Get or initialize the rotation pool for a specific date.
        This ensures we rotate through the same 4 greetings all day.
        
        Args:
            schedule_date: Date in YYYY-MM-DD format
            
        Returns:
            List of greetings to rotate through for this date
        """
        # Check if we already have a pool for this date
        if schedule_date in self.daily_rotation_pools:
            pool = self.daily_rotation_pools[schedule_date]
            # If the pool is empty, clear it and reinitialize
            if not pool:
                holiday_logger.info(f"Found EMPTY rotation pool for {schedule_date}, clearing and reinitializing")
                del self.daily_rotation_pools[schedule_date]
                if schedule_date in self.daily_rotation_indexes:
                    del self.daily_rotation_indexes[schedule_date]
            else:
                holiday_logger.info(f"Found existing rotation pool for {schedule_date} with {len(pool)} greetings")
                return pool
        
        # Initialize the pool with daily assignments
        holiday_logger.info(f"Initializing daily rotation pool for {schedule_date}")
        holiday_logger.info(f"Current pools in memory: {list(self.daily_rotation_pools.keys())}")
        
        # Get ALL assigned greetings for this date (ignore exclude_ids)
        assigned_greetings = self._get_daily_assigned_greetings(schedule_date, [])
        
        if assigned_greetings:
            holiday_logger.info(f"Created rotation pool with {len(assigned_greetings)} greetings for {schedule_date}")
            self.daily_rotation_pools[schedule_date] = assigned_greetings
            self.daily_rotation_indexes[schedule_date] = 0
            return assigned_greetings
        
        # No daily assignments - return empty list
        holiday_logger.warning(f"No daily assignments found for {schedule_date}")
        self.daily_rotation_pools[schedule_date] = []
        return []
    
    def _get_next_from_daily_pool(self, schedule_date: str) -> Optional[Dict[str, Any]]:
        """
        Get the next greeting from the daily rotation pool.
        Rotates through the pool evenly.
        
        Args:
            schedule_date: Date in YYYY-MM-DD format
            
        Returns:
            Next greeting from the pool, or None if pool is empty
        """
        pool = self._get_or_init_daily_rotation_pool(schedule_date)
        
        if not pool:
            return None
        
        # Get current index
        current_index = self.daily_rotation_indexes.get(schedule_date, 0)
        
        # Get the greeting at current index
        greeting = pool[current_index]
        
        # Move to next index (wrap around)
        next_index = (current_index + 1) % len(pool)
        self.daily_rotation_indexes[schedule_date] = next_index
        
        holiday_logger.info(f"Selected greeting {current_index + 1}/{len(pool)} from daily pool: {greeting.get('file_name')}")
        
        return greeting

    def _get_daily_assigned_greetings(self, schedule_date: str, exclude_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Get daily assigned greetings for a specific date
        
        Args:
            schedule_date: Date in YYYY-MM-DD format
            exclude_ids: Asset IDs to exclude (already used)
            
        Returns:
            List of assigned greetings not in exclude_ids
        """
        holiday_logger.info(f"=== _get_daily_assigned_greetings called for date: {schedule_date} ===")
        holiday_logger.info("=== _GET_DAILY_ASSIGNED_GREETINGS CALLED ===")
        holiday_logger.info(f"Schedule date: {schedule_date}")
        holiday_logger.info(f"Exclude IDs count: {len(exclude_ids)}")
        
        conn = None
        try:
            from psycopg2.extras import RealDictCursor
            from datetime import datetime
            
            # Parse the schedule date
            try:
                date_obj = datetime.strptime(schedule_date, '%Y-%m-%d').date()
                holiday_logger.info(f"Parsed date: {date_obj}")
            except ValueError:
                logger.warning(f"Invalid date format: {schedule_date}")
                holiday_logger.error(f"Failed to parse date: {schedule_date}")
                return []
            
            conn = self.db_manager._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # First check if there are ANY assignments for this date
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM holiday_greetings_days hgd
                JOIN assets a ON hgd.asset_id = a.id
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                WHERE hgd.start_date <= %s AND hgd.end_date > %s
            """, (date_obj, date_obj))
            
            count_result = cursor.fetchone()
            holiday_logger.info(f"Total assignments for {date_obj}: {count_result['count']}")
            
            # Query daily assignments for this date
            # No schedule_id needed - assignments are purely date-based
            cursor.execute("""
                SELECT 
                    hgd.asset_id,
                    a.id,
                    a.content_title,
                    i.file_name,
                    i.file_path,
                    a.duration_seconds,
                    a.duration_category,
                    a.content_type,
                    i.id as instance_id,
                    a.engagement_score,
                    a.created_at,
                    a.updated_at,
                    json_build_object(
                        'content_expiry_date', sm.content_expiry_date::text,
                        'featured', COALESCE(sm.featured, false),
                        'available_for_scheduling', COALESCE(sm.available_for_scheduling, true)
                    ) as scheduling
                FROM holiday_greetings_days hgd
                JOIN assets a ON hgd.asset_id = a.id
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE hgd.start_date <= %s 
                AND hgd.end_date > %s
                AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
                ORDER BY hgd.asset_id
            """, (date_obj, date_obj, date_obj))
            
            results = cursor.fetchall()
            cursor.close()
            
            greetings = []
            for r in results:
                greeting = dict(r)
                # Ensure both 'id' and 'asset_id' are present for compatibility
                if 'asset_id' in greeting and 'id' not in greeting:
                    greeting['id'] = greeting['asset_id']
                elif 'id' in greeting and 'asset_id' not in greeting:
                    greeting['asset_id'] = greeting['id']
                greetings.append(greeting)
                
            holiday_logger.info(f"Daily assignments query found {len(greetings)} greetings for {schedule_date}")
            
            # Also check how many were filtered out due to expiration
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT COUNT(*) as total_assigned,
                       SUM(CASE WHEN sm.content_expiry_date <= %s THEN 1 ELSE 0 END) as expired_count
                FROM holiday_greetings_days hgd
                JOIN assets a ON hgd.asset_id = a.id
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE hgd.start_date <= %s AND hgd.end_date > %s
            """, (date_obj, date_obj, date_obj))
            stats = cursor.fetchone()
            cursor.close()
            
            if stats['expired_count'] > 0:
                holiday_logger.warning(f"Filtered out {stats['expired_count']} expired greetings from {stats['total_assigned']} total assignments for {schedule_date}")
            
            if greetings:
                holiday_logger.info(f"Daily assigned greetings: {[g['file_name'] for g in greetings]}")
            else:
                # Debug why no assignments found
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT COUNT(*) as total, 
                           MIN(start_date) as min_date, 
                           MAX(start_date) as max_date
                    FROM holiday_greetings_days
                """)
                stats = cursor.fetchone()
                holiday_logger.warning(f"No assignments found for {date_obj}. Table has {stats['total']} total assignments")
                holiday_logger.warning(f"Date range in table: {stats['min_date']} to {stats['max_date']}")
                cursor.close()
            
            return greetings
            
        except Exception as e:
            logger.error(f"Error getting daily assigned greetings: {e}")
            return []
        finally:
            if conn:
                self.db_manager._put_connection(conn)
    
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
            
            # First check how many are in rotation table
            cursor.execute("SELECT COUNT(*) FROM holiday_greeting_rotation")
            total_in_rotation = cursor.fetchone()[0]
            holiday_logger.info(f"Total greetings in rotation table: {total_in_rotation}")
            
            cursor.execute("""
                SELECT 
                    a.id as asset_id,
                    a.id,
                    i.id as instance_id,
                    i.file_name,
                    i.file_path,
                    a.content_title,
                    a.duration_seconds,
                    a.duration_category,
                    a.content_type,
                    a.active,
                    a.engagement_score,
                    a.created_at,
                    a.updated_at,
                    a.theme,
                    json_build_object(
                        'content_expiry_date', sm.content_expiry_date::text,
                        'featured', COALESCE(sm.featured, false),
                        'available_for_scheduling', COALESCE(sm.available_for_scheduling, true)
                    ) as scheduling
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
            holiday_logger.info(f"Found {len(greetings)} greetings for category {duration_category} with date {compare_date}")
            
            # If no greetings found, check why
            if not greetings:
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM assets a
                    JOIN holiday_greeting_rotation hgr ON a.id = hgr.asset_id
                    WHERE a.duration_category = %s
                """, (duration_category,))
                category_count = cursor.fetchone()[0]
                holiday_logger.warning(f"No greetings found! {category_count} exist for {duration_category} in rotation table")
            
            cursor.close()
            
            # Normalize the results
            normalized_greetings = []
            for g in greetings:
                greeting = dict(g)
                # Ensure both 'id' and 'asset_id' are present for compatibility
                if 'asset_id' in greeting and 'id' not in greeting:
                    greeting['id'] = greeting['asset_id']
                elif 'id' in greeting and 'asset_id' not in greeting:
                    greeting['asset_id'] = greeting['id']
                    
                # Add theme to top level if not already there
                if 'theme' not in greeting and 'theme' in g:
                    greeting['theme'] = g['theme']
                    
                # Log if this greeting is expired
                if greeting.get('scheduling', {}).get('content_expiry_date'):
                    expiry_str = greeting['scheduling']['content_expiry_date']
                    try:
                        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d')
                        if expiry_date < compare_date:
                            holiday_logger.error(f"WARNING: Expired greeting included: {greeting['file_name']} expired on {expiry_str}")
                    except:
                        pass
                        
                normalized_greetings.append(greeting)
                
            return normalized_greetings
            
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