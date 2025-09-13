#!/usr/bin/env python3
"""
Check content inventory to debug scheduling issues
"""

import logging
from datetime import datetime
from database_postgres import PostgreSQLDatabaseManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

def check_content_inventory():
    """Check content inventory and replay delays"""
    db_manager = PostgreSQLDatabaseManager()
    db_manager.initialize()  # Initialize the connection pool
    conn = db_manager._get_connection()
    
    try:
        cursor = conn.cursor()
        
        # 1. Check total content by category
        print("\n=== CONTENT INVENTORY BY CATEGORY ===")
        cursor.execute("""
            SELECT 
                a.duration_category,
                COUNT(*) as total_count,
                COUNT(CASE WHEN sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP THEN 1 END) as active_count,
                COUNT(CASE WHEN sm.last_scheduled_date IS NOT NULL THEN 1 END) as scheduled_count
            FROM assets a
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE a.duration_category IS NOT NULL
            GROUP BY a.duration_category
            ORDER BY a.duration_category
        """)
        
        results = cursor.fetchall()
        print(f"{'Category':12} | {'Total':>6} | {'Active':>6} | {'Ever Scheduled':>14}")
        print("-" * 50)
        for row in results:
            print(f"{row['duration_category']:12} | {row['total_count']:6} | {row['active_count']:6} | {row['scheduled_count']:14}")
        
        # 2. Check replay delays from config
        print("\n=== REPLAY DELAY CONFIGURATION ===")
        cursor.execute("""
            SELECT category, base_delay_hours, additional_delay_per_airing
            FROM scheduling_config
            ORDER BY category
        """)
        
        delays = cursor.fetchall()
        for delay in delays:
            print(f"{delay['category']:12} - Base: {delay['base_delay_hours']:3}h, Additional: {delay['additional_delay_per_airing']:3}h per airing")
        
        # 3. Check content that's been scheduled recently
        print("\n=== RECENTLY SCHEDULED CONTENT (Last 7 days) ===")
        cursor.execute("""
            SELECT 
                a.duration_category,
                COUNT(DISTINCT a.id) as unique_assets,
                COUNT(*) as total_airings,
                AVG(sm.total_airings) as avg_airings_per_asset
            FROM assets a
            JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE sm.last_scheduled_date > CURRENT_TIMESTAMP - INTERVAL '7 days'
            GROUP BY a.duration_category
            ORDER BY a.duration_category
        """)
        
        results = cursor.fetchall()
        print(f"{'Category':12} | {'Unique Assets':>13} | {'Total Airings':>13} | {'Avg Airings':>11}")
        print("-" * 60)
        for row in results:
            print(f"{row['duration_category']:12} | {row['unique_assets']:13} | {row['total_airings']:13} | {row['avg_airings_per_asset']:11.1f}")
        
        # 4. Check content availability for each category with current delays
        print("\n=== CONTENT AVAILABLE WITH CURRENT DELAYS ===")
        
        # Get current timestamp for comparison
        now = datetime.now()
        
        for category in ['id', 'spots', 'short_form', 'long_form']:
            # Get delay config for this category
            cursor.execute("""
                SELECT base_delay_hours, additional_delay_per_airing
                FROM scheduling_config
                WHERE category = %s
            """, (category,))
            
            delay_config = cursor.fetchone()
            if delay_config:
                base_delay = delay_config['base_delay_hours']
                additional_delay = delay_config['additional_delay_per_airing']
                
                # Check how many items are available with current delays
                cursor.execute("""
                    SELECT COUNT(*) as available_count
                    FROM assets a
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE a.duration_category = %s
                      AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
                      AND (
                          sm.last_scheduled_date IS NULL 
                          OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sm.last_scheduled_date)) / 3600 >= 
                             (%s + (COALESCE(sm.total_airings, 0) * %s))
                      )
                """, (category, base_delay, additional_delay))
                
                result = cursor.fetchone()
                available = result['available_count'] if result else 0
                
                print(f"{category:12} - {available:3} items available (base: {base_delay}h, add: {additional_delay}h)")
        
        cursor.close()
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db_manager._put_connection(conn)

if __name__ == "__main__":
    check_content_inventory()