#!/usr/bin/env python3
"""Check holiday greetings table structures"""
import os
import sys
import getpass
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

# Connection string
default_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
connection_string = os.getenv('DATABASE_URL', default_conn)

try:
    conn = psycopg2.connect(connection_string)
    
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Check if holiday_greetings_days table exists
        print("=== CHECKING FOR HOLIDAY GREETINGS TABLES ===")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE '%holiday%'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        if tables:
            print("Found holiday-related tables:")
            for table in tables:
                print(f"  - {table['table_name']}")
        else:
            print("No holiday-related tables found!")
        
        # Check for holiday_greetings_days specifically
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_name = 'holiday_greetings_days'
            );
        """)
        exists = cursor.fetchone()['exists']
        
        if exists:
            print("\n=== HOLIDAY_GREETINGS_DAYS TABLE STRUCTURE ===")
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'holiday_greetings_days'
                ORDER BY ordinal_position;
            """)
            cols = cursor.fetchall()
            for col in cols:
                print(f"  {col['column_name']} ({col['data_type']})")
            
            # Check for any data
            cursor.execute("SELECT COUNT(*) as count FROM holiday_greetings_days;")
            count = cursor.fetchone()['count']
            print(f"\nTotal rows in holiday_greetings_days: {count}")
            
            if count > 0:
                print("\n=== SAMPLE DATA (First 5 rows) ===")
                cursor.execute("SELECT * FROM holiday_greetings_days LIMIT 5;")
                rows = cursor.fetchall()
                for row in rows:
                    print(row)
        else:
            print("\n!!! TABLE holiday_greetings_days DOES NOT EXIST !!!")
            print("This explains why daily assignments aren't being created.")
            
            # Check migration files
            print("\n=== CHECKING FOR MIGRATION FILES ===")
            migrations_dir = "/Users/jaypound/git/ftp-media-sync/backend/migrations"
            if os.path.exists(migrations_dir):
                for file in sorted(os.listdir(migrations_dir)):
                    if 'holiday' in file.lower():
                        print(f"  Found: {file}")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    if 'conn' in locals() and conn:
        conn.close()