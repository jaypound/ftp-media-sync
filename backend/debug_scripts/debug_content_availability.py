#!/usr/bin/env python3
"""
Debug why content stops being scheduled at Thursday 1:15 AM
"""

from datetime import datetime
from scheduler_postgres import PostgreSQLScheduler

# Create scheduler instance
scheduler = PostgreSQLScheduler()

print("=== CONTENT AVAILABILITY DEBUG ===")
print(f"Current time: {datetime.now()}")
print()

# Test getting content for each category
categories = ['id', 'spots', 'short_form', 'long_form']

for category in categories:
    print(f"\n--- Testing {category.upper()} ---")
    
    # Try with no delays
    content = scheduler.get_available_content(
        category,
        exclude_ids=[],
        ignore_delays=True,
        schedule_date=datetime.now().strftime('%Y-%m-%d')
    )
    print(f"Content available with NO delays: {len(content)} items")
    
    # Try with progressive delays
    content_progressive = scheduler._get_content_with_progressive_delays(
        category,
        exclude_ids=[],
        schedule_date=datetime.now().strftime('%Y-%m-%d')
    )
    print(f"Content with progressive delays: {len(content_progressive)} items")
    
    if content and len(content) > 0:
        print(f"Sample item: {content[0].get('content_title', 'Unknown')[:50]}...")

# Check the specific time when content runs out (Thursday 1:15 AM)
print("\n\n=== SIMULATING THURSDAY 1:15 AM ===")

# Thursday 1:15 AM is approximately 97.25 hours into the week
hours_into_week = 4 * 24 + 1.25  # 4 days + 1.25 hours

# Simulate what categories would be requested around that time
test_categories = ['id', 'spots', 'id', 'spots', 'short_form']  # typical rotation

for i, category in enumerate(test_categories):
    print(f"\nAttempt {i+1}: Requesting {category}")
    content = scheduler._get_content_with_progressive_delays(
        category,
        exclude_ids=[],  # In real scenario this would have many IDs
        schedule_date=datetime.now().strftime('%Y-%m-%d')
    )
    print(f"Found {len(content)} items")