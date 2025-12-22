#!/usr/bin/env python3
"""Check how many holiday greetings we have"""

import os
os.environ['USE_POSTGRESQL'] = 'true'

from database import db_manager
from datetime import datetime, timedelta
import pytz

db_manager.connect()
conn = db_manager._get_connection()
cursor = conn.cursor()

eastern = pytz.timezone('US/Eastern')
# Check for Dec 27, 2025 (last day of the schedule)
end_date = datetime(2025, 12, 27, tzinfo=eastern)

cursor.execute("""
    SELECT COUNT(DISTINCT a.id)
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
    AND a.duration_category = 'spots'
    AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
    AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
""", (end_date,))

count = cursor.fetchone()['count']
print(f"Available holiday greetings for Dec 21-27, 2025: {count}")
print(f"Slots needed (7 days x 4 per day): {7 * 4}")

if count < 7 * 4:
    print(f"\nWARNING: Not enough unique greetings! Each greeting would need to appear {(7 * 4) / count:.1f} times on average")

# Check which one is available
cursor.execute("""
    SELECT i.file_name, sm.content_expiry_date
    FROM assets a
    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE i.file_name ILIKE '%%holiday%%greeting%%'
    AND a.duration_category = 'spots'
    AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
    AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
""", (end_date,))

print("\nAvailable greetings:")
for row in cursor.fetchall():
    print(f"  {row['file_name']} - Expires: {row['content_expiry_date']}")

cursor.close()
db_manager._put_connection(conn)