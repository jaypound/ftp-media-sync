#!/usr/bin/env python3
"""Test the fixed scheduler to see if it resolves the SQL parameter issue"""

from scheduler_postgres import PostgreSQLScheduler
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create scheduler instance
scheduler = PostgreSQLScheduler()

# Test get_available_content with different scenarios
print("Testing fixed get_available_content method...")

# Test 1: Basic query
print("\n1. Basic query for 'id' category:")
try:
    results = scheduler.get_available_content('id')
    print(f"   ✓ Success! Found {len(results)} items")
    if results:
        print(f"   First item: {results[0]['content_title'][:50]}...")
except Exception as e:
    print(f"   ✗ Failed: {e}")

# Test 2: With delays reduced
print("\n2. Query with reduced delays (50%):")
try:
    results = scheduler.get_available_content('spots', delay_reduction_factor=0.5)
    print(f"   ✓ Success! Found {len(results)} items")
except Exception as e:
    print(f"   ✗ Failed: {e}")

# Test 3: With no delays
print("\n3. Query with no delays:")
try:
    results = scheduler.get_available_content('long_form', ignore_delays=True)
    print(f"   ✓ Success! Found {len(results)} items")
except Exception as e:
    print(f"   ✗ Failed: {e}")

# Test 4: With exclude_ids
print("\n4. Query with exclude_ids:")
try:
    results = scheduler.get_available_content('short_form', exclude_ids=[1, 2, 3])
    print(f"   ✓ Success! Found {len(results)} items")
except Exception as e:
    print(f"   ✗ Failed: {e}")

# Test 5: Full progressive delay system
print("\n5. Testing progressive delay system:")
try:
    results = scheduler._get_content_with_progressive_delays(
        'id', 
        exclude_ids=[],
        schedule_date='2025-01-12'
    )
    print(f"   ✓ Success! Progressive delays working, found {len(results)} items")
except Exception as e:
    print(f"   ✗ Failed: {e}")

print("\n✅ All tests completed!")