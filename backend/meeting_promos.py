"""
Meeting Promos Management Module
Handles pre and post meeting promotional content scheduling
"""
import os
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class MeetingPromosManager:
    def __init__(self, db_manager):
        self.db = db_manager
        
    def get_settings(self) -> Dict:
        """Get current promo settings"""
        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT pre_meeting_enabled, post_meeting_enabled, 
                           pre_meeting_duration_limit, post_meeting_duration_limit,
                           updated_at, updated_by
                    FROM meeting_promo_settings
                    WHERE id = 1
                """)
                result = cursor.fetchone()
                return dict(result) if result else None
        finally:
            conn.close()
    
    def update_settings(self, pre_enabled: bool, post_enabled: bool, 
                       pre_limit: int = None, post_limit: int = None,
                       updated_by: str = None) -> bool:
        """Update promo settings"""
        conn = self.db._get_connection()
        try:
            with conn.cursor() as cursor:
                query_parts = []
                params = []
                
                query_parts.append("pre_meeting_enabled = %s")
                params.append(pre_enabled)
                
                query_parts.append("post_meeting_enabled = %s")
                params.append(post_enabled)
                
                if pre_limit is not None:
                    query_parts.append("pre_meeting_duration_limit = %s")
                    params.append(pre_limit)
                    
                if post_limit is not None:
                    query_parts.append("post_meeting_duration_limit = %s")
                    params.append(post_limit)
                    
                if updated_by:
                    query_parts.append("updated_by = %s")
                    params.append(updated_by)
                
                query = f"""
                    UPDATE meeting_promo_settings 
                    SET {', '.join(query_parts)}
                    WHERE id = 1
                """
                
                cursor.execute(query, params)
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating promo settings: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_promos(self, promo_type: str = None, active_only: bool = True,
                   include_expired: bool = False) -> List[Dict]:
        """Get meeting promos with optional filters"""
        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                conditions = []
                params = []
                
                if promo_type:
                    conditions.append("promo_type = %s")
                    params.append(promo_type)
                
                if active_only:
                    conditions.append("is_active = true")
                
                if not include_expired:
                    today = date.today()
                    conditions.append("(go_live_date IS NULL OR go_live_date <= %s)")
                    params.append(today)
                    conditions.append("(expiration_date IS NULL OR expiration_date >= %s)")
                    params.append(today)
                
                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                
                query = f"""
                    SELECT id, file_path, file_name, promo_type, duration_seconds,
                           go_live_date, expiration_date, is_active, sort_order,
                           created_at, updated_at, created_by, notes
                    FROM meeting_promos
                    {where_clause}
                    ORDER BY promo_type, sort_order, file_name
                """
                
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def add_promo(self, file_path: str, file_name: str, promo_type: str,
                  duration_seconds: int, go_live_date: date = None,
                  expiration_date: date = None, is_active: bool = True,
                  sort_order: int = 0, created_by: str = None,
                  notes: str = None) -> Optional[int]:
        """Add a new promo"""
        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO meeting_promos 
                    (file_path, file_name, promo_type, duration_seconds,
                     go_live_date, expiration_date, is_active, sort_order,
                     created_by, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (file_path, file_name, promo_type, duration_seconds,
                      go_live_date, expiration_date, is_active, sort_order,
                      created_by, notes))
                
                result = cursor.fetchone()
                if result:
                    promo_id = result['id']
                    conn.commit()
                    logger.info(f"Added {promo_type} meeting promo: {file_name} with ID {promo_id}")
                    return promo_id
                else:
                    logger.error("No ID returned from INSERT")
                    conn.rollback()
                    return None
        except Exception as e:
            logger.error(f"Error adding promo: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def update_promo(self, promo_id: int, **kwargs) -> bool:
        """Update an existing promo"""
        conn = self.db._get_connection()
        try:
            with conn.cursor() as cursor:
                # Build update query dynamically
                allowed_fields = ['file_path', 'file_name', 'promo_type', 
                                'duration_seconds', 'go_live_date', 'expiration_date',
                                'is_active', 'sort_order', 'notes']
                
                update_parts = []
                params = []
                
                for field in allowed_fields:
                    if field in kwargs:
                        update_parts.append(f"{field} = %s")
                        params.append(kwargs[field])
                
                if not update_parts:
                    return True  # Nothing to update
                
                params.append(promo_id)
                query = f"""
                    UPDATE meeting_promos 
                    SET {', '.join(update_parts)}
                    WHERE id = %s
                """
                
                cursor.execute(query, params)
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating promo {promo_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def delete_promo(self, promo_id: int) -> bool:
        """Delete a promo"""
        conn = self.db._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM meeting_promos WHERE id = %s", (promo_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting promo {promo_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def toggle_promo_active(self, promo_id: int) -> bool:
        """Toggle the active status of a promo"""
        conn = self.db._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE meeting_promos 
                    SET is_active = NOT is_active
                    WHERE id = %s
                """, (promo_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error toggling promo {promo_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_active_promos_for_scheduling(self, promo_type: str, 
                                        schedule_date: date = None) -> List[Dict]:
        """Get promos that should be scheduled for a specific date"""
        if schedule_date is None:
            schedule_date = date.today()
            
        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # First check if promos are enabled
                cursor.execute(f"""
                    SELECT {promo_type}_meeting_enabled as enabled
                    FROM meeting_promo_settings
                    WHERE id = 1
                """)
                
                settings = cursor.fetchone()
                if not settings or not settings['enabled']:
                    return []
                
                # Get active promos for the date
                cursor.execute("""
                    SELECT id, file_path, file_name, duration_seconds, sort_order
                    FROM meeting_promos
                    WHERE promo_type = %s
                      AND is_active = true
                      AND (go_live_date IS NULL OR go_live_date <= %s)
                      AND (expiration_date IS NULL OR expiration_date >= %s)
                    ORDER BY sort_order, file_name
                """, (promo_type, schedule_date, schedule_date))
                
                return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def update_sort_order(self, promo_ids: List[int]) -> bool:
        """Update sort order for multiple promos"""
        conn = self.db._get_connection()
        try:
            with conn.cursor() as cursor:
                for index, promo_id in enumerate(promo_ids):
                    cursor.execute("""
                        UPDATE meeting_promos 
                        SET sort_order = %s
                        WHERE id = %s
                    """, (index, promo_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating sort order: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()