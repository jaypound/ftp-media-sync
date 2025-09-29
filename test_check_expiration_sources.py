#!/usr/bin/env python3
"""
Test script to check all possible sources of expiration dates for a file
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

# Database connection parameters - adjust if needed
DB_PARAMS = {
    "host": "localhost",
    "database": "ftp_media_sync",
    "user": "postgres",
    "password": "postgres"
}

filename = "250908_MTG_Zoning_Committee.mp4"

print(f"Checking all expiration date sources for: {filename}")
print("=" * 60)

try:
    conn = psycopg2.connect(**DB_PARAMS)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # 1. Check instances table
        print("\n1. INSTANCES TABLE:")
        cursor.execute("""
            SELECT id, file_name, expiration_date, created_at, updated_at
            FROM instances 
            WHERE file_name LIKE %s
            ORDER BY id
        """, (f'%{filename}%',))
        
        for row in cursor.fetchall():
            print(f"   ID: {row['id']}")
            print(f"   File: {row['file_name']}")
            print(f"   Expiration: {row['expiration_date']}")
            print(f"   Created: {row['created_at']}")
            print(f"   Updated: {row['updated_at']}")
            print()
        
        # 2. Check scheduling_metadata table
        print("\n2. SCHEDULING_METADATA TABLE:")
        cursor.execute("""
            SELECT sm.*, i.file_name 
            FROM scheduling_metadata sm
            JOIN instances i ON sm.asset_id = i.id
            WHERE i.file_name LIKE %s
            ORDER BY sm.asset_id
        """, (f'%{filename}%',))
        
        for row in cursor.fetchall():
            print(f"   Asset ID: {row['asset_id']}")
            print(f"   File: {row['file_name']}")
            print(f"   Content Expiry Date: {row['content_expiry_date']}")
            print(f"   Metadata Synced At: {row['metadata_synced_at']}")
            print()
        
        # 3. Check for multiple entries with similar names
        print("\n3. SIMILAR FILENAMES:")
        cursor.execute("""
            SELECT DISTINCT file_name, COUNT(*) as count
            FROM instances 
            WHERE file_name LIKE '%MTG_Zoning_Committee%'
            GROUP BY file_name
            ORDER BY file_name
        """)
        
        for row in cursor.fetchall():
            print(f"   {row['file_name']} - Count: {row['count']}")
        
        # 4. Check both tables for asset ID 370 specifically
        print("\n4. ASSET ID 370 DETAILS:")
        cursor.execute("""
            SELECT i.*, sm.content_expiry_date 
            FROM instances i
            LEFT JOIN scheduling_metadata sm ON i.id = sm.asset_id
            WHERE i.id = 370
        """)
        
        row = cursor.fetchone()
        if row:
            print(f"   Instances expiration_date: {row['expiration_date']}")
            print(f"   Scheduling content_expiry_date: {row['content_expiry_date']}")
            print(f"   File name: {row['file_name']}")

except Exception as e:
    print(f"Error: {str(e)}")
finally:
    if 'conn' in locals():
        conn.close()

print("\n" + "=" * 60)
print("Check complete")