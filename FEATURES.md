# FTP Media Sync - Feature List

Based on the codebase and recent development, here's a comprehensive list of the FTP Media Sync application's current features:

## Core FTP Synchronization Features
- **Dual FTP Server Management**: Connect to source and target FTP servers simultaneously
- **Bidirectional Sync**: Files can be synced in both directions (source-to-target and target-to-source)
- **Multiple Path Support**: Sync from different folders with different sync rules:
  - On-Air Content folder (unidirectional)
  - Recordings folder (bidirectional)
- **File Filtering**:
  - Filter by file extensions (mp4, mkv, avi, mov, wmv, m4v, flv)
  - Filter by file size (min/max limits)
  - Subdirectory scanning support
- **Sync Options**:
  - Dry run mode (preview changes without actual sync)
  - Overwrite existing files option
  - Keep temporary files for debugging
- **Symbolic Link Support**: Handles /mnt/main → /mnt/md127 symbolic links

## File Management
- **File Comparison**: Compare files between servers showing:
  - Files missing on target
  - Files with size differences
  - Target-only files (for bidirectional sync)
  - Identical files
- **Bulk Operations**:
  - Queue multiple files for sync
  - Bulk delete operations
  - Select/deselect all functionality
- **Delete Functionality**: Delete files from either server with dry run option

## Media Analysis Features
- **Audio Extraction & Transcription**:
  - Extract audio from video files
  - Transcribe using Faster Whisper
  - Language detection
- **AI Content Analysis** (when configured):
  - Generate content summaries
  - Extract topics, people, locations, events
  - Calculate engagement scores
  - Determine shelf life ratings
- **Metadata Extraction**:
  - Parse filename metadata
  - Classify content types (psa, meeting, announcement, etc.)
  - Calculate duration categories

## Database Integration
- **PostgreSQL Storage**: Store analysis results and metadata
- **Content Classification**: 14 different content type categories specific to Atlanta broadcasting
- **Scheduling Metadata**: Track scheduling information for content

## Scheduling Features
- **Schedule Creation**: Create daily schedules from analyzed content
- **Schedule Management**:
  - View schedules by date
  - Edit schedule items
  - Delete schedules
  - Export schedules to JSON
- **Playlist Generation**: Export schedules as playlists for broadcast systems
- **FTP Export**: Export schedules directly to FTP servers

## User Interface
- **Multi-Panel Dashboard**:
  - Server configuration panel
  - Scanning configuration with folder toggles
  - File comparison results
  - Analysis interface
  - Scheduling interface
- **Real-time Logging**: Detailed operation logs in the UI
- **Progress Tracking**: Visual progress bars for long operations
- **Responsive Design**: Clean, modern interface

## Configuration Management
- **Persistent Settings**: Auto-save configuration to JSON
- **Environment Variables**: Support for API keys via .env files
- **Customizable Sync Settings**:
  - File size limits
  - File extensions
  - Connection timeouts
  - Transfer timeouts

## Advanced Features
- **Connection Pooling**: Efficient database connection management
- **Retry Logic**: Automatic retry for failed operations
- **Path Mapping**: Handle complex FTP path structures with quoted folders
- **Error Handling**: Comprehensive error logging and user feedback
- **Concurrent Operations**: Analyze multiple files in batch

## Security Features
- **Password Protection**: FTP passwords stored securely
- **API Key Management**: Separate storage for OpenAI/Anthropic keys
- **No hardcoded credentials**: All sensitive data in config or environment

## Performance Features
- **File Caching**: 15-minute cache for web fetches
- **Efficient Scanning**: Optimized FTP directory listing
- **Smart Verification**: Multiple fallback methods for upload verification
- **Connection Reuse**: Maintain FTP connections across operations

## Content Type Classifications
The application recognizes these Atlanta-specific content types:
- **an**: Announcement
- **bmp**: Bump (short promo)
- **imow**: Inside Moving Atlanta Weekly
- **im**: Inside Atlanta
- **ia**: Interstitial Announcement
- **lm**: Legislative Minute
- **mtg**: Meeting
- **maf**: Moving Atlanta Forward
- **pkg**: Package
- **pmo**: Promo
- **psa**: Public Service Announcement
- **szl**: Sizzle Reel
- **spp**: Special Projects
- **other**: Other/Uncategorized

The application is designed specifically for broadcast media management, with features tailored for managing video content between Castus servers in a television station environment.