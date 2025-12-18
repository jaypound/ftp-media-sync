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
        
        This is the MAIN INTEGRATION POINT. It intercepts content selection
        and ensures holiday greetings are fairly distributed.
        
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
            # Check if any of the available content is a holiday greeting
            has_holiday_greeting = False
            holiday_greetings = []
            other_content = []
            
            for content in available_content:
                if self.scheduler.is_holiday_greeting(
                    content.get('file_name', ''), 
                    content.get('content_title')
                ):
                    has_holiday_greeting = True
                    holiday_greetings.append(content)
                else:
                    other_content.append(content)
            
            if not has_holiday_greeting:
                # No holiday greetings in this batch, return as-is
                return available_content
            
            logger.info(f"Found {len(holiday_greetings)} holiday greetings in {len(available_content)} available items")
            
            # Calculate priorities for all holiday greetings
            greeting_priorities = []
            for greeting in holiday_greetings:
                asset_id = greeting.get('asset_id') or greeting.get('id')
                if asset_id:
                    priority = self.scheduler.get_scheduling_priority(
                        asset_id, 
                        greeting.get('file_name', '')
                    )
                    greeting_priorities.append((greeting, priority))
            
            # Sort by priority (highest first)
            greeting_priorities.sort(key=lambda x: x[1], reverse=True)
            
            if greeting_priorities:
                # Log the selection decision
                selected = greeting_priorities[0][0]
                logger.info(f"Holiday greeting selected: {selected.get('file_name')} "
                          f"(priority: {greeting_priorities[0][1]:.2f})")
                
                # Return the highest priority greeting first, then other content
                return [selected] + other_content + [g[0] for g in greeting_priorities[1:]]
            
            return available_content
            
        except Exception as e:
            logger.error(f"Error in holiday greeting filtering: {e}")
            # On error, return original list unchanged
            return available_content
    
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
            """, (asset_id,))
            
            conn.commit()
            cursor.close()
            self.db_manager._put_connection(conn)
            
        except Exception as e:
            logger.error(f"Error updating holiday greeting database tracking: {e}")
    
    def get_status_report(self) -> str:
        """Get current status of holiday greeting rotation"""
        if not self.enabled:
            return "Holiday Greeting Fair Rotation: DISABLED"
        
        if self.scheduler:
            return self.scheduler.generate_rotation_report()
        
        return "Holiday Greeting Fair Rotation: ENABLED but not initialized"


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