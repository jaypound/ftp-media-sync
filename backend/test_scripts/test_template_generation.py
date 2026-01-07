#!/usr/bin/env python3
"""Test template generation for the Inspector General meeting"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, time, timedelta

# Simulate the meeting data
meeting = {
    'id': 60,
    'meeting_name': 'Office of Inspector General',
    'meeting_date': '2025-09-18',
    'start_time': '06:00 PM',  # This is how it would come from the template generation
    'end_time': '09:05 PM',
    'duration_hours': 3.083,
    'room': 'Committee Room 1'
}

print("Original meeting data:")
print(f"  Start: {meeting['start_time']}")
print(f"  End: {meeting['end_time']}")
print(f"  Duration: {meeting['duration_hours']} hours")

# Simulate the template generation code from app.py
start_time = meeting['start_time']
end_time = meeting['end_time']

# Parse meeting date to get day of week
meeting_date = datetime.strptime(meeting['meeting_date'], '%Y-%m-%d')
day_name = meeting_date.strftime('%a').lower()  # thu

# Add seconds for precision (from app.py lines 7351-7354)
if end_time.count(':') == 1:  # Only HH:MM format
    dt = datetime.strptime(end_time, '%I:%M %p')
    end_time = dt.strftime('%I:%M:%S %p')
    print(f"\nConverted end_time to include seconds: {end_time}")

# Ensure start time also has seconds (from app.py lines 7362-7365)
if start_time.count(':') == 1:  # Only HH:MM format
    dt = datetime.strptime(start_time, '%I:%M %p')
    start_time = dt.strftime('%I:%M:%S %p')
    print(f"Converted start_time to include seconds: {start_time}")

start_time_lower = start_time.lower()
end_time_lower = end_time.lower()

# This is what would be written to the template
print(f"\nTemplate output:")
print(f"  start={day_name} {start_time_lower}")
print(f"  end={day_name} {end_time_lower}")

# Now simulate parsing this back (like when importing a template)
print("\n" + "="*60)
print("Simulating template import/parsing:")

# From parse_castus_schedule function
template_start = f"{day_name} {start_time_lower}"
template_end = f"{day_name} {end_time_lower}"

print(f"Template values:")
print(f"  start_time: '{template_start}'")
print(f"  end_time: '{template_end}'")

# Now test the duration calculation
from app import calculate_duration_from_times

try:
    duration_seconds = calculate_duration_from_times(template_start, template_end)
    duration_hours = duration_seconds / 3600
    duration_minutes = duration_seconds / 60
    
    print(f"\nCalculated duration:")
    print(f"  Seconds: {duration_seconds}")
    print(f"  Minutes: {duration_minutes:.2f}")
    print(f"  Hours: {duration_hours:.2f}")
    
    # Check if this matches the display
    hours = int(duration_hours)
    minutes = int((duration_seconds % 3600) / 60)
    seconds = int(duration_seconds % 60)
    duration_display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    print(f"  Display format: {duration_display}")
    
except Exception as e:
    print(f"Error calculating duration: {e}")
    import traceback
    traceback.print_exc()

# Test with exact values from screenshot
print("\n" + "="*60)
print("Testing with exact values that would produce 4:58 duration:")
test_start = "thu 06:00:00 pm"
test_end = "thu 10:58:00 pm"  # This would give 4:58

try:
    test_duration = calculate_duration_from_times(test_start, test_end)
    test_hours = test_duration / 3600
    print(f"If end time was 10:58 PM instead of 9:05 PM:")
    print(f"  Duration would be: {test_hours:.2f} hours ({test_duration/60:.0f} minutes)")
except Exception as e:
    print(f"Error: {e}")