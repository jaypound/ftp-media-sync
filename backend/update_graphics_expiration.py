#!/usr/bin/env python3
"""
Update expiration dates for graphics files (.jpg, .png) 
that expire on 12/5/2025 to 1/1/2026
"""

import os
import sys
import psycopg2
from datetime import datetime
from database import db_manager

def update_graphics_expiration():
    """Update expiration dates for specific graphics"""
    
    try:
        # Get database connection
        db_manager.connect()
        conn = db_manager._get_connection()
        cursor = conn.cursor()
        
        # First, let's see what graphics are expiring on 12/5/2025
        print("Checking for graphics expiring on 2025-12-05...")
        
        cursor.execute("""
            SELECT id, file_name, end_date
            FROM default_graphics
            WHERE end_date = '2025-12-05'
            AND (file_name ILIKE '%.jpg' OR file_name ILIKE '%.png')
            ORDER BY file_name
        """)
        
        graphics_to_update = cursor.fetchall()
        
        if not graphics_to_update:
            print("No graphics found with expiration date 2025-12-05")
            return
        
        print(f"\nFound {len(graphics_to_update)} graphics to update:")
        print("-" * 60)
        for gfx_id, file_name, end_date in graphics_to_update:
            print(f"ID: {gfx_id:4d} | {file_name} | Expires: {end_date}")
        
        # Confirm before updating
        print("\n" + "="*60)
        response = input("Update these graphics to expire on 2026-01-01? (yes/no): ")
        
        if response.lower() != 'yes':
            print("Update cancelled.")
            return
        
        # Update the expiration dates
        print("\nUpdating expiration dates...")
        
        cursor.execute("""
            UPDATE default_graphics
            SET end_date = '2026-01-01',
                notes = COALESCE(notes || E'\n', '') || 'Expiration extended from 2025-12-05 to 2026-01-01 on ' || CURRENT_DATE::text
            WHERE end_date = '2025-12-05'
            AND (file_name ILIKE '%.jpg' OR file_name ILIKE '%.png')
        """)
        
        rows_updated = cursor.rowcount
        
        # Commit the changes
        conn.commit()
        
        print(f"\n✅ Successfully updated {rows_updated} graphics!")
        print("New expiration date: 2026-01-01")
        
        # Show the updated records
        print("\nVerifying updates...")
        cursor.execute("""
            SELECT id, file_name, end_date
            FROM default_graphics
            WHERE id IN (%s)
            ORDER BY file_name
        """ % ','.join(str(gfx[0]) for gfx in graphics_to_update))
        
        updated_graphics = cursor.fetchall()
        print("\nUpdated graphics:")
        print("-" * 60)
        for gfx_id, file_name, end_date in updated_graphics:
            print(f"ID: {gfx_id:4d} | {file_name} | New expiry: {end_date}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if 'conn' in locals():
            conn.rollback()
        raise
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            db_manager._release_connection(conn)

if __name__ == "__main__":
    update_graphics_expiration()