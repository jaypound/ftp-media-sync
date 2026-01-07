#!/usr/bin/env python3
"""Test the category-specific reset mechanism"""

from scheduler_postgres import PostgreSQLScheduler
from database import db_manager
from datetime import datetime, timedelta
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("=== TESTING CATEGORY RESET MECHANISM ===\n")

# Initialize database connection
print("Initializing database connection...")
db_manager.connect()

# Create scheduler
scheduler = PostgreSQLScheduler()

# Get a future date to avoid conflicts
test_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

print(f"Creating test schedule for {test_date}...")
print("With limited content, we expect to see category resets...\n")

# Delete any existing schedule for this date
existing = scheduler.get_schedule_by_date(test_date)
if existing:
    print(f"Deleting existing schedule for {test_date}")
    scheduler.delete_schedule(existing['id'])

# Create new schedule - this should trigger resets due to limited content
result = scheduler.create_daily_schedule(
    schedule_date=test_date,
    schedule_name=f"Reset Test Schedule - {test_date}",
    max_errors=200  # Allow more errors to see resets in action
)

print("\n" + "="*60)
print("RESULTS:")
print("="*60)

if result['success']:
    print(f"✅ Schedule created successfully!")
    print(f"   Schedule ID: {result['schedule_id']}")
    print(f"   Total duration: {result['total_duration_hours']:.2f} hours")
    print(f"   Total items: {result['total_items']}")
    
    # Show delay statistics
    if 'delay_reduction_stats' in result:
        stats = result['delay_reduction_stats']
        print(f"\nDelay Statistics:")
        print(f"   Full delays (100%): {stats.get('full_delays', 0)}")
        print(f"   Reduced to 75%: {stats.get('reduced_75', 0)}")
        print(f"   Reduced to 50%: {stats.get('reduced_50', 0)}")
        print(f"   Reduced to 25%: {stats.get('reduced_25', 0)}")
        print(f"   No delays (0%): {stats.get('no_delays', 0)}")
        print(f"   🔄 RESETS: {stats.get('resets', 0)}")
    
    # Show category reset counts
    if 'category_reset_counts' in result:
        resets = result['category_reset_counts']
        print(f"\nCategory Reset Counts:")
        for cat in ['id', 'spots', 'short_form', 'long_form']:
            count = resets.get(cat, 0)
            if count > 0:
                print(f"   🔄 {cat}: {count} resets")
            else:
                print(f"   ✅ {cat}: No resets needed")
        
        total_resets = sum(resets.values())
        if total_resets > 0:
            print(f"\n💡 The reset mechanism prevented infinite loops!")
            print(f"   Without resets, the schedule would have failed.")
            print(f"   Categories were reset {total_resets} times total.")
        else:
            print(f"\n✅ No resets were needed - sufficient content variety!")
    
else:
    print(f"❌ FAILED: {result['message']}")
    if 'error' in result:
        print(f"   Error type: {result['error']}")

print("\n" + "="*60)
print("EXPLANATION:")
print("="*60)
print("The reset mechanism works as follows:")
print("1. When a category has no available content (even with 0% delays)")
print("2. The system checks if all content in that category is excluded")
print("3. If so, it removes that category's items from the exclusion list")
print("4. This allows the content to be reused immediately")
print("5. Each category tracks its own resets independently")
print("\nThis prevents infinite loops while maximizing content variety!")