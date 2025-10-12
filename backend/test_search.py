#!/usr/bin/env python3
"""Test the schedule search API directly"""

import requests
import json

# Search for AIM Podcast in schedule 452
url = "http://localhost:5000/api/generate-report"
data = {
    "report_type": "schedule-content-search",
    "schedule_id": 452,
    "search_term": "AIM Podcast"
}

response = requests.post(url, json=data)

if response.status_code == 200:
    result = response.json()
    if result.get('success'):
        data = result.get('data', {})
        matches = data.get('matches', [])
        print(f"Found {len(matches)} matches\n")
        
        # Group by day
        by_day = {}
        for match in matches:
            scheduled_start = match.get('scheduled_start')
            # Parse the ISO date
            if scheduled_start:
                from datetime import datetime
                dt = datetime.fromisoformat(scheduled_start.replace('Z', '+00:00'))
                day_name = dt.strftime('%A')
                if day_name not in by_day:
                    by_day[day_name] = []
                by_day[day_name].append(match)
        
        # Show summary
        print("Matches by day:")
        for day in ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']:
            if day in by_day:
                print(f"  {day}: {len(by_day[day])} items")
        
        print("\n" + "="*80 + "\n")
        
        # Show first few from each day
        for day in ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']:
            if day in by_day:
                print(f"{day}:")
                for i, match in enumerate(by_day[day][:2]):
                    print(f"  {match['file_name']}")
                    print(f"    Start: {match['scheduled_start']}")
                if len(by_day[day]) > 2:
                    print(f"  ... and {len(by_day[day]) - 2} more")
                print()
    else:
        print(f"Error: {result.get('message')}")
else:
    print(f"HTTP Error: {response.status_code}")
    print(response.text)