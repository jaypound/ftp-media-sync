"""
Scheduled Jobs Module
Handles automated tasks using APScheduler with database locking
"""
import os
import logging
import socket
import json
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from psycopg2.extras import RealDictCursor
import psycopg2

# Import from app modules
from config_manager import ConfigManager
from ftp_manager import FTPManager
from castus_metadata import CastusMetadataHandler

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
        
    def start(self):
        """Start the scheduler with configured jobs"""
        # Check if scheduler is enabled in config
        scheduler_config = self.config_manager.get_scheduling_settings()
        self.enabled = scheduler_config.get('auto_sync_enabled', False)
        
        if not self.enabled:
            logger.info("Automatic sync scheduler is disabled in configuration")
            return
            
        # Schedule the Castus sync job at 9am, 12pm, 3pm, 6pm
        self.scheduler.add_job(
            func=self.sync_all_expirations_from_castus,
            trigger=CronTrigger(hour='9,12,15,18', minute=0),
            # trigger=CronTrigger(minute='*'),  # TEST MODE: every minute
            id='castus_sync_all',
            name='Copy All Expirations from Castus',
            misfire_grace_time=300,  # 5 minutes grace period
            max_instances=1  # Only one instance can run at a time
        )
        
        self.scheduler.start()
        logger.info("Scheduler started with automatic Castus sync at 9am, 12pm, 3pm, 6pm")
        logger.info(f"Next run time: {self.scheduler.get_job('castus_sync_all').next_run_time}")
        
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