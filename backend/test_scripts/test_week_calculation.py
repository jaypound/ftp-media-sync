#!/usr/bin/env python3
"""Test week calculation to ensure it matches frontend"""

from datetime import datetime, timedelta

def calculate_week_range(year, week):
    """Calculate week range matching the frontend logic"""
    # Find the first Sunday of the year
    jan1 = datetime(year, 1, 1)
    # In Python weekday(): 0=Monday, 6=Sunday
    # In JS getDay(): 0=Sunday, 6=Saturday
    # So we need to convert: Python Sunday (6) = JS Sunday (0)
    jan1_day_of_week = (jan1.weekday() + 1) % 7  # Convert to JS style where 0=Sunday
    
    # Calculate days to first Sunday (matching JS: dayOfWeek === 0 ? 0 : 7 - dayOfWeek)
    days_to_first_sunday = 0 if jan1_day_of_week == 0 else 7 - jan1_day_of_week
    first_sunday = jan1 + timedelta(days=days_to_first_sunday)
    
    # Calculate the start of the requested week (Sunday)
    week_start = first_sunday + timedelta(days=(week - 1) * 7)
    # End of week is Saturday (6 days later)
    week_end = week_start + timedelta(days=6)
    
    return week_start, week_end

def get_week_number(date):
    """Get week number for a date matching frontend logic"""
    d = datetime(date.year, date.month, date.day)
    jan1 = datetime(d.year, 1, 1)
    
    # Convert Python weekday to JS getDay style
    jan1_day_of_week = (jan1.weekday() + 1) % 7  # 0 = Sunday
    days_to_first_sunday = 0 if jan1_day_of_week == 0 else 7 - jan1_day_of_week
    first_sunday = jan1 + timedelta(days=days_to_first_sunday)
    
    # Calculate days since first Sunday
    days_since_first_sunday = (d - first_sunday).days
    
    # If the date is before the first Sunday, it's week 1
    if days_since_first_sunday < 0:
        return 1
    
    # Calculate week number (add 1 because weeks are 1-indexed)
    return days_since_first_sunday // 7 + 1

# Test cases
print("Testing week calculations for 2025:")
print()

# Test the specific case mentioned: Oct 12, 2025 (Sunday)
test_date = datetime(2025, 10, 12)
week_num = get_week_number(test_date)
print(f"Oct 12, 2025 ({test_date.strftime('%A')}): Week {week_num}")

# Show Week 40 and Week 41
for week in [40, 41]:
    start, end = calculate_week_range(2025, week)
    print(f"Week {week}: {start.strftime('%b %d, %Y')} ({start.strftime('%A')}) - {end.strftime('%b %d, %Y')} ({end.strftime('%A')})")

print()
print("Testing some key dates in 2025:")

# Test first week of year
jan1 = datetime(2025, 1, 1)
print(f"Jan 1, 2025 ({jan1.strftime('%A')}): Week {get_week_number(jan1)}")

# Test first Sunday
first_sunday_2025 = datetime(2025, 1, 5)
print(f"Jan 5, 2025 ({first_sunday_2025.strftime('%A')}): Week {get_week_number(first_sunday_2025)}")

# Test dates around week boundaries
for day in range(11, 14):
    date = datetime(2025, 10, day)
    print(f"Oct {day}, 2025 ({date.strftime('%A')}): Week {get_week_number(date)}")