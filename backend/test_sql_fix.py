#!/usr/bin/env python3
"""Test a simplified version of the query"""

from datetime import datetime, timedelta
from scheduler_postgres import PostgreSQLScheduler

scheduler = PostgreSQLScheduler()

# Override the get_available_content method with a simpler query
def get_available_content_simple(duration_category, exclude_ids=None, ignore_delays=False):
    """Simplified query without complex date arithmetic"""
    from database_postgres import db_manager
    
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        
        # Simple query without INTERVAL literals
        query = """
            SELECT 
                a.id as asset_id,
                a.content_title,
                a.duration_seconds,
                a.duration_category,
                sm.last_scheduled_date,
                sm.total_airings
            FROM assets a
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE a.duration_category = %s
              AND a.analysis_completed = TRUE
        """
        
        params = [duration_category]
        
        if exclude_ids:
            placeholders = ','.join(['%s'] * len(exclude_ids))
            query += f" AND a.id NOT IN ({placeholders})"
            params.extend(exclude_ids)
            
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        print(f"Found {len(results)} items for {duration_category}")
        
        cursor.close()
        return results
        
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        db_manager._put_connection(conn)

# Test each category
for category in ['id', 'spots', 'short_form', 'long_form']:
    print(f"\nTesting {category}:")
    results = get_available_content_simple(category)
    if results:
        print(f"  First item: {results[0]['content_title'][:30]}...")