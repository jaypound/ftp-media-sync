#!/usr/bin/env python3
"""Test holiday greeting rotation table contents"""

import os
import sys

# Force PostgreSQL
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager

def main():
    # Connect to database
    db_manager.connect()
    
    try:
        conn = db_manager._get_connection()
        cursor = conn.cursor()  # Use regular cursor, not RealDictCursor
        
        # Check holiday greeting rotation table
        print("=== Holiday Greeting Rotation Table ===")
        cursor.execute("""
            SELECT 
                hgr.asset_id,
                hgr.file_name,
                hgr.scheduled_count,
                hgr.last_scheduled,
                a.duration_category,
                a.content_type
            FROM holiday_greeting_rotation hgr
            LEFT JOIN assets a ON hgr.asset_id = a.id
            ORDER BY hgr.scheduled_count ASC, hgr.file_name
        """)
        
        rows = cursor.fetchall()
        print(f"\nTotal holiday greetings in rotation table: {len(rows)}")
        
        # Group by duration category
        by_category = {}
        for row in rows:
            asset_id, file_name, count, last_sched, duration_cat, content_type = row
            if duration_cat not in by_category:
                by_category[duration_cat] = []
            by_category[duration_cat].append({
                'asset_id': asset_id,
                'file_name': file_name.replace('251210_SSP_', '').replace('.mp4', '') if file_name else 'Unknown',
                'count': count,
                'last_scheduled': last_sched,
                'content_type': content_type
            })
        
        for category, greetings in sorted(by_category.items()):
            print(f"\n{category or 'UNKNOWN'} Category ({len(greetings)} greetings):")
            for g in greetings[:5]:  # Show first 5
                print(f"  - {g['file_name']}: {g['count']} plays")
        
        # Check for greetings that have never been scheduled
        cursor.execute("""
            SELECT COUNT(*) 
            FROM holiday_greeting_rotation 
            WHERE scheduled_count = 0
        """)
        result = cursor.fetchone()
        never_scheduled = result[0] if result else 0
        print(f"\nGreetings never scheduled: {never_scheduled}")
        
        # Check assets table for holiday greetings
        print("\n=== Assets Table Holiday Greetings ===")
        cursor.execute("""
            SELECT 
                a.id,
                a.content_title,
                a.duration_category,
                a.content_type,
                i.file_name
            FROM assets a
            JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
            WHERE i.file_name ILIKE '%holiday%greeting%'
            ORDER BY a.duration_category, a.content_title
            LIMIT 10
        """)
        
        rows = cursor.fetchall()
        print(f"Found {cursor.rowcount} holiday greetings in assets table")
        for row in rows:
            asset_id, title, dur_cat, cont_type, file_name = row
            print(f"  ID: {asset_id}, Cat: {dur_cat}, Type: {cont_type}, File: {file_name[:50]}")
        
        cursor.close()
        db_manager._put_connection(conn)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()