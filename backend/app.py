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
        "methods": ["GET", "POST", "OPTIONS", "DELETE", "PUT", "PATCH"],
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
            
            # Update scheduler rotation order if provided
            if 'rotation_order' in data['scheduling']:
                scheduler_postgres.update_rotation_order(data['scheduling']['rotation_order'])
        
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
        dry_run = data.get('dry_run', False)
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
            direction = item.get('direction', 'source_to_target')  # Default to source->target
            folder = file_info.get('folder', 'on-air')  # Get folder type
            filename = file_info['name']
            relative_path = file_info.get('path', filename)
            
            logger.info(f"Processing file: {filename}")
            logger.info(f"  Relative path: {relative_path}")
            logger.info(f"  Full path: {file_info.get('full_path', 'Not set')}")
            logger.info(f"  Folder: {folder}")
            logger.info(f"  Action: {action}")
            logger.info(f"  Direction: {direction}")
            logger.info(f"  Dry run: {dry_run}")
            
            try:
                if dry_run:
                    results.append({
                        'file': filename,
                        'action': action,
                        'status': 'would_sync',
                        'size': file_info['size'],
                        'direction': direction,
                        'id': item.get('id', f"{filename}_{file_info['size']}")
                    })
                    logger.info(f"  Would sync {filename}")
                else:
                    logger.info(f"  Starting actual sync for {filename}")
                    
                    # Perform actual sync
                    try:
                        # For recordings folder, we need to use different base paths
                        if folder == 'recordings':
                            logger.info(f"  Using Recordings folder paths")
                            # Create temporary FTP managers with Recordings paths
                            from ftp_manager import FTPManager
                            
                            source_recordings_config = config_manager.get_all_config()['servers']['source'].copy()
                            source_recordings_config['path'] = '/mnt/main/Recordings'
                            
                            target_recordings_config = config_manager.get_all_config()['servers']['target'].copy()
                            target_recordings_config['path'] = '/mnt/main/Recordings'
                            
                            source_recordings_ftp = FTPManager(source_recordings_config)
                            target_recordings_ftp = FTPManager(target_recordings_config)
                            
                            if not source_recordings_ftp.connect() or not target_recordings_ftp.connect():
                                raise Exception("Failed to connect with Recordings paths")
                            
                            # Use recordings-specific FTP connections
                            if direction == 'target_to_source':
                                src_ftp = target_recordings_ftp
                                dst_ftp = source_recordings_ftp
                                logger.info(f"  Direction: target -> source (Recordings)")
                            else:
                                src_ftp = source_recordings_ftp
                                dst_ftp = target_recordings_ftp
                                logger.info(f"  Direction: source -> target (Recordings)")
                        else:
                            # Use regular FTP connections for On-Air Content
                            if direction == 'target_to_source':
                                src_ftp = target_ftp
                                dst_ftp = source_ftp
                                logger.info(f"  Direction: target -> source")
                            else:
                                src_ftp = source_ftp
                                dst_ftp = target_ftp
                                logger.info(f"  Direction: source -> target")
                        
                        if action == 'copy':
                            logger.info(f"  Copying file: {filename}")
                            success = src_ftp.copy_file_to(file_info, dst_ftp, keep_temp=keep_temp_files)
                        else:  # update
                            logger.info(f"  Updating file: {filename}")
                            success = src_ftp.update_file_to(file_info, dst_ftp, keep_temp=keep_temp_files)
                        
                        # Disconnect recordings FTP if used
                        if folder == 'recordings':
                            source_recordings_ftp.disconnect()
                            target_recordings_ftp.disconnect()
                        
                        logger.info(f"  Sync result for {filename}: {success}")
                        
                        if success:
                            results.append({
                                'file': filename,
                                'action': action,
                                'status': 'success',
                                'size': file_info['size'],
                                'direction': direction,
                                'id': item.get('id', f"{filename}_{file_info['size']}")
                            })
                            logger.info(f"  ✅ Successfully synced {filename}")
                        else:
                            results.append({
                                'file': filename,
                                'action': action,
                                'status': 'failed',
                                'error': 'File transfer failed - check FTP connection and permissions',
                                'details': f'Failed to {action} {relative_path}',
                                'direction': direction,
                                'id': item.get('id', f"{filename}_{file_info['size']}")
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
                            'details': f'Exception during {action} of {relative_path}',
                            'direction': direction,
                            'id': item.get('id', f"{filename}_{file_info['size']}")
                        })
                    
            except Exception as item_error:
                error_msg = str(item_error)
                logger.error(f"Error processing item {filename}: {error_msg}", exc_info=True)
                
                results.append({
                    'file': filename,
                    'action': action,
                    'status': 'error',
                    'error': error_msg,
                    'details': f'Error processing sync item for {relative_path}',
                    'direction': direction,
                    'id': item.get('id', f"{filename}_{file_info['size']}")
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
        dry_run = data.get('dry_run', False)
        
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
            
            # Reset all scheduling metadata to use encoded_date as last_scheduled_date
            cursor.execute("""
                UPDATE scheduling_metadata sm
                SET last_scheduled_date = i.encoded_date, 
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
                FROM instances i
                WHERE sm.asset_id = i.asset_id AND i.is_primary = true
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


@app.route('/api/create-monthly-schedule', methods=['POST'])
def create_monthly_schedule():
    """Create a monthly schedule"""
    logger.info("=== CREATE MONTHLY SCHEDULE REQUEST ===")
    try:
        data = request.json
        year = data.get('year')
        month = data.get('month')
        
        logger.info(f"Creating monthly schedule for: {year}-{month:02d}")
        
        if not year or not month:
            return jsonify({
                'success': False,
                'message': 'Year and month are required'
            })
        
        # Get max errors from config
        scheduling_config = config_manager.get_scheduling_settings()
        max_errors = scheduling_config.get('max_consecutive_errors', 100)
        
        # Create monthly schedule using PostgreSQL scheduler
        result = scheduler_postgres.create_monthly_schedule(year, month, max_errors)
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Create monthly schedule error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/generate-simple-playlist', methods=['POST'])
def generate_simple_playlist():
    """Generate a simple playlist from specified folder"""
    logger.info("=== GENERATE SIMPLE PLAYLIST REQUEST ===")
    logger.debug("DEBUG: Endpoint hit - generate_simple_playlist")
    try:
        data = request.json
        logger.debug(f"DEBUG: Request data: {data}")
        
        # Get parameters from request
        server = data.get('server', 'source')
        source_path = data.get('source_path', '/mnt/main/ATL26 On-Air Content/FILL/GLOBAL FILL')
        export_path = data.get('export_path', '/mnt/main/Playlists')
        filename = data.get('filename', 'simple playlist')
        item_count = data.get('item_count', None)  # None means all items
        shuffle = data.get('shuffle', False)
        
        # Add .ply extension if not present
        if not filename.endswith('.ply'):
            filename = filename + '.ply'
        
        logger.debug(f"DEBUG: Server: {server}, Source: {source_path}, Export: {export_path}, Filename: {filename}")
        logger.debug(f"DEBUG: Item count: {item_count}, Shuffle: {shuffle}")
        
        # Get the appropriate FTP server
        if server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{server.capitalize()} server not connected. Please connect to FTP servers first.'
            })
        
        source_ftp = ftp_managers[server]
        
        # List files in the specified directory
        try:
            files = []
            
            try:
                logger.info(f"Listing files from: {source_path}")
                ftp_files = source_ftp.list_files(source_path)
                
                if ftp_files:
                    files = [(os.path.join(source_path, f['name']), f['name']) 
                            for f in ftp_files if f['name'].endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv'))]
                    logger.info(f"Found {len(files)} video files in {source_path}")
                else:
                    logger.warning(f"No files found in {source_path}")
                    
            except Exception as e:
                logger.error(f"Error accessing path {source_path}: {str(e)}")
                return jsonify({
                    'success': False,
                    'message': f'Error accessing path: {str(e)}'
                })
            
            if not files:
                return jsonify({
                    'success': False,
                    'message': f'No video files found in {source_path}. Please check that the folder exists and contains video files.'
                })
            
            # Apply shuffle if requested
            if shuffle:
                import random
                random.shuffle(files)
                logger.info("Files shuffled randomly")
            
            # Apply item count limit if specified
            original_count = len(files)
            if item_count and item_count < len(files):
                files = files[:item_count]
                logger.info(f"Limited playlist to {item_count} items (from {original_count})")
            
            # Log first few files for debugging
            if files:
                logger.debug(f"First 5 files: {files[:5]}")
            
            # Generate playlist content
            playlist_content = generate_simple_playlist_content(files)
            
            # Log playlist content length for debugging
            logger.debug(f"Generated playlist content length: {len(playlist_content)} characters")
            
            # Write to the specified FTP server
            if server not in ftp_managers:
                return jsonify({
                    'success': False,
                    'message': f'{server.capitalize()} server not connected'
                })
            
            ftp_manager = ftp_managers[server]
            
            # Create full file path
            full_path = os.path.join(export_path, filename)
            
            # Create a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
                temp_file.write(playlist_content)
                temp_file_path = temp_file.name
            
            try:
                # Upload to FTP
                ftp_manager.upload_file(temp_file_path, full_path)
                
                # Clean up temp file
                os.unlink(temp_file_path)
                
                logger.info(f"Successfully generated playlist with {len(files)} files at {full_path}")
                
                return jsonify({
                    'success': True,
                    'message': f'Playlist created and exported to {full_path}',
                    'file_count': len(files)
                })
                
            except Exception as upload_error:
                # Clean up temp file on error
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                raise upload_error
                
        except Exception as ftp_error:
            logger.error(f"FTP error: {str(ftp_error)}")
            return jsonify({
                'success': False,
                'message': f'Error accessing FTP server: {str(ftp_error)}'
            })
            
    except Exception as e:
        error_msg = f"Generate playlist error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/preview-playlist-files', methods=['POST'])
def preview_playlist_files():
    """Preview files that would be included in a playlist"""
    logger.info("=== PREVIEW PLAYLIST FILES REQUEST ===")
    try:
        data = request.json
        server = data.get('server', 'source')
        path = data.get('path', '')
        
        if not path:
            return jsonify({
                'success': False,
                'message': 'Path is required'
            })
        
        # Get the appropriate FTP server
        if server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{server.capitalize()} server not connected'
            })
        
        ftp = ftp_managers[server]
        
        try:
            # List files in the directory
            ftp_files = ftp.list_files(path)
            
            # Filter for video files
            video_files = [f['name'] for f in ftp_files 
                          if f['name'].endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv'))]
            
            logger.info(f"Found {len(video_files)} video files in preview")
            
            return jsonify({
                'success': True,
                'files': video_files,
                'total_count': len(video_files)
            })
            
        except Exception as e:
            logger.error(f"Error previewing files: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Error accessing path: {str(e)}'
            })
            
    except Exception as e:
        error_msg = f"Preview playlist files error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/list-playlists', methods=['GET'])
def list_playlists():
    """List all playlists from both FTP servers"""
    logger.info("=== LIST PLAYLISTS REQUEST ===")
    try:
        # Get playlists from both servers
        all_playlists = []
        
        # Define possible playlist locations
        # Note: /mnt/main is a symlink to /mnt/md127, so we only need one
        playlist_paths = [
            '/mnt/main/Playlists',
            '/mnt/main/Playlists/Contributors'  # Will search all subfolders
        ]
        
        # Check both servers
        logger.info(f"Available FTP managers: {list(ftp_managers.keys())}")
        for server_name in ['target', 'source']:
            logger.info(f"=== Checking {server_name} server ===")
            if server_name not in ftp_managers:
                logger.warning(f"{server_name} server not connected, skipping")
                continue
                
            ftp_manager = ftp_managers[server_name]
            logger.info(f"Successfully got {server_name} FTP manager")
            
            # Check each possible path
            for playlist_path in playlist_paths:
                paths_to_check = [playlist_path]
                
                # If this is the Contributors path, get all subdirectories
                if playlist_path.endswith('/Contributors'):
                    try:
                        contrib_files = ftp_manager.list_files(playlist_path)
                        # Add all subdirectories
                        for item in contrib_files:
                            if item.get('is_dir', False) or item.get('permissions', '').startswith('d'):
                                subdir_path = os.path.join(playlist_path, item['name'])
                                paths_to_check.append(subdir_path)
                                logger.info(f"Added contributor subdirectory: {subdir_path}")
                    except Exception as e:
                        logger.warning(f"Could not list Contributors subdirectories: {str(e)}")
                
                # Now check each path (including subdirectories)
                for check_path in paths_to_check:
                    try:
                        files = ftp_manager.list_files(check_path)
                        logger.info(f"Found {len(files)} files in {check_path} on {server_name}")
                    
                        # Filter for playlist files (.ply extension or no extension)
                        import tempfile
                        import json
                        
                        for file in files:
                            logger.debug(f"Checking file: {file['name']} on {server_name} in {check_path}")
                            # Include .ply files and files without extensions (excluding .sch)
                            is_playlist = (file['name'].endswith('.ply') or 
                                         ('.' not in file['name'] or file['name'].count('.') == 0) and 
                                         not file['name'].endswith('.sch'))
                            
                            if is_playlist:
                                # Parse creation date from file info if available
                                created_date = datetime.now().isoformat()  # Default to now
                                
                                # Try to read the playlist to get actual item count
                                item_count = 0
                                try:
                                    full_path = os.path.join(check_path, file['name'])
                                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                                        temp_path = temp_file.name
                                    
                                    # Download and parse the playlist
                                    ftp_manager.download_file(full_path, temp_path)
                                    with open(temp_path, 'r') as f:
                                        content = f.read()
                                    
                                    # Try to parse as regular JSON first
                                    try:
                                        playlist_data = json.loads(content)
                                    except json.JSONDecodeError:
                                        # Try Castus format (add outer braces)
                                        try:
                                            playlist_data = json.loads('{' + content + '}')
                                            # Count items in the playlist
                                            playlist_desc = playlist_data.get('playlist description', {})
                                            item_count = len(playlist_desc.get('list', []))
                                        except json.JSONDecodeError:
                                            logger.warning(f"Failed to parse playlist {file['name']}")
                                            item_count = 0
                                            # Don't continue - still add the playlist with 0 items
                                    else:
                                        # Count items in the playlist (for regular JSON)
                                        playlist_desc = playlist_data.get('playlist description', {})
                                        item_count = len(playlist_desc.get('list', []))
                                    
                                    # Clean up temp file
                                    os.unlink(temp_path)
                                except Exception as e:
                                    logger.warning(f"Could not read playlist {file['name']} to count items: {str(e)}")
                                    item_count = 0
                                
                                playlist_info = {
                                    'id': len(all_playlists) + 1,  # Use all_playlists for unique ID
                                    'name': file['name'],
                                    'description': f'Playlist file from {check_path} on {server_name}',
                                    'path': check_path,
                                    'created_date': created_date,
                                    'item_count': item_count,
                                    'file_size': file.get('size', 0),
                                    'server': server_name
                                }
                                all_playlists.append(playlist_info)
                        
                    except Exception as e:
                        logger.error(f"Error listing playlists in {check_path} on {server_name}: {str(e)}")
                        # Continue to next path instead of failing completely
                        continue
        
        logger.info(f"Found {len(all_playlists)} playlists total")
        
        return jsonify({
            'success': True,
            'playlists': all_playlists
        })
            
    except Exception as e:
        error_msg = f"List playlists error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/playlist/<int:playlist_id>/items', methods=['GET'])
def get_playlist_items(playlist_id):
    """Get items from a specific playlist"""
    logger.info(f"=== GET PLAYLIST ITEMS REQUEST - ID: {playlist_id} ===")
    
    # Get server and path from query parameters
    server = request.args.get('server', 'target')
    playlist_path = request.args.get('path', '/mnt/main/Playlists')
    logger.info(f"Looking for playlist on {server} server at {playlist_path}")
    
    try:
        # Check if specified FTP is connected
        if server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{server.capitalize()} server not connected'
            })
        
        ftp_manager = ftp_managers[server]
        
        # Get the playlist name by listing files in the specified path
        files = ftp_manager.list_files(playlist_path)
        
        # Find the playlist by ID (using index)
        playlist_files = [f for f in files if not f['name'].endswith('.sch')]
        logger.info(f"Found {len(playlist_files)} playlists on {server} server")
        
        if playlist_id > len(playlist_files) or playlist_id < 1:
            logger.warning(f"Playlist ID {playlist_id} not found on {server} server (have {len(playlist_files)} playlists)")
            return jsonify({
                'success': False,
                'message': f'Playlist not found on {server} server'
            })
        
        playlist_file = playlist_files[playlist_id - 1]
        playlist_name = playlist_file['name']
        full_path = os.path.join(playlist_path, playlist_name)
        
        # Download and read the playlist file
        import tempfile
        import json
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Download the playlist file
            ftp_manager.download_file(full_path, temp_path)
            
            # Read and parse the content - handle Castus format (no outer braces)
            with open(temp_path, 'r') as f:
                content = f.read()
            
            logger.debug(f"Read playlist content (first 200 chars): {content[:200]}")
            
            # Try to parse as regular JSON first
            try:
                playlist_data = json.loads(content)
                playlist_desc = playlist_data.get('playlist description', {})
                logger.debug("Parsed as regular JSON")
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse as regular JSON: {str(e)}")
                # Try Castus format (add outer braces)
                try:
                    playlist_data = json.loads('{' + content + '}')
                    playlist_desc = playlist_data.get('playlist description', {})
                    logger.debug("Parsed as Castus format (added outer braces)")
                except json.JSONDecodeError as e2:
                    logger.error(f"Failed to parse playlist file: {str(e2)}")
                    logger.error(f"Content sample: {content[:500]}")
                    return jsonify({
                        'success': False,
                        'message': 'Invalid playlist format'
                    })
            
            # Extract playlist info and items
            # playlist_desc is already extracted above
            items = []
            
            # Debug log the structure
            logger.debug(f"Playlist data keys: {list(playlist_data.keys())}")
            logger.debug(f"Playlist description keys: {list(playlist_desc.keys())}")
            logger.debug(f"Number of items in list: {len(playlist_desc.get('list', []))}")
            
            for idx, item in enumerate(playlist_desc.get('list', [])):
                # Log first item for debugging
                if idx == 0:
                    logger.debug(f"First item structure: {item}")
                
                item_info = {
                    'id': idx + 1,
                    'position': idx,
                    'file_path': item.get('path', ''),
                    'file_name': os.path.basename(item.get('path', '')),
                    'duration': item.get('duration', 0),
                    'start_frame': item.get('startFrame', 0),
                    'end_frame': item.get('endFrame', 0)
                }
                items.append(item_info)
            
            playlist = {
                'id': playlist_id,
                'name': playlist_name,
                'description': f'Playlist from {playlist_path}',
                'created_date': datetime.now().isoformat(),
                'play_mode': playlist_desc.get('play mode', 'sequential'),
                'auto_remove': playlist_desc.get('auto remove', True)
            }
            
            # Clean up temp file
            os.unlink(temp_path)
            
            logger.info(f"Successfully read playlist with {len(items)} items")
            
            return jsonify({
                'success': True,
                'playlist': playlist,
                'items': items,
                'total_items': len(items)
            })
            
        except Exception as read_error:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise read_error
            
    except Exception as e:
        error_msg = f"Get playlist items error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/playlist/<int:playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    """Delete a playlist from the FTP server"""
    logger.info(f"=== DELETE PLAYLIST REQUEST - ID: {playlist_id} ===")
    
    # Get server and path from query parameters
    server = request.args.get('server', 'target')
    playlist_path = request.args.get('path', '/mnt/main/Playlists')
    logger.info(f"Deleting playlist from {server} server at {playlist_path}")
    
    try:
        # Check if specified FTP is connected
        if server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{server.capitalize()} server not connected'
            })
        
        ftp_manager = ftp_managers[server]
        
        # Get the playlist name by listing files in the specified path
        files = ftp_manager.list_files(playlist_path)
        
        # Find the playlist by ID
        playlist_files = []
        for f in files:
            logger.debug(f"Checking file for deletion: {f['name']}")
            # Include .ply files and files without extensions (excluding .sch)
            has_no_extension = '.' not in f['name']
            has_ply_extension = f['name'].endswith('.ply')
            is_not_sch = not f['name'].endswith('.sch')
            
            is_playlist = (has_ply_extension or (has_no_extension and is_not_sch))
            logger.debug(f"File {f['name']}: no_ext={has_no_extension}, ply={has_ply_extension}, not_sch={is_not_sch}, is_playlist={is_playlist}")
            
            if is_playlist:
                playlist_files.append(f)
        
        logger.info(f"Found {len(playlist_files)} playlists in {playlist_path}: {[p['name'] for p in playlist_files]}")
        
        # Special handling: if we can't find the playlist in the provided path,
        # it might be because the path is wrong (e.g., playlist is in a subdirectory)
        if playlist_id > len(playlist_files) or playlist_id < 1:
            logger.warning(f"Playlist ID {playlist_id} not found in {playlist_path} (have {len(playlist_files)} playlists)")
            
            # Try to get the playlist name from the request or return error
            playlist_name = request.args.get('name')
            if playlist_name:
                # Try to delete by name directly
                try:
                    full_path = os.path.join(playlist_path, playlist_name)
                    ftp_manager.ftp.delete(full_path)
                    logger.info(f"Successfully deleted playlist by name: {playlist_name}")
                    return jsonify({
                        'success': True,
                        'message': f'Playlist "{playlist_name}" deleted successfully'
                    })
                except Exception as del_error:
                    logger.error(f"Failed to delete playlist by name: {del_error}")
            
            return jsonify({
                'success': False,
                'message': f'Playlist not found in {playlist_path}'
            })
        
        playlist_file = playlist_files[playlist_id - 1]
        playlist_name = playlist_file['name']
        full_path = os.path.join(playlist_path, playlist_name)
        
        # Delete the file from FTP
        ftp_manager.ftp.delete(full_path)
        
        logger.info(f"Successfully deleted playlist: {playlist_name}")
        
        return jsonify({
            'success': True,
            'message': f'Playlist "{playlist_name}" deleted successfully'
        })
        
    except Exception as e:
        error_msg = f"Delete playlist error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/playlist/<int:playlist_id>/export', methods=['POST'])
def export_playlist(playlist_id):
    """Export a playlist with customizable options"""
    logger.info(f"=== EXPORT PLAYLIST REQUEST - ID: {playlist_id} ===")
    try:
        data = request.get_json()
        
        # Get parameters with defaults
        source_server = data.get('source_server', 'target')  # Server where playlist currently is
        export_server = data.get('server', 'target')  # Destination server
        export_path = data.get('export_path', '/mnt/main/Playlists')
        filename = data.get('filename', '')
        item_count = data.get('item_count', None)  # None means all items
        shuffle = data.get('shuffle', False)
        
        logger.info(f"Export parameters: source={source_server}, dest={export_server}, path={export_path}, filename={filename}, item_count={item_count}, shuffle={shuffle}")
        
        # Get the playlist file from source server
        if source_server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{source_server.capitalize()} server not connected'
            })
        
        source_ftp_manager = ftp_managers[source_server]
        playlist_path = '/mnt/main/Playlists'
        files = source_ftp_manager.list_files(playlist_path)
        
        # Find the playlist by ID
        playlist_files = [f for f in files if not f['name'].endswith('.sch')]
        if playlist_id > len(playlist_files) or playlist_id < 1:
            return jsonify({
                'success': False,
                'message': 'Playlist not found'
            })
        
        playlist_file = playlist_files[playlist_id - 1]
        playlist_name = playlist_file['name']
        source_full_path = os.path.join(playlist_path, playlist_name)
        
        # Download and read the playlist
        import tempfile
        import json
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Download the playlist file
            source_ftp_manager.download_file(source_full_path, temp_path)
            
            # Read and parse the content - handle Castus format (no outer braces)
            with open(temp_path, 'r') as f:
                content = f.read()
            
            # Try to parse as regular JSON first
            try:
                playlist_data = json.loads(content)
                playlist_desc = playlist_data.get('playlist description', {})
            except json.JSONDecodeError:
                # Try Castus format (add outer braces)
                try:
                    playlist_data = json.loads('{' + content + '}')
                    playlist_desc = playlist_data.get('playlist description', {})
                except json.JSONDecodeError:
                    logger.error("Failed to parse playlist file")
                    return jsonify({
                        'success': False,
                        'message': 'Invalid playlist format'
                    })
            
            # Extract items
            items = playlist_desc.get('list', [])
            
            # Apply filtering/modifications
            if shuffle:
                import random
                items = items.copy()
                random.shuffle(items)
            
            if item_count is not None and item_count < len(items):
                items = items[:item_count]
            
            # Update the playlist data
            playlist_desc['list'] = items
            
            # Use provided filename or default to original
            if not filename:
                filename = playlist_name
            
            # Ensure .ply extension
            if not filename.endswith('.ply'):
                filename = filename + '.ply'
            
            # Write modified playlist to temp file in Castus format (no outer braces)
            with open(temp_path, 'w') as f:
                # Create the full object, then manually format it
                full_obj = {"playlist description": playlist_desc}
                json_str = json.dumps(full_obj, indent=2)
                
                # Remove the outer braces for Castus format
                lines = json_str.split('\n')
                if lines[0] == '{' and lines[-1] == '}':
                    lines = lines[1:-1]
                    # Also remove the extra indentation from all lines
                    lines = [line[2:] if line.startswith('  ') else line for line in lines]
                
                f.write('\n'.join(lines))
            
            # Upload to destination
            dest_ftp_manager = ftp_managers[export_server]
            dest_full_path = os.path.join(export_path, filename)
            
            success = dest_ftp_manager.upload_file(temp_path, dest_full_path)
            
            if success:
                logger.info(f"Playlist exported successfully to {dest_full_path}")
                return jsonify({
                    'success': True,
                    'message': f'Playlist exported to: {dest_full_path}',
                    'path': dest_full_path,
                    'item_count': len(items)
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to upload playlist to destination'
                })
                
        finally:
            # Clean up temp file
            os.unlink(temp_path)
        
    except Exception as e:
        error_msg = f"Export playlist error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/playlist/<int:playlist_id>/item/<int:item_id>', methods=['DELETE'])
def remove_playlist_item(playlist_id, item_id):
    """Remove an item from a playlist"""
    logger.info(f"=== REMOVE PLAYLIST ITEM REQUEST - Playlist: {playlist_id}, Item: {item_id} ===")
    try:
        # This would need to:
        # 1. Download the playlist file
        # 2. Parse and modify it
        # 3. Re-upload it
        # For now, return a message indicating this feature needs implementation
        
        return jsonify({
            'success': False,
            'message': 'Removing playlist items requires downloading, modifying, and re-uploading the playlist file. This feature is not yet implemented.'
        })
        
    except Exception as e:
        error_msg = f"Remove playlist item error: {str(e)}"
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
        if format_type == 'castus' or format_type == 'castus_weekly' or format_type == 'castus_monthly':
            # Determine export format
            if format_type == 'castus_weekly':
                export_format = 'weekly'
            elif format_type == 'castus_monthly':
                export_format = 'monthly'
            else:
                export_format = 'daily'
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

def generate_simple_playlist_content(files):
    """Generate content for a simple playlist in Castus format (no outer braces)"""
    import json
    
    logger.debug(f"generate_simple_playlist_content called with {len(files)} files")
    
    playlist_desc = {
        "title": "",
        "author": "",
        "play mode": "sequential",
        "auto remove": True,
        "editor view": {
            "cursor frame": 0,
            "view start": 0,
            "view end": 299.7002997002997
        },
        "aspect ratio": {
            "n": 16,
            "d": 9
        },
        "timeline rate": {
            "n": 30000,
            "d": 1001
        },
        "list": [],
        "duration": 0,
        "invisible": False,
        "mute": False
    }
    
    # Add each file to the playlist
    for file_path, file_name in files:
        logger.debug(f"Processing file: {file_name} at {file_path}")
        # Ensure proper path format
        if not file_path.startswith('/mnt/main/ATL26 On-Air Content/'):
            # Reconstruct the path
            file_path = f"/mnt/main/ATL26 On-Air Content/FILL/GLOBAL FILL/{file_name}"
        
        item = {
            "startFrame": 0,
            "endFrame": 0,
            "offsetFrame": None,
            "start": 0,
            "end": 0,
            "offset": None,
            "durationFrame": 0,
            "duration": 0,
            "isSelected": False,
            "path": file_path,
            "item duration": 0
        }
        playlist_desc["list"].append(item)
    
    logger.debug(f"Total items added to playlist: {len(playlist_desc['list'])}")
    
    # Format without outer braces to match Castus format
    # First create the full object, then manually format it
    full_obj = {"playlist description": playlist_desc}
    json_str = json.dumps(full_obj, indent=2)
    
    # Remove the outer braces
    lines = json_str.split('\n')
    if lines[0] == '{' and lines[-1] == '}':
        lines = lines[1:-1]
        # Also remove the extra indentation from all lines
        lines = [line[2:] if line.startswith('  ') else line for line in lines]
    
    return '\n'.join(lines)

def generate_castus_schedule(schedule, items, date, format_type='daily'):
    # Reset day counter for weekly schedules
    generate_castus_schedule.current_day = 0
    """Generate schedule content in Castus format"""
    
    lines = []
    
    # Parse the date to get day of week
    schedule_date = datetime.strptime(date, '%Y-%m-%d')
    day_of_week = schedule_date.weekday()  # 0=Monday, 6=Sunday
    day_name = schedule_date.strftime('%a').lower()  # mon, tue, wed, etc.
    
    if format_type == 'monthly':
        # Monthly format header
        lines.append("*monthly")
        lines.append("defaults, day of the month{")
        lines.append("}")
        lines.append("year = ")  # Empty as per sample
        lines.append(f"month = {schedule_date.month}")
        lines.append(f"day = {schedule_date.day}")
        lines.append("time slot length = 30")
        lines.append("scrolltime = 12:00 am")
        lines.append("filter script = ")
        lines.append("global default=")
        lines.append("text encoding = UTF-8")
        lines.append("schedule format version = 5.0.0.4 2021/01/15")
    elif format_type == 'weekly':
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
    
    # Track previous end time for overlap detection
    previous_end_seconds = 0.0
    
    # Debug first few items
    if items and len(items) > 0:
        logger.debug("First 5 items from database:")
        for i, item in enumerate(items[:5]):
            st = item.get('scheduled_start_time', 'None')
            logger.debug(f"  Item {i}: scheduled_start_time={st}, type={type(st)}")
    
    # Add schedule items
    for idx, item in enumerate(items):
        start_time = item.get('scheduled_start_time', item.get('start_time', '00:00:00'))
        # Handle both field names for compatibility
        duration_seconds = float(item.get('scheduled_duration_seconds', item.get('duration_seconds', 0)))
        
        # Check if we have a pre-calculated end time
        end_time_provided = item.get('scheduled_end_time', item.get('end_time'))
        
        # Debug log
        logger.debug(f"Item {idx}: start_time={start_time}, duration_seconds={duration_seconds}")
        if end_time_provided:
            logger.debug(f"  Using provided end_time: {end_time_provided}")
        if 'scheduled_duration_seconds' in item:
            logger.debug(f"  Using scheduled_duration_seconds: {item['scheduled_duration_seconds']}")
        if 'duration_seconds' in item:
            logger.debug(f"  Item also has duration_seconds: {item['duration_seconds']}")
        
        # Calculate end time
        # Handle different time formats
        if isinstance(start_time, str):
            # Check if this is a weekly format time (e.g., "sun 12:00:00 am")
            if ' ' in start_time and any(day in start_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                # Parse weekly format
                parts = start_time.split(' ', 1)
                day_name = parts[0]
                time_part = parts[1] if len(parts) > 1 else '12:00:00 am'
                
                # Convert 12-hour format to 24-hour
                time_24 = convert_to_24hour_format(time_part)
                if '.' in time_24:
                    time_base, micro_str = time_24.split('.')
                    time_parts = time_base.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    microseconds = int(micro_str.ljust(6, '0')[:6])
                    start_dt = datetime(2000, 1, 1, hours, minutes, seconds, microseconds)
                else:
                    time_parts = time_24.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    start_dt = datetime(2000, 1, 1, hours, minutes, seconds)
            # Check if time has AM/PM first (before checking for microseconds)
            elif 'am' in start_time.lower() or 'pm' in start_time.lower():
                # Convert to 24-hour format first
                time_24 = convert_to_24hour_format(start_time)
                if '.' in time_24:
                    time_base, micro_str = time_24.split('.')
                    time_parts = time_base.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    microseconds = int(micro_str.ljust(6, '0')[:6])
                    start_dt = datetime(2000, 1, 1, hours, minutes, seconds, microseconds)
                else:
                    time_parts = time_24.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    start_dt = datetime(2000, 1, 1, hours, minutes, seconds)
            # Handle time with microseconds (HH:MM:SS.ffffff) in 24-hour format
            elif '.' in start_time:
                # Has microseconds - parse them
                time_base, micro_str = start_time.split('.')
                time_parts = time_base.split(':')
                hours = int(time_parts[0])
                minutes = int(time_parts[1])
                seconds = int(time_parts[2])
                microseconds = int(micro_str.ljust(6, '0')[:6])  # Pad or truncate to 6 digits
                start_dt = datetime(2000, 1, 1, hours, minutes, seconds, microseconds)
            else:
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
        
        # If we have a provided end time, use it instead of calculating
        if end_time_provided and isinstance(end_time_provided, str):
            # Parse the provided end time
            if ' ' in end_time_provided and any(day in end_time_provided.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                # Weekly format end time
                parts = end_time_provided.split(' ', 1)
                time_part = parts[1] if len(parts) > 1 else '12:00:00 am'
                time_24 = convert_to_24hour_format(time_part)
                if '.' in time_24:
                    time_base, micro_str = time_24.split('.')
                    time_parts = time_base.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    microseconds = int(micro_str.ljust(6, '0')[:6])
                    end_dt = datetime(2000, 1, 1, hours, minutes, seconds, microseconds)
                else:
                    time_parts = time_24.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    end_dt = datetime(2000, 1, 1, hours, minutes, seconds)
            elif '.' in end_time_provided:
                # Has microseconds - check if it's 12-hour format with AM/PM
                if 'am' in end_time_provided.lower() or 'pm' in end_time_provided.lower():
                    # Convert to 24-hour format first
                    time_24 = convert_to_24hour_format(end_time_provided)
                    if '.' in time_24:
                        time_base, micro_str = time_24.split('.')
                        time_parts = time_base.split(':')
                        hours = int(time_parts[0])
                        minutes = int(time_parts[1])
                        seconds = int(time_parts[2])
                        microseconds = int(micro_str.ljust(6, '0')[:6])
                        end_dt = datetime(2000, 1, 1, hours, minutes, seconds, microseconds)
                    else:
                        time_parts = time_24.split(':')
                        hours = int(time_parts[0])
                        minutes = int(time_parts[1])
                        seconds = int(time_parts[2])
                        end_dt = datetime(2000, 1, 1, hours, minutes, seconds)
                else:
                    # Already in 24-hour format
                    time_base, micro_str = end_time_provided.split('.')
                    time_parts = time_base.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    microseconds = int(micro_str.ljust(6, '0')[:6])
                    end_dt = datetime(2000, 1, 1, hours, minutes, seconds, microseconds)
            else:
                # Regular time format - check for AM/PM
                if 'am' in end_time_provided.lower() or 'pm' in end_time_provided.lower():
                    # Convert to 24-hour format first
                    time_24 = convert_to_24hour_format(end_time_provided)
                    time_parts = time_24.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2]) if len(time_parts) > 2 else 0
                    end_dt = datetime(2000, 1, 1, hours, minutes, seconds)
                else:
                    # Already in 24-hour format
                    time_parts = end_time_provided.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2]) if len(time_parts) > 2 else 0
                    end_dt = datetime(2000, 1, 1, hours, minutes, seconds)
            
            # Recalculate duration based on provided times
            duration_seconds = (end_dt - start_dt).total_seconds()
        else:
            # Calculate end time from duration
            end_dt = start_dt + timedelta(seconds=duration_seconds)
        
        # Extract milliseconds from duration
        whole_seconds = int(duration_seconds)
        milliseconds = int((duration_seconds - whole_seconds) * 1000)
        
        if format_type == 'monthly':
            # Monthly format times use "day N" prefix
            day_number = schedule_date.day
            
            # Format times with milliseconds
            start_time_formatted = f"day {day_number} " + start_dt.strftime("%I:%M:%S").lstrip("0")
            if start_dt.microsecond > 0:
                start_time_formatted += f".{start_dt.microsecond // 1000:03d}"
            start_time_formatted += " " + start_dt.strftime("%p").lower()
            
            end_time_formatted = f"day {day_number} " + end_dt.strftime("%I:%M:%S").lstrip("0") 
            end_milliseconds = end_dt.microsecond // 1000
            if end_milliseconds > 0:
                end_time_formatted += f".{end_milliseconds:03d}"
            end_time_formatted += " " + end_dt.strftime("%p").lower()
            
        elif format_type == 'weekly':
            # Weekly format times include day abbreviation
            # For weekly schedules, we need to track cumulative time to determine day boundaries
            # but use exact start times from previous items to avoid precision issues
            
            # Parse the actual start time from the database
            item_day_index = 0  # Default to Sunday
            if isinstance(start_time, str):
                # Check if this is a weekly format time with day prefix
                if ' ' in start_time and any(day in start_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                    # Extract day and time parts
                    parts = start_time.split(' ', 1)
                    day_name = parts[0].lower()
                    time_part = parts[1] if len(parts) > 1 else '12:00:00 am'
                    
                    # Get day index
                    day_map = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
                    item_day_index = day_map.get(day_name, 0)
                    
                    # Convert to 24-hour format
                    time_24 = convert_to_24hour_format(time_part)
                    time_parts = time_24.split(':')
                    db_hours = int(time_parts[0])
                    db_minutes = int(time_parts[1])
                    db_seconds = float(time_parts[2]) if len(time_parts) > 2 else 0
                else:
                    # Regular time format
                    time_parts = start_time.split(':')
                    db_hours = int(time_parts[0])
                    db_minutes = int(time_parts[1])
                    db_seconds = float(time_parts[2]) if len(time_parts) > 2 else 0
            else:
                # Handle datetime.time object from PostgreSQL
                db_hours = start_time.hour
                db_minutes = start_time.minute
                db_seconds = start_time.second + start_time.microsecond / 1000000.0
            
            # Calculate the actual start time in seconds from the database
            # For weekly schedules with day prefixes, use the day index directly
            # Check if we found a day prefix (has_day_prefix would be better but checking the original condition)
            if ' ' in start_time and any(day in start_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                # Calculate exact start time based on day index
                item_start_seconds = (item_day_index * 24 * 60 * 60) + (db_hours * 3600) + (db_minutes * 60) + db_seconds
                current_day = item_day_index
            elif idx == 0:
                item_start_seconds = 0.0
                current_day = 0
            else:
                # Check if we've moved to a new day by comparing with previous item
                prev_item = items[idx - 1]
                prev_start = prev_item.get('scheduled_start_time')
                
                if isinstance(prev_start, str):
                    # Check if this is a weekly format time with day prefix
                    if ' ' in prev_start and any(day in prev_start.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                        # Extract time part and convert to 24-hour
                        parts = prev_start.split(' ', 1)
                        time_part = parts[1] if len(parts) > 1 else '12:00:00 am'
                        time_24 = convert_to_24hour_format(time_part)
                        prev_parts = time_24.split(':')
                        prev_hours = int(prev_parts[0])
                    else:
                        prev_parts = prev_start.split(':')
                        prev_hours = int(prev_parts[0])
                else:
                    prev_hours = prev_start.hour
                
                # If current hour is less than previous, we've crossed midnight
                if db_hours < prev_hours:
                    current_day = getattr(generate_castus_schedule, 'current_day', 0) + 1
                    generate_castus_schedule.current_day = current_day
                else:
                    current_day = getattr(generate_castus_schedule, 'current_day', 0)
                
                # Calculate exact start time including day offset
                item_start_seconds = (current_day * 24 * 60 * 60) + (db_hours * 3600) + (db_minutes * 60) + db_seconds
                
                # Debug logging with comprehensive calculations
                end_calc_seconds = item_start_seconds + duration_seconds
                logger.debug(f"Export item {idx}:")
                logger.debug(f"  DB start_time: {start_time} (type: {type(start_time).__name__})")
                logger.debug(f"  Calculated start: {item_start_seconds:.6f}s = {item_start_seconds/3600:.2f}h")
                logger.debug(f"  Duration: {duration_seconds:.6f}s")
                logger.debug(f"  Calculated end: {end_calc_seconds:.6f}s = {end_calc_seconds/3600:.2f}h")
                if idx > 0:
                    logger.debug(f"  Previous end: {previous_end_seconds:.6f}s")
                    logger.debug(f"  Gap/Overlap: {item_start_seconds - previous_end_seconds:.6f}s")
                
                # Check for overlap with proper rounding to avoid floating-point precision issues
                OVERLAP_TOLERANCE = 0.001  # 1 millisecond tolerance
                if idx > 0:
                    # Round to millisecond precision to avoid floating-point errors
                    item_start_ms = round(item_start_seconds * 1000) / 1000
                    previous_end_ms = round(previous_end_seconds * 1000) / 1000
                    gap_or_overlap = item_start_ms - previous_end_ms
                    
                    if gap_or_overlap < -OVERLAP_TOLERANCE:
                        # Real overlap detected
                        overlap = -gap_or_overlap
                        logger.error(f"OVERLAP DETECTED at item {idx}: Previous end={previous_end_ms:.6f}, Current start={item_start_ms:.6f}, Overlap={overlap:.6f} seconds")
                        # Abort export with error message
                        return f"ERROR: Schedule has overlapping items at position {idx}. Item starts {overlap:.3f} seconds before previous item ends."
                    elif abs(gap_or_overlap) <= OVERLAP_TOLERANCE:
                        # Within tolerance - treat as continuous
                        logger.debug(f"  Note: Tiny gap/overlap of {gap_or_overlap:.9f}s is within tolerance")
                
                # If we detect a midnight crossing (database shows 00:xx:xx after high hours)
                expected_time_in_day = item_start_seconds % (24 * 60 * 60)
                if db_hours == 0 and expected_time_in_day > 20 * 60 * 60:  # After 8pm
                    # Advance to next day
                    current_day = int(item_start_seconds // (24 * 60 * 60))
                    item_start_seconds = (current_day + 1) * 24 * 60 * 60
            
            # Calculate which day of the week this item is on
            # For weekly schedules, use the actual day from the input if available
            if format_type == 'weekly' and ' ' in start_time and any(day in start_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                # Use the day name we already parsed
                day_names = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
                item_day_name = day_names[item_day_index]
            else:
                # Calculate based on offset for non-weekly or items without day prefix
                day_offset = int(item_start_seconds // (24 * 60 * 60))
                item_day = (schedule_date + timedelta(days=day_offset))
                item_day_name = item_day.strftime('%a').lower()
            
            # Format start time with actual milliseconds from database
            # Extract milliseconds from the actual start time
            start_milliseconds = start_dt.microsecond // 1000
            
            if idx == 0 and start_dt.hour == 0 and start_dt.minute == 0 and start_dt.microsecond == 0:
                start_time_formatted = f"{item_day_name} 12:00 am"
            else:
                start_time_formatted = f"{item_day_name} " + start_dt.strftime("%I:%M:%S").lstrip("0") + f".{start_milliseconds:03d} " + start_dt.strftime("%p").lower()
            
            # Debug the formatting
            logger.debug(f"  start_dt info: hour={start_dt.hour}, minute={start_dt.minute}, second={start_dt.second}, microsecond={start_dt.microsecond}")
            logger.debug(f"  start_milliseconds calculation: {start_dt.microsecond} // 1000 = {start_milliseconds}")
            logger.debug(f"  Formatted start: {start_time_formatted}")
            
            # For end time, use the actual end_dt if we have it
            if end_time_provided:
                # Use the end_dt we already parsed
                # For weekly schedules, check if end_time has a day prefix
                if format_type == 'weekly' and isinstance(end_time_provided, str) and ' ' in end_time_provided and any(day in end_time_provided.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                    # Extract the day name from the end time
                    parts = end_time_provided.split(' ', 1)
                    end_item_day_name = parts[0].lower()
                else:
                    # Calculate which day this end time falls on
                    end_seconds = item_start_seconds + duration_seconds
                    end_day_offset = int(end_seconds // (24 * 60 * 60))
                    end_item_day = schedule_date + timedelta(days=end_day_offset)
                    end_item_day_name = end_item_day.strftime('%a').lower()
                
                # Get milliseconds from the actual end_dt
                end_milliseconds = end_dt.microsecond // 1000
                
                # Format end time with actual values from end_dt
                end_time_formatted = f"{end_item_day_name} " + end_dt.strftime("%I:%M:%S").lstrip("0")
                if end_milliseconds > 0:
                    end_time_formatted += f".{end_milliseconds:03d}"
                else:
                    end_time_formatted += ".000"
                end_time_formatted += " " + end_dt.strftime("%p").lower()
            else:
                # Calculate based on actual start time and duration
                # This ensures proper alignment even with gaps
                end_seconds = item_start_seconds + duration_seconds
                end_day_offset = int(end_seconds // (24 * 60 * 60))
                end_time_in_day = end_seconds % (24 * 60 * 60)
                
                # Convert end time to hours, minutes, seconds
                end_hours = int(end_time_in_day // 3600)
                end_minutes = int((end_time_in_day % 3600) // 60)
                end_whole_seconds = int(end_time_in_day % 60)
                # Calculate milliseconds more precisely to avoid floating-point errors
                # Round to nearest millisecond to ensure consistency
                end_milliseconds = round((end_time_in_day % 1) * 1000)
                
                # Create end datetime for formatting
                end_dt_corrected = datetime(2000, 1, 1, end_hours, end_minutes, end_whole_seconds)
                end_item_day = schedule_date + timedelta(days=end_day_offset)
                end_item_day_name = end_item_day.strftime('%a').lower()
                
                # Format end time with actual milliseconds
                end_time_formatted = f"{end_item_day_name} " + end_dt_corrected.strftime("%I:%M:%S").lstrip("0") + f".{end_milliseconds:03d} " + end_dt_corrected.strftime("%p").lower()
            
            # Debug the end time formatting
            if 'end_time_in_day' in locals():
                logger.debug(f"  Formatted end: {end_time_formatted} (end_milliseconds: {end_milliseconds}, from {end_time_in_day % 1:.6f}s)")
            else:
                logger.debug(f"  Formatted end: {end_time_formatted} (end_milliseconds: {end_milliseconds})")
        else:
            # Daily format times
            # Extract actual milliseconds from start time
            start_milliseconds = start_dt.microsecond // 1000
            
            # Special handling for first item - should start at exactly 12:00 am
            if idx == 0 and start_dt.hour == 0 and start_dt.minute == 0 and start_milliseconds == 0:
                start_time_formatted = "12:00 am"
            else:
                # For all start times, include actual milliseconds
                start_time_formatted = start_dt.strftime("%I:%M:%S").lstrip("0")
                if start_milliseconds > 0:
                    start_time_formatted += f".{start_milliseconds:03d}"
                else:
                    start_time_formatted += ".000"
                start_time_formatted += " " + start_dt.strftime("%p").lower()
            
            # For end time, include the actual milliseconds from end_dt
            end_milliseconds = end_dt.microsecond // 1000
            end_time_formatted = end_dt.strftime("%I:%M:%S").lstrip("0") + f".{end_milliseconds:03d} " + end_dt.strftime("%p").lower()
        
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
        
        # Update previous end time for overlap detection
        if format_type == 'weekly':
            # Round to millisecond precision to match overlap detection
            previous_end_seconds = round((item_start_seconds + duration_seconds) * 1000) / 1000
    
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
            
            # Debug: Log first few items to see their times
            if schedule_data['type'] == 'weekly' and schedule_data['items']:
                logger.info("First 3 items from parsed weekly schedule:")
                for i, item in enumerate(schedule_data['items'][:3]):
                    logger.info(f"  Item {i}: start_time='{item.get('start_time')}', filename='{item.get('filename')}'")
            
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
            
            # Final debug before sending
            if schedule_data['type'] == 'weekly':
                logger.info("Sending weekly template to frontend with items:")
                for i, item in enumerate(schedule_data['items'][:3]):
                    logger.info(f"  Item {i}: start_time='{item.get('start_time')}'")
            
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
                
                # Debug logging for weekly schedules
                if schedule_data['type'] == 'weekly':
                    logger.debug(f"Weekly item raw start_time: '{item['start_time']}'")
                
                # Calculate duration from start/end times if available
                if item['start_time'] and item['end_time']:
                    duration = calculate_duration_from_times(item['start_time'], item['end_time'])
                    item['duration_seconds'] = duration
                    
                    # For weekly schedules, preserve the day prefix
                    if schedule_data['type'] == 'weekly' and ' ' in item['start_time']:
                        # Parse weekly format like "wed 12:00:15.040 am"
                        parts = item['start_time'].split(' ', 1)
                        if len(parts[0]) <= 3:  # Likely a day abbreviation
                            day_prefix = parts[0]
                            time_part = parts[1]
                            # Convert time part to 24-hour format
                            time_24h = convert_to_24hour_format(time_part)
                            # Reconstruct with day prefix
                            item['start_time'] = f"{day_prefix} {time_24h}"
                        else:
                            # No day prefix, just convert to 24-hour format
                            item['start_time'] = convert_to_24hour_format(item['start_time'])
                    else:
                        # For daily schedules, convert to 24-hour format
                        item['start_time'] = convert_to_24hour_format(item['start_time'])
                
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
    """Convert Castus time format (12-hour with am/pm) to 24-hour format (HH:MM:SS or HH:MM:SS.mmm)"""
    try:
        import re
        from datetime import datetime
        
        # Extract milliseconds if present
        milliseconds_match = re.search(r'\.(\d+)', time_str)
        milliseconds = milliseconds_match.group(1) if milliseconds_match else None
        
        # Remove milliseconds for parsing
        time_clean = re.sub(r'\.\d+', '', time_str)
        
        # Try different time formats
        for fmt in ["%I:%M:%S %p", "%I:%M %p"]:
            try:
                dt = datetime.strptime(time_clean, fmt)
                result = dt.strftime("%H:%M:%S")
                # Add milliseconds back if they were present
                if milliseconds:
                    result += f".{milliseconds}"
                return result
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
            # Extract milliseconds if present
            milliseconds_match = re.search(r'\.(\d+)', time_str)
            milliseconds = float(f"0.{milliseconds_match.group(1)}") if milliseconds_match else 0.0
            
            # Remove milliseconds for parsing
            time_clean = re.sub(r'\.\d+', '', time_str)
            
            # Parse time
            from datetime import datetime
            
            # Try different time formats
            for fmt in ["%I:%M:%S %p", "%I:%M %p"]:
                try:
                    dt = datetime.strptime(time_clean, fmt)
                    # Add milliseconds as fractional seconds
                    return dt, milliseconds
                except ValueError:
                    continue
            
            raise ValueError(f"Unable to parse time: {time_str}")
        
        start_dt, start_ms = parse_time(start_time)
        end_dt, end_ms = parse_time(end_time)
        
        # Handle day boundary
        if end_dt < start_dt:
            end_dt = end_dt.replace(day=end_dt.day + 1)
        
        # Calculate duration including milliseconds
        duration = (end_dt - start_dt).total_seconds() + (end_ms - start_ms)
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

@app.route('/api/fill-template-gaps', methods=['POST'])
def fill_template_gaps():
    """Fill gaps in a template using the same logic as schedule creation"""
    try:
        data = request.json
        template = data.get('template')
        available_content = data.get('available_content', [])
        gaps = data.get('gaps', [])
        
        # Debug: Log the template items
        logger.info(f"Received template type: {template.get('type')}")
        logger.info(f"Template has {len(template.get('items', []))} items")
        if template.get('items'):
            logger.info("First 3 items for debugging:")
            for i, item in enumerate(template.get('items', [])[:3]):
                logger.info(f"  Item {i}: start_time='{item.get('start_time')}', title='{item.get('title', item.get('file_name'))}'")
        
        if not template or not available_content:
            return jsonify({
                'success': False,
                'message': 'Template and available content are required'
            })
        
        # Determine schedule type
        schedule_type = template.get('type', 'daily')
        
        # Keep a copy of original items with their time ranges for overlap detection
        original_items = []
        
        # For weekly templates with daily-formatted times, we need to understand the intended distribution
        items_with_times = [item for item in template.get('items', []) if 'start_time' in item and item['start_time']]
        
        # Check if this is a weekly template with daily-formatted times
        is_weekly_with_daily_times = (schedule_type == 'weekly' and 
                                     items_with_times and 
                                     all(' ' not in str(item['start_time']) for item in items_with_times))
        
        if is_weekly_with_daily_times:
            logger.warning(f"Weekly template has {len(items_with_times)} items with daily-formatted times. These items will overlap if all placed on same day!")
            # For now, we'll process them as-is, but the gap calculation needs to handle this properly
        
        for idx, item in enumerate(items_with_times):
            # Parse start time to seconds
            start_seconds = 0
            start_time = item['start_time']
            
            if schedule_type == 'weekly' and ' ' in str(start_time):
                # Parse weekly format like "mon 8:00 am"
                parts = start_time.lower().split(' ')
                day_map = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
                day_index = day_map.get(parts[0], 0)
                # Parse time portion
                time_parts = parts[1].split(':')
                hours = int(time_parts[0])
                if len(parts) > 2 and parts[2] == 'pm' and hours != 12:
                    hours += 12
                elif len(parts) > 2 and parts[2] == 'am' and hours == 12:
                    hours = 0
                minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                start_seconds = (day_index * 24 * 3600) + (hours * 3600) + (minutes * 60)
            else:
                # Parse daily format
                time_parts = str(start_time).split(':')
                if len(time_parts) >= 3:
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = float(time_parts[2])
                    start_seconds = (hours * 3600) + (minutes * 60) + seconds
                    
                    # For weekly templates, we need to distribute these across days
                    # This is a temporary fix - ideally the frontend should handle this
                    if is_weekly_with_daily_times:
                        # Simple distribution: spread items across different days
                        # This is just for overlap detection - the frontend will handle actual placement
                        day_offset = (idx % 7) * 24 * 3600
                        start_seconds += day_offset
            
            duration = float(item.get('duration_seconds', 0))
            end_seconds = start_seconds + duration
            
            # Try multiple fields for title
            title = item.get('title') or item.get('content_title') or item.get('file_name') or 'Unknown'
            
            original_items.append({
                'title': title,
                'start': start_seconds,
                'end': end_seconds,
                'start_time': item['start_time'],
                'duration': duration
            })
            
            logger.info(f"Original item {idx}: {title} at '{item['start_time']}' from {start_seconds/3600:.2f}h to {end_seconds/3600:.2f}h")
            logger.info(f"  Duration: {duration}s ({duration/3600:.6f}h), exact end: {end_seconds}s")
        
        logger.info(f"Found {len(original_items)} original items to preserve")
        
        # If gaps are provided, use them. Otherwise calculate total duration
        if gaps:
            logger.info(f"Using {len(gaps)} provided gaps")
            for idx, gap in enumerate(gaps):
                logger.info(f"  Gap {idx + 1}: {gap['start']/3600:.1f}h - {gap['end']/3600:.1f}h (duration: {(gap['end']-gap['start'])/3600:.1f}h)")
            # We'll fill each gap separately
            total_gap_seconds = sum(gap['end'] - gap['start'] for gap in gaps)
            logger.info(f"Total gap time to fill: {total_gap_seconds/3600:.1f} hours")
        else:
            # Calculate total template duration and gaps (old method)
            total_duration = 0
            for item in template.get('items', []):
                total_duration += float(item.get('duration_seconds', 0))
            
            # Target duration based on type
            target_duration = 24 * 3600  # Daily
            if schedule_type == 'weekly':
                target_duration = 7 * 24 * 3600
            elif schedule_type == 'monthly':
                target_duration = 31 * 24 * 3600
            
            gap_seconds = target_duration - total_duration
            
            if gap_seconds <= 0:
                return jsonify({
                    'success': True,
                    'message': 'Template is already full',
                    'items_added': []
                })
            
            # Create a single gap for backward compatibility
            gaps = [{'start': total_duration, 'end': target_duration}]
        
        # Initialize scheduler for rotation logic
        scheduler = scheduler_postgres
        scheduler._reset_rotation()
        
        # Convert available content to the format expected by scheduler
        content_by_id = {}
        for content in available_content:
            content_by_id[content.get('id')] = content
        
        # Debug: Log available content info
        logger.info(f"Available content count: {len(available_content)}")
        if available_content:
            # Check a sample item
            sample = available_content[0]
            logger.info(f"Sample content item keys: {list(sample.keys())}")
            logger.info(f"Sample duration_category: {sample.get('duration_category')}")
            
            # Count items by duration category
            category_counts = {}
            for content in available_content:
                cat = content.get('duration_category', 'none')
                category_counts[cat] = category_counts.get(cat, 0) + 1
            logger.info(f"Content by category: {category_counts}")
        
        # Track what we've scheduled
        scheduled_asset_ids = []  # We'll track this differently now
        items_added = []
        
        # Track when each asset was last scheduled (for replay delays)
        asset_schedule_times = {}  # asset_id -> list of scheduled times in seconds
        
        # For templates, we need to calculate times differently based on type
        for item in template.get('items', []):
            asset_id = item.get('asset_id') or item.get('id') or item.get('content_id')
            if asset_id and 'start_time' in item and item['start_time']:
                # Parse start time to seconds
                start_time = item['start_time']
                time_in_seconds = 0
                
                if schedule_type == 'weekly' and ' ' in str(start_time):
                    # Parse weekly format like "mon 8:00 am"
                    parts = start_time.lower().split(' ')
                    day_map = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
                    day_index = day_map.get(parts[0], 0)
                    # Parse time portion
                    time_parts = parts[1].split(':')
                    hours = int(time_parts[0])
                    if len(parts) > 2 and parts[2] == 'pm' and hours != 12:
                        hours += 12
                    elif len(parts) > 2 and parts[2] == 'am' and hours == 12:
                        hours = 0
                    minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                    time_in_seconds = (day_index * 24 * 3600) + (hours * 3600) + (minutes * 60)
                else:
                    # Parse daily format
                    time_parts = str(start_time).split(':')
                    if len(time_parts) >= 3:
                        hours = int(time_parts[0])
                        minutes = int(time_parts[1])
                        seconds = float(time_parts[2])
                        time_in_seconds = (hours * 3600) + (minutes * 60) + seconds
                
                if asset_id not in asset_schedule_times:
                    asset_schedule_times[asset_id] = []
                asset_schedule_times[asset_id].append(time_in_seconds)
        
        logger.info(f"Assets already scheduled: {len(asset_schedule_times)}")
        
        # Load replay delay configuration
        try:
            from config_manager import ConfigManager
            config_mgr = ConfigManager()
            scheduling_config = config_mgr.get_scheduling_settings()
            replay_delays = scheduling_config.get('replay_delays', {
                'id': 6,
                'spots': 12,
                'short_form': 24,
                'long_form': 48
            })
            logger.info(f"Replay delays: {replay_delays}")
        except Exception as e:
            logger.warning(f"Could not load replay delays, using defaults: {e}")
            replay_delays = {'id': 6, 'spots': 12, 'short_form': 24, 'long_form': 48}
        
        # Fill gaps using rotation logic
        consecutive_errors = 0
        max_errors = 100  # Same as in create schedule
        total_cycles_without_content = 0
        max_cycles = 20  # After trying all categories 20 times, stop
        
        # Process each gap individually
        for gap in gaps:
            gap_start = gap['start']
            gap_end = gap['end']
            gap_duration = gap_end - gap_start
            
            logger.info(f"Filling gap from {gap_start/3600:.1f}h to {gap_end/3600:.1f}h (duration: {gap_duration/3600:.1f}h)")
            logger.info(f"  Exact gap values: start={gap_start}s ({gap_start/3600:.6f}h), end={gap_end}s ({gap_end/3600:.6f}h)")
            
            current_position = gap_start
            
            while current_position < gap_end:
                # Get next duration category from rotation
                duration_category = scheduler._get_next_duration_category()
                
                # Filter available content by category and replay delays
                category_content = []
                wrong_category = 0
                blocked_by_delay = 0
                
                # Get replay delay for this category (in hours)
                replay_delay_hours = replay_delays.get(duration_category, 24)
                replay_delay_seconds = replay_delay_hours * 3600
                
                for content in available_content:
                    # Check duration category
                    if content.get('duration_category') != duration_category:
                        wrong_category += 1
                        continue
                    
                    # Check replay delay
                    content_id = content.get('id')
                    if content_id in asset_schedule_times:
                        # Check if enough time has passed since last scheduling
                        last_times = asset_schedule_times[content_id]
                        can_schedule = True
                        
                        for last_time in last_times:
                            # For templates, current_position represents seconds from start
                            time_since_last = current_position - last_time
                            if time_since_last < replay_delay_seconds:
                                can_schedule = False
                                blocked_by_delay += 1
                                break
                        
                        if not can_schedule:
                            continue
                    
                    category_content.append(content)
            
                if not category_content:
                    logger.info(f"Category {duration_category}: found=0, wrong_category={wrong_category}, blocked_by_delay={blocked_by_delay}, total_available={len(available_content)}")
                
                # If no content due to delays, try without delays
                if not category_content and blocked_by_delay > 0:
                    logger.info(f"Trying category {duration_category} without replay delays")
                    # Try again without checking delays
                    for content in available_content:
                        if content.get('duration_category') == duration_category:
                            category_content.append(content)
                    
                    if category_content:
                        logger.info(f"Found {len(category_content)} items without delay restrictions")
                
                if not category_content:
                    # Try next category if no content available
                    logger.warning(f"No content available for category: {duration_category}")
                    consecutive_errors += 1
                    
                    # Check if we've cycled through all categories multiple times
                    if duration_category == 'id':  # First in rotation
                        total_cycles_without_content += 1
                        if total_cycles_without_content >= max_cycles:
                            logger.error(f"Aborting fill gaps: cycled through all categories {total_cycles_without_content} times without finding content")
                            break
                    
                    # Don't reset rotation - just continue to the next category
                    continue
            
                # Sort by engagement score and shelf life (like scheduler does)
                category_content.sort(key=lambda x: (
                    -(x.get('engagement_score', 50) + 
                      (20 if x.get('shelf_life_score') == 'high' else 10 if x.get('shelf_life_score') == 'medium' else 0))
                ))
                
                # Select the best content
                selected = category_content[0]
                # Check for duration_seconds or file_duration
                duration = float(selected.get('duration_seconds', selected.get('file_duration', 0)))
                consecutive_errors = 0  # Reset consecutive error counter
                total_cycles_without_content = 0  # Reset cycle counter
                
                # Check if it fits in this gap with a safety margin
                remaining = gap_end - current_position
                # Add a safety margin to avoid floating point precision issues and overlaps
                safety_margin = 1.0  # 1 second safety margin
                if duration > remaining - safety_margin:
                    # Try to find shorter content that fits
                    found_fit = False
                    for alt_content in category_content[1:]:
                        alt_duration = float(alt_content.get('duration_seconds', alt_content.get('file_duration', 0)))
                        if alt_duration <= remaining - safety_margin:
                            selected = alt_content
                            duration = alt_duration
                            found_fit = True
                            break
                    
                    if not found_fit:
                        # No content fits in this gap, move to next gap
                        break
            
                # Check for overlap with original items before adding
                new_item_start = current_position
                new_item_end = current_position + duration
                
                # Add small tolerance for floating point comparison
                overlap_tolerance = 0.01  # 10ms tolerance
                
                overlap_found = False
                for orig_item in original_items:
                    # Check if new item would overlap with original item (with tolerance)
                    if (new_item_start < orig_item['end'] - overlap_tolerance and 
                        new_item_end > orig_item['start'] + overlap_tolerance):
                        overlap_found = True
                        logger.error(f"OVERLAP DETECTED! New item '{selected.get('content_title', selected.get('file_name'))}' " +
                                   f"({new_item_start/3600:.2f}h-{new_item_end/3600:.2f}h) would overlap with " +
                                   f"original item '{orig_item['title']}' ({orig_item['start']/3600:.2f}h-{orig_item['end']/3600:.2f}h)")
                        logger.error(f"Gap was supposed to be {gap_start/3600:.2f}h-{gap_end/3600:.2f}h")
                        logger.error(f"Exact values: new_start={new_item_start}s, new_end={new_item_end}s, " +
                                   f"orig_start={orig_item['start']}s, orig_end={orig_item['end']}s")
                        logger.error("ABORTING FILL OPERATION TO PRESERVE ORIGINAL ITEMS")
                        
                        return jsonify({
                            'success': False,
                            'message': f"Overlap detected! Attempted to place content from {new_item_start/3600:.2f}h to {new_item_end/3600:.2f}h " +
                                     f"which overlaps with original item '{orig_item['title']}' at {orig_item['start_time']}. " +
                                     f"Gap calculation may be incorrect.",
                            'overlap_details': {
                                'new_item': {
                                    'title': selected.get('content_title', selected.get('file_name')),
                                    'start_hours': new_item_start/3600,
                                    'end_hours': new_item_end/3600
                                },
                                'original_item': {
                                    'title': orig_item['title'],
                                    'start_hours': orig_item['start']/3600,
                                    'end_hours': orig_item['end']/3600,
                                    'start_time': orig_item['start_time']
                                },
                                'gap': {
                                    'start_hours': gap_start/3600,
                                    'end_hours': gap_end/3600
                                }
                            }
                        })
                
                if not overlap_found:
                    # Add to template
                    new_item = {
                        'asset_id': selected.get('id'),
                        'content_id': selected.get('id'),
                        'title': selected.get('content_title', selected.get('file_name')),
                        'file_name': selected.get('file_name'),
                        'file_path': selected.get('file_path'),
                        'duration_seconds': duration,
                        'duration_category': selected.get('duration_category'),
                        'content_type': selected.get('content_type'),
                        'guid': selected.get('guid', '')
                        # Don't set start_time and end_time - let frontend calculate them
                    }
                    
                    items_added.append(new_item)
                    # Track when this asset was scheduled for replay delay checking
                    content_id = selected.get('id')
                    if content_id not in asset_schedule_times:
                        asset_schedule_times[content_id] = []
                    asset_schedule_times[content_id].append(current_position)
                    
                    current_position += duration
                
                # Log progress every 10 items to prevent timeout appearance
                if len(items_added) % 10 == 0:
                    logger.info(f"Fill gaps progress: {len(items_added)} items added, current gap: {current_position/3600:.1f}h of {gap_end/3600:.1f}h")
        
        # Calculate total filled duration
        total_filled_seconds = sum(item['duration_seconds'] for item in items_added)
        logger.info(f"Fill gaps completed: {len(items_added)} total items added, {total_filled_seconds/3600:.1f} hours total")
        
        # FINAL VERIFICATION: Check that all original items would still be preserved
        logger.info("=== FINAL VERIFICATION: Checking if all original items are preserved ===")
        
        # Create a combined schedule with original items and new items
        all_items = []
        
        # Add original items with their times
        for orig in original_items:
            all_items.append({
                'start': orig['start'],
                'end': orig['end'],
                'title': orig['title'],
                'is_original': True
            })
        
        # Add new items - we need to track where they were placed
        # The frontend will assign actual positions, but for verification
        # we'll simulate the placement in gaps
        item_idx = 0
        for gap in gaps:
            gap_start = gap['start']
            gap_end = gap['end']
            current_pos = gap_start
            
            # Place items in this gap
            while item_idx < len(items_added) and current_pos < gap_end:
                item = items_added[item_idx]
                item_duration = item['duration_seconds']
                
                # Check if item fits in remaining gap
                if current_pos + item_duration <= gap_end:
                    all_items.append({
                        'start': current_pos,
                        'end': current_pos + item_duration,
                        'title': item.get('title', item.get('content_title', item.get('file_name', 'Unknown'))),
                        'is_original': False
                    })
                    current_pos += item_duration
                    item_idx += 1
                else:
                    # Item doesn't fit in this gap, move to next gap
                    break
        
        # Sort all items by start time
        all_items.sort(key=lambda x: x['start'])
        
        # Check for any overlaps
        overlaps_found = []
        for i in range(len(all_items)):
            for j in range(i + 1, len(all_items)):
                item1 = all_items[i]
                item2 = all_items[j]
                
                # Check if items overlap
                if item1['end'] > item2['start'] and item1['start'] < item2['end']:
                    if item1['is_original'] or item2['is_original']:
                        orig_item = item1 if item1['is_original'] else item2
                        new_item = item2 if item1['is_original'] else item1
                        
                        overlap_info = f"Original '{orig_item['title']}' ({orig_item['start']/3600:.1f}h-{orig_item['end']/3600:.1f}h) " + \
                                     f"overlaps with new '{new_item['title']}' ({new_item['start']/3600:.1f}h-{new_item['end']/3600:.1f}h)"
                        overlaps_found.append(overlap_info)
                        logger.error(f"VERIFICATION FAILED: {overlap_info}")
        
        # Check if all original items are still present
        originals_preserved = True
        for orig in original_items:
            found = False
            for item in all_items:
                if item['is_original'] and abs(item['start'] - orig['start']) < 1 and abs(item['end'] - orig['end']) < 1:
                    found = True
                    break
            
            if not found:
                logger.error(f"VERIFICATION FAILED: Original item '{orig['title']}' at {orig['start_time']} is missing!")
                originals_preserved = False
        
        if overlaps_found:
            logger.error(f"VERIFICATION FAILED: Found {len(overlaps_found)} overlaps with original items!")
            return jsonify({
                'success': False,
                'message': f'Final verification failed: {len(overlaps_found)} overlaps detected with original items',
                'verification_errors': overlaps_found,
                'items_added': items_added,
                'total_added': len(items_added)
            })
        
        if not originals_preserved:
            return jsonify({
                'success': False,
                'message': 'Final verification failed: Some original items were not preserved',
                'items_added': items_added,
                'total_added': len(items_added)
            })
        
        logger.info("VERIFICATION PASSED: All original items preserved, no overlaps detected")
        
        return jsonify({
            'success': True,
            'items_added': items_added,
            'total_added': len(items_added),
            'new_duration': total_filled_seconds,
            'verification': 'passed'
        })
        
    except Exception as e:
        logger.error(f"Fill template gaps error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e)
        })

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
        # Determine format type based on template type
        format_type = 'weekly' if template.get('type') == 'weekly' else 'daily'
        
        # Calculate start/end times for items
        current_time = datetime.strptime("00:00:00", "%H:%M:%S")
        
        # For weekly templates, we need to ensure all times have proper day prefixes
        if format_type == 'weekly':
            # Track the current day and time position
            current_seconds = 0.0
            
            for idx, item in enumerate(template['items']):
                # Get the start time
                start_time = item.get('start_time', '')
                
                # Check if start_time already has a day prefix
                has_day_prefix = False
                if ' ' in start_time and any(day in start_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                    has_day_prefix = True
                    item['scheduled_start_time'] = start_time
                    
                    # Parse the day and time to update current position
                    parts = start_time.split(' ', 1)
                    day_name = parts[0].lower()
                    day_map = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
                    day_index = day_map.get(day_name, 0)
                    
                    # Parse time component
                    time_part = parts[1] if len(parts) > 1 else '12:00:00 am'
                    if 'am' in time_part.lower() or 'pm' in time_part.lower():
                        time_24 = convert_to_24hour_format(time_part)
                    else:
                        time_24 = time_part
                    time_parts = time_24.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                    seconds = float(time_parts[2]) if len(time_parts) > 2 else 0
                    
                    current_seconds = (day_index * 24 * 3600) + (hours * 3600) + (minutes * 60) + seconds
                else:
                    # No day prefix - we need to calculate it based on position
                    # Determine which day this item falls on
                    day_index = int(current_seconds // (24 * 3600))
                    day_names = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
                    day_name = day_names[day_index % 7]
                    
                    # Parse the time component
                    if 'am' in start_time.lower() or 'pm' in start_time.lower():
                        # Convert AM/PM to 24-hour first
                        time_24 = convert_to_24hour_format(start_time)
                    else:
                        time_24 = start_time
                    
                    # Add the day prefix
                    if 'am' in start_time.lower() or 'pm' in start_time.lower():
                        # Keep the original AM/PM format
                        item['scheduled_start_time'] = f"{day_name} {start_time}"
                    else:
                        # Convert to AM/PM format for consistency
                        time_parts = time_24.split(':')
                        if time_parts:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                            seconds = float(time_parts[2]) if len(time_parts) > 2 else 0
                            
                            # Format as 12-hour time
                            period = 'am' if hours < 12 else 'pm'
                            display_hours = hours
                            if hours == 0:
                                display_hours = 12
                            elif hours > 12:
                                display_hours = hours - 12
                            
                            time_str = f"{display_hours}:{minutes:02d}:{int(seconds):02d}"
                            if seconds % 1 > 0:
                                milliseconds = int((seconds % 1) * 1000)
                                time_str += f".{milliseconds:03d}"
                            time_str += f" {period}"
                            
                            item['scheduled_start_time'] = f"{day_name} {time_str}"
                
                # Handle end_time similarly if provided
                if 'end_time' in item:
                    end_time = item['end_time']
                    if ' ' in end_time and any(day in end_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                        item['scheduled_end_time'] = end_time
                    else:
                        # Calculate which day the end time falls on
                        duration = float(item.get('duration_seconds', 0))
                        end_seconds = current_seconds + duration
                        end_day_index = int(end_seconds // (24 * 3600))
                        day_names = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
                        end_day_name = day_names[end_day_index % 7]
                        
                        # Add day prefix to end time
                        if 'am' in end_time.lower() or 'pm' in end_time.lower():
                            item['scheduled_end_time'] = f"{end_day_name} {end_time}"
                        else:
                            # Format end time with AM/PM
                            item['scheduled_end_time'] = f"{end_day_name} {end_time}"
                
                # Update current position for next item
                duration = float(item.get('duration_seconds', 0))
                current_seconds += duration
                
                # Also set scheduled_duration_seconds
                item['scheduled_duration_seconds'] = duration
        else:
            # Daily templates - simpler handling
            for item in template['items']:
                if 'start_time' in item:
                    item['scheduled_start_time'] = item['start_time']
                    if 'end_time' in item:
                        item['scheduled_end_time'] = item['end_time']
                else:
                    item['scheduled_start_time'] = current_time.strftime("%H:%M:%S")
            
            # Also set scheduled_duration_seconds for consistency with schedule export
            item['scheduled_duration_seconds'] = float(item.get('duration_seconds', 0))
            
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
        schedule_content = generate_castus_schedule(mock_schedule, template['items'], mock_schedule['air_date'], format_type)
        
        # Check if generate_castus_schedule returned an error (overlap detected)
        if schedule_content.startswith("ERROR:"):
            return jsonify({
                'success': False,
                'message': schedule_content
            })
        
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