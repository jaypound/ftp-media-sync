#!/usr/bin/env python3
"""Test if holiday greeting rotation is now working with the exclude_ids fix"""

import os
import sys
import json
from datetime import datetime

# Force PostgreSQL
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager

def check_recent_holiday_greeting_logs():
    """Check recent logs to see if holiday greetings are being selected"""
    log_file = f"logs/holiday_greeting_{datetime.now().strftime('%Y%m%d')}.log"
    
    if not os.path.exists(log_file):
        print(f"No log file found: {log_file}")
        return
    
    print(f"\n=== Analyzing {log_file} ===\n")
    
    # Track what we find
    stats = {
        'total_calls': 0,
        'greetings_found': 0,
        'greetings_selected': 0,
        'unique_selected': set(),
        'categories': set(),
        'errors': []
    }
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
        
    for line in lines:
        if "=== FILTER CONTENT CALLED ===" in line:
            stats['total_calls'] += 1
        elif "Found" in line and "holiday greetings" in line:
            # Extract number of greetings found
            parts = line.split("Found ")
            if len(parts) > 1:
                count_part = parts[1].split(" holiday")[0]
                try:
                    count = int(count_part)
                    if count > 0:
                        stats['greetings_found'] += 1
                except:
                    pass
        elif "SELECTED greeting:" in line:
            stats['greetings_selected'] += 1
            # Extract greeting name
            if "file_name" in line:
                start = line.find("SELECTED greeting: ") + len("SELECTED greeting: ")
                end = line.find(" (asset_id:")
                if end > start:
                    greeting = line[start:end].strip()
                    stats['unique_selected'].add(greeting)
        elif "Duration category:" in line:
            # Extract category
            parts = line.split("Duration category: ")
            if len(parts) > 1:
                category = parts[1].strip()
                stats['categories'].add(category)
        elif "All" in line and "greetings were in exclude list" in line:
            stats['errors'].append(line.strip())
    
    # Print results
    print(f"Total filter calls: {stats['total_calls']}")
    print(f"Times greetings found in content: {stats['greetings_found']}")
    print(f"Times greetings selected: {stats['greetings_selected']}")
    print(f"Unique greetings selected: {len(stats['unique_selected'])}")
    
    if stats['unique_selected']:
        print("\nGreetings selected:")
        for greeting in sorted(stats['unique_selected']):
            short_name = greeting.replace('251210_SSP_', '').replace('.mp4', '')
            print(f"  - {short_name}")
    
    print(f"\nDuration categories seen: {', '.join(sorted(stats['categories']))}")
    
    if stats['errors']:
        print(f"\nErrors found: {len(stats['errors'])}")
        for err in stats['errors'][:5]:  # Show first 5
            print(f"  - {err}")

def check_holiday_greeting_distribution():
    """Check the current distribution in the database"""
    db_manager.connect()
    
    try:
        conn = db_manager._get_connection()
        cursor = conn.cursor()
        
        # Get current distribution
        cursor.execute("""
            SELECT 
                hgr.file_name,
                hgr.scheduled_count,
                hgr.last_scheduled
            FROM holiday_greeting_rotation hgr
            ORDER BY hgr.scheduled_count DESC, hgr.file_name
            LIMIT 10
        """)
        
        print("\n=== Top 10 Holiday Greetings by Play Count ===")
        for row in cursor.fetchall():
            file_name, count, last = row
            short_name = file_name.replace('251210_SSP_', '').replace('.mp4', '') if file_name else 'Unknown'
            if last and hasattr(last, 'strftime'):
                last_str = last.strftime('%Y-%m-%d %H:%M')
            else:
                last_str = 'Never'
            print(f"{short_name[:30]:30} | {count:3} plays | Last: {last_str}")
        
        # Get distribution stats
        cursor.execute("""
            SELECT 
                MIN(scheduled_count) as min_count,
                MAX(scheduled_count) as max_count,
                AVG(scheduled_count) as avg_count,
                COUNT(CASE WHEN scheduled_count = 0 THEN 1 END) as never_played
            FROM holiday_greeting_rotation
        """)
        
        result = cursor.fetchone()
        min_c, max_c, avg_c, never = result
        
        print(f"\nDistribution Stats:")
        print(f"  Min plays: {min_c}")
        print(f"  Max plays: {max_c}")
        print(f"  Avg plays: {avg_c:.1f}")
        print(f"  Never played: {never}")
        
        cursor.close()
        db_manager._put_connection(conn)
        
    except Exception as e:
        print(f"Database error: {e}")

def main():
    print("Holiday Greeting Rotation Fix Test")
    print("=" * 60)
    
    # Check logs
    check_recent_holiday_greeting_logs()
    
    # Check database
    check_holiday_greeting_distribution()
    
    print("\n" + "=" * 60)
    print("\nTo test the fix:")
    print("1. Create a new daily or weekly schedule")
    print("2. Look for 'spots' category scheduling in the logs")
    print("3. Check if different holiday greetings are selected")
    print("4. Run this script again to see updated stats")

if __name__ == "__main__":
    main()