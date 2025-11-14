# Fill Graphics System Documentation

## Overview

The Fill Graphics System manages default content rotation for ATL26, providing automated video generation and database-tracked graphics management. The system ensures fresh content by automatically generating new videos during meetings and rotating through different sort orders.

## Table of Contents

1. [System Components](#system-components)
2. [Manual Fill Graphics Generation](#manual-fill-graphics-generation)
3. [Automated Video Generation](#automated-video-generation)
4. [Graphics Database Management](#graphics-database-management)
5. [Configuration Settings](#configuration-settings)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

## System Components

### 1. Graphics Database
- Tracks all graphics in `/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION`
- Stores metadata: file names, creation dates, start/end dates, sort order
- Automatically syncs with FTP servers to detect new/removed graphics

### 2. Video Generation Engine
- Creates MP4 videos from active graphics
- Supports multiple sort orders: creation, newest, oldest, alphabetical, random
- Generates videos with configurable duration (default: 360 seconds)
- File naming format: `YYMMDDHHMI_FILL_<sort_order>_<duration>.mp4`

### 3. Automatic Generation System
- Triggers 2 minutes after scheduled meetings start
- Runs only on backend host (Mac Studio)
- Active weekdays 8 AM - 6 PM
- Rotates through sort orders automatically

## Manual Fill Graphics Generation

### Accessing the Fill Graphics Interface

1. Navigate to the Fill Graphics section in the web interface
2. The collapsible card shows current graphics count and last scan time
3. Click "Scan for Graphics" to update the database with latest files

### Creating a Video Manually

1. **Click "Generate Video"** button
2. **Configure Settings:**
   - **Duration**: Default 360 seconds (6 minutes)
   - **Sort Order**: Choose how graphics are ordered
     - Creation: Original file creation order
     - Newest: Most recent files first
     - Oldest: Oldest files first
     - Alphabetical: Z to A by filename
     - Random: Randomized order
   - **Export Options**: Select target servers (Source/Target/Both)

3. **Review Summary:**
   - Shows total graphics to be included
   - Displays expected video duration
   - Lists export destinations

4. **Generate:** Click to create and export video

### Managing Graphics

#### Editing Graphics Dates
1. Click on any graphic in the list
2. Modify start date or end date
3. Click "Save" to update
4. Changes take effect immediately

#### Viewing History
1. Click "View History" to see all generated videos
2. History shows:
   - Generation date and time
   - File name and duration
   - Graphics count included
   - Export status (✓ Success, ✗ Failed)

## Automated Video Generation

### How It Works

The system automatically generates new fill graphics videos during meetings to ensure content variety:

1. **Trigger**: 2 minutes after a scheduled meeting starts
2. **Process**: 
   - System detects meeting start time
   - Waits 2 minutes
   - Generates video with next sort order in rotation
   - Exports to both FTP servers

3. **Result**: Fresh default content before and after each meeting

### Automatic Settings

- **Enable/Disable**: Toggle in "Automatic Video Generation" section
- **Status**: Shows ON/OFF state clearly
- **Backend Host**: Displays current host (only Mac Studio triggers)
- **Schedule**: Weekdays 8 AM - 6 PM only
- **Delay**: 2 minutes after meeting start

### Sort Order Rotation

The system automatically cycles through sort orders:
```
creation → newest → oldest → alphabetical → random → creation...
```

This ensures each generated video has a different graphic sequence.

### Default Selections for Automated Videos

- **Region 1**: All active graphics from database
- **Region 2**: ATL26 SQUEEZEBACK SKYLINE WITH SOCIAL HANDLES.png
- **Region 3**: All WAV files from music directory

## Graphics Database Management

### Automatic Syncing

The database automatically syncs with FTP servers to:
- Detect new graphics added to DEFAULT ROTATION folder
- Remove entries for deleted graphics
- Update file metadata

### Database Fields

| Field | Description |
|-------|-------------|
| File Name | Original filename from FTP |
| Duration | Fixed at 10 seconds per graphic |
| Start Date | When graphic becomes active |
| End Date | When graphic expires |
| Sort Order | Manual ordering (optional) |
| Status | Active/Inactive/Missing |

### Expiration Management

- Graphics expire based on end date
- Expired graphics are excluded from video generation
- Bulk update options available for extending expiration dates

## Configuration Settings

### Video Duration Considerations

**Current Setting**: 300 seconds (5 minutes)
- Provides buffer before and after meetings
- With 33 graphics at 10 seconds each = 330 seconds total

**Recommended Setting**: 360 seconds (6 minutes)
- Accommodates all 33 graphics
- Provides better content coverage
- Reduces repeat frequency

### File Storage Locations

- **Graphics Source**: `/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION`
- **Video Export**: `/mnt/main/Videos/`
- **Database**: PostgreSQL `default_graphics` table

### Timing Windows

- **Pre-meeting window**: 5 minutes before
- **Post-meeting window**: 5 minutes after
- **Recommended adjustment**: Increase to 6 minutes (360 seconds)

## Best Practices

### 1. Regular Maintenance
- Scan for graphics weekly to catch new additions
- Review expiration dates monthly
- Clean up expired graphics quarterly

### 2. Content Planning
- Maintain 30-40 active graphics for variety
- Stagger expiration dates to avoid bulk removals
- Plan graphic updates around major events

### 3. Monitoring
- Check "View History" daily for generation status
- Verify automated generations after meetings
- Monitor export success rates

### 4. Optimal Settings
- Use 360-second duration for complete rotation
- Enable automated generation for all regular meetings
- Export to both servers for redundancy

## Troubleshooting

### Common Issues

#### Videos Not Generating Automatically
1. Check if automatic generation is enabled (toggle shows ON)
2. Verify current time is within 8 AM - 6 PM weekdays
3. Confirm backend host is Mac Studio
4. Check meeting exists in schedule

#### Missing Graphics in Video
1. Run "Scan for Graphics" to update database
2. Check graphic start/end dates
3. Verify graphics are marked as "active"
4. Ensure graphic files exist on FTP server

#### Export Failures
1. Check FTP server connectivity
2. Verify `/mnt/main/Videos/` directory exists
3. Review upload logs in `backend/logs/autogen_upload_*.log`
4. Confirm sufficient disk space

### Log Locations

- **FFmpeg Generation**: `backend/logs/ffmpeg_auto_gen_*.log`
- **Upload Status**: `backend/logs/autogen_upload_*.log`
- **Scheduler Activity**: `backend/logs/scheduler_*.log`

### Database Queries

Check recent generations:
```sql
SELECT * FROM meeting_video_generations 
ORDER BY generation_timestamp DESC 
LIMIT 10;
```

View active graphics count:
```sql
SELECT COUNT(*) FROM default_graphics 
WHERE status = 'active' 
AND start_date <= CURRENT_DATE 
AND (end_date IS NULL OR end_date >= CURRENT_DATE);
```

## Technical Details

### API Endpoints
- `GET /api/default-graphics/active` - List active graphics
- `POST /api/default-graphics/scan` - Scan for new graphics
- `POST /api/default-graphics/generate-video` - Manual generation
- `GET /api/default-graphics/history` - View generation history

### Database Schema
- `default_graphics` - Graphics metadata
- `generated_default_videos` - Generation history
- `meeting_video_generations` - Automated generation tracking
- `auto_generation_config` - System settings

### File Naming Convention
```
YYMMDDHHMI_FILL_<sort_order>_<duration>.mp4

Example: 241114106_FILL_creation_360.mp4
- 24 = 2024
- 11 = November
- 14 = 14th day
- 10 = 10 AM
- 6 = 6 minutes past hour
- creation = sort order
- 360 = duration in seconds
```

## Future Enhancements

1. **Dynamic Duration**: Automatically adjust video length based on graphic count
2. **Content Analytics**: Track which graphics appear most/least frequently
3. **Smart Scheduling**: Avoid generating during back-to-back meetings
4. **Preview Mode**: Generate preview thumbnails before full video
5. **Custom Templates**: Different graphic arrangements for special events

---

*Last Updated: November 14, 2024*