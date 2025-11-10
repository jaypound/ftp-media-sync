#!/usr/bin/env python3
"""
Update graphics expiring on 12/6/2025 to 1/1/2026
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
    
    print("Checking graphics expiring on 2025-12-06...")
    
    # Get the graphics
    cursor.execute("""
        SELECT id, file_name, status
        FROM default_graphics
        WHERE end_date = '2025-12-06'
        AND (file_name ILIKE '%.jpg' OR file_name ILIKE '%.png')
        ORDER BY file_name
    """)
    
    graphics = cursor.fetchall()
    
    if graphics:
        print(f"\nFound {len(graphics)} graphics expiring on 2025-12-06:")
        print("-" * 70)
        for i, (gfx_id, file_name, status) in enumerate(graphics):
            print(f"{i+1:2d}. ID: {gfx_id:4d} | {status:8s} | {file_name}")
        
        print("\n" + "="*70)
        response = input("Update these to expire on 2026-01-01? (yes/no): ")
        
        if response.lower() == 'yes':
            # Update with note
            cursor.execute("""
                UPDATE default_graphics
                SET end_date = '2026-01-01',
                    notes = COALESCE(notes || E'\n', '') || 
                           'Expiration extended from 2025-12-06 to 2026-01-01 on ' || 
                           TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
                WHERE end_date = '2025-12-06'
                AND (file_name ILIKE '%.jpg' OR file_name ILIKE '%.png')
            """)
            
            updated = cursor.rowcount
            conn.commit()
            print(f"\n✅ Successfully updated {updated} graphics to expire on 2026-01-01")
            
            # Verify the update
            cursor.execute("""
                SELECT COUNT(*) 
                FROM default_graphics 
                WHERE end_date = '2026-01-01'
                AND notes LIKE '%extended from 2025-12-06%'
            """)
            
            verified = cursor.fetchone()[0]
            print(f"Verified: {verified} graphics now expire on 2026-01-01")
        else:
            print("Update cancelled.")
    
except Exception as e:
    print(f"Error: {e}")
    if 'conn' in locals():
        conn.rollback()
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals():
        conn.close()