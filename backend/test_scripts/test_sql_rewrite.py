#!/usr/bin/env python3
"""Test rewriting the SQL query to avoid parameter format mixing"""

from datetime import datetime, timedelta
from database_postgres import PostgreSQLDatabaseManager
db_manager = PostgreSQLDatabaseManager()
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_available_content_fixed(duration_category, exclude_ids=None, ignore_delays=False, schedule_date=None):
    """Fixed version that avoids mixing parameter formats"""
    
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        
        # Get replay delay configuration
        delay_config = {
            'id': {'base': 9, 'additional': 2},
            'spots': {'base': 12, 'additional': 3},
            'short_form': {'base': 24, 'additional': 12},
            'long_form': {'base': 48, 'additional': 24}
        }
        
        base_delay = delay_config.get(duration_category, {}).get('base', 0)
        additional_delay = delay_config.get(duration_category, {}).get('additional', 0)
        
        # Calculate dates in Python to avoid INTERVAL in SQL
        if schedule_date:
            try:
                compare_date = datetime.strptime(schedule_date, '%Y-%m-%d')
            except ValueError:
                compare_date = datetime.now()
        else:
            compare_date = datetime.now()
            
        # Pre-calculate the default expiry date (1 year from compare_date)
        default_expiry_date = compare_date + timedelta(days=365)
        epoch_start = datetime(1970, 1, 1)
        
        # Build query without INTERVAL literals
        query = """
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
                COALESCE(sm.content_expiry_date, %(default_expiry_date)s::timestamp) as content_expiry_date,
                -- Calculate required delay based on total airings
                (%(base_delay)s + (COALESCE(sm.total_airings, 0) * %(additional_delay)s)) as required_delay_hours,
                -- Calculate hours since last scheduled
                EXTRACT(EPOCH FROM (%(compare_date)s::timestamp - COALESCE(sm.last_scheduled_date, %(epoch_start)s::timestamp))) / 3600 as hours_since_last_scheduled
            FROM assets a
            JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE 
                a.analysis_completed = TRUE
                AND a.duration_category = %(duration_category)s
                AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                -- Filter out expired content
                AND COALESCE(sm.content_expiry_date, %(default_expiry_date)s::timestamp) > %(compare_date)s::timestamp
                AND NOT (i.file_path LIKE %(fill_pattern)s)
        """
        
        # Add replay delay check if not ignoring delays
        if not ignore_delays:
            query += """
                AND (
                    sm.last_scheduled_date IS NULL 
                    OR EXTRACT(EPOCH FROM (%(compare_date)s::timestamp - sm.last_scheduled_date)) / 3600 >= (%(base_delay)s + (COALESCE(sm.total_airings, 0) * %(additional_delay)s))
                )
            """
            
        query += """
            AND NOT EXISTS (
                SELECT 1 FROM scheduled_items si
                WHERE si.asset_id = a.id
                    AND si.available_for_scheduling = FALSE
            )
        """
        
        params = {
            'base_delay': base_delay,
            'additional_delay': additional_delay,
            'duration_category': duration_category,
            'fill_pattern': '%FILL%',
            'compare_date': compare_date,
            'default_expiry_date': default_expiry_date,
            'epoch_start': epoch_start
        }
        
        # Handle exclude_ids
        if exclude_ids and len(exclude_ids) > 0:
            # Use positional parameters for the array
            placeholders = ','.join(['%s'] * len(exclude_ids))
            query += f" AND a.id NOT IN ({placeholders})"
            
            # Execute with mixed parameters
            cursor.execute(query, [params[k] for k in ['base_delay', 'additional_delay', 'duration_category', 
                                                        'fill_pattern', 'compare_date', 'default_expiry_date', 
                                                        'epoch_start']] + list(exclude_ids))
        else:
            cursor.execute(query, params)
            
        results = cursor.fetchall()
        
        logger.info(f"Found {len(results)} items for {duration_category} (ignore_delays={ignore_delays})")
        
        cursor.close()
        return results
        
    except Exception as e:
        logger.error(f"Error in get_available_content_fixed: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        db_manager._put_connection(conn)

# Test the function
for category in ['id', 'spots', 'short_form', 'long_form']:
    print(f"\nTesting {category}:")
    
    # Test with delays
    results = get_available_content_fixed(category, ignore_delays=False)
    print(f"  With delays: {len(results)} items")
    
    # Test without delays
    results = get_available_content_fixed(category, ignore_delays=True)
    print(f"  Without delays: {len(results)} items")
    
    if results:
        print(f"  First item: {results[0]['content_title'][:30]}...")