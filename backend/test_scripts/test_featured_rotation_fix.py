#!/usr/bin/env python3
"""
Test that featured content appears every 1.5 hours after fixing rotation advancement
"""

import sys
import requests
from datetime import datetime, timedelta

def test_featured_intervals():
    """Create a test schedule and verify featured content appears every 1.5 hours"""
    
    # API endpoint
    base_url = "http://127.0.0.1:5000"
    
    # Test date (tomorrow)
    test_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"Creating test schedule for {test_date}...")
    
    # First, make sure we have featured content
    response = requests.get(f"{base_url}/api/content-scheduling-list")
    if response.status_code == 200:
        content_data = response.json()
        featured_count = sum(1 for item in content_data.get('data', []) if item.get('featured', False))
        print(f"Found {featured_count} featured content items in the system")
    
    # Create a daily schedule
    response = requests.post(f"{base_url}/api/create-schedule", json={
        "date": test_date,
        "schedule_name": f"Featured Rotation Fix Test - {test_date}"
    })
    
    if response.status_code != 200:
        print(f"Failed to create schedule: {response.text}")
        return False
    
    result = response.json()
    if not result.get('success'):
        print(f"Schedule creation failed: {result.get('message')}")
        return False
    
    schedule_id = result.get('schedule_id')
    print(f"Created schedule ID: {schedule_id}")
    
    # Get the schedule content
    response = requests.post(f"{base_url}/api/get-schedule", json={
        "date": test_date
    })
    if response.status_code != 200:
        print(f"Failed to get schedule: {response.text}")
        return False
    
    schedule_data = response.json()
    if not schedule_data.get('success'):
        print(f"Failed to get schedule data: {schedule_data.get('message')}")
        return False
        
    items = schedule_data.get('items', [])
    
    print(f"\nTotal items in schedule: {len(items)}")
    
    # Find all featured content items
    featured_items = []
    for i, item in enumerate(items):
        # Check if this is featured content (Hispanic Heritage Month items are featured)
        if 'Hispanic Heritage Month' in item.get('title', '') or item.get('featured', False):
            # Convert time to seconds
            time_parts = item.get('scheduled_start_time', '').split(':')
            if len(time_parts) >= 3:
                hours = int(time_parts[0])
                minutes = int(time_parts[1])
                seconds = float(time_parts[2])
                time_in_seconds = hours * 3600 + minutes * 60 + seconds
                time_in_hours = time_in_seconds / 3600
                
                featured_items.append({
                    'index': i,
                    'title': item.get('title'),
                    'time': item.get('scheduled_start_time'),
                    'time_hours': time_in_hours,
                    'duration': item.get('duration_seconds', 0)
                })
    
    print(f"\nFound {len(featured_items)} featured items:")
    for item in featured_items:
        print(f"  - {item['title']} at {item['time']} ({item['time_hours']:.2f} hours)")
    
    # Check intervals
    if len(featured_items) > 1:
        print("\nIntervals between featured content:")
        intervals = []
        for i in range(1, len(featured_items)):
            interval = featured_items[i]['time_hours'] - featured_items[i-1]['time_hours']
            intervals.append(interval)
            print(f"  Interval {i}: {interval:.2f} hours")
        
        avg_interval = sum(intervals) / len(intervals)
        print(f"\nAverage interval: {avg_interval:.2f} hours")
        
        # Check if intervals are approximately 1.5 hours
        expected_interval = 1.5
        tolerance = 0.25  # Tighter tolerance now that rotation is fixed
        
        correct_intervals = sum(1 for interval in intervals if expected_interval - tolerance <= interval <= expected_interval + tolerance)
        
        print(f"\nIntervals within expected range (1.25-1.75 hours): {correct_intervals}/{len(intervals)}")
        
        # Calculate expected vs actual featured items
        total_hours = items[-1].get('scheduled_start_time', '').split(':')
        if len(total_hours) >= 2:
            schedule_duration_hours = int(total_hours[0]) + int(total_hours[1])/60
            expected_featured_count = int(schedule_duration_hours / 1.5)
            print(f"\nSchedule duration: ~{schedule_duration_hours:.1f} hours")
            print(f"Expected featured items (every 1.5h): ~{expected_featured_count}")
            print(f"Actual featured items: {len(featured_items)}")
            
            if abs(len(featured_items) - expected_featured_count) <= 2:
                print("✓ Featured content count matches expected frequency!")
            else:
                print("✗ Featured content count does not match expected frequency")
        
        if avg_interval <= 2.0 and correct_intervals >= len(intervals) * 0.8:
            print("\n✓ Featured content is being scheduled approximately every 1.5 hours!")
            return True
        else:
            print("\n✗ Featured content intervals are not consistent with 1.5 hour target")
            return False
    else:
        print("Not enough featured items to verify intervals")
        return False

if __name__ == "__main__":
    # Make sure the Flask server is running
    print("Note: Make sure the Flask server is running on port 5000")
    print("=" * 50)
    
    success = test_featured_intervals()
    sys.exit(0 if success else 1)