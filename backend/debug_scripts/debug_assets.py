#!/usr/bin/env python3
"""Debug assets table to see what's available"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

def check_assets():
    db_manager = PostgreSQLDatabaseManager()
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check total assets
        cursor.execute("SELECT COUNT(*) as count FROM assets")
        result = cursor.fetchone()
        print(f"Total assets in database: {result['count']}")
        
        # Check active assets
        cursor.execute("SELECT COUNT(*) as count FROM assets WHERE active = true")
        result = cursor.fetchone()
        print(f"Active assets: {result['count']}")
        
        # Check by category
        cursor.execute("""
            SELECT duration_category, COUNT(*) as count 
            FROM assets 
            WHERE active = true 
            GROUP BY duration_category
        """)
        print("\nActive assets by category:")
        for row in cursor.fetchall():
            print(f"  {row['duration_category']}: {row['count']}")
        
        # Sample some assets
        cursor.execute("""
            SELECT id, content_title, duration_category, active, created_date, expiration_date
            FROM assets
            LIMIT 10
        """)
        print("\nSample assets:")
        for row in cursor.fetchall():
            print(f"  ID: {row['id']}, Title: {row['content_title'][:30]}, "
                  f"Category: {row['duration_category']}, Active: {row['active']}, "
                  f"Created: {row['created_date']}, Expires: {row['expiration_date']}")
        
        cursor.close()
    finally:
        conn.close()

if __name__ == "__main__":
    check_assets()