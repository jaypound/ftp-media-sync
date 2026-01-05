# Return to Automation Video Selection - Technical Documentation

## Overview

The return to automation workflow ensures that weekly schedules always use the newest default video file from the `/mnt/main/Videos/` folder when exporting schedules. This document describes the technical implementation and debugging procedures.

## Problem Statement

When creating weekly schedules, the system was selecting older video files (e.g., `2512261404_FILL_alphabetical_430.mp4` from Dec 26, 2025) instead of the newest ones (e.g., `2601050923_FILL_alphabetical_420.mp4` from Jan 5, 2026) for the "Weekly Default" content in Castus.

## Solution Architecture

### 1. Video Storage Location
- **Path**: `/mnt/main/Videos/`
- **Naming Convention**: `YYMMDDHHMI_FILL_<sort_order>_<duration>.mp4`
  - YY: Year (2 digits)
  - MM: Month
  - DD: Day
  - HH: Hour (24-hour format)
  - MI: Minutes
  - Example: `2601050923` = January 5, 2026, 09:23 AM

### 2. Key Components

#### Weekly Template Generation (`generate_weekly_schedule_template`)
- Located in: `backend/app.py` (line ~12582)
- Adds placeholder video after meetings:
```python
template_lines.extend([
    '{',
    f'\titem=/mnt/main/Videos/251107_RANDOM.mp4',
    '\tloop=0',
    f'\tguid={video_guid}',
    f'\tstart={day_name} {video_start_time_lower}',
    f'\tend={day_name} {video_end_time_lower}',
    '}'
])
```

#### Template Defaults Update (`update_template_defaults`)
- Located in: `backend/app.py` (line ~14662)
- Sets the global default video:
```python
template['defaults']['global_default'] = default_project
```

#### Schedule Export (`generate_castus_schedule`)
- Located in: `backend/app.py` (lines 5572-5610)
- Critical section that performs the video replacement:

```python
if template and 'defaults' in template and 'global_default' in template['defaults']:
    global_default = template['defaults']['global_default']
    
    # Check if this is a video in the Videos folder - replace with newest
    if '/mnt/main/Videos/' in global_default and global_default.endswith('.mp4'):
        logger.info(f"=== WEEKLY DEFAULT VIDEO DETECTED ===")
        logger.info(f"Original: {global_default}")
        
        # Get the newest video file from the Videos folder via FTP
        try:
            # Get source FTP manager
            source_ftp = ftp_managers.get('source')
            if not source_ftp:
                # Create connection if needed
                source_config = config_manager.get_all_config().get('servers', {}).get('source')
                if source_config:
                    source_ftp = FTPManager(source_config)
                    if source_ftp.connect():
                        ftp_managers['source'] = source_ftp
            
            if source_ftp and source_ftp.connected:
                # List files in Videos folder
                videos_path = '/mnt/main/Videos'
                files = source_ftp.list_files(videos_path)
                
                # Filter for MP4 files and sort by filename (newest first)
                mp4_files = [f for f in files if f['name'].endswith('.mp4')]
                mp4_files.sort(key=lambda x: x['name'], reverse=True)
                
                if mp4_files:
                    newest_filename = mp4_files[0]['name']
                    global_default = f"{videos_path}/{newest_filename}"
                    logger.info(f"✓ Replaced with newest: {global_default}")
                else:
                    logger.warning("✗ No MP4 files found in Videos folder, keeping original")
            else:
                logger.warning("✗ Could not connect to FTP to check Videos folder")
        except Exception as e:
            logger.error(f"Error finding newest video via FTP: {str(e)}")
```

## Process Flow

1. **Weekly Schedule Creation**
   - User creates a weekly schedule template
   - System adds meetings and places default videos after each meeting
   - Template is saved with placeholder or existing video reference

2. **Fill Gaps Process**
   - Template gaps are filled with content from the database
   - The placeholder video (`251107_RANDOM.mp4`) may be replaced with an actual video file

3. **Schedule Export**
   - User exports the schedule
   - `generate_castus_schedule` function is called
   - System checks if the global default is a video in `/mnt/main/Videos/`
   - If yes, connects to FTP and lists all files in the Videos folder
   - Sorts files by filename (descending) to get the newest
   - Replaces the old video path with the newest one
   - Exports the schedule with the updated video reference

## Castus Schedule Format

The weekly default video appears in the Castus schedule header as:
```
defaults, day of the week{
}
day = 0
time slot length = 30
scrolltime = 12:00 am
filter script = 
global default=/mnt/main/Videos/2601050923_FILL_alphabetical_420.mp4
global default section=item duration=;
text encoding = UTF-8
schedule format version = 5.0.0.4 2021/01/15
```

## Important Notes

1. **Videos Not in Database**: Files in `/mnt/main/Videos/` are NOT scanned into the database. This is why the solution uses FTP to list files directly from the folder.

2. **FTP Connection**: The system reuses existing FTP connections when possible, creating new ones only when needed.

3. **Sorting Logic**: Files are sorted by filename in descending order. Since filenames start with YYMMDDHHMI, this effectively sorts by creation timestamp.

4. **Default Videos vs Regular Content**: 
   - Default videos: Stored in `/mnt/main/Videos/`, used for return to automation
   - Regular content: Stored in various subfolders, tracked in the database

## Debugging Steps

### 1. Check if Video Detection is Triggered
Look for these log messages:
```
=== WEEKLY DEFAULT VIDEO DETECTED ===
Original: /mnt/main/Videos/[old_filename]
✓ Replaced with newest: /mnt/main/Videos/[new_filename]
```

### 2. Common Issues and Solutions

**Issue**: "No videos found in Videos folder"
- **Cause**: FTP connection failed or folder is empty
- **Solution**: Check FTP connection and verify folder contents

**Issue**: Wrong video selected
- **Cause**: Filename doesn't follow expected pattern
- **Solution**: Verify all videos follow YYMMDDHHMI naming convention

**Issue**: Detection not triggered
- **Cause**: Global default path doesn't match expected pattern
- **Solution**: Check template['defaults']['global_default'] value

### 3. Manual Testing
1. Create a weekly schedule template with meetings
2. Fill gaps if needed
3. Export the template
4. Check console logs for replacement messages
5. Verify the exported .sch file contains the newest video path

### 4. Log Locations
- Console output: Check terminal or redirect to file with `tee`
- Debug logs show:
  - When `generate_castus_schedule` is called
  - Template structure and items
  - FTP connection status
  - File listing results
  - Replacement operations

## Code Locations Summary

| Component | File | Function | Purpose |
|-----------|------|----------|---------|
| Weekly Template | app.py:~12582 | `generate_weekly_schedule_template` | Adds placeholder videos |
| Template Defaults | app.py:~14662 | `update_template_defaults` | Sets global default |
| Export Logic | app.py:5572-5610 | `generate_castus_schedule` | Replaces with newest video |
| FTP Manager | ftp_manager.py | `list_files` | Lists Videos folder contents |

## Testing Checklist

- [ ] Create weekly schedule with meetings
- [ ] Verify placeholder video is added after meetings
- [ ] Export schedule
- [ ] Check logs for "WEEKLY DEFAULT VIDEO DETECTED"
- [ ] Verify newest video is selected
- [ ] Import schedule in Castus
- [ ] Confirm Weekly Default shows newest video

---

*Last Updated: January 5, 2026*
*Author: Claude Assistant*