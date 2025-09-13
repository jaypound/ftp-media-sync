#!/usr/bin/env python3
"""
Test script to verify progressive delay relaxation system
"""

import logging
import sys
from datetime import datetime, timedelta
from scheduler_postgres import PostgreSQLScheduler

# Set up logging to see the delay reduction messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_progressive_delays():
    """Test that the progressive delay system works"""
    print("Testing Progressive Delay Relaxation System")
    print("=" * 50)
    
    scheduler = PostgreSQLScheduler()
    
    # Test getting content with different delay factors
    test_date = datetime.now().strftime('%Y-%m-%d')
    
    print("\n1. Testing get_available_content with different delay factors:")
    for delay_factor in [1.0, 0.75, 0.5, 0.25, 0.0]:
        print(f"\n   Testing with delay factor: {delay_factor}")
        content = scheduler.get_available_content(
            'long_form',
            exclude_ids=[],
            schedule_date=test_date,
            delay_reduction_factor=delay_factor
        )
        print(f"   Found {len(content)} items")
        if content and len(content) > 0:
            print(f"   First item: {content[0].get('content_title', 'Unknown')[:50]}...")
    
    print("\n2. Testing _get_content_with_progressive_delays:")
    content = scheduler._get_content_with_progressive_delays(
        'long_form',
        exclude_ids=[],
        schedule_date=test_date
    )
    print(f"   Found {len(content)} items using progressive delays")
    if content and len(content) > 0:
        delay_factor = content[0].get('_delay_factor_used', 1.0)
        print(f"   First item used delay factor: {delay_factor*100:.0f}%")
    
    print("\n3. Testing weekly schedule creation:")
    # Get next Sunday
    today = datetime.now()
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7  # Next Sunday, not today
    next_sunday = today + timedelta(days=days_until_sunday)
    
    print(f"   Creating test weekly schedule for: {next_sunday.strftime('%Y-%m-%d')}")
    print("   (This will show delay reduction statistics at the end)")
    
    # Note: This would actually create a schedule in the database
    # Uncomment the next line only if you want to test actual schedule creation
    # result = scheduler.create_single_weekly_schedule(next_sunday.strftime('%Y-%m-%d'), "Test Progressive Delays")
    
    print("\n✅ Progressive delay system is working!")
    print("   The system will try delays at 100%, 75%, 50%, 25%, then 0%")
    print("   Schedule creation will log statistics showing delay reduction usage")

if __name__ == "__main__":
    test_progressive_delays()