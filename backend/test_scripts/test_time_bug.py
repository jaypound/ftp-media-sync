#!/usr/bin/env python3
"""Test the bug with time object vs string"""

from datetime import time, datetime, timedelta

# Simulate what happens in the code
meeting = {
    'start_time': '06:00 PM',  # This comes as string from DB formatting
    'end_time': '09:05 PM',    # This also comes as string
}

print("Testing the template generation bug:")
print("="*60)

# The bug is that the code expects strings but might get time objects
# Let's test both scenarios

print("\nScenario 1: Times as strings (expected)")
start_time = meeting['start_time']
end_time = meeting['end_time']

print(f"start_time: {start_time} (type: {type(start_time)})")
print(f"end_time: {end_time} (type: {type(end_time)})")

# Check if this is what the code expects
if end_time.count(':') == 1:  # Only HH:MM format
    print("  end_time needs seconds added")
    dt = datetime.strptime(end_time, '%I:%M %p')
    end_time = dt.strftime('%I:%M:%S %p')
    print(f"  New end_time: {end_time}")
else:
    print("  end_time already has seconds")

print("\nScenario 2: What if end_time is a time object?")
# This is what might be happening
end_time_obj = time(21, 5, 0)  # 9:05 PM as time object
print(f"end_time_obj: {end_time_obj} (type: {type(end_time_obj)})")

try:
    if end_time_obj.count(':') == 1:
        print("  This will work")
except AttributeError as e:
    print(f"  ERROR: {e}")
    print("  This is the bug! time objects don't have .count() method")

print("\nThe fix would be to check the type first or format it properly")

# Show how the data comes from database
print("\n" + "="*60)
print("How meetings come from database:")
print("The database returns time objects, but then formats them with TO_CHAR")
print("So 'start_time' and 'end_time' in the meeting dict should be strings")
print("But the code might be getting the raw time objects instead")