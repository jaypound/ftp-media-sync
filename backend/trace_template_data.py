#!/usr/bin/env python3
"""Trace where the template data comes from and how it gets the wrong time"""

# The key facts:
# 1. Database has correct time: 18:00 to 21:05 (6 PM to 9:05 PM)
# 2. Template generation code produces correct time when simulated
# 3. Actual .sch file has wrong time: 18:00 to 22:58 (6 PM to 10:58 PM)
# 4. The offset is exactly 1:53 (113 minutes)

print("Analyzing the template data flow:")
print("="*60)

print("\n1. Meeting in database:")
print("   Start: 18:00:00 (6:00 PM)")
print("   End: 21:05:00 (9:05 PM)")
print("   Duration: 3.083 hours (185 minutes)")

print("\n2. Expected template output:")
print("   start=thu 06:00:00 pm")
print("   end=thu 09:05:00 pm")

print("\n3. Actual .sch file content:")
print("   start=thu 6:00:00.000 pm")
print("   end=thu 10:58:00.000 pm")

print("\n4. Key differences:")
print("   - End time: 09:05 -> 10:58 (offset of 1:53)")
print("   - Time format: added milliseconds (.000)")
print("   - Start time: removed leading zero (06:00 -> 6:00)")

print("\n" + "="*60)
print("Possible transformation points:")
print("1. During template generation (ruled out - code works correctly)")
print("2. During template storage/serialization") 
print("3. During template loading/parsing")
print("4. During conversion from meeting to Live Input")
print("5. During schedule export")

print("\n" + "="*60)
print("The milliseconds (.000) suggest this went through additional processing")
print("The 'Live Input' title suggests this was converted from a meeting")

# Check if there's a pattern with the time format
print("\n" + "="*60)
print("Checking time format differences:")
print("  Database format: HH:MM:SS (24-hour)")
print("  Template expected: HH:MM:SS AM/PM")
print("  Actual output: H:MM:SS.mmm AM/PM")
print("  Note: Leading zero dropped and milliseconds added")

# Could this be related to how times are stored in templates?
print("\n" + "="*60)
print("Hypothesis: The template might be storing duration instead of end time")
print("and calculating end time incorrectly when exporting")

# Check what 4:58 duration would be from 6 PM
from datetime import datetime, timedelta
start = datetime.strptime("6:00 PM", "%I:%M %p")
duration = timedelta(hours=4, minutes=58)
calculated_end = start + duration
print(f"\n6:00 PM + 4:58 duration = {calculated_end.strftime('%I:%M %p')}")
print("This matches the output: 10:58 PM")

print("\n" + "="*60)
print("CONCLUSION: The template is likely storing the wrong duration (4:58)")
print("instead of the correct duration (3:05), which causes the wrong end time")
print("when the schedule is exported.")

print("\nNext steps:")
print("1. Find where duration is calculated during template creation")
print("2. Check if duration is being modified somewhere")
print("3. Look for any code that adds 113 minutes to durations")