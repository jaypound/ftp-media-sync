#!/usr/bin/env python3
"""
Analyze featured content intervals in an existing schedule
"""

import requests
import sys
from datetime import datetime

def analyze_schedule(date):
    """Analyze featured content in a specific schedule"""
    
    base_url = "http://127.0.0.1:5000"
    
    print(f"Analyzing schedule for {date}...")
    
    # Get the schedule
    response = requests.post(f"{base_url}/api/get-schedule", json={"date": date})
    
    if response.status_code != 200:
        print(f"Failed to get schedule: {response.text}")
        return
    
    data = response.json()
    if not data.get('success'):
        print(f"Failed to get schedule: {data.get('message')}")
        return
    
    items = data.get('items', [])
    print(f"Total items in schedule: {len(items)}")
    
    # Find featured content
    featured_items = []
    for i, item in enumerate(items):
        if 'Hispanic Heritage Month' in item.get('title', ''):
            time_str = item.get('scheduled_start_time', '')
            if ':' in time_str:
                parts = time_str.split(':')
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2]) if len(parts) > 2 else 0
                time_hours = hours + minutes/60 + seconds/3600
                
                featured_items.append({
                    'index': i,
                    'title': item.get('title'),
                    'time': time_str,
                    'time_hours': time_hours
                })
    
    print(f"\nFound {len(featured_items)} featured items:")
    for item in featured_items[:20]:  # Show first 20
        print(f"  [{item['index']:3d}] {item['time']} ({item['time_hours']:6.2f}h) - {item['title']}")
    
    if len(featured_items) > 20:
        print(f"  ... and {len(featured_items) - 20} more")
    
    # Calculate intervals
    if len(featured_items) > 1:
        print("\nIntervals between featured content:")
        intervals = []
        large_intervals = []
        
        for i in range(1, min(len(featured_items), 20)):  # First 20 intervals
            interval = featured_items[i]['time_hours'] - featured_items[i-1]['time_hours']
            intervals.append(interval)
            print(f"  Interval {i}: {interval:.2f} hours")
            
            if interval > 3.0:  # Flag large gaps
                large_intervals.append((i, interval))
        
        # Calculate all intervals for statistics
        all_intervals = []
        for i in range(1, len(featured_items)):
            interval = featured_items[i]['time_hours'] - featured_items[i-1]['time_hours']
            all_intervals.append(interval)
        
        if all_intervals:
            avg_interval = sum(all_intervals) / len(all_intervals)
            min_interval = min(all_intervals)
            max_interval = max(all_intervals)
            
            print(f"\nInterval Statistics:")
            print(f"  Average: {avg_interval:.2f} hours")
            print(f"  Min: {min_interval:.2f} hours")
            print(f"  Max: {max_interval:.2f} hours")
            print(f"  Total intervals: {len(all_intervals)}")
            
            # Count intervals by range
            ranges = {
                "< 1h": 0,
                "1-2h": 0,
                "2-3h": 0,
                "3-5h": 0,
                "5-10h": 0,
                "> 10h": 0
            }
            
            for interval in all_intervals:
                if interval < 1:
                    ranges["< 1h"] += 1
                elif interval <= 2:
                    ranges["1-2h"] += 1
                elif interval <= 3:
                    ranges["2-3h"] += 1
                elif interval <= 5:
                    ranges["3-5h"] += 1
                elif interval <= 10:
                    ranges["5-10h"] += 1
                else:
                    ranges["> 10h"] += 1
            
            print("\nInterval Distribution:")
            for range_name, count in ranges.items():
                print(f"  {range_name}: {count} ({count/len(all_intervals)*100:.1f}%)")
            
            if large_intervals:
                print(f"\nLarge gaps (>3 hours) found at positions: {large_intervals}")
    
    # Check schedule info
    schedule_info = data.get('schedule_info', {})
    if schedule_info:
        total_duration = schedule_info.get('total_duration_seconds', 0)
        total_hours = total_duration / 3600
        print(f"\nSchedule duration: {total_hours:.1f} hours")
        print(f"Expected featured items (every 1.5h): ~{int(total_hours / 1.5)}")
        print(f"Actual featured items: {len(featured_items)}")

if __name__ == "__main__":
    # Default to Sept 14 or use command line argument
    date = sys.argv[1] if len(sys.argv) > 1 else "2025-09-14"
    
    print("Note: Make sure the Flask server is running on port 5000")
    print("=" * 60)
    
    analyze_schedule(date)