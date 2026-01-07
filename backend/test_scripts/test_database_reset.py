#!/usr/bin/env python3
"""Test the database reset mechanism for content delays"""

from database import db_manager
from scheduler_postgres import PostgreSQLScheduler
from datetime import datetime, timedelta
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("=== TESTING DATABASE RESET MECHANISM ===\n")

# Initialize database connection
print("Initializing database connection...")
db_manager.connect()

# Create scheduler
scheduler = PostgreSQLScheduler()

# First, let's check what content is available for each category
conn = db_manager._get_connection()
cursor = conn.cursor()

print("\n1. Current Content Availability:")
print("-" * 70)

for category in ['id', 'spots', 'short_form', 'long_form']:
    # Check total content
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM assets a
        WHERE a.duration_category = %s
          AND a.analysis_completed = TRUE
    """, (category,))
    total = cursor.fetchone()['total']
    
    # Check content with last_scheduled_date set
    cursor.execute("""
        SELECT COUNT(*) as scheduled
        FROM assets a
        JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.duration_category = %s
          AND a.analysis_completed = TRUE
          AND sm.last_scheduled_date IS NOT NULL
    """, (category,))
    scheduled = cursor.fetchone()['scheduled']
    
    print(f"{category:15} Total: {total:3}  Scheduled: {scheduled:3}  Available: {total - scheduled:3}")

# Test the progressive delay system
print("\n2. Testing Progressive Delay System:")
print("-" * 70)

test_date = '2025-01-20'  # Future date to avoid conflicts

for category in ['id', 'spots', 'short_form', 'long_form']:
    print(f"\n{category.upper()}:")
    
    # Test regular get_available_content
    content = scheduler.get_available_content(
        category,
        exclude_ids=[],
        schedule_date=test_date
    )
    print(f"  With full delays: {len(content)} items")
    
    # Test with progressive delays
    content_progressive = scheduler._get_content_with_progressive_delays(
        category,
        exclude_ids=[],
        schedule_date=test_date
    )
    if content_progressive:
        delay_factor = content_progressive[0].get('_delay_factor_used', 1.0)
        was_reset = content_progressive[0].get('_was_reset', False)
        print(f"  Progressive delays: {len(content_progressive)} items (delay factor: {delay_factor*100:.0f}%, reset: {was_reset})")
    else:
        print(f"  Progressive delays: 0 items (no content available)")

# Test what happens when we exclude all content
print("\n3. Testing Reset When All Content Excluded:")
print("-" * 70)

for category in ['id', 'spots']:  # Test with smaller categories
    # Get all asset IDs for this category
    cursor.execute("""
        SELECT a.id
        FROM assets a
        WHERE a.duration_category = %s
          AND a.analysis_completed = TRUE
    """, (category,))
    all_ids = [row['id'] for row in cursor]
    
    if all_ids:
        print(f"\n{category.upper()} - Excluding all {len(all_ids)} assets:")
        
        # Try to get content while excluding all assets
        content = scheduler._get_content_with_progressive_delays(
            category,
            exclude_ids=all_ids,  # Exclude everything!
            schedule_date=test_date
        )
        
        if content:
            print(f"  ✅ Reset worked! Got {len(content)} items after reset")
            was_reset = content[0].get('_was_reset', False)
            print(f"  First item marked as reset: {was_reset}")
        else:
            print(f"  ❌ Reset failed - still no content available")

# Test the _reset_category_delays method directly
print("\n4. Testing Direct Database Reset:")
print("-" * 70)

# Get some asset IDs to reset
cursor.execute("""
    SELECT a.id
    FROM assets a
    JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE a.duration_category = 'spots'
      AND sm.last_scheduled_date IS NOT NULL
    LIMIT 5
""")
reset_ids = [row['id'] for row in cursor]

if reset_ids:
    print(f"Resetting {len(reset_ids)} 'spots' assets...")
    success = scheduler._reset_category_delays('spots', reset_ids)
    print(f"Reset result: {'✅ Success' if success else '❌ Failed'}")
    
    # Verify the reset
    cursor.execute("""
        SELECT COUNT(*) as reset_count
        FROM scheduling_metadata
        WHERE asset_id = ANY(%s)
          AND last_scheduled_date IS NULL
    """, (reset_ids,))
    reset_count = cursor.fetchone()['reset_count']
    print(f"Verified: {reset_count} assets have NULL last_scheduled_date")
else:
    print("No spots content with last_scheduled_date to test reset")

cursor.close()
db_manager._put_connection(conn)

print("\n" + "="*70)
print("SUMMARY:")
print("="*70)
print("The reset mechanism should:")
print("1. Try progressively reduced delays (100% → 75% → 50% → 25% → 0%)")
print("2. If still no content, reset database delays (set last_scheduled_date to NULL)")
print("3. Allow immediate reuse of content when necessary")
print("\nThis prevents infinite loops while maximizing content variety!")