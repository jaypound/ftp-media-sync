#!/usr/bin/env python3
"""Fixed get_available_content method for PostgreSQLScheduler"""

from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_available_content(self, duration_category, exclude_ids=None, ignore_delays=False, 
                         schedule_date=None, delay_reduction_factor=1.0):
    """
    Retrieve available content for scheduling based on various criteria.
    
    This method considers:
    - Duration category (or content type)
    - Analysis completion status
    - Expiration dates
    - Replay delays (can be reduced or ignored)
    - Already scheduled items
    - Multi-factor scoring for optimal content selection
    
    Args:
        duration_category: Category to filter by (id, spots, short_form, long_form)
        exclude_ids: List of asset IDs to exclude
        ignore_delays: If True, ignore replay delay restrictions
        schedule_date: Date being scheduled (YYYY-MM-DD format)
        delay_reduction_factor: Factor to reduce delays (0.0 to 1.0)
    
    Returns:
        List of content items sorted by relevance score
    """
    from database_postgres import PostgreSQLDatabaseManager
    db_manager = PostgreSQLDatabaseManager()
    
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        
        # Calculate dates in Python to avoid INTERVAL issues
        if schedule_date:
            try:
                compare_date = datetime.strptime(schedule_date, '%Y-%m-%d')
            except ValueError:
                logger.warning(f"Invalid schedule_date format: {schedule_date}, using current time")
                compare_date = datetime.now()
        else:
            compare_date = datetime.now()
        
        # Pre-calculate all date values we'll need
        default_expiry_date = compare_date + timedelta(days=365)
        epoch_start = datetime(1970, 1, 1)
        date_minus_1 = compare_date - timedelta(days=1)
        date_minus_3 = compare_date - timedelta(days=3)
        date_minus_7 = compare_date - timedelta(days=7)
        date_minus_14 = compare_date - timedelta(days=14)
        date_minus_30 = compare_date - timedelta(days=30)
        
        # Get delay configuration
        base_delay = 0
        additional_delay = 0
        
        if not ignore_delays:
            if delay_reduction_factor == 0.0:
                base_delay = 0
                additional_delay = 0
                if delay_reduction_factor < 1.0:
                    logger.info(f"Ignoring delays for {duration_category} (reduction factor would have been {delay_reduction_factor})")
            else:
                try:
                    from config_manager import ConfigManager
                    config_mgr = ConfigManager()
                    scheduling_config = config_mgr.get_scheduling_settings()
                    replay_delays = scheduling_config.get('replay_delays', {})
                    additional_delays = scheduling_config.get('additional_delay_per_airing', {})
                    
                    base_delay = replay_delays.get(duration_category, 24)
                    additional_delay = additional_delays.get(duration_category, 2)
                    
                    if delay_reduction_factor < 1.0:
                        original_base = base_delay
                        original_additional = additional_delay
                        base_delay = base_delay * delay_reduction_factor
                        additional_delay = additional_delay * delay_reduction_factor
                        logger.info(f"Reducing delays for {duration_category} by factor {delay_reduction_factor}: "
                                  f"base {original_base}h -> {base_delay}h, additional {original_additional}h -> {additional_delay}h")
                except Exception as e:
                    logger.warning(f"Could not load replay delay config, using defaults: {e}")
        
        # Build query using only positional parameters
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
                COALESCE(sm.content_expiry_date, %s) as content_expiry_date,
                (%s + (COALESCE(sm.total_airings, 0) * %s)) as required_delay_hours,
                EXTRACT(EPOCH FROM (%s - COALESCE(sm.last_scheduled_date, %s))) / 3600 as hours_since_last_scheduled
            FROM assets a
            JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE 
                a.analysis_completed = TRUE
                AND a.duration_category = %s
                AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                AND COALESCE(sm.content_expiry_date, %s) > %s
                AND NOT (i.file_path LIKE %s)
        """]
        
        # Parameters for the main query
        params = [
            default_expiry_date,  # for COALESCE in SELECT
            base_delay,           # for required_delay_hours
            additional_delay,     # for required_delay_hours
            compare_date,         # for hours_since_last_scheduled
            epoch_start,          # for hours_since_last_scheduled fallback
            duration_category,    # for WHERE clause
            default_expiry_date,  # for expiry check
            compare_date,         # for expiry comparison
            '%FILL%'             # for fill pattern
        ]
        
        # Add replay delay check if not ignoring
        if not ignore_delays:
            query_parts.append("""
                AND (
                    sm.last_scheduled_date IS NULL 
                    OR EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= (%s + (COALESCE(sm.total_airings, 0) * %s))
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
        
        # Add complex ordering with pre-calculated dates
        query_parts.append("""
            ORDER BY 
                (
                    CASE 
                        WHEN i.encoded_date IS NULL THEN 0
                        WHEN i.encoded_date >= %s THEN 100
                        WHEN i.encoded_date >= %s THEN 90
                        WHEN i.encoded_date >= %s THEN 80
                        WHEN i.encoded_date >= %s THEN 60
                        WHEN i.encoded_date >= %s THEN 40
                        WHEN i.encoded_date >= %s THEN 20
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
                        WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 24 THEN 100
                        WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 12 THEN 80
                        WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 6 THEN 60
                        WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 3 THEN 40
                        WHEN EXTRACT(EPOCH FROM (%s - sm.last_scheduled_date)) / 3600 >= 1 THEN 20
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
            compare_date,     # for freshness score comparisons
            date_minus_1,
            date_minus_3,
            date_minus_7,
            date_minus_14,
            date_minus_30,
            compare_date,     # for time since last play calculations
            compare_date,
            compare_date,
            compare_date,
            compare_date
        ])
        
        # Combine query parts
        query = ''.join(query_parts)
        
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
        
        logger.info(f"Retrieved {len(content_list)} available items for {duration_category} "
                   f"(ignore_delays={ignore_delays}, reduction_factor={delay_reduction_factor})")
        
        cursor.close()
        return content_list
        
    except Exception as e:
        logger.error(f"Error retrieving available content: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        db_manager._put_connection(conn)