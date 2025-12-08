#!/usr/bin/env python3
"""
Migration script to move data from MongoDB to PostgreSQL
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from pymongo import MongoClient
from datetime import datetime
import json
import logging
import sys
import argparse
from typing import Dict, List, Any, Optional
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MongoToPostgresMigration:
    def __init__(self, mongo_uri: str, pg_connection_string: str):
        self.mongo_uri = mongo_uri
        self.pg_connection_string = pg_connection_string
        self.mongo_client = None
        self.mongo_db = None
        self.mongo_collection = None
        self.pg_conn = None
        self.pg_cursor = None
        
        # Keep track of tag mappings
        self.tag_type_map = {}
        self.tag_map = {}
        
    def connect(self):
        """Establish connections to both databases"""
        try:
            # Connect to MongoDB
            self.mongo_client = MongoClient(self.mongo_uri)
            self.mongo_db = self.mongo_client['castus']
            self.mongo_collection = self.mongo_db['analysis']
            logger.info("Connected to MongoDB")
            
            # Connect to PostgreSQL
            self.pg_conn = psycopg2.connect(self.pg_connection_string)
            self.pg_cursor = self.pg_conn.cursor(cursor_factory=RealDictCursor)
            logger.info("Connected to PostgreSQL")
            
            # Load tag type mappings
            self.pg_cursor.execute("SELECT id, type_name FROM tag_types")
            for row in self.pg_cursor.fetchall():
                self.tag_type_map[row['type_name']] = row['id']
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise
    
    def disconnect(self):
        """Close all connections"""
        if self.pg_cursor:
            self.pg_cursor.close()
        if self.pg_conn:
            self.pg_conn.close()
        if self.mongo_client:
            self.mongo_client.close()
    
    def classify_content_type(self, filename: str, content_type: str = None) -> str:
        """Classify content type based on filename and existing content_type"""
        if content_type:
            # Map existing content types
            type_map = {
                'AN': 'an',
                'ATLD': 'atld',
                'BMP': 'bmp',
                'IMOW': 'imow',
                'IM': 'im',
                'IA': 'ia',
                'LM': 'lm',
                'MTG': 'mtg',
                'MAF': 'maf',
                'PKG': 'pkg',
                'PMO': 'pmo',
                'PSA': 'psa',
                'SZL': 'szl',
                'SPP': 'spp'
            }
            mapped = type_map.get(content_type.upper())
            if mapped:
                return mapped
        
        # Fallback to filename analysis
        filename_lower = filename.lower()
        if 'psa' in filename_lower:
            return 'psa'
        elif 'meeting' in filename_lower or 'council' in filename_lower or 'mtg' in filename_lower:
            return 'mtg'
        elif 'announcement' in filename_lower or '_an_' in filename_lower:
            return 'an'
        elif 'pkg' in filename_lower:
            return 'pkg'
        elif '_ia_' in filename_lower or 'inside atlanta' in filename_lower:
            return 'ia'
        elif 'maf' in filename_lower or 'moving atlanta forward' in filename_lower:
            return 'maf'
        elif 'bmp' in filename_lower or 'bump' in filename_lower:
            return 'bmp'
        elif 'promo' in filename_lower or 'pmo' in filename_lower:
            return 'pmo'
        else:
            return 'other'
    
    def parse_encoded_date(self, date_value) -> Optional[datetime]:
        """Parse various date formats"""
        if not date_value:
            return None
        
        if isinstance(date_value, datetime):
            return date_value
        
        try:
            # Try common date formats
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(str(date_value), fmt)
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None
    
    def ensure_duration_category(self, category: str) -> str:
        """Ensure duration category is valid"""
        valid_categories = ['spots', 'short', 'medium', 'long', 'id', 'short_form', 'long_form']
        if category in valid_categories:
            return category
        
        # Map common alternatives
        category_map = {
            'spot': 'spots',
            'short-form': 'short_form',
            'long-form': 'long_form'
        }
        
        return category_map.get(category, 'short')
    
    def normalize_shelf_life_score(self, score: str) -> str:
        """Normalize shelf life score to valid enum values"""
        # Map old values to new enum values
        score_map = {
            'short': 'low',
            'medium': 'medium',
            'long': 'high',
            'low': 'low',
            'high': 'high'
        }
        
        return score_map.get(score, 'medium')
    
    def insert_tag(self, asset_id: int, tag_type: str, tag_name: str) -> bool:
        """Insert a tag and link it to an asset"""
        if not tag_name or not isinstance(tag_name, str):
            return False
        
        try:
            tag_type_id = self.tag_type_map.get(tag_type)
            if not tag_type_id:
                logger.warning(f"Unknown tag type: {tag_type}")
                return False
            
            # Check if tag already exists
            tag_key = f"{tag_type}:{tag_name}"
            if tag_key in self.tag_map:
                tag_id = self.tag_map[tag_key]
            else:
                # Insert or get existing tag
                self.pg_cursor.execute("""
                    INSERT INTO tags (tag_type_id, tag_name)
                    VALUES (%s, %s)
                    ON CONFLICT (tag_type_id, tag_name) DO UPDATE
                    SET tag_name = EXCLUDED.tag_name
                    RETURNING id
                """, (tag_type_id, tag_name[:255]))  # Truncate to 255 chars
                
                tag_id = self.pg_cursor.fetchone()['id']
                self.tag_map[tag_key] = tag_id
            
            # Link tag to asset
            self.pg_cursor.execute("""
                INSERT INTO asset_tags (asset_id, tag_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (asset_id, tag_id))
            
            return True
            
        except Exception as e:
            logger.error(f"Error inserting tag {tag_name}: {e}")
            return False
    
    def migrate_document(self, doc: Dict[str, Any]) -> bool:
        """Migrate a single MongoDB document to PostgreSQL"""
        try:
            # 1. Insert into ASSETS table
            asset_data = {
                'mongo_id': str(doc['_id']),
                'guid': doc.get('guid') or str(uuid.uuid4()),
                'content_type': self.classify_content_type(
                    doc.get('file_name', ''), 
                    doc.get('content_type')
                ),
                'content_title': doc.get('content_title', '')[:500],  # Ensure max 500 chars
                'language': doc.get('language', 'en')[:10],
                'transcript': doc.get('transcript', ''),
                'summary': doc.get('summary', ''),
                'duration_seconds': doc.get('file_duration'),
                'duration_category': self.ensure_duration_category(
                    doc.get('duration_category', 'short')
                ),
                'engagement_score': doc.get('engagement_score'),
                'engagement_score_reasons': doc.get('engagement_score_reasons'),
                'shelf_life_score': self.normalize_shelf_life_score(
                    doc.get('shelf_life_score', 'medium')
                ),
                'shelf_life_reasons': doc.get('shelf_life_reasons'),
                'analysis_completed': doc.get('analysis_completed', False),
                'ai_analysis_enabled': doc.get('ai_analysis_enabled', True),
                'created_at': doc.get('created_at', datetime.utcnow()),
                'updated_at': doc.get('updated_at', datetime.utcnow())
            }
            
            # Handle engagement score bounds
            if asset_data['engagement_score'] is not None:
                asset_data['engagement_score'] = max(0, min(100, int(asset_data['engagement_score'])))
            
            self.pg_cursor.execute("""
                INSERT INTO assets (
                    mongo_id, guid, content_type, content_title, language,
                    transcript, summary, duration_seconds, duration_category,
                    engagement_score, engagement_score_reasons, shelf_life_score,
                    shelf_life_reasons, analysis_completed, ai_analysis_enabled,
                    created_at, updated_at
                ) VALUES (
                    %(mongo_id)s, %(guid)s::uuid, %(content_type)s, %(content_title)s, %(language)s,
                    %(transcript)s, %(summary)s, %(duration_seconds)s, %(duration_category)s,
                    %(engagement_score)s, %(engagement_score_reasons)s, %(shelf_life_score)s,
                    %(shelf_life_reasons)s, %(analysis_completed)s, %(ai_analysis_enabled)s,
                    %(created_at)s, %(updated_at)s
                ) RETURNING id
            """, asset_data)
            
            asset_id = self.pg_cursor.fetchone()['id']
            
            # 2. Insert into INSTANCES table
            instance_data = {
                'asset_id': asset_id,
                'file_name': doc.get('file_name', '')[:500],
                'file_path': doc.get('file_path', ''),
                'file_size': doc.get('file_size'),
                'file_duration': doc.get('file_duration'),
                'storage_location': 'primary_server',
                'encoded_date': self.parse_encoded_date(doc.get('encoded_date')),
                'is_primary': True
            }
            
            self.pg_cursor.execute("""
                INSERT INTO instances (
                    asset_id, file_name, file_path, file_size,
                    file_duration, storage_location, encoded_date, is_primary
                ) VALUES (
                    %(asset_id)s, %(file_name)s, %(file_path)s, %(file_size)s,
                    %(file_duration)s, %(storage_location)s, %(encoded_date)s, %(is_primary)s
                )
            """, instance_data)
            
            # 3. Migrate scheduling metadata
            scheduling_data = doc.get('scheduling', {})
            if scheduling_data:
                sched_meta = {
                    'asset_id': asset_id,
                    'available_for_scheduling': scheduling_data.get('available_for_scheduling', True),
                    'content_expiry_date': self.parse_encoded_date(
                        scheduling_data.get('content_expiry_date')
                    ),
                    'last_scheduled_date': self.parse_encoded_date(
                        scheduling_data.get('last_scheduled_date')
                    ),
                    'total_airings': scheduling_data.get('total_airings', 0),
                    'created_for_scheduling': self.parse_encoded_date(
                        scheduling_data.get('created_for_scheduling')
                    ) or datetime.utcnow(),
                    'last_scheduled_in_overnight': self.parse_encoded_date(
                        scheduling_data.get('last_scheduled_in_overnight')
                    ),
                    'last_scheduled_in_early_morning': self.parse_encoded_date(
                        scheduling_data.get('last_scheduled_in_early_morning')
                    ),
                    'last_scheduled_in_morning': self.parse_encoded_date(
                        scheduling_data.get('last_scheduled_in_morning')
                    ),
                    'last_scheduled_in_afternoon': self.parse_encoded_date(
                        scheduling_data.get('last_scheduled_in_afternoon')
                    ),
                    'last_scheduled_in_prime_time': self.parse_encoded_date(
                        scheduling_data.get('last_scheduled_in_prime_time')
                    ),
                    'last_scheduled_in_evening': self.parse_encoded_date(
                        scheduling_data.get('last_scheduled_in_evening')
                    ),
                    'replay_count_for_overnight': scheduling_data.get('replay_count_for_overnight', 0),
                    'replay_count_for_early_morning': scheduling_data.get('replay_count_for_early_morning', 0),
                    'replay_count_for_morning': scheduling_data.get('replay_count_for_morning', 0),
                    'replay_count_for_afternoon': scheduling_data.get('replay_count_for_afternoon', 0),
                    'replay_count_for_prime_time': scheduling_data.get('replay_count_for_prime_time', 0),
                    'replay_count_for_evening': scheduling_data.get('replay_count_for_evening', 0),
                    'priority_score': scheduling_data.get('priority_score'),
                    'optimal_timeslots': scheduling_data.get('optimal_timeslots', [])
                }
                
                self.pg_cursor.execute("""
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
                """, sched_meta)
            
            # 4. Migrate tags
            # Topics
            topics = doc.get('topics', [])
            if isinstance(topics, list):
                for topic in topics:
                    self.insert_tag(asset_id, 'topic', topic)
            
            # People
            people = doc.get('people', [])
            if isinstance(people, list):
                for person in people:
                    self.insert_tag(asset_id, 'person', person)
            
            # Events
            events = doc.get('events', [])
            if isinstance(events, list):
                for event in events:
                    self.insert_tag(asset_id, 'event', event)
            
            # Locations
            locations = doc.get('locations', [])
            if isinstance(locations, list):
                for location in locations:
                    self.insert_tag(asset_id, 'location', location)
            
            return True
            
        except Exception as e:
            logger.error(f"Error migrating document {doc.get('_id')}: {e}")
            return False
    
    def migrate(self, batch_size: int = 100):
        """Run the migration"""
        try:
            self.connect()
            
            # Get total count
            total_count = self.mongo_collection.count_documents({})
            logger.info(f"Found {total_count} documents to migrate")
            
            # Migrate in batches
            success_count = 0
            error_count = 0
            batch_count = 0
            
            cursor = self.mongo_collection.find().batch_size(batch_size)
            
            for doc in cursor:
                if self.migrate_document(doc):
                    success_count += 1
                    # Commit successful document immediately
                    self.pg_conn.commit()
                else:
                    error_count += 1
                    # Rollback failed document
                    self.pg_conn.rollback()
                
                # Log progress every batch
                if (success_count + error_count) % batch_size == 0:
                    batch_count += 1
                    logger.info(f"Batch {batch_count} completed. Progress: {success_count + error_count}/{total_count}")
            
            # Final commit
            self.pg_conn.commit()
            
            logger.info(f"Migration completed!")
            logger.info(f"Successfully migrated: {success_count} documents")
            logger.info(f"Errors: {error_count} documents")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            if self.pg_conn:
                self.pg_conn.rollback()
            raise
        finally:
            self.disconnect()


def main():
    parser = argparse.ArgumentParser(description='Migrate MongoDB data to PostgreSQL')
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017/', 
                        help='MongoDB connection URI')
    
    # Default to current user for macOS
    import getpass
    default_pg_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
    
    parser.add_argument('--pg-connection', 
                        default=default_pg_conn,
                        help='PostgreSQL connection string')
    parser.add_argument('--batch-size', type=int, default=100,
                        help='Batch size for migration')
    
    args = parser.parse_args()
    
    migration = MongoToPostgresMigration(args.mongo_uri, args.pg_connection)
    
    try:
        migration.migrate(batch_size=args.batch_size)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()