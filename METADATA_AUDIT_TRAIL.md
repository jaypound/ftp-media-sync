# Metadata Audit Trail System

## Overview

The Metadata Audit Trail system provides comprehensive tracking and logging of all changes to content expiration and go-live dates. This system ensures accountability, enables historical analysis, and provides insights into content lifecycle management.

## Architecture

### Database Schema

#### metadata_audit_log Table
```sql
CREATE TABLE metadata_audit_log (
    id SERIAL PRIMARY KEY,
    asset_id VARCHAR(255) NOT NULL,
    instance_id INTEGER,
    field_name VARCHAR(50) NOT NULL, -- 'content_expiry_date' or 'go_live_date'
    old_value TIMESTAMP,
    new_value TIMESTAMP,
    changed_by VARCHAR(255),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_source VARCHAR(100), -- 'web_ui', 'api', 'bulk_operation', etc.
    change_reason TEXT, -- optional reason/note
    
    -- Foreign key with cascade delete
    CONSTRAINT fk_asset
        FOREIGN KEY (asset_id) 
        REFERENCES assets(id) 
        ON DELETE CASCADE,
    
    -- Indexes for performance
    INDEX idx_asset_id (asset_id),
    INDEX idx_changed_at (changed_at),
    INDEX idx_field_name (field_name)
);
```

### System Components

#### Backend Services

1. **AuditService (database_postgres.py)**
   - `log_metadata_change()` - Records metadata changes
   - `get_asset_audit_history()` - Retrieves history for specific asset
   - `get_all_audit_logs()` - Retrieves all changes with filtering
   - `cleanup_old_audit_logs()` - Removes old audit entries

2. **Integration Points**
   - Content expiration updates
   - Go-live date modifications
   - Bulk operations
   - API-based updates

#### API Endpoints

| Endpoint | Method | Description | Parameters |
|----------|--------|-------------|------------|
| `/api/metadata-audit/<asset_id>` | GET | Get audit history for specific asset | - |
| `/api/metadata-audit-log` | GET | Get all audit logs | date_from, date_to, field_name, page, limit |
| `/api/metadata-audit/export` | GET | Export audit logs to CSV | date_from, date_to, field_name |

## User Interface

### 1. Available Content Table Enhancement

Each row in the Available Content table will include an audit history icon:

```
┌─────────────────────────────────────────────────────────┐
│ Title          │ Expiration  │ Go Live  │ Actions      │
├─────────────────────────────────────────────────────────┤
│ Video Title    │ 2025-01-15  │ 2024-12-01 │ [📋] [✏️]   │
└─────────────────────────────────────────────────────────┘
```

Clicking the 📋 icon opens a modal showing the asset's metadata history.

### 2. Audit History Modal

```
╔═══════════════════════════════════════════════════════════╗
║ [Asset Title] - Metadata Change History                   ║
╠═══════════════════════════════════════════════════════════╣
║ Date/Time          │ Field      │ From       │ To         ║
║────────────────────┼────────────┼────────────┼────────────║
║ 2024-12-12 15:45  │ Expiration │ 2024-12-31 │ 2025-01-15 ║
║ 2024-12-10 09:30  │ Go Live    │ (not set)  │ 2024-12-15 ║
║ 2024-12-08 14:22  │ Expiration │ 2024-12-15 │ 2024-12-31 ║
╚═══════════════════════════════════════════════════════════╝
```

### 3. Metadata Change Log Page

Accessible via "Metadata Change Log" button on Content Expiration page:

```
╔═══════════════════════════════════════════════════════════╗
║ Metadata Change Log                                       ║
╠═══════════════════════════════════════════════════════════╣
║ [Date Filter] [Field Filter] [Export CSV]                 ║
║───────────────────────────────────────────────────────────║
║ Date/Time      │ Asset        │ Field      │ Old → New   ║
║────────────────┼──────────────┼────────────┼─────────────║
║ 2024-12-12     │ News Segment │ Expiration │ 12/31→01/15 ║
║ 15:45:32       │              │            │             ║
║────────────────┼──────────────┼────────────┼─────────────║
║ 2024-12-12     │ Weather      │ Go Live    │ None→12/15  ║
║ 14:30:15       │ Update       │            │             ║
╚═══════════════════════════════════════════════════════════╝
```

## Features

### Core Features
1. **Automatic Change Tracking** - All metadata changes are automatically logged
2. **Cascading Deletes** - Audit logs are removed when assets are deleted
3. **Change Attribution** - Track who made changes and when
4. **Change Source Tracking** - Identify if changes came from UI, API, or bulk operations

### Advanced Features

#### 1. Audit Retention Policy
- Configurable retention period (default: 365 days)
- Automated cleanup via scheduled job
- Archive option for long-term storage

#### 2. Change Notifications
- Real-time notifications for critical changes
- Email alerts for expiration date modifications
- Dashboard widget showing recent activity

#### 3. Export and Reporting
- CSV export functionality
- Scheduled reports
- API access for external systems

#### 4. Visual Timeline
- Graphical representation of changes over time
- Color coding by change type
- Interactive hover details

## Implementation Guidelines

### Audit Logging Best Practices

1. **Always log both old and new values**
   ```python
   def update_expiration(asset_id, new_date):
       old_date = get_current_expiration(asset_id)
       # Update the expiration
       log_metadata_change(
           asset_id=asset_id,
           field_name='content_expiry_date',
           old_value=old_date,
           new_value=new_date
       )
   ```

2. **Include context information**
   - User identification
   - Change source (UI, API, bulk operation)
   - Optional reason for change

3. **Handle bulk operations efficiently**
   - Batch insert audit logs
   - Use transactions for consistency

### Performance Considerations

1. **Indexing Strategy**
   - Index on asset_id for fast lookups
   - Index on changed_at for time-based queries
   - Composite index for common query patterns

2. **Data Retention**
   - Regular cleanup of old audit logs
   - Consider partitioning for large datasets

3. **Query Optimization**
   - Paginate results for UI display
   - Use database views for complex queries

## Security and Compliance

### Access Control
- Audit logs are read-only
- Role-based permissions for viewing
- No ability to modify or delete individual audit entries

### Data Integrity
- Database constraints ensure consistency
- Transactions for atomic operations
- Regular backup of audit data

### Compliance Features
- Immutable audit trail
- Complete change history
- Export capabilities for auditors

## Migration and Rollout

### Phase 1: Database Setup
1. Create audit table and indexes
2. Set up foreign key constraints
3. Create database functions and triggers

### Phase 2: Backend Implementation
1. Implement audit service
2. Integrate with existing update code
3. Add API endpoints

### Phase 3: Frontend Development
1. Add history icons to Available Content
2. Create audit history modal
3. Build Metadata Change Log page

### Phase 4: Advanced Features
1. Implement retention policies
2. Add export functionality
3. Create reporting capabilities

## Monitoring and Maintenance

### Key Metrics
- Audit log growth rate
- Query performance
- Storage utilization

### Maintenance Tasks
- Regular cleanup of old logs
- Index optimization
- Performance monitoring

### Troubleshooting
- Check for missing audit entries
- Verify cascade delete operations
- Monitor for performance issues

## Future Enhancements

1. **Machine Learning Integration**
   - Anomaly detection for unusual changes
   - Pattern recognition for optimization

2. **Advanced Visualization**
   - Heat maps of change frequency
   - Predictive analytics

3. **Integration Capabilities**
   - Webhook notifications
   - Third-party audit system integration
   - Compliance reporting APIs