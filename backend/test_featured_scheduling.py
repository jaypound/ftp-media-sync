#!/usr/bin/env python3
"""
Test script to verify featured content scheduling
"""

import sys
from datetime import datetime, timedelta
from scheduler_postgres import PostgreSQLScheduler

def test_featured_scheduling():
    """Test that featured content is scheduled every 1.5 hours"""
    
    scheduler = PostgreSQLScheduler()
    
    # Check if we have any featured content
    featured_content = scheduler.get_featured_content(
        exclude_ids=[],
        schedule_date=datetime.now().strftime('%Y-%m-%d')
    )
    
    if not featured_content:
        print("No featured content found in database")
        print("Please mark some content as featured and try again")
        return False
    
    print(f"Found {len(featured_content)} featured items:")
    for item in featured_content:
        print(f"  - {item['content_title']} (ID: {item['asset_id']})")
    
    # Test the scheduling logic
    print("\nTesting featured content scheduling intervals:")
    
    # Simulate scheduling for 24 hours
    last_featured_time = None
    featured_times = []
    
    for hours in range(24):
        for minutes in [0, 30]:
            current_time = hours * 3600 + minutes * 60
            
            # Check if featured content should be scheduled
            should_schedule = scheduler._should_schedule_featured_content(
                current_time, 
                last_featured_time, 
                1.5  # featured_delay
            )
            
            if should_schedule:
                featured_times.append(current_time / 3600)
                last_featured_time = current_time
                print(f"  Featured content scheduled at {current_time/3600:.1f} hours")
    
    # Verify intervals
    print(f"\nTotal featured content scheduled: {len(featured_times)}")
    
    if len(featured_times) > 1:
        intervals = []
        for i in range(1, len(featured_times)):
            interval = featured_times[i] - featured_times[i-1]
            intervals.append(interval)
            print(f"  Interval {i}: {interval:.1f} hours")
        
        avg_interval = sum(intervals) / len(intervals)
        print(f"\nAverage interval: {avg_interval:.1f} hours")
        
        if 1.4 <= avg_interval <= 1.6:
            print("✓ Featured content scheduling intervals are correct!")
            return True
        else:
            print("✗ Featured content scheduling intervals are incorrect")
            return False
    
    return True

if __name__ == "__main__":
    test_featured_scheduling()