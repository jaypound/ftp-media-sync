# Schedule Workflow Documentation

## Overview
The schedule creation and management system follows a three-step workflow to create weekly broadcast schedules.

## Workflow Steps

### Step 1: Import Weekly Meetings
- Weekly meetings are imported into a schedule template
- Meeting information includes:
  - Meeting name
  - Date and time
  - Duration
  - Type (live broadcast)
- Creates the foundation schedule with fixed meeting times

### Step 2: Fill Template Gaps
- The system runs gap-filling logic to populate available time slots
- Content is added before and after live meetings
- Follows content rotation rules (ID, SPOTS, SHORT_FORM, LONG_FORM)
- Respects replay delays to prevent content repetition
- **Important**: Leaves gaps for default content before and after live meetings
- Default content gaps ensure smooth transitions around live broadcasts

### Step 3: Export to Castus
- The completed schedule is exported to both Castus1 and Castus2 servers
- Export format is compatible with Castus automation system
- Includes all scheduled content with precise timing
- Default content videos are selected during export (newest video in /mnt/main/Videos)

## Key Components

### Meeting Import
- Source: PDF meeting schedules or manual entry
- Destination: Schedule template in database

### Gap Filling Algorithm
- Analyzes time slots between meetings
- Selects appropriate content based on:
  - Duration categories
  - Content availability
  - Replay delay restrictions
  - Featured content rules
  
### Default Content Gaps
- Preserved before and after each live meeting
- Filled with latest video from /mnt/main/Videos during export
- Ensures smooth transitions for live broadcasts

### Export Process
- Generates Castus-compatible schedule files
- Uploads via FTP to both Castus servers
- Includes all timing and content information

## Integration Points

### Meeting Promos (New Feature - Integrated)
- **Pre-meeting promos**: Automatically inserted before live meetings (SDI/Live Input)
- **Post-meeting promos**: Automatically inserted after live meetings (SDI/Live Input)  
- **Important**: Promos are only added around live meetings, not pre-recorded content (MTG type)
- Respects duration limits set in configuration
- Only active promos within go-live/expiration dates are used
- Promos are sorted by their configured sort_order
- Gap filling logic automatically adjusts to accommodate promo durations
- Multiple promos can be scheduled in sequence if configured

## Related Files
- `scheduler_postgres.py` - Main scheduling logic
- `app.py` - API endpoints for schedule creation/export
- `meeting_promos.py` - Meeting promo management
- `/api/create-schedule-from-template` - Template-based schedule creation
- `/api/export-schedule` - Export to Castus systems