#!/usr/bin/env python3
"""Add metadata column to scheduled_items table."""

import sys
from database import db_manager

def add_metadata_column():
    """Add metadata column to scheduled_items table if it doesn't exist."""
    
    # Connect to database if not already connected
    if hasattr(db_manager, 'connected') and not db_manager.connected:
        db_manager.connect()
    elif hasattr(db_manager, 'is_connected') and not db_manager.is_connected():
        db_manager.connect()
    
    conn = db_manager._get_connection()
    
    try:
        cursor = conn.cursor()
        
        # Check if metadata column exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'scheduled_items' 
            AND column_name = 'metadata'
        """)
        result = cursor.fetchone()
        
        if not result:
            # Add metadata column
            cursor.execute("""
                ALTER TABLE scheduled_items ADD COLUMN metadata JSONB
            """)
            conn.commit()
            print('✓ Added metadata column to scheduled_items table')
        else:
            print('✓ metadata column already exists in scheduled_items table')
        
        # Verify the column was added
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'scheduled_items' 
            AND column_name = 'metadata'
        """)
        result = cursor.fetchone()
        
        if result:
            print(f'  Column details: {result["column_name"]} ({result["data_type"]})')
        
        cursor.close()
        db_manager._put_connection(conn)
        
        print('\nMetadata column is ready for storing live input details.')
        
    except Exception as e:
        print(f'✗ Error: {str(e)}')
        if conn:
            conn.rollback()
            db_manager._put_connection(conn)
        sys.exit(1)

if __name__ == '__main__':
    add_metadata_column()