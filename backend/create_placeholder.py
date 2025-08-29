#!/usr/bin/env python3
"""Create a placeholder asset for live inputs in the database."""

import sys
from database import db_manager

def create_placeholder_asset():
    """Create a placeholder asset for live inputs if it doesn't exist."""
    
    # Connect to database if not already connected
    if hasattr(db_manager, 'connected') and not db_manager.connected:
        db_manager.connect()
    elif hasattr(db_manager, 'is_connected') and not db_manager.is_connected():
        db_manager.connect()
    
    conn = db_manager._get_connection()
    
    try:
        cursor = conn.cursor()
        
        # Check if placeholder exists
        cursor.execute("""
            SELECT id, guid, content_title FROM assets WHERE guid = '00000000-0000-0000-0000-000000000000'
        """)
        result = cursor.fetchone()
        
        if result:
            print(f'✓ Placeholder asset already exists:')
            print(f'  ID: {result["id"]}')
            print(f'  GUID: {result["guid"]}')
            print(f'  Title: {result["content_title"]}')
        else:
            # Create placeholder
            cursor.execute("""
                INSERT INTO assets (
                    guid, 
                    content_title, 
                    content_type, 
                    duration_seconds, 
                    duration_category,
                    engagement_score,
                    created_at,
                    updated_at
                ) VALUES (
                    '00000000-0000-0000-0000-000000000000',
                    'Live Input Placeholder',
                    'other',
                    0,
                    'spots',
                    0,
                    NOW(),
                    NOW()
                )
                RETURNING id
            """)
            new_id = cursor.fetchone()
            conn.commit()
            print(f'✓ Created placeholder asset for live inputs:')
            print(f'  ID: {new_id["id"]}')
            print(f'  GUID: 00000000-0000-0000-0000-000000000000')
            print(f'  Title: Live Input Placeholder')
        
        cursor.close()
        db_manager._put_connection(conn)
        
        print('\nPlaceholder asset is ready for use with live inputs.')
        
    except Exception as e:
        print(f'✗ Error: {str(e)}')
        if conn:
            conn.rollback()
            db_manager._put_connection(conn)
        sys.exit(1)

if __name__ == '__main__':
    create_placeholder_asset()