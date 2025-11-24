#!/usr/bin/env python3
import psycopg2
import os
import getpass
from datetime import datetime

# Use same connection as the app
connection_string = os.getenv(
    'DATABASE_URL', 
    f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
)

def find_and_fix_bad_date():
    try:
        # Connect to database
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        
        print("Connected to database successfully")
        print("\nSearching for meeting: 251117_MTG_City Council.mp4")
        
        # Find the specific meeting in instances table
        # First get basic info without the problematic date field
        cursor.execute("""
            SELECT i.id, i.asset_id, i.file_name, a.content_title
            FROM instances i
            JOIN assets a ON i.asset_id = a.id
            WHERE i.file_name = %s
        """, ('251117_MTG_City Council.mp4',))
        
        result = cursor.fetchone()
        
        if result:
            instance_id, asset_id, file_name, title = result
            print(f"\nFound meeting!")
            print(f"Instance ID: {instance_id}")
            print(f"Asset ID: {asset_id}")
            print(f"File name: {file_name}")
            print(f"Title: {title}")
            
            # Remove the problematic expiration date
            print("\nRemoving the expiration date for this meeting...")
            
            # Auto-fix without prompting
            if True:
                cursor.execute("""
                    UPDATE scheduling_metadata 
                    SET content_expiry_date = NULL
                    WHERE asset_id = %s
                """, (asset_id,))
                
                conn.commit()
                print("\nExpiration date has been removed successfully!")
                
                # Verify the fix
                cursor.execute("""
                    SELECT content_expiry_date 
                    FROM scheduling_metadata 
                    WHERE asset_id = %s
                """, (asset_id,))
                
                result = cursor.fetchone()
                new_date = result[0] if result else None
                print(f"Verified expiry date is now: {new_date}")
        else:
            print("\nMeeting not found in database.")
            print("Let's check if there are any other meetings with bad dates...")
            
            # Look for any dates with year > 3000
            cursor.execute("""
                SELECT i.file_name, sm.content_expiry_date::text
                FROM instances i
                JOIN assets a ON i.asset_id = a.id
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE a.content_type = 'mtg'
                AND sm.content_expiry_date IS NOT NULL
                ORDER BY sm.content_expiry_date::text DESC
                LIMIT 10
            """)
            
            meetings = cursor.fetchall()
            if meetings:
                print("\nTop 10 meetings by expiry date:")
                for fname, exp_date in meetings:
                    print(f"  {fname}: {exp_date}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_and_fix_bad_date()