#!/usr/bin/env python3
"""Investigate why the same BMP files are being scheduled repeatedly"""

import os
import sys
os.chdir('/Users/jaypound/git/ftp-media-sync/backend')
sys.path.insert(0, '/Users/jaypound/git/ftp-media-sync/backend')

from database import db_manager
from datetime import datetime, timedelta

def main():
    # Use the global db_manager instance
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    
    print("=== BMP Rotation Investigation ===\n")
    
    # Check total BMP files available
    cursor.execute('''
        SELECT COUNT(DISTINCT a.id) as count
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.content_type = 'bmp'
        AND a.analysis_completed = TRUE
        AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
        AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > NOW())
        AND (sm.go_live_date IS NULL OR sm.go_live_date <= NOW())
    ''')
    result = cursor.fetchone()
    print(f'Total available BMP files: {result["count"]}')
    
    # Get list of BMP files sorted by usage
    print('\n--- BMP Files by Usage (least used first) ---')
    cursor.execute('''
        SELECT 
            a.id,
            a.content_title,
            i.file_name,
            sm.last_scheduled_date,
            sm.total_airings,
            sm.featured,
            a.engagement_score,
            a.theme,
            EXTRACT(EPOCH FROM (NOW() - COALESCE(sm.last_scheduled_date, '2000-01-01'))) / 3600 as hours_since_last
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.content_type = 'bmp'
        AND a.analysis_completed = TRUE
        AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
        AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > NOW())
        AND (sm.go_live_date IS NULL OR sm.go_live_date <= NOW())
        ORDER BY COALESCE(sm.total_airings, 0) ASC, sm.last_scheduled_date ASC NULLS FIRST
        LIMIT 15
    ''')
    
    for row in cursor:
        last_scheduled = f"{row['last_scheduled_date']:%Y-%m-%d %H:%M}" if row['last_scheduled_date'] else "Never"
        print(f"\n  File: {row['file_name']}")
        print(f"    ID: {row['id']}, Airings: {row['total_airings'] or 0}, Last: {last_scheduled}")
        print(f"    Hours since: {row['hours_since_last']:.1f}, Score: {row['engagement_score']}, Theme: {row['theme']}")
    
    # Check the specific problematic files
    print('\n\n--- Checking Specific Problem Files ---')
    problem_files = [
        '240711_BMP_Fox Theatre_DAY_ATL26.mp4',
        '251014_MAF_Crime is Toast_v2.mp4'
    ]
    
    for filename in problem_files:
        print(f'\n{filename}:')
        # Remove .mp4 for the second file name pattern
        filename_pattern = filename.replace('.mp4', '%')
        cursor.execute('''
            SELECT 
                a.id,
                a.content_type,
                a.duration_category,
                a.engagement_score,
                sm.total_airings,
                sm.last_scheduled_date,
                sm.featured,
                sm.available_for_scheduling,
                i.file_name,
                EXTRACT(EPOCH FROM (NOW() - COALESCE(sm.last_scheduled_date, '2000-01-01'))) / 3600 as hours_since_last
            FROM assets a
            JOIN instances i ON a.id = i.asset_id
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE i.file_name LIKE %s
        ''', (filename_pattern,))
        
        found = False
        for row in cursor:
            found = True
            last_scheduled = f"{row['last_scheduled_date']:%Y-%m-%d %H:%M}" if row['last_scheduled_date'] else "Never"
            print(f"  Found: {row['file_name']}")
            print(f"  Asset ID: {row['id']}")
            print(f"  Type: {row['content_type']}, Category: {row['duration_category']}")
            print(f"  Total Airings: {row['total_airings'] or 0}")
            print(f"  Last Scheduled: {last_scheduled}")
            print(f"  Hours since last: {row['hours_since_last']:.1f}")
            print(f"  Featured: {row['featured']}")
            print(f"  Available: {row['available_for_scheduling']}")
            print(f"  Engagement: {row['engagement_score']}")
        
        if not found:
            print(f"  NOT FOUND in database")
    
    # Check recent schedule to see repetition pattern
    print('\n\n--- Recent BMP Scheduling Pattern (last 48 hours) ---')
    cursor.execute('''
        SELECT 
            si.start_time,
            si.content_title,
            si.file_name,
            si.asset_id
        FROM scheduled_items si
        WHERE si.content_type = 'bmp'
        AND si.start_time >= NOW() - INTERVAL '48 hours'
        ORDER BY si.start_time DESC
        LIMIT 30
    ''')
    
    bmp_pattern = {}
    for row in cursor:
        filename = row['file_name']
        if filename not in bmp_pattern:
            bmp_pattern[filename] = 0
        bmp_pattern[filename] += 1
        print(f"  {row['start_time']:%Y-%m-%d %H:%M} - {filename} (ID: {row['asset_id']})")
    
    print('\n--- BMP Frequency in last 48 hours ---')
    for filename, count in sorted(bmp_pattern.items(), key=lambda x: x[1], reverse=True):
        print(f"  {filename}: {count} times")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()