import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from database import db_manager
from create_schedules_table import schedules_db
import uuid

logger = logging.getLogger(__name__)

class ATL26Scheduler:
    def __init__(self):
        self.schedule_collection = None
        self.setup_collections()
        self.setup_schedules_db()
        
        # Default scheduling configuration
        self.config = {
            'duration_categories': {
                'id': {'min': 0, 'max': 16, 'label': 'ID (< 16s)'},
                'spots': {'min': 16, 'max': 120, 'label': 'Spots (16s - 2min)'},
                'short_form': {'min': 120, 'max': 1200, 'label': 'Short Form (2-20min)'},
                'long_form': {'min': 1200, 'max': float('inf'), 'label': 'Long Form (> 20min)'}
            },
            'timeslots': {
                'overnight': {'start': 0, 'end': 6, 'label': 'Overnight (12-6 AM)', 'duration_hours': 6},
                'early_morning': {'start': 6, 'end': 9, 'label': 'Early Morning (6-9 AM)', 'duration_hours': 3},
                'morning': {'start': 9, 'end': 12, 'label': 'Morning (9 AM-12 PM)', 'duration_hours': 3},
                'afternoon': {'start': 12, 'end': 18, 'label': 'Afternoon (12-6 PM)', 'duration_hours': 6},
                'prime_time': {'start': 18, 'end': 21, 'label': 'Prime Time (6-9 PM)', 'duration_hours': 3},
                'evening': {'start': 21, 'end': 24, 'label': 'Evening (9 PM-12 AM)', 'duration_hours': 3}
            },
            'replay_delays': {
                'id': 6,
                'spots': 12,
                'short_form': 24,
                'long_form': 48
            }
        }
    
    def setup_collections(self):
        """Setup MongoDB collections for schedules"""
        try:
            if db_manager.client is None:
                db_manager.connect()
            
            if db_manager.db is not None:
                self.schedule_collection = db_manager.db['schedules']
                logger.info("Schedule collection initialized")
            
        except Exception as e:
            logger.error(f"Error setting up schedule collections: {str(e)}")
    
    def setup_schedules_db(self):
        """Setup schedules database connection"""
        try:
            # Connect to schedules database
            if not schedules_db.connect():
                logger.error("Failed to connect to schedules database")
                return False
            
            # Create schedules collection/table if it doesn't exist
            if not schedules_db.create_schedules_collection():
                logger.error("Failed to create schedules collection")
                return False
            
            logger.info("Schedules database initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up schedules database: {str(e)}")
            return False
    
    def create_daily_schedule(self, schedule_date: str, timeslot: str = None, use_engagement_scoring: bool = True) -> Dict[str, Any]:
        """Create a daily schedule for a specific date and optionally timeslot. If no timeslot provided, creates for all timeslots."""
        if timeslot:
            logger.info(f"Creating schedule for {schedule_date} in {timeslot} timeslot (engagement scoring: {use_engagement_scoring})")
            return self.create_single_timeslot_schedule(schedule_date, timeslot, use_engagement_scoring)
        else:
            logger.info(f"Creating full daily schedule for {schedule_date} across all timeslots (engagement scoring: {use_engagement_scoring})")
            return self.create_full_daily_schedule(schedule_date, use_engagement_scoring)
    
    def create_single_timeslot_schedule(self, schedule_date: str, timeslot: str, use_engagement_scoring: bool = True) -> Dict[str, Any]:
        """Create a schedule for a single timeslot"""
        try:
            # Parse date
            target_date = datetime.strptime(schedule_date, '%Y-%m-%d')
            
            # Check if schedule already exists
            existing_schedule = self.get_schedule(schedule_date, timeslot)
            if existing_schedule:
                return {
                    'success': False,
                    'message': f'Schedule already exists for {schedule_date} {timeslot}',
                    'schedule_id': existing_schedule.get('schedule_id')
                }
            
            # Get available content for this timeslot
            available_content = self.get_available_content_for_timeslot(timeslot, target_date)
            
            if not available_content:
                return {
                    'success': False,
                    'message': f'No available content found for {timeslot} timeslot'
                }
            
            # Generate schedule using engagement-based algorithm
            if use_engagement_scoring:
                schedule_items = self.create_engagement_based_schedule(available_content, timeslot, target_date)
            else:
                schedule_items = self.create_basic_schedule(available_content, timeslot, target_date)
            
            # Create schedule document
            schedule_doc = {
                'schedule_id': str(uuid.uuid4()),
                'date': target_date,
                'timeslot': timeslot,
                'created_at': datetime.utcnow(),
                'created_by': 'ATL26_Scheduler',
                'engagement_scoring_enabled': use_engagement_scoring,
                'total_items': len(schedule_items),
                'total_duration': sum(item['duration'] for item in schedule_items),
                'items': schedule_items,
                'status': 'active'
            }
            
            # Save to both old and new database structures
            # Old MongoDB collection (for backward compatibility)
            result = self.schedule_collection.insert_one(schedule_doc)
            
            # New schedules table (for requirement compliance)
            schedule_table_data = {
                "date": schedule_date,
                "timeslot": timeslot,
                "created_by": "ATL26_Scheduler",
                "items": schedule_items
            }
            schedules_table_success = schedules_db.insert_schedule_items(schedule_table_data)
            
            if result.inserted_id and schedules_table_success:
                # Update content scheduling metadata
                self.update_content_scheduling_metadata(schedule_items, target_date, timeslot)
                
                logger.info(f"Successfully created schedule {schedule_doc['schedule_id']} with {len(schedule_items)} items")
                
                # Convert ObjectId to string for JSON serialization
                schedule_doc['_id'] = str(result.inserted_id)
                
                return {
                    'success': True,
                    'message': f'Schedule created successfully for {schedule_date} {timeslot}',
                    'schedule_id': schedule_doc['schedule_id'],
                    'schedule': self.convert_schedule_for_json(schedule_doc)
                }
            else:
                error_messages = []
                if not result.inserted_id:
                    error_messages.append("Failed to save to MongoDB")
                if not schedules_table_success:
                    error_messages.append("Failed to save to schedules table")
                
                return {
                    'success': False,
                    'message': f'Failed to save schedule: {", ".join(error_messages)}'
                }
                
        except Exception as e:
            error_msg = f"Error creating schedule: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg
            }
    
    def create_full_daily_schedule(self, schedule_date: str, use_engagement_scoring: bool = True) -> Dict[str, Any]:
        """Create schedules for all timeslots in a single day"""
        try:
            target_date = datetime.strptime(schedule_date, '%Y-%m-%d')
            created_schedules = []
            failed_timeslots = []
            
            # Define timeslot order for daily programming
            timeslots = ['overnight', 'early_morning', 'morning', 'afternoon', 'prime_time', 'evening']
            
            for timeslot in timeslots:
                try:
                    # Check if schedule already exists
                    existing_schedule = self.get_schedule(schedule_date, timeslot)
                    if existing_schedule:
                        logger.info(f"Schedule already exists for {schedule_date} {timeslot}, skipping")
                        continue
                    
                    # Create schedule for this timeslot
                    result = self.create_single_timeslot_schedule(schedule_date, timeslot, use_engagement_scoring)
                    
                    if result['success']:
                        created_schedules.append({
                            'timeslot': timeslot,
                            'schedule_id': result['schedule_id'],
                            'total_items': result['schedule']['total_items'],
                            'total_duration': result['schedule']['total_duration']
                        })
                        logger.info(f"✅ Created {timeslot} schedule with {result['schedule']['total_items']} items")
                    else:
                        failed_timeslots.append({
                            'timeslot': timeslot,
                            'error': result['message']
                        })
                        logger.warning(f"⚠️ Failed to create {timeslot} schedule: {result['message']}")
                        
                except Exception as e:
                    failed_timeslots.append({
                        'timeslot': timeslot,
                        'error': str(e)
                    })
                    logger.error(f"❌ Error creating {timeslot} schedule: {str(e)}")
            
            # Return results
            total_created = len(created_schedules)
            total_failed = len(failed_timeslots)
            
            if total_created > 0:
                return {
                    'success': True,
                    'message': f'Created {total_created} schedule(s) for {schedule_date}' + 
                              (f', {total_failed} failed' if total_failed > 0 else ''),
                    'created_schedules': created_schedules,
                    'failed_timeslots': failed_timeslots,
                    'total_created': total_created,
                    'total_failed': total_failed
                }
            else:
                return {
                    'success': False,
                    'message': f'Failed to create any schedules for {schedule_date}',
                    'failed_timeslots': failed_timeslots
                }
                
        except Exception as e:
            error_msg = f"Error creating daily schedule: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg
            }
    
    def get_available_content_for_timeslot(self, timeslot: str, target_date: datetime) -> List[Dict[str, Any]]:
        """Get content available for scheduling in a specific timeslot"""
        try:
            # Query for available content
            query = {
                "analysis_completed": True,
                "scheduling.available_for_scheduling": True,
                "scheduling.optimal_timeslots": {"$in": [timeslot]},
                "scheduling.content_expiry_date": {"$gt": target_date}
            }
            
            logger.info(f"Querying for content with query: {query}")
            logger.info(f"Target date: {target_date}, Timeslot: {timeslot}")
            
            # Get content from database
            cursor = db_manager.collection.find(query)
            all_content = list(cursor)
            
            # Filter based on replay delays
            available_content = []
            for content in all_content:
                if self.can_schedule_content(content, timeslot, target_date):
                    available_content.append(content)
            
            logger.info(f"Found {len(available_content)} available content items for {timeslot}")
            return available_content
            
        except Exception as e:
            logger.error(f"Error getting available content: {str(e)}")
            return []
    
    def can_schedule_content(self, content: Dict[str, Any], timeslot: str, target_date: datetime) -> bool:
        """Check if content can be scheduled based on replay delays"""
        try:
            scheduling = content.get('scheduling', {})
            duration_category = content.get('duration_category', 'short_form')
            
            # Get replay delay for this content category (in hours)
            replay_delay_hours = self.config['replay_delays'].get(duration_category, 24)
            
            # Check last scheduled date for this timeslot
            last_scheduled_key = f"last_scheduled_in_{timeslot}"
            last_scheduled = scheduling.get(last_scheduled_key)
            
            if last_scheduled and isinstance(last_scheduled, datetime):
                hours_since_last = (target_date - last_scheduled).total_seconds() / 3600
                if hours_since_last < replay_delay_hours:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking content scheduling eligibility: {str(e)}")
            return False
    
    def create_engagement_based_schedule(self, content_list: List[Dict[str, Any]], timeslot: str, target_date: datetime) -> List[Dict[str, Any]]:
        """Create schedule using AI engagement scoring"""
        logger.info(f"Creating engagement-based schedule with {len(content_list)} items")
        
        # Sort content by priority score and engagement score
        sorted_content = sorted(content_list, key=lambda x: (
            x.get('scheduling', {}).get('priority_score', 0),
            x.get('engagement_score', 0)
        ), reverse=True)
        
        # Get timeslot duration in seconds
        timeslot_config = self.config['timeslots'].get(timeslot, {})
        timeslot_duration_hours = timeslot_config.get('duration_hours', 3)
        total_available_seconds = timeslot_duration_hours * 3600
        
        # Create schedule balancing engagement and content variety
        schedule_items = []
        used_seconds = 0
        content_type_counts = {}
        
        for content in sorted_content:
            duration = content.get('file_duration', 0)
            content_type = content.get('content_type', 'UNKNOWN')
            
            # Check if we have time left
            if used_seconds + duration > total_available_seconds:
                continue
            
            # Ensure content type variety (max 3 of same type per schedule)
            type_count = content_type_counts.get(content_type, 0)
            if type_count >= 3:
                continue
            
            # Add to schedule
            schedule_item = {
                'content_id': str(content.get('_id')),
                'guid': content.get('guid'),
                'file_name': content.get('file_name'),
                'content_title': content.get('content_title'),
                'content_type': content_type,
                'duration': duration,
                'duration_category': content.get('duration_category'),
                'engagement_score': content.get('engagement_score', 0),
                'priority_score': content.get('scheduling', {}).get('priority_score', 0),
                'scheduled_time': used_seconds,  # Seconds from start of timeslot
                'order': len(schedule_items) + 1
            }
            
            schedule_items.append(schedule_item)
            used_seconds += duration
            content_type_counts[content_type] = type_count + 1
            
            # Fill about 80% of timeslot to allow for flexibility
            if used_seconds >= (total_available_seconds * 0.8):
                break
        
        logger.info(f"Created schedule with {len(schedule_items)} items, {used_seconds/60:.1f} minutes of {timeslot_duration_hours*60} minutes")
        return schedule_items
    
    def create_basic_schedule(self, content_list: List[Dict[str, Any]], timeslot: str, target_date: datetime) -> List[Dict[str, Any]]:
        """Create basic schedule without engagement scoring"""
        logger.info(f"Creating basic schedule with {len(content_list)} items")
        
        # Simple scheduling: random selection with duration constraints
        import random
        random.shuffle(content_list)
        
        # Get timeslot duration
        timeslot_config = self.config['timeslots'].get(timeslot, {})
        timeslot_duration_hours = timeslot_config.get('duration_hours', 3)
        total_available_seconds = timeslot_duration_hours * 3600
        
        schedule_items = []
        used_seconds = 0
        
        for content in content_list:
            duration = content.get('file_duration', 0)
            
            if used_seconds + duration > total_available_seconds:
                continue
            
            schedule_item = {
                'content_id': str(content.get('_id')),
                'guid': content.get('guid'),
                'file_name': content.get('file_name'),
                'content_title': content.get('content_title'),
                'content_type': content.get('content_type', 'UNKNOWN'),
                'duration': duration,
                'duration_category': content.get('duration_category'),
                'engagement_score': content.get('engagement_score', 0),
                'priority_score': 0,
                'scheduled_time': used_seconds,
                'order': len(schedule_items) + 1
            }
            
            schedule_items.append(schedule_item)
            used_seconds += duration
            
            if used_seconds >= (total_available_seconds * 0.8):
                break
        
        return schedule_items
    
    def update_content_scheduling_metadata(self, schedule_items: List[Dict[str, Any]], target_date: datetime, timeslot: str):
        """Update content scheduling metadata after creating schedule"""
        try:
            for item in schedule_items:
                content_id = item.get('content_id')
                if content_id:
                    # Update scheduling metadata
                    update_fields = {
                        '$set': {
                            'scheduling.last_scheduled_date': target_date,
                            f'scheduling.last_scheduled_in_{timeslot}': target_date
                        },
                        '$inc': {
                            'scheduling.total_airings': 1,
                            f'scheduling.replay_count_for_{timeslot}': 1
                        }
                    }
                    
                    # Update in database
                    from bson import ObjectId
                    db_manager.collection.update_one(
                        {'_id': ObjectId(content_id)},
                        update_fields
                    )
            
            logger.info(f"Updated scheduling metadata for {len(schedule_items)} content items")
            
        except Exception as e:
            logger.error(f"Error updating content scheduling metadata: {str(e)}")
    
    def get_schedule(self, date: str, timeslot: str = None) -> Optional[Dict[str, Any]]:
        """Get schedule for a specific date and optionally timeslot"""
        try:
            if self.schedule_collection is None:
                self.setup_collections()
                if self.schedule_collection is None:
                    return None
            
            # Parse date
            target_date = datetime.strptime(date, '%Y-%m-%d')
            
            # Build query
            query = {
                'date': {
                    '$gte': target_date,
                    '$lt': target_date + timedelta(days=1)
                },
                'status': 'active'
            }
            
            if timeslot:
                query['timeslot'] = timeslot
            
            # Get schedule
            schedule = self.schedule_collection.find_one(query)
            
            if schedule:
                # Convert ObjectId to string
                schedule['_id'] = str(schedule['_id'])
                return schedule
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting schedule: {str(e)}")
            return None
    
    def delete_schedule(self, schedule_id: str) -> Dict[str, Any]:
        """Delete a schedule by ID"""
        try:
            if self.schedule_collection is None:
                self.setup_collections()
                if self.schedule_collection is None:
                    return {'success': False, 'message': 'Database not connected'}
            
            # Find and delete schedule
            result = self.schedule_collection.update_one(
                {'schedule_id': schedule_id},
                {'$set': {'status': 'deleted', 'deleted_at': datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Successfully deleted schedule {schedule_id}")
                return {
                    'success': True,
                    'message': f'Schedule {schedule_id} deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'message': f'Schedule {schedule_id} not found'
                }
                
        except Exception as e:
            error_msg = f"Error deleting schedule: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
    
    def get_all_schedules(self, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """Get all schedules within a date range"""
        try:
            if self.schedule_collection is None:
                self.setup_collections()
                if self.schedule_collection is None:
                    return []
            
            query = {'status': 'active'}
            
            # Add date range filter if provided
            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter['$gte'] = datetime.strptime(start_date, '%Y-%m-%d')
                if end_date:
                    date_filter['$lte'] = datetime.strptime(end_date, '%Y-%m-%d')
                query['date'] = date_filter
            
            # Get schedules
            cursor = self.schedule_collection.find(query).sort('date', 1)
            schedules = list(cursor)
            
            # Convert ObjectIds to strings
            for schedule in schedules:
                schedule['_id'] = str(schedule['_id'])
            
            return schedules
            
        except Exception as e:
            logger.error(f"Error getting schedules: {str(e)}")
            return []
    
    def convert_schedule_for_json(self, schedule_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert schedule document for JSON serialization"""
        from datetime import datetime
        
        # Create a copy to avoid modifying the original
        json_doc = schedule_doc.copy()
        
        # Convert datetime objects to ISO strings
        if isinstance(json_doc.get('date'), datetime):
            json_doc['date'] = json_doc['date'].isoformat()
        if isinstance(json_doc.get('created_at'), datetime):
            json_doc['created_at'] = json_doc['created_at'].isoformat()
        
        return json_doc
    
    def create_weekly_schedule(self, start_date: str, use_engagement_scoring: bool = True) -> Dict[str, Any]:
        """Create schedules for an entire week (7 days) across all timeslots"""
        logger.info(f"Creating weekly schedule starting {start_date} (engagement scoring: {use_engagement_scoring})")
        
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            created_schedules = []
            failed_schedules = []
            
            for day_offset in range(7):  # 7 days in a week
                current_date = start_date_obj + timedelta(days=day_offset)
                current_date_str = current_date.strftime('%Y-%m-%d')
                
                logger.info(f"Creating daily schedule for {current_date_str}")
                
                # Create full daily schedule (all timeslots)
                daily_result = self.create_full_daily_schedule(current_date_str, use_engagement_scoring)
                
                if daily_result['success']:
                    created_schedules.extend([{
                        'date': current_date_str,
                        'day_of_week': current_date.strftime('%A'),
                        **schedule
                    } for schedule in daily_result.get('created_schedules', [])])
                    
                    # Track any failed timeslots from this day
                    if daily_result.get('failed_timeslots'):
                        failed_schedules.extend([{
                            'date': current_date_str,
                            'day_of_week': current_date.strftime('%A'),
                            **failed
                        } for failed in daily_result['failed_timeslots']])
                else:
                    failed_schedules.append({
                        'date': current_date_str,
                        'day_of_week': current_date.strftime('%A'),
                        'error': daily_result['message']
                    })
            
            # Calculate summary
            total_created = len(created_schedules)
            total_failed = len(failed_schedules)
            
            if total_created > 0:
                return {
                    'success': True,
                    'message': f'Created {total_created} schedule(s) for week starting {start_date}' + 
                              (f', {total_failed} failed' if total_failed > 0 else ''),
                    'created_schedules': created_schedules,
                    'failed_schedules': failed_schedules,
                    'total_created': total_created,
                    'total_failed': total_failed,
                    'week_start_date': start_date
                }
            else:
                return {
                    'success': False,
                    'message': f'Failed to create any schedules for week starting {start_date}',
                    'failed_schedules': failed_schedules
                }
                
        except Exception as e:
            error_msg = f"Error creating weekly schedule: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg
            }

# Global scheduler instance
scheduler = ATL26Scheduler()