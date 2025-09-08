#!/usr/bin/env python3
"""
Test finding and syncing all content expirations from Castus metadata
Outputs to both console and text file
"""

import os
import sys
from datetime import datetime
from database_postgres import PostgreSQLDatabaseManager
from castus_metadata import CastusMetadataHandler
from ftp_manager import FTPManager
from config_manager import ConfigManager
import logging

# Setup logging to suppress debug messages
logging.getLogger('ftp_manager').setLevel(logging.ERROR)
logging.getLogger('castus_metadata').setLevel(logging.ERROR)
logging.getLogger('config_manager').setLevel(logging.ERROR)


class DualOutput:
    """Class to write output to both console and file"""
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()  # Ensure immediate write
    
    def close(self):
        self.log.close()


def get_all_content_for_sync():
    """Get all content assets that need metadata sync"""
    db = PostgreSQLDatabaseManager()
    
    if not db.connect():
        print("❌ Failed to connect to database")
        return []
    
    try:
        conn = db._get_connection()
        with conn.cursor() as cursor:
            # Get all assets with their file paths and current metadata status
            cursor.execute("""
                SELECT 
                    a.id as asset_id,
                    a.content_type,
                    a.content_title,
                    i.file_name,
                    i.file_path,
                    sm.content_expiry_date,
                    sm.metadata_synced_at,
                    CASE 
                        WHEN sm.metadata_synced_at IS NULL THEN 'Never synced'
                        ELSE 'Previously synced'
                    END as sync_status
                FROM assets a
                JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE a.content_type IS NOT NULL
                ORDER BY 
                    sm.metadata_synced_at NULLS FIRST,  -- Unsynced first
                    a.content_type,
                    a.content_title
            """)
            
            results = cursor.fetchall()
            return results
            
    finally:
        db._put_connection(conn)
        db.disconnect()


def sync_all_expirations(assets, output):
    """Sync expiration dates for all assets"""
    # Setup FTP connection
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    server_config = all_config['servers']['source']
    
    ftp = FTPManager(server_config)
    if not ftp.connect():
        output.write("❌ Failed to connect to FTP server\n")
        return
    
    handler = CastusMetadataHandler(ftp)
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    # Statistics
    stats = {
        'total': len(assets),
        'synced': 0,
        'no_metadata': 0,
        'errors': 0,
        'expiring_soon': [],
        'expired': []
    }
    
    output.write(f"\n{'='*100}\n")
    output.write(f"PROCESSING {len(assets)} ASSETS\n")
    output.write(f"{'='*100}\n\n")
    
    for i, asset in enumerate(assets, 1):
        asset_id = asset['asset_id']
        file_name = asset['file_name']
        file_path = asset['file_path']
        current_expiry = asset['content_expiry_date']
        sync_status = asset['sync_status']
        
        # Construct full path
        if not file_path.startswith('/'):
            # Relative path, prepend base path
            full_path = f"/mnt/md127/ATL26 On-Air Content/{file_path}"
        else:
            full_path = file_path
        
        output.write(f"{i}/{len(assets)}: {file_name}\n")
        output.write(f"   Type: {asset['content_type']} | Status: {sync_status}\n")
        
        try:
            # Try to get expiration from Castus
            expiration = handler.get_content_window_close(full_path)
            
            if expiration:
                output.write(f"   ✅ Found expiration: {expiration.strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                # Calculate days
                if expiration.tzinfo:
                    now = datetime.now(expiration.tzinfo)
                else:
                    now = datetime.now()
                days_left = (expiration - now).days
                
                output.write(f"   📅 Days until expiration: {days_left}\n")
                
                # Check if different from current
                if current_expiry:
                    if current_expiry.tzinfo:
                        current_expiry = current_expiry.replace(tzinfo=None)
                    if expiration.tzinfo:
                        exp_compare = expiration.replace(tzinfo=None)
                    else:
                        exp_compare = expiration
                    
                    if abs((current_expiry - exp_compare).days) > 1:
                        output.write(f"   ⚠️  CHANGED from {current_expiry.strftime('%Y-%m-%d')} to {expiration.strftime('%Y-%m-%d')}\n")
                
                # Update database
                conn = db._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            UPDATE scheduling_metadata 
                            SET content_expiry_date = %s,
                                metadata_synced_at = CURRENT_TIMESTAMP
                            WHERE asset_id = %s
                        """, (expiration, asset_id))
                        
                        if cursor.rowcount == 0:
                            # No existing record, insert
                            cursor.execute("""
                                INSERT INTO scheduling_metadata (asset_id, content_expiry_date, metadata_synced_at)
                                VALUES (%s, %s, CURRENT_TIMESTAMP)
                            """, (asset_id, expiration))
                        
                    conn.commit()
                    output.write(f"   💾 Database updated\n")
                    stats['synced'] += 1
                    
                    # Track expiring content
                    if days_left < 0:
                        stats['expired'].append((file_name, days_left))
                    elif days_left < 30:
                        stats['expiring_soon'].append((file_name, days_left))
                    
                finally:
                    db._put_connection(conn)
                    
            else:
                output.write(f"   ❌ No metadata file found\n")
                stats['no_metadata'] += 1
                
        except Exception as e:
            output.write(f"   ❌ Error: {str(e)}\n")
            stats['errors'] += 1
        
        output.write("\n")
    
    # Cleanup
    ftp.disconnect()
    db.disconnect()
    
    # Print summary
    output.write(f"\n{'='*100}\n")
    output.write(f"SUMMARY\n")
    output.write(f"{'='*100}\n\n")
    
    output.write(f"Total assets processed: {stats['total']}\n")
    output.write(f"✅ Successfully synced: {stats['synced']}\n")
    output.write(f"📄 No metadata found: {stats['no_metadata']}\n")
    output.write(f"❌ Errors: {stats['errors']}\n\n")
    
    if stats['expired']:
        output.write(f"🚨 EXPIRED CONTENT ({len(stats['expired'])} files):\n")
        for name, days in sorted(stats['expired'], key=lambda x: x[1]):
            output.write(f"   - {name}: {abs(days)} days ago\n")
        output.write("\n")
    
    if stats['expiring_soon']:
        output.write(f"⏰ EXPIRING WITHIN 30 DAYS ({len(stats['expiring_soon'])} files):\n")
        for name, days in sorted(stats['expiring_soon'], key=lambda x: x[1]):
            output.write(f"   - {name}: {days} days\n")
        output.write("\n")
    
    # Success rate
    if stats['total'] > 0:
        success_rate = (stats['synced'] / stats['total']) * 100
        output.write(f"Success rate: {success_rate:.1f}%\n")
    
    output.write(f"\nReport saved to: expiration_sync_report.txt\n")


def main():
    # Create output file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"expiration_sync_report_{timestamp}.txt"
    
    # Setup dual output
    output = DualOutput(output_file)
    
    output.write(f"🚀 CASTUS METADATA EXPIRATION SYNC\n")
    output.write(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write(f"📄 Output file: {output_file}\n")
    
    # Get all assets
    output.write(f"\n📊 Fetching all content assets from database...\n")
    assets = get_all_content_for_sync()
    
    if not assets:
        output.write("❌ No assets found in database\n")
        output.close()
        return
    
    output.write(f"✅ Found {len(assets)} assets to process\n")
    
    # Show breakdown by sync status
    never_synced = len([a for a in assets if a['sync_status'] == 'Never synced'])
    previously_synced = len([a for a in assets if a['sync_status'] == 'Previously synced'])
    
    output.write(f"   - Never synced: {never_synced}\n")
    output.write(f"   - Previously synced: {previously_synced}\n")
    
    # Ask for confirmation
    print("\n⚠️  This will process ALL assets. Continue? (y/N): ", end='')
    response = input().strip().lower()
    
    if response != 'y':
        output.write("\n❌ Cancelled by user\n")
        output.close()
        return
    
    # Process all assets
    sync_all_expirations(assets, output)
    
    output.write(f"\n✅ Process complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.close()
    
    print(f"\n✅ Report saved to: {output_file}")


if __name__ == "__main__":
    main()