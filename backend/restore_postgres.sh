#!/bin/bash

# PostgreSQL Restore Script for FTP Media Sync
# This script restores a PostgreSQL database from a backup

# Configuration
DB_NAME="ftp_media_sync"
DB_USER="jaypound"
DB_HOST="localhost"
DB_PORT="5432"

# Backup directory
BACKUP_DIR="$HOME/postgres_backups/ftp-media-sync"

# PostgreSQL paths for macOS (Homebrew)
PG_RESTORE="/usr/local/bin/psql"
DROPDB="/usr/local/bin/dropdb"
CREATEDB="/usr/local/bin/createdb"
PG_DUMP="/usr/local/bin/pg_dump"

# Check for Apple Silicon paths
if [ ! -f "$PG_RESTORE" ]; then
    PG_RESTORE="/opt/homebrew/bin/psql"
    DROPDB="/opt/homebrew/bin/dropdb"
    CREATEDB="/opt/homebrew/bin/createdb"
    PG_DUMP="/opt/homebrew/bin/pg_dump"
fi

# Check if commands exist, fallback to system path
if [ ! -f "$PG_RESTORE" ]; then
    PG_RESTORE=$(which psql)
fi
if [ ! -f "$DROPDB" ]; then
    DROPDB=$(which dropdb)
fi
if [ ! -f "$CREATEDB" ]; then
    CREATEDB=$(which createdb)
fi

echo "PostgreSQL Restore Utility"
echo "========================="
echo ""

# Function to list available backups
list_backups() {
    echo "Available backups:"
    echo ""
    echo "LOCAL BACKUPS:"
    echo "--------------"
    echo "Daily backups:"
    ls -la "$BACKUP_DIR/daily/"*.sql.gz 2>/dev/null | tail -10
    echo ""
    echo "Weekly backups:"
    ls -la "$BACKUP_DIR/weekly/"*.sql.gz 2>/dev/null | tail -5
    echo ""
    echo "Monthly backups:"
    ls -la "$BACKUP_DIR/monthly/"*.sql.gz 2>/dev/null | tail -5
}

# Function to list FTP backups
list_ftp_backups() {
    echo ""
    echo "FTP BACKUPS:"
    echo "------------"
    
    cd /Users/jaypound/git/ftp-media-sync/backend
    python3 << EOF
import sys
from ftp_manager import FTPManager
import config_manager

def list_server_backups(server_name, ftp_dir):
    try:
        cm = config_manager.ConfigManager()
        config = cm.get_server_config(server_name)
        ftp = FTPManager(config)
        if ftp.connect():
            files = ftp.list_files(ftp_dir)
            if files:
                print(f"\n{server_name.upper()} server backups:")
                # Sort by filename (which includes timestamp) in reverse order
                backup_files = [f for f in files if f['name'].startswith('ftp_media_sync_backup_') and f['name'].endswith('.sql.gz')]
                backup_files.sort(key=lambda x: x['name'], reverse=True)
                for f in backup_files[:10]:  # Show last 10
                    size_mb = f.get('size', 0) / (1024 * 1024)
                    print(f"  {f['name']} ({size_mb:.1f} MB)")
            ftp.disconnect()
    except Exception as e:
        print(f"Error listing {server_name} backups: {str(e)}")

list_server_backups('source', '/mnt/md127/Backups/postgres')
list_server_backups('target', '/mnt/md127/Backups/postgres')
EOF
}

# List available backups
list_backups
list_ftp_backups

echo ""
echo "To restore from FTP, enter: ftp:source:/path/to/file or ftp:target:/path/to/file"
echo "To restore from local, enter the full local path"
echo ""
echo "Enter the backup file to restore:"
read BACKUP_FILE

# Check if it's an FTP restore
if [[ "$BACKUP_FILE" == ftp:* ]]; then
    # Parse FTP path
    FTP_SERVER=$(echo "$BACKUP_FILE" | cut -d: -f2)
    FTP_PATH=$(echo "$BACKUP_FILE" | cut -d: -f3-)
    
    echo "Downloading backup from $FTP_SERVER server..."
    
    # Download to temp file
    TEMP_BACKUP="/tmp/postgres_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
    
    cd /Users/jaypound/git/ftp-media-sync/backend
    python3 << EOF
import sys
from ftp_manager import FTPManager
import config_manager

try:
    cm = config_manager.ConfigManager()
    config = cm.get_server_config('$FTP_SERVER')
    ftp = FTPManager(config)
    if ftp.connect():
        success = ftp.download_file('$FTP_PATH', '$TEMP_BACKUP')
        if success:
            print("Download successful")
            sys.exit(0)
        else:
            print("Download failed")
            sys.exit(1)
        ftp.disconnect()
except Exception as e:
    print(f"FTP download error: {str(e)}")
    sys.exit(1)
EOF
    
    if [ $? -ne 0 ]; then
        echo "Failed to download backup from FTP"
        exit 1
    fi
    
    BACKUP_FILE="$TEMP_BACKUP"
    CLEANUP_TEMP=true
fi

# Check if file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Verify it's a gzip file
if ! file "$BACKUP_FILE" | grep -q "gzip compressed data"; then
    echo "Error: File is not a valid gzipped backup"
    exit 1
fi

echo ""
echo "WARNING: This will DROP and RECREATE the database '$DB_NAME'"
echo "All current data will be lost!"
echo ""
echo "Type 'YES' to continue:"
read CONFIRM

if [ "$CONFIRM" != "YES" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""
echo "Creating backup of current database before restore..."
SAFETY_BACKUP="$BACKUP_DIR/safety_backup_$(date +%Y%m%d_%H%M%S).sql.gz"
"$PG_DUMP" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" | gzip > "$SAFETY_BACKUP"

if [ $? -eq 0 ]; then
    echo "Safety backup created: $SAFETY_BACKUP"
else
    echo "Warning: Failed to create safety backup. Continue anyway? (yes/no)"
    read CONTINUE
    if [ "$CONTINUE" != "yes" ]; then
        exit 1
    fi
fi

echo ""
echo "Starting restore process..."

# Drop existing database
echo "Dropping existing database..."
"$DROPDB" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"

# Create new database
echo "Creating new database..."
"$CREATEDB" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"

# Restore from backup
echo "Restoring from backup..."
gunzip -c "$BACKUP_FILE" | "$PG_RESTORE" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Restore completed successfully!"
    echo ""
    echo "Verifying restore..."
    
    # Run some verification queries
    "$PG_RESTORE" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << EOF
SELECT 'Tables:', COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';
SELECT 'Schedules:', COUNT(*) FROM schedules;
SELECT 'Scheduled Items:', COUNT(*) FROM scheduled_items;
SELECT 'Assets:', COUNT(*) FROM assets;
EOF
    
else
    echo ""
    echo "✗ Restore failed!"
    echo ""
    echo "To restore the safety backup, run:"
    echo "$0"
    echo "And select: $SAFETY_BACKUP"
    exit 1
fi

echo ""
echo "Restore process completed."

# Clean up temp file if downloaded from FTP
if [ "$CLEANUP_TEMP" = true ] && [ -f "$TEMP_BACKUP" ]; then
    rm -f "$TEMP_BACKUP"
    echo "Cleaned up temporary file."
fi

echo "Please restart the FTP Media Sync application to use the restored database."