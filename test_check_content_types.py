#!/usr/bin/env python3
"""
Check what content types exist in the database
"""
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection parameters
DB_PARAMS = {
    "host": "localhost",
    "database": "ftp_media_sync",
    "user": "postgres",
    "password": "postgres"
}

try:
    conn = psycopg2.connect(**DB_PARAMS)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get distinct content types
        print("Checking content_type values in assets table...")
        print("-" * 60)
        
        cursor.execute("""
            SELECT DISTINCT content_type, COUNT(*) as count
            FROM assets
            GROUP BY content_type
            ORDER BY content_type
        """)
        
        results = cursor.fetchall()
        print(f"Found {len(results)} distinct content types:\n")
        
        for row in results:
            print(f"  {row['content_type']}: {row['count']} items")
        
        # Check the enum definition
        print("\n" + "-" * 60)
        print("Checking content_type enum definition...")
        
        cursor.execute("""
            SELECT 
                t.typname as enum_name,
                string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) as enum_values
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid
            WHERE t.typname = 'content_type'
            GROUP BY t.typname
        """)
        
        enum_info = cursor.fetchone()
        if enum_info:
            print(f"\nEnum name: {enum_info['enum_name']}")
            print(f"Valid values: {enum_info['enum_values']}")
        
        # Check a specific MTG file
        print("\n" + "-" * 60)
        print("Checking MTG files...")
        
        cursor.execute("""
            SELECT i.file_name, a.content_type
            FROM instances i
            JOIN assets a ON i.asset_id = a.id
            WHERE i.file_name LIKE '%MTG%'
            LIMIT 5
        """)
        
        mtg_files = cursor.fetchall()
        if mtg_files:
            print(f"Found {len(mtg_files)} MTG files:")
            for f in mtg_files:
                print(f"  {f['file_name']}: {f['content_type']}")
                
except Exception as e:
    print(f"Error: {str(e)}")
finally:
    if 'conn' in locals():
        conn.close()