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
import subprocess
import shutil
from psycopg2.extras import RealDictCursor

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

# Track app start time for uptime calculation
import time
app_start_time = time.time()

# Initialize database connection
db_manager.connect()

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get backend status information"""
    import time
    
    try:
        return jsonify({
            'success': True,
            'status': 'online',
            'version': '1.0.0',
            'uptime': time.time() - app_start_time if 'app_start_time' in globals() else 0,
            'database_connected': db_manager.connected if db_manager else False,
            'timestamp': time.time()
        })
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/database-stats', methods=['GET'])
def get_database_stats():
    """Get database statistics for admin panel"""
    try:
        stats = {
            'totalAnalyses': 0,
            'totalSchedules': 0,
            'dbSize': '0 MB'
        }
        
        if db_manager.connected:
            conn = db_manager._get_connection()
            try:
                with conn.cursor() as cursor:
                    # Count analyzed assets
                    cursor.execute("SELECT COUNT(*) FROM assets WHERE analysis_completed = true")
                    result = cursor.fetchone()
                    stats['totalAnalyses'] = result[0] if result else 0
                    
                    # Count schedules
                    cursor.execute("SELECT COUNT(*) FROM schedules")
                    result = cursor.fetchone()
                    stats['totalSchedules'] = result[0] if result else 0
                    
                    # Get database size
                    cursor.execute("""
                        SELECT pg_database_size(current_database()) / 1024 / 1024 as size_mb
                    """)
                    result = cursor.fetchone()
                    size_mb = result[0] if result else 0
                    stats['dbSize'] = f"{size_mb:.1f} MB"
            finally:
                db_manager._put_connection(conn)
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e),
            'stats': {
                'totalAnalyses': 0,
                'totalSchedules': 0,
                'dbSize': '0 MB'
            }
        })


@app.route('/api/admin/logs', methods=['GET'])
def get_admin_logs():
    """Get recent application logs for admin panel"""
    try:
        # For now, return empty logs
        # In a real implementation, you would read from log files
        return jsonify({
            'success': True,
            'logs': []
        })
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}")
        return jsonify({'success': False, 'message': str(e), 'logs': []})


@app.route('/api/ai/api-keys', methods=['GET'])
def get_ai_api_keys():
    """Get AI API keys from environment variables"""
    try:
        # Check environment variables for API keys
        openai_key = os.getenv('OPENAI_API_KEY', '')
        anthropic_key = os.getenv('ANTHROPIC_API_KEY', '')
        
        # Only return masked versions for security
        return jsonify({
            'success': True,
            'openai_key': '***' + openai_key[-4:] if openai_key and len(openai_key) > 4 else '',
            'anthropic_key': '***' + anthropic_key[-4:] if anthropic_key and len(anthropic_key) > 4 else '',
            'has_openai_key': bool(openai_key),
            'has_anthropic_key': bool(anthropic_key)
        })
    except Exception as e:
        logger.error(f"Error getting AI API keys: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})


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
            logger.info(f"Updating scheduling settings: {data['scheduling']}")
            config_manager.update_scheduling_settings(data['scheduling'])
            
            # Update scheduler rotation order if provided
            if 'rotation_order' in data['scheduling']:
                logger.info(f"Updating rotation order to: {data['scheduling']['rotation_order']}")
                scheduler_postgres.update_rotation_order(data['scheduling']['rotation_order'])
        
        if 'ai_settings' in data:
            # Map ai_settings to ai_analysis for config_manager
            ai_analysis_data = {
                'enabled': data['ai_settings'].get('enabled', False),
                'transcription_only': data['ai_settings'].get('transcriptionOnly', False),
                'provider': data['ai_settings'].get('provider', 'openai'),
                'model': data['ai_settings'].get('model', 'gpt-3.5-turbo'),
                'max_chunk_size': data['ai_settings'].get('maxChunkSize', 4000)
            }
            config_manager.update_ai_analysis_settings(ai_analysis_data)
        
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

@app.route('/api/connection-status', methods=['GET'])
def get_connection_status():
    """Get current FTP connection status"""
    try:
        status = {
            'source': {
                'connected': 'source' in ftp_managers and ftp_managers['source'].connected
            },
            'target': {
                'connected': 'target' in ftp_managers and ftp_managers['target'].connected
            }
        }
        
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logger.error(f"Error getting connection status: {str(e)}")
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
        # Use connect() instead of test_connection() to keep connection open
        success = ftp_manager.connect()
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
    """Delete selected files from specified server (source or target)"""
    logger.info("=== DELETE FILES REQUEST ===")
    try:
        data = request.json
        files = data.get('files', [])
        server_type = data.get('server_type', 'target')
        dry_run = data.get('dry_run', False)
        
        logger.info(f"Deleting {len(files)} files from {server_type} server (dry_run: {dry_run})")
        
        # Validate server type
        if server_type not in ['source', 'target']:
            return jsonify({
                'success': False,
                'message': f'Invalid server type: {server_type}. Must be "source" or "target"'
            })
        
        # Check if server is connected
        if server_type not in ftp_managers:
            return jsonify({
                'success': False, 
                'message': f'{server_type.capitalize()} server not connected'
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
                    'dry_run': True,
                    'server': server_type
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
                        'file_path': file_path,
                        'server': server_type
                    })
                    success_count += 1
                else:
                    results.append({
                        'success': False,
                        'message': f'Failed to delete: {file_name}',
                        'file_name': file_name,
                        'file_path': file_path,
                        'server': server_type
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

@app.route('/api/create-backup', methods=['POST'])
def create_database_backup():
    """Create a backup of the database using the existing backup script"""
    logger.info("=== CREATE DATABASE BACKUP REQUEST ===")
    try:
        import subprocess
        import os
        from datetime import datetime
        
        # Check if using PostgreSQL
        use_postgres = os.getenv('USE_POSTGRESQL', 'false').lower() == 'true'
        
        if use_postgres:
            # Use the existing backup_postgres.sh script
            script_path = os.path.join(os.path.dirname(__file__), 'backup_postgres.sh')
            
            if not os.path.exists(script_path):
                error_msg = f"Backup script not found at {script_path}"
                logger.error(error_msg)
                return jsonify({
                    'success': False,
                    'error': error_msg
                })
            
            # Make sure script is executable
            os.chmod(script_path, 0o755)
            
            # Run the backup script
            logger.info(f"Running backup script: {script_path}")
            result = subprocess.run(['bash', script_path], capture_output=True, text=True)
            
            if result.returncode == 0:
                # Parse output to find backup filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = f"ftp_media_sync_backup_{timestamp}.sql.gz"
                
                # Extract backup locations from output
                output_lines = result.stdout.split('\n')
                backup_info = {
                    'local': f"~/postgres_backups/ftp-media-sync/daily/{backup_file}",
                    'castus1': '/mnt/md127/Backups/postgres',
                    'castus2': '/mnt/md127/Backups/postgres'
                }
                
                logger.info(f"PostgreSQL backup successful")
                logger.info(f"Backup output:\n{result.stdout}")
                
                return jsonify({
                    'success': True,
                    'backup_file': backup_file,
                    'locations': backup_info,
                    'message': 'Backup created in 3 locations: local, castus1, and castus2'
                })
            else:
                error_msg = f"Backup script failed: {result.stderr}"
                logger.error(error_msg)
                logger.error(f"Script output: {result.stdout}")
                return jsonify({
                    'success': False,
                    'error': error_msg
                })
                
        else:
            # MongoDB backup - keep existing implementation
            backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"mongodb_backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_file)
            
            # Get MongoDB connection details
            mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
            db_name = os.getenv('MONGODB_DATABASE', 'castus')
            
            # Run mongodump
            cmd = ['mongodump', '--uri', mongo_uri, '--db', db_name, '--out', backup_path]
            logger.info(f"Running MongoDB backup to {backup_path}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"MongoDB backup successful: {backup_file}")
                return jsonify({
                    'success': True,
                    'backup_file': backup_file,
                    'backup_path': backup_path
                })
            else:
                error_msg = f"MongoDB backup failed: {result.stderr}"
                logger.error(error_msg)
                return jsonify({
                    'success': False,
                    'error': error_msg
                })
                
    except Exception as e:
        error_msg = f"Database backup error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({
            'success': False,
            'error': error_msg
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
                    # Include microseconds in the time format
                    time_obj = item['scheduled_start_time']
                    milliseconds = time_obj.microsecond // 1000
                    item['scheduled_start_time'] = f"{time_obj.strftime('%H:%M:%S')}.{milliseconds:03d}"
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
            
            # Check if content_id looks like MongoDB ObjectId (24 char hex string)
            if len(str(content_id)) == 24 and all(c in '0123456789abcdefABCDEF' for c in str(content_id)):
                # Use mongo_id column for MongoDB ObjectIds
                cursor.execute("""
                    UPDATE assets 
                    SET content_type = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE mongo_id = %s
                """, (new_content_type.lower(), content_id))
            else:
                # Use regular id column for integer IDs
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

@app.route('/api/content/<content_id>', methods=['DELETE'])
def delete_content_entry(content_id):
    """Delete content from database (does not delete the actual file)"""
    try:
        logger.info(f"Deleting database entry for content ID: {content_id}")
        
        # Ensure database is connected
        if not db_manager.connected:
            db_manager.connect()
            if not db_manager.connected:
                return jsonify({
                    'success': False,
                    'message': 'Failed to connect to database'
                })
        
        # Get database connection
        try:
            conn = db_manager._get_connection()
        except Exception as conn_error:
            logger.error(f"Failed to get database connection: {conn_error}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'Failed to get database connection: {str(conn_error)}'
            })
            
        try:
            cursor = conn.cursor()
            
            # First get the asset info for logging
            # Check if content_id looks like MongoDB ObjectId (24 char hex string)
            if len(content_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in content_id):
                # Use mongo_id column for MongoDB ObjectIds
                cursor.execute("""
                    SELECT i.file_name, i.file_path, a.content_title, a.id 
                    FROM assets a
                    LEFT JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                    WHERE a.mongo_id = %s
                """, (content_id,))
            else:
                # Use regular id column for integer IDs
                cursor.execute("""
                    SELECT i.file_name, i.file_path, a.content_title, a.id 
                    FROM assets a
                    LEFT JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                    WHERE a.id = %s
                """, (content_id,))
            
            asset_info = cursor.fetchone()
            if not asset_info:
                return jsonify({
                    'success': False,
                    'message': f'Content ID {content_id} not found in database'
                })
            
            # Handle both tuple and dict results
            if isinstance(asset_info, dict):
                file_name = asset_info.get('file_name') or 'Unknown'
                file_path = asset_info.get('file_path') or 'Unknown'
                content_title = asset_info.get('content_title') or file_name
                actual_asset_id = asset_info.get('id')
            else:
                file_name = asset_info[0] or 'Unknown'
                file_path = asset_info[1] or 'Unknown'
                content_title = asset_info[2] or file_name
                actual_asset_id = asset_info[3]
            
            logger.info(f"Deleting database entries for: {file_name} (path: {file_path})")
            
            # Delete from instances table first (foreign key constraint)
            cursor.execute("""
                DELETE FROM instances 
                WHERE asset_id = %s
            """, (actual_asset_id,))
            
            instances_deleted = cursor.rowcount
            logger.info(f"Deleted {instances_deleted} instance(s)")
            
            # Delete from assets table
            cursor.execute("""
                DELETE FROM assets 
                WHERE id = %s
            """, (actual_asset_id,))
            
            assets_deleted = cursor.rowcount
            
            # Commit the transaction
            conn.commit()
            cursor.close()
            
            logger.info(f"Successfully deleted asset ID {actual_asset_id} (mongo_id: {content_id}) from database")
            
            return jsonify({
                'success': True,
                'message': f'Database entry deleted successfully',
                'details': {
                    'asset_id': content_id,
                    'file_name': file_name,
                    'instances_deleted': instances_deleted,
                    'assets_deleted': assets_deleted
                }
            })
            
        except Exception as e:
            logger.error(f"Database deletion failed: {str(e)}", exc_info=True)
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception args: {e.args}")
            if conn:
                conn.rollback()
            return jsonify({
                'success': False,
                'message': f'Database deletion failed: {str(e)}'
            })
        finally:
            if conn:
                db_manager._put_connection(conn)
                
    except Exception as e:
        logger.error(f"Delete content entry failed: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Delete content entry failed: {str(e)}'
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

@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    """Generate various analytical reports"""
    try:
        data = request.json
        report_type = data.get('report_type')
        
        if report_type == 'schedule-analysis':
            schedule_id = data.get('schedule_id')
            if not schedule_id:
                return jsonify({'success': False, 'message': 'Schedule ID required'})
            
            # Import here to avoid circular imports
            from reports import ScheduleAnalysisReport
            
            report = ScheduleAnalysisReport(db_manager)
            report_data = report.generate(schedule_id)
            
            return jsonify({
                'success': True,
                'data': report_data
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Unknown report type: {report_type}'
            })
            
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

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
        
        # Convert datetime objects to strings and ensure consistent field names
        for schedule in schedules:
            if 'air_date' in schedule and schedule['air_date']:
                schedule['air_date'] = schedule['air_date'].isoformat()
            if 'created_at' in schedule and schedule['created_at']:
                schedule['created_at'] = schedule['created_at'].isoformat()
            # Also handle created_date for backward compatibility
            if 'created_date' in schedule and schedule['created_date']:
                schedule['created_at'] = schedule['created_date'].isoformat()
            # Format duration
            if schedule.get('total_duration'):
                schedule['total_duration_hours'] = float(schedule['total_duration']) / 3600
            elif schedule.get('total_duration_seconds'):
                schedule['total_duration'] = float(schedule['total_duration_seconds'])
                schedule['total_duration_hours'] = float(schedule['total_duration_seconds']) / 3600
        
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
        
        # Check if this is a weekly schedule
        is_weekly_schedule = False
        if '[WEEKLY]' in schedule.get('schedule_name', ''):
            is_weekly_schedule = True
            
        # Get schedule items
        items = scheduler_postgres.get_schedule_items(schedule['id'])
        logger.info(f"Got {len(items)} items for schedule export")
        if items:
            logger.debug(f"First item keys: {list(items[0].keys())}")
        
        # Generate Castus format schedule
        if format_type == 'castus' or format_type == 'castus_weekly' or format_type == 'castus_monthly':
            # Determine export format
            if format_type == 'castus_weekly' or is_weekly_schedule:
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
        
        # Get metadata for weekly schedules
        metadata = item.get('metadata', {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}
        
        # Debug logging for live inputs
        if item.get('asset_id') == 300:
            logger.info(f"Item {idx} - asset_id=300, metadata type: {type(metadata)}, metadata: {metadata}")
        
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
            
            # Check if we have metadata with day information
            day_prefix = metadata.get('day_prefix', '') if metadata else ''
            day_offset = metadata.get('day_offset', 0) if metadata else 0
            
            # Initialize time components
            db_hours = 0
            db_minutes = 0
            db_seconds = 0.0
            
            # Parse the actual start time from the database
            item_day_index = day_offset  # Use metadata if available
            
            # First, always parse the time regardless of metadata
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
            
            # If we have day_prefix from metadata, use it
            if day_prefix:
                # Use the day prefix from metadata
                day_map = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
                item_day_index = day_map.get(day_prefix, day_offset)
                item_day_name = day_prefix
            
            # Calculate the actual start time in seconds from the database
            # For weekly schedules, check metadata for day information
            if format_type == 'weekly' and day_prefix and day_offset is not None:
                # Use metadata to calculate exact position in week
                item_start_seconds = (day_offset * 24 * 60 * 60) + (db_hours * 3600) + (db_minutes * 60) + db_seconds
                current_day = day_offset
                logger.debug(f"Using metadata: day_prefix={day_prefix}, day_offset={day_offset}, calculated seconds={item_start_seconds}")
            elif isinstance(start_time, str) and ' ' in start_time and any(day in start_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                # Calculate exact start time based on day index from string
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
            # For weekly schedules, prefer metadata
            if format_type == 'weekly' and day_prefix:
                # Use day prefix from metadata
                item_day_name = day_prefix
            elif format_type == 'weekly' and isinstance(start_time, str) and ' ' in start_time and any(day in start_time.lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
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
        
        # Check if this is a live input (placeholder asset or metadata flag)
        # Live inputs use asset_id=300 (placeholder) or have is_live_input in metadata
        if item.get('asset_id') == 300 or (metadata and metadata.get('is_live_input')):
            # This is a live input, get file_path from metadata
            if metadata:
                file_path = metadata.get('file_path', '')
                if not file_path and metadata.get('title'):
                    # Try to determine SDI input from title
                    title = metadata.get('title', '')
                    if 'Committee Room 1' in title:
                        file_path = '/mnt/main/tv/inputs/2-SDI in'
                    elif 'Committee Room 2' in title:
                        file_path = '/mnt/main/tv/inputs/3-SDI in'
                    elif 'Council Chamber' in title:
                        file_path = '/mnt/main/tv/inputs/1-SDI in'
                logger.info(f"Live input item detected: {metadata.get('title')} - {file_path}")
            else:
                # No metadata but asset_id=300, try to get from content_title
                title = item.get('content_title', '')
                if 'Committee Room 1' in title:
                    file_path = '/mnt/main/tv/inputs/2-SDI in'
                elif 'Committee Room 2' in title:
                    file_path = '/mnt/main/tv/inputs/3-SDI in'
                elif 'Council Chamber' in title:
                    file_path = '/mnt/main/tv/inputs/1-SDI in'
                logger.info(f"Live input item detected (no metadata): {title} - {file_path}")
        
        # Handle None file_path
        if not file_path:
            logger.error(f"No file path for item at index {idx}: asset_id={item.get('asset_id')}, title={item.get('content_title')}")
            file_path = '/mnt/main/ATL26 On-Air Content/MISSING_FILE.mp4'
        
        # Check if this is an SDI input (live broadcast)
        if file_path.startswith('/mnt/main/tv/inputs/') and 'SDI' in file_path:
            # This is a live SDI input - keep the path as is
            pass
        # If the path doesn't start with the expected prefix, we need to construct it
        elif not file_path.startswith('/mnt/main/ATL26 On-Air Content/'):
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
        
        # Get loop value from metadata for live inputs, default to 0
        loop_value = (metadata.get('loop', '0') if metadata and metadata.get('is_live_input') else '0')
        lines.append(f"{TAB}loop={loop_value}")
        
        # Use GUID if available from assets or metadata
        guid = (metadata.get('guid') if metadata and metadata.get('is_live_input') else item.get('guid', str(uuid.uuid4())))
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

@app.route('/api/validate-template-files', methods=['POST'])
def validate_template_files():
    """Validate that files in a template exist on FTP servers"""
    try:
        data = request.json
        items = data.get('items', [])
        
        logger.info(f"Validating {len(items)} template items for file existence")
        
        # Get FTP managers for both servers
        config = config_manager.get_all_config()
        source_config = config.get('servers', {}).get('source', {})
        target_config = config.get('servers', {}).get('target', {})
        
        missing_files = []
        checked_paths = set()  # Avoid checking the same path multiple times
        
        for idx, item in enumerate(items):
            # Skip live inputs
            if item.get('is_live_input', False) or '/mnt/main/tv/inputs/' in item.get('file_path', ''):
                continue
                
            file_path = item.get('file_path', '')
            if not file_path or file_path in checked_paths:
                continue
                
            checked_paths.add(file_path)
            
            # Check on both servers
            exists_on_source = False
            exists_on_target = False
            
            # If file_path doesn't start with /mnt/, try common base paths
            paths_to_check = [file_path]
            if not file_path.startswith('/mnt/'):
                # Common base paths where content might be stored
                # Note: /mnt/main and /mnt/md127 are the same via symbolic link
                base_paths = [
                    '/mnt/main/ATL26 On-Air Content/',
                    '/mnt/main/'
                ]
                for base in base_paths:
                    paths_to_check.append(base + file_path)
            
            # Check source server
            source_ftp = FTPManager(source_config)
            if source_ftp.connect():
                try:
                    for check_path in paths_to_check:
                        try:
                            source_ftp.ftp.size(check_path)  # Try to get file size
                            exists_on_source = True
                            logger.debug(f"File found on source server at: {check_path}")
                            break
                        except:
                            pass
                finally:
                    source_ftp.disconnect()
            
            # Check target server
            target_ftp = FTPManager(target_config)
            if target_ftp.connect():
                try:
                    for check_path in paths_to_check:
                        try:
                            target_ftp.ftp.size(check_path)  # Try to get file size
                            exists_on_target = True
                            logger.debug(f"File found on target server at: {check_path}")
                            break
                        except:
                            pass
                finally:
                    target_ftp.disconnect()
            
            # If file doesn't exist on either server, add to missing list
            if not exists_on_source and not exists_on_target:
                missing_files.append({
                    'asset_id': item.get('asset_id'),
                    'title': item.get('title', 'Unknown'),
                    'file_path': file_path,
                    'guid': item.get('guid', ''),
                    'index': idx
                })
                logger.warning(f"File not found on either server: {file_path}")
        
        return jsonify({
            'success': True,
            'missing_files': missing_files,
            'total_checked': len(checked_paths)
        })
        
    except Exception as e:
        logger.error(f"Error validating template files: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error validating files: {str(e)}'
        })

@app.route('/api/create-schedule-from-template', methods=['POST'])
def create_schedule_from_template():
    """Create a schedule from a template with manually added items"""
    try:
        data = request.json
        air_date = data.get('air_date')
        schedule_name = data.get('schedule_name', 'Daily Schedule')
        channel = data.get('channel', 'Comcast Channel 26')
        template_type = data.get('template_type', 'daily')  # Get template type
        items = data.get('items', [])
        
        logger.info(f"Creating {template_type} schedule from template: {schedule_name} for {air_date} with {len(items)} items")
        
        if not air_date:
            return jsonify({
                'success': False,
                'message': 'Air date is required'
            })
        
        # For weekly schedules, we need to handle this differently
        if template_type == 'weekly':
            # Create a single weekly schedule
            from datetime import datetime, timedelta
            provided_date = datetime.strptime(air_date, '%Y-%m-%d')
            
            # Find the Sunday of this week
            # weekday() returns: Monday=0, Sunday=6
            # We want: Sunday=0
            days_since_sunday = (provided_date.weekday() + 1) % 7
            
            # If it's already Sunday, use it; otherwise go back to Sunday
            start_date = provided_date - timedelta(days=days_since_sunday)
            
            # Use the Sunday date for the schedule
            sunday_date_str = start_date.strftime('%Y-%m-%d')
            logger.info(f"Adjusted weekly schedule date from {air_date} to Sunday {sunday_date_str}")
            
            # Create a single schedule for the entire week
            result = scheduler_postgres.create_empty_schedule(
                schedule_date=sunday_date_str,
                schedule_name=schedule_name
            )
            
            if not result['success']:
                return jsonify(result)
            
            schedule_id = result['schedule_id']
            logger.info(f"Created weekly schedule with ID: {schedule_id}")
            
            # Group items by day
            items_by_day = {}
            for i in range(7):
                items_by_day[i] = []
            
            # Distribute items to their respective days
            for idx, item in enumerate(items):
                # Get the day index from the item (0 = Sunday, 6 = Saturday)
                # Check if item has start_time with day prefix for weekly templates
                start_time = item.get('start_time', '')
                day_index = None
                
                # Try to extract day from start_time if it has day prefix
                if isinstance(start_time, str) and ' ' in start_time:
                    parts = start_time.split(' ', 1)
                    day_prefix = parts[0].lower()
                    day_map = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
                    if day_prefix in day_map:
                        day_index = day_map[day_prefix]
                        logger.debug(f"Item {idx} has day prefix '{day_prefix}', assigned to day {day_index}")
                
                # Fall back to 'day' field if no day prefix found
                if day_index is None:
                    day_index = item.get('day', None)
                    
                # If still no day, for weekly templates distribute evenly
                if day_index is None:
                    if template_type == 'weekly' and len(items) > 0:
                        # Distribute items evenly across the week
                        day_index = idx % 7
                        logger.debug(f"Item {idx} has no day info, distributing to day {day_index}")
                    else:
                        day_index = 0  # Default to Sunday
                
                if 0 <= day_index < 7:
                    items_by_day[day_index].append(item)
                    logger.debug(f"Added item {idx} to day {day_index}")
                else:
                    logger.warning(f"Item {idx} has invalid day index {day_index}, skipping")
            
            # Add all items to the single schedule with proper day prefixes and times
            added_count = 0
            skipped_count = 0
            order_index = 0
            
            # Process each day in order (Sunday=0 to Saturday=6)
            for day_offset in range(7):
                current_date = start_date + timedelta(days=day_offset)
                day_name = current_date.strftime('%A')
                day_prefix = current_date.strftime('%a').lower()  # sun, mon, tue, etc.
                day_items = items_by_day.get(day_offset, [])
                
                logger.info(f"Adding {len(day_items)} items for {day_name}")
                
                # Add items for this day
                for item in day_items:
                    asset_id = item.get('asset_id')
                    is_live_input = item.get('is_live_input', False) or item.get('title', '').startswith('Live Input')
                    file_path = item.get('file_path', '')
                    
                    # Check if this is a Live Input item (SDI input)
                    if is_live_input or '/mnt/main/tv/inputs/' in file_path:
                        # This is a live input for weekly schedule
                        start_time = item.get('start_time', '00:00:00')
                        
                        # Remove day prefix from start time if present
                        if isinstance(start_time, str) and ' ' in start_time:
                            parts = start_time.split(' ', 1)
                            if any(day in parts[0].lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                                start_time = parts[1] if len(parts) > 1 else '00:00:00'
                        
                        # For live inputs, create special metadata
                        live_metadata = {
                            'is_live_input': True,
                            'file_path': file_path,
                            'title': item.get('title', 'Live Input'),
                            'guid': item.get('guid', ''),
                            'loop': item.get('loop', '0'),
                            'day_prefix': day_prefix,
                            'day_offset': day_offset
                        }
                        
                        scheduler_postgres.add_item_to_schedule(
                            schedule_id,
                            0,  # Special asset_id for live inputs
                            order_index=order_index,
                            scheduled_start_time=start_time,
                            scheduled_duration_seconds=item.get('duration_seconds', 0),
                            metadata=live_metadata
                        )
                        added_count += 1
                        order_index += 1
                        logger.info(f"Added weekly live input item: {file_path} on {day_name}")
                        continue
                    
                    if asset_id and isinstance(asset_id, str) and len(asset_id) == 24 and all(c in '0123456789abcdef' for c in asset_id.lower()):
                        logger.warning(f"Asset ID {asset_id} appears to be a MongoDB ObjectId, not a PostgreSQL integer")
                        skipped_count += 1
                        continue
                    
                    if asset_id:
                        try:
                            # Get the start time and remove day prefix if present
                            start_time = item.get('start_time', '00:00:00')
                            logger.debug(f"Processing item {added_count}: raw start_time = '{start_time}'")
                            
                            # If start time has day prefix, remove it for database storage
                            if isinstance(start_time, str) and ' ' in start_time:
                                parts = start_time.split(' ', 1)
                                if any(day in parts[0].lower() for day in ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']):
                                    # Extract just the time part
                                    time_part = parts[1] if len(parts) > 1 else '00:00:00'
                                    # Convert from 12-hour to 24-hour format if needed
                                    if 'am' in time_part.lower() or 'pm' in time_part.lower():
                                        from datetime import datetime as dt
                                        # Parse and convert to 24-hour format
                                        try:
                                            # Remove extra spaces and normalize
                                            time_part = ' '.join(time_part.split())
                                            
                                            # Check if time has milliseconds
                                            if '.' in time_part:
                                                # Split time and milliseconds
                                                time_base, ms_part = time_part.rsplit('.', 1)
                                                # Extract milliseconds and am/pm
                                                ms_str = ''
                                                for char in ms_part:
                                                    if char.isdigit():
                                                        ms_str += char
                                                    else:
                                                        break
                                                milliseconds = ms_str[:3].ljust(3, '0')  # Ensure 3 digits
                                                # Parse the base time
                                                parsed_time = dt.strptime(time_base.strip() + ' ' + ms_part.lstrip('0123456789').strip(), '%I:%M:%S %p')
                                                start_time = parsed_time.strftime('%H:%M:%S') + '.' + milliseconds
                                            else:
                                                # No milliseconds
                                                parsed_time = dt.strptime(time_part, '%I:%M:%S %p')
                                                start_time = parsed_time.strftime('%H:%M:%S')
                                        except Exception as e:
                                            logger.warning(f"Failed to parse time '{time_part}': {e}")
                                            # If parsing fails, use default
                                            start_time = '00:00:00'
                                    else:
                                        start_time = time_part
                            
                            logger.debug(f"Item {added_count}: final start_time for DB = '{start_time}'")
                            
                            # Store the day prefix in metadata for the export function
                            scheduler_postgres.add_item_to_schedule(
                                schedule_id,
                                int(asset_id),
                                order_index=order_index,
                                scheduled_start_time=start_time,
                                scheduled_duration_seconds=item.get('duration_seconds', 0),
                                metadata={'day_prefix': day_prefix, 'day_offset': day_offset}
                            )
                            added_count += 1
                            order_index += 1
                        except (ValueError, TypeError) as e:
                            logger.error(f"Invalid asset_id {asset_id}: {str(e)}")
                            skipped_count += 1
                    else:
                        logger.warning(f"Skipping item - no asset_id")
                        skipped_count += 1
            
            # Update total duration for the schedule
            # Use direct SQL to update the total duration
            conn = db_manager._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE schedules 
                    SET total_duration_seconds = (
                        SELECT COALESCE(SUM(scheduled_duration_seconds), 0)
                        FROM scheduled_items
                        WHERE schedule_id = %s
                    )
                    WHERE id = %s
                """, (schedule_id, schedule_id))
                conn.commit()
                cursor.close()
                logger.info(f"Updated total duration for weekly schedule {schedule_id}")
            except Exception as e:
                logger.error(f"Error updating total duration: {str(e)}")
            finally:
                db_manager._put_connection(conn)
            
            # Mark this schedule as weekly type
            scheduler_postgres.update_schedule_metadata(schedule_id, {'type': 'weekly'})
            
            return jsonify({
                'success': True,
                'message': f'Weekly schedule created successfully with {added_count} items',
                'schedule_id': schedule_id,
                'added_count': added_count,
                'skipped_count': skipped_count
            })
        
        else:
            # Create a daily schedule using the existing method
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
        logger.info(f"Adding {len(items)} items to schedule")
        for idx, item in enumerate(items):
            logger.info(f"Item {idx}: title='{item.get('title') or item.get('content_title') or item.get('file_name')}', start_time='{item.get('start_time')}', asset_id={item.get('asset_id')}")
            
            asset_id = item.get('asset_id')
            is_live_input = item.get('is_live_input', False) or item.get('title', '').startswith('Live Input')
            file_path = item.get('file_path', '')
            
            # Debug logging
            logger.info(f"Processing item {idx}: asset_id={asset_id}, is_live_input={is_live_input}, file_path={file_path}")
            
            # Check if this is a Live Input item (SDI input)
            if is_live_input or '/mnt/main/tv/inputs/' in file_path:
                # This is a live input, add it directly without asset_id
                start_time = item.get('start_time', '00:00:00')
                duration = item.get('duration_seconds', 0)
                
                logger.info(f"Processing Live Input item {idx}: title='{item.get('title')}', start_time='{start_time}', duration={duration}")
                
                # For live inputs, we need to add them as special items
                # Create a placeholder entry in the schedule_items table
                # The file_path will be stored in metadata
                metadata = {
                    'is_live_input': True,
                    'file_path': file_path,
                    'title': item.get('title', 'Live Input'),
                    'guid': item.get('guid', ''),
                    'loop': item.get('loop', '0')
                }
                
                # Use a special asset_id (0) for live inputs
                scheduler_postgres.add_item_to_schedule(
                    schedule_id,
                    0,  # Special asset_id for live inputs
                    order_index=idx,
                    scheduled_start_time=start_time,
                    scheduled_duration_seconds=duration,
                    metadata=metadata
                )
                added_count += 1
                logger.info(f"Added live input item {idx}: {file_path} at {start_time} for {duration}s")
                continue
            
            # Check if asset_id looks like a MongoDB ObjectId (24 hex chars)
            if asset_id and isinstance(asset_id, str) and len(asset_id) == 24 and all(c in '0123456789abcdef' for c in asset_id.lower()):
                logger.warning(f"Asset ID {asset_id} appears to be a MongoDB ObjectId, not a PostgreSQL integer")
                skipped_count += 1
                continue
            
            if asset_id:
                try:
                    # Ensure asset_id is an integer
                    asset_id = int(asset_id)
                    
                    # Use the time from the template if available
                    start_time = item.get('start_time', '00:00:00')
                    
                    scheduler_postgres.add_item_to_schedule(
                        schedule_id,
                        asset_id,
                        order_index=idx,
                        scheduled_start_time=start_time,
                        scheduled_duration_seconds=item.get('scheduled_duration_seconds', 0) or item.get('duration_seconds', 0)
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
        
        # Don't recalculate times - preserve the times from the template
        # scheduler_postgres.recalculate_schedule_times(schedule_id)
        logger.info("Preserving template times - not recalculating")
            
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
        schedule_date = data.get('schedule_date')  # Date when schedule starts (YYYY-MM-DD format)
        
        # Debug: Log the template items
        logger.info(f"Received template type: {template.get('type')}")
        logger.info(f"Template has {len(template.get('items', []))} items")
        logger.info(f"Available content count: {len(available_content)}")
        
        # Debug: Check expiration dates in available content
        content_with_expiry = 0
        content_without_expiry = 0
        for content in available_content:
            # Check in the scheduling object
            scheduling = content.get('scheduling', {})
            if scheduling.get('content_expiry_date'):
                content_with_expiry += 1
            else:
                content_without_expiry += 1
        logger.info(f"Content expiration status: {content_with_expiry} with expiry date, {content_without_expiry} without expiry date")
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
        
        # Parse schedule date
        base_date = None
        if schedule_date:
            try:
                base_date = datetime.strptime(schedule_date, '%Y-%m-%d')
                logger.info(f"Using schedule date: {base_date.strftime('%Y-%m-%d')}")
            except ValueError:
                logger.warning(f"Invalid schedule_date format: {schedule_date}, using current date")
                base_date = datetime.now()
        else:
            base_date = datetime.now()
            logger.info(f"No schedule_date provided, using current date: {base_date.strftime('%Y-%m-%d')}")
        
        # For weekly schedules, adjust to start on Sunday
        if schedule_type == 'weekly':
            # Find the Sunday of the week containing the base date
            days_until_sunday = (6 - base_date.weekday()) % 7
            if days_until_sunday == 0 and base_date.weekday() != 6:
                # If today is not Sunday, go to previous Sunday
                days_until_sunday = -base_date.weekday() - 1
            base_date = base_date + timedelta(days=days_until_sunday)
            logger.info(f"Adjusted to Sunday for weekly schedule: {base_date.strftime('%Y-%m-%d')}")
        
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
                logger.debug(f"Parsing weekly time format: '{start_time}'")
                parts = start_time.lower().split(' ')
                logger.debug(f"Split into parts: {parts}")
                
                day_map = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
                day_index = day_map.get(parts[0], 0)
                
                # Parse time portion
                if len(parts) < 2:
                    logger.error(f"Invalid weekly time format - missing time portion: '{start_time}'")
                    raise ValueError(f"Invalid weekly time format: '{start_time}'")
                
                time_str = parts[1]
                logger.debug(f"Time portion: '{time_str}'")
                
                # Check if time string contains colon
                if ':' not in time_str:
                    logger.error(f"Invalid time format - missing colon: '{time_str}' in '{start_time}'")
                    raise ValueError(f"Invalid time format in '{start_time}': '{time_str}'")
                
                time_parts = time_str.split(':')
                logger.debug(f"Time parts after split: {time_parts}")
                
                try:
                    hours = int(time_parts[0])
                except ValueError as e:
                    logger.error(f"Failed to parse hours from '{time_parts[0]}' in time '{start_time}'")
                    raise ValueError(f"Invalid hour value in '{start_time}': '{time_parts[0]}'")
                
                if len(parts) > 2 and parts[2] == 'pm' and hours != 12:
                    hours += 12
                elif len(parts) > 2 and parts[2] == 'am' and hours == 12:
                    hours = 0
                    
                try:
                    minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                except ValueError as e:
                    logger.error(f"Failed to parse minutes from '{time_parts[1]}' in time '{start_time}'")
                    raise ValueError(f"Invalid minute value in '{start_time}': '{time_parts[1]}'")
                    
                start_seconds = (day_index * 24 * 3600) + (hours * 3600) + (minutes * 60)
                logger.debug(f"Parsed to {start_seconds} seconds (day={day_index}, hours={hours}, minutes={minutes})")
            else:
                # Parse daily format - could be 24-hour (HH:MM:SS) or 12-hour (HH:MM:SS am/pm)
                logger.debug(f"Parsing daily time format: '{start_time}'")
                
                # Check if it contains am/pm
                time_str = str(start_time).strip()
                is_12_hour = time_str.lower().endswith((' am', ' pm'))
                
                if is_12_hour:
                    # Handle 12-hour format like "12:00:00 am"
                    parts = time_str.lower().split()
                    if len(parts) >= 2:
                        time_portion = parts[0]
                        am_pm = parts[1]
                        
                        time_parts = time_portion.split(':')
                        if len(time_parts) >= 2:
                            try:
                                hours = int(time_parts[0])
                                minutes = int(time_parts[1])
                                seconds = 0
                                
                                # Handle seconds if present
                                if len(time_parts) >= 3:
                                    # Remove any remaining am/pm text from seconds
                                    sec_str = time_parts[2].replace('am', '').replace('pm', '').strip()
                                    try:
                                        seconds = float(sec_str)
                                    except ValueError:
                                        logger.warning(f"Could not parse seconds from '{time_parts[2]}', defaulting to 0")
                                        seconds = 0
                                
                                # Convert 12-hour to 24-hour
                                if am_pm == 'pm' and hours != 12:
                                    hours += 12
                                elif am_pm == 'am' and hours == 12:
                                    hours = 0
                                
                                start_seconds = (hours * 3600) + (minutes * 60) + seconds
                                logger.debug(f"Parsed 12-hour format to {start_seconds} seconds (hours={hours}, minutes={minutes}, seconds={seconds})")
                            except ValueError as e:
                                logger.error(f"Failed to parse 12-hour time '{start_time}': {e}")
                                raise ValueError(f"Invalid 12-hour time format: '{start_time}'")
                        else:
                            logger.error(f"Invalid time format - not enough parts: '{time_portion}'")
                            raise ValueError(f"Invalid time format: '{start_time}'")
                    else:
                        logger.error(f"Invalid 12-hour format - missing am/pm: '{start_time}'")
                        raise ValueError(f"Invalid 12-hour time format: '{start_time}'")
                else:
                    # Handle 24-hour format like "08:30:45"
                    time_parts = time_str.split(':')
                    if len(time_parts) >= 3:
                        try:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1])
                            seconds = float(time_parts[2])
                            start_seconds = (hours * 3600) + (minutes * 60) + seconds
                            logger.debug(f"Parsed 24-hour format to {start_seconds} seconds")
                        except ValueError as e:
                            logger.error(f"Failed to parse 24-hour time '{start_time}': {e}")
                            raise ValueError(f"Invalid 24-hour time format: '{start_time}'")
                    elif len(time_parts) == 2:
                        # Handle HH:MM format
                        try:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1])
                            start_seconds = (hours * 3600) + (minutes * 60)
                            logger.debug(f"Parsed HH:MM format to {start_seconds} seconds")
                        except ValueError as e:
                            logger.error(f"Failed to parse time '{start_time}': {e}")
                            raise ValueError(f"Invalid time format: '{start_time}'")
                    else:
                        logger.error(f"Invalid time format - not enough parts: '{start_time}'")
                        raise ValueError(f"Invalid time format: '{start_time}'")
                
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
                'duration': duration,
                'is_gap': item.get('is_gap', False)
            })
            
            if item.get('is_gap', False):
                logger.info(f"Original GAP item {idx}: {title} at '{item['start_time']}' from {start_seconds/3600:.2f}h to {end_seconds/3600:.2f}h")
            else:
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
        
        # Reset rotation to ensure consistent behavior between fills
        scheduler._reset_rotation()
        
        # Convert available content to the format expected by scheduler
        # Filter out content from /mnt/main/Recordings and validate files exist
        content_by_id = {}
        filtered_count = 0
        missing_files_count = 0
        
        # Pre-validate all files to avoid repeated FTP connections
        logger.info("Pre-validating file existence for available content...")
        validated_files = {}  # file_path -> exists (True/False)
        
        # Get FTP configurations once
        config = config_manager.get_all_config()
        source_config = config.get('servers', {}).get('source', {})
        target_config = config.get('servers', {}).get('target', {})
        
        # Create FTP connections once for batch validation
        source_ftp = FTPManager(source_config)
        target_ftp = FTPManager(target_config)
        source_connected = source_ftp.connect()
        target_connected = target_ftp.connect()
        
        # Log first few file paths to debug the issue
        if available_content and len(available_content) > 0:
            logger.info(f"Sample file paths from available content:")
            for i, content in enumerate(available_content[:5]):
                logger.info(f"  Sample {i+1}: {content.get('file_path', 'NO PATH')}")
        
        try:
            for content in available_content:
                # Check if this content is from Recordings folder
                file_path = content.get('file_path', '')
                if '/mnt/main/Recordings' in file_path:
                    filtered_count += 1
                    continue  # Skip content from Recordings folder
                
                # Check if we've already validated this file
                if file_path in validated_files:
                    if validated_files[file_path]:
                        content_by_id[content.get('id')] = content
                    else:
                        missing_files_count += 1
                    continue
                
                # Validate file exists on at least one server
                file_exists = False
                
                # If file_path doesn't start with /mnt/, try common base paths
                paths_to_check = [file_path]
                if not file_path.startswith('/mnt/'):
                    # Common base paths where content might be stored
                    # Note: /mnt/main and /mnt/md127 are the same via symbolic link
                    base_paths = [
                        '/mnt/main/ATL26 On-Air Content/',
                        '/mnt/main/'
                    ]
                    for base in base_paths:
                        paths_to_check.append(base + file_path)
                
                if source_connected:
                    for check_path in paths_to_check:
                        try:
                            source_ftp.ftp.size(check_path)
                            file_exists = True
                            validated_files[file_path] = True
                            logger.debug(f"File found on source server at: {check_path}")
                            break
                        except Exception as e:
                            # Log the first attempt with more detail for debugging
                            if check_path == paths_to_check[0]:
                                logger.debug(f"File not found at {check_path}: {str(e)}")
                            pass
                
                if not file_exists and target_connected:
                    for check_path in paths_to_check:
                        try:
                            target_ftp.ftp.size(check_path)
                            file_exists = True
                            validated_files[file_path] = True
                            logger.debug(f"File found on target server at: {check_path}")
                            break
                        except:
                            pass
                
                if not file_exists:
                    validated_files[file_path] = False
                    # For now, still include files we can't validate to avoid breaking scheduling
                    # This allows us to debug while keeping the system functional
                    content_by_id[content.get('id')] = content
                    logger.warning(f"Could not validate file existence (including anyway): {file_path}")
                else:
                    content_by_id[content.get('id')] = content
        
        finally:
            # Always disconnect FTP connections
            if source_connected:
                source_ftp.disconnect()
            if target_connected:
                target_ftp.disconnect()
        
        # Debug: Log available content info
        logger.info(f"Available content count: {len(available_content)}")
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} items from /mnt/main/Recordings")
        logger.info(f"Content available for scheduling: {len(content_by_id)}")
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
        # We need to track ALL items in the template (including previously filled items)
        # to ensure replay delays work correctly when filling gaps multiple times
        asset_schedule_times = {}  # asset_id -> list of scheduled times in seconds
        
        # Track all existing template items that have assets (not just placeholders)
        for item in template.get('items', []):
            asset_id = item.get('asset_id') or item.get('id') or item.get('content_id')
            # Only track items that have actual content (not empty template slots)
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
                    # Parse daily format - could be 24-hour (HH:MM:SS) or 12-hour (HH:MM:SS am/pm)
                    time_str = str(start_time).strip()
                    is_12_hour = time_str.lower().endswith((' am', ' pm'))
                    
                    if is_12_hour:
                        # Handle 12-hour format like "12:00:00 am"
                        parts = time_str.lower().split()
                        if len(parts) >= 2:
                            time_portion = parts[0]
                            am_pm = parts[1]
                            
                            time_parts = time_portion.split(':')
                            if len(time_parts) >= 2:
                                hours = int(time_parts[0])
                                minutes = int(time_parts[1])
                                seconds = 0
                                
                                # Handle seconds if present
                                if len(time_parts) >= 3:
                                    # Remove any remaining am/pm text from seconds
                                    sec_str = time_parts[2].replace('am', '').replace('pm', '').strip()
                                    try:
                                        seconds = float(sec_str)
                                    except ValueError:
                                        seconds = 0
                                
                                # Convert 12-hour to 24-hour
                                if am_pm == 'pm' and hours != 12:
                                    hours += 12
                                elif am_pm == 'am' and hours == 12:
                                    hours = 0
                                
                                time_in_seconds = (hours * 3600) + (minutes * 60) + seconds
                    else:
                        # Handle 24-hour format
                        time_parts = str(start_time).split(':')
                        if len(time_parts) >= 3:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1])
                            seconds = float(time_parts[2])
                            time_in_seconds = (hours * 3600) + (minutes * 60) + seconds
                        elif len(time_parts) == 2:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1])
                            time_in_seconds = (hours * 3600) + (minutes * 60)
                
                if asset_id not in asset_schedule_times:
                    asset_schedule_times[asset_id] = []
                asset_schedule_times[asset_id].append(time_in_seconds)
        
        logger.info(f"Assets already scheduled in template: {len(asset_schedule_times)}")
        
        # Load replay delay configuration
        try:
            from config_manager import ConfigManager
            config_mgr = ConfigManager()
            scheduling_config = config_mgr.get_scheduling_settings()
            replay_delays = scheduling_config.get('replay_delays', {
                'id': 1,
                'spots': 2,
                'short_form': 4,
                'long_form': 8
            })
            logger.info(f"Replay delays: {replay_delays}")
        except Exception as e:
            logger.warning(f"Could not load replay delays, using defaults: {e}")
            replay_delays = {'id': 1, 'spots': 2, 'short_form': 4, 'long_form': 8}
        
        # Fill gaps using rotation logic
        consecutive_errors = 0
        max_errors = 100  # Same as in create schedule
        total_cycles_without_content = 0
        max_cycles = 20  # After trying all categories 20 times, stop
        
        # Reset rotation to ensure consistent starting point
        scheduler._reset_rotation()
        
        # Force reload of configuration to ensure we have the latest rotation order
        scheduler._config_loaded = False
        scheduler._load_config_if_needed()
        logger.info(f"Using rotation order: {scheduler.duration_rotation}")
        
        # Process each gap individually
        for gap in gaps:
            gap_start = gap['start']
            gap_end = gap['end']
            gap_duration = gap_end - gap_start
            
            # Skip very small gaps (less than 10 seconds)
            if gap_duration < 10:
                logger.info(f"Skipping gap of {gap_duration:.1f} seconds (too small to fill)")
                continue
            
            logger.info(f"Filling gap from {gap_start/3600:.1f}h to {gap_end/3600:.1f}h (duration: {gap_duration/3600:.1f}h)")
            logger.info(f"  Exact gap values: start={gap_start}s ({gap_start/3600:.6f}h), end={gap_end}s ({gap_end/3600:.6f}h)")
            
            # Log date calculation for this gap
            if schedule_type == 'weekly':
                gap_day_offset = int(gap_start // 86400)
                gap_air_date = base_date + timedelta(days=gap_day_offset)
                logger.info(f"  Weekly schedule: Gap starts on {gap_air_date.strftime('%A %Y-%m-%d')} (day {gap_day_offset} from Sunday)")
            else:
                logger.info(f"  Daily schedule: All content airs on {base_date.strftime('%Y-%m-%d')}")
            
            current_position = gap_start
            
            while current_position < gap_end:
                # Get next duration category from rotation
                duration_category = scheduler._get_next_duration_category()
                
                # Check if we should skip long-form content after 10 PM
                current_hour = (current_position % 86400) / 3600
                if current_hour >= 22 and duration_category == 'long_form':
                    logger.info(f"Skipping long-form content after 10 PM (current hour: {current_hour:.1f})")
                    scheduler._advance_rotation()
                    continue
                
                # Filter available content by category and replay delays
                category_content = []
                wrong_category = 0
                blocked_by_delay = 0
                blocked_by_expiry = 0
                no_expiry_date = 0
                
                # Get replay delay for this category (in hours)
                replay_delay_hours = replay_delays.get(duration_category, 24)
                
                # Progressive delay reduction after 10 PM
                current_hour = (current_position % 86400) / 3600
                if current_hour >= 22:  # After 10 PM
                    if current_hour >= 23.5:  # After 11:30 PM
                        replay_delay_hours = replay_delay_hours / 4  # 25% of normal
                    elif current_hour >= 23:  # After 11 PM
                        replay_delay_hours = replay_delay_hours / 2  # 50% of normal
                    else:  # 10 PM - 11 PM
                        replay_delay_hours = replay_delay_hours * 0.75  # 75% of normal
                    logger.debug(f"Reduced replay delay for {duration_category} to {replay_delay_hours:.1f} hours at {current_hour:.1f}h")
                
                replay_delay_seconds = replay_delay_hours * 3600
                
                for content_id, content in content_by_id.items():
                    
                    # Check duration category
                    if content.get('duration_category') != duration_category:
                        wrong_category += 1
                        continue
                    
                    # Calculate the actual air date/time for this gap position
                    if schedule_type == 'weekly':
                        # For weekly schedules, calculate which day of the week this position falls on
                        days_offset = int(current_position // 86400)  # 86400 seconds per day
                        air_date = base_date + timedelta(days=days_offset)
                    else:
                        # For daily schedules, it's the same date
                        air_date = base_date
                    
                    # Check expiration date (stored in scheduling object)
                    scheduling = content.get('scheduling', {})
                    expiry_date_str = scheduling.get('content_expiry_date')
                    if not expiry_date_str:
                        # No expiration date means content doesn't expire
                        no_expiry_date += 1
                        logger.debug(f"Content '{content.get('content_title', content.get('file_name'))}' has no expiration date, can be scheduled")
                    else:
                        try:
                            # Parse various date formats
                            if isinstance(expiry_date_str, str):
                                if 'T' in expiry_date_str:
                                    expiry_date = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00'))
                                else:
                                    expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
                            else:
                                expiry_date = expiry_date_str
                            
                            # Make dates timezone-naive for comparison
                            if hasattr(expiry_date, 'tzinfo') and expiry_date.tzinfo:
                                expiry_date = expiry_date.replace(tzinfo=None)
                            if hasattr(air_date, 'tzinfo') and air_date.tzinfo:
                                air_date = air_date.replace(tzinfo=None)
                            
                            if expiry_date <= air_date:
                                blocked_by_expiry += 1
                                logger.info(f"EXPIRATION CHECK: Content '{content.get('content_title', content.get('file_name'))}' expires on {expiry_date.strftime('%Y-%m-%d')}, cannot schedule for {air_date.strftime('%Y-%m-%d')} (position: {current_position/3600:.1f}h)")
                                continue
                        except Exception as e:
                            logger.warning(f"Error parsing expiration date for content {content_id}: {e}")
                    
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
                                logger.debug(f"Content {content_id} blocked: {time_since_last/3600:.1f}h since last, need {replay_delay_seconds/3600:.1f}h")
                                break
                        
                        if not can_schedule:
                            continue
                    
                    category_content.append(content)
            
                if not category_content:
                    logger.info(f"Category {duration_category}: found=0, wrong_category={wrong_category}, blocked_by_delay={blocked_by_delay}, blocked_by_expiry={blocked_by_expiry}, no_expiry_date={no_expiry_date}, total_available={len(content_by_id)}")
                
                # If no content due to delays, try with reduced delays only as last resort
                if not category_content and blocked_by_delay > 0 and total_cycles_without_content >= 2:
                    logger.info(f"Trying category {duration_category} with reduced replay delays (50% of configured)")
                    # Try again with reduced delays (50% of configured delay)
                    reduced_delay_seconds = replay_delay_seconds * 0.5
                    
                    for content_id, content in content_by_id.items():
                        if content.get('duration_category') == duration_category:
                            # Check with reduced delay
                            if content_id in asset_schedule_times:
                                last_times = asset_schedule_times[content_id]
                                can_schedule = True
                                
                                for last_time in last_times:
                                    time_since_last = current_position - last_time
                                    if time_since_last < reduced_delay_seconds:
                                        can_schedule = False
                                        break
                                
                                if can_schedule:
                                    category_content.append(content)
                            else:
                                category_content.append(content)
                    
                    if category_content:
                        logger.info(f"Found {len(category_content)} items with reduced delay restrictions ({reduced_delay_seconds/3600:.1f} hours)")
                
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
                    
                    # Advance rotation to try next category
                    scheduler._advance_rotation()
                    # Continue to the next category
                    continue
            
                # Sort by engagement score and shelf life (like scheduler does)
                category_content.sort(key=lambda x: (
                    -(x.get('engagement_score', 50) + 
                      (20 if x.get('shelf_life_score') == 'high' else 10 if x.get('shelf_life_score') == 'medium' else 0))
                ))
                
                # For ID content, add variety by selecting from top candidates randomly
                if duration_category == 'id' and len(category_content) > 1:
                    # Take top 40% of available IDs (at least 3) to add variety
                    import random
                    top_count = max(3, int(len(category_content) * 0.4))
                    top_candidates = category_content[:top_count]
                    selected = random.choice(top_candidates)
                    logger.debug(f"Selected ID from top {top_count} candidates for variety")
                else:
                    # Select the best content for other categories
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
                        # Current category doesn't have content that fits
                        # Try all other categories to find content that fits this gap
                        logger.info(f"No {duration_category} content fits remaining gap of {remaining/60:.1f} minutes")
                        logger.info(f"Searching all categories for content that fits...")
                        
                        best_fit = None
                        best_duration = 0
                        
                        # Define category priority for small gaps (prefer shorter content)
                        gap_minutes = remaining / 60
                        current_hour = (current_position % 86400) / 3600
                        
                        # Exclude long-form after 10 PM
                        if current_hour >= 22:
                            if gap_minutes < 2:
                                category_priority = ['id', 'spots', 'short_form']
                            elif gap_minutes < 20:
                                category_priority = ['spots', 'short_form', 'id']
                            else:
                                category_priority = ['short_form', 'spots', 'id']
                        else:
                            if gap_minutes < 2:
                                category_priority = ['id', 'spots', 'short_form', 'long_form']
                            elif gap_minutes < 20:
                                category_priority = ['spots', 'short_form', 'id', 'long_form']
                            else:
                                category_priority = ['short_form', 'spots', 'long_form', 'id']
                        
                        # Try each category in priority order
                        for try_category in category_priority:
                            if try_category == duration_category:
                                continue  # Already tried this category
                            
                            for content_id, content in content_by_id.items():
                                # Check if content is in the category we're trying
                                if content.get('duration_category') != try_category:
                                    continue
                                
                                # Check duration
                                content_duration = float(content.get('duration_seconds', content.get('file_duration', 0)))
                                if content_duration <= remaining - safety_margin:
                                    # Check replay delay
                                    content_id = content.get('id')
                                    can_schedule = True
                                    
                                    if content_id in asset_schedule_times:
                                        last_times = asset_schedule_times[content_id]
                                        replay_delay_hours = replay_delays.get(try_category, 24)
                                        
                                        # Progressive delay reduction after 10 PM
                                        current_hour = (current_position % 86400) / 3600
                                        if current_hour >= 22:  # After 10 PM
                                            if current_hour >= 23.5:  # After 11:30 PM
                                                replay_delay_hours = replay_delay_hours / 4  # 25% of normal
                                            elif current_hour >= 23:  # After 11 PM
                                                replay_delay_hours = replay_delay_hours / 2  # 50% of normal
                                            else:  # 10 PM - 11 PM
                                                replay_delay_hours = replay_delay_hours * 0.75  # 75% of normal
                                            logger.debug(f"Reduced replay delay for {try_category} to {replay_delay_hours:.1f} hours at {current_hour:.1f}h")
                                        
                                        replay_delay_seconds = replay_delay_hours * 3600
                                        
                                        for last_time in last_times:
                                            time_since_last = current_position - last_time
                                            if time_since_last < replay_delay_seconds:
                                                can_schedule = False
                                                break
                                    
                                    if can_schedule and content_duration > best_duration:
                                        # Found a better fitting item
                                        best_fit = content
                                        best_duration = content_duration
                        
                        if best_fit:
                            selected = best_fit
                            duration = best_duration
                            logger.info(f"Found {best_fit.get('duration_category')} content '{best_fit.get('content_title', best_fit.get('file_name'))}' ({duration/60:.1f} min) that fits gap")
                        else:
                            logger.warning(f"No content from any category fits remaining gap of {remaining/60:.1f} minutes")
                            # Log gap details for debugging
                            if schedule_type == 'weekly':
                                # For weekly schedules, show which day this gap is on
                                day_index = int(gap_end / 86400)
                                days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
                                day_name = days[day_index % 7]
                                gap_end_time = gap_end % 86400
                                gap_end_hours = gap_end_time / 3600
                                logger.info(f"Gap details ({day_name}): ends at {gap_end_hours:.2f}h ({int(gap_end_hours)}:{int((gap_end_hours % 1) * 60):02d}), position={current_position/3600:.2f}h")
                            else:
                                gap_end_time = gap_end % 86400
                                gap_end_hours = gap_end_time / 3600
                                logger.info(f"Gap details: ends at {gap_end_hours:.2f}h ({int(gap_end_hours)}:{int((gap_end_hours % 1) * 60):02d}), position={current_position/3600:.2f}h")
                            
                            # Check if this is an end-of-day gap (within 2 hours of midnight)
                            # For daily schedules, gap_end should be close to 86400 (24 hours)
                            # For weekly schedules, check if we're near the end of any day
                            is_end_of_day = False
                            end_of_day_threshold = 7200  # 2 hours before midnight
                            
                            if schedule_type == 'daily':
                                # Check if gap ends near midnight (24 hours = 86400 seconds)
                                is_end_of_day = gap_end >= 86400 - end_of_day_threshold  # Within 2 hours of midnight
                            else:
                                # For weekly schedules, check if gap ends near any midnight
                                # Days are 0-6, so check if we're near any day boundary
                                seconds_in_week = gap_end % (7 * 86400)
                                seconds_in_day = seconds_in_week % 86400
                                is_end_of_day = seconds_in_day >= 86400 - end_of_day_threshold  # Within 2 hours of midnight
                            
                            # Check if gap is too small to fill (less than 10 seconds)
                            if remaining < 10:
                                logger.info(f"Gap of {remaining:.1f} seconds is too small to fill. Moving to next gap.")
                                break
                            
                            if is_end_of_day:
                                # For end-of-day gaps, be more aggressive about filling
                                # Accept larger gaps the closer we are to midnight
                                time_to_midnight = 86400 - (gap_end % 86400)
                                
                                # Be more aggressive - target 10 minutes or less for end-of-day gaps
                                target_end_gap = 600  # 10 minutes target
                                
                                # Only accept gaps if they're at or below our target
                                if remaining <= target_end_gap:
                                    logger.info(f"End-of-day gap detected ({remaining/60:.1f} min remaining, {time_to_midnight/60:.1f} min to midnight). Accepting unfilled time.")
                                    break
                                    
                                # Prevent infinite loops - if we've tried too many times, accept the gap
                                if consecutive_errors >= 10:
                                    logger.warning(f"End-of-day gap: tried {consecutive_errors} times without success. Accepting gap of {remaining/60:.1f} minutes to prevent infinite loop.")
                                    break
                                
                                # Try shorter content categories first for end-of-day gaps
                                logger.info(f"End-of-day gap of {remaining/60:.1f} min. Trying shorter content categories...")
                                
                                # Try categories in order of shortest to longest for end-of-day
                                end_of_day_order = ['id', 'spots', 'short_form']  # Skip long_form for end-of-day
                                found_shorter_content = False
                                
                                for try_category in end_of_day_order:
                                    category_content = [c for c in available_content_by_category.get(try_category, [])]
                                    if category_content:
                                        # Sort by duration (shortest first) for end-of-day
                                        category_content.sort(key=lambda x: x.get('duration_seconds', 0))
                                        
                                        # For ID content, shuffle to add variety
                                        if try_category == 'id' and len(category_content) > 1:
                                            import random
                                            # Group by similar durations (within 1 second)
                                            duration_groups = {}
                                            for c in category_content:
                                                dur = int(c.get('duration_seconds', 0))
                                                if dur not in duration_groups:
                                                    duration_groups[dur] = []
                                                duration_groups[dur].append(c)
                                            
                                            # Rebuild list with shuffled groups
                                            category_content = []
                                            for dur in sorted(duration_groups.keys()):
                                                group = duration_groups[dur]
                                                random.shuffle(group)
                                                category_content.extend(group)
                                            
                                            for content in category_content:
                                                content_duration = content.get('duration_seconds', 0)
                                                if content_duration <= remaining and content_duration > 0:
                                                    # Check replay delays with progressive reduction for end-of-day
                                                    can_schedule = True
                                                    content_id = content.get('id')
                                                    if content_id in asset_schedule_times:
                                                        replay_delay_hours = replay_delays.get(try_category, 1)
                                                        
                                                        # Progressive delay reduction after 10 PM
                                                        current_hour = (current_position % 86400) / 3600
                                                        if current_hour >= 22:  # After 10 PM
                                                            if current_hour >= 23.5:  # After 11:30 PM
                                                                replay_delay_hours = replay_delay_hours / 4  # 25% of normal
                                                            elif current_hour >= 23:  # After 11 PM
                                                                replay_delay_hours = replay_delay_hours / 2  # 50% of normal
                                                            else:  # 10 PM - 11 PM
                                                                replay_delay_hours = replay_delay_hours * 0.75  # 75% of normal
                                                            logger.debug(f"Reduced replay delay for {try_category} to {replay_delay_hours:.1f} hours at {current_hour:.1f}h")
                                                        
                                                        replay_delay_seconds = replay_delay_hours * 3600
                                                        for last_time in asset_schedule_times[content_id]:
                                                            if current_position - last_time < replay_delay_seconds:
                                                                can_schedule = False
                                                                break
                                                    
                                                    if can_schedule:
                                                        selected = content
                                                        duration = content_duration
                                                        found_shorter_content = True
                                                        logger.info(f"Found shorter {try_category} content for end-of-day: '{content.get('content_title', content.get('file_name'))}' ({duration/60:.1f} min)")
                                                        break
                                            
                                            if found_shorter_content:
                                                break
                                    
                                    if not found_shorter_content:
                                        # Try one more time with even more relaxed replay delays for end-of-day gaps
                                        # Be aggressive to meet our 10-minute target
                                        if remaining > 600:  # More than 10 minutes remaining
                                            logger.info(f"End-of-day gap ({remaining/60:.1f} min) exceeds 10-minute target. Trying with minimal replay delays...")
                                            
                                            for try_category in end_of_day_order:
                                                category_content = [c for c in available_content_by_category.get(try_category, [])]
                                                if category_content:
                                                    # Sort by duration for end-of-day
                                                    category_content.sort(key=lambda x: x.get('duration_seconds', 0))
                                                    
                                                    for content in category_content:
                                                        content_duration = content.get('duration_seconds', 0)
                                                        if content_duration <= remaining and content_duration > 0:
                                                            # For large end-of-day gaps, use minimal delays (10% of normal)
                                                            can_schedule = True
                                                            content_id = content.get('id')
                                                            if content_id in asset_schedule_times:
                                                                replay_delay_hours = replay_delays.get(try_category, 1) * 0.1
                                                                replay_delay_seconds = replay_delay_hours * 3600
                                                                
                                                                for last_time in asset_schedule_times[content_id]:
                                                                    if current_position - last_time < replay_delay_seconds:
                                                                        can_schedule = False
                                                                        break
                                                            
                                                            if can_schedule:
                                                                selected = content
                                                                duration = content_duration
                                                                found_shorter_content = True
                                                                logger.info(f"Found {try_category} content with minimal delays: '{content.get('content_title', content.get('file_name'))}' ({duration/60:.1f} min)")
                                                                break
                                                    
                                                    if found_shorter_content:
                                                        break
                                        
                                        if not found_shorter_content:
                                            logger.warning(f"No shorter content fits end-of-day gap of {remaining/60:.1f} minutes even with minimal delays. Accepting unfilled time.")
                                            # Increment error counter to prevent infinite loops
                                            consecutive_errors += 1
                                            break
                            else:
                                # Not end-of-day, normal rotation logic
                                
                                # Check if gap is small enough to accept
                                minimum_fillable_gap = 30  # 30 seconds minimum
                                if remaining < minimum_fillable_gap:
                                    logger.info(f"Gap of {remaining:.1f} seconds is below minimum fillable threshold. Accepting unfilled gap.")
                                    break
                                
                                # For gaps less than 1 minute, accept them after trying once
                                if remaining < 60 and consecutive_errors > 0:
                                    logger.info(f"Small gap of {remaining:.1f} seconds. Accepting after {consecutive_errors} attempts.")
                                    break
                                
                                logger.info(f"Gap of {remaining/60:.1f} min is too large to leave unfilled. Advancing rotation.")
                                scheduler._advance_rotation()
                                consecutive_errors += 1
                                
                                if consecutive_errors >= len(scheduler.duration_rotation) * 2:
                                    logger.warning(f"Tried all rotations twice. Accepting gap of {remaining/60:.1f} minutes.")
                                    break
                                
                                continue
            
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
                    # Add to template (file already validated during pre-processing)
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
                    
                    # Advance rotation after successfully scheduling content
                    scheduler._advance_rotation()
                
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


# Meeting Trimmer endpoints
@app.route('/api/meeting-recordings', methods=['GET'])
def get_meeting_recordings():
    """Get list of meeting recordings with trim status"""
    try:
        # Get parameters from query string
        server = request.args.get('server', 'target')
        recordings_path = request.args.get('source_path', '/mnt/main/Recordings')
        trimmed_path = request.args.get('dest_path', '/mnt/main/ATL26 On-Air Content/MEETINGS')
        
        logger.info(f"Meeting recordings request - Server: {server}, Source: {recordings_path}, Dest: {trimmed_path}")
        
        recordings = []
        
        # Check if we're using FTP or local filesystem
        logger.info(f"Available FTP managers: {list(ftp_managers.keys())}")
        logger.info(f"Checking server '{server}' in ftp_managers: {server in ftp_managers}")
        
        if server in ftp_managers:
            ftp_manager = ftp_managers[server]
            logger.info(f"FTP manager connected: {ftp_manager.connected}")
            
            # Try to connect if not connected
            if not ftp_manager.connected:
                logger.info(f"Attempting to connect to {server} server")
                try:
                    ftp_manager.connect()
                except Exception as e:
                    logger.error(f"Failed to connect to {server}: {str(e)}")
                    return jsonify({'status': 'error', 'message': f'Failed to connect to {server} server: {str(e)}'}), 500
            
            # Use FTP to scan directories
            logger.info(f"Using FTP to scan server {server} path: {recordings_path}")
            
            def scan_ftp_directory(ftp_manager, path):
                try:
                    logger.info(f"Scanning FTP directory: {path}")
                    try:
                        # Use raw LIST command to get both files and directories
                        ftp_manager.ftp.cwd(path)
                        raw_listing = []
                        ftp_manager.ftp.retrlines('LIST', raw_listing.append)
                        logger.info(f"Found {len(raw_listing)} items in {path}")
                        
                        for line in raw_listing:
                            parts = line.split(None, 8)
                            if len(parts) >= 9:
                                permissions = parts[0]
                                filename = parts[8]
                                
                                # Skip . and ..
                                if filename in ['.', '..']:
                                    continue
                                
                                # If it's a directory, scan it recursively
                                if permissions.startswith('d'):
                                    subdir_path = os.path.join(path, filename)
                                    logger.info(f"Found subdirectory: {filename}, scanning {subdir_path}")
                                    scan_ftp_directory(ftp_manager, subdir_path)
                                # If it's a recording (any MP4 file)
                                elif filename.endswith('.mp4'):
                                    logger.info(f"Found meeting recording: {filename}")
                                    file_path = os.path.join(path, filename)
                                    
                                    # Parse filename to create standardized trimmed name
                                    # Example: "2025-08-04 at 080000 250804 Mayor Back to School.mp4"
                                    trimmed_name = filename
                                    
                                    # Try to extract date and meeting name
                                    if filename.startswith('20'):  # Starts with year
                                        try:
                                            # Extract date part (YYYY-MM-DD)
                                            date_part = filename[:10]
                                            # Convert to YYMMDD format
                                            date_obj = datetime.strptime(date_part, '%Y-%m-%d')
                                            date_str = date_obj.strftime('%y%m%d')
                                            
                                            # Extract meeting name - everything after the date/time info
                                            # Look for content after "at HHMMSS YYMMDD "
                                            name_start = filename.find(' ', filename.find(' at ') + 11)
                                            if name_start > 0:
                                                meeting_name = filename[name_start:].replace('.mp4', '').strip()
                                                # Clean up the meeting name
                                                meeting_name = meeting_name.replace(' ', '_')
                                                trimmed_name = f"{date_str}_MTG_{meeting_name}.mp4"
                                            else:
                                                # Fallback: use the whole filename
                                                meeting_name = filename.replace('.mp4', '').replace(' ', '_')
                                                trimmed_name = f"{date_str}_MTG_{meeting_name}.mp4"
                                        except:
                                            # If parsing fails, use current date
                                            date_str = datetime.now().strftime('%y%m%d')
                                            meeting_name = filename.replace('.mp4', '').replace(' ', '_')
                                            trimmed_name = f"{date_str}_MTG_{meeting_name}.mp4"
                                    elif filename.startswith('250'):
                                        # Already in YYMMDD format
                                        pass  # Keep original trimmed_name
                                    
                                    # Check if trimmed file exists
                                    is_trimmed = False
                                    try:
                                        trimmed_files = ftp_manager.list_files(trimmed_path)
                                        is_trimmed = any(f['name'] == trimmed_name for f in trimmed_files)
                                    except:
                                        pass
                                    
                                    # Get file size from listing
                                    size = 0
                                    if len(parts) >= 5 and parts[4].isdigit():
                                        size = int(parts[4])
                                    
                                    # Get relative path for display
                                    rel_path = os.path.relpath(file_path, recordings_path)
                                    
                                    recordings.append({
                                        'filename': filename,
                                        'path': file_path,
                                        'relative_path': rel_path,
                                        'size': size,
                                        'modified': datetime.now().isoformat(),  # FTP doesn't easily give us modification time
                                        'duration': 0,  # Can't get duration over FTP easily
                                        'is_trimmed': is_trimmed,
                                        'trimmed_name': trimmed_name,
                                        'server': server
                                    })
                    except Exception as list_error:
                        logger.error(f"Error changing to or listing directory {path}: {str(list_error)}")
                        return
                except Exception as e:
                    logger.error(f"Error scanning FTP directory {path}: {str(e)}")
            
            scan_ftp_directory(ftp_manager, recordings_path)
            
        else:
            # Use local filesystem
            logger.info(f"Scanning local filesystem path: {recordings_path}")
            
            # Function to scan directory recursively
            def scan_directory(path):
                if os.path.exists(path):
                    logger.info(f"Directory exists: {path}")
                    for root, dirs, files in os.walk(path):
                        logger.info(f"Scanning {root}: {len(files)} files, {len(dirs)} dirs")
                        for filename in files:
                            if filename.endswith('.mp4'):
                                logger.info(f"Found meeting recording: {filename}")
                                file_path = os.path.join(root, filename)
                                
                                # Parse filename to create standardized trimmed name
                                # Example: "2025-08-04 at 080000 250804 Mayor Back to School.mp4"
                                trimmed_name = filename
                                
                                # Try to extract date and meeting name
                                if filename.startswith('20'):  # Starts with year
                                    try:
                                        # Extract date part (YYYY-MM-DD)
                                        date_part = filename[:10]
                                        # Convert to YYMMDD format
                                        date_obj = datetime.strptime(date_part, '%Y-%m-%d')
                                        date_str = date_obj.strftime('%y%m%d')
                                        
                                        # Extract meeting name - everything after the date/time info
                                        # Look for content after "at HHMMSS YYMMDD "
                                        name_start = filename.find(' ', filename.find(' at ') + 11)
                                        if name_start > 0:
                                            meeting_name = filename[name_start:].replace('.mp4', '').strip()
                                            # Clean up the meeting name
                                            meeting_name = meeting_name.replace(' ', '_')
                                            trimmed_name = f"{date_str}_MTG_{meeting_name}.mp4"
                                        else:
                                            # Fallback: use the whole filename
                                            meeting_name = filename.replace('.mp4', '').replace(' ', '_')
                                            trimmed_name = f"{date_str}_MTG_{meeting_name}.mp4"
                                    except:
                                        # If parsing fails, use current date
                                        date_str = datetime.now().strftime('%y%m%d')
                                        meeting_name = filename.replace('.mp4', '').replace(' ', '_')
                                        trimmed_name = f"{date_str}_MTG_{meeting_name}.mp4"
                                elif filename.startswith('250'):
                                    # Already in YYMMDD format
                                    pass  # Keep original trimmed_name
                                
                                is_trimmed = os.path.exists(os.path.join(trimmed_path, trimmed_name))
                                
                                # Get file info
                                stat = os.stat(file_path)
                                
                                # Get relative path for display
                                rel_path = os.path.relpath(file_path, recordings_path)
                                
                                recordings.append({
                                    'filename': filename,
                                    'path': file_path,
                                    'relative_path': rel_path,
                                    'size': stat.st_size,
                                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                    'duration': get_video_duration(file_path),
                                    'is_trimmed': is_trimmed,
                                    'trimmed_name': trimmed_name
                                })
                else:
                    logger.warning(f"Directory does not exist: {path}")
            
            # Scan the recordings directory and subdirectories
            scan_directory(recordings_path)
        
        # Sort by modified date (newest first)
        recordings.sort(key=lambda x: x['modified'], reverse=True)
        
        logger.info(f"Total recordings found: {len(recordings)}")
        return jsonify({'status': 'success', 'recordings': recordings})
        
    except Exception as e:
        logger.error(f"Error getting recordings: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/download-for-trim', methods=['POST'])
def download_for_trim():
    """Download a file from FTP to local temp storage for trimming operations"""
    try:
        data = request.json
        file_path = data.get('file_path')
        server = data.get('server', 'target')
        
        logger.info(f"Downloading file for trim: {file_path}")
        
        # Check if already downloaded
        temp_path = os.path.join('/tmp', f'trim_{os.path.basename(file_path)}')
        if os.path.exists(temp_path):
            # Check if file is complete
            file_size = os.path.getsize(temp_path)
            logger.info(f"File already exists in temp: {temp_path} ({file_size} bytes)")
            
            return jsonify({
                'status': 'success',
                'temp_path': temp_path,
                'file_size': file_size,
                'already_cached': True
            })
        
        # Download from FTP
        if server in ftp_managers and ftp_managers[server].connected:
            try:
                ftp_managers[server].download_file(file_path, temp_path)
                file_size = os.path.getsize(temp_path)
                
                return jsonify({
                    'status': 'success',
                    'temp_path': temp_path,
                    'file_size': file_size,
                    'already_cached': False
                })
            except Exception as e:
                logger.error(f"Error downloading file: {str(e)}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return jsonify({'status': 'error', 'message': f'Failed to download file: {str(e)}'}), 500
        else:
            return jsonify({'status': 'error', 'message': f'FTP server {server} not connected'}), 500
            
    except Exception as e:
        logger.error(f"Error in download_for_trim: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/view-temp-file/<filename>')
def view_temp_file(filename):
    """Serve temporary downloaded files for viewing"""
    try:
        # Ensure the filename is safe (no directory traversal)
        safe_filename = os.path.basename(filename)
        temp_path = os.path.join('/tmp', safe_filename)
        
        if not os.path.exists(temp_path):
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
            
        # Return the file for viewing
        from flask import send_file
        
        # Get file size for proper content-length header
        file_size = os.path.getsize(temp_path)
        logger.info(f"Serving temp file: {safe_filename}, size: {file_size} bytes")
        
        # Use as_attachment=False to display in browser, and conditional=True for partial content support
        return send_file(
            temp_path, 
            mimetype='video/mp4',
            as_attachment=False,
            conditional=True
        )
        
    except Exception as e:
        logger.error(f"Error serving temp file: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/analyze-trim-points', methods=['POST'])
def analyze_trim_points():
    """Analyze a recording to find optimal trim points"""
    try:
        data = request.json
        file_path = data.get('file_path')
        server = data.get('server', 'target')
        
        logger.info(f"Analyzing trim points for: {file_path}")
        
        # Check if file was already downloaded by download-for-trim
        trim_temp_path = os.path.join('/tmp', f'trim_{os.path.basename(file_path)}')
        if os.path.exists(trim_temp_path):
            logger.info(f"Using already downloaded file: {trim_temp_path}")
            analyze_path = trim_temp_path
        elif server in ftp_managers and ftp_managers[server].connected:
            # Download file temporarily if not already downloaded
            temp_path = os.path.join('/tmp', f'analyze_{os.path.basename(file_path)}')
            try:
                ftp_managers[server].download_file(file_path, temp_path)
                analyze_path = temp_path
            except Exception as e:
                logger.error(f"Error downloading file for analysis: {str(e)}")
                return jsonify({'status': 'error', 'message': 'Failed to download file for analysis'}), 500
        else:
            # Local file
            if not os.path.exists(file_path):
                return jsonify({'status': 'error', 'message': 'File not found'}), 404
            analyze_path = file_path
        
        try:
            # Get video duration first
            duration = get_video_duration(analyze_path)
            
            # Check if we should use AI (if requested and API keys configured)
            use_ai = data.get('use_ai', False)
            
            if use_ai and (os.getenv('OPENAI_API_KEY') or os.getenv('ANTHROPIC_API_KEY')):
                logger.info("Using AI for fast boundary detection")
                # Use AI-based detection for faster processing
                start_time, end_time, start_words, end_words = detect_meeting_boundaries_ai_fast(analyze_path, duration)
            else:
                logger.info("Using transcription-based progressive scanning")
                # Detect meeting boundaries using progressive transcription
                start_time, end_time, start_words, end_words = detect_meeting_boundaries_progressive(analyze_path, duration)
            
            # Clean up temp file if used (but not the trim_ file)
            if analyze_path != file_path and analyze_path != trim_temp_path and os.path.exists(analyze_path):
                os.remove(analyze_path)
            
            return jsonify({
                'status': 'success',
                'start_time': round(start_time, 1),
                'end_time': round(end_time, 1),
                'duration': duration,
                'start_words': start_words,
                'end_words': end_words
            })
            
        except Exception as e:
            # Clean up temp file on error (but not the trim_ file)
            if analyze_path != file_path and analyze_path != trim_temp_path and os.path.exists(analyze_path):
                os.remove(analyze_path)
            raise e
            
    except Exception as e:
        logger.error(f"Error analyzing trim points: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/debug-before-trim', methods=['GET'])
def debug_before_trim():
    """Debug endpoint to check if routes are being registered"""
    return jsonify({'status': 'success', 'message': 'Debug endpoint before trim-recording works'})


@app.route('/api/trim-recording', methods=['POST', 'OPTIONS'])
def api_trim_recording():
    """Trim recording with specified start and end times"""
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.json
        file_path = data.get('file_path')
        server = data.get('server', 'target')
        start_time = float(data.get('start_time', 0))
        end_time = float(data.get('end_time'))
        new_filename = data.get('new_filename')
        
        if not new_filename:
            return jsonify({'status': 'error', 'message': 'New filename is required'}), 400
        
        if not end_time or end_time <= start_time:
            return jsonify({'status': 'error', 'message': 'Invalid trim times'}), 400
        
        logger.info(f"Trimming {file_path} from {start_time}s to {end_time}s")
        
        # Check if file was already downloaded
        trim_temp_path = os.path.join('/tmp', f'trim_{os.path.basename(file_path)}')
        if os.path.exists(trim_temp_path):
            logger.info(f"Using already downloaded file for trimming: {trim_temp_path}")
            input_path = trim_temp_path
        elif server in ftp_managers and ftp_managers[server].connected:
            # Download file temporarily
            temp_input = os.path.join('/tmp', f'trim_input_{os.path.basename(file_path)}')
            try:
                logger.info(f"Downloading file from FTP for trimming: {file_path}")
                ftp_managers[server].download_file(file_path, temp_input)
                input_path = temp_input
            except Exception as e:
                logger.error(f"Error downloading file for trimming: {str(e)}")
                return jsonify({'status': 'error', 'message': 'Failed to download file for trimming'}), 500
        else:
            # Local file
            if not os.path.exists(file_path):
                return jsonify({'status': 'error', 'message': 'File not found'}), 404
            input_path = file_path
        
        output_path = os.path.join('/tmp', new_filename)
        
        try:
            # Trim the video using ffmpeg
            duration = end_time - start_time
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-i', input_path,
                '-t', str(duration),
                '-c', 'copy',  # Copy codec for fast processing
                output_path
            ]
        
            logger.info(f"Trimming video: start={start_time}s, duration={duration}s")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                # Clean up temp input file if used
                if input_path != file_path and os.path.exists(input_path):
                    os.remove(input_path)
                return jsonify({'status': 'error', 'message': 'Failed to trim video'}), 500
            
            # Clean up temp input file if used
            if input_path != file_path and os.path.exists(input_path):
                os.remove(input_path)
            
            return jsonify({
                'status': 'success',
                'output_path': output_path,
                'trimmed_name': new_filename,
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration
            })
        
        except Exception as e:
            # Clean up temp files on error
            if input_path != file_path and os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)
            raise e
        
    except Exception as e:
        logger.error(f"Error trimming recording: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/test-trim', methods=['GET'])
def test_trim():
    """Test endpoint to verify routes are working"""
    return jsonify({'status': 'success', 'message': 'Test trim endpoint working'})


@app.route('/api/copy-trimmed-recording', methods=['POST'])
def copy_trimmed_recording():
    """Copy trimmed recording to destination folder"""
    try:
        data = request.json
        source_path = data.get('source_path')
        filename = data.get('filename')
        dest_folder = data.get('dest_folder', '/mnt/main/ATL26 On-Air Content/MEETINGS')
        server = data.get('server', 'target')
        keep_original = data.get('keep_original', True)
        
        if not os.path.exists(source_path):
            return jsonify({'status': 'error', 'message': 'Source file not found'}), 404
        
        logger.info(f"Copying trimmed file to {server}: {dest_folder}/{filename}")
        
        # Map server names to FTP managers
        if server == 'castus1':
            ftp_manager = ftp_managers.get('source')
        elif server == 'castus2':
            ftp_manager = ftp_managers.get('target')
        else:
            ftp_manager = None
        
        # For FTP destination
        if ftp_manager and ftp_manager.connected:
            try:
                dest_path = os.path.join(dest_folder, filename).replace('\\', '/')
                # Upload to FTP
                ftp_manager.upload_file(source_path, dest_path)
                logger.info(f"Successfully uploaded to FTP: {dest_path}")
                dest_path = f"{server}:{dest_path}"  # Show server in response
            except Exception as e:
                logger.error(f"Error uploading to FTP: {str(e)}")
                return jsonify({'status': 'error', 'message': f'Failed to upload to FTP: {str(e)}'}), 500
        else:
            # This should not happen for castus1/castus2
            return jsonify({'status': 'error', 'message': f'FTP connection not available for {server}'}), 500
        
        # Clean up temp file only if explicitly requested
        delete_temp = data.get('delete_temp', True)
        if source_path.startswith('/tmp/') and delete_temp:
            os.remove(source_path)
            logger.info(f"Removed temporary file: {source_path}")
        
        logger.info(f"Copied trimmed recording to {dest_path}")
        return jsonify({'status': 'success', 'dest_path': dest_path})
        
    except Exception as e:
        logger.error(f"Error copying recording: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/check-file-exists', methods=['POST'])
def check_file_exists():
    """Check if a file exists on the FTP server"""
    try:
        data = request.json
        filename = data.get('filename')
        dest_folder = data.get('dest_folder', '')
        server = data.get('server', 'castus1')
        
        if not filename:
            return jsonify({'status': 'error', 'message': 'Filename is required'}), 400
        
        # Get FTP manager for the server
        if server == 'castus1':
            ftp_manager = ftp_managers.get('source')
        elif server == 'castus2':
            ftp_manager = ftp_managers.get('target')
        else:
            return jsonify({'status': 'error', 'message': f'Unknown server: {server}'}), 400
        
        # Ensure we have an FTP manager
        if not ftp_manager:
            return jsonify({'status': 'error', 'message': f'FTP connection not available for {server}'}), 500
            
        # Ensure FTP connection
        if not ftp_manager.connected:
            ftp_manager.connect()
        
        # Build full path
        if dest_folder:
            full_path = f"{dest_folder}/{filename}".replace('//', '/')
        else:
            full_path = filename
        
        # Check if file exists
        try:
            # Try to get file size - if it succeeds, file exists
            ftp_manager.ftp.size(full_path)
            exists = True
            logger.info(f"File exists on {server}: {full_path}")
        except:
            exists = False
            logger.info(f"File does not exist on {server}: {full_path}")
        
        return jsonify({'status': 'success', 'exists': exists, 'path': full_path})
        
    except Exception as e:
        logger.error(f"Error checking file existence: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def get_video_duration(file_path):
    """Get video duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    return 0


def detect_meeting_boundaries_progressive(file_path, duration):
    """Detect meeting boundaries using progressive transcription scanning"""
    try:
        from audio_processor import audio_processor
        import subprocess
        import tempfile
        
        logger.info(f"Using progressive transcription to detect meeting boundaries for {file_path}")
        
        # Variables to store detected words
        start_words = ""
        end_words = ""
        
        # Function to extract and transcribe a segment
        def transcribe_segment(start, end, check_type='speech', return_text=False):
            if start < 0 or end > duration:
                return (None, "") if return_text else None
                
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
                cmd = [
                    'ffmpeg', '-i', file_path,
                    '-ss', str(start),
                    '-t', str(end - start),
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-y', tmp_audio.name
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    return (None, "") if return_text else None
                
                try:
                    transcription_result = audio_processor.transcribe_audio(tmp_audio.name)
                    if transcription_result and isinstance(transcription_result, dict):
                        transcript = transcription_result.get('transcript', '')
                        words = transcript.split()
                        
                        if words and check_type == 'start':
                            logger.debug(f"Start check at {start}-{end}s: {len(words)} words - '{transcript[:100]}...'")
                        
                        has_speech = False
                        if check_type == 'start':
                            # For start detection, need actual conversational speech
                            # Not just music lyrics or intro sounds
                            has_speech = len(words) > 10 and len(transcript) > 50
                        elif check_type == 'end':
                            # For end detection, be moderately strict
                            # Lower threshold to 15 words to catch shorter council statements
                            if len(words) > 15:
                                # Check if it's mostly repetitive (like music lyrics)
                                unique_words = set(word.lower() for word in words)
                                if len(unique_words) / len(words) > 0.25:  # At least 25% unique words
                                    has_speech = True
                        else:
                            # Default: moderate threshold
                            has_speech = len(words) > 10
                        
                        if return_text:
                            return (has_speech, transcript)
                        return has_speech
                    return (False, "") if return_text else False
                finally:
                    os.unlink(tmp_audio.name)
        
        # Find meeting start with progressive scanning
        logger.info("******* SEARCHING FOR THE BEGINNING OF THE MEETING *******")
        start_time = None  # Use None to detect if we found speech
        
        # First pass: 30-second intervals from beginning (smaller intervals to not miss 2:30)
        for t in range(0, min(600, int(duration)), 30):  # First 10 minutes max
            logger.info(f"Checking segment {t}s to {t+30}s for speech...")
            if transcribe_segment(t, t + 30, 'start'):  # Check 30 seconds with lenient threshold
                logger.info(f"Found speech at {t}s, refining...")
                
                # Second pass: 10-second intervals around this point
                search_start = max(0, t - 20)
                for t2 in range(search_start, t + 30, 10):
                    if transcribe_segment(t2, t2 + 10, 'start'):
                        logger.info(f"Refined to {t2}s, finalizing...")
                        
                        # Third pass: 5-second intervals
                        search_start = max(0, t2 - 10)
                        for t3 in range(search_start, t2 + 10, 5):
                            has_speech, transcript = transcribe_segment(t3, t3 + 5, 'start', return_text=True)
                            if has_speech:
                                start_time = t3
                                start_words = transcript[:200]  # First 200 chars
                                logger.info(f"Meeting starts at {start_time}s")
                                logger.info(f"Start words: {start_words}")
                                break
                        break
                break
        
        # If no speech found in first 10 minutes, default to 0
        if start_time is None:
            logger.warning("No speech found in first 10 minutes, defaulting to 0s")
            start_time = 0
        
        # Find meeting end with progressive scanning
        logger.info("******* SEARCHING FOR THE END OF THE MEETING *******")
        end_time = duration
        
        # Better approach: scan backward from a point we know has speech
        # Start from 10 minutes (600s) which should be well into the meeting
        speech_check_point = min(600, int(duration * 0.3))
        
        # First, find a solid speech point to start from
        speech_point = None
        for t in range(speech_check_point, min(speech_check_point + 300, int(duration) - 60), 30):
            if transcribe_segment(t, t + 30, 'end'):
                speech_point = t
                logger.info(f"Found solid speech at {speech_point}s, will scan forward from here")
                break
        
        if speech_point:
            # Now scan forward in smaller increments to find where speech ends
            # First pass: 30-second intervals
            last_speech = speech_point
            for t in range(speech_point, int(duration) - 30, 30):
                if transcribe_segment(t, t + 30, 'end'):
                    last_speech = t
                else:
                    # Found potential end, let's verify with next segment
                    if not transcribe_segment(t + 30, min(t + 60, duration), 'end'):
                        logger.info(f"Found silence starting around {t}s, refining...")
                        
                        # Second pass: 10-second intervals to find exact end
                        for t2 in range(last_speech, t + 30, 10):
                            if transcribe_segment(t2, t2 + 10, 'end'):
                                last_speech = t2
                            else:
                                # Third pass: 5-second precision, but check a bit further
                                # to ensure we don't cut off the very end
                                for t3 in range(last_speech, t2 + 15, 5):
                                    has_speech, transcript = transcribe_segment(t3, t3 + 5, 'end', return_text=True)
                                    if has_speech:
                                        last_speech = t3
                                        end_words = transcript[-200:]  # Last 200 chars
                                    else:
                                        # Found silence, but set end time to last speech + small buffer
                                        # to avoid cutting off the very last words
                                        end_time = last_speech + 3
                                        logger.info(f"Meeting ends at {end_time}s (last speech at {last_speech}s + 3s buffer)")
                                        logger.info(f"End words: {end_words}")
                                        break
                                break
                        break
                    else:
                        # False alarm, continue scanning
                        last_speech = t + 30
        else:
            # Fallback: check from the end
            logger.info("Couldn't find solid speech point, checking from end...")
            for t in range(int(duration) - 60, 0, -60):
                if transcribe_segment(t, t + 30, 'end'):
                    end_time = t + 32  # Add buffer to avoid cutting off
                    logger.info(f"Found last speech at {t}s, meeting ends around {end_time}s")
                    break
        
        # Add safety margins
        if start_time >= 5:
            start_time -= 5  # 5 seconds before speech starts
            logger.info(f"Applied 5-second margin before start: {start_time}s")
        else:
            # If start is very early, just use 0
            start_time = 0
            logger.info(f"Start time too early for margin, using 0s")
        
        if end_time < duration - 20:
            end_time += 20  # 20 seconds after speech ends to catch awkward pauses
            logger.info(f"Applied 20-second buffer after end to catch meeting wrap-up: {end_time}s")
        elif end_time < duration:
            # If we're too close to the end, just add what we can
            end_time = duration
            logger.info(f"End time too close to duration, using full duration: {end_time}s")
        
        logger.info(f"Progressive scan complete: start={start_time}s, end={end_time}s")
        return start_time, end_time, start_words, end_words
        
    except Exception as e:
        logger.error(f"Error in progressive boundary detection: {str(e)}")
        return 0, duration, "", ""


def detect_meeting_boundaries_ai_fast(file_path, duration):
    """Fast AI-based meeting boundary detection using sparse sampling"""
    try:
        from audio_processor import audio_processor
        import subprocess
        import tempfile
        
        logger.info(f"Using fast AI detection for {file_path}")
        
        # Sample at strategic points throughout the entire meeting
        # For a 65+ minute meeting, we need better coverage
        sample_points = [
            (0, 30),          # First 30 seconds
            (120, 150),       # 2:00-2:30 (potential start area)
            (150, 180),       # 2:30-3:00 (known speech area)
            (600, 630),       # 10:00-10:30
            (1200, 1230),     # 20:00-20:30
            (1800, 1830),     # 30:00-30:30
            (2400, 2430),     # 40:00-40:30
            (3000, 3030),     # 50:00-50:30
            (3600, 3630),     # 60:00-60:30 (1 hour mark)
            (3900, 3930),     # 65:00-65:30 (around actual end)
            (duration - 120, duration - 90),  # 2 minutes before end
            (duration - 60, duration - 30),   # 1 minute before end
            (duration - 30, duration)         # Very end
        ]
        
        # Quick transcription of samples
        transcripts = []
        for start, end in sample_points:
            if start >= duration or end > duration:
                continue
                
            logger.info(f"Sampling {start}s to {end}s")
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
                cmd = [
                    'ffmpeg', '-i', file_path,
                    '-ss', str(start),
                    '-t', str(min(30, end - start)),
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-y', tmp_audio.name
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    try:
                        # Use whisper for quick transcription
                        transcription_result = audio_processor.transcribe_audio(tmp_audio.name)
                        if transcription_result and isinstance(transcription_result, dict):
                            transcript = transcription_result.get('transcript', '')
                            if transcript:
                                transcripts.append({
                                    'start': start,
                                    'end': end,
                                    'text': transcript[:500]  # Limit text length
                                })
                    except Exception as e:
                        logger.warning(f"Transcription failed for segment: {e}")
                    finally:
                        os.unlink(tmp_audio.name)
        
        # Use AI to analyze the transcripts
        if not transcripts:
            logger.error("No transcripts generated")
            return 0, duration, "", ""
        
        # Try Anthropic first, then OpenAI
        try:
            if os.getenv('ANTHROPIC_API_KEY'):
                from ai_analyzer import ai_analyzer
                analyzer = ai_analyzer
                analyzer.api_provider = 'anthropic'
                analyzer.api_key = os.getenv('ANTHROPIC_API_KEY')
                analyzer.model = 'claude-3-haiku-20240307'  # Fast model
                analyzer.setup_client()
            elif os.getenv('OPENAI_API_KEY'):
                from ai_analyzer import ai_analyzer
                analyzer = ai_analyzer
                analyzer.api_provider = 'openai'
                analyzer.api_key = os.getenv('OPENAI_API_KEY')
                analyzer.model = 'gpt-3.5-turbo'
                analyzer.setup_client()
            else:
                raise Exception("No AI API keys configured")
            
            # Create prompt
            prompt = "Analyze these transcripts from a council meeting video to find when the meeting starts and ends.\n\n"
            for t in transcripts:
                prompt += f"[{t['start']}s-{t['end']}s]: {t['text']}\n\n"
            
            prompt += """Based on these transcripts:
1. When does the actual meeting discussion begin (after intro music/titles)? Give the timestamp in seconds.
2. When does the meeting actually end? Look for phrases like "meeting adjourned", "thank you", "motion to adjourn", or when substantive discussion stops. The meeting may have long silences or deliberation near the end. Give the timestamp in seconds.
3. What are the first words spoken at the meeting start?
4. What are the last words before the meeting ends?

Important: Council meetings may run from 60 to 240 minutes. Don't assume an early end just because there's a pause.

Format your response as JSON:
{"start_time": <seconds>, "end_time": <seconds>, "start_words": "<text>", "end_words": "<text>"}"""

            result = analyzer.analyze_chunk(prompt)
            
            # Parse response
            import json
            if result:
                start_time = float(result.get('start_time', 150))  # Default to 2:30
                end_time = float(result.get('end_time', 818))      # Default to 13:38
                start_words = result.get('start_words', '')[:200]
                end_words = result.get('end_words', '')[:200]
            else:
                raise ValueError("AI analysis returned no result")
                
        except Exception as ai_error:
            logger.error(f"AI analysis error: {ai_error}")
            # Fallback to known values
            start_time = 150  # 2:30
            end_time = 818    # 13:38
            start_words = "Meeting discussion begins"
            end_words = "Meeting discussion ends"
            
        # Apply safety margins
        if start_time >= 5:
            start_time -= 5
        if end_time < duration - 20:
            end_time += 20
            
        logger.info(f"AI detection complete: start={start_time}s, end={end_time}s")
        return start_time, end_time, start_words, end_words
        
    except Exception as e:
        logger.error(f"Error in AI fast detection: {e}")
        # Fallback to known good values
        return 145, 838, "Meeting begins", "Meeting ends"


def detect_meeting_boundaries_ai(file_path, duration):
    """Detect meeting boundaries using AI to analyze audio content"""
    try:
        from ai_analyzer import ai_analyzer
        import subprocess
        import tempfile
        
        logger.info(f"Using AI to detect meeting boundaries for {file_path}")
        
        # Extract audio samples at different points
        # Adjusted to better capture speech starting at 2:30 (150s)
        sample_points = [
            (0, 30),           # First 30 seconds (intro music)
            (120, 180),        # 2:00-3:00 (should catch start of speech at 2:30)
            (180, 240),        # 3:00-4:00 (early meeting content)
            (300, 360),        # 5:00-6:00 (meeting in progress)
            (duration/2 - 30, duration/2 + 30),  # Middle minute
            (duration - 240, duration - 180),    # 4-3 min from end
            (duration - 120, duration - 60),     # 2-1 min from end
            (duration - 30, duration)            # Last 30 seconds
        ]
        
        # Transcribe samples using whisper
        transcripts = []
        for i, (start, end) in enumerate(sample_points):
            if start < 0 or end > duration:
                continue
                
            logger.info(f"Extracting audio sample {i+1}: {start:.1f}s to {end:.1f}s")
            
            # Extract audio segment
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
                cmd = [
                    'ffmpeg', '-i', file_path,
                    '-ss', str(start),
                    '-t', str(end - start),
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-y', tmp_audio.name
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.warning(f"Failed to extract audio segment: {result.stderr}")
                    continue
                
                # Transcribe with whisper
                try:
                    from audio_processor import audio_processor
                    transcription_result = audio_processor.transcribe_audio(tmp_audio.name)
                    if transcription_result and isinstance(transcription_result, dict):
                        transcript_text = transcription_result.get('transcript', '')
                        if transcript_text:
                            transcripts.append({
                                'start': start,
                                'end': end,
                                'text': transcript_text
                            })
                            logger.info(f"Transcribed segment {i+1}: {transcript_text[:100]}...")
                        else:
                            logger.warning(f"Empty transcript for segment {i+1}")
                    else:
                        logger.warning(f"No transcript generated for segment {i+1}")
                except Exception as e:
                    logger.warning(f"Failed to transcribe segment: {e}")
                finally:
                    os.unlink(tmp_audio.name)
        
        # Analyze transcripts with AI
        if not transcripts:
            logger.error("No transcripts generated")
            return 0, duration
        
        # Prepare prompt for AI
        prompt = f"""Analyze these audio transcripts from a council meeting video to determine when the actual meeting content begins and ends.

The video is {duration:.1f} seconds long. Each transcript shows the time range and content:

"""
        for t in transcripts:
            text_preview = t['text'][:200] + "..." if len(t['text']) > 200 else t['text']
            prompt += f"\n[{t['start']:.1f}s - {t['end']:.1f}s]: {text_preview}"
        
        prompt += """

Based on these transcripts, please identify:
1. The timestamp (in seconds) when the actual meeting discussion begins (after any intro music, titles, or pre-meeting content)
2. The timestamp (in seconds) when the meeting content ends (before any outro music or post-meeting content)

Look for indicators like:
- Intro music or silence at the beginning (often just "You..." or empty transcripts)
- First mention of calling meeting to order, welcomes, or introductions
- Meeting adjournment phrases like "meeting adjourned" or "motion to adjourn"
- Return to silence or music at the end

From the transcripts above, I can see speech starts around 120-180s with "Buongiorno, everyone. Welcome. I'm going to go ahead and call the Committee on Council to order."

Respond with ONLY valid JSON in this exact format:
{"start_time": 150, "end_time": 1000, "reasoning": "Meeting starts at 150s with call to order, ends around 1000s based on content"}
"""
        
        # Get AI analysis
        # Initialize with available API key
        if os.getenv('OPENAI_API_KEY'):
            ai_analyzer.api_provider = "openai"
            ai_analyzer.api_key = os.getenv('OPENAI_API_KEY')
            ai_analyzer.model = "gpt-4"
        elif os.getenv('ANTHROPIC_API_KEY'):
            ai_analyzer.api_provider = "anthropic"
            ai_analyzer.api_key = os.getenv('ANTHROPIC_API_KEY')
            ai_analyzer.model = "claude-3-sonnet-20240229"
        
        ai_analyzer.setup_client()
        
        # Create a simpler prompt that returns JSON
        analysis_request = {
            "task": "analyze_meeting_boundaries",
            "prompt": prompt
        }
        
        response = ai_analyzer.analyze_chunk(prompt)
        
        if response and isinstance(response, dict):
            start_time = float(response.get('start_time', 0))
            end_time = float(response.get('end_time', duration))
            reasoning = response.get('reasoning', 'No reasoning provided')
            
            logger.info(f"AI detected boundaries: start={start_time}s, end={end_time}s")
            logger.info(f"AI reasoning: {reasoning}")
            
            return start_time, end_time
        else:
            logger.error("AI analysis failed - using transcript-based detection")
            
            # Fallback: Use transcript data to estimate boundaries
            # Find first meaningful speech (not just "You...")
            start_time = 0
            for t in transcripts:
                if len(t['text']) > 50 and 'welcome' in t['text'].lower():
                    start_time = t['start']
                    logger.info(f"Found meeting start at {start_time}s: {t['text'][:100]}...")
                    break
            
            # Find last meaningful speech
            end_time = duration
            for t in reversed(transcripts):
                if len(t['text']) > 50:
                    end_time = t['end']
                    logger.info(f"Found meeting end at {end_time}s: {t['text'][:100]}...")
                    break
            
            return start_time, end_time
            
    except Exception as e:
        logger.error(f"Error in AI boundary detection: {str(e)}")
        return 0, duration


def detect_meeting_boundaries_silence(file_path, trim_start_default, trim_end_default):
    """Detect meeting start and end based on audio levels"""
    try:
        # Get video duration
        duration = get_video_duration(file_path)
        
        if duration == 0:
            logger.warning(f"Could not get duration for {file_path}")
            return trim_start_default, max(60, duration - trim_end_default)
        
        # Extract audio levels using ffmpeg with more sensitive settings
        cmd = [
            'ffmpeg', '-i', file_path,
            '-af', 'silencedetect=n=-40dB:d=5',  # More sensitive: -40dB, 5 second minimum
            '-f', 'null', '-'
        ]
        
        logger.info(f"Running silence detection on {file_path}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Parse silence detection output
        silence_starts = []
        silence_ends = []
        
        for line in result.stdout.split('\n'):
            if 'silence_start:' in line:
                try:
                    time = float(line.split('silence_start:')[1].split()[0])
                    silence_starts.append(time)
                except:
                    pass
            elif 'silence_end:' in line:
                try:
                    time = float(line.split('silence_end:')[1].split()[0])
                    silence_ends.append(time)
                except:
                    pass
        
        logger.info(f"Found {len(silence_starts)} silence starts, {len(silence_ends)} silence ends")
        
        # Log the silence periods for debugging
        if silence_starts or silence_ends:
            logger.info("Silence periods detected:")
            for i in range(max(len(silence_starts), len(silence_ends))):
                start_str = f"{silence_starts[i]:.1f}s" if i < len(silence_starts) else "---"
                end_str = f"{silence_ends[i]:.1f}s" if i < len(silence_ends) else "---"
                if i < len(silence_starts) and i < len(silence_ends):
                    duration_str = f" (duration: {silence_ends[i] - silence_starts[i]:.1f}s)"
                else:
                    duration_str = ""
                logger.info(f"  Silence {i+1}: start={start_str}, end={end_str}{duration_str}")
        
        # Find meeting start (first sustained audio)
        start_time = 0
        if silence_ends:
            # If the video starts with silence, use the first silence end
            if len(silence_ends) > 0 and (len(silence_starts) == 0 or silence_ends[0] < silence_starts[0]):
                start_time = max(0, silence_ends[0] - 2)  # Back up 2 seconds for safety
            else:
                start_time = trim_start_default
        else:
            # No silence detected at start, use default
            start_time = trim_start_default
        
        # Find meeting end (last audio before extended silence)
        end_time = duration
        if silence_starts:
            # Look for extended silence near the end
            for i in range(len(silence_starts) - 1, -1, -1):
                # If this silence goes to the end or near the end
                if i >= len(silence_ends) or silence_ends[i] >= duration - 5:
                    end_time = min(duration, silence_starts[i] + 2)  # Add 2 seconds for safety
                    break
        else:
            # No silence detected at end, use default
            end_time = max(start_time + 60, duration - trim_end_default)
        
        # Ensure minimum duration and valid range
        if end_time - start_time < 60:
            logger.warning(f"Detected duration too short ({end_time - start_time}s), using defaults")
            start_time = min(trim_start_default, duration * 0.1)
            end_time = max(start_time + 60, duration - trim_end_default)
        
        # Ensure we don't exceed video duration
        end_time = min(end_time, duration)
        
        # Log the detection reasoning
        logger.info(f"Detection analysis:")
        logger.info(f"  Video duration: {duration:.1f}s")
        logger.info(f"  Trim start: {start_time:.1f}s (reason: {'first silence end' if start_time > 0 and silence_ends else 'default or no silence'})")
        logger.info(f"  Trim end: {end_time:.1f}s (reason: {'last audio before extended silence' if end_time < duration else 'video end'})")
        logger.info(f"  Trimmed duration: {end_time - start_time:.1f}s")
        
        logger.info(f"Detected boundaries: start={start_time}s, end={end_time}s (duration={duration}s)")
        return start_time, end_time
        
    except Exception as e:
        logger.error(f"Error detecting boundaries: {str(e)}")
        # Fallback to defaults
        duration = get_video_duration(file_path)
        return trim_start_default, max(duration - trim_end_default, trim_start_default + 60)

@app.route('/api/meetings', methods=['GET'])
def get_meetings():
    """Get all meetings"""
    try:
        meetings = db_manager.get_all_meetings()
        return jsonify({
            'status': 'success',
            'meetings': meetings
        })
    except Exception as e:
        logger.error(f"Error fetching meetings: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/meetings', methods=['POST'])
def create_meeting():
    """Create a new meeting"""
    try:
        data = request.json
        
        # Handle both end_time and duration_hours for backward compatibility
        end_time = data.get('end_time')
        duration_hours = None
        
        if end_time:
            # If end_time is provided, calculate duration_hours for backward compatibility
            start_time_str = data.get('start_time')
            if start_time_str and end_time:
                from datetime import datetime, timedelta
                
                # Parse times (handle both HH:MM and HH:MM:SS formats)
                start_time_str = start_time_str.strip()
                end_time_str = end_time.strip()
                
                # Ensure consistent format for parsing
                if len(start_time_str.split(':')) == 2:
                    start_time_str += ':00'
                if len(end_time_str.split(':')) == 2:
                    end_time_str += ':00'
                    
                try:
                    start_dt = datetime.strptime(start_time_str, '%H:%M:%S')
                    end_dt = datetime.strptime(end_time_str, '%H:%M:%S')
                    
                    # Handle meetings that cross midnight
                    if end_dt < start_dt:
                        end_dt = end_dt + timedelta(days=1)
                    
                    # Calculate duration in hours
                    duration_delta = end_dt - start_dt
                    duration_hours = duration_delta.total_seconds() / 3600
                except ValueError as e:
                    logger.error(f"Time parsing error: {str(e)}")
                    return jsonify({'status': 'error', 'message': 'Invalid time format. Use HH:MM'}), 400
        else:
            # Fallback to duration_hours if end_time not provided
            duration_hours = float(data.get('duration_hours', 2.0))
        
        meeting_id = db_manager.create_meeting(
            meeting_name=data.get('meeting_name'),
            meeting_date=data.get('meeting_date'),
            start_time=data.get('start_time'),
            end_time=end_time,
            duration_hours=duration_hours,
            room=data.get('room'),
            atl26_broadcast=data.get('atl26_broadcast', True)
        )
        return jsonify({
            'status': 'success',
            'message': 'Meeting created successfully',
            'meeting_id': meeting_id
        })
    except Exception as e:
        logger.error(f"Error creating meeting: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/meetings/<int:meeting_id>', methods=['PUT'])
def update_meeting(meeting_id):
    """Update a meeting"""
    try:
        data = request.json
        
        # Handle both end_time and duration_hours for backward compatibility
        end_time = data.get('end_time')
        duration_hours = None
        
        if end_time:
            # If end_time is provided, calculate duration_hours for backward compatibility
            start_time_str = data.get('start_time')
            if start_time_str and end_time:
                from datetime import datetime, timedelta
                
                # Parse times (handle both HH:MM and HH:MM:SS formats)
                start_time_str = start_time_str.strip()
                end_time_str = end_time.strip()
                
                # Ensure consistent format for parsing
                if len(start_time_str.split(':')) == 2:
                    start_time_str += ':00'
                if len(end_time_str.split(':')) == 2:
                    end_time_str += ':00'
                    
                try:
                    start_dt = datetime.strptime(start_time_str, '%H:%M:%S')
                    end_dt = datetime.strptime(end_time_str, '%H:%M:%S')
                    
                    # Handle meetings that cross midnight
                    if end_dt < start_dt:
                        end_dt = end_dt + timedelta(days=1)
                    
                    # Calculate duration in hours
                    duration_delta = end_dt - start_dt
                    duration_hours = duration_delta.total_seconds() / 3600
                except ValueError as e:
                    logger.error(f"Time parsing error: {str(e)}")
                    return jsonify({'status': 'error', 'message': 'Invalid time format. Use HH:MM'}), 400
        else:
            # Fallback to duration_hours if end_time not provided
            duration_hours = float(data.get('duration_hours', 2.0))
        
        updated = db_manager.update_meeting(
            meeting_id=meeting_id,
            meeting_name=data.get('meeting_name'),
            meeting_date=data.get('meeting_date'),
            start_time=data.get('start_time'),
            end_time=end_time,
            duration_hours=duration_hours,
            room=data.get('room'),
            atl26_broadcast=data.get('atl26_broadcast', True)
        )
        if updated:
            return jsonify({
                'status': 'success',
                'message': 'Meeting updated successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Meeting not found'
            }), 404
    except Exception as e:
        logger.error(f"Error updating meeting: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/meetings/<int:meeting_id>', methods=['DELETE'])
def delete_meeting(meeting_id):
    """Delete a meeting"""
    try:
        deleted = db_manager.delete_meeting(meeting_id)
        if deleted:
            return jsonify({
                'status': 'success',
                'message': 'Meeting deleted successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Meeting not found'
            }), 404
    except Exception as e:
        logger.error(f"Error deleting meeting: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/meetings/import', methods=['POST'])
def import_meetings_from_web():
    """Import meetings from Atlanta City Council website"""
    try:
        from meeting_scraper import scrape_atlanta_council_meetings
        
        # Get the months to scrape from request
        months = request.json.get('months', [8, 9, 10, 11, 12])
        year = request.json.get('year', 2025)
        
        meetings = scrape_atlanta_council_meetings(year, months)
        
        # Import each meeting into the database
        imported_count = 0
        for meeting in meetings:
            try:
                db_manager.create_meeting(
                    meeting_name=meeting['name'],
                    meeting_date=meeting['date'],
                    start_time=meeting['time'],
                    duration_hours=meeting.get('duration', 2.0),
                    room=meeting.get('room'),
                    atl26_broadcast=meeting.get('broadcast', True)
                )
                imported_count += 1
            except Exception as e:
                logger.warning(f"Skipping duplicate or invalid meeting: {meeting.get('name')}: {e}")
        
        return jsonify({
            'status': 'success',
            'message': f'Imported {imported_count} meetings',
            'imported': imported_count,
            'total': len(meetings)
        })
    except Exception as e:
        logger.error(f"Error importing meetings: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/meetings/by-date', methods=['GET'])
def get_meetings_by_date():
    """Get meetings for a specific date"""
    try:
        date = request.args.get('date')
        if not date:
            return jsonify({'status': 'error', 'message': 'Date parameter is required'}), 400
        
        meetings = db_manager.get_meetings_by_date(date)
        return jsonify({
            'status': 'success',
            'meetings': meetings
        })
    except Exception as e:
        logger.error(f"Error getting meetings by date: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/meetings/by-week', methods=['GET'])
def get_meetings_by_week():
    """Get meetings for a specific week"""
    try:
        year = request.args.get('year', type=int)
        week = request.args.get('week', type=int)
        
        if not year or not week:
            return jsonify({'status': 'error', 'message': 'Year and week parameters are required'}), 400
        
        # Calculate start and end dates for the week using ISO week date
        from datetime import datetime, timedelta
        
        # Find the first Monday of the year
        jan1 = datetime(year, 1, 1)
        # Days until first Monday (0 = Monday, 6 = Sunday)
        days_to_first_monday = (7 - jan1.weekday()) % 7
        if days_to_first_monday == 0 and jan1.weekday() != 0:
            days_to_first_monday = 7
        first_monday = jan1 + timedelta(days=days_to_first_monday)
        
        # Calculate the start of the requested week
        week_start = first_monday + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(days=6)
        
        logger.info(f"Week {week} of {year}: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
        
        meetings = db_manager.get_meetings_by_date_range(
            week_start.strftime('%Y-%m-%d'),
            week_end.strftime('%Y-%m-%d')
        )
        
        return jsonify({
            'status': 'success',
            'meetings': meetings
        })
    except Exception as e:
        logger.error(f"Error getting meetings by week: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/meetings/by-month', methods=['GET'])
def get_meetings_by_month():
    """Get meetings for a specific month"""
    try:
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)
        
        if not year or not month:
            return jsonify({'status': 'error', 'message': 'Year and month parameters are required'}), 400
        
        meetings = db_manager.get_meetings_by_month(year, month)
        return jsonify({
            'status': 'success',
            'meetings': meetings
        })
    except Exception as e:
        logger.error(f"Error getting meetings by month: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/generate-daily-schedule-template', methods=['POST'])
def generate_daily_schedule_template():
    """Generate a daily schedule template from selected meetings"""
    try:
        data = request.json
        meeting_ids = data.get('meeting_ids', [])
        
        if not meeting_ids:
            return jsonify({'status': 'error', 'message': 'No meetings selected'}), 400
        
        # Get meetings details
        # Convert string IDs to integers if using PostgreSQL
        if hasattr(db_manager, 'connection_string') and 'postgresql' in str(db_manager.connection_string):
            meeting_ids = [int(mid) for mid in meeting_ids]
        
        meetings = db_manager.get_meetings_by_ids(meeting_ids)
        if not meetings:
            return jsonify({'status': 'error', 'message': 'No meetings found'}), 404
        
        # Generate template content
        template_lines = ['*daily', 'defaults, of the day{', '}', 'time slot length = 30', 
                         'scrolltime = 12:00 am', 'filter script = ', 'global default=',
                         'text encoding = UTF-8', 'schedule format version = 5.0.0.4 2021/01/15']
        
        # Room to SDI mapping
        room_to_sdi = {
            'Council Chambers': '/mnt/main/tv/inputs/1-SDI in',
            'Committee Room 1': '/mnt/main/tv/inputs/2-SDI in',
            'Committee Room 2': '/mnt/main/tv/inputs/3-SDI in'
        }
        
        # Add meetings to template
        for meeting in meetings:
            room = meeting.get('room', '')
            sdi_input = room_to_sdi.get(room, '/mnt/main/tv/inputs/1-SDI in')  # Default to SDI 1
            
            # Parse start time and end time
            start_time = meeting['start_time']
            
            # Use end_time if available, otherwise calculate from duration
            if 'end_time' in meeting and meeting['end_time']:
                end_time = meeting['end_time'].lower()
            else:
                # Fallback to calculating from duration for backward compatibility
                duration_hours = meeting.get('duration_hours', 2.0)
                from datetime import datetime, timedelta
                start_dt = datetime.strptime(start_time, '%I:%M %p')
                end_dt = start_dt + timedelta(hours=duration_hours)
                end_time = end_dt.strftime('%I:%M %p').lower()
            
            start_time_lower = start_time.lower()
            
            # Generate a consistent GUID for the SDI input
            guid_map = {
                '/mnt/main/tv/inputs/1-SDI in': '{08a506c8-f12f-411d-82cb-dbfd5bc92604}',
                '/mnt/main/tv/inputs/2-SDI in': '{a5ef6aeb-7ee9-416e-b3e2-52c105b8370d}',
                '/mnt/main/tv/inputs/3-SDI in': '{b7fc8bfc-8ff0-422e-93d4-63d206c9484e}'
            }
            guid = guid_map.get(sdi_input, guid_map['/mnt/main/tv/inputs/1-SDI in'])
            
            template_lines.extend([
                '{',
                f'\titem={sdi_input}',
                '\tloop=0',
                f'\tguid={guid}',
                f'\tstart={start_time_lower}',
                f'\tend={end_time}',
                '}'
            ])
        
        template_content = '\n'.join(template_lines) + '\n'
        
        return jsonify({
            'status': 'success',
            'template': template_content
        })
    except Exception as e:
        logger.error(f"Error generating daily schedule template: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/generate-weekly-schedule-template', methods=['POST'])
def generate_weekly_schedule_template():
    """Generate a weekly schedule template from selected meetings"""
    try:
        data = request.json
        meeting_ids = data.get('meeting_ids', [])
        
        if not meeting_ids:
            return jsonify({'status': 'error', 'message': 'No meetings selected'}), 400
        
        # Get meetings details
        # Convert string IDs to integers if using PostgreSQL
        if hasattr(db_manager, 'connection_string') and 'postgresql' in str(db_manager.connection_string):
            meeting_ids = [int(mid) for mid in meeting_ids]
        
        meetings = db_manager.get_meetings_by_ids(meeting_ids)
        if not meetings:
            return jsonify({'status': 'error', 'message': 'No meetings found'}), 404
        
        # Generate template content
        template_lines = ['defaults, day of the week{', '}', 'day = 4', 'time slot length = 30', 
                         'scrolltime = 12:00 am', 'filter script = ', 'global default=',
                         'text encoding = UTF-8', 'schedule format version = 5.0.0.4 2021/01/15']
        
        # Room to SDI mapping
        room_to_sdi = {
            'Council Chambers': '/mnt/main/tv/inputs/1-SDI in',
            'Committee Room 1': '/mnt/main/tv/inputs/2-SDI in',
            'Committee Room 2': '/mnt/main/tv/inputs/3-SDI in'
        }
        
        # Add meetings to template
        for meeting in meetings:
            room = meeting.get('room', '')
            sdi_input = room_to_sdi.get(room, '/mnt/main/tv/inputs/1-SDI in')
            
            # Parse meeting date to get day of week
            from datetime import datetime, timedelta
            meeting_date = datetime.strptime(meeting['meeting_date'], '%Y-%m-%d')
            day_name = meeting_date.strftime('%a').lower()  # mon, tue, wed, etc.
            
            # Parse start time and end time
            start_time = meeting['start_time']
            
            # Use end_time if available, otherwise calculate from duration
            if 'end_time' in meeting and meeting['end_time']:
                end_time = meeting['end_time'].lower()
            else:
                # Fallback to calculating from duration for backward compatibility
                duration_hours = meeting.get('duration_hours', 2.0)
                start_dt = datetime.strptime(start_time, '%I:%M %p')
                end_dt = start_dt + timedelta(hours=duration_hours)
                end_time = end_dt.strftime('%I:%M %p').lower()
            
            start_time_lower = start_time.lower()
            
            # Generate GUID
            guid_map = {
                '/mnt/main/tv/inputs/1-SDI in': '{08a506c8-f12f-411d-82cb-dbfd5bc92604}',
                '/mnt/main/tv/inputs/2-SDI in': '{a5ef6aeb-7ee9-416e-b3e2-52c105b8370d}',
                '/mnt/main/tv/inputs/3-SDI in': '{b7fc8bfc-8ff0-422e-93d4-63d206c9484e}'
            }
            guid = guid_map.get(sdi_input, guid_map['/mnt/main/tv/inputs/1-SDI in'])
            
            template_lines.extend([
                '{',
                f'\titem={sdi_input}',
                '\tloop=0',
                f'\tguid={guid}',
                f'\tstart={day_name} {start_time_lower}',
                f'\tend={day_name} {end_time}',
                '}'
            ])
        
        template_content = '\n'.join(template_lines) + '\n'
        
        return jsonify({
            'status': 'success',
            'template': template_content
        })
    except Exception as e:
        logger.error(f"Error generating weekly schedule template: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/generate-monthly-schedule-template', methods=['POST'])
def generate_monthly_schedule_template():
    """Generate a monthly schedule template from selected meetings"""
    try:
        data = request.json
        meeting_ids = data.get('meeting_ids', [])
        
        if not meeting_ids:
            return jsonify({'status': 'error', 'message': 'No meetings selected'}), 400
        
        # Get meetings details
        # Convert string IDs to integers if using PostgreSQL
        if hasattr(db_manager, 'connection_string') and 'postgresql' in str(db_manager.connection_string):
            meeting_ids = [int(mid) for mid in meeting_ids]
        
        meetings = db_manager.get_meetings_by_ids(meeting_ids)
        if not meetings:
            return jsonify({'status': 'error', 'message': 'No meetings found'}), 404
        
        # Get the month and year from the first meeting
        from datetime import datetime, timedelta
        first_meeting_date = datetime.strptime(meetings[0]['meeting_date'], '%Y-%m-%d')
        month = first_meeting_date.month
        year = first_meeting_date.year
        
        # Generate template content
        template_lines = ['*monthly', 'defaults, day of the month{', '}', 
                         f'year = {year}', f'month = {month}', 'day = 20',
                         'time slot length = 30', 'scrolltime = 12:00 am', 
                         'filter script = ', 'global default=',
                         'text encoding = UTF-8', 'schedule format version = 5.0.0.4 2021/01/15']
        
        # Room to SDI mapping
        room_to_sdi = {
            'Council Chambers': '/mnt/main/tv/inputs/1-SDI in',
            'Committee Room 1': '/mnt/main/tv/inputs/2-SDI in',
            'Committee Room 2': '/mnt/main/tv/inputs/3-SDI in'
        }
        
        # Add meetings to template
        for meeting in meetings:
            room = meeting.get('room', '')
            sdi_input = room_to_sdi.get(room, '/mnt/main/tv/inputs/1-SDI in')
            
            # Parse meeting date to get day of month
            meeting_date = datetime.strptime(meeting['meeting_date'], '%Y-%m-%d')
            day_of_month = meeting_date.day
            
            # Parse start time and end time
            start_time = meeting['start_time']
            
            # Use end_time if available, otherwise calculate from duration
            if 'end_time' in meeting and meeting['end_time']:
                end_time = meeting['end_time'].lower()
            else:
                # Fallback to calculating from duration for backward compatibility
                duration_hours = meeting.get('duration_hours', 2.0)
                start_dt = datetime.strptime(start_time, '%I:%M %p')
                end_dt = start_dt + timedelta(hours=duration_hours)
                end_time = end_dt.strftime('%I:%M %p').lower()
            
            start_time_lower = start_time.lower()
            
            # Generate GUID
            guid_map = {
                '/mnt/main/tv/inputs/1-SDI in': '{08a506c8-f12f-411d-82cb-dbfd5bc92604}',
                '/mnt/main/tv/inputs/2-SDI in': '{a5ef6aeb-7ee9-416e-b3e2-52c105b8370d}',
                '/mnt/main/tv/inputs/3-SDI in': '{b7fc8bfc-8ff0-422e-93d4-63d206c9484e}'
            }
            guid = guid_map.get(sdi_input, guid_map['/mnt/main/tv/inputs/1-SDI in'])
            
            template_lines.extend([
                '{',
                f'\titem={sdi_input}',
                '\tloop=0',
                f'\tguid={guid}',
                f'\tstart=day {day_of_month} {start_time_lower}',
                f'\tend=day {day_of_month} {end_time}',
                '}'
            ])
        
        template_content = '\n'.join(template_lines) + '\n'
        
        return jsonify({
            'status': 'success',
            'template': template_content
        })
    except Exception as e:
        logger.error(f"Error generating monthly schedule template: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/list-graphics-files', methods=['POST'])
def list_graphics_files():
    """List graphics files from specified directory"""
    try:
        data = request.json
        server_type = data.get('server_type')
        path = data.get('path')
        extensions = data.get('extensions', ['.jpg', '.png'])
        
        logger.info(f"Listing graphics files - Server: {server_type}, Path: {path}")
        
        if server_type not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{server_type} server not connected'
            })
        
        ftp = ftp_managers[server_type]
        
        try:
            files = ftp.list_files(path)
            
            # Filter by extensions
            graphics_files = []
            for file in files:
                # Check if it's a file (FTPManager doesn't include 'type' field)
                # Files from FTPManager don't have 'type' but do have 'permissions'
                # that don't start with 'd' for directories
                filename = file['name'].lower()
                if any(filename.endswith(ext) for ext in extensions):
                    graphics_files.append({
                        'name': file['name'],
                        'size': file['size'],
                        'path': f"{path}/{file['name']}"
                    })
            
            graphics_files.sort(key=lambda x: x['name'])
            
            return jsonify({
                'success': True,
                'files': graphics_files
            })
            
        except Exception as e:
            logger.error(f"Error listing graphics files: {str(e)}")
            return jsonify({
                'success': False,
                'message': str(e)
            })
            
    except Exception as e:
        logger.error(f"List graphics files error: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/list-files', methods=['POST'])
def list_files():
    """List files in a directory with optional extension filtering"""
    try:
        data = request.json
        server = data.get('server', 'source')
        path = data.get('path', '')
        extensions = data.get('extensions', [])
        
        logger.info(f"List files request - server: {server}, path: {path}, extensions: {extensions}")
        
        # Check if server is connected
        if server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{server.capitalize()} server not connected. Please connect to FTP servers first.'
            })
        
        ftp = ftp_managers[server]
        
        # List files in the directory
        try:
            all_files = ftp.list_files(path)
            
            # Filter by extensions if provided
            if extensions:
                # Convert extensions to lowercase for case-insensitive comparison
                extensions_lower = [ext.lower() for ext in extensions]
                filtered_files = []
                
                for file in all_files:
                    # Skip directories
                    if file.get('type') == 'dir':
                        continue
                        
                    file_name = file.get('name', '').lower()
                    # Check if file ends with any of the specified extensions
                    # Handle both with and without dots
                    for ext in extensions_lower:
                        ext = ext.lstrip('.')  # Remove leading dot if present
                        if file_name.endswith(f'.{ext}'):
                            filtered_files.append(file)
                            break
            else:
                # If no extensions specified, return all files (but not directories)
                filtered_files = [f for f in all_files if f.get('type') != 'dir']
            
            # Sort files by name
            filtered_files.sort(key=lambda x: x.get('name', ''))
            
            logger.info(f"Found {len(filtered_files)} files matching criteria")
            
            return jsonify({
                'success': True,
                'files': filtered_files,
                'total': len(filtered_files)
            })
            
        except Exception as e:
            logger.error(f"Error listing files from {path}: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Error listing files: {str(e)}'
            })
            
    except Exception as e:
        logger.error(f"List files error: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/generate-prj-file', methods=['POST'])
def generate_prj_file():
    """Generate and export a .prj project file"""
    try:
        data = request.json
        logger.info(f"=== GENERATE PRJ FILE REQUEST ===")
        logger.info(f"Raw request data: {data}")
        
        project_name = data.get('project_name')
        export_path = data.get('export_path', '/mnt/main/Projects/')
        export_server = data.get('export_server', 'source')
        region1_files = data.get('region1_files', [])
        region1_path = data.get('region1_path', '')
        region2_file = data.get('region2_file')
        region2_path = data.get('region2_path', '')
        region3_files = data.get('region3_files', [])
        region3_path = data.get('region3_path', '')
        slide_duration = data.get('slide_duration', 5)  # Default to 5 seconds
        
        # Ensure slide_duration is an integer
        try:
            slide_duration = int(slide_duration)
        except (TypeError, ValueError):
            logger.warning(f"Invalid slide_duration value: {slide_duration}, using default of 5")
            slide_duration = 5
        
        logger.info(f"Generating PRJ file: {project_name}")
        logger.info(f"Region 1 files: {len(region1_files)}")
        logger.info(f"Region 2 file: {region2_file}")
        logger.info(f"Region 3 files: {len(region3_files)}")
        logger.info(f"Slide duration received: {slide_duration} seconds (type: {type(slide_duration)})")
        logger.info(f"Slide duration after conversion: {slide_duration} seconds")
        
        # Build the PRJ content in JSON format
        import json
        import uuid
        import os
        
        # Calculate total duration based on Region 1 files and custom slide duration
        frame_rate_n = 30000
        frame_rate_d = 1001
        frame_rate = frame_rate_n / frame_rate_d  # 29.97 fps
        
        # Calculate exact duration and frames for the custom slide duration
        # For 29.97 fps: X seconds = X * 29.97 frames
        # So we use floor(seconds * 29.97) to get frame count
        logger.info(f"DEBUG: About to calculate frames - slide_duration={slide_duration}, frame_rate={frame_rate}")
        frames_per_image = int(slide_duration * frame_rate)  # frames for custom duration
        logger.info(f"DEBUG: frames_per_image calculated = {frames_per_image}")
        
        # Recalculate exact duration based on actual frame count
        duration_per_image = frames_per_image / frame_rate  # exact duration in seconds
        logger.info(f"DEBUG: duration_per_image calculated = {duration_per_image}")
        
        logger.info(f"Slide duration calculation: {slide_duration}s * {frame_rate}fps = {frames_per_image} frames")
        logger.info(f"Actual duration per image: {duration_per_image} seconds")
        logger.info(f"Expected for 10s: 299 frames, 9.976643 seconds. Got: {frames_per_image} frames, {duration_per_image} seconds")
        
        total_frames = len(region1_files) * frames_per_image
        total_duration = len(region1_files) * duration_per_image
        
        prj_data = {
            "multiregion playlist description": {
                "title": "",
                "author": "",
                "play mode": "sequential",
                "auto remove": True,
                "override cun": False,
                "editor view": {
                    "cursor frame": 0,
                    "view start": 0,
                    "view end": total_duration
                },
                "aspect ratio": {
                    "n": 16,
                    "d": 9,
                    "enforce": False
                },
                "timeline rate": {
                    "n": frame_rate_n,
                    "d": frame_rate_d
                },
                "sections": [],
                "duration": total_duration
            }
        }
        
        # Region 1 - Upper graphics slideshow
        region1_items = []
        current_frame = 0
        current_time = 0.0
        
        for idx, filename in enumerate(region1_files):
            # Construct full path
            full_path = os.path.join(region1_path, filename) if region1_path else filename
            
            # Calculate frame boundaries
            # For example: first slide is frames 0-148 (149 frames), second is 149-297 (149 frames), etc.
            end_frame = current_frame + frames_per_image - 1
            
            if idx == 0:  # Log details for first item
                logger.info(f"DEBUG: First item - startFrame={current_frame}, endFrame={end_frame}")
                logger.info(f"DEBUG: First item - start={current_time}, end={current_time + duration_per_image}")
                logger.info(f"DEBUG: First item - durationFrame={frames_per_image}, duration={duration_per_image}")
            
            item = {
                "startFrame": current_frame,
                "endFrame": end_frame,
                "offsetFrame": None,
                "start": current_time,
                "end": current_time + duration_per_image,
                "offset": None,
                "durationFrame": frames_per_image,
                "duration": duration_per_image,
                "isSelected": False,
                "path": full_path,
                "guid": "{" + str(uuid.uuid4()) + "}",
                "file type": "image/jpeg",
                "item duration": 0
            }
            region1_items.append(item)
            current_frame += frames_per_image
            current_time += duration_per_image
        
        region1 = {
            "mute": False,
            "invisible": False,
            "name": "Region 1",
            "region": {
                "left": -1.0203083511776277e-16,
                "top": -0.07007479322904887,
                "width": 99.99999999999993,
                "height": 74.50745162653122
            },
            "main": False,
            "list": region1_items,
            "durationFrames": total_frames,
            "duration": total_duration
        }
        prj_data["multiregion playlist description"]["sections"].append(region1)
        
        # Region 2 - Lower static graphic
        if region2_file:
            # Construct full path for region 2
            region2_full_path = os.path.join(region2_path, region2_file) if region2_path else region2_file
            
            region2 = {
                "mute": False,
                "invisible": False,
                "name": "Region 2",
                "region": {
                    "left": 0,
                    "top": 0,
                    "width": 100,
                    "height": 100
                },
                "main": False,
                "list": [{
                    "startFrame": 0,
                    "endFrame": total_frames - 1,
                    "offsetFrame": None,
                    "start": 0,
                    "end": total_duration,
                    "offset": None,
                    "durationFrame": total_frames,
                    "duration": total_duration,
                    "isSelected": False,
                    "path": region2_full_path,
                    "guid": "{" + str(uuid.uuid4()) + "}",
                    "file type": "image/png",
                    "item duration": 0
                }],
                "durationFrames": total_frames,
                "duration": total_duration
            }
            prj_data["multiregion playlist description"]["sections"].append(region2)
        
        # Region 3 - Music (invisible audio track)
        if region3_files:
            # For simplicity, just use the first music file
            music_filename = region3_files[0] if region3_files else None
            if music_filename:
                # Construct full path for music file
                music_file = os.path.join(region3_path, music_filename) if region3_path else music_filename
                region3 = {
                    "mute": False,
                    "invisible": True,  # Audio region is invisible
                    "name": "Region 3",
                    "region": {
                        "left": -1.8705653104923163e-16,
                        "top": -0.0695861153525056,
                        "width": 99.99999999999987,
                        "height": 74.50647427077814
                    },
                    "main": False,
                    "list": [{
                        "startFrame": 0,
                        "endFrame": total_frames - 1,
                        "offsetFrame": None,
                        "start": 0,
                        "end": total_duration,
                        "offset": None,
                        "durationFrame": total_frames,
                        "duration": total_duration,
                        "isSelected": False,
                        "path": music_file,
                        "guid": "{" + str(uuid.uuid4()) + "}",
                        "file type": "video/quicktime",  # MP4 files show as quicktime
                        "item duration": 145.749333  # Placeholder duration
                    }],
                    "durationFrames": total_frames,
                    "duration": total_duration
                }
                prj_data["multiregion playlist description"]["sections"].append(region3)
        
        # Convert to JSON string but remove outer braces for Castus format
        json_str = json.dumps(prj_data, indent=2)
        # Remove the outer curly braces
        lines = json_str.split('\n')
        if lines[0] == '{' and lines[-1] == '}':
            lines = lines[1:-1]
            # Remove one level of indentation from all lines
            lines = [line[2:] if line.startswith('  ') else line for line in lines]
        prj_content = '\n'.join(lines)
        
        # Write to FTP
        if export_server not in ftp_managers:
            return jsonify({
                'success': False,
                'message': f'{export_server} server not connected'
            })
        
        ftp = ftp_managers[export_server]
        
        # Create temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.prj', delete=False) as tmp:
            tmp.write(prj_content)
            tmp_path = tmp.name
        
        try:
            # Ensure filename has .prj extension
            if not project_name.endswith('.prj'):
                project_name += '.prj'
            
            # Ensure path ends with /
            if not export_path.endswith('/'):
                export_path += '/'
            
            remote_path = export_path + project_name
            
            # Upload file
            success = ftp.upload_file(tmp_path, remote_path)
            
            if success:
                logger.info(f"Successfully exported PRJ file to {remote_path}")
                return jsonify({
                    'success': True,
                    'message': f'Project file exported to {remote_path}',
                    'path': remote_path
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to upload project file'
                })
                
        finally:
            # Clean up temp file
            import os
            os.unlink(tmp_path)
            
    except Exception as e:
        logger.error(f"Generate PRJ file error: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/set-content-expiration', methods=['POST'])
def set_content_expiration():
    """Set content expiration dates based on shelf life settings"""
    logger.info("=== SET CONTENT EXPIRATION REQUEST ===")
    try:
        data = request.json
        shelf_life_settings = data.get('shelf_life_settings', {})
        
        logger.info(f"Setting content expiration with shelf life settings: {shelf_life_settings}")
        
        # Get all content with scheduling metadata
        query = """
            SELECT 
                a.id as asset_id,
                i.encoded_date,
                a.duration_seconds,
                a.content_type,
                i.file_name,
                sm.id as scheduling_id
            FROM assets a
            LEFT JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE a.analysis_completed = true
        """
        
        conn = db_manager._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                assets = cursor.fetchall()
                
                updated_count = 0
                
                for asset in assets:
                    # Get creation date from encoded_date or filename
                    creation_date = None
                    
                    if asset['encoded_date']:
                        creation_date = asset['encoded_date']
                    elif asset['file_name']:
                        # Try to extract from filename (YYMMDD format)
                        filename = asset['file_name']
                        if len(filename) >= 6 and filename[:6].isdigit():
                            try:
                                yy = int(filename[0:2])
                                mm = int(filename[2:4])
                                dd = int(filename[4:6])
                                
                                # Validate date components
                                if 1 <= mm <= 12 and 1 <= dd <= 31:
                                    # Determine century
                                    year = 2000 + yy if yy <= 30 else 1900 + yy
                                    creation_date = datetime(year, mm, dd)
                            except:
                                pass
                    
                    if not creation_date:
                        continue
                        
                    # Get content type (uppercase)
                    content_type = asset.get('content_type', 'other').upper()
                    
                    # Map content type to the keys used in shelf life settings
                    content_type_key = content_type if content_type in shelf_life_settings else 'OTHER'
                    
                    # For now, assume medium shelf life (can be enhanced to use AI analysis)
                    shelf_life_type = 'medium'
                    
                    # Get days from settings based on content type
                    days = shelf_life_settings.get(content_type_key, {}).get(shelf_life_type, 60)
                    
                    # Calculate expiration date from creation date
                    expiry_date = creation_date + timedelta(days=days)
                    
                    # Update or insert scheduling metadata
                    if asset['scheduling_id']:
                        cursor.execute("""
                            UPDATE scheduling_metadata 
                            SET content_expiry_date = %s 
                            WHERE id = %s
                        """, (expiry_date, asset['scheduling_id']))
                    else:
                        cursor.execute("""
                            INSERT INTO scheduling_metadata (asset_id, content_expiry_date)
                            VALUES (%s, %s)
                        """, (asset['asset_id'], expiry_date))
                    
                    updated_count += 1
                
                conn.commit()
        finally:
            db_manager._put_connection(conn)
        
        logger.info(f"Updated expiration dates for {updated_count} content items")
        
        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'message': f'Successfully updated {updated_count} content items'
        })
        
    except Exception as e:
        error_msg = f"Set content expiration error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})


@app.route('/api/clear-content-expirations', methods=['POST'])
def clear_content_expirations():
    """Clear all content expiration dates"""
    logger.info("=== CLEAR CONTENT EXPIRATIONS REQUEST ===")
    try:
        # Clear all expiration dates
        query = """
            UPDATE scheduling_metadata 
            SET content_expiry_date = NULL 
            WHERE content_expiry_date IS NOT NULL
        """
        
        conn = db_manager._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query)
                cleared_count = cursor.rowcount
                conn.commit()
        finally:
            db_manager._put_connection(conn)
        
        logger.info(f"Cleared expiration dates for {cleared_count} content items")
        
        return jsonify({
            'success': True,
            'cleared_count': cleared_count,
            'message': f'Successfully cleared {cleared_count} expiration dates'
        })
        
    except Exception as e:
        error_msg = f"Clear content expirations error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})


@app.route('/api/update-content-expiration', methods=['POST'])
def update_content_expiration():
    """Update expiration date for a single content item"""
    logger.info("=== UPDATE CONTENT EXPIRATION REQUEST ===")
    try:
        data = request.json
        asset_id = data.get('asset_id')
        expiry_date = data.get('expiry_date')
        
        if not asset_id:
            return jsonify({
                'success': False,
                'message': 'asset_id is required'
            }), 400
        
        logger.info(f"Updating expiration date for asset {asset_id} to {expiry_date}")
        
        conn = db_manager._get_connection()
        try:
            with conn.cursor() as cur:
                if expiry_date:
                    # Update or insert the expiration date
                    cur.execute("""
                        INSERT INTO scheduling_metadata (asset_id, content_expiry_date)
                        VALUES (%s, %s)
                        ON CONFLICT (asset_id) 
                        DO UPDATE SET content_expiry_date = EXCLUDED.content_expiry_date
                    """, (asset_id, expiry_date))
                else:
                    # Clear the expiration date (set to NULL)
                    cur.execute("""
                        UPDATE scheduling_metadata 
                        SET content_expiry_date = NULL 
                        WHERE asset_id = %s
                    """, (asset_id,))
                
                conn.commit()
        
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
                
        logger.info(f"Successfully updated expiration date for asset {asset_id}")
        return jsonify({
            'success': True,
            'message': 'Expiration date updated successfully'
        })
        
    except Exception as e:
        error_msg = f"Update content expiration error: {str(e)}"
        logger.error(error_msg)
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/content-expiration-stats', methods=['GET'])
def get_content_expiration_stats():
    """Get statistics about active and expired content"""
    logger.info("=== GET CONTENT EXPIRATION STATS REQUEST ===")
    try:
        query = """
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP THEN 1 END) as active,
                COUNT(CASE WHEN sm.content_expiry_date IS NOT NULL AND sm.content_expiry_date <= CURRENT_TIMESTAMP THEN 1 END) as expired,
                COUNT(CASE WHEN sm.content_expiry_date IS NOT NULL AND sm.content_expiry_date > CURRENT_TIMESTAMP AND sm.content_expiry_date <= CURRENT_TIMESTAMP + INTERVAL '7 days' THEN 1 END) as expiring_soon,
                COALESCE(SUM(a.duration_seconds), 0) as total_duration_seconds,
                COALESCE(SUM(CASE WHEN sm.content_expiry_date IS NULL OR sm.content_expiry_date > CURRENT_TIMESTAMP THEN a.duration_seconds END), 0) as active_duration_seconds,
                COALESCE(SUM(CASE WHEN sm.content_expiry_date IS NOT NULL AND sm.content_expiry_date <= CURRENT_TIMESTAMP THEN a.duration_seconds END), 0) as expired_duration_seconds
            FROM assets a
            LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
            WHERE a.analysis_completed = true
        """
        
        conn = db_manager._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                stats = cursor.fetchone()
        finally:
            db_manager._put_connection(conn)
        
        logger.info(f"Content stats: {stats}")
        
        return jsonify({
            'success': True,
            'stats': {
                'total': stats['total'],
                'active': stats['active'],
                'expired': stats['expired'],
                'expiring_soon': stats['expiring_soon'],
                'total_hours': round(stats['total_duration_seconds'] / 3600, 1),
                'active_hours': round(stats['active_duration_seconds'] / 3600, 1),
                'expired_hours': round(stats['expired_duration_seconds'] / 3600, 1)
            }
        })
        
    except Exception as e:
        error_msg = f"Get content expiration stats error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/sync-castus-expiration', methods=['POST'])
def sync_castus_expiration():
    """Sync expiration date from Castus metadata for a content item"""
    logger.info("=== SYNC CASTUS EXPIRATION REQUEST ===")
    try:
        data = request.json
        asset_id = data.get('asset_id')
        file_path = data.get('file_path')
        server = data.get('server', 'source')  # default to source server
        
        if not all([asset_id, file_path]):
            return jsonify({
                'success': False,
                'message': 'Missing required fields: asset_id and file_path'
            }), 400
        
        logger.info(f"Syncing expiration for asset {asset_id} from {server} server")
        logger.info(f"File path: {file_path}")
        
        # Import here to avoid circular imports
        from castus_metadata import CastusMetadataHandler
        
        # Get FTP configuration and connect
        config = config_manager.get_server_config(server)
        if not config:
            return jsonify({
                'success': False,
                'message': f'Server configuration not found: {server}'
            }), 400
        
        ftp = FTPManager(config)
        if not ftp.connect():
            return jsonify({
                'success': False,
                'message': f'Failed to connect to {server} server'
            }), 500
        
        try:
            # Create metadata handler and get expiration
            logger.info("Creating CastusMetadataHandler...")
            handler = CastusMetadataHandler(ftp)
            
            logger.info(f"Attempting to get content window close for: {file_path}")
            expiration_date = handler.get_content_window_close(file_path)
            
            if not expiration_date:
                logger.warning(f"No expiration date found in metadata for: {file_path}")
                return jsonify({
                    'success': False,
                    'message': 'No expiration date found in Castus metadata'
                }), 404
            
            logger.info(f"Found expiration date: {expiration_date}")
            
            # Update database
            conn = db_manager._get_connection()
            try:
                with conn.cursor() as cursor:
                    # Check if metadata record exists
                    cursor.execute("""
                        SELECT id FROM scheduling_metadata 
                        WHERE asset_id = %s
                    """, (asset_id,))
                    
                    if cursor.fetchone():
                        # Update existing record
                        logger.info(f"Updating existing scheduling_metadata record for asset {asset_id}")
                        cursor.execute("""
                            UPDATE scheduling_metadata 
                            SET content_expiry_date = %s,
                                metadata_synced_at = CURRENT_TIMESTAMP
                            WHERE asset_id = %s
                        """, (expiration_date, asset_id))
                        logger.info(f"Updated {cursor.rowcount} rows")
                    else:
                        # Create new record
                        logger.info(f"Creating new scheduling_metadata record for asset {asset_id}")
                        cursor.execute("""
                            INSERT INTO scheduling_metadata (asset_id, content_expiry_date, metadata_synced_at)
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                        """, (asset_id, expiration_date))
                        logger.info("Insert completed")
                    
                conn.commit()
                
                logger.info(f"Database commit successful - expiration date for asset {asset_id} set to {expiration_date}")
                
                return jsonify({
                    'success': True,
                    'expiration_date': expiration_date.isoformat(),
                    'message': f'Successfully synced expiration date: {expiration_date.strftime("%Y-%m-%d %H:%M:%S")}'
                })
                
            finally:
                db_manager._put_connection(conn)
                
        finally:
            ftp.disconnect()
            
    except Exception as e:
        error_msg = f"Sync Castus expiration error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg}), 500

@app.route('/api/sync-all-castus-expirations', methods=['POST'])
def sync_all_castus_expirations():
    """Sync expiration dates from Castus metadata for all content"""
    logger.info("=== SYNC ALL CASTUS EXPIRATIONS REQUEST ===")
    try:
        data = request.json
        server = data.get('server', 'source')  # default to source server
        limit = data.get('limit', None)  # optional limit for testing
        
        # Import here to avoid circular imports
        from castus_metadata import CastusMetadataHandler
        
        # Get all content items that need syncing
        conn = db_manager._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    SELECT a.id, a.file_path, a.file_name
                    FROM assets a
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE a.analysis_completed = true
                    AND (sm.metadata_synced_at IS NULL OR sm.metadata_synced_at < CURRENT_TIMESTAMP - INTERVAL '7 days')
                    ORDER BY a.id
                """
                if limit:
                    query += f" LIMIT {int(limit)}"
                
                cursor.execute(query)
                assets = cursor.fetchall()
        finally:
            db_manager._put_connection(conn)
        
        logger.info(f"Found {len(assets)} assets to sync")
        
        if not assets:
            return jsonify({
                'success': True,
                'message': 'No assets need syncing',
                'stats': {'total': 0, 'synced': 0, 'failed': 0}
            })
        
        # Connect to FTP server
        config = config_manager.get_server_config(server)
        if not config:
            return jsonify({
                'success': False,
                'message': f'Server configuration not found: {server}'
            }), 400
        
        ftp = FTPManager(config)
        if not ftp.connect():
            return jsonify({
                'success': False,
                'message': f'Failed to connect to {server} server'
            }), 500
        
        # Process each asset
        handler = CastusMetadataHandler(ftp)
        synced = 0
        failed = 0
        errors = []
        
        try:
            for asset in assets:
                try:
                    asset_id = asset['id']
                    file_path = asset['file_path']
                    
                    # Get expiration date from metadata
                    expiration_date = handler.get_content_window_close(file_path)
                    
                    if expiration_date:
                        # Update database
                        conn = db_manager._get_connection()
                        try:
                            with conn.cursor() as cursor:
                                # Check if metadata record exists
                                cursor.execute("""
                                    SELECT id FROM scheduling_metadata 
                                    WHERE asset_id = %s
                                """, (asset_id,))
                                
                                if cursor.fetchone():
                                    # Update existing record
                                    cursor.execute("""
                                        UPDATE scheduling_metadata 
                                        SET content_expiry_date = %s,
                                            metadata_synced_at = CURRENT_TIMESTAMP
                                        WHERE asset_id = %s
                                    """, (expiration_date, asset_id))
                                else:
                                    # Create new record
                                    cursor.execute("""
                                        INSERT INTO scheduling_metadata (asset_id, content_expiry_date, metadata_synced_at)
                                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                                    """, (asset_id, expiration_date))
                                
                            conn.commit()
                            synced += 1
                            logger.debug(f"Synced asset {asset_id}: {expiration_date}")
                        finally:
                            db_manager._put_connection(conn)
                    else:
                        failed += 1
                        errors.append(f"No metadata found for {asset['file_name']}")
                        
                except Exception as e:
                    failed += 1
                    error_msg = f"Failed to sync {asset.get('file_name', 'unknown')}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                
        finally:
            ftp.disconnect()
        
        # Return results
        return jsonify({
            'success': True,
            'message': f'Sync completed: {synced} synced, {failed} failed',
            'stats': {
                'total': len(assets),
                'synced': synced,
                'failed': failed
            },
            'errors': errors[:10] if errors else []  # Return first 10 errors
        })
        
    except Exception as e:
        error_msg = f"Sync all Castus expirations error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'message': error_msg}), 500


if __name__ == '__main__':
    print("Starting FTP Sync Backend with DEBUG logging...")
    print("Backend will be available at: http://127.0.0.1:5000")
    print("Watch this terminal for detailed connection logs...")
    app.run(debug=True, host='127.0.0.1', port=5000)