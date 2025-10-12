#!/usr/bin/env python3
"""Debug script to check filename matching issues"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Initialize database
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    # Test filenames from the schedule
    test_filenames = [
        '240711_BMP_Inman Park_DAY_ATL26.mp4',
        '250121_PSA_Gun Safe Stories Reba 30 ENG.mp4',
        '250825_PKG_Community Food Center_Atlanta_v2.mp4',
        '251002_PKG_Neighborhood Reinvestment Initiative Presser.mp4',
        '240711_BMP_Fox Theatre_DAY_ATL26.mp4'
    ]
    
    conn = db._get_connection()
    cursor = conn.cursor()
    
    print("\n=== FILENAME MATCHING DEBUG ===\n")
    
    for test_file in test_filenames:
        print(f"\nTesting: '{test_file}'")
        print(f"Length: {len(test_file)}")
        print(f"Repr: {repr(test_file)}")
        
        # Test exact match
        cursor.execute("SELECT COUNT(*) FROM instances WHERE file_name = %s", (test_file,))
        result = cursor.fetchone()
        exact_count = result[0] if result else 0
        print(f"Exact match count: {exact_count}")
        
        # Test LIKE match with first part
        like_pattern = test_file[:20] + '%'
        cursor.execute("SELECT file_name FROM instances WHERE file_name LIKE %s LIMIT 3", (like_pattern,))
        like_results = cursor.fetchall()
        if like_results:
            print(f"LIKE matches for '{like_pattern}':")
            for row in like_results:
                print(f"  - '{row[0]}'")
                print(f"    Length: {len(row[0])}")
                print(f"    Repr: {repr(row[0])}")
        else:
            print(f"No LIKE matches for '{like_pattern}'")
        
        # Test with stripped/cleaned filename
        clean_file = test_file.strip()
        if clean_file != test_file:
            print(f"After strip: '{clean_file}'")
            cursor.execute("SELECT COUNT(*) FROM instances WHERE file_name = %s", (clean_file,))
            clean_count = cursor.fetchone()[0]
            print(f"Clean match count: {clean_count}")
    
    # Also check what's actually in the database
    print("\n\n=== SAMPLE DATABASE FILENAMES ===\n")
    cursor.execute("""
        SELECT DISTINCT file_name 
        FROM instances 
        WHERE file_name LIKE '240711_BMP%' OR file_name LIKE '250121_PSA%'
        LIMIT 10
    """)
    db_samples = cursor.fetchall()
    for row in db_samples:
        print(f"DB: '{row[0]}'")
        print(f"    Length: {len(row[0])}")
        print(f"    Repr: {repr(row[0])}")
    
    cursor.close()
    db._put_connection(conn)

if __name__ == "__main__":
    main()