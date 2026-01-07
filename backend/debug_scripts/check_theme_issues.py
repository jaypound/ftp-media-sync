#!/usr/bin/env python3
"""
Script to analyze theme-based back-to-back prevention issues
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database_postgres import PostgreSQLDatabaseManager

def analyze_theme_distribution():
    """Analyze theme distribution in spots and IDs"""
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    conn = db._get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get theme distribution for spots and IDs
        cursor.execute("""
            SELECT 
                duration_category,
                theme,
                COUNT(*) as count,
                STRING_AGG(content_title, ', ' ORDER BY content_title) as titles
            FROM assets
            WHERE duration_category IN ('spots', 'id')
                AND theme IS NOT NULL
                AND theme != ''
            GROUP BY duration_category, theme
            ORDER BY duration_category, count DESC
        """)
        
        results = cursor.fetchall()
        
        print("\n=== THEME DISTRIBUTION FOR SPOTS AND IDs ===")
        current_category = None
        for row in results:
            if row['duration_category'] != current_category:
                current_category = row['duration_category']
                print(f"\n{current_category.upper()}:")
            print(f"  Theme: {row['theme']} (Count: {row['count']})")
            print(f"    Titles: {row['titles'][:100]}...")
            
        # Check for recent schedules with back-to-back same themes
        cursor.execute("""
            WITH scheduled_with_themes AS (
                SELECT 
                    si.id,
                    si.schedule_id,
                    si.sequence_number,
                    si.asset_id,
                    a.content_title,
                    a.duration_category,
                    a.theme,
                    s.air_date,
                    LAG(a.theme) OVER (PARTITION BY si.schedule_id ORDER BY si.sequence_number) as prev_theme,
                    LAG(a.duration_category) OVER (PARTITION BY si.schedule_id ORDER BY si.sequence_number) as prev_category
                FROM scheduled_items si
                JOIN assets a ON si.asset_id = a.id
                JOIN schedules s ON si.schedule_id = s.id
                WHERE s.air_date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY s.air_date DESC, si.sequence_number
            )
            SELECT 
                air_date,
                sequence_number,
                content_title,
                duration_category,
                theme,
                prev_theme,
                prev_category
            FROM scheduled_with_themes
            WHERE theme IS NOT NULL 
                AND prev_theme IS NOT NULL
                AND theme = prev_theme
                AND duration_category IN ('spots', 'id')
                AND prev_category IN ('spots', 'id')
            ORDER BY air_date DESC, sequence_number
            LIMIT 20
        """)
        
        violations = cursor.fetchall()
        
        print("\n=== RECENT THEME CONFLICTS (Back-to-Back Same Themes) ===")
        if violations:
            for v in violations:
                print(f"\nDate: {v['air_date']}, Sequence: {v['sequence_number']}")
                print(f"  Previous: {v['prev_category']} - Theme: {v['prev_theme']}")
                print(f"  Current:  {v['duration_category']} - Theme: {v['theme']}")
                print(f"  Title: {v['content_title']}")
        else:
            print("No theme conflicts found in recent schedules")
            
        # Check if themes are populated for spots/IDs
        cursor.execute("""
            SELECT 
                duration_category,
                COUNT(*) as total,
                COUNT(CASE WHEN theme IS NOT NULL AND theme != '' THEN 1 END) as with_theme,
                COUNT(CASE WHEN theme IS NULL OR theme = '' THEN 1 END) as without_theme
            FROM assets
            WHERE duration_category IN ('spots', 'id')
            GROUP BY duration_category
        """)
        
        theme_coverage = cursor.fetchall()
        
        print("\n=== THEME COVERAGE FOR SPOTS AND IDs ===")
        for row in theme_coverage:
            percent_with_theme = (row['with_theme'] / row['total'] * 100) if row['total'] > 0 else 0
            print(f"\n{row['duration_category'].upper()}:")
            print(f"  Total: {row['total']}")
            print(f"  With Theme: {row['with_theme']} ({percent_with_theme:.1f}%)")
            print(f"  Without Theme: {row['without_theme']}")
            
    except Exception as e:
        logger.error(f"Error analyzing themes: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        db._put_connection(conn)
        db.disconnect()

if __name__ == "__main__":
    analyze_theme_distribution()