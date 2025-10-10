#!/usr/bin/env python3
"""
Run the sync_jobs table migration
"""
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

def run_migration():
    """Run the sync_jobs migration"""
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
        
        # Read migration SQL
        migration_file = 'migrations/add_sync_jobs_table.sql'
        print(f"Reading migration file: {migration_file}")
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        print("Executing migration...")
        cursor.execute(migration_sql)
        
        # Verify table was created
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'sync_jobs'
            );
        """)
        
        table_exists = cursor.fetchone()[0]
        if table_exists:
            print("✅ sync_jobs table created successfully!")
            
            # Check the default job entry
            cursor.execute("SELECT * FROM sync_jobs WHERE job_name = 'castus_expiration_sync_all'")
            job = cursor.fetchone()
            if job:
                print("✅ Default job entry created: castus_expiration_sync_all")
            else:
                print("❌ Default job entry not found")
        else:
            print("❌ sync_jobs table creation failed!")
            
        # Commit changes
        conn.commit()
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error running migration: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        sys.exit(1)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    run_migration()