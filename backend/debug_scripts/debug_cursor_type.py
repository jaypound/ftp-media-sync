#!/usr/bin/env python3
"""Debug cursor type issue"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager

db_manager.connect()
conn = db_manager._get_connection()
cursor = conn.cursor()

# Check what type of cursor this is
print(f"Cursor type: {type(cursor)}")
print(f"Cursor class: {cursor.__class__.__name__}")

# Try a simple query
cursor.execute("SELECT 1 as test_col")
result = cursor.fetchone()
print(f"Result type: {type(result)}")
print(f"Result: {result}")

# Try accessing by index
try:
    print(f"Result[0]: {result[0]}")
except Exception as e:
    print(f"Error accessing by index: {e}")

# Try accessing as dict
try:
    print(f"Result['test_col']: {result['test_col']}")
except Exception as e:
    print(f"Error accessing as dict: {e}")

cursor.close()
db_manager._put_connection(conn)