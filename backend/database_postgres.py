import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class PostgreSQLDatabaseManager:
    def __init__(self, connection_string=None):
        import getpass
        default_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
        self.connection_string = connection_string or os.getenv(
            'DATABASE_URL', 
            default_conn
        )
        self.pool = None
        self.connected = False
        self.collection = None  # Compatibility property for MongoDB checks
        self.client = None  # Compatibility property for MongoDB checks
        self.db = None  # Compatibility property for MongoDB checks
    
    def _get_connection(self):
        """Get a connection from the pool"""
        if not self.pool:
            raise Exception("Database connection pool not initialized")
        return self.pool.getconn()
    
    def _put_connection(self, conn):
        """Return a connection to the pool"""
        if self.pool:
            self.pool.putconn(conn)
    
    def connect(self):
        """Initialize the connection pool"""
        try:
            self.pool = ThreadedConnectionPool(
                1, 20,  # min and max connections
                self.connection_string,
                cursor_factory=RealDictCursor
            )
            
            # Test connection
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            self._put_connection(conn)
            
            self.connected = True
            self.collection = True  # Set to True for compatibility with MongoDB checks
            self.client = self.pool  # Set to pool for compatibility
            self.db = True  # Set to True for compatibility
            logger.info("Connected to PostgreSQL database")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()
            self.connected = False
            self.collection = None  # Reset compatibility property
            self.client = None  # Reset compatibility property
            self.db = None  # Reset compatibility property
            logger.info("Disconnected from PostgreSQL")
    
    def check_analysis_status(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Check which files have already been analyzed"""
        if not self.connected:
            return []
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get file paths
            file_paths = [file.get('path') or file.get('name') for file in files]
            
            # Query for analyzed files
            cursor.execute("""
                SELECT 
                    a.id,
                    a.guid,
                    a.created_at,
                    a.mongo_id as _id,
                    i.file_path,
                    i.file_name
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                WHERE i.file_path = ANY(%s)
            """, (file_paths,))
            
            results = cursor.fetchall()
            cursor.close()
            
            # Convert to expected format
            analyzed_files = []
            for row in results:
                analyzed_files.append({
                    '_id': row['_id'] or str(row['id']),
                    'file_path': row['file_path'],
                    'file_name': row['file_name'],
                    'guid': str(row['guid']),
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None
                })
            
            return analyzed_files
            
        except Exception as e:
            logger.error(f"Error checking analysis status: {str(e)}")
            return []
        finally:
            self._put_connection(conn)
    
    def get_analysis_by_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get analysis result for a specific file path"""
        if not self.connected:
            return None
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get full asset details
            cursor.execute("""
                SELECT 
                    a.*,
                    i.file_name,
                    i.file_path,
                    i.file_size,
                    i.storage_location,
                    i.encoded_date,
                    sm.available_for_scheduling,
                    sm.content_expiry_date,
                    sm.last_scheduled_date,
                    sm.total_airings,
                    sm.priority_score,
                    sm.optimal_timeslots,
                    -- Scheduling metadata fields
                    sm.last_scheduled_in_overnight,
                    sm.last_scheduled_in_early_morning,
                    sm.last_scheduled_in_morning,
                    sm.last_scheduled_in_afternoon,
                    sm.last_scheduled_in_prime_time,
                    sm.last_scheduled_in_evening,
                    sm.replay_count_for_overnight,
                    sm.replay_count_for_early_morning,
                    sm.replay_count_for_morning,
                    sm.replay_count_for_afternoon,
                    sm.replay_count_for_prime_time,
                    sm.replay_count_for_evening
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE i.file_path = %s
            """, (file_path,))
            
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                return None
            
            asset_id = result['id']
            
            # Get tags
            cursor.execute("""
                SELECT tt.type_name, t.tag_name
                FROM asset_tags at
                JOIN tags t ON at.tag_id = t.id
                JOIN tag_types tt ON t.tag_type_id = tt.id
                WHERE at.asset_id = %s
            """, (asset_id,))
            
            tags = cursor.fetchall()
            cursor.close()
            
            # Convert to MongoDB-compatible format
            analysis = {
                '_id': result['mongo_id'] or str(result['id']),
                'guid': str(result['guid']),
                'file_name': result['file_name'],
                'file_path': result['file_path'],
                'file_size': result['file_size'],
                'file_duration': float(result['duration_seconds']) if result['duration_seconds'] else None,
                'duration_category': result['duration_category'],
                'encoded_date': result['encoded_date'].isoformat() if result['encoded_date'] else None,
                'content_type': result['content_type'],
                'content_title': result['content_title'],
                'transcript': result['transcript'],
                'language': result['language'],
                'summary': result['summary'],
                'engagement_score': result['engagement_score'],
                'engagement_score_reasons': result['engagement_score_reasons'],
                'shelf_life_score': result['shelf_life_score'],
                'shelf_life_reasons': result['shelf_life_reasons'],
                'analysis_completed': result['analysis_completed'],
                'ai_analysis_enabled': result['ai_analysis_enabled'],
                'created_at': result['created_at'].isoformat() if result['created_at'] else None,
                'updated_at': result['updated_at'].isoformat() if result['updated_at'] else None,
                
                # Extract tags by type
                'topics': [t['tag_name'] for t in tags if t['type_name'] == 'topic'],
                'people': [t['tag_name'] for t in tags if t['type_name'] == 'person'],
                'events': [t['tag_name'] for t in tags if t['type_name'] == 'event'],
                'locations': [t['tag_name'] for t in tags if t['type_name'] == 'location'],
            }
            
            # Add scheduling metadata if it exists
            if result['available_for_scheduling'] is not None:
                analysis['scheduling'] = {
                    'available_for_scheduling': result['available_for_scheduling'],
                    'content_expiry_date': result['content_expiry_date'].isoformat() if result['content_expiry_date'] else None,
                    'last_scheduled_date': result['last_scheduled_date'].isoformat() if result['last_scheduled_date'] else None,
                    'total_airings': result['total_airings'],
                    'priority_score': float(result['priority_score']) if result['priority_score'] else None,
                    'optimal_timeslots': result['optimal_timeslots'] or [],
                    'last_scheduled_in_overnight': result['last_scheduled_in_overnight'].isoformat() if result['last_scheduled_in_overnight'] else None,
                    'last_scheduled_in_early_morning': result['last_scheduled_in_early_morning'].isoformat() if result['last_scheduled_in_early_morning'] else None,
                    'last_scheduled_in_morning': result['last_scheduled_in_morning'].isoformat() if result['last_scheduled_in_morning'] else None,
                    'last_scheduled_in_afternoon': result['last_scheduled_in_afternoon'].isoformat() if result['last_scheduled_in_afternoon'] else None,
                    'last_scheduled_in_prime_time': result['last_scheduled_in_prime_time'].isoformat() if result['last_scheduled_in_prime_time'] else None,
                    'last_scheduled_in_evening': result['last_scheduled_in_evening'].isoformat() if result['last_scheduled_in_evening'] else None,
                    'replay_count_for_overnight': result['replay_count_for_overnight'],
                    'replay_count_for_early_morning': result['replay_count_for_early_morning'],
                    'replay_count_for_morning': result['replay_count_for_morning'],
                    'replay_count_for_afternoon': result['replay_count_for_afternoon'],
                    'replay_count_for_prime_time': result['replay_count_for_prime_time'],
                    'replay_count_for_evening': result['replay_count_for_evening'],
                }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error getting analysis for {file_path}: {str(e)}")
            return None
        finally:
            self._put_connection(conn)
    
    def upsert_analysis(self, analysis_data: Dict[str, Any]) -> bool:
        """Insert or update analysis result"""
        if not self.connected:
            return False
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conn.autocommit = False
            
            # Check if asset exists
            cursor.execute("""
                SELECT a.id, a.guid
                FROM assets a
                JOIN instances i ON a.id = i.asset_id
                WHERE i.file_path = %s
            """, (analysis_data['file_path'],))
            
            existing = cursor.fetchone()
            
            # Prepare asset data
            content_type = self._classify_content_type(
                analysis_data.get('file_name', ''),
                analysis_data.get('content_type')
            )
            
            asset_data = {
                'content_type': content_type,
                'content_title': analysis_data.get('content_title', '')[:500],
                'language': analysis_data.get('language', 'en')[:10],
                'transcript': analysis_data.get('transcript', ''),
                'summary': analysis_data.get('summary', ''),
                'duration_seconds': analysis_data.get('file_duration'),
                'duration_category': self._ensure_duration_category(
                    analysis_data.get('duration_category', 'short')
                ),
                'engagement_score': self._bound_engagement_score(
                    analysis_data.get('engagement_score')
                ),
                'engagement_score_reasons': analysis_data.get('engagement_score_reasons'),
                'shelf_life_score': analysis_data.get('shelf_life_score', 'medium'),
                'shelf_life_reasons': analysis_data.get('shelf_life_reasons'),
                'analysis_completed': analysis_data.get('analysis_completed', False),
                'ai_analysis_enabled': analysis_data.get('ai_analysis_enabled', True),
            }
            
            if existing:
                # Update existing asset
                asset_id = existing['id']
                asset_data['updated_at'] = datetime.utcnow()
                
                update_fields = ', '.join([f"{k} = %({k})s" for k in asset_data.keys()])
                cursor.execute(f"""
                    UPDATE assets 
                    SET {update_fields}
                    WHERE id = %(id)s
                """, {**asset_data, 'id': asset_id})
                
                logger.info(f"Updated analysis for {analysis_data['file_name']}")
            else:
                # Insert new asset
                asset_data['guid'] = analysis_data.get('guid') or str(uuid.uuid4())
                asset_data['created_at'] = datetime.utcnow()
                asset_data['updated_at'] = datetime.utcnow()
                
                cursor.execute("""
                    INSERT INTO assets (
                        guid, content_type, content_title, language,
                        transcript, summary, duration_seconds, duration_category,
                        engagement_score, engagement_score_reasons, shelf_life_score,
                        shelf_life_reasons, analysis_completed, ai_analysis_enabled,
                        created_at, updated_at
                    ) VALUES (
                        %(guid)s::uuid, %(content_type)s, %(content_title)s, %(language)s,
                        %(transcript)s, %(summary)s, %(duration_seconds)s, %(duration_category)s,
                        %(engagement_score)s, %(engagement_score_reasons)s, %(shelf_life_score)s,
                        %(shelf_life_reasons)s, %(analysis_completed)s, %(ai_analysis_enabled)s,
                        %(created_at)s, %(updated_at)s
                    ) RETURNING id
                """, asset_data)
                
                asset_id = cursor.fetchone()['id']
                
                # Insert instance
                instance_data = {
                    'asset_id': asset_id,
                    'file_name': analysis_data.get('file_name', '')[:500],
                    'file_path': analysis_data.get('file_path', ''),
                    'file_size': analysis_data.get('file_size'),
                    'file_duration': analysis_data.get('file_duration'),
                    'storage_location': 'primary_server',
                    'encoded_date': self._parse_date(analysis_data.get('encoded_date')),
                    'is_primary': True
                }
                
                cursor.execute("""
                    INSERT INTO instances (
                        asset_id, file_name, file_path, file_size,
                        file_duration, storage_location, encoded_date, is_primary
                    ) VALUES (
                        %(asset_id)s, %(file_name)s, %(file_path)s, %(file_size)s,
                        %(file_duration)s, %(storage_location)s, %(encoded_date)s, %(is_primary)s
                    )
                """, instance_data)
                
                logger.info(f"Inserted new analysis for {analysis_data['file_name']}")
            
            # Update tags
            self._update_tags(cursor, asset_id, analysis_data)
            
            # Update scheduling metadata
            if 'scheduling' in analysis_data:
                self._update_scheduling_metadata(cursor, asset_id, analysis_data['scheduling'])
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error upserting analysis: {str(e)}")
            return False
        finally:
            conn.autocommit = True
            self._put_connection(conn)
    
    def get_all_analyses(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all analysis results"""
        if not self.connected:
            return []
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get assets with primary instances
            cursor.execute("""
                SELECT 
                    a.id,
                    a.guid,
                    a.content_type,
                    a.content_title,
                    a.summary,
                    a.duration_seconds,
                    a.engagement_score,
                    a.created_at,
                    a.mongo_id,
                    i.file_name,
                    i.file_path,
                    i.file_size
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                ORDER BY a.created_at DESC
                LIMIT %s
            """, (limit,))
            
            results = cursor.fetchall()
            cursor.close()
            
            # Convert to MongoDB-compatible format
            analyses = []
            for row in results:
                analyses.append({
                    '_id': row['mongo_id'] or str(row['id']),
                    'guid': str(row['guid']),
                    'file_name': row['file_name'],
                    'file_path': row['file_path'],
                    'file_size': row['file_size'],
                    'file_duration': float(row['duration_seconds']) if row['duration_seconds'] else None,
                    'content_type': row['content_type'],
                    'content_title': row['content_title'],
                    'summary': row['summary'],
                    'engagement_score': row['engagement_score'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None
                })
            
            return analyses
            
        except Exception as e:
            logger.error(f"Error getting all analyses: {str(e)}")
            return []
        finally:
            self._put_connection(conn)
    
    def delete_analysis(self, file_path: str) -> bool:
        """Delete analysis result"""
        if not self.connected:
            return False
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Find and delete the asset (cascades to instances, tags, etc.)
            cursor.execute("""
                DELETE FROM assets
                WHERE id IN (
                    SELECT asset_id FROM instances WHERE file_path = %s
                )
                RETURNING id
            """, (file_path,))
            
            result = cursor.fetchone()
            conn.commit()
            cursor.close()
            
            if result:
                logger.info(f"Deleted analysis for {file_path}")
                return True
            else:
                logger.warning(f"No analysis found for {file_path}")
                return False
                
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting analysis: {str(e)}")
            return False
        finally:
            self._put_connection(conn)
    
    def clear_all_analyses(self) -> Dict[str, Any]:
        """Delete all analysis results from the database"""
        if not self.connected:
            return {"success": False, "message": "Database not connected", "deleted_count": 0}
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get count before deletion
            cursor.execute("SELECT COUNT(*) as count FROM assets")
            count_before = cursor.fetchone()['count']
            
            logger.info(f"Found {count_before} analysis records to delete")
            
            # Delete all assets (cascades to all related tables)
            cursor.execute("DELETE FROM assets")
            deleted_count = cursor.rowcount
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Successfully cleared {deleted_count} analysis records from database")
            
            return {
                "success": True,
                "message": f"Cleared {deleted_count} analysis records",
                "deleted_count": deleted_count
            }
            
        except Exception as e:
            conn.rollback()
            error_msg = f"Error clearing all analyses: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "deleted_count": 0
            }
        finally:
            self._put_connection(conn)
    
    # Helper methods
    def _classify_content_type(self, filename: str, content_type: str = None) -> str:
        """Classify content type based on filename and existing content_type"""
        if content_type:
            type_map = {
                'PSA': 'psa',
                'PKG': 'pkg',
                'IA': 'ia',
                'MTG': 'mtg',
                'MEETING': 'meeting'
            }
            mapped = type_map.get(content_type.upper())
            if mapped:
                return mapped
        
        filename_lower = filename.lower()
        if 'psa' in filename_lower:
            return 'psa'
        elif 'meeting' in filename_lower or 'council' in filename_lower or 'mtg' in filename_lower:
            return 'meeting'
        elif 'announcement' in filename_lower:
            return 'announcement'
        elif 'pkg' in filename_lower:
            return 'pkg'
        elif '_ia_' in filename_lower:
            return 'ia'
        else:
            return 'other'
    
    def _ensure_duration_category(self, category: str) -> str:
        """Ensure duration category is valid"""
        valid_categories = ['spots', 'short', 'medium', 'long', 'id', 'short_form', 'long_form']
        if category in valid_categories:
            return category
        
        category_map = {
            'spot': 'spots',
            'short-form': 'short_form',
            'long-form': 'long_form'
        }
        
        return category_map.get(category, 'short')
    
    def _bound_engagement_score(self, score: Any) -> Optional[int]:
        """Ensure engagement score is within bounds"""
        if score is None:
            return None
        try:
            score_int = int(score)
            return max(0, min(100, score_int))
        except (ValueError, TypeError):
            return None
    
    def _parse_date(self, date_value: Any) -> Optional[datetime]:
        """Parse various date formats"""
        if not date_value:
            return None
        
        if isinstance(date_value, datetime):
            return date_value
        
        try:
            # Try ISO format first
            return datetime.fromisoformat(str(date_value).replace('Z', '+00:00'))
        except:
            try:
                # Try common formats
                from dateutil import parser
                return parser.parse(str(date_value))
            except:
                return None
    
    def _update_tags(self, cursor, asset_id: int, analysis_data: Dict[str, Any]):
        """Update tags for an asset"""
        # Clear existing tags
        cursor.execute("DELETE FROM asset_tags WHERE asset_id = %s", (asset_id,))
        
        # Get tag type IDs
        cursor.execute("SELECT id, type_name FROM tag_types")
        tag_types = {row['type_name']: row['id'] for row in cursor.fetchall()}
        
        # Insert tags
        tag_mapping = {
            'topic': analysis_data.get('topics', []),
            'person': analysis_data.get('people', []),
            'event': analysis_data.get('events', []),
            'location': analysis_data.get('locations', [])
        }
        
        for tag_type, tags in tag_mapping.items():
            if not isinstance(tags, list):
                continue
                
            tag_type_id = tag_types.get(tag_type)
            if not tag_type_id:
                continue
            
            for tag_name in tags:
                if not tag_name or not isinstance(tag_name, str):
                    continue
                
                # Insert or get tag
                cursor.execute("""
                    INSERT INTO tags (tag_type_id, tag_name)
                    VALUES (%s, %s)
                    ON CONFLICT (tag_type_id, tag_name) DO UPDATE
                    SET tag_name = EXCLUDED.tag_name
                    RETURNING id
                """, (tag_type_id, tag_name[:255]))
                
                tag_id = cursor.fetchone()['id']
                
                # Link to asset
                cursor.execute("""
                    INSERT INTO asset_tags (asset_id, tag_id)
                    VALUES (%s, %s)
                """, (asset_id, tag_id))
    
    def _update_scheduling_metadata(self, cursor, asset_id: int, scheduling_data: Dict[str, Any]):
        """Update scheduling metadata for an asset"""
        sched_meta = {
            'asset_id': asset_id,
            'available_for_scheduling': scheduling_data.get('available_for_scheduling', True),
            'content_expiry_date': self._parse_date(scheduling_data.get('content_expiry_date')),
            'last_scheduled_date': self._parse_date(scheduling_data.get('last_scheduled_date')),
            'total_airings': scheduling_data.get('total_airings', 0),
            'created_for_scheduling': self._parse_date(scheduling_data.get('created_for_scheduling')) or datetime.utcnow(),
            'last_scheduled_in_overnight': self._parse_date(scheduling_data.get('last_scheduled_in_overnight')),
            'last_scheduled_in_early_morning': self._parse_date(scheduling_data.get('last_scheduled_in_early_morning')),
            'last_scheduled_in_morning': self._parse_date(scheduling_data.get('last_scheduled_in_morning')),
            'last_scheduled_in_afternoon': self._parse_date(scheduling_data.get('last_scheduled_in_afternoon')),
            'last_scheduled_in_prime_time': self._parse_date(scheduling_data.get('last_scheduled_in_prime_time')),
            'last_scheduled_in_evening': self._parse_date(scheduling_data.get('last_scheduled_in_evening')),
            'replay_count_for_overnight': scheduling_data.get('replay_count_for_overnight', 0),
            'replay_count_for_early_morning': scheduling_data.get('replay_count_for_early_morning', 0),
            'replay_count_for_morning': scheduling_data.get('replay_count_for_morning', 0),
            'replay_count_for_afternoon': scheduling_data.get('replay_count_for_afternoon', 0),
            'replay_count_for_prime_time': scheduling_data.get('replay_count_for_prime_time', 0),
            'replay_count_for_evening': scheduling_data.get('replay_count_for_evening', 0),
            'priority_score': scheduling_data.get('priority_score'),
            'optimal_timeslots': scheduling_data.get('optimal_timeslots', [])
        }
        
        cursor.execute("""
            INSERT INTO scheduling_metadata (
                asset_id, available_for_scheduling, content_expiry_date,
                last_scheduled_date, total_airings, created_for_scheduling,
                last_scheduled_in_overnight, last_scheduled_in_early_morning,
                last_scheduled_in_morning, last_scheduled_in_afternoon,
                last_scheduled_in_prime_time, last_scheduled_in_evening,
                replay_count_for_overnight, replay_count_for_early_morning,
                replay_count_for_morning, replay_count_for_afternoon,
                replay_count_for_prime_time, replay_count_for_evening,
                priority_score, optimal_timeslots
            ) VALUES (
                %(asset_id)s, %(available_for_scheduling)s, %(content_expiry_date)s,
                %(last_scheduled_date)s, %(total_airings)s, %(created_for_scheduling)s,
                %(last_scheduled_in_overnight)s, %(last_scheduled_in_early_morning)s,
                %(last_scheduled_in_morning)s, %(last_scheduled_in_afternoon)s,
                %(last_scheduled_in_prime_time)s, %(last_scheduled_in_evening)s,
                %(replay_count_for_overnight)s, %(replay_count_for_early_morning)s,
                %(replay_count_for_morning)s, %(replay_count_for_afternoon)s,
                %(replay_count_for_prime_time)s, %(replay_count_for_evening)s,
                %(priority_score)s, %(optimal_timeslots)s
            )
            ON CONFLICT (asset_id) DO UPDATE SET
                available_for_scheduling = EXCLUDED.available_for_scheduling,
                content_expiry_date = EXCLUDED.content_expiry_date,
                last_scheduled_date = EXCLUDED.last_scheduled_date,
                total_airings = EXCLUDED.total_airings,
                last_scheduled_in_overnight = EXCLUDED.last_scheduled_in_overnight,
                last_scheduled_in_early_morning = EXCLUDED.last_scheduled_in_early_morning,
                last_scheduled_in_morning = EXCLUDED.last_scheduled_in_morning,
                last_scheduled_in_afternoon = EXCLUDED.last_scheduled_in_afternoon,
                last_scheduled_in_prime_time = EXCLUDED.last_scheduled_in_prime_time,
                last_scheduled_in_evening = EXCLUDED.last_scheduled_in_evening,
                replay_count_for_overnight = EXCLUDED.replay_count_for_overnight,
                replay_count_for_early_morning = EXCLUDED.replay_count_for_early_morning,
                replay_count_for_morning = EXCLUDED.replay_count_for_morning,
                replay_count_for_afternoon = EXCLUDED.replay_count_for_afternoon,
                replay_count_for_prime_time = EXCLUDED.replay_count_for_prime_time,
                replay_count_for_evening = EXCLUDED.replay_count_for_evening,
                priority_score = EXCLUDED.priority_score,
                optimal_timeslots = EXCLUDED.optimal_timeslots
        """, sched_meta)
    
    def get_analyzed_content_for_scheduling(self, content_type: str = '', duration_category: str = '', search: str = '') -> List[Dict[str, Any]]:
        """Get analyzed content for scheduling with filters"""
        if not self.connected:
            return []
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Build query
            query = """
                SELECT 
                    a.*,
                    i.file_name,
                    i.file_path,
                    i.file_size,
                    i.file_duration,
                    sm.available_for_scheduling,
                    sm.content_expiry_date,
                    sm.last_scheduled_date,
                    sm.total_airings,
                    sm.priority_score,
                    sm.optimal_timeslots
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE a.analysis_completed = TRUE
            """
            
            params = []
            
            # Add filters
            if content_type:
                query += " AND a.content_type = %s"
                params.append(content_type)
            
            if duration_category:
                query += " AND a.duration_category = %s"
                params.append(duration_category)
            
            # Add search filter if provided
            if search:
                query += """ AND (
                    LOWER(i.file_name) LIKE %s OR 
                    LOWER(a.content_title) LIKE %s OR 
                    LOWER(a.summary) LIKE %s
                )"""
                search_pattern = f'%{search}%'
                params.extend([search_pattern, search_pattern, search_pattern])
            
            # Filter out expired content
            query += """
                AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP)
                AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
            """
            
            # Order by priority score and engagement score
            query += """
                ORDER BY 
                    COALESCE(sm.priority_score, 0) DESC,
                    a.engagement_score DESC NULLS LAST
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()
            
            # Convert to MongoDB-compatible format
            content_list = []
            for row in results:
                content = {
                    '_id': row['mongo_id'] or str(row['id']),
                    'guid': str(row['guid']),
                    'file_name': row['file_name'],
                    'file_path': row['file_path'],
                    'file_size': row['file_size'],
                    'file_duration': float(row['file_duration']) if row['file_duration'] else float(row['duration_seconds']) if row['duration_seconds'] else 0,
                    'duration_category': row['duration_category'],
                    'content_type': row['content_type'],
                    'content_title': row['content_title'],
                    'summary': row['summary'],
                    'engagement_score': row['engagement_score'],
                    'analysis_completed': row['analysis_completed'],
                    'scheduling': {
                        'available_for_scheduling': row.get('available_for_scheduling', True),
                        'content_expiry_date': row['content_expiry_date'],
                        'last_scheduled_date': row['last_scheduled_date'],
                        'total_airings': row.get('total_airings', 0),
                        'priority_score': float(row['priority_score']) if row['priority_score'] else 0,
                        'optimal_timeslots': row.get('optimal_timeslots', [])
                    }
                }
                content_list.append(content)
            
            return content_list
            
        except Exception as e:
            logger.error(f"Error getting analyzed content: {str(e)}")
            return []
        finally:
            self._put_connection(conn)


# Global database manager instance - will be replaced in database.py
# db_manager = PostgreSQLDatabaseManager()