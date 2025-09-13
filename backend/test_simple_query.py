#!/usr/bin/env python3
"""Test simple query to debug SQL issues"""

from database_postgres import db_manager

conn = db_manager._get_connection()

try:
    cursor = conn.cursor()
    
    # Test 1: Simple count with no parameters
    print("Test 1: Simple count")
    cursor.execute("SELECT COUNT(*) FROM assets WHERE duration_category = 'id'")
    result = cursor.fetchone()
    print(f"  IDs in database: {result[0]}")
    
    # Test 2: With named parameters 
    print("\nTest 2: Named parameters")
    cursor.execute(
        "SELECT COUNT(*) FROM assets WHERE duration_category = %(cat)s",
        {'cat': 'spots'}
    )
    result = cursor.fetchone()
    print(f"  Spots in database: {result[0]}")
    
    # Test 3: Date with INTERVAL
    print("\nTest 3: Date with INTERVAL")
    from datetime import datetime
    cursor.execute("""
        SELECT COUNT(*) FROM assets a
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.duration_category = %(cat)s
          AND COALESCE(sm.content_expiry_date, %(dt)s::timestamp + INTERVAL '1 year') > %(dt)s::timestamp
    """, {'cat': 'long_form', 'dt': datetime.now()})
    result = cursor.fetchone()
    print(f"  Long form available: {result[0]}")
    
    cursor.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db_manager._put_connection(conn)