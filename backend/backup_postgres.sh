#!/bin/bash

# PostgreSQL Backup Script for FTP Media Sync (macOS)
# This script creates daily backups of the PostgreSQL database
# and manages retention of old backups

# Configuration
DB_NAME="ftp_media_sync"
DB_USER="jaypound"  # Using your macOS username for peer auth
DB_HOST="localhost"
DB_PORT="5432"

# No password needed - using peer authentication
# PostgreSQL on macOS with Homebrew typically uses peer auth for local connections

# Backup locations (recommended storage options for macOS)
# Option 1: User's home directory (recommended primary)
LOCAL_BACKUP_DIR="$HOME/postgres_backups/ftp-media-sync"

# Option 2: macOS standard backup location
# LOCAL_BACKUP_DIR="$HOME/Library/Application Support/PostgreSQL/backups/ftp-media-sync"

# Option 3: FTP server backup (recommended secondary)
# Enable FTP backup to both servers
FTP_BACKUP_DIR="/mnt/md127/Backups/postgres"
FTP_SERVER_SOURCE="source"  # castus1
FTP_SERVER_TARGET="target"  # castus2

# Option 4: External drive (if available)
# EXTERNAL_BACKUP_DIR="/Volumes/ExternalDrive/postgres_backups"

# Option 5: iCloud Drive (if you want cloud backup)
# ICLOUD_BACKUP_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Backups/postgres"

# Retention settings
RETENTION_DAYS=30  # Keep daily backups for 30 days
WEEKLY_RETENTION_DAYS=90  # Keep weekly backups for 90 days
MONTHLY_RETENTION_DAYS=365  # Keep monthly backups for 1 year

# PostgreSQL paths for macOS (adjust if needed)
# For Homebrew PostgreSQL (default):
PG_DUMP="/usr/local/bin/pg_dump"
# For Homebrew on Apple Silicon:
if [ ! -f "$PG_DUMP" ]; then
    PG_DUMP="/opt/homebrew/bin/pg_dump"
fi
# For Postgres.app:
# PG_DUMP="/Applications/Postgres.app/Contents/Versions/latest/bin/pg_dump"

# Check if pg_dump exists, fallback to system path
if [ ! -f "$PG_DUMP" ]; then
    PG_DUMP=$(which pg_dump)
fi

# Create timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DAY_OF_WEEK=$(date +"%u")  # 1=Monday, 7=Sunday
DAY_OF_MONTH=$(date +"%d")

# Create backup filename
BACKUP_FILENAME="ftp_media_sync_backup_${TIMESTAMP}.sql.gz"

# Ensure local backup directory exists
mkdir -p "$LOCAL_BACKUP_DIR"
mkdir -p "$LOCAL_BACKUP_DIR/daily"
mkdir -p "$LOCAL_BACKUP_DIR/weekly"
mkdir -p "$LOCAL_BACKUP_DIR/monthly"
mkdir -p "$LOCAL_BACKUP_DIR/logs"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOCAL_BACKUP_DIR/logs/backup.log"
}

# Function to send macOS notification
send_notification() {
    local title="$1"
    local message="$2"
    osascript -e "display notification \"$message\" with title \"$title\"" 2>/dev/null
}

# Function to perform backup
perform_backup() {
    local backup_path="$1"
    
    log_message "Starting PostgreSQL backup to: $backup_path"
    
    # Use pg_dump to create backup and compress with gzip
    "$PG_DUMP" \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --verbose \
        --no-owner \
        --no-privileges \
        --format=plain \
        --encoding=UTF8 2>"$LOCAL_BACKUP_DIR/logs/pg_dump_error.log" | gzip > "$backup_path"
    
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        local size=$(du -h "$backup_path" | cut -f1)
        log_message "Backup completed successfully. Size: $size"
        return 0
    else
        log_message "ERROR: Backup failed! Check $LOCAL_BACKUP_DIR/logs/pg_dump_error.log"
        rm -f "$backup_path"
        return 1
    fi
}

# Function to clean old backups
clean_old_backups() {
    local dir="$1"
    local days="$2"
    
    log_message "Cleaning backups older than $days days from $dir"
    
    find "$dir" -name "*.sql.gz" -type f -mtime +${days}d -delete 2>/dev/null
    
    # Count remaining backups
    local count=$(find "$dir" -name "*.sql.gz" -type f 2>/dev/null | wc -l)
    log_message "Remaining backups in $dir: $count"
}

# Main backup process
log_message "====== Starting PostgreSQL Backup Process ======"

# Check if PostgreSQL is running
if ! pgrep -x "postgres" > /dev/null; then
    log_message "ERROR: PostgreSQL is not running!"
    send_notification "Backup Failed" "PostgreSQL is not running"
    exit 1
fi

# 1. Create daily backup
DAILY_BACKUP_PATH="$LOCAL_BACKUP_DIR/daily/$BACKUP_FILENAME"
if perform_backup "$DAILY_BACKUP_PATH"; then
    
    # 2. Copy to weekly on Sundays
    if [ "$DAY_OF_WEEK" -eq 7 ]; then
        log_message "Creating weekly backup (Sunday)"
        cp "$DAILY_BACKUP_PATH" "$LOCAL_BACKUP_DIR/weekly/"
    fi
    
    # 3. Copy to monthly on 1st of month
    if [ "$DAY_OF_MONTH" -eq "01" ]; then
        log_message "Creating monthly backup (1st of month)"
        cp "$DAILY_BACKUP_PATH" "$LOCAL_BACKUP_DIR/monthly/"
    fi
    
    # 4. Copy to iCloud if configured
    if [ ! -z "$ICLOUD_BACKUP_DIR" ] && [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs" ]; then
        log_message "Copying backup to iCloud Drive"
        mkdir -p "$ICLOUD_BACKUP_DIR"
        cp "$DAILY_BACKUP_PATH" "$ICLOUD_BACKUP_DIR/"
    fi
    
    # 5. Upload to FTP servers if configured
    if [ ! -z "$FTP_BACKUP_DIR" ]; then
        # Upload to source server (castus1)
        if [ ! -z "$FTP_SERVER_SOURCE" ]; then
            log_message "Uploading backup to source FTP server (castus1)"
            
            cd /Users/jaypound/git/ftp-media-sync/backend
            python3 << EOF
import sys
from ftp_manager import FTPManager
import config_manager

try:
    cm = config_manager.ConfigManager()
    config = cm.get_server_config('$FTP_SERVER_SOURCE')
    ftp = FTPManager(config)
    if ftp.connect():
        # Create directory if it doesn't exist
        ftp.create_directory('$FTP_BACKUP_DIR')
        success = ftp.upload_file('$DAILY_BACKUP_PATH', '$FTP_BACKUP_DIR/$BACKUP_FILENAME')
        if success:
            print("FTP upload to castus1 successful")
        else:
            print("FTP upload to castus1 failed")
        ftp.disconnect()
except Exception as e:
    print(f"FTP upload error (castus1): {str(e)}")
EOF
        fi
        
        # Upload to target server (castus2)
        if [ ! -z "$FTP_SERVER_TARGET" ]; then
            log_message "Uploading backup to target FTP server (castus2)"
            
            cd /Users/jaypound/git/ftp-media-sync/backend
            python3 << EOF
import sys
from ftp_manager import FTPManager
import config_manager

try:
    cm = config_manager.ConfigManager()
    config = cm.get_server_config('$FTP_SERVER_TARGET')
    ftp = FTPManager(config)
    if ftp.connect():
        # Create directory if it doesn't exist
        ftp.create_directory('$FTP_BACKUP_DIR')
        success = ftp.upload_file('$DAILY_BACKUP_PATH', '$FTP_BACKUP_DIR/$BACKUP_FILENAME')
        if success:
            print("FTP upload to castus2 successful")
        else:
            print("FTP upload to castus2 failed")
        ftp.disconnect()
except Exception as e:
    print(f"FTP upload error (castus2): {str(e)}")
EOF
        fi
    fi
    
    # 6. Copy to external drive if available and mounted
    if [ ! -z "$EXTERNAL_BACKUP_DIR" ]; then
        # Check if external drive is mounted
        EXTERNAL_VOLUME=$(echo "$EXTERNAL_BACKUP_DIR" | cut -d'/' -f3)
        if [ -d "/Volumes/$EXTERNAL_VOLUME" ]; then
            log_message "Copying backup to external drive"
            mkdir -p "$EXTERNAL_BACKUP_DIR"
            cp "$DAILY_BACKUP_PATH" "$EXTERNAL_BACKUP_DIR/"
        else
            log_message "External drive not mounted, skipping external backup"
        fi
    fi
    
    send_notification "Backup Success" "PostgreSQL backup completed successfully"
    
else
    log_message "ERROR: Primary backup failed. Aborting."
    send_notification "Backup Failed" "PostgreSQL backup failed. Check logs."
    exit 1
fi

# 7. Clean old backups
clean_old_backups "$LOCAL_BACKUP_DIR/daily" "$RETENTION_DAYS"
clean_old_backups "$LOCAL_BACKUP_DIR/weekly" "$WEEKLY_RETENTION_DAYS"
clean_old_backups "$LOCAL_BACKUP_DIR/monthly" "$MONTHLY_RETENTION_DAYS"

# Clean old FTP backups
if [ ! -z "$FTP_BACKUP_DIR" ]; then
    log_message "Cleaning old backups from FTP servers"
    
    cd /Users/jaypound/git/ftp-media-sync/backend
    python3 << EOF
import sys
from datetime import datetime, timedelta
from ftp_manager import FTPManager
import config_manager

def clean_ftp_backups(server_name, ftp_dir, retention_days):
    try:
        cm = config_manager.ConfigManager()
        config = cm.get_server_config(server_name)
        ftp = FTPManager(config)
        if ftp.connect():
            # List files in backup directory
            files = ftp.list_files(ftp_dir)
            if files:
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                for file_info in files:
                    filename = file_info.get('name', '')
                    # Parse date from filename (ftp_media_sync_backup_YYYYMMDD_HHMMSS.sql.gz)
                    if filename.startswith('ftp_media_sync_backup_') and filename.endswith('.sql.gz'):
                        try:
                            # Split: ['ftp', 'media', 'sync', 'backup', 'YYYYMMDD', 'HHMMSS.sql.gz']
                            parts = filename.split('_')
                            date_str = parts[4] + parts[5].split('.')[0]
                            file_date = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                            if file_date < cutoff_date:
                                ftp.ftp.delete(f"{ftp_dir}/{filename}")
                                print(f"Deleted old backup from {server_name}: {filename}")
                        except Exception as e:
                            print(f"Error parsing date from {filename}: {e}")
            ftp.disconnect()
    except Exception as e:
        print(f"Error cleaning FTP backups on {server_name}: {str(e)}")

# Clean both servers
clean_ftp_backups('$FTP_SERVER_SOURCE', '$FTP_BACKUP_DIR', $RETENTION_DAYS)
clean_ftp_backups('$FTP_SERVER_TARGET', '$FTP_BACKUP_DIR', $RETENTION_DAYS)
EOF
fi

# 8. Verify backup integrity
log_message "Verifying backup integrity"
if gunzip -t "$DAILY_BACKUP_PATH" 2>/dev/null; then
    log_message "Backup integrity check passed"
else
    log_message "WARNING: Backup integrity check failed!"
    send_notification "Backup Warning" "Backup integrity check failed!"
fi

# 9. Log disk space
DISK_USAGE=$(df -h "$LOCAL_BACKUP_DIR" | tail -1 | awk '{print $5}')
log_message "Backup directory disk usage: $DISK_USAGE"

log_message "====== Backup Process Completed ======"

exit 0