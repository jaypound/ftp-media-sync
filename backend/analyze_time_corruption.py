#!/usr/bin/env python3
"""Analyze the pattern of time corruption in the test meetings"""

test_meetings = [
    {
        'name': 'TEST1',
        'expected_start': '11:00 AM',
        'expected_end': '01:00 PM',
        'actual_start': 'tue 11:00:00.000 am',
        'actual_end': 'tue 12:00:00.000 pm',
        'shown_duration': '00:00:00.000'
    },
    {
        'name': 'TEST2',
        'expected_start': '01:00 PM',
        'expected_end': '03:30 PM',
        'actual_start': 'tue 1:00:00.000 pm',
        'actual_end': 'wed 7:00:00.000 pm',
        'shown_duration': '30:00:00.000'
    },
    {
        'name': 'TEST3',
        'expected_start': '04:00 PM',
        'expected_end': '05:15 PM',
        'actual_start': 'tue 4:00:00.000 pm',
        'actual_end': 'wed 7:00:00.000 am',
        'shown_duration': '15:00:00.000'
    },
    {
        'name': 'Office of Inspector General',
        'expected_start': '06:00 PM',
        'expected_end': '09:05 PM',
        'actual_start': 'thu 6:00:00.000 pm',
        'actual_end': 'thu 10:58:00.000 pm',
        'shown_duration': '04:58:00.000'
    }
]

print("Analysis of time corruption:")
print("="*80)

for meeting in test_meetings:
    print(f"\n{meeting['name']}:")
    print(f"  Expected: {meeting['expected_start']} - {meeting['expected_end']}")
    print(f"  Actual in .sch: {meeting['actual_start']} to {meeting['actual_end']}")
    print(f"  Shown duration: {meeting['shown_duration']}")
    
    # Parse expected end time
    from datetime import datetime
    try:
        expected_end_dt = datetime.strptime(meeting['expected_end'], '%I:%M %p')
        expected_end_24h = expected_end_dt.strftime('%H:%M')
        
        # Extract actual end time (remove day and milliseconds)
        actual_end_parts = meeting['actual_end'].split()
        if len(actual_end_parts) >= 3:
            actual_time = actual_end_parts[1].split('.')[0]  # Remove milliseconds
            actual_ampm = actual_end_parts[2]
            actual_end_dt = datetime.strptime(f"{actual_time} {actual_ampm}", '%I:%M:%S %p')
            actual_end_24h = actual_end_dt.strftime('%H:%M')
            
            print(f"  Expected end (24h): {expected_end_24h}")
            print(f"  Actual end (24h): {actual_end_24h}")
            
            # Check for pattern
            expected_minutes = expected_end_dt.hour * 60 + expected_end_dt.minute
            actual_minutes = actual_end_dt.hour * 60 + actual_end_dt.minute
            
            print(f"  Expected total minutes: {expected_minutes}")
            print(f"  Actual total minutes: {actual_minutes}")
            
    except Exception as e:
        print(f"  Error parsing: {e}")

print("\n" + "="*80)
print("PATTERN ANALYSIS:")
print("\nLooking at the actual end times:")
print("  TEST1: 12:00 PM (expected 1:00 PM) - 1 hour early")
print("  TEST2: 7:00 PM next day (expected 3:30 PM) - way off")
print("  TEST3: 7:00 AM next day (expected 5:15 PM) - way off")
print("  Inspector: 10:58 PM (expected 9:05 PM) - 1:53 late")

print("\nThe pattern suggests the end times are being corrupted in different ways.")
print("This might be a data type issue or format parsing problem.")