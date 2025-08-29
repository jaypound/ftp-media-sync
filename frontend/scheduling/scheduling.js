
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
                        showDayHeader = true;
                    } else if (previousStartHour > 20 && startHour < 4) {
                        // Crossed midnight (e.g., from 23:xx to 00:xx)
                        currentDay++;
                        dayNumber = currentDay;
                        showDayHeader = true;
                    } else if (index > 0 && currentDay === -1) {
                        // First item might not start at midnight
                        currentDay = 0;
                        dayNumber = 0;
                        showDayHeader = true;
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