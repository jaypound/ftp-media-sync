#!/usr/bin/env python3
"""Debug why reset condition isn't triggering"""

from database import db_manager
from datetime import datetime, timedelta

db_manager.connect()
conn = db_manager._get_connection()
cursor = conn.cursor()

# Check short_form content
schedule_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

print("Checking SHORT_FORM content...")

# Total in category
cursor.execute("""
    SELECT COUNT(*) as total
    FROM assets a
    WHERE a.duration_category = 'short_form'
      AND a.analysis_completed = TRUE
""")
total = cursor.fetchone()['total']
print(f"Total short_form assets (analyzed): {total}")

# Non-expired
cursor.execute("""
    SELECT COUNT(*) as total
    FROM assets a
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE a.duration_category = 'short_form'
      AND a.analysis_completed = TRUE
      AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > %s)
""", (schedule_date,))
non_expired = cursor.fetchone()['total']
print(f"Non-expired short_form assets: {non_expired}")

# Get actual IDs
cursor.execute("""
    SELECT a.id, a.content_title, sm.content_expiry_date
    FROM assets a
    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
    WHERE a.duration_category = 'short_form'
      AND a.analysis_completed = TRUE
    ORDER BY a.id
""")

print("\nShort form content details:")
for row in cursor:
    expiry = row['content_expiry_date']
    if expiry and expiry < datetime.strptime(schedule_date, '%Y-%m-%d'):
        status = "EXPIRED"
    else:
        status = "Available"
    print(f"  ID {row['id']}: {row['content_title'][:40]:<40} - {status}")

cursor.close()
db_manager._put_connection(conn)

print(f"\nThe reset condition requires:")
print(f"1. All {non_expired} non-expired items to be in exclude_ids")
print(f"2. But only 14 are being excluded")
print(f"This suggests some content is being filtered out for other reasons")