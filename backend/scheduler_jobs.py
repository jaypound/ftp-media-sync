"""
Scheduled Jobs Module
Handles automated tasks using APScheduler with database locking
"""
import os
import logging
import socket
import json
import random
import re
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from psycopg2.extras import RealDictCursor
import psycopg2

# Import from app modules
from config_manager import ConfigManager
from ftp_manager import FTPManager
from castus_metadata import CastusMetadataHandler
from email_notifier import EmailNotifier
from host_verification import is_backend_host, get_host_info

# Setup dedicated logger for scheduler with file output
logger = logging.getLogger(__name__)
scheduler_file_handler = None

def setup_scheduler_logging():
    """Setup file logging for scheduler activities"""
    global scheduler_file_handler
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(os.path.dirname(__file__), 'logs', f'scheduler_{timestamp}.log')
    
    # Create logs directory if it doesn't exist
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    scheduler_file_handler = logging.FileHandler(log_file)
    scheduler_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(scheduler_file_handler)
    logger.setLevel(logging.DEBUG)
    
    logger.info("=== Scheduler logging initialized ===")
    return log_file

# Initialize logging on module load
log_file_path = setup_scheduler_logging()

class SchedulerJobs:
    def __init__(self, db_manager, config_manager: ConfigManager):
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.scheduler = BackgroundScheduler()
        self.hostname = socket.gethostname()
        self.enabled = False
        self.email_notifier = None
        self._setup_email_notifier()
        
    def _setup_email_notifier(self):
        """Setup email notifier from configuration"""
        scheduling_config = self.config_manager.get_scheduling_settings()
        email_config = scheduling_config.get('email_notifications', {})
        
        if email_config.get('enabled', False):
            # Get SMTP config from environment or config
            smtp_password = os.environ.get('SMTP_PASSWORD', '')
            if not smtp_password:
                logger.warning("Email notifications enabled but SMTP_PASSWORD not set")
                return
            
            smtp_config = {
                'smtp_server': email_config.get('smtp_server', 'mail.smtp2go.com'),
                'smtp_port': email_config.get('smtp_port', 2525),
                'smtp_username': email_config.get('smtp_username', 'alerts@atl26.atlantaga.gov'),
                'smtp_password': smtp_password,
                'from_email': email_config.get('from_email', 'alerts@atl26.atlantaga.gov'),
                'use_tls': email_config.get('use_tls', True),
                'use_ssl': email_config.get('use_ssl', False)
            }
            
            self.email_notifier = EmailNotifier(smtp_config)
            self.notification_recipients = email_config.get('recipients', [])
            logger.info(f"Email notifications enabled for {len(self.notification_recipients)} recipients")
        else:
            logger.info("Email notifications disabled")
    
    def start(self):
        """Start the scheduler with configured jobs"""
        # Scheduler now always starts - individual jobs check their own enabled status
        
        # CASTUS SYNC JOB REMOVED - No longer scheduling automatic expiration sync
        # # Schedule the Castus sync job at 9am, 12pm, 3pm, 6pm
        # self.scheduler.add_job(
        #     func=self.sync_all_expirations_from_castus,
        #     trigger=CronTrigger(hour='9,12,15,18', minute=0),
        #     # trigger=CronTrigger(minute='*'),  # TEST MODE: every minute
        #     id='castus_sync_all',
        #     name='Copy All Expirations from Castus',
        #     misfire_grace_time=300,  # 5 minutes grace period
        #     max_instances=1  # Only one instance can run at a time
        # )
        
        # Schedule the meeting video generation check every minute
        self.scheduler.add_job(
            func=self.check_meetings_for_video_generation,
            trigger=CronTrigger(minute='*'),  # Every minute
            id='meeting_video_generation',
            name='Check Meetings for Video Generation',
            misfire_grace_time=30,  # 30 seconds grace period
            max_instances=1  # Only one instance can run at a time
        )
        
        self.scheduler.start()
        logger.info("Scheduler started")
        logger.info("Meeting video generation check runs every minute")
        logger.info(f"Next video check: {self.scheduler.get_job('meeting_video_generation').next_run_time}")
        
        # List all jobs
        jobs = self.scheduler.get_jobs()
        logger.info(f"Active jobs: {len(jobs)}")
        for job in jobs:
            logger.info(f"  - {job.name} (ID: {job.id})")
        
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
            
    def acquire_job_lock(self, job_name: str, lock_duration_minutes: int = 30) -> bool:
        """
        Acquire a lock for a job using database row locking
        Returns True if lock acquired, False otherwise
        """
        conn = self.db_manager._get_connection()
        try:
            # Use regular cursor, not RealDictCursor
            with conn.cursor(cursor_factory=None) as cursor:
                # Try to acquire lock with SELECT FOR UPDATE SKIP LOCKED
                cursor.execute("""
                    SELECT id, lock_expires_at 
                    FROM sync_jobs 
                    WHERE job_name = %s
                    FOR UPDATE SKIP LOCKED
                """, (job_name,))
                
                row = cursor.fetchone()
                if not row:
                    # Another process has the lock
                    logger.info(f"Could not acquire lock for job {job_name} - locked by another process")
                    return False
                
                # Debug the row contents
                logger.debug(f"Raw row data: {row}")
                logger.debug(f"Row type: {type(row)}, length: {len(row) if row else 0}")
                
                # Handle RealDictRow which behaves like both dict and tuple
                if hasattr(row, 'values'):
                    # It's a RealDictRow, get values by key
                    job_id = row['id']
                    lock_expires_at = row['lock_expires_at']
                else:
                    # Regular tuple
                    job_id, lock_expires_at = row
                
                # Validate job_id
                if not isinstance(job_id, int):
                    logger.error(f"Invalid job_id type: {type(job_id)}, value: {job_id}")
                    logger.error(f"Full row data: {row}")
                    return False
                
                # Check if existing lock has expired
                if lock_expires_at is not None:
                    # PostgreSQL returns datetime objects, not strings
                    # If we somehow get a string, log it and treat as no lock
                    if not isinstance(lock_expires_at, datetime):
                        logger.warning(f"Unexpected lock_expires_at type: {type(lock_expires_at)}, value: {lock_expires_at}")
                        # Treat as no lock
                        lock_expires_at = None
                    else:
                        # Ensure timezone awareness
                        if lock_expires_at.tzinfo is None:
                            lock_expires_at = lock_expires_at.replace(tzinfo=timezone.utc)
                        
                        if lock_expires_at > datetime.now(timezone.utc):
                            logger.info(f"Job {job_name} is already running, expires at {lock_expires_at}")
                            return False
                    
                # Acquire the lock
                lock_expires = datetime.now(timezone.utc) + timedelta(minutes=lock_duration_minutes)
                cursor.execute("""
                    UPDATE sync_jobs 
                    SET lock_acquired_at = CURRENT_TIMESTAMP,
                        lock_expires_at = %s,
                        last_run_by = %s,
                        last_run_status = 'running'
                    WHERE id = %s
                """, (lock_expires, self.hostname, job_id))
                
                conn.commit()
                logger.info(f"Acquired lock for job {job_name} until {lock_expires}")
                return True
                
        except Exception as e:
            logger.error(f"Error acquiring job lock: {str(e)}")
            conn.rollback()
            return False
        finally:
            self.db_manager._put_connection(conn)
            
    def release_job_lock(self, job_name: str, status: str = 'completed', details: dict = None):
        """Release a job lock and update status"""
        conn = self.db_manager._get_connection()
        try:
            # Use regular cursor, not RealDictCursor
            with conn.cursor(cursor_factory=None) as cursor:
                cursor.execute("""
                    UPDATE sync_jobs 
                    SET lock_acquired_at = NULL,
                        lock_expires_at = NULL,
                        last_run_at = CURRENT_TIMESTAMP,
                        last_run_status = %s,
                        last_run_details = %s
                    WHERE job_name = %s
                """, (status, json.dumps(details or {}), job_name))
                
                conn.commit()
                logger.info(f"Released lock for job {job_name} with status {status}")
                
        except Exception as e:
            logger.error(f"Error releasing job lock: {str(e)}")
            conn.rollback()
        finally:
            self.db_manager._put_connection(conn)
            
    def sync_all_expirations_from_castus(self):
        """
        Scheduled job to sync all expiration dates from Castus
        This runs at configured times and uses database locking
        """
        job_name = 'castus_expiration_sync_all'
        
        # Force flush to ensure logging works
        for handler in logger.handlers:
            handler.flush()
            
        logger.info("="*80)
        logger.info(f"STARTING SCHEDULED JOB: {job_name}")
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        
        # Force flush again
        for handler in logger.handlers:
            handler.flush()
        
        # Try to acquire lock
        if not self.acquire_job_lock(job_name):
            logger.info(f"Skipping {job_name} - another instance is already running")
            return
            
        try:
            # Get content expiration configuration
            scheduling_config = self.config_manager.get_scheduling_settings()
            content_expiration_config = scheduling_config.get('content_expiration', {})
            
            logger.info("Content Expiration Configuration:")
            for ct, days in content_expiration_config.items():
                logger.info(f"  {ct}: {days} days")
            
            # Get all content types
            content_types = ['AN', 'ATLD', 'BMP', 'IMOW', 'IM', 'IA', 'LM', 'MTG', 'MAF', 'PKG', 'PMO', 'PSA', 'SZL', 'SPP', 'OTHER']
            
            # Track results
            results = {
                'total_synced': 0,
                'total_updated': 0,
                'total_errors': 0,
                'total_changes': [],
                'by_type': {}
            }
            
            # Process each content type
            for ct in content_types:
                type_results = self._sync_content_type_expirations(ct, content_expiration_config.get(ct, 0))
                results['by_type'][ct] = type_results
                results['total_synced'] += type_results['synced']
                results['total_updated'] += type_results['updated']
                results['total_errors'] += type_results['errors']
                if 'changes' in type_results:
                    results['total_changes'].extend(type_results['changes'])
                
            # Log final summary
            logger.info("="*80)
            logger.info("JOB COMPLETE - FINAL SUMMARY:")
            logger.info(f"  Total files processed: {results['total_synced']}")
            logger.info(f"  Total expiration dates changed: {results['total_updated']}")
            logger.info(f"  Total errors: {results['total_errors']}")
            
            if len(results['total_changes']) > 0:
                logger.info(f"\nAll Changes Made ({len(results['total_changes'])} total):")
                for i, change in enumerate(results['total_changes'][:50]):  # Show first 50
                    logger.info(f"  {i+1}. {change['file']}: {change['old']} → {change['new']} ({change['source']})")
                if len(results['total_changes']) > 50:
                    logger.info(f"  ... and {len(results['total_changes']) - 50} more changes")
            else:
                logger.info("\nNo expiration date changes were needed.")
                
            logger.info("="*80)
            
            # Release lock with results
            self.release_job_lock(job_name, 'completed', results)
            
        except Exception as e:
            logger.error(f"Error in scheduled sync: {str(e)}")
            self.release_job_lock(job_name, 'failed', {'error': str(e)})
            
    def _sync_content_type_expirations(self, content_type: str, expiration_days: int) -> dict:
        """Sync expiration dates for a specific content type"""
        logger.info(f"=== Processing {content_type} (expiration_days={expiration_days}) ===")
        
        # Get server configuration (default to source)
        server_config = self.config_manager.get_server_config('source')
        if not server_config:
            logger.error("Source server configuration not found")
            return {'synced': 0, 'updated': 0, 'errors': 1}
            
        # Initialize FTP connection for Castus metadata
        ftp = None
        if expiration_days == 0:
            logger.info(f"Will copy expiration dates from Castus metadata for {content_type}")
            ftp = FTPManager(server_config)
            if not ftp.connect():
                logger.error("Failed to connect to source server")
                return {'synced': 0, 'updated': 0, 'errors': 1}
        else:
            logger.info(f"Will calculate expiration as creation_date + {expiration_days} days for {content_type}")
        
        # Track results
        synced = 0
        updated = 0
        errors = 0
        changes_made = []
        
        conn = self.db_manager._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get all assets of this content type
                ct_lower = content_type.lower()
                cursor.execute("""
                    SELECT a.id, i.file_path, i.file_name, a.content_title, i.encoded_date,
                           sm.content_expiry_date as current_expiry
                    FROM assets a
                    JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE a.content_type = %s
                    AND a.analysis_completed = true
                    ORDER BY a.id
                """, (ct_lower,))
                
                assets = cursor.fetchall()
                logger.info(f"Found {len(assets)} {content_type} assets to sync")
                
                for asset in assets:
                    asset_id = asset['id']
                    file_name = asset['file_name']
                    file_path = asset['file_path'] or file_name
                    current_expiry = asset['current_expiry']
                    
                    if not file_path:
                        errors += 1
                        continue
                        
                    try:
                        expiry_date = None
                        go_live_date = None
                        source = None
                        
                        if expiration_days == 0 and ftp:
                            # Get from Castus metadata
                            handler = CastusMetadataHandler(ftp)
                            expiry_date = handler.get_content_window_close(file_path)
                            go_live_date = handler.get_content_window_open(file_path)
                            source = "Castus metadata"
                        else:
                            # Calculate based on creation date
                            creation_date = self._extract_creation_date(file_name, asset['encoded_date'])
                            if creation_date:
                                expiry_date = creation_date + timedelta(days=expiration_days)
                                source = f"calculated from {creation_date.date()} + {expiration_days} days"
                            else:
                                logger.warning(f"No creation date for {file_name}, skipping")
                                continue
                                
                        # Check if value changed
                        changed = False
                        old_expiry_str = current_expiry.strftime('%Y-%m-%d') if current_expiry else 'None'
                        new_expiry_str = expiry_date.strftime('%Y-%m-%d') if expiry_date else 'None'
                        
                        if old_expiry_str != new_expiry_str:
                            changed = True
                            logger.info(f"  {file_name}: {old_expiry_str} → {new_expiry_str} ({source})")
                            changes_made.append({
                                'file': file_name,
                                'old': old_expiry_str,
                                'new': new_expiry_str,
                                'source': source
                            })
                                
                        # Update database
                        with conn.cursor(cursor_factory=None) as update_cursor:
                            update_cursor.execute("""
                                UPDATE scheduling_metadata 
                                SET content_expiry_date = %s,
                                    go_live_date = %s,
                                    metadata_synced_at = CURRENT_TIMESTAMP
                                WHERE asset_id = %s
                            """, (expiry_date, go_live_date, asset_id))
                            
                            if update_cursor.rowcount == 0:
                                # Create record if doesn't exist
                                update_cursor.execute("""
                                    INSERT INTO scheduling_metadata 
                                    (asset_id, content_expiry_date, go_live_date, metadata_synced_at)
                                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                                """, (asset_id, expiry_date, go_live_date))
                                
                        conn.commit()
                        synced += 1
                        if expiry_date or go_live_date:
                            if changed:
                                updated += 1
                            
                    except Exception as e:
                        logger.error(f"Error syncing asset {asset_id} ({file_name}): {str(e)}")
                        errors += 1
                
                # Log summary for this content type        
                logger.info(f"{content_type} Summary: {synced} synced, {updated} changed, {errors} errors")
                if len(changes_made) > 0:
                    logger.info(f"  Total changes made: {len(changes_made)}")
                else:
                    logger.info(f"  No expiration date changes needed")
                        
        finally:
            if ftp:
                ftp.disconnect()
            self.db_manager._put_connection(conn)
            
        return {'synced': synced, 'updated': updated, 'errors': errors, 'changes': changes_made}
        
    def _extract_creation_date(self, filename: str, encoded_date):
        """Extract creation date from filename or encoded date"""
        # First try encoded date
        if encoded_date:
            return encoded_date
            
        # Try to extract from filename (YYMMDD format)
        if filename and len(filename) >= 6 and filename[:6].isdigit():
            try:
                yy = int(filename[0:2])
                mm = int(filename[2:4])
                dd = int(filename[4:6])
                
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    # Convert 2-digit year
                    year = 1900 + yy if yy >= 90 else 2000 + yy
                    return datetime(year, mm, dd, tzinfo=timezone.utc)
            except (ValueError, IndexError):
                pass
                
        return None
    
    def check_meetings_for_video_generation(self):
        """Check for meetings that need video generation"""
        # First check if we're the backend host
        if not is_backend_host():
            logger.debug("Not backend host, skipping video generation check")
            return
        
        # Check if auto generation is enabled
        config = self.get_auto_generation_config()
        if not config or not config.get('enabled', False):
            logger.debug("Auto video generation is disabled")
            return
        
        # Check time constraints
        now = datetime.now()
        if not self.is_valid_generation_time(now, config):
            logger.debug(f"Outside valid generation window (weekdays {config['start_hour']}-{config['end_hour']})")
            return
        
        # Find meetings that started X minutes ago (default 2)
        delay_minutes = config.get('delay_minutes', 2)
        meetings = self.find_meetings_for_generation(delay_minutes)
        
        if meetings:
            logger.info(f"Found {len(meetings)} meeting(s) that need video generation")
        
        for meeting in meetings:
            try:
                logger.info(f"Generating video for meeting: {meeting['meeting_name']}")
                self.generate_video_for_meeting(meeting, config)
            except Exception as e:
                logger.error(f"Failed to generate video for meeting {meeting['id']}: {str(e)}", exc_info=True)
    
    def get_auto_generation_config(self):
        """Get auto generation configuration from database"""
        conn = self.db_manager._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM auto_generation_config LIMIT 1")
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting auto generation config: {e}")
            return None
        finally:
            self.db_manager._put_connection(conn)
    
    def is_valid_generation_time(self, dt, config):
        """Check if current time is within allowed generation window"""
        # Check weekday (0=Monday, 4=Friday)
        if config['weekdays_only'] and dt.weekday() > 4:
            return False
        
        # Check hour range
        current_hour = dt.hour
        if current_hour < config['start_hour'] or current_hour >= config['end_hour']:
            return False
        
        return True
    
    def find_meetings_for_generation(self, delay_minutes):
        """Find meetings that started X minutes ago and need video generation"""
        conn = self.db_manager._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Calculate target time (X minutes ago)
                target_time = datetime.now() - timedelta(minutes=delay_minutes)
                target_start = target_time - timedelta(minutes=1)  # 1 minute window
                target_end = target_time + timedelta(minutes=1)
                
                # Find meetings that:
                # 1. Are scheduled for today
                # 2. Started within our target window
                # 3. Haven't had a video generated today
                cursor.execute("""
                    SELECT m.* 
                    FROM meetings m
                    WHERE m.meeting_date = CURRENT_DATE
                    AND m.start_time BETWEEN %s::time AND %s::time
                    AND NOT EXISTS (
                        SELECT 1 FROM meeting_video_generations mvg
                        WHERE mvg.meeting_id = m.id
                        AND DATE(mvg.generation_timestamp) = CURRENT_DATE
                        AND mvg.status IN ('generating', 'completed')
                    )
                """, (target_start.time(), target_end.time()))
                
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error finding meetings for generation: {e}")
            return []
        finally:
            self.db_manager._put_connection(conn)
    
    def generate_video_for_meeting(self, meeting, config):
        """Generate fill graphics video for a meeting"""
        conn = self.db_manager._get_connection()
        generation_id = None
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Create generation record
                cursor.execute("""
                    INSERT INTO meeting_video_generations 
                    (meeting_id, status, generated_by_host, sort_order)
                    VALUES (%s, 'generating', %s, %s)
                    RETURNING id
                """, (meeting['id'], socket.gethostname(), 'pending'))
                generation_id = cursor.fetchone()['id']
                conn.commit()
                
                # Get active graphics count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM default_graphics
                    WHERE status = 'active' 
                    AND start_date <= CURRENT_DATE 
                    AND (end_date IS NULL OR end_date >= CURRENT_DATE)
                """)
                graphic_count = cursor.fetchone()['count']
                
                if graphic_count == 0:
                    raise Exception("No active graphics available")
                
                # Calculate duration based on active graphics
                # Gap duration: minimum 5 minutes (300 seconds) or 10 seconds per graphic
                gap_duration = max(300, graphic_count * 10)
                # Video duration is gap + 60 seconds
                duration = gap_duration + 60
                
                logger.info(f"Auto generation: {graphic_count} graphics, gap={gap_duration}s, video={duration}s")
                
                # Get next sort order
                sort_order = self.get_next_sort_order()
                
                # Update generation record with sort order and duration
                cursor.execute("""
                    UPDATE meeting_video_generations
                    SET sort_order = %s, duration_seconds = %s, graphics_count = %s
                    WHERE id = %s
                """, (sort_order, duration, graphic_count, generation_id))
                
                # Generate filename using YYMMDDHHMI_FILL_<sort_order>_<duration_seconds>.mp4
                # sort_order will always be 'alphabetical' now that rotation is disabled
                timestamp = datetime.now().strftime('%y%m%d%H%M')  # YYMMDDHHMI format
                file_name = f'{timestamp}_FILL_{sort_order}_{duration}.mp4'
                
                # Import and call the video generation function
                from app import generate_default_graphics_video_internal
                
                result = generate_default_graphics_video_internal({
                    'file_name': file_name,
                    'export_path': '/mnt/main/Videos',  # Correct path on FTP servers
                    'sort_order': sort_order,
                    'max_length': duration,
                    'export_to_source': True,
                    'export_to_target': True,  # Export to both servers
                    'auto_generated': True,
                    'meeting_id': meeting['id'],
                    # Default selections for auto generation
                    'region2_file': 'ATL26 SQUEEZEBACK SKYLINE WITH SOCIAL HANDLES.png',
                    'region3_files': 'all_wav'  # Special flag to select all WAV files
                })
                
                # Update generation record with success
                cursor.execute("""
                    UPDATE meeting_video_generations
                    SET status = 'completed', video_id = %s
                    WHERE id = %s
                """, (result.get('video_id'), generation_id))
                conn.commit()
                
                logger.info(f"Successfully generated video for meeting {meeting['meeting_name']}: {file_name}")
                
        except Exception as e:
            logger.error(f"Failed to generate video for meeting {meeting['id']}: {str(e)}")
            if generation_id:
                try:
                    # Get a new connection for the update since the original might be corrupted
                    update_conn = self.db_manager._get_connection()
                    try:
                        with update_conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE meeting_video_generations
                                SET status = 'failed', error_message = %s
                                WHERE id = %s
                            """, (str(e), generation_id))
                            update_conn.commit()
                    finally:
                        self.db_manager._put_connection(update_conn)
                except Exception as update_error:
                    logger.error(f"Failed to update generation status: {update_error}")
            raise
        finally:
            try:
                self.db_manager._put_connection(conn)
            except Exception as pool_error:
                logger.error(f"Error returning connection to pool: {pool_error}")
                # Connection might already be closed or invalid, ignore the error
    
    def get_next_sort_order(self):
        """Get the next sort order - DISABLED ROTATION, always returns alphabetical"""
        # ROTATION DISABLED - Always use alphabetical (reverse) sort order
        return 'alphabetical'
        
        # COMMENTED OUT - Original rotation logic
        # SORT_ORDERS = ['alphabetical', 'newest', 'oldest', 'creation', 'random']
        # 
        # conn = self.db_manager._get_connection()
        # try:
        #     with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        #         # Get the most recent video's sort order
        #         cursor.execute("""
        #             SELECT generation_params
        #             FROM generated_default_videos
        #             ORDER BY generation_date DESC
        #             LIMIT 1
        #         """)
        #         
        #         last_video = cursor.fetchone()
        #         if not last_video:
        #             return 'alphabetical'
        #         
        #         try:
        #             params = json.loads(last_video['generation_params'] or '{}')
        #             last_sort = params.get('sort_order', 'alphabetical')
        #             
        #             # If last was random, pick any other
        #             if last_sort == 'random':
        #                 return random.choice([s for s in SORT_ORDERS if s != 'random'])
        #             
        #             # Otherwise, get next in rotation
        #             if last_sort in SORT_ORDERS:
        #                 current_index = SORT_ORDERS.index(last_sort)
        #                 next_index = (current_index + 1) % len(SORT_ORDERS)
        #                 return SORT_ORDERS[next_index]
        #             else:
        #                 return 'alphabetical'
        #                 
        #         except (json.JSONDecodeError, ValueError):
        #             return 'alphabetical'
        #             
        # except Exception as e:
        #     logger.error(f"Error getting next sort order: {e}")
        #     return 'alphabetical'
        # finally:
        #     self.db_manager._put_connection(conn)
    
    def sanitize_filename(self, name):
        """Sanitize filename by removing invalid characters"""
        # Remove or replace invalid filename characters
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Replace multiple spaces/underscores with single underscore
        name = re.sub(r'[_\s]+', '_', name)
        # Limit length
        return name[:50].strip('_')
