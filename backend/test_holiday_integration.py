#!/usr/bin/env python3
"""
Test the holiday greeting integration without enabling it in production
"""

import sys
import json
from holiday_greeting_integration import HolidayGreetingIntegration
from database import db_manager

def test_filter_behavior():
    """Test how the filter behaves with sample data"""
    
    # Create integration instance
    integration = HolidayGreetingIntegration(db_manager)
    
    print("=== Holiday Greeting Integration Test ===")
    print(f"Current Status: {'ENABLED' if integration.enabled else 'DISABLED'}")
    print()
    
    # Sample content list (simulating what scheduler returns)
    sample_content = [
        {
            'id': 1,
            'asset_id': 1,
            'file_name': '251210_SSP_Strategy Office Holiday Greeting.mp4',
            'duration_category': 'spots',
            'duration_seconds': 22.256
        },
        {
            'id': 2,
            'asset_id': 2,
            'file_name': '251210_SSP_Watershed Holiday Greeting.mp4',
            'duration_category': 'spots',
            'duration_seconds': 30.564
        },
        {
            'id': 3,
            'asset_id': 3,
            'file_name': 'Some_Other_Content.mp4',
            'duration_category': 'spots',
            'duration_seconds': 60.0
        },
        {
            'id': 4,
            'asset_id': 4,
            'file_name': 'Another_Regular_Content.mp4',
            'duration_category': 'spots',
            'duration_seconds': 45.0
        }
    ]
    
    print("Original content list:")
    for i, content in enumerate(sample_content):
        print(f"  {i+1}. {content['file_name']}")
    print()
    
    # Test filter when DISABLED
    print("Testing filter when DISABLED:")
    filtered = integration.filter_available_content(sample_content, 'spots', [])
    print(f"  Returned {len(filtered)} items (should be same as input: {len(sample_content)})")
    print(f"  Same object? {filtered is sample_content}")
    print()
    
    # Temporarily enable to test behavior
    print("Testing filter when ENABLED (temporary):")
    integration.enabled = True
    integration.scheduler = integration.scheduler or type('obj', (object,), {
        'is_holiday_greeting': lambda self, f, t=None: 'holiday' in f.lower() and 'greeting' in f.lower()
    })()
    
    filtered = integration.filter_available_content(sample_content, 'spots', [])
    print(f"  Returned {len(filtered)} items")
    print("  Filtered content list:")
    for i, content in enumerate(filtered):
        print(f"    {i+1}. {content['file_name']}")
    
    # Count holiday greetings
    greeting_count = sum(1 for c in filtered if 'holiday' in c['file_name'].lower() and 'greeting' in c['file_name'].lower())
    print(f"\n  Holiday greetings in result: {greeting_count} (should be max 1)")
    
    # Reset
    integration.enabled = False


def test_database_query():
    """Test the database query for getting best greeting"""
    integration = HolidayGreetingIntegration(db_manager)
    
    print("\n=== Testing Database Query ===")
    
    try:
        # Get current distribution
        dist = integration.get_current_distribution()
        print(f"Total holiday greetings in DB: {dist.get('unique_greetings', 0)}")
        print(f"Total plays so far: {dist.get('total_plays', 0)}")
        print(f"Average plays: {dist.get('average_plays', 0):.1f}")
        
        if dist.get('distribution'):
            print("\nTop 5 most scheduled:")
            items = sorted(dist['distribution'].items(), key=lambda x: x[1]['count'], reverse=True)[:5]
            for name, info in items:
                print(f"  {name}: {info['count']} plays")
            
            print("\nBottom 5 least scheduled:")
            items = sorted(dist['distribution'].items(), key=lambda x: x[1]['count'])[:5]
            for name, info in items:
                print(f"  {name}: {info['count']} plays")
    
    except Exception as e:
        print(f"Error testing database: {e}")


def main():
    print("Holiday Greeting Integration Test Suite")
    print("=" * 50)
    
    # Check config file
    try:
        with open('holiday_greeting_config.json', 'r') as f:
            config = json.load(f)
            print(f"Config file exists: enabled = {config.get('enabled')}")
    except:
        print("Config file not found")
    
    print()
    
    # Run tests
    test_filter_behavior()
    test_database_query()
    
    print("\n" + "=" * 50)
    print("Test complete. System is still DISABLED in production.")


if __name__ == "__main__":
    main()