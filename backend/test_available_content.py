#!/usr/bin/env python3
"""
Test the get_available_content query to verify it returns all content, not just featured items
"""

import os
import sys
from datetime import datetime, timedelta

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler_postgres import PostgreSQLScheduler
from config_manager import ConfigManager

def test_available_content():
    """Test that get_available_content returns all available content"""
    
    # Initialize scheduler
    scheduler = PostgreSQLScheduler()
    
    # Test parameters
    duration_category = 'id'  # Must be lowercase
    exclude_ids = []
    schedule_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"Testing get_available_content for duration category: {duration_category}")
    print(f"Schedule date: {schedule_date}")
    print("=" * 50)
    
    # Get available content
    available_content = scheduler.get_available_content(
        duration_category=duration_category,
        exclude_ids=exclude_ids,
        schedule_date=schedule_date
    )
    
    print(f"\nTotal content items returned: {len(available_content)}")
    
    # Separate featured and non-featured content
    featured_content = [c for c in available_content if c.get('featured', False)]
    non_featured_content = [c for c in available_content if not c.get('featured', False)]
    
    print(f"Featured content: {len(featured_content)}")
    print(f"Non-featured content: {len(non_featured_content)}")
    
    # Show some sample content
    print("\nSample content (first 5 of each type):")
    
    if featured_content:
        print("\nFeatured content:")
        for i, content in enumerate(featured_content[:5]):
            print(f"  {i+1}. {content.get('content_title', 'Unknown')} (ID: {content.get('content_id')})")
    
    if non_featured_content:
        print("\nNon-featured content:")
        for i, content in enumerate(non_featured_content[:5]):
            print(f"  {i+1}. {content.get('content_title', 'Unknown')} (ID: {content.get('content_id')})")
    
    # Test other categories too
    print("\n" + "=" * 50)
    print("Testing all categories:")
    
    for cat in ['id', 'spots', 'short_form', 'long_form']:
        content = scheduler.get_available_content(
            duration_category=cat,
            exclude_ids=[],
            schedule_date=schedule_date
        )
        featured = len([c for c in content if c.get('featured', False)])
        total = len(content)
        print(f"{cat}: {total} items ({featured} featured)")
    
    return len(available_content) > 2  # Should have more than just the 2 featured items

if __name__ == "__main__":
    print("Testing available content query...")
    print("Note: Make sure your database connection is configured properly")
    print("=" * 50)
    
    try:
        success = test_available_content()
        if success:
            print("\n✓ Query is returning more than just featured content!")
        else:
            print("\n✗ Query is still only returning featured content")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nError running test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)