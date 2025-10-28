#!/usr/bin/env python3
"""
Find Assets - Helper script to find asset IDs for testing
"""

import sys
import os
import argparse

# Add backend directory to path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_dir)

from database_postgres import PostgreSQLDatabaseManager

def main():
    parser = argparse.ArgumentParser(description='Find asset IDs for testing')
    parser.add_argument('--type', help='Content type (e.g., PSA, MTG, AN)')
    parser.add_argument('--title', help='Search in content title')
    parser.add_argument('--has-loudness', action='store_true', help='Only show assets with loudness data')
    parser.add_argument('--limit', type=int, default=20, help='Number of results to show')
    
    args = parser.parse_args()
    
    # Initialize database with connection string
    import getpass
    default_pg_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
    db = PostgreSQLDatabaseManager(
        connection_string=os.getenv('DATABASE_URL', default_pg_conn)
    )
    db.connect()  # Initialize the connection pool
    
    # Build query
    query = "SELECT id, content_title, content_type, duration_seconds FROM assets WHERE 1=1"
    params = []
    
    if args.type:
        query += " AND content_type = %s"
        params.append(args.type.lower())
    
    if args.title:
        query += " AND content_title ILIKE %s"
        params.append(f"%{args.title}%")
    
    if args.has_loudness:
        query += " AND id IN (SELECT DISTINCT asset_id FROM metadata WHERE meta_key LIKE 'loudness_%')"
    
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(args.limit)
    
    # Execute query
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    cursor.close()
    db._put_connection(conn)
    
    if results:
        print(f"\nFound {len(results)} assets:\n")
        print(f"{'ID':<8} {'Type':<6} {'Duration':<10} Title")
        print("-" * 80)
        
        for result in results:
            asset_id, title, content_type, duration = result
            duration_str = f"{int(duration)}s" if duration else "N/A"
            print(f"{asset_id:<8} {(content_type or 'N/A').upper():<6} {duration_str:<10} {title}")
    else:
        print("No assets found matching criteria")
    
    print()

if __name__ == '__main__':
    main()