#!/usr/bin/env python3
"""
Audio Normalization Test Script
Test normalizing a single file from Castus to -24 LKFS
"""

import sys
import os
import argparse
import logging

# Add backend directory to path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_dir)

from config_manager import ConfigManager
from ftp_manager import FTPManager
from database_postgres import PostgreSQLDatabaseManager

# Add parent directory for loudness_analysis
parent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, parent_dir)

from loudness_analysis.audio_normalizer import AudioNormalizer
import tempfile

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Test audio normalization on a file from Castus')
    parser.add_argument('asset_id', type=int, help='Asset ID to normalize')
    parser.add_argument('--target-lkfs', type=float, default=-24.0, help='Target LKFS (default: -24)')
    parser.add_argument('--output-dir', default='./normalized_files', help='Output directory for normalized files')
    parser.add_argument('--preview-only', action='store_true', help='Only preview, do not process')
    parser.add_argument('--upload', action='store_true', help='Upload to Castus after normalization')
    parser.add_argument('--replace', action='store_true', help='Replace original file (requires --upload)')
    
    args = parser.parse_args()
    
    # Initialize database and config
    logger.info("Initializing database and configuration...")
    
    # Use PostgreSQL with connection string
    import getpass
    default_pg_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
    db = PostgreSQLDatabaseManager(
        connection_string=os.getenv('DATABASE_URL', default_pg_conn)
    )
    db.connect()  # Initialize the connection pool
    
    # Use config file from backend directory
    config_file_path = os.path.join(backend_dir, 'config.json')
    config_manager = ConfigManager(config_file=config_file_path)
    config_manager.load_config()
    config = config_manager.config
    
    # Get asset information
    asset = db.get_asset_by_id(args.asset_id)
    if not asset:
        logger.error(f"Asset {args.asset_id} not found")
        return 1
    
    logger.info(f"Asset: {asset['content_title']} ({asset['content_type']})")
    
    # Get file instance
    instances = db.get_instances_by_asset_id(args.asset_id)
    instance = None
    for inst in instances:
        if inst.get('is_primary'):
            instance = inst
            break
    
    if not instance and instances:
        instance = instances[0]  # Use first instance if no primary
    if not instance:
        logger.error("No file instance found for this asset")
        return 1
    
    file_path = instance['file_path']
    file_name = instance['file_name']
    
    if not file_path.startswith('/'):
        file_path = f"/mnt/main/ATL26 On-Air Content/{file_path}"
    
    logger.info(f"File: {file_name}")
    logger.info(f"Path: {file_path}")
    
    # Connect to FTP
    logger.info("Connecting to FTP...")
    if 'servers' not in config or 'target' not in config.get('servers', {}):
        logger.error("No FTP server configuration found. Please configure FTP servers in the web interface first.")
        print("\nERROR: FTP server configuration missing!")
        print("Please use the web interface to configure FTP servers before using this tool.")
        print("Go to: http://localhost:8000")
        return 1
    
    target_config = config['servers']['target']
    if not all(k in target_config for k in ['host', 'user', 'password']):
        logger.error("Incomplete FTP configuration. Please configure the target server in the web interface.")
        print("\nERROR: Incomplete FTP configuration!")
        print("Please configure the target FTP server (Castus2) in the web interface.")
        return 1
    
    ftp = FTPManager(target_config)
    if not ftp.connect():
        logger.error("Failed to connect to FTP server")
        print("\nERROR: Failed to connect to FTP server!")
        print(f"Host: {target_config.get('host', 'not set')}")
        print("Please check your FTP configuration and ensure the server is accessible.")
        return 1
    
    # Download file
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_name)[1], delete=False) as temp_file:
        temp_path = temp_file.name
    
    try:
        logger.info(f"Downloading file from FTP...")
        if not ftp.download_file(file_path, temp_path):
            logger.error("Failed to download file from FTP")
            print("\nERROR: Failed to download file from FTP server!")
            print(f"File path: {file_path}")
            return 1
        
        # Create normalizer
        normalizer = AudioNormalizer(
            target_lkfs=args.target_lkfs,
            target_lra=7.0,
            target_tp=-2.0
        )
        
        if args.preview_only:
            # Preview only
            logger.info("Analyzing file (preview mode)...")
            _, info = normalizer.normalize(temp_path, preview_only=True)
            
            print("\n" + "="*60)
            print("NORMALIZATION PREVIEW")
            print("="*60)
            print(f"File: {file_name}")
            print(f"\nCurrent Loudness:")
            print(f"  Integrated: {info['measured']['integrated_lkfs']:.1f} LKFS")
            print(f"  True Peak:  {info['measured']['true_peak']:.1f} dBTP")
            print(f"  Range:      {info['measured']['loudness_range']:.1f} LU")
            print(f"\nTarget Loudness:")
            print(f"  Integrated: {info['target']['integrated_lkfs']:.1f} LKFS")
            print(f"  True Peak:  {info['target']['true_peak']:.1f} dBTP")
            print(f"  Range:      {info['target']['loudness_range']:.1f} LU")
            print(f"\nAdjustment: {info['offset']:.1f} dB")
            
            if info['will_normalize']:
                print("\n⚠️  File will be normalized to target loudness")
            else:
                print("\n✓ File is already close to target loudness")
            print("="*60)
            
        else:
            # Process normalization
            os.makedirs(args.output_dir, exist_ok=True)
            output_file = os.path.join(args.output_dir, f"{os.path.splitext(file_name)[0]}_normalized{os.path.splitext(file_name)[1]}")
            
            logger.info(f"Normalizing file to {args.target_lkfs} LKFS...")
            output_path, info = normalizer.normalize(temp_path, output_file)
            
            if info['success']:
                output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                
                print("\n" + "="*60)
                print("NORMALIZATION COMPLETE")
                print("="*60)
                print(f"File: {file_name}")
                print(f"Output: {output_path}")
                print(f"Size: {output_size_mb:.2f} MB")
                
                if 'output_lkfs' in info:
                    print(f"Final Loudness: {info['output_lkfs']:.1f} LKFS")
                
                print("\n✓ File normalized successfully!")
                print(f"  Saved to: {output_path}")
                
                # Upload if requested
                if args.upload:
                    print("\n" + "-"*60)
                    if args.replace:
                        print("Uploading and replacing original file...")
                        backup_path = f"{file_path}.backup_{os.path.basename(output_path).split('_normalized')[0]}"
                        upload_path = file_path
                    else:
                        print("Uploading as new file...")
                        backup_path = None
                        dir_path = os.path.dirname(file_path)
                        upload_path = os.path.join(dir_path, os.path.basename(output_path))
                    
                    try:
                        if args.replace and backup_path:
                            logger.info(f"Creating backup: {backup_path}")
                            ftp.ftp.rename(file_path, backup_path)
                        
                        logger.info(f"Uploading to: {upload_path}")
                        ftp.upload_file(output_path, upload_path)
                        
                        print("✓ Upload complete!")
                        print(f"  Path: {upload_path}")
                        if backup_path:
                            print(f"  Backup: {backup_path}")
                            
                    except Exception as e:
                        logger.error(f"Upload failed: {str(e)}")
                        print(f"\n❌ Upload failed: {str(e)}")
                
                print("="*60)
                
            else:
                print(f"\n❌ Normalization failed: {info.get('error', 'Unknown error')}")
                
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        ftp.disconnect()
    
    return 0


if __name__ == '__main__':
    exit(main())