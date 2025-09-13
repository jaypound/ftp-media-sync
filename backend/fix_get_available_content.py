#!/usr/bin/env python3
"""Implement a fixed version of get_available_content that works with psycopg2"""

from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def create_fixed_query(duration_category, base_delay, additional_delay, compare_date, 
                      default_expiry_date, epoch_start, exclude_ids=None, ignore_delays=False):
    """Create the SQL query with proper parameter handling"""
    
    # Build base query
    query_parts = ["""
        SELECT 
            a.id as asset_id,
            a.content_title,
            a.duration_seconds,
            a.duration_category,
            a.engagement_score,
            i.file_path,
            i.encoded_date,
            sm.last_scheduled_date,
            sm.total_airings,
            COALESCE(sm.content_expiry_date, %s::timestamp) as content_expiry_date,
            (%s + (COALESCE(sm.total_airings, 0) * %s)) as required_delay_hours,
            EXTRACT(EPOCH FROM (%s::timestamp - COALESCE(sm.last_scheduled_date, %s::timestamp))) / 3600 as hours_since_last_scheduled
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE 
            a.analysis_completed = TRUE
            AND a.duration_category = %s
            AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
            AND COALESCE(sm.content_expiry_date, %s::timestamp) > %s::timestamp
            AND NOT (i.file_path LIKE %s)
    """]
    
    # Start with base parameters
    params = [
        default_expiry_date,  # for COALESCE in SELECT
        base_delay,           # for required_delay_hours calculation
        additional_delay,     # for required_delay_hours calculation
        compare_date,         # for hours_since_last_scheduled
        epoch_start,          # for hours_since_last_scheduled fallback
        duration_category,    # for WHERE clause
        default_expiry_date,  # for expiry check in WHERE
        compare_date,         # for expiry comparison
        '%FILL%'             # for fill pattern
    ]
    
    # Add replay delay check if not ignoring
    if not ignore_delays:
        query_parts.append("""
            AND (
                sm.last_scheduled_date IS NULL 
                OR EXTRACT(EPOCH FROM (%s::timestamp - sm.last_scheduled_date)) / 3600 >= (%s + (COALESCE(sm.total_airings, 0) * %s))
            )
        """)
        params.extend([compare_date, base_delay, additional_delay])
    
    # Add existence check
    query_parts.append("""
        AND NOT EXISTS (
            SELECT 1 FROM scheduled_items si
            WHERE si.asset_id = a.id
                AND si.available_for_scheduling = FALSE
        )
    """)
    
    # Handle exclude_ids
    if exclude_ids and len(exclude_ids) > 0:
        placeholders = ','.join(['%s'] * len(exclude_ids))
        query_parts.append(f" AND a.id NOT IN ({placeholders})")
        params.extend(exclude_ids)
    
    # Add ordering
    query_parts.append("""
        ORDER BY 
            (
                CASE 
                    WHEN i.encoded_date IS NULL THEN 0
                    WHEN i.encoded_date >= %s::date THEN 100
                    WHEN i.encoded_date >= (%s::date - INTERVAL '1 days') THEN 90
                    WHEN i.encoded_date >= (%s::date - INTERVAL '3 days') THEN 80
                    WHEN i.encoded_date >= (%s::date - INTERVAL '7 days') THEN 60
                    WHEN i.encoded_date >= (%s::date - INTERVAL '14 days') THEN 40
                    WHEN i.encoded_date >= (%s::date - INTERVAL '30 days') THEN 20
                    ELSE 10
                END * 0.35
                
                + COALESCE(a.engagement_score, 50) * 0.25
                
                + CASE
                    WHEN sm.total_airings IS NULL OR sm.total_airings = 0 THEN 100
                    WHEN sm.total_airings <= 2 THEN 80
                    WHEN sm.total_airings <= 5 THEN 60
                    WHEN sm.total_airings <= 10 THEN 40
                    WHEN sm.total_airings <= 20 THEN 20
                    ELSE 10
                END * 0.20
                
                + CASE
                    WHEN sm.last_scheduled_date IS NULL THEN 100
                    WHEN EXTRACT(EPOCH FROM (%s::timestamp - sm.last_scheduled_date)) / 3600 >= 24 THEN 100
                    WHEN EXTRACT(EPOCH FROM (%s::timestamp - sm.last_scheduled_date)) / 3600 >= 12 THEN 80
                    WHEN EXTRACT(EPOCH FROM (%s::timestamp - sm.last_scheduled_date)) / 3600 >= 6 THEN 60
                    WHEN EXTRACT(EPOCH FROM (%s::timestamp - sm.last_scheduled_date)) / 3600 >= 3 THEN 40
                    WHEN EXTRACT(EPOCH FROM (%s::timestamp - sm.last_scheduled_date)) / 3600 >= 1 THEN 20
                    ELSE 0
                END * 0.20
            ) DESC,
            
            sm.last_scheduled_date ASC NULLS FIRST,
            sm.total_airings ASC NULLS FIRST,
            i.encoded_date DESC NULLS LAST
        LIMIT 100
    """)
    
    # Add date parameters for ORDER BY
    params.extend([
        compare_date,  # for date comparisons in freshness score
        compare_date,
        compare_date,
        compare_date,
        compare_date,
        compare_date,
        compare_date,  # for time since last play calculations
        compare_date,
        compare_date,
        compare_date,
        compare_date
    ])
    
    return ''.join(query_parts), params


# Create the fixed method to patch into scheduler_postgres.py
def get_available_content_fixed(self, duration_category, exclude_ids=None, ignore_delays=False, schedule_date=None):
    """Fixed version of get_available_content that avoids parameter format mixing"""
    from database_postgres import PostgreSQLDatabaseManager
    db_manager = PostgreSQLDatabaseManager()
    
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        
        # Get configuration for this category
        delay_config = self._get_delay_config(duration_category)
        base_delay = delay_config['base_delay']
        additional_delay = delay_config['additional_delay']
        
        # Calculate dates in Python
        if schedule_date:
            try:
                compare_date = datetime.strptime(schedule_date, '%Y-%m-%d')
            except ValueError:
                logger.warning(f"Invalid schedule_date format: {schedule_date}, using current time")
                compare_date = datetime.now()
        else:
            compare_date = datetime.now()
            
        # Pre-calculate dates to avoid INTERVAL in SQL
        default_expiry_date = compare_date + timedelta(days=365)
        epoch_start = datetime(1970, 1, 1)
        
        # Create query and parameters
        query, params = create_fixed_query(
            duration_category, base_delay, additional_delay,
            compare_date, default_expiry_date, epoch_start,
            exclude_ids, ignore_delays
        )
        
        # Execute query
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Process results
        content_list = []
        for row in results:
            content_list.append({
                'asset_id': row['asset_id'],
                'content_title': row['content_title'],
                'duration_seconds': row['duration_seconds'],
                'duration_category': row['duration_category'],
                'engagement_score': row['engagement_score'],
                'file_path': row['file_path'],
                'encoded_date': row['encoded_date'],
                'last_scheduled_date': row['last_scheduled_date'],
                'total_airings': row['total_airings'],
                'content_expiry_date': row['content_expiry_date'],
                'required_delay_hours': row['required_delay_hours'],
                'hours_since_last_scheduled': row['hours_since_last_scheduled']
            })
            
        logger.info(f"Retrieved {len(content_list)} available items for {duration_category} (ignore_delays={ignore_delays})")
        
        cursor.close()
        return content_list
        
    except Exception as e:
        logger.error(f"Error retrieving available content: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        db_manager._put_connection(conn)


# Show the implementation
print("Fixed get_available_content method created.")
print("\nKey changes:")
print("1. Pre-calculate dates in Python (default_expiry_date, epoch_start)")
print("2. Use only positional parameters (%s) throughout the query")
print("3. Build parameters list in the correct order")
print("4. Avoid mixing %(name)s style with SQL INTERVAL literals")
print("\nThis should resolve the 'argument formats can't be mixed' error.")