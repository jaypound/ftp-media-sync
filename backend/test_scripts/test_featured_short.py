#!/usr/bin/env python3
"""
Quick test to verify featured content intervals in the first few hours of a schedule
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler_postgres import PostgreSQLScheduler
from datetime import datetime, timedelta

def test_featured_timing():
    """Test featured content timing directly"""
    
    scheduler = PostgreSQLScheduler()
    
    # Simulate schedule creation tracking variables
    total_duration = 0
    last_featured_time = 0
    featured_times = []
    featured_delay = 1.5  # hours
    
    print("Simulating schedule creation to check featured content timing...")
    print("=" * 50)
    
    # Simulate 10 hours of scheduling
    target_hours = 10
    target_seconds = target_hours * 3600
    
    while total_duration < target_seconds:
        # Check if we should schedule featured content
        if scheduler._should_schedule_featured_content(total_duration, last_featured_time, featured_delay):
            featured_times.append(total_duration / 3600)  # Convert to hours
            last_featured_time = total_duration
            print(f"Featured content at {total_duration/3600:.2f} hours")
        
        # Simulate adding regular content (average 30 minutes)
        content_duration = 1800  # 30 minutes
        total_duration += content_duration
    
    print(f"\nTotal featured items in {target_hours} hours: {len(featured_times)}")
    print(f"Expected featured items (every {featured_delay}h): {int(target_hours / featured_delay)}")
    
    # Check intervals
    if len(featured_times) > 1:
        print("\nIntervals between featured content:")
        intervals = []
        for i in range(1, len(featured_times)):
            interval = featured_times[i] - featured_times[i-1]
            intervals.append(interval)
            print(f"  Interval {i}: {interval:.2f} hours")
        
        avg_interval = sum(intervals) / len(intervals)
        print(f"\nAverage interval: {avg_interval:.2f} hours")
        
        return avg_interval <= 2.0
    
    return False

if __name__ == "__main__":
    success = test_featured_timing()
    if success:
        print("\n✓ Featured content timing logic is working correctly!")
    else:
        print("\n✗ Featured content timing issue detected")
    sys.exit(0 if success else 1)