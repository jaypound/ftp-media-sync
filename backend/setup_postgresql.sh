#!/bin/bash
# Setup script for PostgreSQL database

echo "FTP Media Sync - PostgreSQL Setup"
echo "================================="
echo ""

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "Error: PostgreSQL is not installed."
    echo "Please install PostgreSQL first:"
    echo "  - macOS: brew install postgresql"
    echo "  - Ubuntu/Debian: sudo apt-get install postgresql postgresql-contrib"
    echo "  - RHEL/CentOS: sudo yum install postgresql-server postgresql-contrib"
    exit 1
fi

# Database configuration
DB_NAME="${DB_NAME:-ftp_media_sync}"
DB_USER="${DB_USER:-$USER}"  # Use current macOS user by default
DB_PASSWORD="${DB_PASSWORD:-}"  # No password needed for local connections
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

echo "Database Configuration:"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Host: $DB_HOST:$DB_PORT"
echo ""

# Create database if it doesn't exist
echo "Creating database if it doesn't exist..."
if [ -z "$DB_PASSWORD" ]; then
    # No password (typical for local macOS Homebrew installation)
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME"
else
    # With password
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME"
fi

# Apply schema
echo "Applying database schema..."
if [ -z "$DB_PASSWORD" ]; then
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f schema.sql
else
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f schema.sql
fi

if [ $? -eq 0 ]; then
    echo ""
    echo "Database setup completed successfully!"
    echo ""
    echo "To use PostgreSQL instead of MongoDB, set the following environment variable:"
    echo "  export USE_POSTGRESQL=true"
    if [ -z "$DB_PASSWORD" ]; then
        echo "  export DATABASE_URL=\"postgresql://$DB_USER@$DB_HOST:$DB_PORT/$DB_NAME\""
    else
        echo "  export DATABASE_URL=\"postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME\""
    fi
    echo ""
    echo "To migrate data from MongoDB to PostgreSQL, run:"
    echo "  python migrate_mongodb_to_postgresql.py"
else
    echo ""
    echo "Error: Database setup failed!"
    exit 1
fi