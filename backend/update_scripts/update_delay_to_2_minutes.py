#!/usr/bin/env python3
"""
Update auto generation delay from 5 minutes to 2 minutes
"""
import os
import sys

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from database import db_manager

def update_delay():
    """Update delay_minutes in auto generation config"""
    try:
        # Check if database is connected
        if not db_manager.connected:
            print("Connecting to database...")
            db_manager.connect()
        
        if not db_manager.connected:
            print("Failed to connect to database")
            return False
        
        # Update config
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Update delay_minutes to 2
            cursor.execute("""
                UPDATE auto_generation_config 
                SET delay_minutes = 2, updated_at = NOW()
                WHERE id = 1
            """)
            
            # Check if update succeeded
            cursor.execute("SELECT delay_minutes FROM auto_generation_config WHERE id = 1")
            result = cursor.fetchone()
            
            if result and result['delay_minutes'] == 2:
                print("✅ Delay has been updated to 2 minutes!")
                conn.commit()
                return True
            else:
                print("❌ Failed to update delay")
                conn.rollback()
                return False
                
        finally:
            cursor.close()
            db_manager._put_connection(conn)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    update_delay()