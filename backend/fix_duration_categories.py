#!/usr/bin/env python3
"""
Fix duration categories for assets that have NULL or invalid values.
Uses the same logic as file_analyzer.py to categorize content based on duration.
"""

import logging
from datetime import datetime
from database_postgres import PostgreSQLDatabase

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_duration_category(duration_seconds: float) -> str:
    """Determine duration category based on seconds (same logic as file_analyzer.py)"""
    if duration_seconds < 16:
        return 'id'
    elif duration_seconds < 120:
        return 'spots'
    elif duration_seconds < 1200:
        return 'short_form'
    else:
        return 'long_form'

def fix_duration_categories():
    """Fix duration categories for all assets"""
    db = PostgreSQLDatabase()
    
    try:
        if not db.connected:
            db.connect()
        
        conn = db._get_connection()
        cursor = conn.cursor()
        
        # First, get count of assets with invalid duration categories
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM assets
            WHERE duration_category IS NULL 
            OR duration_category NOT IN ('id', 'spots', 'short_form', 'long_form')
        """)
        result = cursor.fetchone()
        invalid_count = result['count'] if result else 0
        
        logger.info(f"Found {invalid_count} assets with invalid duration categories")
        
        if invalid_count == 0:
            logger.info("No assets need fixing")
            return
        
        # Get all assets with invalid duration categories
        cursor.execute("""
            SELECT id, content_type, content_title, duration_seconds, duration_category
            FROM assets
            WHERE duration_category IS NULL 
            OR duration_category NOT IN ('id', 'spots', 'short_form', 'long_form')
            ORDER BY content_type, id
        """)
        
        assets_to_fix = cursor.fetchall()
        
        # Fix each asset
        fixed_count = 0
        for asset in assets_to_fix:
            asset_id = asset['id']
            duration_seconds = asset['duration_seconds'] or 0
            old_category = asset['duration_category']
            new_category = get_duration_category(duration_seconds)
            
            cursor.execute("""
                UPDATE assets
                SET duration_category = %s, updated_at = %s
                WHERE id = %s
            """, (new_category, datetime.utcnow(), asset_id))
            
            fixed_count += 1
            
            logger.info(f"Fixed asset {asset_id} ({asset['content_type']}): "
                       f"'{asset['content_title'][:50]}...' "
                       f"duration={duration_seconds}s, "
                       f"category: {old_category} -> {new_category}")
        
        conn.commit()
        cursor.close()
        
        logger.info(f"Successfully fixed {fixed_count} assets")
        
        # Show summary by content type
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                content_type,
                duration_category,
                COUNT(*) as count,
                AVG(duration_seconds) as avg_duration
            FROM assets
            GROUP BY content_type, duration_category
            ORDER BY content_type, duration_category
        """)
        
        results = cursor.fetchall()
        
        logger.info("\nSummary by content type and duration category:")
        logger.info("-" * 80)
        logger.info(f"{'Content Type':<15} {'Category':<15} {'Count':<10} {'Avg Duration':<15}")
        logger.info("-" * 80)
        
        for row in results:
            avg_duration = f"{row['avg_duration']:.1f}s" if row['avg_duration'] else "N/A"
            logger.info(f"{row['content_type']:<15} {row['duration_category']:<15} "
                       f"{row['count']:<10} {avg_duration:<15}")
        
        cursor.close()
        
    except Exception as e:
        logger.error(f"Error fixing duration categories: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        db._put_connection(conn)

if __name__ == "__main__":
    fix_duration_categories()