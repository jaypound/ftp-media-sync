#!/usr/bin/env python3
"""Test heatmap hour distribution for weekly schedule"""

import requests
import json
from collections import defaultdict

# Generate the heatmap report
response = requests.post(
    'http://127.0.0.1:5000/api/generate-report',
    json={
        'schedule_id': 459,
        'report_type': 'replay-heatmap'
    }
)

if response.status_code == 200:
    data = response.json()
    
    # Analyze hour distribution
    hour_counts = defaultdict(int)
    day_counts = defaultdict(int)
    
    for item in data['data']['heatmap_data']:
        hour = item['hour']
        hour_counts[hour] += 1
        day = hour // 24
        day_counts[day] += 1
    
    print("Hour distribution in heatmap:")
    print(f"Total data points: {len(data['data']['heatmap_data'])}")
    print(f"Unique hours with content: {len(hour_counts)}")
    print(f"Days with content: {sorted(day_counts.keys())}")
    
    # Show sample of hours
    print("\nSample hours with content:")
    for hour in sorted(hour_counts.keys())[:20]:
        day = hour // 24
        hour_in_day = hour % 24
        print(f"  Hour {hour} (Day {day}, {hour_in_day}:00) - {hour_counts[hour]} items")
        
    # Check if content is distributed throughout days
    print("\nContent by day:")
    days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    for day, count in sorted(day_counts.items()):
        if day < 7:
            print(f"  {days[day]}: {count} content items")
else:
    print(f"Error: {response.status_code}")
    print(response.text)