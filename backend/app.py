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
import logging
from bson import ObjectId
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

def convert_objectid_to_string(obj):
    """Convert ObjectId and datetime objects to JSON serializable format"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
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
        
        return jsonify({
            'success': True, 
            'files': files,
            'count': len(files)
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

@app.route('/api/analyze-files', methods=['POST'])
def analyze_files():
    """Start analysis of selected files"""
    logger.info("=== ANALYZE FILES REQUEST ===")
    try:
        data = request.json
        files = data.get('files', [])
        server_type = data.get('server_type', 'source')
        
        # Get AI config from config manager
        ai_config = config_manager.get_ai_analysis_settings()
        
        # Override with any config from request
        if 'ai_config' in data:
            ai_config.update(data['ai_config'])
        
        logger.info(f"Starting analysis of {len(files)} files from {server_type} server")
        logger.info(f"AI config: provider={ai_config.get('provider')}, enabled={ai_config.get('enabled')}")
        
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
        results = file_analyzer.analyze_batch(files, ftp_manager, ai_config)
        
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

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'FTP Sync Backend is running'})

if __name__ == '__main__':
    print("Starting FTP Sync Backend with DEBUG logging...")
    print("Backend will be available at: http://127.0.0.1:5000")
    print("Watch this terminal for detailed connection logs...")
    app.run(debug=True, host='127.0.0.1', port=5000)