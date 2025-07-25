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
from scheduler import scheduler
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
        
        # Create schedule using PostgreSQL scheduler
        result = scheduler_postgres.create_daily_schedule(schedule_date, schedule_name)
        
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
        
        logger.info(f"Creating weekly schedule starting: {start_date}")
        
        if not start_date:
            return jsonify({
                'success': False,
                'message': 'Start date is required'
            })
        
        # Create weekly schedule using PostgreSQL scheduler
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
        
        # Generate Castus format schedule
        if format_type == 'castus':
            # Determine if it's a daily or weekly schedule
            schedule_content = generate_castus_schedule(schedule, items, date)
            
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

def generate_castus_schedule(schedule, items, date):
    """Generate schedule content in Castus format"""
    # For now, always generate daily format
    # Weekly format will be handled separately later
    
    # Start with header for daily schedule
    lines = []
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
        start_time = item['scheduled_start_time']
        duration_seconds = float(item['scheduled_duration_seconds'])
        
        # Calculate end time
        start_dt = datetime.strptime(f"2000-01-01 {start_time}", "%Y-%m-%d %H:%M:%S")
        end_dt = start_dt + timedelta(seconds=duration_seconds)
        
        # Format times with milliseconds for daily schedule
        # Extract milliseconds from duration
        whole_seconds = int(duration_seconds)
        milliseconds = int((duration_seconds - whole_seconds) * 1000)
        
        # Special handling for first item - should start at exactly 12:00 am
        if idx == 0 and start_dt.hour == 0 and start_dt.minute == 0:
            start_time_formatted = "12:00 am"
        else:
            # For other start times, add .000 if no milliseconds
            start_time_formatted = start_dt.strftime("%I:%M:%S").lstrip("0") + ".000 " + start_dt.strftime("%p").lower()
        
        # For end time, include the actual milliseconds
        end_time_formatted = end_dt.strftime("%I:%M:%S").lstrip("0") + f".{milliseconds:03d} " + end_dt.strftime("%p").lower()
        
        # Add FTP path prefix if not already present
        file_path = item['file_path']
        if not file_path.startswith('/mnt/main/ATL26 On-Air Content/'):
            # Preserve subdirectory structure
            # Remove common prefixes like /media/videos/ but keep the subdirectory structure
            path_parts = file_path.split('/')
            
            # Find where the content starts (after common prefixes)
            content_start_idx = 0
            for i, part in enumerate(path_parts):
                if part in ['media', 'videos', 'content', 'files']:
                    content_start_idx = i + 1
                    break
            
            # Get the relative path from content start
            if content_start_idx > 0 and content_start_idx < len(path_parts):
                relative_path = '/'.join(path_parts[content_start_idx:])
            else:
                # If no common prefix found, just use the filename
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

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'FTP Sync Backend is running'})

if __name__ == '__main__':
    print("Starting FTP Sync Backend with DEBUG logging...")
    print("Backend will be available at: http://127.0.0.1:5000")
    print("Watch this terminal for detailed connection logs...")
    app.run(debug=True, host='127.0.0.1', port=5000)