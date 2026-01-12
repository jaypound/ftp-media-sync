
function schedulingDisplayScheduleDetails(schedule) {
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    
    if (!scheduleDisplay) return;
    
    const airDate = schedule.air_date ? schedule.air_date.split('T')[0] : 'Unknown';
    // Format created date in local timezone
    const createdAt = new Date(schedule.created_date || schedule.created_at).toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
    const totalDurationHours = schedule.total_duration_hours || 0;
    
    let html = `
        <div class="scheduling-schedule-header">
            <h4>📅 ${schedule.schedule_name || 'Daily Schedule'}</h4>
            <p><strong>Air Date:</strong> ${airDate} | <strong>Channel:</strong> ${schedule.channel || 'Comcast Channel 26'}</p>
            <p><strong>Created:</strong> ${createdAt} | <strong>Items:</strong> ${schedule.total_items || 0} | <strong>Total Duration:</strong> ${totalDurationHours.toFixed(1)} hours</p>
        </div>
        <div class="scheduling-schedule-items">
            <div class="scheduling-schedule-table-header">
                <span class="scheduling-col-start-time">Start Time</span>
                <span class="scheduling-col-end-time">End Time</span>
                <span class="scheduling-col-title">Title</span>
                <span class="scheduling-col-category">Category</span>
                <span class="scheduling-col-duration">Duration</span>
                <span class="scheduling-col-last-scheduled">Encoded Date</span>
                <span class="scheduling-col-actions">Actions</span>
            </div>
    `;
    
    if (schedule.items && schedule.items.length > 0) {
        // Check if this is a weekly or monthly schedule by looking at the schedule name
        const isWeeklySchedule = schedule.schedule_name && schedule.schedule_name.toLowerCase().includes('weekly');
        const isMonthlySchedule = schedule.schedule_name && schedule.schedule_name.toLowerCase().includes('monthly');
        console.log(`Schedule type: ${schedule.schedule_name}, isWeekly: ${isWeeklySchedule}, isMonthly: ${isMonthlySchedule}`);
        let currentDay = -1;
        let previousStartHour = -1;
        let lastDayOffset = -1;
        
        schedule.items.forEach((item, index) => {
            const startTime = item.scheduled_start_time || '00:00:00';
            const durationSeconds = item.scheduled_duration_seconds || 0;
            
            // Parse the start time to get the hour
            const timeParts = startTime.split(':');
            const startHour = parseInt(timeParts[0]);
            
            // For weekly or monthly schedules, detect day changes
            if (isWeeklySchedule || isMonthlySchedule) {
                if (index < 3) {
                    console.log(`Item ${index} metadata:`, item.metadata);
                }
                let dayNumber = 0;
                let showDayHeader = false;
                
                // Check if item has metadata with day_offset (for weekly schedules)
                if (item.metadata && item.metadata.day_offset !== undefined) {
                    dayNumber = item.metadata.day_offset;
                    // Show header if this is the first item or day has changed
                    showDayHeader = (index === 0 || dayNumber !== lastDayOffset);
                    lastDayOffset = dayNumber;
                    currentDay = dayNumber;
                    console.log(`Item ${index}: has metadata.day_offset = ${dayNumber}, showDayHeader = ${showDayHeader}`);
                } else {
                    // Fallback: detect day change by hour crossing midnight
                    if (index === 0) {
                        dayNumber = 0;
                        currentDay = 0;
                        showDayHeader = true;
                    } else if (previousStartHour >= 0 && previousStartHour > 20 && startHour < 4) {
                        // Crossed midnight (e.g., from 23:xx to 00:xx)
                        currentDay++;
                        dayNumber = currentDay;
                        showDayHeader = true;
                    } else {
                        // Continue with current day
                        dayNumber = currentDay;
                        showDayHeader = false;
                    }
                }
                
                // Add day header if needed
                if (showDayHeader) {
                    // Parse air_date properly to avoid timezone issues
                    const airDateStr = schedule.air_date.split('T')[0];
                    const [year, month, day] = airDateStr.split('-').map(num => parseInt(num));
                    
                    // Calculate the date for this day
                    const dayDate = new Date(year, month - 1, day + dayNumber);
                    
                    if (isWeeklySchedule) {
                        const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
                        const dayName = dayNames[dayDate.getDay()];
                        const formattedDate = dayDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                        
                        html += `
                            <div class="scheduling-schedule-day-header">
                                <h5>${dayName} - ${formattedDate}</h5>
                            </div>
                        `;
                    } else if (isMonthlySchedule) {
                        const dayName = dayDate.toLocaleDateString('en-US', { weekday: 'long' });
                        const formattedDate = dayDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
                        
                        html += `
                            <div class="scheduling-schedule-day-header">
                                <h5>${dayName}, ${formattedDate}</h5>
                            </div>
                        `;
                    }
                }
                
                previousStartHour = startHour;
            }
            
            // Calculate end time
            const endTime = calculateEndTime(startTime, durationSeconds);
            
            // Format duration as timecode
            const durationTimecode = formatDurationTimecode(durationSeconds);
            
            // Extract content type description
            const contentTypeLabel = getContentTypeLabel(item.content_type);
            
            // Use content title or file name
            const title = item.content_title || item.file_name || 'Untitled';
            const categoryLabel = item.duration_category ? item.duration_category.replace('_', ' ').toUpperCase() : '';
            
            // Format encoded date
            let encodedDateDisplay = 'Unknown';
            if (item.encoded_date) {
                const encodedDate = new Date(item.encoded_date);
                const month = (encodedDate.getMonth() + 1).toString().padStart(2, '0');
                const day = encodedDate.getDate().toString().padStart(2, '0');
                const year = encodedDate.getFullYear().toString().slice(-2);
                encodedDateDisplay = `${month}/${day}/${year}`;
            }
            
            // Check if item is available for scheduling (default to true if not set)
            const isAvailable = item.available_for_scheduling !== false;
            const rowClass = isAvailable ? '' : 'disabled-item';
            const toggleTitle = isAvailable ? 'Disable for future scheduling' : 'Enable for future scheduling';
            const toggleIcon = isAvailable ? 'fa-toggle-on' : 'fa-toggle-off';
            const toggleClass = isAvailable ? 'success' : 'secondary';
            
            html += `
                <div class="scheduling-schedule-item-row ${rowClass}" data-item-id="${item.id}" data-schedule-id="${schedule.id}">
                    <span class="scheduling-col-start-time">${formatTimeWithMilliseconds(startTime)}</span>
                    <span class="scheduling-col-end-time">${endTime}</span>
                    <span class="scheduling-col-title" title="${item.file_name}">${title}</span>
                    <span class="scheduling-col-category">${categoryLabel}</span>
                    <span class="scheduling-col-duration">${durationTimecode}</span>
                    <span class="scheduling-col-last-scheduled">${encodedDateDisplay}</span>
                    <span class="scheduling-col-actions">
                        <button class="button secondary small" onclick="viewScheduleItemDetails(${schedule.id}, ${item.id || item.asset_id}, ${index})" title="View details">
                            <i class="fas fa-info"></i>
                        </button>
                        <button class="button ${toggleClass} small" onclick="toggleScheduleItemAvailability(${schedule.id}, ${item.id}, ${!isAvailable})" title="${toggleTitle}">
                            <i class="fas ${toggleIcon}"></i>
                        </button>
                        <button class="button danger small" onclick="deleteScheduleItem(${schedule.id}, ${item.id}, ${index})" title="Delete item">
                            <i class="fas fa-trash"></i>
                        </button>
                    </span>
                </div>
            `;
        });
    } else {
        html += `<p>No items in this schedule.</p>`;
    }
    
    html += '</div>';
    
    // Add export and delete buttons at the bottom
    html += `
        <div class="scheduling-schedule-actions">
            <button class="button secondary" onclick="exportSchedule()">
                <i class="fas fa-download"></i> Export Schedule
            </button>
            <button class="button danger" onclick="deleteScheduleById(${schedule.id}, '${airDate}')">
                <i class="fas fa-trash"></i> Delete This Schedule
            </button>
        </div>
    `;
    
    scheduleDisplay.innerHTML = html;
    
    // Store the schedule globally for export function to use
    currentSchedule = schedule;
    // Also store it on window object for cross-module access
    window.currentSchedule = schedule;
}

// Function to show list of schedules
function schedulingDisplayScheduleList(schedules) {
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    
    if (!scheduleDisplay) return;
    
    let html = '<div class="scheduling-schedules-list compact">';
    html += '<h3>All Schedules</h3>';
    html += '<div class="scheduling-schedule-table">';
    
    schedules.forEach(schedule => {
        const airDate = schedule.air_date ? schedule.air_date.split('T')[0] : 'Unknown';
        const airDateObj = new Date(airDate + 'T12:00:00');
        const dayName = airDateObj.toLocaleDateString('en-US', { weekday: 'long' });
        const createdTime = new Date(schedule.created_date || schedule.created_at).toLocaleTimeString('en-US', {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
        const totalDurationHours = schedule.total_duration_hours || 0;
        const isWeeklySchedule = schedule.schedule_name && schedule.schedule_name.toLowerCase().includes('weekly');
        const isMonthlySchedule = schedule.schedule_name && schedule.schedule_name.toLowerCase().includes('monthly');
        
        let scheduleIcon = '📅';
        if (isWeeklySchedule) scheduleIcon = '📆';
        if (isMonthlySchedule) scheduleIcon = '🗓️';
        
        html += `
            <div class="scheduling-schedule-row">
                <div class="scheduling-schedule-icon">${scheduleIcon}</div>
                <div class="scheduling-schedule-info">
                    <div class="scheduling-schedule-title">${schedule.schedule_name || 'Schedule'} for ${airDate}</div>
                    <div class="scheduling-schedule-meta">${dayName} • ${schedule.total_items || 0} items • ${totalDurationHours.toFixed(1)}h • Created: ${createdTime}</div>
                </div>
                <div class="scheduling-schedule-actions">
                    <button class="button primary small icon-only" onclick="viewScheduleDetails(${schedule.id}, '${airDate}')" title="View Schedule">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="button secondary small icon-only" onclick="exportSchedule(${schedule.id}, '${airDate}')" title="Export Schedule">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="button danger small icon-only" onclick="deleteScheduleById(${schedule.id}, '${airDate}')" title="Delete Schedule">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
    });
    
    html += '</div></div>';
    
    scheduleDisplay.innerHTML = html;
}

// Export functions to global scope
window.schedulingDisplayScheduleDetails = schedulingDisplayScheduleDetails;
window.schedulingDisplayScheduleList = schedulingDisplayScheduleList;

// All Audit Log Functions
let allAuditLogs = [];

function openAllAuditLogModal() {
    const modal = document.getElementById('allAuditLogModal');
    if (!modal) {
        console.error('All audit log modal not found');
        return;
    }
    
    modal.style.display = 'block';
    loadAllAuditLogs();
}

function closeAllAuditLogModal() {
    const modal = document.getElementById('allAuditLogModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function loadAllAuditLogs() {
    const contentDiv = document.getElementById('allAuditLogContent');
    contentDiv.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary);"><i class="fas fa-spinner fa-spin" style="font-size: 2em;"></i><p>Loading audit logs...</p></div>';
    
    try {
        const response = await fetch('/api/metadata-audit-log?limit=1000');
        const data = await response.json();
        
        if (data.success) {
            allAuditLogs = data.logs || [];
            displayAuditLogs(allAuditLogs);
            updateAuditLogCount(allAuditLogs.length);
        } else {
            contentDiv.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--error-color);"><i class="fas fa-exclamation-circle" style="font-size: 2em;"></i><p>Failed to load audit logs</p></div>';
        }
    } catch (error) {
        console.error('Error loading audit logs:', error);
        contentDiv.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--error-color);"><i class="fas fa-exclamation-circle" style="font-size: 2em;"></i><p>Error loading audit logs</p></div>';
    }
}

function displayAuditLogs(logs) {
    const contentDiv = document.getElementById('allAuditLogContent');
    
    if (!logs || logs.length === 0) {
        contentDiv.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary);"><i class="fas fa-info-circle" style="font-size: 2em;"></i><p>No audit logs found</p></div>';
        return;
    }
    
    let html = '<table class="audit-log-table" style="width: 100%; border-collapse: collapse;">';
    html += '<thead><tr style="background: var(--card-bg); border-bottom: 2px solid var(--border-color);">';
    html += '<th style="padding: 12px; text-align: left;">Date/Time</th>';
    html += '<th style="padding: 12px; text-align: left;">File</th>';
    html += '<th style="padding: 12px; text-align: left;">Field</th>';
    html += '<th style="padding: 12px; text-align: left;">Change</th>';
    html += '<th style="padding: 12px; text-align: left;">Type</th>';
    html += '<th style="padding: 12px; text-align: left;">Source</th>';
    html += '</tr></thead>';
    html += '<tbody>';
    
    logs.forEach((log, index) => {
        // Parse the timestamp assuming it's already in local time (Eastern)
        // The backend stores timestamps without timezone info, so they're in server local time
        const timestampStr = log.changed_at;
        const changeDate = new Date(timestampStr + ' EST');
        
        const formattedDate = changeDate.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
            timeZone: 'America/New_York' // Ensure Eastern Time display
        });
        
        const rowStyle = index % 2 === 0 ? 'background: var(--bg-color);' : 'background: var(--card-bg);';
        
        html += `<tr style="${rowStyle} border-bottom: 1px solid var(--border-color);">`;
        html += `<td style="padding: 12px; font-size: 0.9em;">${formattedDate}</td>`;
        html += `<td style="padding: 12px; font-weight: 500;">${log.content_title || log.asset_id || 'Unknown'}</td>`;
        html += `<td style="padding: 12px;">${log.field_name || 'Unknown'}</td>`;
        html += `<td style="padding: 12px;">`;
        
        if (log.old_value || log.new_value) {
            // Function to format date values from GMT to Eastern Time
            const formatValue = (value) => {
                if (!value) return '<em>empty</em>';
                
                // Check if the value looks like a date with GMT timezone
                if (typeof value === 'string' && value.includes('GMT')) {
                    try {
                        // Parse the date string
                        const dateMatch = value.match(/^(.*?)(\s+\d{2}:\d{2}:\d{2})?\s*GMT$/);
                        if (dateMatch) {
                            const datePart = dateMatch[1] + (dateMatch[2] || ' 00:00:00');
                            const date = new Date(datePart + ' GMT');
                            
                            // Format to Eastern Time
                            const formatted = date.toLocaleString('en-US', {
                                weekday: 'short',
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                                second: '2-digit',
                                timeZone: 'America/New_York',
                                hour12: false
                            });
                            
                            return formatted + ' ET';
                        }
                    } catch (e) {
                        // If parsing fails, return original value
                        return value;
                    }
                }
                
                return value;
            };
            
            const oldVal = formatValue(log.old_value);
            const newVal = formatValue(log.new_value);
            
            html += `<div style="font-size: 0.85em;">`;
            html += `<div><span style="color: var(--text-secondary);">From:</span> ${oldVal}</div>`;
            html += `<div><span style="color: var(--text-secondary);">To:</span> ${newVal}</div>`;
            html += `</div>`;
        } else {
            html += '<em>No details</em>';
        }
        
        html += `</td>`;
        html += `<td style="padding: 12px;">${log.change_type || 'Unknown'}</td>`;
        html += `<td style="padding: 12px;">${log.change_source || 'Unknown'}</td>`;
        html += '</tr>';
    });
    
    html += '</tbody></table>';
    contentDiv.innerHTML = html;
}

function filterAuditLogs() {
    const typeFilter = document.getElementById('auditLogTypeFilter').value;
    const contentFilter = document.getElementById('auditLogContentFilter').value;
    const searchTerm = document.getElementById('auditLogSearchInput').value.toLowerCase();
    
    let filtered = allAuditLogs;
    
    // Filter by activity type
    if (typeFilter) {
        filtered = filtered.filter(log => log.change_type === typeFilter);
    }
    
    // Filter by content type
    if (contentFilter) {
        filtered = filtered.filter(log => {
            const title = (log.content_title || '').toLowerCase();
            return title.includes(`_${contentFilter}_`) || title.includes(`_${contentFilter.toLowerCase()}_`);
        });
    }
    
    // Filter by search term
    if (searchTerm) {
        filtered = filtered.filter(log => {
            const title = (log.content_title || '').toLowerCase();
            const field = (log.field_name || '').toLowerCase();
            const oldVal = (log.old_value || '').toLowerCase();
            const newVal = (log.new_value || '').toLowerCase();
            return title.includes(searchTerm) || 
                   field.includes(searchTerm) ||
                   oldVal.includes(searchTerm) ||
                   newVal.includes(searchTerm);
        });
    }
    
    displayAuditLogs(filtered);
    updateAuditLogCount(filtered.length);
}

function updateAuditLogCount(count) {
    const countSpan = document.getElementById('auditLogCount');
    if (countSpan) {
        countSpan.textContent = `(${count} logs)`;
    }
}

async function exportAuditLogs() {
    try {
        const typeFilter = document.getElementById('auditLogTypeFilter').value;
        const contentFilter = document.getElementById('auditLogContentFilter').value;
        
        let url = '/api/metadata-audit/export?';
        if (typeFilter) url += `field_name=${encodeURIComponent(typeFilter)}&`;
        
        const response = await fetch(url);
        const blob = await response.blob();
        
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `audit_log_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);
        
        showNotification('Audit log exported successfully', 'success');
    } catch (error) {
        console.error('Error exporting audit logs:', error);
        showNotification('Failed to export audit logs', 'error');
    }
}

// Export the audit log functions
window.openAllAuditLogModal = openAllAuditLogModal;
window.closeAllAuditLogModal = closeAllAuditLogModal;
window.filterAuditLogs = filterAuditLogs;
window.exportAuditLogs = exportAuditLogs;
