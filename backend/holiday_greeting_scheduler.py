#!/usr/bin/env python3
"""
Holiday Greeting Fair Rotation Scheduler
========================================
A standalone module for ensuring fair rotation of holiday greeting content.
This module does NOT modify existing scheduling logic and operates independently.

Author: Claude
Created: December 2025
Status: INACTIVE until explicitly enabled
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import json
import os

# Create dedicated logger for holiday greeting scheduling
logger = logging.getLogger('holiday_greeting_scheduler')
logger.setLevel(logging.DEBUG)

# Create file handler for holiday greeting logs
handler = logging.FileHandler('logs/holiday_greeting_scheduler.log')
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(handler)


class HolidayGreetingScheduler:
    """
    Manages fair rotation of holiday greeting content.
    
    This class is designed to:
    1. Track which holiday greetings have been scheduled
    2. Ensure fair distribution across all available greetings
    3. Prevent over-scheduling of any single greeting
    4. Integrate safely with existing scheduling system
    """
    
    def __init__(self, db_manager=None, config=None):
        """
        Initialize the Holiday Greeting Scheduler.
        
        Args:
            db_manager: Database manager instance (optional for now)
            config: Configuration dictionary (optional)
        """
        self.db_manager = db_manager
        
        # Load config from file if it exists, otherwise use default
        if config:
            self.config = config
        else:
            config_file = 'holiday_greeting_config.json'
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        loaded_config = json.load(f)
                        # Start with default and update with loaded config
                        self.config = self._get_default_config()
                        self.config.update(loaded_config)
                        logger.info(f"Loaded config from {config_file}: enabled={self.config.get('enabled')}")
                except Exception as e:
                    logger.error(f"Error loading config file: {e}")
                    self.config = self._get_default_config()
            else:
                self.config = self._get_default_config()
        
        # Pattern to identify holiday greetings
        self.greeting_pattern = re.compile(
            r'holiday\s*greeting', 
            re.IGNORECASE
        )
        
        # In-memory tracking (until DB table approved)
        self.rotation_history = {}
        
        # Log initialization status based on actual config
        mode = "ACTIVE" if self.config.get('enabled', False) else "INACTIVE"
        logger.info(f"Holiday Greeting Scheduler initialized ({mode} MODE)")
        logger.info(f"Configuration: {json.dumps(self.config, indent=2, default=str)}")
    
    def _get_default_config(self) -> Dict:
        """Get default configuration for holiday greeting scheduling."""
        return {
            'enabled': False,  # MUST BE EXPLICITLY ENABLED
            'min_time_between_plays': {
                'hours': 2
            },
            'max_plays_per_day': 3,
            'max_plays_per_week': 10,
            'fair_rotation_weight': 0.9,  # 90% fair rotation, 10% random
            'date_range': {
                'start': '2025-12-01',
                'end': '2026-01-15'
            },
            'excluded_patterns': [],  # Patterns to exclude
            'priority_boost_unplayed': 1000,  # Score boost for never-played content
            'replay_delay_minutes': 120  # 2 hours minimum between replays
        }
    
    def is_enabled(self) -> bool:
        """Check if the holiday greeting scheduler is enabled."""
        enabled = self.config.get('enabled', False)
        if enabled:
            # Check if we're within the active date range
            now = datetime.now()
            start_date = datetime.fromisoformat(self.config['date_range']['start'])
            end_date = datetime.fromisoformat(self.config['date_range']['end'])
            
            if start_date <= now <= end_date:
                logger.debug("Holiday Greeting Scheduler is ACTIVE")
                return True
            else:
                logger.debug(f"Holiday Greeting Scheduler outside date range: {start_date} to {end_date}")
                return False
        else:
            logger.debug("Holiday Greeting Scheduler is DISABLED")
            return False
    
    def is_holiday_greeting(self, file_name: str, content_title: Optional[str] = None) -> bool:
        """
        Determine if a content item is a holiday greeting.
        
        Args:
            file_name: The filename to check
            content_title: Optional content title to check
            
        Returns:
            True if this is a holiday greeting content
        """
        # Check filename
        if self.greeting_pattern.search(file_name):
            logger.debug(f"Identified holiday greeting by filename: {file_name}")
            return True
        
        # Check content title if provided
        if content_title and self.greeting_pattern.search(content_title):
            logger.debug(f"Identified holiday greeting by title: {content_title}")
            return True
        
        return False
    
    def get_scheduling_priority(self, asset_id: int, file_name: str) -> float:
        """
        Calculate scheduling priority for a holiday greeting.
        
        Higher scores = higher priority to be scheduled.
        
        Args:
            asset_id: The asset ID
            file_name: The filename
            
        Returns:
            Priority score (higher = more likely to be scheduled)
        """
        if not self.is_enabled():
            return 0.0
        
        # Get history from memory (will be from DB later)
        history = self.rotation_history.get(asset_id, {
            'scheduled_count': 0,
            'last_scheduled': None
        })
        
        scheduled_count = history['scheduled_count']
        last_scheduled = history['last_scheduled']
        
        # Base priority inversely proportional to scheduled count
        if scheduled_count == 0:
            priority = self.config['priority_boost_unplayed']
        else:
            priority = 100.0 / (scheduled_count + 1)
        
        # Boost priority based on time since last scheduled
        if last_scheduled:
            hours_since = (datetime.now() - last_scheduled).total_seconds() / 3600
            time_boost = min(hours_since / 24, 10.0)  # Max boost of 10 after 10 days
            priority += time_boost
        
        logger.debug(f"Priority for {file_name}: {priority:.2f} "
                    f"(count: {scheduled_count}, last: {last_scheduled})")
        
        return priority
    
    def record_scheduling(self, asset_id: int, file_name: str):
        """
        Record that a holiday greeting has been scheduled.
        
        Args:
            asset_id: The asset ID that was scheduled
            file_name: The filename that was scheduled
        """
        if not self.is_enabled():
            return
        
        if asset_id not in self.rotation_history:
            self.rotation_history[asset_id] = {
                'scheduled_count': 0,
                'last_scheduled': None,
                'file_name': file_name
            }
        
        self.rotation_history[asset_id]['scheduled_count'] += 1
        self.rotation_history[asset_id]['last_scheduled'] = datetime.now()
        
        logger.info(f"Recorded scheduling: {file_name} "
                   f"(total: {self.rotation_history[asset_id]['scheduled_count']})")
    
    def get_rotation_stats(self) -> Dict:
        """
        Get statistics about holiday greeting rotation.
        
        Returns:
            Dictionary containing rotation statistics
        """
        if not self.rotation_history:
            return {
                'total_unique_greetings': 0,
                'total_plays': 0,
                'never_played': 0,
                'distribution': {}
            }
        
        total_plays = sum(h['scheduled_count'] for h in self.rotation_history.values())
        never_played = sum(1 for h in self.rotation_history.values() if h['scheduled_count'] == 0)
        
        distribution = {
            h['file_name']: h['scheduled_count'] 
            for h in self.rotation_history.values()
        }
        
        return {
            'total_unique_greetings': len(self.rotation_history),
            'total_plays': total_plays,
            'never_played': never_played,
            'distribution': distribution,
            'most_played': max(distribution.items(), key=lambda x: x[1]) if distribution else None,
            'least_played': min(distribution.items(), key=lambda x: x[1]) if distribution else None
        }
    
    def should_override_selection(self, original_selection: Dict) -> bool:
        """
        Determine if we should override the normal content selection.
        
        Args:
            original_selection: The content item selected by normal scheduling
            
        Returns:
            True if we should override this selection
        """
        if not self.is_enabled():
            return False
        
        # Check if the original selection is a holiday greeting
        if not self.is_holiday_greeting(
            original_selection.get('file_name', ''),
            original_selection.get('content_title')
        ):
            return False
        
        # Check if this greeting has been over-scheduled
        asset_id = original_selection.get('asset_id')
        if not asset_id:
            return False
        
        history = self.rotation_history.get(asset_id, {'scheduled_count': 0})
        avg_plays = sum(h['scheduled_count'] for h in self.rotation_history.values()) / max(len(self.rotation_history), 1)
        
        # Override if this greeting has been played significantly more than average
        if history['scheduled_count'] > avg_plays * 1.5:
            logger.info(f"Overriding selection of {original_selection.get('file_name')} "
                       f"(played {history['scheduled_count']} times, avg: {avg_plays:.1f})")
            return True
        
        return False
    
    def get_next_holiday_greeting(self, duration_category: str, 
                                excluded_asset_ids: Optional[Set[int]] = None) -> Optional[Dict]:
        """
        Get the next holiday greeting to schedule using fair rotation.
        
        NOTE: This method currently returns None as it requires database access.
        It will be implemented once the database table is approved.
        
        Args:
            duration_category: The duration category needed
            excluded_asset_ids: Set of asset IDs to exclude
            
        Returns:
            Content item dictionary or None
        """
        if not self.is_enabled():
            return None
        
        logger.warning("get_next_holiday_greeting called but DB access not yet implemented")
        return None
    
    def generate_rotation_report(self) -> str:
        """Generate a human-readable report of holiday greeting rotation."""
        stats = self.get_rotation_stats()
        
        report = [
            "Holiday Greeting Rotation Report",
            "=" * 40,
            f"Status: {'ENABLED' if self.is_enabled() else 'DISABLED'}",
            f"Total Unique Greetings: {stats['total_unique_greetings']}",
            f"Total Plays: {stats['total_plays']}",
            f"Never Played: {stats['never_played']}",
            "",
            "Distribution:",
            "-" * 40
        ]
        
        if stats['distribution']:
            for file_name, count in sorted(stats['distribution'].items(), 
                                         key=lambda x: x[1], reverse=True):
                report.append(f"{count:3d} plays - {file_name}")
        else:
            report.append("No holiday greetings have been scheduled yet")
        
        return "\n".join(report)


# Module-level instance (not active until explicitly enabled)
_scheduler_instance = None

def get_holiday_scheduler(db_manager=None) -> HolidayGreetingScheduler:
    """
    Get the singleton instance of the Holiday Greeting Scheduler.
    
    Args:
        db_manager: Database manager to use
        
    Returns:
        HolidayGreetingScheduler instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = HolidayGreetingScheduler(db_manager)
    return _scheduler_instance


# Test function (safe to run)
if __name__ == "__main__":
    print("Holiday Greeting Scheduler Module Test")
    print("-" * 40)
    
    scheduler = get_holiday_scheduler()
    
    # Test pattern matching
    test_files = [
        "251210_SSP_Strategy Office Holiday Greeting.mp4",
        "251209_SPP_Mayor Holiday Greeting.mp4",
        "some_other_file.mp4",
        "Holiday_Greetings_2024.mp4"
    ]
    
    print("\nPattern Matching Test:")
    for file in test_files:
        is_greeting = scheduler.is_holiday_greeting(file)
        print(f"{file}: {'YES' if is_greeting else 'NO'}")
    
    print("\nScheduler Status:")
    print(f"Enabled: {scheduler.is_enabled()}")
    
    print("\nRotation Report:")
    print(scheduler.generate_rotation_report())