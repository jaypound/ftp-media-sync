#!/usr/bin/env python3
"""
Clear stuck sync job locks
"""
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def clear_locks():
    """Clear all sync job locks"""
    try:
        # Database connection parameters
        db_params = {
            'dbname': os.getenv('DB_NAME', 'ftp_media_sync'),
            'user': os.getenv('DB_USER', 'jaypound'),
            'password': os.getenv('DB_PASSWORD', ''),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432')
        }
        
        # Connect to database
        print(f"Connecting to database {db_params['dbname']}...")
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        # Clear all locks
        cursor.execute("""
            UPDATE sync_jobs 
            SET lock_acquired_at = NULL,
                lock_expires_at = NULL,
                last_run_status = 'idle'
            WHERE job_name = 'castus_expiration_sync_all'
        """)
        
        print(f"Cleared {cursor.rowcount} locks")
        
        # Show current state
        cursor.execute("SELECT * FROM sync_jobs")
        for row in cursor.fetchall():
            print(f"Job: {row[1]}, Status: {row[4]}, Lock: {row[6]}")
        
        conn.commit()
        print("✅ Locks cleared successfully!")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    clear_locks()