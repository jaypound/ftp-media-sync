"""
Schedule Analysis Report Generator
Generates comprehensive analysis of scheduled content
"""

import logging
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ScheduleAnalysisReport:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def generate(self, schedule_id: int) -> Dict[str, Any]:
        """Generate schedule analysis report data"""
        try:
            # Get schedule info
            schedule_info = self._get_schedule_info(schedule_id)
            if not schedule_info:
                raise ValueError(f"Schedule {schedule_id} not found")
            
            # Generate report sections
            report_data = {
                'schedule_id': schedule_id,
                'generated_at': datetime.now().isoformat(),
                'overview': self._get_overview(schedule_id, schedule_info),
                'category_distribution': self._get_category_distribution(schedule_id),
                'type_distribution': self._get_type_distribution(schedule_id),
                'most_scheduled': self._get_most_scheduled(schedule_id),
                'rotation_pattern': self._get_rotation_pattern(schedule_id),
                'time_slots': self._get_time_slot_analysis(schedule_id),
                'not_scheduled': self._get_not_scheduled(schedule_id, schedule_info['air_date'])
            }
            
            return report_data
            
        except Exception as e:
            logger.error(f"Error generating schedule analysis report: {str(e)}")
            raise
    
    def _get_schedule_info(self, schedule_id: int) -> Dict[str, Any]:
        """Get basic schedule information"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    s.schedule_name as name,
                    s.air_date,
                    s.created_date as created_at,
                    COUNT(si.id) as total_items,
                    COALESCE(s.total_duration_seconds, SUM(si.scheduled_duration_seconds)) as total_duration_seconds
                FROM schedules s
                LEFT JOIN scheduled_items si ON s.id = si.schedule_id
                WHERE s.id = %s
                GROUP BY s.id, s.schedule_name, s.air_date, s.created_date, s.total_duration_seconds
            """, (schedule_id,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return {
                    'name': result['name'],
                    'air_date': result['air_date'],
                    'created_at': result['created_at'],
                    'total_items': result['total_items'],
                    'total_duration_seconds': float(result['total_duration_seconds']) if result['total_duration_seconds'] else 0
                }
            return None
        finally:
            self.db._put_connection(conn)
    
    def _get_overview(self, schedule_id: int, schedule_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get schedule overview statistics"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get unique content count
            cursor.execute("""
                SELECT COUNT(DISTINCT asset_id) as unique_content
                FROM scheduled_items
                WHERE schedule_id = %s
            """, (schedule_id,))
            
            unique_count = cursor.fetchone()['unique_content']
            cursor.close()
            
            return {
                'schedule_name': schedule_info['name'],
                'air_date': schedule_info['air_date'].strftime('%Y-%m-%d'),
                'created_at': schedule_info['created_at'].strftime('%Y-%m-%d %H:%M') if schedule_info['created_at'] else 'Unknown',
                'total_items': schedule_info['total_items'],
                'unique_content': unique_count,
                'total_hours': float(schedule_info['total_duration_seconds']) / 3600 if schedule_info['total_duration_seconds'] else 0
            }
        finally:
            self.db._put_connection(conn)
    
    def _get_category_distribution(self, schedule_id: int) -> List[Dict[str, Any]]:
        """Get distribution by duration category"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    a.duration_category as category,
                    COUNT(DISTINCT si.id) as count,
                    COUNT(DISTINCT a.id) as unique_content,
                    SUM(si.scheduled_duration_seconds) / 3600.0 as total_hours,
                    AVG(si.scheduled_duration_seconds) / 60.0 as avg_minutes
                FROM scheduled_items si
                JOIN assets a ON si.asset_id = a.id
                WHERE si.schedule_id = %s
                GROUP BY a.duration_category
                ORDER BY total_hours DESC
            """, (schedule_id,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'category': row['category'] or 'unknown',
                    'count': int(row['count']),
                    'unique_content': int(row['unique_content']),
                    'total_hours': float(row['total_hours']) if row['total_hours'] else 0,
                    'avg_minutes': float(row['avg_minutes']) if row['avg_minutes'] else 0
                })
            
            cursor.close()
            return results
        finally:
            self.db._put_connection(conn)
    
    def _get_type_distribution(self, schedule_id: int) -> List[Dict[str, Any]]:
        """Get distribution by content type"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    a.content_type as type,
                    COUNT(DISTINCT si.id) as count,
                    COUNT(DISTINCT a.id) as unique_content,
                    SUM(si.scheduled_duration_seconds) / 3600.0 as total_hours
                FROM scheduled_items si
                JOIN assets a ON si.asset_id = a.id
                WHERE si.schedule_id = %s
                GROUP BY a.content_type
                ORDER BY count DESC
            """, (schedule_id,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'type': row['type'] or 'unknown',
                    'count': int(row['count']),
                    'unique_content': int(row['unique_content']),
                    'total_hours': float(row['total_hours']) if row['total_hours'] else 0
                })
            
            cursor.close()
            return results
        finally:
            self.db._put_connection(conn)
    
    def _get_most_scheduled(self, schedule_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most frequently scheduled content"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    a.content_title as title,
                    a.content_type as type,
                    a.duration_category as category,
                    COUNT(si.id) as count,
                    a.duration_seconds / 60.0 as duration_minutes
                FROM scheduled_items si
                JOIN assets a ON si.asset_id = a.id
                WHERE si.schedule_id = %s
                GROUP BY a.id, a.content_title, a.content_type, 
                         a.duration_category, a.duration_seconds
                ORDER BY count DESC
                LIMIT %s
            """, (schedule_id, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'title': row['title'],
                    'type': row['type'],
                    'category': row['category'],
                    'count': int(row['count']),
                    'duration_minutes': float(row['duration_minutes']) if row['duration_minutes'] else 0
                })
            
            cursor.close()
            return results
        finally:
            self.db._put_connection(conn)
    
    def _get_rotation_pattern(self, schedule_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Analyze the rotation pattern"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    si.sequence_number as position,
                    a.duration_category as category
                FROM scheduled_items si
                JOIN assets a ON si.asset_id = a.id
                WHERE si.schedule_id = %s
                ORDER BY si.sequence_number
                LIMIT %s
            """, (schedule_id, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'position': row['position'],
                    'category': row['category']
                })
            
            cursor.close()
            return results
        finally:
            self.db._put_connection(conn)
    
    def _get_time_slot_analysis(self, schedule_id: int) -> Dict[str, Any]:
        """Analyze content by time slots"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    EXTRACT(HOUR FROM si.scheduled_start_time) as hour,
                    a.duration_category as category,
                    COUNT(*) as count
                FROM scheduled_items si
                JOIN assets a ON si.asset_id = a.id
                WHERE si.schedule_id = %s
                GROUP BY hour, a.duration_category
                ORDER BY hour, count DESC
            """, (schedule_id,))
            
            # Group by hour
            hour_data = defaultdict(list)
            for row in cursor.fetchall():
                hour = int(row['hour'])
                hour_data[hour].append({
                    'category': row['category'],
                    'count': row['count']
                })
            
            cursor.close()
            return dict(hour_data)
        finally:
            self.db._put_connection(conn)
    
    def _get_not_scheduled(self, schedule_id: int, air_date, limit: int = 20) -> List[Dict[str, Any]]:
        """Find available content that wasn't scheduled"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    a.content_title as title,
                    a.content_type as type,
                    a.duration_category as category,
                    a.duration_seconds / 60.0 as duration_minutes,
                    sm.last_scheduled_date,
                    sm.total_airings
                FROM assets a
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE a.analysis_completed = TRUE
                AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                AND COALESCE(sm.content_expiry_date, %s::date + INTERVAL '1 year') > %s::date
                AND a.id NOT IN (
                    SELECT DISTINCT asset_id 
                    FROM scheduled_items 
                    WHERE schedule_id = %s
                )
                ORDER BY 
                    sm.last_scheduled_date ASC NULLS FIRST,
                    a.duration_category,
                    a.content_title
                LIMIT %s
            """, (air_date, air_date, schedule_id, limit))
            
            results = []
            for row in cursor.fetchall():
                # Determine why it wasn't scheduled
                reason = 'Not selected in rotation'
                if row['category'] not in ['id', 'spots', 'short_form', 'long_form']:
                    reason = f'Invalid category: {row["category"]}'
                elif row['last_scheduled_date']:
                    # Could add logic to check replay delays
                    reason = 'Recently aired or rotation timing'
                
                results.append({
                    'title': row['title'],
                    'type': row['type'],
                    'category': row['category'],
                    'duration_minutes': float(row['duration_minutes']) if row['duration_minutes'] else 0,
                    'last_scheduled': row['last_scheduled_date'].strftime('%Y-%m-%d') 
                                     if row['last_scheduled_date'] else None,
                    'total_airings': int(row['total_airings']) if row['total_airings'] else 0,
                    'reason': reason
                })
            
            cursor.close()
            return results
        finally:
            self.db._put_connection(conn)