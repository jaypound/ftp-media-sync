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
import random
from holiday_greeting_integration import HolidayGreetingIntegration

logger = logging.getLogger(__name__)


class PostgreSQLScheduler:
    def __init__(self):
        # Default rotation order
        self.duration_rotation = ['id', 'short_form', 'long_form', 'spots']
        self.rotation_index = 0
        self.target_duration_seconds = 24 * 60 * 60  # 24 hours in seconds
        self._config_loaded = False
        
        # Defer holiday greeting integration initialization until database is ready
        self.holiday_integration = None
    
    def _ensure_holiday_integration(self):
        """Initialize holiday integration if not already done"""
        if self.holiday_integration is None:
            try:
                self.holiday_integration = HolidayGreetingIntegration(db_manager)
                logger.info(f"Holiday greeting integration initialized (enabled: {self.holiday_integration.enabled})")
            except Exception as e:
                logger.error(f"Failed to initialize holiday greeting integration: {e}")
                # Create a disabled integration as fallback
                self.holiday_integration = HolidayGreetingIntegration(None)
                self.holiday_integration.enabled = False
    
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
    
    def _should_schedule_featured_content(self, total_duration: float, last_featured_time: float, featured_delay: float) -> bool:
        """Check if it's time to schedule featured content
        
        Args:
            total_duration: Current total duration in seconds
            last_featured_time: Time when featured content was last scheduled (in seconds)
            featured_delay: Configured delay between featured content (in hours)
            
        Returns:
            True if featured content should be scheduled next
        """
        # Convert featured_delay from hours to seconds
        featured_delay_seconds = featured_delay * 3600
        
        # Check if enough time has passed since last featured content
        time_since_last_featured = total_duration - last_featured_time
        
        # Allow featured content immediately at the start (when last_featured_time is 0 and total_duration is small)
        # or after the delay has passed
        return time_since_last_featured >= featured_delay_seconds
    
    def _get_meeting_relevance_tier(self, meeting_date, schedule_date, config) -> str:
        """Determine the relevance tier for a meeting based on age
        
        Args:
            meeting_date: Date of the meeting (datetime or string)
            schedule_date: Date being scheduled (string YYYY-MM-DD)
            config: Meeting relevance configuration
            
        Returns:
            'fresh', 'relevant', 'archive', or 'expired'
        """
        from datetime import datetime
        
        # Convert dates to datetime objects if needed
        if isinstance(meeting_date, str):
            meeting_date = datetime.strptime(meeting_date[:10], '%Y-%m-%d')
        if isinstance(schedule_date, str):
            schedule_date = datetime.strptime(schedule_date, '%Y-%m-%d')
        
        # Calculate days since meeting
        days_old = (schedule_date - meeting_date).days
        
        # Determine tier
        if days_old < 0:
            return 'future'  # Meeting hasn't happened yet
        elif days_old <= config.get('fresh_days', 3):
            return 'fresh'
        elif days_old <= config.get('relevant_days', 7):
            return 'relevant'
        elif days_old <= config.get('archive_days', 14):
            return 'archive'
        else:
            return 'expired'
    
    def _should_auto_feature_content(self, content: Dict, schedule_date: str) -> bool:
        """Determine if content should be automatically featured
        
        Args:
            content: Content item dictionary
            schedule_date: Date being scheduled
            
        Returns:
            True if content should be featured
        """
        try:
            from config_manager import ConfigManager
            config_mgr = ConfigManager()
            scheduling_config = config_mgr.get_scheduling_settings()
            content_priorities = scheduling_config.get('content_priorities', {})
            meeting_config = scheduling_config.get('meeting_relevance', {})
            
            content_type = content.get('content_type', '')
            type_config = content_priorities.get(content_type, {})
            
            # Check if type is always featured
            if type_config.get('always_featured', False):
                return True
            
            # Check meeting relevance for MTG content
            if content_type == 'MTG' and type_config.get('auto_feature_days', 0) > 0:
                # Get meeting date from content
                meeting_date = content.get('meeting_date') or content.get('encoded_date')
                if meeting_date:
                    tier = self._get_meeting_relevance_tier(meeting_date, schedule_date, meeting_config)
                    return tier in ['fresh', 'relevant']
            
            # Check engagement-based featuring
            if type_config.get('engagement_based', False):
                engagement_score = content.get('engagement_score', 0)
                threshold = type_config.get('feature_threshold', 80)
                if engagement_score >= threshold:
                    return True
            
            # Check if manually marked as featured
            return content.get('featured', False)
            
        except Exception as e:
            logger.error(f"Error checking auto-feature status: {e}")
            return content.get('featured', False)
    
    def _is_daytime_slot(self, total_duration: float, config: Dict) -> bool:
        """Check if the current scheduling position is during daytime hours
        
        Args:
            total_duration: Current position in schedule (seconds from start)
            config: Featured content configuration
            
        Returns:
            True if position falls within daytime hours
        """
        # Calculate hour of day for this position
        hour_of_day = (total_duration / 3600) % 24
        
        daytime_start = config.get('daytime_hours', {}).get('start', 6)
        daytime_end = config.get('daytime_hours', {}).get('end', 18)
        
        return daytime_start <= hour_of_day < daytime_end
    
    def _should_prioritize_featured_for_daytime(self, total_duration: float, config: Dict) -> bool:
        """Determine if featured content should be prioritized for this time slot
        
        Args:
            total_duration: Current position in schedule (seconds)
            config: Featured content configuration
            
        Returns:
            True if featured content should be given priority
        """
        import random
        
        # Get daytime probability (default 75%)
        daytime_prob = config.get('daytime_probability', 0.75)
        
        # If we're in daytime, use the probability
        if self._is_daytime_slot(total_duration, config):
            return random.random() < daytime_prob
        else:
            # Outside daytime, use inverse probability
            return random.random() < (1 - daytime_prob)
    
    def get_featured_content(self, exclude_ids: List[int] = None, schedule_date: str = None) -> List[Dict[str, Any]]:
        """Get available featured content (both manually marked and auto-featured)
        
        Args:
            exclude_ids: List of asset IDs to exclude
            schedule_date: Date being scheduled (YYYY-MM-DD format)
            
        Returns:
            List of featured content items
        """
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get configuration for auto-featuring
            from config_manager import ConfigManager
            config_mgr = ConfigManager()
            scheduling_config = config_mgr.get_scheduling_settings()
            meeting_config = scheduling_config.get('meeting_relevance', {})
            content_priorities = scheduling_config.get('content_priorities', {})
            
            # Parse schedule date
            if schedule_date:
                schedule_date_obj = datetime.strptime(schedule_date, '%Y-%m-%d').date()
            else:
                schedule_date_obj = datetime.now().date()
            
            # Parameters for the query
            params = []
            
            # Build query to get featured content
            query = """
                SELECT 
                    a.id as asset_id,
                    a.guid,
                    a.content_type,
                    a.content_title,
                    a.duration_seconds,
                    a.duration_category,
                    a.engagement_score,
                    a.theme,
                    a.meeting_date,
                    i.id as instance_id,
                    i.file_name,
                    i.file_path,
                    i.encoded_date,
                    sm.last_scheduled_date,
                    sm.total_airings,
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = 'scheduling_metadata' 
                            AND column_name = 'featured'
                        ) THEN COALESCE(sm.featured, FALSE)
                        ELSE FALSE
                    END as featured,
                    sm.content_expiry_date,
                    sm.go_live_date
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE 
                    a.analysis_completed = TRUE
                    AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                    AND NOT (i.file_path LIKE %s)
            """
            params.append('%FILL%')
            
            # Don't filter by featured flag here - we'll check auto-featuring logic later
            # Get content types that might be featured
            from config_manager import ConfigManager
            config_mgr = ConfigManager()
            scheduling_config = config_mgr.get_scheduling_settings()
            content_priorities = scheduling_config.get('content_priorities', {})
            
            # Build list of content types that could be featured
            featurable_types = []
            for content_type, config in content_priorities.items():
                if config.get('always_featured') or config.get('engagement_based') or config.get('auto_feature_days'):
                    featurable_types.append(content_type)
            
            # Also include manually featured content
            if featurable_types:
                placeholders = ','.join(['%s'] * len(featurable_types))
                query += f"""
                    AND (
                        a.content_type IN ({placeholders})
                        OR CASE 
                            WHEN EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name = 'scheduling_metadata' 
                                AND column_name = 'featured'
                            ) THEN COALESCE(sm.featured, FALSE) = TRUE
                            ELSE FALSE
                        END
                    )
                """
                params.extend(featurable_types)
            
            # Add expiry date check
            if schedule_date:
                query += " AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s::date)"
                params.append(schedule_date)
            else:
                query += " AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)"
            
            # Add go live date check
            if schedule_date:
                query += " AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s::date)"
                params.append(schedule_date)
            else:
                query += " AND (sm.go_live_date IS NULL OR sm.go_live_date <= CURRENT_TIMESTAMP)"
            
            # Handle exclude_ids
            if exclude_ids and len(exclude_ids) > 0:
                placeholders = ','.join(['%s'] * len(exclude_ids))
                query += f" AND a.id NOT IN ({placeholders})"
                params.extend(exclude_ids)
            
            # Order by last scheduled date and engagement score
            query += """
                ORDER BY 
                    sm.last_scheduled_date ASC NULLS FIRST,
                    a.engagement_score DESC NULLS LAST,
                    RANDOM()
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            
            # Filter results to only include content that should be featured
            featured_results = []
            for content in results:
                if self._should_auto_feature_content(content, schedule_date):
                    featured_results.append(content)
            
            return featured_results
            
        except Exception as e:
            logger.error(f"Error getting featured content: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            db_manager._put_connection(conn)
        
        return []
    
    def _get_content_with_progressive_delays(self, duration_category: str, exclude_ids: List[int], 
                                            schedule_date: str, scheduled_asset_times: dict = None) -> List[Dict[str, Any]]:
        """Get available content, progressively relaxing delay requirements if needed
        
        This method tries to get content with increasingly relaxed delay requirements:
        1. Full delays (100%)
        2. 75% of configured delays
        3. 50% of configured delays
        4. 25% of configured delays
        5. No delays (0%)
        6. If still no content, reset category-specific exclusions and try again
        
        Returns:
            List of available content items
        """
        delay_factors = [1.0, 0.75, 0.5, 0.25, 0.0]
        
        for factor in delay_factors:
            if factor == 0.0:
                # For no delays, use the ignore_delays flag for backward compatibility
                available_content = self.get_available_content(
                    duration_category, 
                    exclude_ids=exclude_ids,
                    ignore_delays=True,
                    schedule_date=schedule_date,
                    scheduled_asset_times=scheduled_asset_times
                )
                if available_content:
                    logger.warning(f"⚠️ Found {len(available_content)} items for {duration_category} with NO delay restrictions - schedule quality may be impacted")
            else:
                available_content = self.get_available_content(
                    duration_category, 
                    exclude_ids=exclude_ids,
                    schedule_date=schedule_date,
                    delay_reduction_factor=factor,
                    scheduled_asset_times=scheduled_asset_times
                )
                if available_content and factor < 1.0:
                    logger.warning(f"⚠️ Found {len(available_content)} items for {duration_category} with REDUCED {factor*100:.0f}% delay requirements")
            
            if available_content:
                # Mark content items with the delay factor used to retrieve them
                for item in available_content:
                    item['_delay_factor_used'] = factor
                
                # Apply holiday greeting fair rotation filter if enabled
                self._ensure_holiday_integration()
                if hasattr(self, 'holiday_integration'):
                    logger.info(f"Holiday integration exists, enabled={self.holiday_integration.enabled}")
                    if self.holiday_integration.enabled:
                        logger.info(f"Applying holiday greeting filter for {duration_category}")
                        available_content = self.holiday_integration.filter_available_content(
                            available_content, 
                            duration_category, 
                            exclude_ids,
                            schedule_date
                        )
                    else:
                        logger.info("Holiday integration is disabled")
                else:
                    logger.warning("No holiday_integration attribute found")
                
                return available_content
        
        # No content found even with no delays - check if we can reset
        logger.error(f"❌ No content available for {duration_category} even with all delay restrictions removed")
        
        # Get all assets in this category to see what we're excluding
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get all asset IDs for this category
            cursor.execute("""
                SELECT a.id
                FROM assets a
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE a.duration_category = %s
                  AND a.analysis_completed = TRUE
                  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
                  AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
            """, (duration_category, schedule_date if schedule_date else datetime.now()))
            
            category_asset_ids = {row['id'] for row in cursor}
            cursor.close()
            
            if not category_asset_ids:
                logger.error(f"   No valid {duration_category} content in database (all expired or not analyzed)")
                return []
            
            # Find which category assets are being excluded
            excluded_category_assets = set(exclude_ids) & category_asset_ids
            
            logger.error(f"   Total {duration_category} content in database: {len(category_asset_ids)}")
            logger.error(f"   Excluded items from this category: {len(excluded_category_assets)}")
            
            # Check if we should reset - either all content is excluded OR we have excluded content but still can't find anything
            should_reset = False
            if excluded_category_assets:
                if len(excluded_category_assets) == len(category_asset_ids):
                    # All content in this category has been excluded
                    should_reset = True
                    logger.warning(f"🔄 All {duration_category} content is excluded - triggering reset")
                elif len(category_asset_ids) > 0:
                    # We have valid content but still can't get any - likely all blocked by other constraints
                    # If we've excluded at least 25% of the category, allow reset
                    exclusion_ratio = len(excluded_category_assets) / len(category_asset_ids)
                    if exclusion_ratio >= 0.25:
                        should_reset = True
                        logger.warning(f"🔄 {exclusion_ratio*100:.0f}% of {duration_category} content is excluded and nothing available - triggering reset")
            
            if should_reset:
                # RESET!
                logger.warning(f"🔄 RESETTING exclusions for {duration_category} content to allow reuse")
                logger.warning(f"   Removing {len(excluded_category_assets)} {duration_category} items from exclusion list")
                
                # Create a new exclude list without this category's assets
                reset_exclude_ids = [aid for aid in exclude_ids if aid not in excluded_category_assets]
                
                # Also reset the scheduled times for this category's assets to allow immediate reuse
                if scheduled_asset_times:
                    for asset_id in excluded_category_assets:
                        if asset_id in scheduled_asset_times:
                            # Clear all scheduled times for this asset
                            scheduled_asset_times[asset_id] = []
                            logger.debug(f"   Reset scheduled times for asset {asset_id}")
                
                # CRITICAL: Reset the last_scheduled_date in the database for this category
                # This is what actually makes the content available again
                if self._reset_category_delays(duration_category, list(excluded_category_assets)):
                    logger.info(f"✅ Successfully reset database delays for {len(excluded_category_assets)} {duration_category} assets")
                else:
                    logger.error(f"❌ Failed to reset database delays for {duration_category} assets")
                
                # Try again with reset exclusions and no delays
                available_content = self.get_available_content(
                    duration_category,
                    exclude_ids=reset_exclude_ids,
                    ignore_delays=True,  # Use no delays after reset
                    schedule_date=schedule_date,
                    scheduled_asset_times=scheduled_asset_times
                )
                
                if available_content:
                    logger.info(f"✅ After reset: Found {len(available_content)} items for {duration_category}")
                    for item in available_content:
                        item['_delay_factor_used'] = 0.0
                        item['_was_reset'] = True
                    
                    # Update the original exclude_ids list to reflect the reset
                    # This is important so the calling function knows about the reset
                    exclude_ids[:] = reset_exclude_ids
                    
                    return available_content
                else:
                    logger.error(f"❌ Still no content available for {duration_category} even after reset")
            
        except Exception as e:
            logger.error(f"Error during category reset check: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            db_manager._put_connection(conn)
        
        return []
    
    def _reset_category_delays(self, duration_category: str, asset_ids: List[int]) -> bool:
        """Reset last_scheduled_date for assets in a category to allow immediate reuse
        
        This is called when no content is available for a category even with all
        delay restrictions removed. It clears the last_scheduled_date in the database
        for the specified assets, making them immediately available for scheduling.
        """
        if not asset_ids:
            return False
            
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Reset last_scheduled_date to NULL for these assets
            # This makes them appear as if they've never been scheduled
            cursor.execute("""
                UPDATE scheduling_metadata
                SET last_scheduled_date = NULL
                WHERE asset_id = ANY(%s)
            """, (asset_ids,))
            
            affected_rows = cursor.rowcount
            conn.commit()
            cursor.close()
            
            logger.warning(f"🔄 Reset last_scheduled_date for {affected_rows} {duration_category} assets")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error resetting category delays: {str(e)}")
            return False
        finally:
            db_manager._put_connection(conn)
    
    def _has_theme_conflict(self, candidate_content: dict, last_scheduled_category: str, 
                           last_scheduled_theme: str, current_category: str,
                           scheduled_items: list = None, candidate_is_pkg: bool = False,
                           remaining_hours: float = None) -> bool:
        """Check if candidate content has a theme conflict with the last scheduled item
        
        Args:
            candidate_content: The content being considered
            last_scheduled_category: Category of the last scheduled item
            last_scheduled_theme: Theme of the last scheduled item
            current_category: Category we're trying to schedule
            scheduled_items: List of recently scheduled items (for package checking)
            candidate_is_pkg: True if the candidate content is a package
            remaining_hours: Hours remaining until end of day/schedule
            
        Returns:
            True if there's a theme conflict, False otherwise
        """
        candidate_theme = candidate_content.get('theme')
        
        # Special handling for all short-form content (id, spots, short_form) - must be separated by at least one long_form
        # This includes content types like PKG, MAF, PSA, BMP, etc. when they fall into short duration categories
        candidate_category = candidate_content.get('duration_category', current_category)
        
        if (candidate_category in ['id', 'spots', 'short_form'] and 
            candidate_theme and scheduled_items):
            
            # If we're within 2 hours of end-of-day, relax theme conflict requirements
            # This prevents infinite loops when trying to fill end-of-day gaps
            if remaining_hours is not None and remaining_hours < 2.0:
                logger.debug(f"Relaxing theme conflict check near end-of-day ({remaining_hours:.1f}h remaining)")
                return False
            
            # Look backwards through scheduled items to find content with same theme
            for i in range(len(scheduled_items) - 1, -1, -1):
                item = scheduled_items[i]
                
                # If we find a long_form content before finding same-theme short content, we're good
                if item.get('duration_category') == 'long_form':
                    break
                
                # If we find short-form content with the same theme before any long_form, that's a conflict
                if (item.get('duration_category') in ['id', 'spots', 'short_form'] and 
                    item.get('theme') and 
                    item.get('theme').lower() == candidate_theme.lower()):
                    content_type = candidate_content.get('content_type', 'unknown')
                    item_type = item.get('content_type', 'unknown')
                    logger.debug(f"Short-form theme conflict: '{candidate_theme}' - "
                               f"{content_type} ({candidate_category}) conflicts with {item_type} ({item.get('duration_category')}) - "
                               f"short-form content with same theme must be separated by long_form content")
                    return True
        
        return False
    
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
    
    def get_available_content(self, duration_category: str, exclude_ids: List[int] = None, ignore_delays: bool = False, schedule_date: str = None, delay_reduction_factor: float = 1.0, scheduled_asset_times: dict = None) -> List[Dict[str, Any]]:
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
            delay_reduction_factor: Factor to reduce delays by (0.0 = no delays, 0.5 = half delays, 1.0 = full delays)
        """
        # Ensure database is connected
        if hasattr(db_manager, 'connected') and not db_manager.connected:
            db_manager.connect()
        elif hasattr(db_manager, 'is_connected') and not db_manager.is_connected():
            db_manager.connect()
        
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Calculate dates in Python to avoid INTERVAL issues
            if schedule_date:
                try:
                    compare_date = datetime.strptime(schedule_date, '%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid schedule_date format: {schedule_date}, using current time")
                    compare_date = datetime.now()
            else:
                compare_date = datetime.now()
            
            # Pre-calculate all date values we'll need
            default_expiry_date = compare_date + timedelta(days=365)
            epoch_start = datetime(1970, 1, 1)
            date_minus_1 = compare_date - timedelta(days=1)
            date_minus_3 = compare_date - timedelta(days=3)
            date_minus_7 = compare_date - timedelta(days=7)
            date_minus_14 = compare_date - timedelta(days=14)
            date_minus_30 = compare_date - timedelta(days=30)
            
            # Get delay configuration
            base_delay = 0
            additional_delay = 0
            featured_delay = 2.0  # Default featured delay
            
            if not ignore_delays:
                if delay_reduction_factor == 0.0:
                    base_delay = 0
                    additional_delay = 0
                    if delay_reduction_factor < 1.0:
                        logger.info(f"Ignoring delays for {duration_category} (reduction factor would have been {delay_reduction_factor})")
                else:
                    try:
                        from config_manager import ConfigManager
                        config_mgr = ConfigManager()
                        scheduling_config = config_mgr.get_scheduling_settings()
                        replay_delays = scheduling_config.get('replay_delays', {})
                        additional_delays = scheduling_config.get('additional_delay_per_airing', {})
                        featured_config = scheduling_config.get('featured_content', {})
                        featured_delay = featured_config.get('minimum_spacing', 2.0)
                        
                        # Define default delays for content types
                        content_type_defaults = {
                            'an': 2,
                            'atld': 2,
                            'bmp': 3,
                            'imow': 4,
                            'im': 3,
                            'ia': 4,
                            'lm': 3,
                            'mtg': 8,
                            'maf': 4,
                            'pkg': 3,
                            'pmo': 3,
                            'psa': 2,
                            'szl': 3,
                            'spp': 3
                        }
                        
                        # Check if this is a content type or duration category
                        if duration_category.lower() in content_type_defaults:
                            # It's a content type, use content type defaults
                            base_delay = replay_delays.get(duration_category.lower(), content_type_defaults.get(duration_category.lower(), 4))
                            additional_delay = additional_delays.get(duration_category.lower(), 0.5)
                        else:
                            # It's a duration category, use regular defaults
                            base_delay = replay_delays.get(duration_category, 24)
                            additional_delay = additional_delays.get(duration_category, 2)
                        
                        if delay_reduction_factor < 1.0:
                            original_base = base_delay
                            original_additional = additional_delay
                            base_delay = base_delay * delay_reduction_factor
                            additional_delay = additional_delay * delay_reduction_factor
                            logger.info(f"Reducing delays for {duration_category} by factor {delay_reduction_factor}: "
                                      f"base {original_base}h -> {base_delay}h, additional {original_additional}h -> {additional_delay}h")
                    except Exception as e:
                        logger.warning(f"Could not load replay delay config, using defaults: {e}")
            
            # Determine if we're filtering by duration category or content type
            duration_categories = ['id', 'spots', 'short_form', 'long_form']
            is_duration_category = duration_category in duration_categories
            
            # Handle uppercase content type codes from frontend (BMP -> bmp)
            if not is_duration_category:
                duration_category = duration_category.lower()
            
            # Build query using only positional parameters
            query_parts = ["""
                SELECT 
                    a.id as asset_id,
                    a.guid,
                    a.content_type,
                    a.content_title,
                    a.duration_seconds,
                    a.duration_category,
                    a.engagement_score,
                    a.theme,
                    i.id as instance_id,
                    i.file_name,
                    i.file_path,
                    i.encoded_date,
                    sm.last_scheduled_date,
                    sm.total_airings,
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = 'scheduling_metadata' 
                            AND column_name = 'featured'
                        ) THEN COALESCE(sm.featured, FALSE)
                        ELSE FALSE
                    END as featured,
                    COALESCE(sm.content_expiry_date, %s) as content_expiry_date,
                    sm.go_live_date,
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = 'scheduling_metadata' 
                            AND column_name = 'featured'
                        ) AND COALESCE(sm.featured, FALSE) = TRUE THEN %s
                        ELSE (%s + (COALESCE(sm.total_airings, 0) * %s))
                    END as required_delay_hours,
                    EXTRACT(EPOCH FROM (%s - COALESCE(sm.last_scheduled_date, %s))) / 3600 as hours_since_last_scheduled
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE 
                    a.analysis_completed = TRUE
            """]
            
            # Parameters for the main query
            params = [
                default_expiry_date,  # for COALESCE in SELECT
                featured_delay,       # for required_delay_hours CASE featured
                base_delay,           # for required_delay_hours CASE normal
                additional_delay,     # for required_delay_hours CASE normal
                compare_date,         # for hours_since_last_scheduled
                epoch_start,          # for hours_since_last_scheduled fallback
            ]
            
            # Add category filter
            if is_duration_category:
                query_parts.append(" AND a.duration_category = %s")
            else:
                query_parts.append(" AND a.content_type = %s")
            params.append(duration_category)
            
            # Add remaining filters
            query_parts.append("""
                AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                AND COALESCE(sm.content_expiry_date, %s) > %s
                AND (sm.go_live_date IS NULL OR sm.go_live_date <= %s)
                AND NOT (i.file_path LIKE %s)
            """)
            params.extend([default_expiry_date, compare_date, compare_date, '%FILL%'])
            
            # Add replay delay check if not ignoring
            if not ignore_delays:
                query_parts.append("""
                    AND (
                        sm.last_scheduled_date IS NULL 
                        OR sm.last_scheduled_date > %s  -- Content scheduled in the future is available
                        OR EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 
                            CASE 
                                WHEN EXISTS (
                                    SELECT 1 FROM information_schema.columns 
                                    WHERE table_name = 'scheduling_metadata' 
                                    AND column_name = 'featured'
                                ) AND COALESCE(sm.featured, FALSE) = TRUE THEN %s
                                ELSE (%s + (COALESCE(sm.total_airings, 0) * %s))
                            END
                    )
                """)
                params.extend([compare_date, compare_date, featured_delay, base_delay, additional_delay])
            
            # Remove invalid existence check - scheduled_items doesn't have available_for_scheduling column
            # The available_for_scheduling check is already done via scheduling_metadata table above
            
            # Handle exclude_ids
            if exclude_ids and len(exclude_ids) > 0:
                placeholders = ','.join(['%s'] * len(exclude_ids))
                query_parts.append(f" AND a.id NOT IN ({placeholders})")
                params.extend(exclude_ids)
            
            # Add complex ordering with pre-calculated dates
            query_parts.append("""
                ORDER BY 
                    (
                        CASE 
                            WHEN i.encoded_date IS NULL THEN 0
                            WHEN i.encoded_date >= %s THEN 100
                            WHEN i.encoded_date >= %s THEN 90
                            WHEN i.encoded_date >= %s THEN 80
                            WHEN i.encoded_date >= %s THEN 60
                            WHEN i.encoded_date >= %s THEN 40
                            WHEN i.encoded_date >= %s THEN 20
                            ELSE 10
                        END * 0.35
                        
                        + COALESCE(a.engagement_score, 50) * 0.25
                        
                        + CASE
                            WHEN sm.total_airings IS NULL OR sm.total_airings = 0 THEN 100
                            WHEN sm.total_airings <= 2 THEN 80
                            WHEN sm.total_airings <= 5 THEN 60
                            WHEN sm.total_airings <= 10 THEN 40
                            WHEN sm.total_airings <= 20 THEN 20
                            ELSE 10
                        END * 0.20
                        
                        + CASE
                            WHEN sm.last_scheduled_date IS NULL THEN 100
                            WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 24 THEN 100
                            WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 12 THEN 80
                            WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 6 THEN 60
                            WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 3 THEN 40
                            WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 1 THEN 20
                            ELSE 0
                        END * 0.20
                    ) DESC,
                    
                    sm.last_scheduled_date ASC NULLS FIRST,
                    sm.total_airings ASC NULLS FIRST,
                    i.encoded_date DESC NULLS LAST,
                    RANDOM()  -- Add randomization to break ties and avoid same content order
                LIMIT 200  -- Increased to get more variety
            """)
            
            # Add date parameters for ORDER BY
            params.extend([
                compare_date,     # for freshness score comparisons
                date_minus_1,
                date_minus_3,
                date_minus_7,
                date_minus_14,
                date_minus_30,
                compare_date,     # for time since last play calculations
                compare_date,
                compare_date,
                compare_date,
                compare_date
            ])
            
            # Combine query parts
            query = ''.join(query_parts)
            
            # Execute query
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
            
            # Reset holiday greeting session tracking for new schedule
            self._ensure_holiday_integration()
            if hasattr(self, 'holiday_integration') and self.holiday_integration.enabled:
                self.holiday_integration.reset_session()
            
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
            
            # Set up holiday greeting daily assignments if enabled
            self._ensure_holiday_integration()
            if hasattr(self, 'holiday_integration') and self.holiday_integration.enabled:
                logger.info("Setting up holiday greeting daily assignments for daily schedule")
                try:
                    # Create daily assignments for the single day
                    from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
                    daily_assignments = HolidayGreetingDailyAssignments(db_manager)
                    success = daily_assignments.assign_greetings_for_schedule(
                        schedule_id, 
                        schedule_dt,
                        num_days=1
                    )
                    
                    if success:
                        # Set the current schedule ID in holiday integration
                        self._ensure_holiday_integration()
                        self.holiday_integration.set_current_schedule(schedule_id)
                        logger.info(f"Successfully assigned holiday greetings for schedule {schedule_id}")
                    else:
                        logger.warning("Failed to assign holiday greeting daily assignments")
                except Exception as e:
                    logger.error(f"Error setting up holiday greeting daily assignments: {e}")
            
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
            
            # Track the theme of the last scheduled item to avoid back-to-back same themes
            last_scheduled_theme = None
            last_scheduled_category = None
            
            # Track recent plays for fatigue prevention (asset_id -> list of scheduled times)
            recent_plays = {}
            
            # Track when we use reduced delays
            delay_reduction_stats = {
                'full_delays': 0,       # 100% delays
                'reduced_75': 0,        # 75% delays
                'reduced_50': 0,        # 50% delays
                'reduced_25': 0,        # 25% delays
                'no_delays': 0,         # 0% delays
                'resets': 0             # Category resets
            }
            
            # Track category-specific resets
            category_reset_counts = {
                'id': 0,
                'spots': 0,
                'short_form': 0,
                'long_form': 0
            }
            
            # Infinite loop detection
            last_progress_duration = 0
            no_progress_iterations = 0
            max_no_progress = 50  # Allow max 50 iterations without progress
            consecutive_no_content_cycles = 0  # Track cycles where all categories fail
            max_no_content_cycles = 3  # Max full rotation cycles with no content
            
            # Track featured content scheduling
            last_featured_time = 0  # Initialize to 0 so featured content can be scheduled immediately
            featured_content_index = 0  # Track which featured content to use next
            
            # Get featured delay from config
            try:
                from config_manager import ConfigManager
                config_mgr = ConfigManager()
                scheduling_config = config_mgr.get_scheduling_settings()
                featured_config = scheduling_config.get('featured_content', {})
                featured_delay = featured_config.get('minimum_spacing', 2.0)
                logger.info(f"Featured content minimum spacing: {featured_delay} hours")
            except:
                featured_config = {}
                featured_delay = 2.0
                logger.info(f"Using default featured config")
                
            while total_duration < self.target_duration_seconds:
                # Calculate remaining hours for use throughout this iteration
                remaining_hours = (self.target_duration_seconds - total_duration) / 3600
                
                # Determine if we should prioritize featured content based on time of day
                should_try_featured = False
                
                # First check if it's time for featured content (minimum spacing)
                if self._should_schedule_featured_content(total_duration, last_featured_time, featured_delay):
                    # Check daytime priority
                    if self._should_prioritize_featured_for_daytime(total_duration, featured_config):
                        should_try_featured = True
                
                if should_try_featured:
                    # Get all available featured content
                    featured_content = self.get_featured_content(
                        exclude_ids=[],
                        schedule_date=schedule_date
                    )
                    
                    if featured_content:
                        # We have featured content and it's appropriate for this time slot
                        # Use round-robin selection of featured content
                        content = featured_content[featured_content_index % len(featured_content)]
                        featured_content_index += 1
                        
                        is_daytime = self._is_daytime_slot(total_duration, featured_config)
                        logger.info(f"Scheduling featured content: {content.get('content_title', 'Unknown')} "
                                  f"at {total_duration/3600:.2f} hours ({'daytime' if is_daytime else 'nighttime'})")
                        
                        available_content = [content]
                    else:
                        # No featured content available, get regular content
                        duration_category = self._get_next_duration_category()
                        available_content = self._get_content_with_progressive_delays(
                            duration_category, 
                            exclude_ids=scheduled_asset_ids,
                            schedule_date=schedule_date,
                            scheduled_asset_times=scheduled_asset_times
                        )
                else:
                    # Not appropriate time/slot for featured content, get regular content
                    duration_category = self._get_next_duration_category()
                    available_content = self._get_content_with_progressive_delays(
                        duration_category, 
                        exclude_ids=scheduled_asset_ids,
                        schedule_date=schedule_date,
                        scheduled_asset_times=scheduled_asset_times
                    )
                
                if not available_content:
                    logger.warning(f"No available content for category: {duration_category} even without delays. "
                                 f"Remaining hours in day: {remaining_hours:.1f}")
                    
                    # Check if we're near midnight and trying to schedule longform content
                    # Skip longform requirement if within last hour of the day
                    if remaining_hours < 1.0 and duration_category == 'long_form':
                        logger.info(f"Skipping long_form content near midnight (only {remaining_hours:.1f} hours left). Advancing rotation.")
                        self._advance_rotation()
                        consecutive_errors = 0  # Reset error counter since we're making progress
                        continue
                    
                    consecutive_errors += 1
                    total_errors += 1
                    
                    # IMPORTANT: Always advance rotation when no content is found
                    # This prevents getting stuck on the same category
                    self._advance_rotation()
                    logger.info(f"Advanced rotation to next category after no content found for {duration_category}")
                    
                    # Track if we've cycled through all categories without finding content
                    if self.rotation_index == 0:  # We've completed a full rotation cycle
                        consecutive_no_content_cycles += 1
                        logger.warning(f"⚠️ Completed full rotation cycle #{consecutive_no_content_cycles} with no available content")
                        
                        if consecutive_no_content_cycles >= max_no_content_cycles:
                            # Check if we're very close to the end of the day
                            if remaining_hours < 0.5:  # Less than 30 minutes left
                                logger.warning(f"Accepting gap of {remaining_hours:.1f} hours at end of day after {consecutive_no_content_cycles} cycles")
                                break
                            else:
                                logger.error(f"❌ Infinite loop detected: {consecutive_no_content_cycles} full rotation cycles with no available content")
                                # Delete the partially created schedule
                                self.delete_schedule(schedule_id)
                                return {
                                    'success': False,
                                    'message': f'Schedule creation failed: No content available after {consecutive_no_content_cycles} complete rotation cycles. '
                                             f'All content is blocked by replay delays. Please add more content or reduce replay delay settings.',
                                    'error': 'infinite_loop_all_blocked',
                                    'stopped_at_hours': total_duration / 3600,
                                    'rotation_cycles_failed': consecutive_no_content_cycles
                                }
                    
                    # Check for infinite loop (no progress at all)
                    if total_duration == last_progress_duration:
                        no_progress_iterations += 1
                        if no_progress_iterations >= max_no_progress:
                            # Check if we're very close to the end of the day
                            if remaining_hours < 0.5:  # Less than 30 minutes left
                                logger.warning(f"Accepting gap of {remaining_hours:.1f} hours at end of day after {max_no_progress} iterations")
                                break
                            else:
                                logger.error(f"❌ Infinite loop detected: No progress for {max_no_progress} iterations at {total_duration/3600:.2f} hours")
                                # Delete the partially created schedule
                                self.delete_schedule(schedule_id)
                                return {
                                    'success': False,
                                    'message': f'Schedule creation failed: Infinite loop detected at {total_duration/3600:.2f} hours. '
                                             f'No content available to continue. Please add more content or adjust replay delays.',
                                    'error': 'infinite_loop',
                                    'stopped_at_hours': total_duration / 3600,
                                    'iterations_without_progress': no_progress_iterations
                                }
                    
                    # Check if we should abort (only for significant gaps)
                    if consecutive_errors >= max_errors and remaining_hours > 1.0:
                        logger.error(f"Aborting schedule creation: {consecutive_errors} consecutive errors with {remaining_hours:.1f} hours remaining")
                        # Delete the partially created schedule
                        self.delete_schedule(schedule_id)
                        return {
                            'success': False,
                            'message': f'Schedule creation failed: No available content after {total_errors} attempts. Check content availability.',
                            'error_count': total_errors
                        }
                    continue
                
                # Select the best content with multi-factor scoring and fatigue prevention
                content = None
                best_score = -1
                
                # If we have featured content selected, use it directly without scoring
                if available_content and len(available_content) == 1 and available_content[0].get('featured'):
                    content = available_content[0]
                    logger.debug(f"Using featured content directly: {content.get('content_title', 'Unknown')}")
                else:
                    # Always check theme conflicts for IDs and spots regardless of content type
                    # These short durations are typically PSAs/announcements that shouldn't repeat themes
                    
                    # Score and rank all available content
                    for candidate in available_content:
                        asset_id = candidate['asset_id']
                        current_category = candidate.get('duration_category', '')
                        current_theme = candidate.get('theme', '').strip() if candidate.get('theme') else None
                    
                        # Start with base score from SQL query (already calculated)
                        score = 100  # Base score
                    
                        # Boost score for featured content
                        if candidate.get('featured', False):
                            score += 150  # Significant boost for featured content
                            logger.debug(f"Featured content boost for '{candidate.get('content_title', 'Unknown')}'")
                    
                        # Apply fatigue penalty based on recent plays within this schedule
                        if asset_id in recent_plays:
                            plays = recent_plays[asset_id]
                            for play_time in plays:
                                time_gap = (total_duration - play_time) / 3600  # Hours since last play
                                
                                if time_gap < 1:
                                    score -= 100  # Heavy penalty for content played within 1 hour
                                elif time_gap < 2:
                                    score -= 50   # Medium penalty for 1-2 hours
                                elif time_gap < 4:
                                    score -= 25   # Light penalty for 2-4 hours
                                elif time_gap < 6:
                                    score -= 10   # Very light penalty for 4-6 hours
                            
                            # Additional penalty for multiple plays
                            if len(plays) >= 3:
                                score -= 50 * (len(plays) - 2)  # Heavy penalty for 3+ plays
                    
                        # Special handling for IDs - stronger rotation requirements
                        if current_category == 'id':
                            if asset_id in recent_plays and len(recent_plays[asset_id]) > 0:
                                last_play = recent_plays[asset_id][-1]
                                time_gap = (total_duration - last_play) / 3600
                                if time_gap < 2:
                                    score -= 300  # Very heavy penalty for IDs within 2 hours
                            
                            # Bonus for IDs not recently played
                            if asset_id not in recent_plays:
                                score += 50
                    
                        # Theme conflict check for all short-form content
                        # Short-form content with same theme must be separated by long_form
                        if self._has_theme_conflict(candidate, last_scheduled_category, 
                                                   last_scheduled_theme, current_category,
                                                   scheduled_items, remaining_hours=remaining_hours):
                            score -= 400  # Heavy penalty for theme conflicts
                            content_type = candidate.get('content_type', 'unknown')
                            logger.debug(f"Theme conflict penalty for {content_type} with theme '{current_theme}'")
                    
                        # Track best scoring content
                        if score > best_score:
                            best_score = score
                            content = candidate
                
                # If no good content found (all have very negative scores), use the first available
                if not content and available_content:
                    content = available_content[0]
                    logger.warning(f"All content has poor scores, using first available")
                
                if not content:
                    # This shouldn't happen if available_content has items
                    consecutive_errors += 1
                    total_errors += 1
                    continue
                
                # Log selected content details
                if content:
                    play_count = len(recent_plays.get(content['asset_id'], []))
                    delay_factor = content.get('_delay_factor_used', 1.0)
                    logger.debug(f"Selected: {content.get('content_title', 'Unknown')} "
                               f"(ID: {content['asset_id']}, Category: {content.get('duration_category')}, "
                               f"Theme: {content.get('theme', 'None')}, Plays: {play_count}, Score: {best_score}, "
                               f"Delay Factor: {delay_factor*100:.0f}%)")
                    
                    # Track delay reduction usage
                    if delay_factor == 1.0:
                        delay_reduction_stats['full_delays'] += 1
                    elif delay_factor == 0.75:
                        delay_reduction_stats['reduced_75'] += 1
                    elif delay_factor == 0.5:
                        delay_reduction_stats['reduced_50'] += 1
                    elif delay_factor == 0.25:
                        delay_reduction_stats['reduced_25'] += 1
                    elif delay_factor == 0.0:
                        delay_reduction_stats['no_delays'] += 1
                    
                    # Check if this was a reset
                    if content.get('_was_reset', False):
                        delay_reduction_stats['resets'] += 1
                        category_reset_counts[duration_category] += 1
                        logger.warning(f"🔄 Using RESET content for {duration_category} (reset #{category_reset_counts[duration_category]})")
                
                consecutive_errors = 0  # Reset consecutive error counter
                
                # The delay constraint checking is now handled in get_available_content
                # with progressive delay reduction, so we don't need to check again here
                
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
                            # Check for theme conflict before accepting this alternative
                            if self._has_theme_conflict(alt_content, last_scheduled_category, 
                                                       last_scheduled_theme, duration_category,
                                                       scheduled_items, remaining_hours=remaining_hours):
                                logger.debug(f"Skipping alternative content due to theme conflict: {alt_content.get('theme')}")
                                continue
                            
                            # Found content that fits and has no theme conflict!
                            content = alt_content
                            content_duration = alt_duration
                            found_fitting_content = True
                            logger.info(f"Found alternative content that fits in remaining {remaining_seconds/60:.1f} minutes")
                            break
                    
                    if not found_fitting_content:
                        # No content fits in remaining time
                        logger.info(f"No content fits in remaining {remaining_seconds/60:.1f} minutes, stopping at {total_duration/3600:.2f} hours")
                        
                        # Special handling for very small gaps at end of schedule
                        if remaining_seconds < 60:  # Less than 1 minute
                            logger.warning(f"Accepting {remaining_seconds:.1f} second gap at end of schedule to prevent infinite loop")
                            # Move to next target duration to exit gracefully
                            total_duration = self.target_duration_seconds
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
                    'scheduled_duration_seconds': content['duration_seconds'],
                    # Add metadata for theme conflict checking
                    'content_type': content.get('content_type'),
                    'theme': content.get('theme'),
                    'duration_category': content.get('duration_category'),
                    'file_name': content.get('file_name')  # Add for holiday greeting tracking
                }
                
                scheduled_items.append(item)
                scheduled_asset_ids.append(content['asset_id'])
                
                # Track when this asset is scheduled (for delay enforcement)
                if content['asset_id'] not in scheduled_asset_times:
                    scheduled_asset_times[content['asset_id']] = []
                scheduled_asset_times[content['asset_id']].append(total_duration)
                
                # Track recent plays for fatigue prevention
                if content['asset_id'] not in recent_plays:
                    recent_plays[content['asset_id']] = []
                recent_plays[content['asset_id']].append(total_duration)
                
                # Update totals
                total_duration += content_duration
                
                # Add one frame gap between items (29.976 fps)
                frame_gap = 1.0 / 29.976  # approximately 0.033367 seconds
                total_duration += frame_gap
                
                sequence_number += 1
                
                # Advance rotation only if this wasn't featured content
                # Featured content doesn't participate in the rotation
                if not content.get('featured'):
                    self._advance_rotation()
                
                # Update theme tracking for next iteration
                last_scheduled_theme = content.get('theme', '').strip() if content.get('theme') else None
                last_scheduled_category = content.get('duration_category', '')
                
                # Update featured content tracking if we just scheduled a featured item
                if content.get('featured'):
                    last_featured_time = total_duration
                    logger.info(f"✨ Featured content scheduled at {total_duration/3600:.2f} hours, next featured at ~{(total_duration + featured_delay * 3600)/3600:.2f} hours")
                
                # Calculate actual air time for this item
                # The item starts at (total_duration - content_duration) seconds from schedule start
                actual_air_time = schedule_dt + timedelta(seconds=total_duration - content_duration)
                
                # Update the asset's last scheduled date with actual air time
                self._update_asset_last_scheduled(content['asset_id'], actual_air_time)
                
                # Log progress
                if sequence_number % 10 == 0:
                    logger.info(f"Scheduled {sequence_number} items, duration: {total_duration/3600:.2f} hours")
                
                # Reset no-progress counter since we made progress
                no_progress_iterations = 0
                last_progress_duration = total_duration
                consecutive_no_content_cycles = 0  # Reset cycle counter on successful scheduling
            
            # Save all scheduled items
            saved_count = self._save_scheduled_items(scheduled_items)
            
            # Update schedule total duration
            self._update_schedule_duration(schedule_id, total_duration)
            
            # Log delay reduction statistics
            total_delay_stats = sum(delay_reduction_stats.values())
            if total_delay_stats > 0:
                logger.info("=== Delay Reduction Statistics ===")
                logger.info(f"Total items scheduled: {total_delay_stats}")
                logger.info(f"Full delays (100%): {delay_reduction_stats['full_delays']} ({delay_reduction_stats['full_delays']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['reduced_75'] > 0:
                    logger.warning(f"⚠️ Reduced to 75%: {delay_reduction_stats['reduced_75']} ({delay_reduction_stats['reduced_75']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['reduced_50'] > 0:
                    logger.warning(f"⚠️ Reduced to 50%: {delay_reduction_stats['reduced_50']} ({delay_reduction_stats['reduced_50']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['reduced_25'] > 0:
                    logger.warning(f"⚠️ Reduced to 25%: {delay_reduction_stats['reduced_25']} ({delay_reduction_stats['reduced_25']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['no_delays'] > 0:
                    logger.error(f"❌ No delays (0%): {delay_reduction_stats['no_delays']} ({delay_reduction_stats['no_delays']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['resets'] > 0:
                    logger.warning(f"🔄 Category resets: {delay_reduction_stats['resets']} ({delay_reduction_stats['resets']/total_delay_stats*100:.1f}%)")
                    for cat, count in category_reset_counts.items():
                        if count > 0:
                            logger.warning(f"   - {cat}: {count} resets")
            
            logger.info(f"Created schedule with {saved_count} items, total duration: {total_duration/3600:.2f} hours")
            
            return {
                'success': True,
                'message': f'Successfully created schedule for {schedule_date}',
                'schedule_id': schedule_id,
                'total_items': saved_count,
                'total_duration_hours': total_duration / 3600,
                'delay_reduction_stats': delay_reduction_stats,
                'category_reset_counts': category_reset_counts
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
            
            # Record holiday greeting scheduling if applicable
            self._ensure_holiday_integration()
            if hasattr(self, 'holiday_integration') and asset and 'file_name' in asset:
                self.holiday_integration.record_scheduled_item(
                    asset['asset_id'], 
                    asset['file_name']
                )
            
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
                # Ensure time wraps at 24 hours for schedules that go past midnight
                time_in_day = current_time % 86400  # 86400 seconds = 24 hours
                hours = int(time_in_day // 3600)
                minutes = int((time_in_day % 3600) // 60)
                seconds_total = time_in_day % 60
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
                
                # Record holiday greeting scheduling if applicable
                self._ensure_holiday_integration()
                if hasattr(self, 'holiday_integration') and 'file_name' in item:
                    self.holiday_integration.record_scheduled_item(
                        item['asset_id'], 
                        item['file_name']
                    )
            
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
            
            # Get all schedules within a reasonable date range for reporting
            # Include schedules from 90 days ago to any future date
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
                WHERE s.air_date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY s.id, s.schedule_name, s.air_date, s.created_date, s.active, s.total_duration_seconds
                ORDER BY s.air_date DESC, s.created_date DESC
                LIMIT 300
            """)
            
            results = cursor.fetchall()
            cursor.close()
            
            # Debug logging to help diagnose missing schedules
            logger.info(f"get_active_schedules: Found {len(results)} schedules")
            if len(results) > 0:
                logger.debug(f"First schedule: {results[0].get('name')} - Air date: {results[0].get('air_date')} - ID: {results[0].get('id')}")
                logger.debug(f"Date range: 90 days ago to future")
                # Log all schedules for debugging
                logger.debug("All schedules:")
                for idx, sched in enumerate(results[:10]):  # First 10 schedules
                    logger.debug(f"  {idx+1}. {sched.get('name')} - Air date: {sched.get('air_date')} - ID: {sched.get('id')}")
            else:
                logger.warning("No schedules found in get_active_schedules - check if schedules exist in the database")
            
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
            
            # Reset holiday greeting session tracking for new schedule
            self._ensure_holiday_integration()
            if hasattr(self, 'holiday_integration') and self.holiday_integration.enabled:
                self.holiday_integration.reset_session()
            
            # Parse start date and ensure it's a Sunday
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            
            # Adjust to previous Sunday if not already Sunday
            if start_date_obj.weekday() != 6:  # 6 is Sunday in Python
                # Go back to the previous Sunday
                days_since_sunday = (start_date_obj.weekday() + 1) % 7
                start_date_obj = start_date_obj - timedelta(days=days_since_sunday)
                logger.info(f"Adjusted start date to Sunday: {start_date_obj.strftime('%Y-%m-%d')}")
            
            # Set up holiday greeting daily assignments BEFORE creating schedules
            self._ensure_holiday_integration()
            if hasattr(self, 'holiday_integration') and self.holiday_integration.enabled:
                logger.info("Setting up holiday greeting daily assignments for weekly schedule")
                try:
                    # We need to create a temporary schedule ID for the assignments
                    # Since we're creating 7 separate daily schedules, we'll use a special approach
                    # We'll get the first available schedule ID and use that for assignments
                    conn = db_manager._get_connection()
                    cursor = conn.cursor()
                    
                    # Get the next schedule ID that will be created
                    cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 as next_id FROM schedules")
                    next_schedule_id = cursor.fetchone()[0]
                    cursor.close()
                    db_manager._put_connection(conn)
                    
                    from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
                    daily_assignments = HolidayGreetingDailyAssignments(db_manager)
                    success = daily_assignments.assign_greetings_for_schedule(
                        next_schedule_id,  # Use the predicted next schedule ID
                        start_date_obj,
                        num_days=7
                    )
                    
                    if success:
                        logger.info(f"Successfully pre-assigned holiday greetings for week starting {start_date}")
                        # Set the schedule ID so the holiday integration knows to use daily assignments
                        self._ensure_holiday_integration()
                        self.holiday_integration.set_current_schedule(next_schedule_id)
                    else:
                        logger.warning("Failed to pre-assign holiday greeting daily assignments")
                except Exception as e:
                    logger.error(f"Error setting up holiday greeting daily assignments: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
            
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
                        
                        # Update holiday integration with the actual schedule ID for this day
                        self._ensure_holiday_integration()
                        if hasattr(self, 'holiday_integration') and self.holiday_integration.enabled:
                            self.holiday_integration.set_current_schedule(result.get('schedule_id'))
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
                schedule_name=schedule_name or f"[WEEKLY] Schedule: {start_date_obj.strftime('%Y-%m-%d')} - {end_date_obj.strftime('%Y-%m-%d')}"
            )
            
            if not schedule_id:
                return {
                    'success': False,
                    'message': 'Failed to create schedule record'
                }
            
            # Set up holiday greeting daily assignments if enabled
            self._ensure_holiday_integration()
            if hasattr(self, 'holiday_integration') and self.holiday_integration.enabled:
                logger.info("Setting up holiday greeting daily assignments for weekly schedule")
                try:
                    # Create daily assignments for the 7-day schedule
                    from holiday_greeting_daily_assignments import HolidayGreetingDailyAssignments
                    daily_assignments = HolidayGreetingDailyAssignments(db_manager)
                    success = daily_assignments.assign_greetings_for_schedule(
                        schedule_id, 
                        start_date_obj,
                        num_days=7
                    )
                    
                    if success:
                        # Set the current schedule ID in holiday integration
                        self._ensure_holiday_integration()
                        self.holiday_integration.set_current_schedule(schedule_id)
                        logger.info(f"Successfully assigned holiday greetings for schedule {schedule_id}")
                    else:
                        logger.warning("Failed to assign holiday greeting daily assignments")
                except Exception as e:
                    logger.error(f"Error setting up holiday greeting daily assignments: {e}")
            
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
            
            # Track the theme of the last scheduled item to avoid back-to-back same themes
            last_scheduled_theme = None
            last_scheduled_category = None
            
            # Track recent plays for fatigue prevention (asset_id -> list of scheduled times)
            recent_plays = {}
            
            # Track when we use reduced delays
            delay_reduction_stats = {
                'full_delays': 0,       # 100% delays
                'reduced_75': 0,        # 75% delays
                'reduced_50': 0,        # 50% delays
                'reduced_25': 0,        # 25% delays
                'no_delays': 0,         # 0% delays
                'resets': 0             # Category resets
            }
            
            # Track category-specific resets
            category_reset_counts = {
                'id': 0,
                'spots': 0,
                'short_form': 0,
                'long_form': 0
            }
            
            # Infinite loop detection
            last_progress_duration = 0
            no_progress_iterations = 0
            max_no_progress = 50  # Allow max 50 iterations without progress
            consecutive_no_content_cycles = 0  # Track cycles where all categories fail
            max_no_content_cycles = 3  # Max full rotation cycles with no content
            
            # Track featured content scheduling
            last_featured_time = 0  # Initialize to 0 so featured content can be scheduled immediately
            featured_content_index = 0  # Track which featured content to use next
            
            # Get featured delay from config
            try:
                from config_manager import ConfigManager
                config_mgr = ConfigManager()
                scheduling_config = config_mgr.get_scheduling_settings()
                featured_config = scheduling_config.get('featured_content', {})
                featured_delay = featured_config.get('minimum_spacing', 2.0)
                logger.info(f"Featured content minimum spacing: {featured_delay} hours")
            except:
                featured_config = {}
                featured_delay = 2.0
                logger.info(f"Using default featured config")
            
            # Generate content for each day
            days_completed = 0
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
                day_start_time = total_duration  # Track where this day started
                
                while total_duration < day_target_seconds:
                    # Calculate remaining hours for use throughout this iteration
                    remaining_hours = (day_target_seconds - total_duration) / 3600
                    
                    # Check if we're stuck at the same position
                    current_position_hours = round(total_duration / 3600, 2)
                    if current_position_hours == last_position:
                        position_stuck_counter += 1
                        if position_stuck_counter >= max_position_stuck:
                            logger.error(f"❌ Stuck at position {current_position_hours}h for {position_stuck_counter} iterations")
                            remaining_gap = (day_target_seconds - total_duration) / 60
                            logger.warning(f"Accepting remaining gap of {remaining_gap:.1f} minutes on {day_name} to prevent infinite loop")
                            # Move to next day
                            total_duration = day_target_seconds
                            no_progress_iterations = 0  # Reset to avoid triggering other checks
                            break
                    else:
                        last_position = current_position_hours
                        position_stuck_counter = 0
                    
                    # Determine if we should prioritize featured content based on time of day
                    should_try_featured = False
                    
                    # First check if it's time for featured content (minimum spacing)
                    if self._should_schedule_featured_content(total_duration, last_featured_time, featured_delay):
                        # Check daytime priority
                        if self._should_prioritize_featured_for_daytime(total_duration, featured_config):
                            should_try_featured = True
                    
                    if should_try_featured:
                        # Get all available featured content
                        featured_content = self.get_featured_content(
                            exclude_ids=[],
                            schedule_date=current_day.strftime('%Y-%m-%d')
                        )
                        
                        if featured_content:
                            # We have featured content and it's appropriate for this time slot
                            # Use round-robin selection of featured content
                            content = featured_content[featured_content_index % len(featured_content)]
                            featured_content_index += 1
                            
                            is_daytime = self._is_daytime_slot(total_duration, featured_config)
                            logger.info(f"Scheduling featured content: {content.get('content_title', 'Unknown')} "
                                      f"at {total_duration/3600:.2f} hours on {day_name} ({'daytime' if is_daytime else 'nighttime'})")
                            
                            available_content = [content]
                        else:
                            # No featured content available, get regular content
                            duration_category = self._get_next_duration_category()
                            available_content = self._get_content_with_progressive_delays(
                                duration_category, 
                                exclude_ids=day_scheduled_asset_ids,
                                schedule_date=current_day.strftime('%Y-%m-%d'),
                                scheduled_asset_times=None
                            )
                    else:
                        # Not time for featured content yet or outside preferred time, get regular content
                        duration_category = self._get_next_duration_category()
                        available_content = self._get_content_with_progressive_delays(
                            duration_category, 
                            exclude_ids=day_scheduled_asset_ids,
                            schedule_date=current_day.strftime('%Y-%m-%d'),
                            scheduled_asset_times=None
                        )
                    
                    if not available_content:
                        current_time_str = self._seconds_to_time(total_duration % (24 * 60 * 60))
                        logger.warning(f"No available content for category: {duration_category} on {day_name} at {current_time_str} "
                                     f"(hour {(total_duration % (24 * 60 * 60)) / 3600:.1f}) even without delays. "
                                     f"Remaining hours in day: {remaining_hours:.1f}")
                        
                        # Check if we're near midnight and trying to schedule longform content
                        # Skip longform requirement if within last 2 hours of the day
                        if remaining_hours < 2.0 and duration_category == 'long_form':
                            logger.info(f"Skipping long_form content near midnight (only {remaining_hours:.1f} hours left). Advancing rotation.")
                            self._advance_rotation()
                            consecutive_errors = 0  # Reset error counter since we're making progress
                            continue
                        
                        consecutive_errors += 1
                        total_errors += 1
                        
                        # IMPORTANT: Always advance rotation when no content is found
                        # This prevents getting stuck on the same category
                        self._advance_rotation()
                        logger.info(f"Advanced rotation to next category after no content found for {duration_category}")
                        
                        # Track if we've cycled through all categories without finding content
                        if self.rotation_index == 0:  # We've completed a full rotation cycle
                            consecutive_no_content_cycles += 1
                            logger.warning(f"⚠️ Completed full rotation cycle #{consecutive_no_content_cycles} with no available content on {day_name}")
                            
                            if consecutive_no_content_cycles >= max_no_content_cycles:
                                # Check if we're very close to the end of the day
                                if remaining_hours < 0.5:  # Less than 30 minutes left
                                    logger.warning(f"Accepting gap of {remaining_hours:.1f} hours at end of {day_name} after {consecutive_no_content_cycles} cycles")
                                    total_duration = day_target_seconds
                                    break
                                else:
                                    logger.error(f"❌ Infinite loop detected: {consecutive_no_content_cycles} full rotation cycles with no available content")
                                    # Delete the partially created schedule
                                    self.delete_schedule(schedule_id)
                                    return {
                                        'success': False,
                                        'message': f'Schedule creation failed: No content available after {consecutive_no_content_cycles} complete rotation cycles. '
                                                 f'All content is blocked by replay delays. Please add more content or reduce replay delay settings.',
                                        'error': 'infinite_loop_all_blocked',
                                        'stopped_at_hours': total_duration / 3600,
                                        'stopped_at_day': day_name,
                                        'days_completed': days_completed,
                                        'rotation_cycles_failed': consecutive_no_content_cycles
                                    }
                        
                        # Check for infinite loop (no progress at all)
                        if total_duration == last_progress_duration:
                            no_progress_iterations += 1
                            if no_progress_iterations >= max_no_progress:
                                # Check if we're very close to the end of the day
                                if remaining_hours < 0.5:  # Less than 30 minutes left
                                    logger.warning(f"Accepting gap of {remaining_hours:.1f} hours at end of {day_name} after {max_no_progress} iterations")
                                    total_duration = day_target_seconds
                                    break
                                else:
                                    logger.error(f"❌ Infinite loop detected: No progress for {max_no_progress} iterations at {total_duration/3600:.2f} hours on {day_name}")
                                    # Delete the partially created schedule
                                    self.delete_schedule(schedule_id)
                                    return {
                                        'success': False,
                                        'message': f'Schedule creation failed: Infinite loop detected at {total_duration/3600:.2f} hours on {day_name}. '
                                                 f'No content available to continue. Please add more content or adjust replay delays.',
                                        'error': 'infinite_loop',
                                        'stopped_at_hours': total_duration / 3600,
                                        'stopped_at_day': day_name,
                                        'days_completed': days_completed,
                                        'iterations_without_progress': no_progress_iterations
                                    }
                        
                        # Check if we should abort (only for significant gaps)
                        if consecutive_errors >= max_errors and remaining_hours > 1.0:
                            logger.error(f"Aborting schedule creation: {consecutive_errors} consecutive errors with {remaining_hours:.1f} hours remaining")
                            # Delete the partially created schedule
                            self.delete_schedule(schedule_id)
                            return {
                                'success': False,
                                'message': f'Schedule creation failed: No available content after {total_errors} attempts. Check content availability.',
                                'error_count': total_errors
                            }
                        continue
                    
                    # Select the best content with multi-factor scoring and fatigue prevention
                    content = None
                    best_score = -1
                    
                    # If we have featured content selected, use it directly without scoring
                    if available_content and len(available_content) == 1 and available_content[0].get('featured'):
                        content = available_content[0]
                        logger.debug(f"Using featured content directly: {content.get('content_title', 'Unknown')}")
                    else:
                        # Always check theme conflicts for IDs and spots regardless of content type
                        # These short durations are typically PSAs/announcements that shouldn't repeat themes
                        
                        # Store the requested category for penalty calculations
                        requested_category = duration_category if 'duration_category' in locals() else 'unknown'
                        
                        # Define content type defaults for penalty calculations
                        content_type_defaults = {
                            'an': 2,
                            'atld': 2,
                            'bmp': 3,
                            'imow': 4,
                            'im': 3,
                            'ia': 4,
                            'lm': 3,
                            'mtg': 8,
                            'maf': 4,
                            'pkg': 3,
                            'pmo': 3,
                            'psa': 2,
                            'szl': 3,
                            'spp': 3
                        }
                        
                        # Score and rank all available content
                        for candidate in available_content:
                            asset_id = candidate['asset_id']
                            current_category = candidate.get('duration_category', '')
                            current_theme = candidate.get('theme', '').strip() if candidate.get('theme') else None
                            
                            # Start with base score from SQL query (already calculated)
                            # Add small random component to break ties between similar content
                            score = 100 + random.uniform(-5, 5)  # Base score with small random variation
                            
                            # Boost score for featured content
                            if candidate.get('featured', False):
                                score += 150  # Significant boost for featured content
                                logger.debug(f"Featured content boost for '{candidate.get('content_title', 'Unknown')}'")
                            
                            # Apply fatigue penalty based on recent plays within this schedule
                            if asset_id in recent_plays:
                                plays = recent_plays[asset_id]
                                for play_time in plays:
                                    time_gap = (total_duration - play_time) / 3600  # Hours since last play
                                    
                                    if time_gap < 1:
                                        score -= 100  # Heavy penalty for content played within 1 hour
                                    elif time_gap < 2:
                                        score -= 50   # Medium penalty for 1-2 hours
                                    elif time_gap < 4:
                                        score -= 25   # Light penalty for 2-4 hours
                                    elif time_gap < 6:
                                        score -= 10   # Very light penalty for 4-6 hours
                                
                                # Additional penalty for multiple plays
                                if len(plays) >= 3:
                                    score -= 50 * (len(plays) - 2)  # Heavy penalty for 3+ plays
                            
                            # Get the actual content type
                            content_type = candidate.get('content_type', '').lower()
                            
                            # Check what was requested in the rotation - content type or duration category
                            # Use the actual requested category from the current rotation position
                            requested_category_lower = requested_category.lower()
                            
                            # Determine which delay rules to apply based on what was requested
                            if requested_category_lower in content_type_defaults:
                                # A content type was requested (like BMP, PSA, MAF)
                                # Use content-type specific delays regardless of duration category
                                if asset_id in recent_plays and len(recent_plays[asset_id]) > 0:
                                    last_play = recent_plays[asset_id][-1]
                                    time_gap = (total_duration - last_play) / 3600
                                    
                                    min_delay = content_type_defaults.get(content_type, 3)
                                    if time_gap < min_delay:
                                        penalty = 200 * (min_delay - time_gap) / min_delay
                                        score -= penalty
                                        logger.debug(f"Content type {content_type} penalty: -{penalty:.0f} (gap: {time_gap:.1f}h < {min_delay}h)")
                                
                                # Bonus for content types not recently played
                                if asset_id not in recent_plays:
                                    score += 30
                                
                                # Extra penalty if this content has been used multiple times today
                                if asset_id in recent_plays:
                                    plays_today = len(recent_plays[asset_id])
                                    if plays_today >= 2:
                                        score -= 30 * (plays_today - 1)  # Increasing penalty for multiple uses
                            else:
                                # A duration category was requested (id, spots, short_form, long_form)
                                # Apply duration category rules
                                if current_category == 'id':
                                    if asset_id in recent_plays and len(recent_plays[asset_id]) > 0:
                                        last_play = recent_plays[asset_id][-1]
                                        time_gap = (total_duration - last_play) / 3600
                                        if time_gap < 2:
                                            score -= 300  # Very heavy penalty for IDs within 2 hours
                                    
                                    # Bonus for IDs not recently played
                                    if asset_id not in recent_plays:
                                        score += 50
                                    
                                    # Extra penalty if this ID has been used multiple times today
                                    if asset_id in recent_plays:
                                        plays_today = len(recent_plays[asset_id])
                                        if plays_today >= 2:
                                            score -= 50 * (plays_today - 1)  # Heavier penalty for IDs
                            
                            # Theme conflict check for all short-form content
                            # Short-form content with same theme must be separated by long_form
                            if self._has_theme_conflict(candidate, last_scheduled_category, 
                                                       last_scheduled_theme, current_category,
                                                       scheduled_items):
                                score -= 400  # Heavy penalty for theme conflicts
                                content_type = candidate.get('content_type', 'unknown')
                                logger.debug(f"Theme conflict penalty for {content_type} with theme '{current_theme}'")
                            
                            # Track best scoring content
                            if score > best_score:
                                best_score = score
                                content = candidate
                    
                    # If no good content found (all have very negative scores), use the first available
                    if not content and available_content:
                        content = available_content[0]
                        logger.warning(f"All content has poor scores, using first available")
                    
                    if not content:
                        # This shouldn't happen if available_content has items
                        consecutive_errors += 1
                        total_errors += 1
                        continue
                    
                    # Log selected content details
                    if content:
                        play_count = len(recent_plays.get(content['asset_id'], []))
                        delay_factor = content.get('_delay_factor_used', 1.0)
                        logger.debug(f"Selected: {content.get('content_title', 'Unknown')} "
                                   f"(ID: {content['asset_id']}, Category: {content.get('duration_category')}, "
                                   f"Theme: {content.get('theme', 'None')}, Plays: {play_count}, Score: {best_score}, "
                                   f"Delay Factor: {delay_factor*100:.0f}%)")
                        
                        # Track delay reduction usage
                        if delay_factor == 1.0:
                            delay_reduction_stats['full_delays'] += 1
                        elif delay_factor == 0.75:
                            delay_reduction_stats['reduced_75'] += 1
                        elif delay_factor == 0.5:
                            delay_reduction_stats['reduced_50'] += 1
                        elif delay_factor == 0.25:
                            delay_reduction_stats['reduced_25'] += 1
                        elif delay_factor == 0.0:
                            delay_reduction_stats['no_delays'] += 1
                    
                    # Check if this was a reset
                    if content.get('_was_reset', False):
                        delay_reduction_stats['resets'] += 1
                        category_reset_counts[duration_category] += 1
                        logger.warning(f"🔄 Using RESET content for {duration_category} (reset #{category_reset_counts[duration_category]})")
                    
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
                                # Check for theme conflict before accepting this alternative
                                if self._has_theme_conflict(alt_content, last_scheduled_category, 
                                                           last_scheduled_theme, duration_category,
                                                           scheduled_items, remaining_hours=remaining_hours):
                                    logger.debug(f"Skipping alternative content due to theme conflict: {alt_content.get('theme')}")
                                    continue
                                
                                # Found content that fits and has no theme conflict!
                                content = alt_content
                                content_duration = alt_duration
                                found_fitting_content = True
                                logger.info(f"Found alternative content that fits in remaining {remaining_seconds/60:.1f} minutes")
                                break
                        
                        if not found_fitting_content:
                            # No content fits in remaining time, move to next day
                            logger.info(f"No content fits in remaining {remaining_seconds/60:.1f} minutes on {day_name}, moving to next day")
                            
                            # Special handling for very small gaps
                            if remaining_seconds < 60:  # Less than 1 minute
                                logger.warning(f"Accepting {remaining_seconds:.1f} second gap at end of {day_name} to prevent infinite loop")
                                # Count this as a completed iteration to prevent infinite loops
                                no_progress_iterations = 0
                            
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
                    
                    # Track recent plays for fatigue prevention
                    if content['asset_id'] not in recent_plays:
                        recent_plays[content['asset_id']] = []
                    recent_plays[content['asset_id']].append(total_duration)
                    
                    # Log delay tracking info
                    if len(scheduled_asset_times[content['asset_id']]) > 1:
                        prev_time = scheduled_asset_times[content['asset_id']][-2]
                        time_since_last = (total_duration - prev_time) / 3600
                        delay_factor = content.get('_delay_factor_used', 1.0)
                        logger.info(f"Asset {content['asset_id']} scheduled again after {time_since_last:.1f}h (delay factor: {delay_factor*100:.0f}%)")
                    
                    # Add to schedule
                    item = {
                        'schedule_id': schedule_id,
                        'asset_id': content['asset_id'],
                        'instance_id': content['instance_id'],
                        'sequence_number': sequence_number,
                        'scheduled_start_time': scheduled_start,
                        'scheduled_duration_seconds': content_duration,  # Use the exact duration we used for calculations
                        # Add metadata for theme conflict checking
                        'content_type': content.get('content_type'),
                        'theme': content.get('theme'),
                        'duration_category': content.get('duration_category'),
                        'file_name': content.get('file_name')  # Add for holiday greeting tracking
                    }
                    
                    scheduled_items.append(item)
                    scheduled_asset_ids.append(content['asset_id'])
                    day_scheduled_asset_ids.append(content['asset_id'])
                    
                    # Update totals
                    total_duration += content_duration
                    sequence_number += 1
                    
                    # Advance rotation only if this wasn't featured content
                    # Featured content doesn't participate in the rotation
                    if not content.get('featured'):
                        self._advance_rotation()
                    
                    # Update theme tracking for next iteration
                    last_scheduled_theme = content.get('theme', '').strip() if content.get('theme') else None
                    last_scheduled_category = content.get('duration_category', '')
                    
                    # Update featured content tracking if we just scheduled a featured item
                    if content.get('featured'):
                        last_featured_time = total_duration
                        logger.info(f"✨ Featured content scheduled at {total_duration/3600:.2f} hours on {day_name}, next featured at ~{(total_duration + featured_delay * 3600)/3600:.2f} hours")
                    
                    # Calculate actual air time for this item
                    # The item starts at (total_duration - content_duration) seconds from schedule start
                    actual_air_time = start_date_obj + timedelta(seconds=total_duration - content_duration)
                    
                    # Update the asset's last scheduled date with actual air time
                    self._update_asset_last_scheduled(content['asset_id'], actual_air_time)
                    
                    # Reset no-progress counter since we made progress
                    no_progress_iterations = 0
                    last_progress_duration = total_duration
                    consecutive_no_content_cycles = 0  # Reset cycle counter on successful scheduling
                    
                    # Stop if we've filled the current day
                    if total_duration >= day_target_seconds:
                        break
                
                # Check if the day was fully completed
                day_duration = total_duration - day_start_time
                expected_day_duration = 24 * 60 * 60
                completion_percentage = (day_duration / expected_day_duration) * 100
                
                if completion_percentage < 95:  # Allow 5% tolerance
                    logger.error(f"❌ {day_name} incomplete: only {completion_percentage:.1f}% filled ({day_duration/3600:.1f} hours)")
                    
                    # Check if this is due to a large gap before end of day
                    # If we have a reasonable amount of content but can't fill the last bit, that's different
                    # from running out of content early in the day
                    hours_filled = day_duration / 3600
                    if hours_filled < 20:  # Less than 20 hours means we ran out of content too early
                        logger.error(f"❌ Critical failure: Only {hours_filled:.1f} hours of content for {day_name}")
                        # Delete the partially created schedule
                        self.delete_schedule(schedule_id)
                        return {
                            'success': False,
                            'message': f'Schedule creation failed: {day_name} could only be filled for {hours_filled:.1f} hours. '
                                     f'This indicates insufficient content. Please add more content or adjust replay delay settings.',
                            'error': 'insufficient_content',
                            'days_completed': days_completed,
                            'failed_day': day_name,
                            'hours_filled': hours_filled
                        }
                    else:
                        # Just a gap at end of day, log warning but continue
                        logger.warning(f"⚠️ {day_name} has a gap at end of day: {24 - hours_filled:.1f} hours empty")
                        # Don't fail the schedule for small end-of-day gaps
                
                # Log day completion with info about content reuse
                day_items = len(day_scheduled_asset_ids)
                reused_items = day_items - len(set(day_scheduled_asset_ids))
                logger.info(f"✅ Completed {day_name} with {day_items} items ({reused_items} repeated within day) - {completion_percentage:.1f}% filled")
                days_completed += 1
                
                if day_offset > 0:
                    logger.info(f"Content can be reused from previous days for variety across the week")
            
            # Final validation: ensure we have a complete week
            expected_total_duration = 7 * 24 * 60 * 60  # 7 days
            actual_completion = (total_duration / expected_total_duration) * 100
            
            if days_completed < 7:
                logger.error(f"❌ Weekly schedule incomplete: only {days_completed} of 7 days completed")
                self.delete_schedule(schedule_id)
                return {
                    'success': False,
                    'message': f'Schedule creation failed: Only {days_completed} of 7 days could be filled. '
                             f'Please add more content or adjust replay delay settings.',
                    'error': 'incomplete_week',
                    'days_completed': days_completed,
                    'total_duration_hours': total_duration / 3600
                }
            
            if actual_completion < 95:  # Allow 5% tolerance for the full week
                logger.error(f"❌ Weekly schedule incomplete: only {actual_completion:.1f}% of week filled")
                self.delete_schedule(schedule_id)
                return {
                    'success': False,
                    'message': f'Schedule creation failed: Only {actual_completion:.1f}% of the week could be filled. '
                             f'Please add more content or adjust replay delay settings.',
                    'error': 'incomplete_duration',
                    'actual_hours': total_duration / 3600,
                    'expected_hours': expected_total_duration / 3600
                }
            
            # Debug: Log first few items to check time format
            if scheduled_items:
                logger.debug("First 5 scheduled items before saving:")
                for i, item in enumerate(scheduled_items[:5]):
                    logger.debug(f"  Item {i+1}: start_time={item['scheduled_start_time']}, duration={item['scheduled_duration_seconds']:.6f}s, type={type(item['scheduled_start_time'])}")
            
            # Save all scheduled items
            saved_count = self._save_scheduled_items(scheduled_items)
            
            # Update schedule total duration
            self._update_schedule_duration(schedule_id, total_duration)
            
            # Log delay reduction statistics
            total_delay_stats = sum(delay_reduction_stats.values())
            if total_delay_stats > 0:
                logger.info("=== Delay Reduction Statistics ===")
                logger.info(f"Total items scheduled: {total_delay_stats}")
                logger.info(f"Full delays (100%): {delay_reduction_stats['full_delays']} ({delay_reduction_stats['full_delays']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['reduced_75'] > 0:
                    logger.warning(f"⚠️ Reduced to 75%: {delay_reduction_stats['reduced_75']} ({delay_reduction_stats['reduced_75']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['reduced_50'] > 0:
                    logger.warning(f"⚠️ Reduced to 50%: {delay_reduction_stats['reduced_50']} ({delay_reduction_stats['reduced_50']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['reduced_25'] > 0:
                    logger.warning(f"⚠️ Reduced to 25%: {delay_reduction_stats['reduced_25']} ({delay_reduction_stats['reduced_25']/total_delay_stats*100:.1f}%)")
                if delay_reduction_stats['no_delays'] > 0:
                    logger.error(f"❌ No delays (0%): {delay_reduction_stats['no_delays']} ({delay_reduction_stats['no_delays']/total_delay_stats*100:.1f}%)")
                
                # Warn if too many items required reduced delays
                reduced_count = total_delay_stats - delay_reduction_stats['full_delays']
                if reduced_count > total_delay_stats * 0.2:  # More than 20% required reduction
                    logger.warning(f"⚠️ {reduced_count/total_delay_stats*100:.1f}% of items required reduced delays - consider adding more content or adjusting delay settings")
            
            logger.info(f"Created weekly schedule with {saved_count} items, total duration: {total_duration/3600:.2f} hours")
            
            return {
                'success': True,
                'message': f'Successfully created weekly schedule starting {start_date_obj.strftime("%Y-%m-%d")}',
                'schedule_id': schedule_id,
                'total_items': saved_count,
                'total_duration_hours': total_duration / 3600,
                'schedule_type': 'weekly',
                'delay_reduction_stats': delay_reduction_stats
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
            
            # Reset holiday greeting session tracking for new schedule
            self._ensure_holiday_integration()
            if hasattr(self, 'holiday_integration') and self.holiday_integration.enabled:
                self.holiday_integration.reset_session()
            
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
            
            # Track the theme of the last scheduled item to avoid back-to-back same themes
            last_scheduled_theme = None
            last_scheduled_category = None
            
            # Track recent plays for fatigue prevention (asset_id -> list of scheduled times)
            recent_plays = {}
            
            # Infinite loop detection
            last_progress_duration = 0
            no_progress_iterations = 0
            max_no_progress = 50  # Allow max 50 iterations without progress
            consecutive_no_content_cycles = 0  # Track cycles where all categories fail
            max_no_content_cycles = 3  # Max full rotation cycles with no content
            
            # Track featured content scheduling
            last_featured_time = 0  # Initialize to 0 so featured content can be scheduled immediately
            featured_content_index = 0  # Track which featured content to use next
            
            # Get featured delay from config
            try:
                from config_manager import ConfigManager
                config_mgr = ConfigManager()
                scheduling_config = config_mgr.get_scheduling_settings()
                featured_config = scheduling_config.get('featured_content', {})
                featured_delay = featured_config.get('minimum_spacing', 2.0)
                logger.info(f"Featured content minimum spacing: {featured_delay} hours")
            except:
                featured_config = {}
                featured_delay = 2.0
                logger.info(f"Using default featured config")
            
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
                    # Check if we should try to schedule featured content
                    if self._should_schedule_featured_content(total_duration, last_featured_time, featured_delay):
                        # Get all available featured content
                        featured_content = self.get_featured_content(
                            exclude_ids=[],
                            schedule_date=current_date.strftime('%Y-%m-%d')
                        )
                        
                        if featured_content:
                            # We have featured content and enough time has passed
                            # Use round-robin selection of featured content
                            content = featured_content[featured_content_index % len(featured_content)]
                            featured_content_index += 1
                            
                            logger.info(f"Scheduling featured content: {content.get('content_title', 'Unknown')} "
                                      f"at {total_duration/3600:.2f} hours on {current_date.strftime('%B %d')}")
                            
                            available_content = [content]
                        else:
                            # No featured content available, get regular content
                            duration_category = self._get_next_duration_category()
                            available_content = self._get_content_with_progressive_delays(
                                duration_category, 
                                exclude_ids=day_scheduled_asset_ids,
                                schedule_date=current_date.strftime('%Y-%m-%d'),
                                scheduled_asset_times=None
                            )
                    else:
                        # Not time for featured content yet, get regular content
                        duration_category = self._get_next_duration_category()
                        available_content = self._get_content_with_progressive_delays(
                            duration_category, 
                            exclude_ids=day_scheduled_asset_ids,
                            schedule_date=current_date.strftime('%Y-%m-%d'),
                            scheduled_asset_times=None
                        )
                    
                    if not available_content:
                        current_time_str = self._seconds_to_time(total_duration % (24 * 60 * 60))
                        logger.warning(f"No available content for category: {duration_category} on {day_name} at {current_time_str} "
                                     f"(hour {(total_duration % (24 * 60 * 60)) / 3600:.1f}) even without delays. "
                                     f"Remaining hours in day: {remaining_hours:.1f}")
                        
                        # Check if we're near midnight and trying to schedule longform content
                        # Skip longform requirement if within last 2 hours of the day
                        if remaining_hours < 2.0 and duration_category == 'long_form':
                            logger.info(f"Skipping long_form content near midnight (only {remaining_hours:.1f} hours left). Advancing rotation.")
                            self._advance_rotation()
                            consecutive_errors = 0  # Reset error counter since we're making progress
                            continue
                        
                        consecutive_errors += 1
                        total_errors += 1
                        
                        # IMPORTANT: Always advance rotation when no content is found
                        # This prevents getting stuck on the same category
                        self._advance_rotation()
                        logger.info(f"Advanced rotation to next category after no content found for {duration_category}")
                        
                        # Check if we should abort (only for significant gaps)
                        if consecutive_errors >= max_errors and remaining_hours > 1.0:
                            logger.error(f"Aborting schedule creation: {consecutive_errors} consecutive errors with {remaining_hours:.1f} hours remaining")
                            # Delete the partially created schedule
                            self.delete_schedule(schedule_id)
                            return {
                                'success': False,
                                'message': f'Schedule creation failed: No available content after {total_errors} attempts. Check content availability.',
                                'error_count': total_errors
                            }
                            
                        # If we're near the end of the day and have many consecutive errors, accept the gap
                        if consecutive_errors >= 10 and remaining_hours < 0.5:
                            logger.warning(f"Accepting gap of {remaining_hours:.1f} hours at end of {day_name} after {consecutive_errors} consecutive errors")
                            total_duration = day_target_seconds
                            break
                            
                        continue
                    
                    # Select the best content, avoiding same theme back-to-back for PSAs, spots, and IDs
                    content = None
                    
                    # If we have featured content selected, use it directly without theme checking
                    if available_content and len(available_content) == 1 and available_content[0].get('featured'):
                        content = available_content[0]
                        logger.debug(f"Using featured content directly: {content.get('content_title', 'Unknown')}")
                    else:
                        # Try to find content that doesn't have the same theme for IDs and spots
                        for candidate in available_content:
                            current_category = candidate.get('duration_category', '')
                            current_theme = candidate.get('theme', '').strip() if candidate.get('theme') else None
                            
                            # Theme conflict check for IDs and spots (regardless of content type)
                            if (last_scheduled_category in ['id', 'spots'] and 
                                current_category in ['id', 'spots'] and
                                current_theme and last_scheduled_theme and
                                current_theme.lower() == last_scheduled_theme.lower()):
                                logger.info(f"Skipping content with same theme '{current_theme}' as previous item "
                                          f"({last_scheduled_category} -> {current_category})")
                                continue
                            
                            # This content is acceptable
                            content = candidate
                            break
                        
                        # If no content found without theme conflict, use the first available
                        if not content and available_content:
                            content = available_content[0]
                            logger.warning(f"No content available without theme conflict, using first available")
                    
                    if not content:
                        # This shouldn't happen if available_content has items
                        consecutive_errors += 1
                        total_errors += 1
                        continue
                    
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
                                # Check for theme conflict before accepting this alternative
                                if self._has_theme_conflict(alt_content, last_scheduled_category, 
                                                           last_scheduled_theme, duration_category,
                                                           scheduled_items, remaining_hours=remaining_hours):
                                    logger.debug(f"Skipping alternative content due to theme conflict: {alt_content.get('theme')}")
                                    continue
                                
                                # Found content that fits and has no theme conflict!
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
                        'scheduled_duration_seconds': content_duration,
                        # Add metadata for theme conflict checking
                        'content_type': content.get('content_type'),
                        'theme': content.get('theme'),
                        'duration_category': content.get('duration_category'),
                        'file_name': content.get('file_name')  # Add for holiday greeting tracking
                    }
                    
                    scheduled_items.append(item)
                    scheduled_asset_ids.append(content['asset_id'])
                    day_scheduled_asset_ids.append(content['asset_id'])
                    
                    # Track recent plays for fatigue prevention
                    if content['asset_id'] not in recent_plays:
                        recent_plays[content['asset_id']] = []
                    recent_plays[content['asset_id']].append(total_duration)
                    
                    # Update totals
                    total_duration += content_duration
                    sequence_number += 1
                    
                    # Advance rotation only if this wasn't featured content
                    # Featured content doesn't participate in the rotation
                    if not content.get('featured'):
                        self._advance_rotation()
                    
                    # Update theme tracking for next iteration
                    last_scheduled_theme = content.get('theme', '').strip() if content.get('theme') else None
                    last_scheduled_category = content.get('duration_category', '')
                    
                    # Update featured content tracking if we just scheduled a featured item
                    if content.get('featured'):
                        last_featured_time = total_duration
                        logger.info(f"✨ Featured content scheduled at {total_duration/3600:.2f} hours on {current_date.strftime('%B %d')}, next featured at ~{(total_duration + featured_delay * 3600)/3600:.2f} hours")
                    
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