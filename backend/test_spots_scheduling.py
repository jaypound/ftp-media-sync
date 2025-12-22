#!/usr/bin/env python3
"""Test if spots category scheduling now properly rotates holiday greetings"""

import os
import sys
from datetime import datetime

# Force PostgreSQL
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager
from scheduler_postgres import scheduler_postgres

def test_spots_content():
    """Test getting spots content to see if holiday greetings are included"""
    db_manager.connect()
    
    print("=== Testing Spots Category Content ===\n")
    
    # Get available content for spots category
    available = scheduler_postgres.get_available_content(
        duration_category='spots',
        exclude_ids=[],  # Start with empty exclude list
        schedule_date=datetime.now().strftime('%Y-%m-%d')
    )
    
    print(f"Total spots content available: {len(available)}")
    
    # Check for holiday greetings
    holiday_greetings = []
    for content in available:
        if 'holiday' in content.get('file_name', '').lower() and 'greeting' in content.get('file_name', '').lower():
            holiday_greetings.append(content)
    
    print(f"Holiday greetings found: {len(holiday_greetings)}")
    
    if holiday_greetings:
        print("\nFirst 5 holiday greetings:")
        for hg in holiday_greetings[:5]:
            print(f"  - {hg['file_name']} (ID: {hg['asset_id']})")
    
    # Now test the filter
    print("\n=== Testing Holiday Integration Filter ===")
    
    if hasattr(scheduler_postgres, 'holiday_integration'):
        print(f"Holiday integration enabled: {scheduler_postgres.holiday_integration.enabled}")
        
        if scheduler_postgres.holiday_integration.enabled:
            # Reset session
            scheduler_postgres.holiday_integration.reset_session()
            
            # Test filter
            filtered = scheduler_postgres.holiday_integration.filter_available_content(
                available_content=available,
                duration_category='spots',
                exclude_ids=[]  # Empty exclude list
            )
            
            print(f"\nContent after holiday filter: {len(filtered)}")
            
            # Check what was selected
            selected_greetings = [c for c in filtered if 'holiday' in c.get('file_name', '').lower()]
            if selected_greetings:
                print(f"Holiday greeting selected: {selected_greetings[0]['file_name']}")
            else:
                print("No holiday greeting was selected!")
    else:
        print("Holiday integration not found!")

def check_greeting_stats():
    """Check current greeting statistics"""
    print("\n=== Current Holiday Greeting Stats ===")
    
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute("""
        SELECT 
            MIN(scheduled_count) as min_plays,
            MAX(scheduled_count) as max_plays,
            COUNT(CASE WHEN scheduled_count = 0 THEN 1 END) as never_played,
            COUNT(*) as total
        FROM holiday_greeting_rotation
    """)
    
    result = cursor.fetchone()
    if result:
        print(f"Min plays: {result[0]}")
        print(f"Max plays: {result[1]}")  
        print(f"Never played: {result[2]} out of {result[3]}")
    
    cursor.close()
    db_manager._put_connection(conn)

def main():
    print("Holiday Greeting Spots Scheduling Test")
    print("=" * 50)
    
    test_spots_content()
    check_greeting_stats()
    
    print("\n" + "=" * 50)
    print("\nTo fully test the fix:")
    print("1. Create a NEW daily or weekly schedule")
    print("2. The 11 never-played greetings should be prioritized")
    print("3. Check the logs for 'SELECTED greeting' entries")

if __name__ == "__main__":
    main()