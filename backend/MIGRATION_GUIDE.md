# MongoDB to PostgreSQL Migration Guide

This guide explains how to migrate your FTP Media Sync application from MongoDB to PostgreSQL.

## Why PostgreSQL?

The PostgreSQL schema provides several advantages:

1. **Normalized Data Structure**: Separates assets from file instances, tags, and metadata
2. **Better Query Performance**: Full-text search indexes on transcripts and summaries
3. **Data Integrity**: Foreign key constraints and data validation
4. **Flexibility**: Supports both structured data and flexible metadata
5. **Scalability**: Better support for complex queries and reporting

## Migration Steps

### 1. Install PostgreSQL

```bash
# macOS
brew install postgresql

# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# RHEL/CentOS
sudo yum install postgresql-server postgresql-contrib
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create PostgreSQL Database

Run the setup script:

```bash
cd backend
./setup_postgresql.sh
```

Or manually:

```bash
# Create database
createdb ftp_media_sync

# Apply schema
psql -d ftp_media_sync -f schema.sql
```

### 4. Configure Environment Variables

Add to your `.env` file:

```bash
# Enable PostgreSQL
USE_POSTGRESQL=true

# PostgreSQL connection
DATABASE_URL=postgresql://postgres:password@localhost/ftp_media_sync

# Keep MongoDB settings for migration
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=castus
```

### 5. Run Migration Script

```bash
python migrate_mongodb_to_postgresql.py \
  --mongo-uri "mongodb://localhost:27017/" \
  --pg-connection "postgresql://postgres:password@localhost/ftp_media_sync" \
  --batch-size 100
```

The migration script will:
- Connect to both databases
- Migrate all analysis records
- Preserve MongoDB ObjectIds for rollback capability
- Convert tags and metadata to normalized structure
- Maintain all scheduling information

### 6. Verify Migration

Check the migration results:

```sql
-- Connect to PostgreSQL
psql -d ftp_media_sync

-- Check asset count
SELECT COUNT(*) FROM assets;

-- View sample data
SELECT * FROM v_asset_details LIMIT 5;

-- Check tags
SELECT COUNT(*) as tag_count, type_name 
FROM tags t 
JOIN tag_types tt ON t.tag_type_id = tt.id 
GROUP BY type_name;
```

### 7. Switch Application to PostgreSQL

Once migration is verified, the application will automatically use PostgreSQL when `USE_POSTGRESQL=true` is set.

## Database Schema Overview

### Main Tables

1. **assets**: Core content metadata
2. **instances**: Physical file information
3. **tags**: Categorization system
4. **metadata**: Flexible key-value storage
5. **scheduling_metadata**: Scheduling history and metrics
6. **schedules**: Broadcast schedules
7. **scheduled_items**: Items within schedules

### Key Features

- **Full-text search** on transcripts and summaries
- **Normalized tags** for better categorization
- **Flexible metadata** for custom fields
- **Scheduling support** with history tracking
- **View helpers** for common queries

## Rollback Plan

If you need to rollback to MongoDB:

1. Set `USE_POSTGRESQL=false` in environment
2. The application will automatically use MongoDB
3. All MongoDB data remains untouched during migration

## Performance Considerations

- The PostgreSQL schema includes indexes for common queries
- Full-text search indexes improve transcript searches
- Consider partitioning for very large datasets
- Use connection pooling for better performance

## Troubleshooting

### Connection Issues

```bash
# Test PostgreSQL connection
psql -h localhost -U postgres -d ftp_media_sync -c "SELECT 1"

# Check if service is running
# macOS
brew services list | grep postgresql

# Linux
sudo systemctl status postgresql
```

### Migration Errors

- Check logs for specific error messages
- Ensure both databases are accessible
- Verify data types match schema constraints
- Run with smaller batch sizes if memory issues occur

### Schema Issues

```bash
# Drop and recreate schema
psql -d ftp_media_sync -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
psql -d ftp_media_sync -f schema.sql
```

## Support

For issues or questions:
1. Check application logs
2. Review PostgreSQL logs
3. Verify environment variables
4. Test database connections independently