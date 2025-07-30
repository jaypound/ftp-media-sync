from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from dotenv import load_dotenv
from ftp_manager import FTPManager
from file_scanner import FileScanner
from config_manager import ConfigManager
from file_analyzer import file_analyzer
from database import db_manager
# from scheduler import scheduler  # MongoDB scheduler - no longer used
from scheduler_postgres import scheduler_postgres
import logging
from bson import ObjectId
from datetime import datetime, timedelta
import uuid

# Load environment variables from .env file
load_dotenv()

def convert_objectid_to_string(obj):
    """Convert ObjectId and datetime objects to JSON serializable format"""
    from datetime import date, time
    from decimal import Decimal
    
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, time):
        return obj.strftime('%H:%M:%S')
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_string(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_string(item) for item in obj]
    return obj

app = Flask(__name__)

# Configure CORS to allow requests from the frontend
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://127.0.0.1:8000", "http://localhost:8000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global managers
ftp_managers = {}
config_manager = ConfigManager()

# Initialize database connection
db_manager.connect()

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        config = config_manager.get_all_config()
        # Include passwords in response for frontend convenience
        # Note: This is acceptable since communication is over localhost
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        logger.error(f"Error getting config: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/config', methods=['POST'])
def save_config():
    """Save configuration"""
    try:
        data = request.json
        
        if 'servers' in data:
            for server_type, server_config in data['servers'].items():
                config_manager.update_server_config(server_type, server_config)
        
        if 'sync_settings' in data:
            config_manager.update_sync_settings(data['sync_settings'])
        
        if 'scheduling' in data:
            config_manager.update_scheduling_settings(data['scheduling'])
        
        return jsonify({'success': True, 'message': 'Configuration saved'})
    except Exception as e:
        logger.error(f"Error saving config: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/config/sample', methods=['POST'])
def create_sample_config():
    """Create a sample configuration file"""
    try:
        success = config_manager.create_sample_config()
        if success:
            return jsonify({'success': True, 'message': 'Sample config created: config.sample.json'})
        else:
            return jsonify({'success': False, 'message': 'Failed to create sample config'})
    except Exception as e:
        logger.error(f"Error creating sample config: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    logger.info("=== TEST CONNECTION REQUEST ===")
    try:
        data = request.json
        logger.info(f"Received data: {data}")
        
        server_type = data.get('server_type')
        logger.info(f"Server type: {server_type}")
        
        ftp_config = {
            'host': data.get('host'),
            'port': int(data.get('port', 21)),
            'user': data.get('user'),
            'password': '***', # Don't log passwords
            'path': data.get('path', '/')  # Include the path field
        }
        
        logger.info(f"FTP config: host={ftp_config['host']}, port={ftp_config['port']}, user={ftp_config['user']}, path={ftp_config['path']}")
        
        # Create FTP manager with actual password
        ftp_config['password'] = data.get('password')
        ftp_manager = FTPManager(ftp_config)
        
        logger.info("Attempting FTP connection...")
        success = ftp_manager.test_connection()
        logger.info(f"Connection result: {success}")
        
        if success:
            ftp_managers[server_type] = ftp_manager
            response = {'success': True, 'message': f'Connected to {server_type} server successfully'}
            logger.info(f"SUCCESS: {response}")
            return jsonify(response)
        else:
            response = {'success': False, 'message': f'Failed to connect to {server_type} server'}
            logger.error(f"FAILURE: {response}")
            return jsonify(response)
            
    except Exception as e:
        error_msg = f"Connection test error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/scan-files', methods=['POST'])
def scan_files():
    logger.info("=== SCAN FILES REQUEST ===")
    try:
        data = request.json
        logger.info(f"Scan data: {data}")
        
        server_type = data.get('server_type')
        path = data.get('path')
        filters = data.get('filters', {})
        
        logger.info(f"Server: {server_type}, Path: {path}, Filters: {filters}")
        
        if server_type not in ftp_managers:
            error_msg = f'{server_type} server not connected'
            logger.error(error_msg)
            return jsonify({'success': False, 'message': error_msg})
        
        scanner = FileScanner(ftp_managers[server_type])
        logger.info("Starting file scan...")
        files = scanner.scan_directory(path, filters)
        logger.info(f"Found {len(files)} files")
        
        # Check analysis status for all files
        logger.info("Checking analysis status for scanned files...")
        analyzed_files = db_manager.check_analysis_status(files)
        
        # Create a lookup map for analyzed files
        analyzed_map = {af['file_path']: af for af in analyzed_files}
        
        # Add analysis status to each file
        for file_info in files:
            file_path = file_info.get('path', file_info.get('name', ''))
            file_info['is_analyzed'] = file_path in analyzed_map
            if file_info['is_analyzed']:
                file_info['analysis_info'] = analyzed_map[file_path]
        
        analyzed_count = len(analyzed_files)
        logger.info(f"Analysis status check completed: {analyzed_count}/{len(files)} files analyzed")
        
        return jsonify({
            'success': True, 
            'files': files,
            'count': len(files),
            'analyzed_count': analyzed_count
        })
        
    except Exception as e:
        error_msg = f"Scan error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/sync-files', methods=['POST'])
def sync_files():
    logger.info("=== SYNC FILES REQUEST ===")
    try:
        data = request.json
        sync_queue = data.get('sync_queue', [])
        dry_run = data.get('dry_run', True)
        keep_temp_files = data.get('keep_temp_files', False)
        
        logger.info(f"Sync queue length: {len(sync_queue)}, Dry run: {dry_run}, Keep temp files: {keep_temp_files}")
        
        if 'source' not in ftp_managers or 'target' not in ftp_managers:
            error_msg = 'Both servers must be connected'
            logger.error(error_msg)
            return jsonify({'success': False, 'message': error_msg})
        
        source_ftp = ftp_managers['source']
        target_ftp = ftp_managers['target']
        
        results = []
        
        for item in sync_queue:
            file_info = item['file']
            action = item['type']
            filename = file_info['name']
            relative_path = file_info.get('path', filename)
            
            logger.info(f"Processing file: {filename}")
            logger.info(f"  Relative path: {relative_path}")
            logger.info(f"  Full path: {file_info.get('full_path', 'Not set')}")
            logger.info(f"  Action: {action}")
            logger.info(f"  Dry run: {dry_run}")
            
            try:
                if dry_run:
                    results.append({
                        'file': filename,
                        'action': action,
                        'status': 'would_sync',
                        'size': file_info['size']
                    })
                    logger.info(f"  Would sync {filename}")
                else:
                    logger.info(f"  Starting actual sync for {filename}")
                    
                    # Perform actual sync
                    try:
                        if action == 'copy':
                            logger.info(f"  Copying file: {filename}")
                            success = source_ftp.copy_file_to(file_info, target_ftp, keep_temp=keep_temp_files)
                        else:  # update
                            logger.info(f"  Updating file: {filename}")
                            success = source_ftp.update_file_to(file_info, target_ftp, keep_temp=keep_temp_files)
                        
                        logger.info(f"  Sync result for {filename}: {success}")
                        
                        if success:
                            results.append({
                                'file': filename,
                                'action': action,
                                'status': 'success',
                                'size': file_info['size']
                            })
                            logger.info(f"  ✅ Successfully synced {filename}")
                        else:
                            results.append({
                                'file': filename,
                                'action': action,
                                'status': 'failed',
                                'error': 'File transfer failed - check FTP connection and permissions',
                                'details': f'Failed to {action} {relative_path}'
                            })
                            logger.error(f"  ❌ Failed to sync {filename}")
                            
                    except Exception as sync_error:
                        error_msg = str(sync_error)
                        logger.error(f"  ❌ Sync exception for {filename}: {error_msg}", exc_info=True)
                        
                        results.append({
                            'file': filename,
                            'action': action,
                            'status': 'failed',
                            'error': error_msg,
                            'details': f'Exception during {action} of {relative_path}'
                        })
                    
            except Exception as item_error:
                error_msg = str(item_error)
                logger.error(f"Error processing item {filename}: {error_msg}", exc_info=True)
                
                results.append({
                    'file': filename,
                    'action': action,
                    'status': 'error',
                    'error': error_msg,
                    'details': f'Error processing sync item for {relative_path}'
                })
        
        logger.info(f"Sync completed. Results: {len(results)} items processed")
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        error_msg = f"Sync error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg, 'details': error_msg})

@app.route('/api/analysis-status', methods=['POST'])
def get_analysis_status():
    """Get analysis status for a list of files"""
    logger.info("=== ANALYSIS STATUS REQUEST ===")
    try:
        data = request.json
        files = data.get('files', [])
        
        logger.info(f"Checking analysis status for {len(files)} files")
        
        # Connect to database if not already connected
        if db_manager.collection is None:
            success = db_manager.connect()
            if not success:
                return jsonify({
                    'success': False, 
                    'message': 'Failed to connect to database'
                })
        
        # Get analysis status
        status_result = file_analyzer.get_analysis_status(files)
        
        if status_result.get('success'):
            logger.info(f"Analysis status: {status_result['analyzed_count']}/{status_result['total_count']} files analyzed")
            # Convert any ObjectId objects to strings before returning
            safe_result = convert_objectid_to_string(status_result)
            return jsonify(safe_result)
        else:
            logger.error(f"Failed to get analysis status: {status_result.get('error')}")
            return jsonify(status_result)
            
    except Exception as e:
        error_msg = f"Analysis status error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/delete-files', methods=['POST'])
def delete_files():
    """Delete selected files from target server"""
    logger.info("=== DELETE FILES REQUEST ===")
    try:
        data = request.json
        files = data.get('files', [])
        server_type = data.get('server_type', 'target')
        dry_run = data.get('dry_run', True)
        
        logger.info(f"Deleting {len(files)} files from {server_type} server (dry_run: {dry_run})")
        
        # Check if server is connected
        if server_type not in ftp_managers:
            return jsonify({
                'success': False, 
                'message': f'{server_type} server not connected'
            })
        
        # Get the FTP manager
        ftp_manager = ftp_managers[server_type]
        
        results = []
        success_count = 0
        failure_count = 0
        
        for file_info in files:
            file_path = file_info.get('path', file_info.get('name', ''))
            file_name = file_info.get('name', '')
            
            logger.info(f"Processing delete for: {file_name} (path: {file_path})")
            
            if dry_run:
                # Simulate deletion
                results.append({
                    'success': True,
                    'message': f'Would delete: {file_name}',
                    'file_name': file_name,
                    'file_path': file_path,
                    'dry_run': True
                })
                success_count += 1
            else:
                # Actually delete the file
                success = ftp_manager.delete_file(file_path)
                
                if success:
                    results.append({
                        'success': True,
                        'message': f'Successfully deleted: {file_name}',
                        'file_name': file_name,
                        'file_path': file_path
                    })
                    success_count += 1
                else:
                    results.append({
                        'success': False,
                        'message': f'Failed to delete: {file_name}',
                        'file_name': file_name,
                        'file_path': file_path
                    })
                    failure_count += 1
        
        logger.info(f"Delete operation completed: {success_count} successful, {failure_count} failed")
        
        return jsonify({
            'success': True,
            'results': results,
            'success_count': success_count,
            'failure_count': failure_count,
            'total_count': len(files),
            'dry_run': dry_run
        })
        
    except Exception as e:
        error_msg = f"Delete error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/clear-all-analyses', methods=['POST'])
def clear_all_analyses():
    """Clear all analysis data from the database"""
    logger.info("=== CLEAR ALL ANALYSES REQUEST ===")
    try:
        # Connect to database if not already connected
        if db_manager.collection is None:
            success = db_manager.connect()
            if not success:
                return jsonify({
                    'success': False, 
                    'message': 'Failed to connect to database'
                })
        
        # Clear all analysis data
        result = db_manager.clear_all_analyses()
        
        logger.info(f"Clear all analyses result: {result}")
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Clear all analyses error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({
            'success': False, 
            'message': error_msg,
            'deleted_count': 0
        })

@app.route('/api/analyze-files', methods=['POST'])
def analyze_files():
    """Start analysis of selected files"""
    logger.info("=== ANALYZE FILES REQUEST ===")
    try:
        data = request.json
        files = data.get('files', [])
        server_type = data.get('server_type', 'source')
        force_reanalysis = data.get('force_reanalysis', False)
        
        # Get AI config from config manager
        ai_config = config_manager.get_ai_analysis_settings()
        
        # Override with any config from request
        if 'ai_config' in data:
            ai_config.update(data['ai_config'])
        
        logger.info(f"Starting analysis of {len(files)} files from {server_type} server")
        logger.info(f"AI config: provider={ai_config.get('provider')}, enabled={ai_config.get('enabled')}")
        logger.info(f"Force reanalysis: {force_reanalysis}")
        
        # Check if server is connected
        if server_type not in ftp_managers:
            return jsonify({
                'success': False, 
                'message': f'{server_type} server not connected'
            })
        
        # Connect to database if not already connected
        if db_manager.collection is None:
            success = db_manager.connect()
            if not success:
                return jsonify({
                    'success': False, 
                    'message': 'Failed to connect to database'
                })
        
        # Get the FTP manager
        ftp_manager = ftp_managers[server_type]
        
        # Start analysis
        results = file_analyzer.analyze_batch(files, ftp_manager, ai_config, force_reanalysis)
        
        # Count success/failure
        success_count = sum(1 for r in results if r.get('success'))
        failure_count = len(results) - success_count
        
        logger.info(f"Analysis batch completed: {success_count} successful, {failure_count} failed")
        
        # Convert any ObjectId objects to strings before returning
        safe_results = convert_objectid_to_string(results)
        
        return jsonify({
            'success': True,
            'results': safe_results,
            'summary': {
                'total': len(results),
                'successful': success_count,
                'failed': failure_count
            }
        })
        
    except Exception as e:
        error_msg = f"Analysis error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/ai-config', methods=['GET'])
def get_ai_config():
    """Get AI analysis configuration"""
    try:
        ai_config = config_manager.get_ai_analysis_settings()
        
        # Load API keys from environment variables if available
        openai_key = os.getenv('OPENAI_API_KEY')
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        
        # Merge environment keys with config (env takes precedence)
        if openai_key:
            ai_config['openai_api_key'] = openai_key
        if anthropic_key:
            ai_config['anthropic_api_key'] = anthropic_key
        
        # Don't send API keys to frontend for security
        safe_config = ai_config.copy()
        safe_config['openai_api_key'] = '***' if ai_config.get('openai_api_key') else ''
        safe_config['anthropic_api_key'] = '***' if ai_config.get('anthropic_api_key') else ''
        return jsonify({'success': True, 'config': safe_config})
    except Exception as e:
        logger.error(f"Error getting AI config: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/ai-config', methods=['POST'])
def save_ai_config():
    """Save AI analysis configuration"""
    try:
        data = request.json
        
        # Update AI analysis settings
        if 'ai_analysis' in data:
            config_manager.update_ai_analysis_settings(data['ai_analysis'])
        
        return jsonify({'success': True, 'message': 'AI configuration saved'})
    except Exception as e:
        logger.error(f"Error saving AI config: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/analyzed-content', methods=['POST'])
def get_analyzed_content():
    """Get analyzed content for scheduling with filters"""
    logger.info("=== ANALYZED CONTENT REQUEST ===")
    try:
        data = request.json
        content_type = data.get('content_type', '')
        duration_category = data.get('duration_category', '')
        search = data.get('search', '').lower()
        
        logger.info(f"Filters: content_type={content_type}, duration_category={duration_category}, search={search}")
        
        # Connect to database if not already connected
        if not db_manager.connected:
            success = db_manager.connect()
            if not success:
                return jsonify({
                    'success': False, 
                    'message': 'Failed to connect to database'
                })
        
        # Get analyzed content from PostgreSQL
        content_list = db_manager.get_analyzed_content_for_scheduling(
            content_type=content_type,
            duration_category=duration_category,
            search=search
        )
        
        logger.info(f"Found {len(content_list)} content items")
        
        # Convert any datetime objects to strings
        safe_content = convert_objectid_to_string(content_list)
        
        return jsonify({
            'success': True,
            'content': safe_content,
            'count': len(safe_content),
            'filters_applied': {
                'content_type': content_type,
                'duration_category': duration_category,
                'search': search
            }
        })
        
    except Exception as e:
        error_msg = f"Analyzed content error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/create-schedule', methods=['POST'])
def create_schedule():
    """Create a daily schedule for Comcast Channel 26"""
    logger.info("=== CREATE SCHEDULE REQUEST ===")
    try:
        data = request.json
        schedule_date = data.get('date')
        schedule_name = data.get('schedule_name')  # Optional schedule name
        
        logger.info(f"Creating schedule for date: {schedule_date}")
        
        if not schedule_date:
            return jsonify({
                'success': False,
                'message': 'Schedule date is required'
            })
        
        # Get max errors from config
        scheduling_config = config_manager.get_scheduling_settings()
        max_errors = scheduling_config.get('max_consecutive_errors', 100)
        
        # Create schedule using PostgreSQL scheduler
        result = scheduler_postgres.create_daily_schedule(schedule_date, schedule_name, max_errors)
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Create schedule error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/get-schedule', methods=['POST'])
def get_schedule():
    """Get schedule for a specific date"""
    logger.info("=== GET SCHEDULE REQUEST ===")
    try:
        data = request.json
        date = data.get('date')
        
        logger.info(f"Getting schedule for date: {date}")
        
        if not date:
            return jsonify({
                'success': False,
                'message': 'Date is required'
            })
        
        # Get schedule
        schedule = scheduler_postgres.get_schedule_by_date(date)
        
        if schedule:
            # Get schedule items
            items = scheduler_postgres.get_schedule_items(schedule['id'])
            
            # Convert time objects to strings and ensure duration is a proper number
            for item in items:
                if 'scheduled_start_time' in item and hasattr(item['scheduled_start_time'], 'strftime'):
                    item['scheduled_start_time'] = item['scheduled_start_time'].strftime('%H:%M:%S')
                # Ensure scheduled_duration_seconds is a float, not Decimal
                if 'scheduled_duration_seconds' in item and item['scheduled_duration_seconds'] is not None:
                    item['scheduled_duration_seconds'] = float(item['scheduled_duration_seconds'])
                # Convert last_scheduled_date to ISO format if present
                if 'last_scheduled_date' in item and item['last_scheduled_date'] is not None:
                    if hasattr(item['last_scheduled_date'], 'isoformat'):
                        item['last_scheduled_date'] = item['last_scheduled_date'].isoformat()
                    else:
                        item['last_scheduled_date'] = str(item['last_scheduled_date'])
            
            schedule['items'] = items
            schedule['total_items'] = len(items)
            schedule['total_duration_hours'] = float(schedule.get('total_duration_seconds', 0)) / 3600 if schedule.get('total_duration_seconds') else 0
            
            # Convert schedule dates to strings
            safe_schedule = convert_objectid_to_string(schedule)
            
            return jsonify({
                'success': True,
                'schedule': safe_schedule
            })
        else:
            return jsonify({
                'success': False,
                'message': f'No schedule found for {date}'
            })
        
    except Exception as e:
        error_msg = f"Get schedule error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/delete-schedule', methods=['POST'])
def delete_schedule():
    """Delete a schedule by ID"""
    logger.info("=== DELETE SCHEDULE REQUEST ===")
    try:
        data = request.json
        schedule_id = data.get('schedule_id')
        
        logger.info(f"Deleting schedule: {schedule_id}")
        
        if not schedule_id:
            return jsonify({
                'success': False,
                'message': 'Schedule ID is required'
            })
        
        # Delete schedule
        success = scheduler_postgres.delete_schedule(int(schedule_id))
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Schedule {schedule_id} deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to delete schedule {schedule_id}'
            })
        
    except Exception as e:
        error_msg = f"Delete schedule error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/delete-all-schedules', methods=['POST'])
def delete_all_schedules():
    """Delete all schedules and reset scheduling metadata"""
    logger.info("=== DELETE ALL SCHEDULES REQUEST ===")
    try:
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            # Delete all schedules (items will cascade)
            cursor.execute("DELETE FROM schedules")
            schedules_deleted = cursor.rowcount
            
            # Reset all scheduling metadata
            cursor.execute("""
                UPDATE scheduling_metadata 
                SET last_scheduled_date = NULL, 
                    total_airings = 0,
                    last_scheduled_in_overnight = NULL,
                    last_scheduled_in_early_morning = NULL,
                    last_scheduled_in_morning = NULL,
                    last_scheduled_in_afternoon = NULL,
                    last_scheduled_in_prime_time = NULL,
                    last_scheduled_in_evening = NULL,
                    replay_count_for_overnight = 0,
                    replay_count_for_early_morning = 0,
                    replay_count_for_morning = 0,
                    replay_count_for_afternoon = 0,
                    replay_count_for_prime_time = 0,
                    replay_count_for_evening = 0
            """)
            metadata_reset = cursor.rowcount
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Deleted {schedules_deleted} schedules and reset {metadata_reset} metadata records")
            
            return jsonify({
                'success': True,
                'message': f'Successfully deleted {schedules_deleted} schedules and reset scheduling history',
                'schedules_deleted': schedules_deleted,
                'metadata_reset': metadata_reset
            })
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting all schedules: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Failed to delete all schedules: {str(e)}'
            })
        finally:
            db_manager._put_connection(conn)
            
    except Exception as e:
        error_msg = f"Delete all schedules error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/add-item-to-schedule', methods=['POST'])
def add_item_to_schedule():
    """Add a single item to an existing schedule"""
    logger.info("=== ADD ITEM TO SCHEDULE REQUEST ===")
    try:
        data = request.json
        schedule_id = data.get('schedule_id')
        asset_id = data.get('asset_id')
        
        logger.info(f"Adding asset {asset_id} to schedule {schedule_id}")
        
        if not schedule_id or not asset_id:
            return jsonify({
                'success': False,
                'message': 'Schedule ID and Asset ID are required'
            })
        
        # Get current schedule items to determine order
        schedule = scheduler_postgres.get_schedule_by_id(int(schedule_id))
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found in database")
            # Try to check if it exists with a simple query
            return jsonify({
                'success': False,
                'message': f'Schedule {schedule_id} not found'
            })
        
        # Determine the order index (add to end)
        current_items = schedule.get('items', [])
        order_index = len(current_items)
        
        # Calculate start time based on previous items
        start_seconds = 0
        for item in current_items:
            start_seconds += float(item.get('scheduled_duration_seconds', 0))
        
        hours = int(start_seconds // 3600)
        minutes = int((start_seconds % 3600) // 60)
        seconds = int(start_seconds % 60)
        start_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        # Add item to schedule
        success = scheduler_postgres.add_item_to_schedule(
            schedule_id=int(schedule_id),
            asset_id=asset_id,
            order_index=order_index,
            scheduled_start_time=start_time
        )
        
        if success:
            # Recalculate all schedule times
            scheduler_postgres.recalculate_schedule_times(int(schedule_id))
            
            return jsonify({
                'success': True,
                'message': f'Item added to schedule successfully',
                'order_index': order_index
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to add item to schedule'
            })
        
    except Exception as e:
        error_msg = f"Add item to schedule error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/update-content-type', methods=['POST'])
def update_content_type():
    """Update content type only"""
    try:
        data = request.json
        content_id = data.get('content_id')
        new_content_type = data.get('content_type')
        
        if not all([content_id, new_content_type]):
            return jsonify({
                'success': False,
                'message': 'Missing required parameters'
            })
        
        logger.info(f"Updating content type for ID {content_id} to {new_content_type}")
        
        # Update content_type in assets table (convert to lowercase for PostgreSQL enum)
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE assets 
                SET content_type = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_content_type.lower(), content_id))
            
            conn.commit()
            cursor.close()
            
            logger.info("Content type updated successfully")
            
            return jsonify({
                'success': True,
                'message': 'Content type updated successfully'
            })
            
        except Exception as e:
            logger.error(f"Database update failed: {str(e)}")
            if conn:
                conn.rollback()
            return jsonify({
                'success': False,
                'message': f'Database update failed: {str(e)}'
            })
        finally:
            if conn:
                db_manager._put_connection(conn)
            
    except Exception as e:
        logger.error(f"Update content type failed: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/rename-content', methods=['POST'])
def rename_content():
    """Rename content file only"""
    logger.info("=== RENAME CONTENT REQUEST ===")
    try:
        data = request.json
        content_id = data.get('content_id')
        old_file_name = data.get('old_file_name')
        old_file_path = data.get('old_file_path')
        new_file_name = data.get('new_file_name')
        new_content_type = data.get('new_content_type', '')  # Optional for determining folder
        
        logger.info(f"Renaming {old_file_name} to {new_file_name}")
        
        if not all([content_id, old_file_name, new_file_name]):
            return jsonify({
                'success': False,
                'message': 'Missing required parameters'
            })
        
        # Validate filename format
        import re
        if not re.match(r'^\d{6}_\w+_.+\.mp4$', new_file_name):
            return jsonify({
                'success': False,
                'message': 'Invalid filename format. Use: YYMMDD_TYPE_Description.mp4'
            })
        
        # Determine new folder based on content type
        content_type_mappings = {
            'AN': 'ATLANTA NOW',
            'BMP': 'BUMPS', 
            'IMOW': 'IMOW',
            'IM': 'INCLUSION MONTHS',
            'IA': 'INSIDE ATLANTA',
            'LM': 'LEGISLATIVE MINUTE',
            'MTG': 'MEETINGS',
            'MAF': 'MOVING ATLANTA FORWARD',
            'PKG': 'PKGS',
            'PMO': 'PROMOS',
            'PSA': 'PSAs',
            'SZL': 'SIZZLES',
            'SPP': 'SPECIAL PROJECTS',
            'OTHER': 'OTHER'
        }
        
        new_folder = content_type_mappings.get(new_content_type, 'OTHER')
        
        # Handle old file path - if it's relative, we need to make it absolute
        if not old_file_path.startswith('/'):
            # Get the base path from FTP configuration
            source_ftp = ftp_managers.get('source')
            if source_ftp and source_ftp.config:
                base_ftp_path = source_ftp.config.get('path', '/mnt/md127')
                old_file_path_absolute = f"{base_ftp_path}/{old_file_path}"
            else:
                # Default to common path
                old_file_path_absolute = f"/mnt/md127/{old_file_path}"
        else:
            old_file_path_absolute = old_file_path
        
        # Construct new path - all content should go under ATL26 On-Air Content
        # Use the actual base path from the server, not a relative path
        base_path = '/mnt/md127/ATL26 On-Air Content'
        
        # If file is on /mnt/main (symlink), use that instead
        if '/mnt/main/' in old_file_path_absolute:
            base_path = '/mnt/main/ATL26 On-Air Content'
        
        # Construct full new path
        new_file_path = f"{base_path}/{new_folder}/{new_file_name}"
        
        logger.info(f"Old path (relative): {old_file_path}")
        logger.info(f"Old path (absolute): {old_file_path_absolute}")
        logger.info(f"New path: {new_file_path}")
        
        # Check if this is just a content type change (paths are the same)
        path_changed = (old_file_path_absolute != new_file_path)
        
        # Rename files on both FTP servers (only if path actually changed)
        rename_success = True
        rename_messages = []
        
        if path_changed:
            for server_type in ['source', 'target']:
                if server_type in ftp_managers:
                    ftp = ftp_managers[server_type]
                    try:
                        # Connect if not connected
                        if not ftp.connected:
                            ftp.connect()
                        
                        # Rename/move the file using FTP rename command
                        # This works across directories and acts as a move
                        ftp.ftp.rename(old_file_path_absolute, new_file_path)
                        rename_messages.append(f"{server_type}: renamed successfully")
                        logger.info(f"Renamed on {server_type} server")
                    except Exception as e:
                        logger.error(f"Failed to rename on {server_type}: {str(e)}")
                        rename_messages.append(f"{server_type}: {str(e)}")
                        rename_success = False
        else:
            logger.info("No path change needed - only updating content type in database")
            rename_messages.append("No file rename needed - content type update only")
        
        # Update database
        if rename_success:
            # Update instances table
            conn = db_manager._get_connection()
            try:
                cursor = conn.cursor()
                
                # Only update instances if path changed
                if path_changed:
                    cursor.execute("""
                        UPDATE instances 
                        SET file_name = %s, file_path = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE file_path = %s
                    """, (new_file_name, new_file_path, old_file_path))
                
                conn.commit()
                cursor.close()
                
                logger.info("Database updated successfully")
                
                return jsonify({
                    'success': True,
                    'message': 'Content renamed and type updated successfully',
                    'details': rename_messages
                })
                
            except Exception as db_e:
                conn.rollback()
                logger.error(f"Database update failed: {str(db_e)}")
                return jsonify({
                    'success': False,
                    'message': f'Files renamed but database update failed: {str(db_e)}',
                    'details': rename_messages
                })
            finally:
                db_manager._put_connection(conn)
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to rename files on FTP servers',
                'details': rename_messages
            })
                
    except Exception as e:
        error_msg = f"Rename content error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/reorder-schedule-items', methods=['POST'])
def reorder_schedule_items():
    """Reorder items within a schedule"""
    try:
        data = request.json
        schedule_id = data.get('schedule_id')
        item_id = data.get('item_id')
        old_position = data.get('old_position')
        new_position = data.get('new_position')
        
        if not all([schedule_id, item_id is not None, old_position is not None, new_position is not None]):
            return jsonify({
                'success': False,
                'message': 'Missing required parameters'
            })
        
        logger.info(f"Reordering item {item_id} in schedule {schedule_id} from position {old_position} to {new_position}")
        
        # Call the scheduler method to reorder items
        success = scheduler_postgres.reorder_schedule_items(schedule_id, old_position, new_position)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Schedule items reordered successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to reorder schedule items'
            })
            
    except Exception as e:
        error_msg = f"Reorder schedule items error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/delete-schedule-item', methods=['POST'])
def delete_schedule_item():
    """Delete a single item from a schedule"""
    try:
        data = request.json
        schedule_id = data.get('schedule_id')
        item_id = data.get('item_id')
        
        if not all([schedule_id, item_id]):
            return jsonify({
                'success': False,
                'message': 'Missing required parameters'
            })
        
        logger.info(f"Deleting item {item_id} from schedule {schedule_id}")
        
        # Call the scheduler method to delete the item
        success = scheduler_postgres.delete_schedule_item(schedule_id, item_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Schedule item deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to delete schedule item'
            })
            
    except Exception as e:
        error_msg = f"Delete schedule item error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})


@app.route('/api/toggle-schedule-item-availability', methods=['POST'])
def toggle_schedule_item_availability():
    """Toggle the availability of a schedule item for future scheduling"""
    try:
        data = request.json
        schedule_id = data.get('schedule_id')
        item_id = data.get('item_id')
        available = data.get('available', True)
        
        if not all([schedule_id is not None, item_id is not None]):
            return jsonify({
                'success': False,
                'message': 'Missing required parameters'
            })
        
        logger.info(f"Toggling availability for item {item_id} in schedule {schedule_id} to {available}")
        
        # Update the item availability
        success = scheduler_postgres.toggle_item_availability(schedule_id, item_id, available)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Item {"enabled" if available else "disabled"} for scheduling',
                'available': available
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update item availability'
            })
            
    except Exception as e:
        error_msg = f"Toggle item availability error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/list-schedules', methods=['GET'])
def list_schedules():
    """List all active schedules"""
    logger.info("=== LIST SCHEDULES REQUEST ===")
    try:
        # Get active schedules from PostgreSQL
        schedules = scheduler_postgres.get_active_schedules()
        
        # Convert datetime objects to strings
        for schedule in schedules:
            if 'air_date' in schedule and schedule['air_date']:
                schedule['air_date'] = schedule['air_date'].isoformat()
            if 'created_date' in schedule and schedule['created_date']:
                schedule['created_date'] = schedule['created_date'].isoformat()
            # Format duration
            if schedule.get('total_duration'):
                schedule['total_duration_hours'] = float(schedule['total_duration']) / 3600
        
        logger.info(f"Found {len(schedules)} active schedules")
        
        return jsonify({
            'success': True,
            'schedules': schedules,
            'count': len(schedules)
        })
        
    except Exception as e:
        error_msg = f"List schedules error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})



@app.route('/api/create-weekly-schedule', methods=['POST'])
def create_weekly_schedule():
    """Create a weekly schedule (7 days)"""
    logger.info("=== CREATE WEEKLY SCHEDULE REQUEST ===")
    try:
        data = request.json
        start_date = data.get('start_date')
        schedule_type = data.get('schedule_type', 'multiple')  # 'multiple' or 'single'
        
        logger.info(f"Creating weekly schedule starting: {start_date}, type: {schedule_type}")
        
        if not start_date:
            return jsonify({
                'success': False,
                'message': 'Start date is required'
            })
        
        # Get max errors from config
        scheduling_config = config_manager.get_scheduling_settings()
        max_errors = scheduling_config.get('max_consecutive_errors', 100)
        
        # Create weekly schedule using PostgreSQL scheduler
        if schedule_type == 'single':
            result = scheduler_postgres.create_single_weekly_schedule(start_date, None, max_errors)
        else:
            result = scheduler_postgres.create_weekly_schedule(start_date)
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Create weekly schedule error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/export-schedule', methods=['POST'])
def export_schedule():
    """Export a schedule to FTP server in Castus format"""
    logger.info("=== EXPORT SCHEDULE REQUEST ===")
    try:
        data = request.json
        date = data.get('date')
        export_server = data.get('export_server')
        export_path = data.get('export_path')
        filename = data.get('filename')
        format_type = data.get('format', 'castus')
        
        logger.info(f"Exporting schedule for {date} to {export_server}:{export_path}")
        
        if not date or not export_server or not export_path:
            return jsonify({
                'success': False,
                'message': 'Date, export server, and export path are required'
            })
        
        # Check if FTP manager exists for the export server
        if export_server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{export_server} server not connected'
            })
        
        # Get the schedule
        schedule = scheduler_postgres.get_schedule_by_date(date)
        if not schedule:
            return jsonify({
                'success': False,
                'message': f'No schedule found for {date}'
            })
        
        # Get schedule items
        items = scheduler_postgres.get_schedule_items(schedule['id'])
        logger.info(f"Got {len(items)} items for schedule export")
        if items:
            logger.debug(f"First item keys: {list(items[0].keys())}")
        
        # Generate Castus format schedule
        if format_type == 'castus' or format_type == 'castus_weekly':
            # Determine if it's a daily or weekly schedule
            export_format = 'weekly' if format_type == 'castus_weekly' else 'daily'
            schedule_content = generate_castus_schedule(schedule, items, date, export_format)
            
            # Use provided filename or generate default
            if not filename:
                schedule_date = datetime.strptime(date, '%Y-%m-%d')
                day_name = schedule_date.strftime('%a').lower()
                filename = f"{day_name}_{date.replace('-', '')}.sch"
            
            # Full path for export
            full_path = f"{export_path}/{filename}"
            
            # Write to temporary file first - explicitly preserve TABs
            import tempfile
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.sch') as temp_file:
                # Write as binary to ensure no text processing happens
                temp_file.write(schedule_content.encode('utf-8'))
                temp_file_path = temp_file.name
            
            # Debug: Check if TABs are in the generated content
            logger.debug(f"Schedule content contains TABs: {chr(9) in schedule_content}")
            logger.debug(f"First item block sample: {repr(schedule_content[200:300])}")
            
            try:
                # Upload to FTP server
                ftp_manager = ftp_managers[export_server]
                success = ftp_manager.upload_file(temp_file_path, full_path)
                
                if success:
                    file_size = os.path.getsize(temp_file_path)
                    return jsonify({
                        'success': True,
                        'message': f'Schedule exported successfully to {export_server}',
                        'file_path': full_path,
                        'file_size': file_size
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Failed to upload schedule file to FTP server'
                    })
            finally:
                # Clean up temp file
                os.unlink(temp_file_path)
        else:
            return jsonify({
                'success': False,
                'message': f'Unsupported export format: {format_type}'
            })
        
    except Exception as e:
        error_msg = f"Export schedule error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

def generate_castus_schedule(schedule, items, date, format_type='daily'):
    """Generate schedule content in Castus format"""
    
    lines = []
    
    # Parse the date to get day of week
    schedule_date = datetime.strptime(date, '%Y-%m-%d')
    day_of_week = schedule_date.weekday()  # 0=Monday, 6=Sunday
    day_name = schedule_date.strftime('%a').lower()  # mon, tue, wed, etc.
    
    if format_type == 'weekly':
        # Weekly format header
        lines.append("defaults, day of the week{")
        lines.append("}")
        # Weekly schedules always start on Sunday (day 0 in Castus)
        lines.append("day = 0")
        lines.append("time slot length = 30")
        lines.append("scrolltime = 12:00 am")
        lines.append("filter script = ")
        lines.append("global default=/mnt/main/Playlists/simple playlist")
        lines.append("global default section=item duration=;")
        lines.append("text encoding = UTF-8")
        lines.append("schedule format version = 5.0.0.4 2021/01/15")
    else:
        # Daily format header
        lines.append("*daily")
        lines.append("defaults, of the day{")
        lines.append("}")
        lines.append("time slot length = 30")
        lines.append("scrolltime = 12:00 am")
        lines.append("filter script = ")
        lines.append("global default=")
        lines.append("text encoding = UTF-8")
        lines.append("schedule format version = 5.0.0.4 2021/01/15")
    
    # Add schedule items
    for idx, item in enumerate(items):
        start_time = item.get('scheduled_start_time', item.get('start_time', '00:00:00'))
        # Handle both field names for compatibility
        duration_seconds = float(item.get('scheduled_duration_seconds', item.get('duration_seconds', 0)))
        
        # Calculate end time
        # Handle different time formats
        if isinstance(start_time, str):
            # Handle time with frames (HH:MM:SS:FF) by removing frame part
            time_parts = start_time.split(':')
            if len(time_parts) == 4:
                # Remove frames for datetime parsing
                start_time_no_frames = ':'.join(time_parts[:3])
            else:
                start_time_no_frames = start_time
            start_dt = datetime.strptime(f"2000-01-01 {start_time_no_frames}", "%Y-%m-%d %H:%M:%S")
        else:
            # Handle datetime.time object from PostgreSQL
            start_dt = datetime.combine(datetime(2000, 1, 1), start_time)
        end_dt = start_dt + timedelta(seconds=duration_seconds)
        
        # Extract milliseconds from duration
        whole_seconds = int(duration_seconds)
        milliseconds = int((duration_seconds - whole_seconds) * 1000)
        
        if format_type == 'weekly':
            # Weekly format times include day abbreviation
            # For weekly schedules, we need to calculate which day this item falls on
            # based on the total duration so far
            item_start_seconds = 0
            for i in range(idx):
                item_start_seconds += float(items[i].get('scheduled_duration_seconds', items[i].get('duration_seconds', 0)))
            
            # Calculate which day of the week this item is on
            day_offset = int(item_start_seconds // (24 * 60 * 60))
            item_day = (schedule_date + timedelta(days=day_offset))
            item_day_name = item_day.strftime('%a').lower()
            
            # Special handling for first item - should start at exactly 12:00 am
            if idx == 0 and start_dt.hour == 0 and start_dt.minute == 0:
                start_time_formatted = f"{item_day_name} 12:00 am"
            else:
                start_time_formatted = f"{item_day_name} " + start_dt.strftime("%I:%M:%S").lstrip("0") + ".000 " + start_dt.strftime("%p").lower()
            
            # For end time, include the actual milliseconds
            end_time_formatted = f"{item_day_name} " + end_dt.strftime("%I:%M:%S").lstrip("0") + f".{milliseconds:03d} " + end_dt.strftime("%p").lower()
        else:
            # Daily format times
            # Special handling for first item - should start at exactly 12:00 am
            if idx == 0 and start_dt.hour == 0 and start_dt.minute == 0:
                start_time_formatted = "12:00 am"
            else:
                # For other start times, add .000 if no milliseconds
                start_time_formatted = start_dt.strftime("%I:%M:%S").lstrip("0") + ".000 " + start_dt.strftime("%p").lower()
            
            # For end time, include the actual milliseconds
            end_time_formatted = end_dt.strftime("%I:%M:%S").lstrip("0") + f".{milliseconds:03d} " + end_dt.strftime("%p").lower()
        
        # Get the file path from the database
        file_path = item.get('file_path', '')
        
        # If the path doesn't start with the expected prefix, we need to construct it
        if not file_path.startswith('/mnt/main/ATL26 On-Air Content/'):
            # Extract just the relevant part of the path
            # The file_path from database might be something like:
            # /media/videos/MEETINGS/250609_MTG_Zoning Committee Meeting.mp4
            # We want to preserve MEETINGS/filename.mp4
            
            # Remove common storage prefixes
            if file_path.startswith('/media/videos/'):
                relative_path = file_path[len('/media/videos/'):]
            elif file_path.startswith('/content/'):
                relative_path = file_path[len('/content/'):]
            elif file_path.startswith('/files/'):
                relative_path = file_path[len('/files/'):]
            else:
                # If no known prefix, try to extract subdirectory + filename
                path_parts = file_path.split('/')
                if len(path_parts) >= 2:
                    # Take the last two parts (subfolder/filename)
                    relative_path = '/'.join(path_parts[-2:])
                else:
                    # Just the filename
                    relative_path = path_parts[-1]
            
            file_path = f"/mnt/main/ATL26 On-Air Content/{relative_path}"
        
        lines.append("{")
        # Explicitly use TAB character (ASCII 9) to ensure it's not converted
        TAB = chr(9)
        lines.append(f"{TAB}item={file_path}")
        lines.append(f"{TAB}loop=0")
        
        # Use GUID if available from assets
        guid = item.get('guid', str(uuid.uuid4()))
        lines.append(f"{TAB}guid={{{guid}}}")
        
        # Daily format times
        lines.append(f"{TAB}start={start_time_formatted}")
        lines.append(f"{TAB}end={end_time_formatted}")
        lines.append("}")
    
    return "\n".join(lines)

@app.route('/api/list-schedule-files', methods=['POST'])
def list_schedule_files():
    """List schedule files (.sch) from FTP server"""
    try:
        data = request.json
        server = data.get('server')
        path = data.get('path', '/mnt/md127/Schedules')
        
        if not server or server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'Invalid server or server not connected: {server}'
            })
        
        ftp_manager = ftp_managers[server]
        
        # List files in the specified path
        all_files = ftp_manager.list_files(path)
        
        # Filter for .sch files
        schedule_files = []
        for file in all_files:
            if file['name'].lower().endswith('.sch'):
                schedule_files.append({
                    'name': file['name'],
                    'size': file['size'],
                    'path': os.path.join(path, file['name'])
                })
        
        return jsonify({
            'success': True,
            'files': schedule_files
        })
        
    except Exception as e:
        error_msg = f"List schedule files error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/load-schedule-template', methods=['POST'])
def load_schedule_template():
    """Load a schedule template file from FTP server"""
    logger.info("=== LOAD SCHEDULE TEMPLATE REQUEST ===")
    try:
        data = request.json
        server = data.get('server')
        file_path = data.get('file_path')
        
        logger.info(f"Server: {server}, File path: {file_path}")
        
        if not server or not file_path:
            logger.error("Missing required parameters")
            return jsonify({
                'success': False,
                'message': 'Server and file path are required'
            })
        
        if server not in ftp_managers:
            logger.error(f"Server {server} not in ftp_managers. Available: {list(ftp_managers.keys())}")
            return jsonify({
                'success': False,
                'message': f'{server} server not connected'
            })
        
        ftp_manager = ftp_managers[server]
        logger.info(f"Using FTP manager for {server}")
        
        # Download file to temporary location
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.sch') as temp_file:
            temp_file_path = temp_file.name
        
        logger.info(f"Downloading {file_path} to temp file {temp_file_path}")
        success = ftp_manager.download_file(file_path, temp_file_path)
        
        if not success:
            logger.error("Failed to download file from FTP")
            os.unlink(temp_file_path)
            return jsonify({
                'success': False,
                'message': 'Failed to download template file'
            })
        
        try:
            # Parse the schedule file
            logger.info(f"Reading downloaded file from {temp_file_path}")
            with open(temp_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            logger.info(f"File content length: {len(content)} chars")
            logger.debug(f"First 200 chars: {content[:200]}")
            
            # Parse Castus schedule format
            schedule_data = parse_castus_schedule(content)
            
            logger.info(f"Parsed schedule: type={schedule_data['type']}, items={len(schedule_data['items'])}")
            
            # Try to match items with database assets
            for item in schedule_data['items']:
                filename = item.get('filename')
                if filename:
                    logger.debug(f"Looking up asset for: {filename}")
                    asset_match = db_manager.find_asset_by_filename(filename)
                    if asset_match:
                        item['asset_id'] = asset_match['id']
                        item['content_id'] = asset_match['id']  # For backwards compatibility
                        item['content_type'] = asset_match.get('content_type')
                        item['content_title'] = asset_match.get('content_title')
                        # Use the duration from the database
                        if asset_match.get('duration_seconds'):
                            item['duration_seconds'] = asset_match['duration_seconds']
                        item['matched'] = True
                        logger.debug(f"Found match for {filename}: asset_id={asset_match['id']}, duration={asset_match.get('duration_seconds')}")
                    else:
                        item['matched'] = False
                        logger.debug(f"No match found for {filename}")
            
            return jsonify({
                'success': True,
                'template': schedule_data,
                'filename': os.path.basename(file_path)
            })
            
        finally:
            os.unlink(temp_file_path)
        
    except Exception as e:
        error_msg = f"Load template error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

def parse_castus_schedule(content):
    """Parse Castus schedule file format"""
    lines = content.strip().split('\n')
    
    schedule_data = {
        'type': 'daily',  # default
        'items': [],
        'header': {}
    }
    
    current_item = None
    in_item_block = False
    
    for line in lines:
        line = line.strip()
        
        # Detect schedule type
        if line == '*daily':
            schedule_data['type'] = 'daily'
        elif line == '*weekly':
            schedule_data['type'] = 'weekly'
        elif line.startswith('day = '):
            # Weekly format without *weekly header
            schedule_data['type'] = 'weekly'
            schedule_data['header']['day'] = line.split('=')[1].strip()
        
        # Start of item block
        elif line == '{':
            in_item_block = True
            current_item = {}
        
        # End of item block
        elif line == '}' and in_item_block:
            if current_item and 'item' in current_item:
                # Extract filename from path
                file_path = current_item['item']
                filename = os.path.basename(file_path)
                
                # Convert to schedule item format
                item = {
                    'file_path': file_path,
                    'filename': filename,
                    'start_time': current_item.get('start', ''),
                    'end_time': current_item.get('end', ''),
                    'guid': current_item.get('guid', '').strip('{}'),
                    'loop': current_item.get('loop', '0')
                }
                
                # Calculate duration from start/end times if available
                if item['start_time'] and item['end_time']:
                    duration = calculate_duration_from_times(item['start_time'], item['end_time'])
                    item['duration_seconds'] = duration
                
                schedule_data['items'].append(item)
            
            in_item_block = False
            current_item = None
        
        # Inside item block
        elif in_item_block and current_item is not None:
            # Remove leading TAB or spaces
            line_content = line.lstrip('\t ')
            if '=' in line_content:
                key, value = line_content.split('=', 1)
                current_item[key.strip()] = value.strip()
        
        # Header information
        elif '=' in line and not in_item_block:
            key, value = line.split('=', 1)
            schedule_data['header'][key.strip()] = value.strip()
    
    return schedule_data

def convert_to_24hour_format(time_str):
    """Convert Castus time format (12-hour with am/pm) to 24-hour format (HH:MM:SS)"""
    try:
        import re
        from datetime import datetime
        
        # Remove milliseconds for parsing
        time_clean = re.sub(r'\.\d+', '', time_str)
        
        # Try different time formats
        for fmt in ["%I:%M:%S %p", "%I:%M %p"]:
            try:
                dt = datetime.strptime(time_clean, fmt)
                return dt.strftime("%H:%M:%S")
            except ValueError:
                continue
        
        # If no format works, return as-is (might already be 24-hour)
        return time_str
    except Exception as e:
        logger.error(f"Error converting time format: {e}")
        return "00:00:00"

def calculate_duration_from_times(start_time, end_time):
    """Calculate duration in seconds from start/end time strings"""
    try:
        # Parse times like "12:00 am", "12:30:45.123 pm"
        import re
        
        def parse_time(time_str):
            # Remove milliseconds for parsing
            time_clean = re.sub(r'\.\d+', '', time_str)
            
            # Parse time
            from datetime import datetime
            
            # Try different time formats
            for fmt in ["%I:%M:%S %p", "%I:%M %p"]:
                try:
                    return datetime.strptime(time_clean, fmt)
                except ValueError:
                    continue
            
            raise ValueError(f"Unable to parse time: {time_str}")
        
        start_dt = parse_time(start_time)
        end_dt = parse_time(end_time)
        
        # Handle day boundary
        if end_dt < start_dt:
            end_dt = end_dt.replace(day=end_dt.day + 1)
        
        duration = (end_dt - start_dt).total_seconds()
        return duration
        
    except:
        return 0

@app.route('/api/create-schedule-from-template', methods=['POST'])
def create_schedule_from_template():
    """Create a schedule from a template with manually added items"""
    try:
        data = request.json
        air_date = data.get('air_date')
        schedule_name = data.get('schedule_name', 'Daily Schedule')
        channel = data.get('channel', 'Comcast Channel 26')
        items = data.get('items', [])
        
        logger.info(f"Creating schedule from template: {schedule_name} for {air_date} with {len(items)} items")
        
        if not air_date:
            return jsonify({
                'success': False,
                'message': 'Air date is required'
            })
        
        # Create an empty schedule using the new method
        result = scheduler_postgres.create_empty_schedule(
            schedule_date=air_date,
            schedule_name=schedule_name
        )
        
        if not result['success']:
            return jsonify(result)
        
        schedule_id = result['schedule_id']
        logger.info(f"Created empty schedule with ID: {schedule_id}")
        
        added_count = 0
        skipped_count = 0
        
        # Now add only the template items
        for idx, item in enumerate(items):
            asset_id = item.get('asset_id')
            
            # Debug logging
            logger.info(f"Processing item {idx}: asset_id={asset_id}, type={type(asset_id)}")
            
            # Check if asset_id looks like a MongoDB ObjectId (24 hex chars)
            if asset_id and isinstance(asset_id, str) and len(asset_id) == 24 and all(c in '0123456789abcdef' for c in asset_id.lower()):
                logger.warning(f"Asset ID {asset_id} appears to be a MongoDB ObjectId, not a PostgreSQL integer")
                skipped_count += 1
                continue
            
            if asset_id:
                try:
                    # Ensure asset_id is an integer
                    asset_id = int(asset_id)
                    
                    scheduler_postgres.add_item_to_schedule(
                        schedule_id,
                        asset_id,
                        order_index=idx,
                        scheduled_start_time='00:00:00',  # Will be recalculated
                        scheduled_duration_seconds=item.get('scheduled_duration_seconds', 0)
                    )
                    added_count += 1
                    logger.info(f"Added item {idx} with asset_id {asset_id}")
                except ValueError as ve:
                    logger.warning(f"Failed to convert asset_id to integer: {asset_id}")
                    skipped_count += 1
                except Exception as item_error:
                    logger.warning(f"Failed to add item {idx} with asset_id {asset_id}: {str(item_error)}")
                    skipped_count += 1
            else:
                logger.warning(f"Skipping item {idx} - no asset_id")
                skipped_count += 1
        
        # Recalculate start times
        scheduler_postgres.recalculate_schedule_times(schedule_id)
            
        message = f'Schedule created with {added_count} items'
        if skipped_count > 0:
            message += f' ({skipped_count} items skipped - no asset ID)'
        
        logger.info(f"Template schedule created: {added_count} items added, {skipped_count} skipped")
        
        return jsonify({
            'success': True,
            'schedule_id': schedule_id,
            'message': message,
            'added_count': added_count,
            'skipped_count': skipped_count
        })
            
    except Exception as e:
        error_msg = f"Create schedule from template error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/load-schedule-from-ftp', methods=['POST'])
def load_schedule_from_ftp():
    """Load a schedule from FTP and create it in the database"""
    logger.info("=== LOAD SCHEDULE FROM FTP REQUEST ===")
    try:
        data = request.json
        server_type = data.get('server')
        path = data.get('path', '/mnt/md127/Schedules')
        filename = data.get('filename')
        schedule_date = data.get('schedule_date')
        
        if not all([server_type, filename, schedule_date]):
            return jsonify({'success': False, 'message': 'Missing required parameters'})
        
        # Check if server is connected
        if server_type not in ftp_managers:
            return jsonify({'success': False, 'message': f'{server_type} server not connected'})
        
        # Get FTP manager from global dictionary
        ftp_manager = ftp_managers[server_type]
        
        # Download and parse schedule file
        remote_path = f"{path}/{filename}".replace('//', '/')
        logger.info(f"Downloading schedule from: {remote_path}")
        
        # Download to temporary file
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.sch', delete=False) as temp_file:
            temp_path = temp_file.name
            
        try:
            # Download file
            success = ftp_manager.download_file(remote_path, temp_path)
            if not success:
                return jsonify({'success': False, 'message': 'Failed to download schedule file'})
            
            # Parse schedule file
            with open(temp_path, 'r') as f:
                content = f.read()
            
            logger.info(f"Parsing schedule file for date: {schedule_date}")
            
            # Parse the Castus schedule format
            schedule_data = parse_castus_schedule(content)
            
            # Process the schedule items
            schedule_items = []
            matched_count = 0
            unmatched_count = 0
            
            for item in schedule_data['items']:
                file_path = item['file_path']
                file_name = item['filename']
                
                # Try to match with analyzed content
                asset_match = db_manager.find_asset_by_filename(file_name)
                
                if asset_match:
                    schedule_items.append({
                        'file_path': file_path,
                        'file_name': file_name,
                        'asset_id': asset_match['id'],
                        'duration_seconds': asset_match.get('duration_seconds', 0),
                        'content_type': asset_match.get('content_type'),
                        'content_title': asset_match.get('content_title'),
                        'start_time': item.get('start_time'),
                        'end_time': item.get('end_time'),
                        'guid': item.get('guid')
                    })
                    matched_count += 1
                else:
                    # Still add unmatched items
                    schedule_items.append({
                        'file_path': file_path,
                        'file_name': file_name,
                        'asset_id': None,
                        'duration_seconds': item.get('duration_seconds', 0),
                        'content_type': None,
                        'content_title': file_name,
                        'start_time': item.get('start_time'),
                        'end_time': item.get('end_time'),
                        'guid': item.get('guid')
                    })
                    unmatched_count += 1
                    logger.warning(f"No match found for file: {file_name}")
            
            if not schedule_items:
                return jsonify({'success': False, 'message': 'No valid items found in schedule file'})
            
            # Check if schedule already exists for this date
            existing_schedule = scheduler_postgres.get_schedule_by_date(schedule_date)
            if existing_schedule:
                return jsonify({
                    'success': False, 
                    'message': f'A schedule already exists for {schedule_date}. Please delete it first or choose a different date.',
                    'schedule_exists': True
                })
            
            # Create schedule in database
            logger.info(f"Creating schedule for {schedule_date} with {len(schedule_items)} items")
            
            # Create empty schedule
            result = scheduler_postgres.create_empty_schedule(
                schedule_date=schedule_date,
                schedule_name=f"Imported from {filename}"
            )
            
            if not result.get('success'):
                return jsonify(result)
            
            schedule_id = result['schedule_id']
            
            # Add items to schedule
            success_count = 0
            for idx, item in enumerate(schedule_items):
                if item['asset_id']:
                    # Use the start time from the Castus file or calculate if not available
                    if item.get('start_time'):
                        # Convert Castus time format (e.g., "12:30:45.123 am") to 24-hour format
                        start_time = convert_to_24hour_format(item['start_time'])
                    else:
                        # Fallback: calculate based on previous items
                        start_seconds = sum(float(schedule_items[i].get('duration_seconds', 0)) for i in range(idx))
                        hours = int(start_seconds // 3600)
                        minutes = int((start_seconds % 3600) // 60)
                        seconds = int(start_seconds % 60)
                        start_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    
                    success = scheduler_postgres.add_item_to_schedule(
                        schedule_id=schedule_id,
                        asset_id=item['asset_id'],
                        order_index=idx,
                        scheduled_start_time=start_time,
                        scheduled_duration_seconds=item['duration_seconds']
                    )
                    if success:
                        success_count += 1
            
            # Recalculate times
            scheduler_postgres.recalculate_schedule_times(schedule_id)
            
            return jsonify({
                'success': True,
                'schedule_id': schedule_id,
                'total_items': len(schedule_items),
                'matched_items': matched_count,
                'unmatched_items': unmatched_count,
                'items_added': success_count,
                'message': f'Schedule loaded with {success_count} items'
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
    except Exception as e:
        logger.error(f"Error loading schedule from FTP: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/export-template', methods=['POST'])
def export_template():
    """Export a template as a schedule file"""
    try:
        data = request.json
        template = data.get('template')
        export_server = data.get('export_server')
        export_path = data.get('export_path')
        filename = data.get('filename')
        
        if not template or not export_server or not export_path or not filename:
            return jsonify({
                'success': False,
                'message': 'Template, export server, path, and filename are required'
            })
        
        # Check if FTP manager exists for the export server
        if export_server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{export_server} server not connected'
            })
        
        # Generate schedule content from template
        # Calculate start/end times for items
        current_time = datetime.strptime("00:00:00", "%H:%M:%S")
        
        for item in template['items']:
            # Handle time with frames if present
            if 'start_time' in item and ':' in item['start_time']:
                time_parts = item['start_time'].split(':')
                if len(time_parts) == 4:
                    # Has frames, use the base time for calculation
                    item['scheduled_start_time'] = ':'.join(time_parts[:3])
                else:
                    item['scheduled_start_time'] = item['start_time']
            else:
                item['scheduled_start_time'] = current_time.strftime("%H:%M:%S")
            
            duration_seconds = float(item.get('duration_seconds', 0))
            current_time += timedelta(seconds=duration_seconds)
            
        # Create a mock schedule object for the generator
        mock_schedule = {
            'id': 0,
            'air_date': datetime.now().strftime('%Y-%m-%d'),
            'schedule_name': template.get('filename', 'Template'),
            'channel': 'Comcast Channel 26'
        }
        
        # Generate Castus format
        # Determine format type based on template type
        format_type = 'weekly' if template.get('type') == 'weekly' else 'daily'
        schedule_content = generate_castus_schedule(mock_schedule, template['items'], mock_schedule['air_date'], format_type)
        
        # Write to temporary file - explicitly preserve TABs
        import tempfile
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.sch') as temp_file:
            # Write as binary to ensure no text processing happens
            temp_file.write(schedule_content.encode('utf-8'))
            temp_file_path = temp_file.name
        
        try:
            # Full path for export
            full_path = f"{export_path}/{filename}"
            
            # Upload to FTP server
            ftp_manager = ftp_managers[export_server]
            success = ftp_manager.upload_file(temp_file_path, full_path)
            
            if success:
                file_size = os.path.getsize(temp_file_path)
                return jsonify({
                    'success': True,
                    'message': f'Template exported successfully to {export_server}',
                    'file_path': full_path,
                    'file_size': file_size
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to upload template file to FTP server'
                })
        finally:
            # Clean up temp file
            os.unlink(temp_file_path)
            
    except Exception as e:
        error_msg = f"Export template error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'FTP Sync Backend is running'})

if __name__ == '__main__':
    print("Starting FTP Sync Backend with DEBUG logging...")
    print("Backend will be available at: http://127.0.0.1:5000")
    print("Watch this terminal for detailed connection logs...")
    app.run(debug=True, host='127.0.0.1', port=5000)