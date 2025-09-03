#!/bin/bash

# Setup script for PostgreSQL backup on macOS

echo "PostgreSQL Backup Setup for macOS"
echo "================================="

# Make backup script executable
chmod +x backup_postgres.sh

# Create backup directories
echo "Creating backup directories..."
mkdir -p "$HOME/postgres_backups/ftp-media-sync/daily"
mkdir -p "$HOME/postgres_backups/ftp-media-sync/weekly"
mkdir -p "$HOME/postgres_backups/ftp-media-sync/monthly"
mkdir -p "$HOME/postgres_backups/ftp-media-sync/logs"

# Check PostgreSQL installation
echo "Checking PostgreSQL installation..."
if command -v pg_dump &> /dev/null; then
    echo "✓ Found PostgreSQL in PATH: $(which pg_dump)"
    PG_PATH=$(dirname $(which pg_dump))
elif [ -f "/opt/homebrew/bin/pg_dump" ]; then
    echo "✓ Found Homebrew PostgreSQL (Apple Silicon)"
    PG_PATH="/opt/homebrew/bin"
elif [ -f "/usr/local/bin/pg_dump" ]; then
    echo "✓ Found Homebrew PostgreSQL (Intel)"
    PG_PATH="/usr/local/bin"
else
    echo "✗ PostgreSQL not found. Please install PostgreSQL first."
    exit 1
fi

# No password setup needed for peer authentication
echo "✓ Using peer authentication (no password required)"

# Test database connection
echo ""
echo "Testing database connection..."
if "$PG_PATH/psql" -U jaypound -d ftp_media_sync -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✓ Successfully connected to database 'ftp_media_sync' as user 'jaypound'"
else
    echo "✗ Failed to connect to database. Please ensure PostgreSQL is running."
    exit 1
fi

# Install launchd service
echo ""
echo "Installing launchd service..."
PLIST_FILE="com.ftpmediasync.postgres-backup.plist"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$LAUNCHD_DIR"

# Copy plist file to LaunchAgents
cp "$PLIST_FILE" "$LAUNCHD_DIR/"

# Load the service
launchctl unload "$LAUNCHD_DIR/$PLIST_FILE" 2>/dev/null
launchctl load -w "$LAUNCHD_DIR/$PLIST_FILE"

if launchctl list | grep -q "com.ftpmediasync.postgres-backup"; then
    echo "✓ Backup service installed successfully"
else
    echo "✗ Failed to install backup service"
    exit 1
fi

# Test backup
echo ""
echo "Running test backup..."
./backup_postgres.sh

if [ $? -eq 0 ]; then
    echo "✓ Test backup completed successfully"
    echo ""
    echo "Backup Location: $HOME/postgres_backups/ftp-media-sync"
    ls -la "$HOME/postgres_backups/ftp-media-sync/daily/"
else
    echo "✗ Test backup failed. Check the logs."
    exit 1
fi

echo ""
echo "Setup completed!"
echo ""
echo "Backup Schedule: Daily at 2:00 AM"
echo "Backup Locations:"
echo "  - Local: $HOME/postgres_backups/ftp-media-sync"
echo "  - FTP: /mnt/md127/Backups/postgres/ (on both castus1 and castus2)"
echo ""
echo "Retention Policy:"
echo "  - Daily backups: 30 days"
echo "  - Weekly backups: 90 days (Sundays)"
echo "  - Monthly backups: 365 days (1st of month)"
echo ""
echo "Commands:"
echo "  - Manual backup: ./backup_postgres.sh"
echo "  - Restore: ./restore_postgres.sh"
echo "  - Check status: launchctl list | grep postgres-backup"
echo "  - View logs: tail -f $HOME/postgres_backups/ftp-media-sync/logs/backup.log"
echo ""
echo "To disable/enable backups:"
echo "  - Disable: launchctl unload ~/Library/LaunchAgents/com.ftpmediasync.postgres-backup.plist"
echo "  - Enable: launchctl load ~/Library/LaunchAgents/com.ftpmediasync.postgres-backup.plist"