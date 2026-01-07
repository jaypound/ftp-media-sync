#!/usr/bin/env python3
"""
Test if holiday integration is properly initialized and working
"""

import sys
sys.path.append('.')

from scheduler_postgres import scheduler_postgres
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

print("=== Testing Holiday Integration Fix ===")

# Check if holiday integration exists
print(f"1. Has holiday_integration attribute: {hasattr(scheduler_postgres, 'holiday_integration')}")
print(f"2. Holiday integration object: {scheduler_postgres.holiday_integration}")

# Try to ensure it's initialized
print("\n3. Calling _ensure_holiday_integration()...")
scheduler_postgres._ensure_holiday_integration()

print(f"4. After ensure - holiday integration object: {scheduler_postgres.holiday_integration}")
if scheduler_postgres.holiday_integration:
    print(f"5. Holiday integration enabled: {scheduler_postgres.holiday_integration.enabled}")
else:
    print("5. Holiday integration is still None!")

# Try to test the filter
if scheduler_postgres.holiday_integration and scheduler_postgres.holiday_integration.enabled:
    print("\n6. Testing filter_available_content...")
    test_content = [
        {'id': 1, 'file_name': 'test.mp4', 'content_title': 'Test Content', 'duration_category': 'spots'},
        {'id': 2, 'file_name': '251210_SSP_AFRD Holiday Greetings.mp4', 'content_title': 'AFRD Holiday Greetings', 'duration_category': 'spots'},
    ]
    
    filtered = scheduler_postgres.holiday_integration.filter_available_content(
        test_content, 'spots', [], '2025-12-21'
    )
    
    print(f"   Original content count: {len(test_content)}")
    print(f"   Filtered content count: {len(filtered)}")
    for item in filtered:
        print(f"   - {item['content_title']}")

print("\nDone!")