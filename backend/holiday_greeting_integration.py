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

logger = logging.getLogger(__name__)

class HolidayGreetingIntegration:
    """Safe integration wrapper for holiday greeting scheduling"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.config_file = 'holiday_greeting_config.json'
        self.scheduler = None
        self.enabled = False
        self._load_config_and_init()
        
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
                        logger.info("Holiday Greeting Fair Rotation: ENABLED")
                    else:
                        logger.info("Holiday Greeting Fair Rotation: DISABLED (config file exists but enabled=false)")
            else:
                logger.info("Holiday Greeting Fair Rotation: DISABLED (no config file)")
        except Exception as e:
            logger.error(f"Error loading holiday greeting config: {e}")
            self.enabled = False
    
    def filter_available_content(self, available_content: List[Dict[str, Any]], 
                               duration_category: str, 
                               exclude_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Filter available content to ensure fair holiday greeting rotation
        
        This is the MAIN INTEGRATION POINT. When enabled, it:
        1. Removes ALL holiday greetings from the normal selection
        2. Selects ONE greeting using fair rotation algorithm
        3. Returns the fair selection + all non-greeting content
        
        Args:
            available_content: List of content items from normal selection
            duration_category: The duration category being filled
            exclude_ids: Asset IDs already scheduled
            
        Returns:
            Filtered/modified content list
        """
        if not self.enabled or not self.scheduler:
            return available_content
        
        try:
            # Step 1: Remove ALL holiday greetings from the list
            other_content = []
            removed_greetings = []
            
            for content in available_content:
                if self.scheduler.is_holiday_greeting(
                    content.get('file_name', ''), 
                    content.get('content_title')
                ):
                    removed_greetings.append(content)
                else:
                    other_content.append(content)
            
            logger.info(f"Removed {len(removed_greetings)} holiday greetings from normal selection")
            
            # Step 2: Get the BEST holiday greeting using our algorithm
            best_greeting = self.get_best_holiday_greeting(
                duration_category, 
                exclude_ids,
                removed_greetings  # Pass the greetings that were available
            )
            
            # Step 3: Return our selected greeting + all non-greeting content
            if best_greeting:
                logger.info(f"Selected holiday greeting: {best_greeting.get('file_name')} "
                          f"(replacing {len(removed_greetings)} options from old selection)")
                return [best_greeting] + other_content
            else:
                # No suitable holiday greeting found, just return non-greeting content
                if removed_greetings:
                    logger.warning(f"Could not find suitable holiday greeting to replace {len(removed_greetings)} removed items")
                return other_content
            
        except Exception as e:
            logger.error(f"Error in holiday greeting filtering: {e}")
            # On error, return original list unchanged
            return available_content
    
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