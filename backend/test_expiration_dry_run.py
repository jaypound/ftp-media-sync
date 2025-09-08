#!/usr/bin/env python3
"""
Dry run test - Check content expirations without updating database
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
        self.log.flush()
    
    def close(self):
        self.log.close()


def get_sample_content(limit=20):
    """Get a sample of content for dry run"""
    db = PostgreSQLDatabaseManager()
    
    if not db.connect():
        print("❌ Failed to connect to database")
        return []
    
    try:
        conn = db._get_connection()
        with conn.cursor() as cursor:
            # Get a mix of synced and unsynced content
            cursor.execute("""
                (
                    -- First get some unsynced content
                    SELECT 
                        a.id as asset_id,
                        a.content_type,
                        a.content_title,
                        i.file_name,
                        i.file_path,
                        sm.content_expiry_date,
                        sm.metadata_synced_at,
                        'Never synced' as sync_status
                    FROM assets a
                    JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE sm.metadata_synced_at IS NULL
                    AND a.content_type IS NOT NULL
                    LIMIT %s
                )
                UNION ALL
                (
                    -- Then get some previously synced content
                    SELECT 
                        a.id as asset_id,
                        a.content_type,
                        a.content_title,
                        i.file_name,
                        i.file_path,
                        sm.content_expiry_date,
                        sm.metadata_synced_at,
                        'Previously synced' as sync_status
                    FROM assets a
                    JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE sm.metadata_synced_at IS NOT NULL
                    AND a.content_type IS NOT NULL
                    LIMIT %s
                )
                ORDER BY sync_status, content_type, content_title
            """, (limit // 2, limit // 2))
            
            results = cursor.fetchall()
            return results
            
    finally:
        db._put_connection(conn)
        db.disconnect()


def check_expirations_dry_run(assets, output):
    """Check expiration dates without updating database"""
    # Setup FTP connection
    config_mgr = ConfigManager()
    all_config = config_mgr.get_all_config()
    server_config = all_config['servers']['source']
    
    ftp = FTPManager(server_config)
    if not ftp.connect():
        output.write("❌ Failed to connect to FTP server\n")
        return
    
    handler = CastusMetadataHandler(ftp)
    
    # Statistics
    stats = {
        'total': len(assets),
        'has_metadata': 0,
        'no_metadata': 0,
        'changed': 0,
        'errors': 0,
        'expiring_soon': [],
        'expired': []
    }
    
    output.write(f"\n{'='*100}\n")
    output.write(f"DRY RUN - CHECKING {len(assets)} SAMPLE ASSETS\n")
    output.write(f"{'='*100}\n\n")
    
    for i, asset in enumerate(assets, 1):
        file_name = asset['file_name']
        file_path = asset['file_path']
        current_expiry = asset['content_expiry_date']
        sync_status = asset['sync_status']
        
        # Construct full path
        if not file_path.startswith('/'):
            full_path = f"/mnt/md127/ATL26 On-Air Content/{file_path}"
        else:
            full_path = file_path
        
        output.write(f"{i}/{len(assets)}: {file_name}\n")
        output.write(f"   Type: {asset['content_type']} | Status: {sync_status}\n")
        
        if current_expiry:
            output.write(f"   Current DB expiry: {current_expiry.strftime('%Y-%m-%d')}\n")
        
        try:
            # Try to get expiration from Castus
            expiration = handler.get_content_window_close(full_path)
            
            if expiration:
                output.write(f"   ✅ Castus expiration: {expiration.strftime('%Y-%m-%d %H:%M:%S')}\n")
                stats['has_metadata'] += 1
                
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
                        current_expiry_compare = current_expiry.replace(tzinfo=None)
                    else:
                        current_expiry_compare = current_expiry
                        
                    if expiration.tzinfo:
                        exp_compare = expiration.replace(tzinfo=None)
                    else:
                        exp_compare = expiration
                    
                    diff_days = abs((current_expiry_compare - exp_compare).days)
                    if diff_days > 1:
                        output.write(f"   ⚠️  DIFFERENCE: {diff_days} days\n")
                        stats['changed'] += 1
                
                # Track expiring content
                if days_left < 0:
                    stats['expired'].append((file_name, days_left))
                elif days_left < 30:
                    stats['expiring_soon'].append((file_name, days_left))
                    
            else:
                output.write(f"   ❌ No Castus metadata found\n")
                stats['no_metadata'] += 1
                
        except Exception as e:
            output.write(f"   ❌ Error: {str(e)}\n")
            stats['errors'] += 1
        
        output.write("\n")
    
    # Cleanup
    ftp.disconnect()
    
    # Print summary
    output.write(f"\n{'='*100}\n")
    output.write(f"DRY RUN SUMMARY\n")
    output.write(f"{'='*100}\n\n")
    
    output.write(f"Sample size: {stats['total']} assets\n")
    output.write(f"✅ Has Castus metadata: {stats['has_metadata']}\n")
    output.write(f"📄 No metadata found: {stats['no_metadata']}\n")
    output.write(f"⚠️  Expiry dates changed: {stats['changed']}\n")
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
    
    # Metadata availability rate
    if stats['total'] > 0:
        metadata_rate = (stats['has_metadata'] / stats['total']) * 100
        output.write(f"Metadata availability: {metadata_rate:.1f}%\n")
        
        if stats['changed'] > 0:
            change_rate = (stats['changed'] / stats['has_metadata']) * 100 if stats['has_metadata'] > 0 else 0
            output.write(f"Expiry dates that would change: {change_rate:.1f}%\n")
    
    output.write(f"\n📝 This was a DRY RUN - no database changes were made\n")


def main():
    # Create output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"expiration_dry_run_{timestamp}.txt"
    
    # Setup dual output
    output = DualOutput(output_file)
    
    output.write(f"🚀 CASTUS METADATA EXPIRATION CHECK - DRY RUN\n")
    output.write(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write(f"📄 Output file: {output_file}\n")
    
    # Get sample assets
    output.write(f"\n📊 Fetching sample content from database...\n")
    
    # You can adjust the sample size here
    sample_size = 30
    assets = get_sample_content(limit=sample_size)
    
    if not assets:
        output.write("❌ No assets found in database\n")
        output.close()
        return
    
    output.write(f"✅ Found {len(assets)} assets for dry run\n")
    
    # Show breakdown
    never_synced = len([a for a in assets if a['sync_status'] == 'Never synced'])
    previously_synced = len([a for a in assets if a['sync_status'] == 'Previously synced'])
    
    output.write(f"   - Never synced: {never_synced}\n")
    output.write(f"   - Previously synced: {previously_synced}\n")
    
    # Check expirations
    check_expirations_dry_run(assets, output)
    
    output.write(f"\n✅ Dry run complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.close()
    
    print(f"\n✅ Report saved to: {output_file}")


if __name__ == "__main__":
    main()