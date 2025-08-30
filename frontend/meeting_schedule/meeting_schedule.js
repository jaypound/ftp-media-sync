/**
 * Meeting Schedule Module
 * Handles Atlanta City Council meetings schedule and trimming functionality
 */

// Meeting Schedule State
const meetingScheduleState = {
    meetings: [],
    recordings: [],
    autoTrimEnabled: false,
    trimSettings: {
        server: 'target',
        sourcePath: '/mnt/main/Recordings',
        destPath: '/mnt/main/ATL26 On-Air Content/MEETINGS',
        keepOriginal: true
    },
    currentTrimFile: null
};

// Initialize Meeting Schedule Module
function meetingScheduleInit() {
    console.log('Initializing Meeting Schedule module...');
    
    // Load meetings
    meetingScheduleLoadMeetings();
    
    // Load trim settings
    meetingScheduleLoadTrimSettings();
    
    // Update AppState
    AppState.setModule('meeting_schedule', meetingScheduleState);
}

// Load meetings from database
async function meetingScheduleLoadMeetings() {
    try {
        const response = await window.API.get('/meetings');
        if (response.success) {
            meetingScheduleState.meetings = response.meetings;
            meetingScheduleDisplayMeetings();
        }
    } catch (error) {
        console.error('Failed to load meetings:', error);
    }
}

// Display meetings in table
function meetingScheduleDisplayMeetings() {
    const tbody = document.getElementById('meetingsTableBody');
    const noMeetingsMsg = document.getElementById('noMeetingsMessage');
    
    if (!tbody) return;
    
    if (meetingScheduleState.meetings.length === 0) {
        tbody.innerHTML = '';
        if (noMeetingsMsg) noMeetingsMsg.style.display = 'block';
        return;
    }
    
    if (noMeetingsMsg) noMeetingsMsg.style.display = 'none';
    
    // Sort meetings by date (newest first)
    const sortedMeetings = [...meetingScheduleState.meetings].sort((a, b) => 
        new Date(b.meeting_date) - new Date(a.meeting_date)
    );
    
    let html = '';
    sortedMeetings.forEach(meeting => {
        const meetingDate = new Date(meeting.meeting_date);
        const dateStr = meetingDate.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
        
        const startTime = meeting.start_time || '--:--';
        const duration = meeting.duration_hours ? `${meeting.duration_hours} hrs` : '--';
        const room = meeting.room || 'TBD';
        const broadcast = meeting.broadcast_on_atl26;
        
        html += `
            <tr>
                <td class="meeting-schedule-name">${meeting.meeting_name}</td>
                <td class="meeting-schedule-date">${dateStr}</td>
                <td class="meeting-schedule-time">${startTime}</td>
                <td class="meeting-schedule-duration">${duration}</td>
                <td><span class="meeting-schedule-room">${room}</span></td>
                <td class="meeting-schedule-atl26">
                    ${broadcast ? 
                        '<i class="fas fa-check-circle meeting-schedule-broadcast-yes"></i>' : 
                        '<i class="fas fa-times-circle meeting-schedule-broadcast-no"></i>'}
                </td>
                <td>
                    <div class="meeting-schedule-actions">
                        <button class="button secondary small" onclick="meetingScheduleEditMeeting(${meeting.id})">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        <button class="button danger small" onclick="meetingScheduleDeleteMeeting(${meeting.id})">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// Import meetings from web
async function meetingScheduleImportFromWeb() {
    const button = event.target;
    const statusEl = document.getElementById('importStatus');
    
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Importing...';
    if (statusEl) statusEl.textContent = 'Importing meetings...';
    
    try {
        const response = await window.API.post('/meetings/import-from-web');
        if (response.success) {
            const count = response.imported_count || 0;
            if (statusEl) {
                statusEl.textContent = `Successfully imported ${count} meetings`;
                statusEl.className = 'meeting-schedule-import-status success';
            }
            window.showNotification(`Imported ${count} meetings from City Council website`, 'success');
            
            // Reload meetings
            await meetingScheduleLoadMeetings();
        }
    } catch (error) {
        if (statusEl) {
            statusEl.textContent = 'Import failed';
            statusEl.className = 'meeting-schedule-import-status error';
        }
        window.showNotification('Failed to import meetings', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-download"></i> Import from City Council Website';
    }
}

// Open add meeting modal
function meetingScheduleOpenAddModal() {
    const modalTitle = document.getElementById('meetingModalTitle');
    if (modalTitle) modalTitle.textContent = 'Add Meeting';
    
    // Clear form
    document.getElementById('meetingId').value = '';
    document.getElementById('meetingForm').reset();
    
    // Show modal
    const modal = document.getElementById('meetingModal');
    if (modal) modal.classList.add('active');
}

// Edit meeting
async function meetingScheduleEditMeeting(meetingId) {
    const meeting = meetingScheduleState.meetings.find(m => m.id === meetingId);
    if (!meeting) {
        console.error('Meeting not found with ID:', meetingId);
        return;
    }
    
    console.log('Editing meeting:', meeting);
    
    // Populate form
    document.getElementById('meetingId').value = meeting.id;
    document.getElementById('meetingName').value = meeting.meeting_name;
    document.getElementById('meetingDate').value = meeting.meeting_date.split('T')[0];
    
    // Format time for HTML time input (expects 24-hour HH:MM format)
    let timeValue = meeting.start_time || '';
    console.log('Meeting edit - Original time from database:', meeting.start_time);
    
    if (timeValue) {
        // First, trim any whitespace
        timeValue = timeValue.trim();
        
        // Convert 12-hour format (H:MM AM/PM or HH:MM AM/PM) to 24-hour format (HH:MM)
        const timeMatch = timeValue.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
        if (timeMatch) {
            let hours = parseInt(timeMatch[1]);
            const minutes = timeMatch[2];
            const meridiem = timeMatch[3].toUpperCase();
            
            console.log(`Parsed time components - hours: ${hours}, minutes: ${minutes}, meridiem: ${meridiem}`);
            
            // Convert to 24-hour format
            if (meridiem === 'PM' && hours !== 12) {
                hours += 12;
            } else if (meridiem === 'AM' && hours === 12) {
                hours = 0;
            }
            
            // Format as HH:MM
            timeValue = `${hours.toString().padStart(2, '0')}:${minutes}`;
            console.log('Converted to 24-hour format:', timeValue);
        }
        // If time includes seconds in 24-hour format, remove them
        else if (timeValue.match(/^\d{2}:\d{2}:\d{2}$/)) {
            timeValue = timeValue.substring(0, 5); // Get only HH:MM
        }
        // If time has milliseconds or timezone, extract just the time
        else if (timeValue.includes('T')) {
            const timePart = timeValue.split('T')[1];
            timeValue = timePart.substring(0, 5);
        }
        else {
            console.warn('Time format not recognized:', timeValue);
        }
    }
    
    console.log('Final formatted time for input:', timeValue);
    const timeInput = document.getElementById('meetingTime');
    if (timeInput) {
        timeInput.value = timeValue;
        console.log('Time input value set to:', timeInput.value);
    } else {
        console.error('Time input element not found!');
    }
    
    document.getElementById('meetingDuration').value = meeting.duration_hours;
    document.getElementById('meetingRoom').value = meeting.room || '';
    document.getElementById('meetingBroadcast').checked = meeting.broadcast_on_atl26;
    
    // Update modal title
    const modalTitle = document.getElementById('meetingModalTitle');
    if (modalTitle) modalTitle.textContent = 'Edit Meeting';
    
    // Show modal
    const modal = document.getElementById('meetingModal');
    if (modal) modal.classList.add('active');
}

// Save meeting
async function meetingScheduleSaveMeeting() {
    const meetingId = document.getElementById('meetingId').value;
    
    // Convert 24-hour time to 12-hour format with AM/PM
    let timeValue = document.getElementById('meetingTime').value;
    if (timeValue) {
        const [hours24, minutes] = timeValue.split(':');
        let hours = parseInt(hours24);
        let meridiem = 'AM';
        
        if (hours >= 12) {
            meridiem = 'PM';
            if (hours > 12) {
                hours -= 12;
            }
        } else if (hours === 0) {
            hours = 12;
        }
        
        timeValue = `${hours}:${minutes} ${meridiem}`;
    }
    
    const formData = {
        meeting_name: document.getElementById('meetingName').value,
        meeting_date: document.getElementById('meetingDate').value,
        start_time: timeValue,
        duration_hours: parseFloat(document.getElementById('meetingDuration').value),
        room: document.getElementById('meetingRoom').value,
        broadcast_on_atl26: document.getElementById('meetingBroadcast').checked
    };
    
    try {
        let response;
        if (meetingId) {
            // Update existing
            response = await window.API.put(`/meetings/${meetingId}`, formData);
        } else {
            // Create new
            response = await window.API.post('/meetings', formData);
        }
        
        if (response.success) {
            window.showNotification(meetingId ? 'Meeting updated' : 'Meeting added', 'success');
            meetingScheduleCloseMeetingModal();
            await meetingScheduleLoadMeetings();
        }
    } catch (error) {
        window.showNotification('Failed to save meeting', 'error');
    }
}

// Delete meeting
async function meetingScheduleDeleteMeeting(meetingId) {
    if (!confirm('Are you sure you want to delete this meeting?')) return;
    
    try {
        const response = await window.API.delete(`/meetings/${meetingId}`);
        if (response.success) {
            window.showNotification('Meeting deleted', 'success');
            await meetingScheduleLoadMeetings();
        }
    } catch (error) {
        window.showNotification('Failed to delete meeting', 'error');
    }
}

// Close meeting modal
function meetingScheduleCloseMeetingModal() {
    const modal = document.getElementById('meetingModal');
    if (modal) modal.classList.remove('active');
}

// Load trim settings
function meetingScheduleLoadTrimSettings() {
    // Load from local storage or use defaults
    const saved = localStorage.getItem('trimSettings');
    if (saved) {
        Object.assign(meetingScheduleState.trimSettings, JSON.parse(saved));
    }
}

// Save trim settings
function meetingScheduleSaveTrimSettings() {
    meetingScheduleState.trimSettings = {
        server: document.getElementById('trimServer').value,
        sourcePath: document.getElementById('trimSourcePath').value,
        destPath: document.getElementById('trimDestPath').value,
        keepOriginal: document.getElementById('keepOriginal').checked
    };
    
    localStorage.setItem('trimSettings', JSON.stringify(meetingScheduleState.trimSettings));
    window.showNotification('Trim settings saved', 'success');
    
    const modal = document.getElementById('trimSettingsModal');
    if (modal) modal.classList.remove('active');
}

// Show trim settings modal
function meetingScheduleShowTrimSettings() {
    // Populate form
    document.getElementById('trimServer').value = meetingScheduleState.trimSettings.server;
    document.getElementById('trimSourcePath').value = meetingScheduleState.trimSettings.sourcePath;
    document.getElementById('trimDestPath').value = meetingScheduleState.trimSettings.destPath;
    document.getElementById('keepOriginal').checked = meetingScheduleState.trimSettings.keepOriginal;
    
    const modal = document.getElementById('trimSettingsModal');
    if (modal) modal.classList.add('active');
}

// Refresh recordings list
async function meetingScheduleRefreshRecordingsList() {
    const button = event.target;
    const listEl = document.getElementById('recordingsList');
    
    if (!listEl) return;
    
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    
    try {
        const response = await window.API.post('/meetings/scan-recordings', {
            server: meetingScheduleState.trimSettings.server,
            path: meetingScheduleState.trimSettings.sourcePath
        });
        
        if (response.success) {
            meetingScheduleState.recordings = response.recordings;
            meetingScheduleDisplayRecordings();
        }
    } catch (error) {
        window.showNotification('Failed to load recordings', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-sync"></i> Refresh List';
    }
}

// Display recordings
function meetingScheduleDisplayRecordings() {
    const listEl = document.getElementById('recordingsList');
    if (!listEl) return;
    
    if (meetingScheduleState.recordings.length === 0) {
        listEl.innerHTML = '<p style="text-align: center; color: #666; padding: 2rem;">No recordings found</p>';
        return;
    }
    
    let html = '<div class="meeting-schedule-recordings-list">';
    meetingScheduleState.recordings.forEach(recording => {
        html += `
            <div class="meeting-schedule-recording-item">
                <div class="meeting-schedule-recording-info">
                    <h4>${recording.filename}</h4>
                    <p>Size: ${meetingScheduleFormatFileSize(recording.size)} | Duration: ${recording.duration || 'Unknown'}</p>
                </div>
                <button class="button primary small" onclick="meetingScheduleOpenTrimAnalysis('${recording.filename}')">
                    <i class="fas fa-cut"></i> Trim
                </button>
            </div>
        `;
    });
    html += '</div>';
    
    listEl.innerHTML = html;
}

// Toggle auto trim
function meetingScheduleToggleAutoTrim() {
    meetingScheduleState.autoTrimEnabled = !meetingScheduleState.autoTrimEnabled;
    
    const button = document.getElementById('autoTrimToggle');
    if (button) {
        button.className = meetingScheduleState.autoTrimEnabled ? 
            'button info small meeting-schedule-auto-trim-toggle active' : 
            'button info small meeting-schedule-auto-trim-toggle';
        button.innerHTML = `<i class="fas fa-robot"></i> Auto-Trim: ${meetingScheduleState.autoTrimEnabled ? 'ON' : 'OFF'}`;
    }
}

// Open trim analysis modal
function meetingScheduleOpenTrimAnalysis(filename) {
    meetingScheduleState.currentTrimFile = filename;
    
    // Update modal
    const filenameEl = document.getElementById('trimAnalysisFilename');
    if (filenameEl) filenameEl.textContent = filename;
    
    // Reset form
    document.getElementById('trimAnalysisStartTime').value = '';
    document.getElementById('trimAnalysisEndTime').value = '';
    document.getElementById('trimAnalysisNewFilename').value = filename;
    
    // Show modal
    const modal = document.getElementById('trimAnalysisModal');
    if (modal) modal.classList.add('active');
}

// Format file size
function meetingScheduleFormatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Export functions to global scope
window.meetingScheduleInit = meetingScheduleInit;
window.meetingScheduleImportFromWeb = meetingScheduleImportFromWeb;
window.meetingScheduleOpenAddModal = meetingScheduleOpenAddModal;
window.meetingScheduleEditMeeting = meetingScheduleEditMeeting;
window.meetingScheduleSaveMeeting = meetingScheduleSaveMeeting;
window.meetingScheduleDeleteMeeting = meetingScheduleDeleteMeeting;
window.meetingScheduleCloseMeetingModal = meetingScheduleCloseMeetingModal;
window.meetingScheduleShowTrimSettings = meetingScheduleShowTrimSettings;
window.meetingScheduleSaveTrimSettings = meetingScheduleSaveTrimSettings;
window.meetingScheduleRefreshRecordingsList = meetingScheduleRefreshRecordingsList;
window.meetingScheduleToggleAutoTrim = meetingScheduleToggleAutoTrim;
window.meetingScheduleOpenTrimAnalysis = meetingScheduleOpenTrimAnalysis;

// Legacy support
window.importMeetingsFromWeb = meetingScheduleImportFromWeb;
window.openAddMeetingModal = meetingScheduleOpenAddModal;
window.saveMeeting = meetingScheduleSaveMeeting;
window.closeMeetingModal = meetingScheduleCloseMeetingModal;
window.showTrimSettings = meetingScheduleShowTrimSettings;
window.saveTrimSettings = meetingScheduleSaveTrimSettings;
window.refreshRecordingsList = meetingScheduleRefreshRecordingsList;
window.toggleAutoTrim = meetingScheduleToggleAutoTrim;