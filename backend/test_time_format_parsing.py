#!/usr/bin/env python3
"""Test parsing of 09:05 PM to see if it could be misread as 10:58 PM"""

from datetime import datetime

# Test various ways "09:05 PM" might be parsed
test_times = [
    "09:05 PM",
    "9:05 PM",
    " 09:05 PM",
    "09:05 PM ",
    "09:05PM",
    "9:05PM",
    "09:05:00 PM",
    "21:05:00",  # 24-hour format from DB
]

print("Testing time parsing for various formats:")
print("="*60)

for time_str in test_times:
    print(f"\nInput: '{time_str}'")
    
    # Try different parsing formats
    formats = [
        '%I:%M %p',
        '%I:%M%p',
        '%I:%M:%S %p',
        '%H:%M:%S',
        '%H:%M'
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            print(f"  Format '{fmt}' -> {dt.strftime('%H:%M:%S')} (24h) / {dt.strftime('%I:%M %p')} (12h)")
            
            # Check if this could somehow become 22:58 (10:58 PM)
            if dt.hour == 22 and dt.minute == 58:
                print(f"  *** WARNING: This parsed as 10:58 PM! ***")
        except ValueError:
            pass  # Expected for non-matching formats

# Now let's check character-by-character comparison
print("\n" + "="*60)
print("Character comparison between '09:05' and '10:58':")
s1 = "09:05"
s2 = "10:58"
print(f"  Position: 0 1 2 3 4")
print(f"  Original: {' '.join(s1)}")
print(f"  Wrong:    {' '.join(s2)}")
print("  Changes:  ", end="")
for i in range(5):
    if s1[i] == s2[i]:
        print("  ", end="")
    else:
        print("X ", end="")
print("\n")
print("  0→1, 9→0, 0→5, 5→8 : All 4 digits would need to change!")

# Check if there's a pattern
print("\n" + "="*60)
print("Looking for patterns in the transformation:")
print("  09:05 -> 10:58")
print("  Observations:")
print("  - First digit: 0 -> 1 (increment by 1)")
print("  - Second digit: 9 -> 0 (wrap around)")
print("  - Third digit: 0 -> 5 (increment by 5)")
print("  - Fourth digit: 5 -> 8 (increment by 3)")
print("  - This looks like it could be adding 1:53 to the time!")

# Verify this theory
from datetime import timedelta
original = datetime.strptime("09:05 PM", "%I:%M %p")
offset = timedelta(hours=1, minutes=53)
result = original + offset
print(f"\n  Theory: 09:05 PM + 1:53 = {result.strftime('%I:%M %p')}")
print(f"  Expected: 10:58 PM")
print(f"  Match: {result.strftime('%I:%M %p') == '10:58 PM'}")

print("\n" + "="*60)
print("CONCLUSION: There's exactly a 1:53 (113 minute) offset being added somewhere!")