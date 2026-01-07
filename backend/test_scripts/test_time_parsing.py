#!/usr/bin/env python3
"""Test time parsing issue where 6PM-9:05PM meeting shows as 4:58 duration"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import re

def parse_time(time_str):
    """Parse time string - from app.py calculate_duration_from_times"""
    # Handle weekly format by removing day prefix
    if ' ' in time_str:
        parts = time_str.split(' ', 1)
        # Check if first part is a day abbreviation
        if len(parts[0]) <= 3 and parts[0].lower() in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']:
            time_str = parts[1]
    
    # Extract milliseconds if present
    milliseconds_match = re.search(r'\.(\d+)', time_str)
    milliseconds = float(f"0.{milliseconds_match.group(1)}") if milliseconds_match else 0.0
    
    # Remove milliseconds for parsing
    time_clean = re.sub(r'\.\d+', '', time_str).strip()
    
    # Try different time formats
    for fmt in ["%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"]:
        try:
            dt = datetime.strptime(time_clean, fmt)
            # Return datetime and milliseconds separately for precision
            return dt, milliseconds
        except ValueError:
            continue
    
    raise ValueError(f"Unable to parse time: {time_str}")

def calculate_duration_from_times(start_time, end_time):
    """Calculate duration in seconds from start/end time strings"""
    try:
        start_dt, start_ms = parse_time(start_time)
        end_dt, end_ms = parse_time(end_time)
        
        # Handle day boundary
        if end_dt < start_dt:
            end_dt = end_dt.replace(day=end_dt.day + 1)
        
        # Calculate duration with full precision
        duration_seconds = (end_dt - start_dt).total_seconds()
        millisecond_diff = end_ms - start_ms
        total_duration = duration_seconds + millisecond_diff
        
        print(f"Duration calculation detail:")
        print(f"  Start: {start_dt} + {start_ms}s")
        print(f"  End: {end_dt} + {end_ms}s")
        print(f"  Duration: {total_duration}s ({total_duration/60:.2f} minutes, {total_duration/3600:.2f} hours)")
        
        return total_duration
        
    except Exception as e:
        print(f"Error calculating duration: {e}")
        return 0

# Test cases
print("Test 1: 6:00 PM to 9:05 PM (expected: 3h 5m = 185 minutes)")
duration1 = calculate_duration_from_times("6:00 PM", "9:05 PM")
print(f"Result: {duration1/60:.2f} minutes, {duration1/3600:.2f} hours\n")

print("Test 2: 06:00 PM to 09:05 PM (with leading zeros)")
duration2 = calculate_duration_from_times("06:00 PM", "09:05 PM")
print(f"Result: {duration2/60:.2f} minutes, {duration2/3600:.2f} hours\n")

print("Test 3: 18:00:00 to 21:05:00 (24-hour format)")
duration3 = calculate_duration_from_times("18:00:00", "21:05:00")
print(f"Result: {duration3/60:.2f} minutes, {duration3/3600:.2f} hours\n")

print("Test 4: Weekly format - thu 06:00:00 pm to thu 09:05:00 pm")
duration4 = calculate_duration_from_times("thu 06:00:00 pm", "thu 09:05:00 pm")
print(f"Result: {duration4/60:.2f} minutes, {duration4/3600:.2f} hours\n")

# Test what might cause 4:58 duration (298 minutes)
print("Test 5: What end time would give 4:58 duration from 6:00 PM?")
# 6:00 PM + 4:58 = 10:58 PM
duration5 = calculate_duration_from_times("6:00 PM", "10:58 PM")
print(f"Result: {duration5/60:.2f} minutes, {duration5/3600:.2f} hours\n")

print("Test 6: Checking if 9:05 PM might be misread as 10:58 PM")
print("  9:05 PM parsed:", parse_time("9:05 PM"))
print("  10:58 PM parsed:", parse_time("10:58 PM"))