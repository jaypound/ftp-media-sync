#!/usr/bin/env python3
"""Test the batch lookup function directly"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
import logging

logging.basicConfig(level=logging.INFO)

def main():
    # Initialize database
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    # Test filenames from the schedule
    test_filenames = [
        '250828_PSA_Fulleffect-hd-eng-60.mov.mp4',
        '240711_BMP_Fox Theatre_DAY_ATL26.mp4',
        '251006_PKG_ Westmoreland-Shook Path 400 Ribbon Cutting.mp4'
    ]
    
    print("\n=== TESTING BATCH LOOKUP ===\n")
    
    # Test batch lookup
    results = db.find_assets_by_filenames_batch(test_filenames)
    
    print(f"Batch lookup input: {len(test_filenames)} files")
    print(f"Batch lookup output: {len(results)} entries")
    
    for filename in test_filenames:
        result = results.get(filename)
        if result:
            print(f"\n✓ FOUND: {filename}")
            print(f"  Asset ID: {result['id']}")
            print(f"  Content Type: {result.get('content_type')}")
        else:
            print(f"\n✗ NOT FOUND: {filename}")
    
    # Now test individual lookup for comparison
    print("\n\n=== TESTING INDIVIDUAL LOOKUPS ===\n")
    
    for filename in test_filenames:
        result = db.find_asset_by_filename(filename)
        if result:
            print(f"\n✓ FOUND: {filename}")
            print(f"  Asset ID: {result['id']}")
        else:
            print(f"\n✗ NOT FOUND: {filename}")
    
    # Test with the scheduling query method
    print("\n\n=== TESTING WITH SCHEDULING QUERY ===\n")
    
    for filename in test_filenames:
        content_list = db.get_analyzed_content_for_scheduling(search=filename)
        if content_list:
            print(f"\n✓ FOUND via scheduling: {filename}")
            print(f"  Found {len(content_list)} matches")
            if content_list:
                print(f"  First match: {content_list[0].get('file_name')}")
        else:
            print(f"\n✗ NOT FOUND via scheduling: {filename}")

if __name__ == "__main__":
    main()