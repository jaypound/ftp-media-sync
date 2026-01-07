#!/usr/bin/env python3
"""
Check and update graphics expiring on 12/5/2025
"""

import psycopg2
from datetime import datetime
import os
import getpass

# Database connection
default_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
conn_string = os.getenv('DATABASE_URL', default_conn)

try:
    # Connect to database
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    
    print("Checking for graphics expiring on 2025-12-05...")
    
    # First check if any exist
    cursor.execute("""
        SELECT id, file_name, end_date, status
        FROM default_graphics
        WHERE end_date = '2025-12-05'
        AND (file_name ILIKE '%.jpg' OR file_name ILIKE '%.png')
        ORDER BY file_name
    """)
    
    graphics = cursor.fetchall()
    
    if graphics:
        print(f"\nFound {len(graphics)} graphics expiring on 2025-12-05:")
        print("-" * 70)
        for gfx_id, file_name, end_date, status in graphics:
            print(f"ID: {gfx_id:4d} | {status:8s} | {file_name}")
        
        # Ask to update
        response = input("\nUpdate these to expire on 2026-01-01? (yes/no): ")
        
        if response.lower() == 'yes':
            cursor.execute("""
                UPDATE default_graphics
                SET end_date = '2026-01-01'
                WHERE end_date = '2025-12-05'
                AND (file_name ILIKE '%.jpg' OR file_name ILIKE '%.png')
            """)
            
            updated = cursor.rowcount
            conn.commit()
            print(f"\n✅ Updated {updated} graphics to expire on 2026-01-01")
        else:
            print("Update cancelled.")
    else:
        # Check for any December 2025 dates
        print("\nNo graphics found with 2025-12-05 expiration.")
        print("\nChecking all December 2025 expirations...")
        
        cursor.execute("""
            SELECT DISTINCT end_date, COUNT(*) as count
            FROM default_graphics
            WHERE end_date >= '2025-12-01' AND end_date <= '2025-12-31'
            AND (file_name ILIKE '%.jpg' OR file_name ILIKE '%.png')
            GROUP BY end_date
            ORDER BY end_date
        """)
        
        dec_dates = cursor.fetchall()
        
        if dec_dates:
            print("\nDecember 2025 expiration dates found:")
            print("-" * 30)
            for date, count in dec_dates:
                print(f"{date}: {count} graphics")
        else:
            print("No graphics expiring in December 2025.")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals():
        conn.close()