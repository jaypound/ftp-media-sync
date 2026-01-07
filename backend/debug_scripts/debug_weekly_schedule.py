#!/usr/bin/env python3
"""Debug weekly schedule replay analysis"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import db_manager
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_weekly_schedule(schedule_id):
    """Analyze replay patterns in a weekly schedule"""
    
    conn = db_manager._get_connection()
    try:
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get schedule items
        cursor.execute("""
            SELECT 
                si.asset_id,
                si.scheduled_start_time,
                a.content_title,
                a.duration_category,
                EXTRACT(EPOCH FROM si.scheduled_start_time) as start_seconds
            FROM scheduled_items si
            LEFT JOIN assets a ON si.asset_id = a.id
            WHERE si.schedule_id = %s
            ORDER BY si.scheduled_start_time
        """, (schedule_id,))
        
        items = cursor.fetchall()
        logger.info(f"Found {len(items)} items in schedule")
        
        # Count total plays per asset
        total_plays = defaultdict(int)
        asset_info = {}
        
        for item in items:
            if item['asset_id']:  # asset_id exists
                asset_id = item['asset_id']
                total_plays[asset_id] += 1
                if asset_id not in asset_info:
                    asset_info[asset_id] = {
                        'title': item['content_title'],
                        'category': item['duration_category']
                    }
        
        # Show top repeated content
        sorted_plays = sorted(total_plays.items(), key=lambda x: x[1], reverse=True)
        
        logger.info("\nTop 20 most repeated content:")
        for asset_id, count in sorted_plays[:20]:
            info = asset_info[asset_id]
            logger.info(f"  {count} plays: {info['title']} ({info['category']})")
        
        # Show distribution
        play_distribution = defaultdict(int)
        for count in total_plays.values():
            play_distribution[count] += 1
        
        logger.info("\nPlay count distribution:")
        for plays, content_count in sorted(play_distribution.items()):
            logger.info(f"  {content_count} items played {plays} time(s)")
        
        # Analyze by day
        logger.info("\nAnalyzing by day:")
        items_by_day = defaultdict(list)
        for item in items:
            if item['asset_id']:  # asset_id exists
                start_seconds = item['start_seconds']
                day = int(start_seconds // 86400)
                items_by_day[day].append(item)
        
        for day, day_items in sorted(items_by_day.items()):
            day_plays = defaultdict(int)
            for item in day_items:
                if item['asset_id']:
                    day_plays[item['asset_id']] += 1
            
            unique_content = len(day_plays)
            max_plays = max(day_plays.values()) if day_plays else 0
            avg_plays = sum(day_plays.values()) / len(day_plays) if day_plays else 0
            
            logger.info(f"  Day {day}: {len(day_items)} items, {unique_content} unique, max {max_plays} plays, avg {avg_plays:.1f} plays")
            
            # Show most repeated on this day
            if max_plays > 1:
                for asset_id, count in sorted(day_plays.items(), key=lambda x: x[1], reverse=True)[:5]:
                    if count > 1:
                        info = asset_info[asset_id]
                        logger.info(f"    - {count} plays: {info['title']}")
        
        cursor.close()
        
    finally:
        db_manager._put_connection(conn)

if __name__ == '__main__':
    db_manager.connect()
    try:
        # Use the weekly schedule ID 458
        analyze_weekly_schedule(458)
    finally:
        db_manager.disconnect()