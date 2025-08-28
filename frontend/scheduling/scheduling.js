/* Scheduling Module JavaScript */
/* All scheduling-specific functions with proper namespacing */

// Initialize Scheduling Module
function schedulingInit() {
    console.log('Initializing Scheduling module...');
    
    // Override viewScheduleDetails to add debugging
    const originalViewScheduleDetails = window.viewScheduleDetails;
    window.viewScheduleDetails = function(scheduleId, date) {
        console.log('viewScheduleDetails called with:', { scheduleId, date });
        if (!date) {
            console.error('Date parameter is missing!');
            window.showNotification('Error: Schedule date is missing', 'error');
            return;
        }
        return originalViewScheduleDetails.call(this, scheduleId, date);
    };
}

// Display schedule details with proper CSS classes
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
        let currentDay = -1;
        let previousStartHour = -1;
        
        schedule.items.forEach((item, index) => {
            const startTime = item.scheduled_start_time || '00:00:00';
            const durationSeconds = item.scheduled_duration_seconds || 0;
            
            // Parse the start time to get the hour
            const timeParts = startTime.split(':');
            const startHour = parseInt(timeParts[0]);
            
            // For weekly or monthly schedules, detect day changes
            if (isWeeklySchedule || isMonthlySchedule) {
                let dayNumber = 0;
                
                // Detect day change: when hour goes from high (e.g., 23) to low (e.g., 0, 1, 2)
                // or this is the first item
                if (index === 0) {
                    dayNumber = 0;
                } else if (previousStartHour > 20 && startHour < 4) {
                    // Crossed midnight (e.g., from 23:xx to 00:xx)
                    currentDay++;
                    dayNumber = currentDay;
                } else if (index > 0 && currentDay === -1) {
                    // First item might not start at midnight
                    currentDay = 0;
                    dayNumber = 0;
                }
                
                // Add day header if we've moved to a new day
                if ((index === 0) || (previousStartHour > 20 && startHour < 4)) {
                    if (index === 0) {
                        currentDay = 0;
                    }
                    
                    // Parse air_date properly to avoid timezone issues
                    const airDateStr = schedule.air_date.split('T')[0];
                    const [year, month, day] = airDateStr.split('-').map(num => parseInt(num));
                    
                    // Calculate the date for this day
                    const dayDate = new Date(year, month - 1, day + currentDay);
                    
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
                        <button class="button secondary small" onclick="moveScheduleItem(${schedule.id}, ${index}, 'up')" ${index === 0 ? 'disabled' : ''} title="Move up">
                            <i class="fas fa-arrow-up"></i>
                        </button>
                        <button class="button secondary small" onclick="moveScheduleItem(${schedule.id}, ${index}, 'down')" ${index === schedule.items.length - 1 ? 'disabled' : ''} title="Move down">
                            <i class="fas fa-arrow-down"></i>
                        </button>
                    </span>
                </div>
            `;
        });
    } else {
        html += '<div class="scheduling-schedule-no-items">No scheduled items found.</div>';
    }
    
    html += '</div>';
    
    scheduleDisplay.innerHTML = html;
}

// Display schedule list with proper CSS classes
function schedulingDisplayScheduleList(schedules) {
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    
    if (!scheduleDisplay) return;
    
    if (!schedules || schedules.length === 0) {
        scheduleDisplay.innerHTML = '<p>📅 No schedules found. Create a schedule to get started.</p>';
        return;
    }
    
    let html = `
        <div class="scheduling-schedule-list-header">
            <h3>📅 All Schedules (${schedules.length})</h3>
        </div>
    `;
    
    // Sort schedules by air date (newest first)
    schedules.sort((a, b) => new Date(b.air_date) - new Date(a.air_date));
    
    schedules.forEach(schedule => {
        const airDate = schedule.air_date ? schedule.air_date.split('T')[0] : 'Unknown';
        const createdAt = new Date(schedule.created_date || schedule.created_at).toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
        const totalDurationHours = schedule.total_duration_hours || 0;
        const itemCount = schedule.total_items || 0;
        
        // Determine schedule type based on name
        let scheduleType = '📅 Daily';
        let typeClass = 'daily';
        if (schedule.schedule_name && schedule.schedule_name.toLowerCase().includes('weekly')) {
            scheduleType = '📆 Weekly';
            typeClass = 'weekly';
        } else if (schedule.schedule_name && schedule.schedule_name.toLowerCase().includes('monthly')) {
            scheduleType = '🗓️ Monthly';
            typeClass = 'monthly';
        }
        
        html += `
            <div class="scheduling-schedule-list-item schedule-type-${typeClass}">
                <div class="scheduling-schedule-info">
                    <h4>${scheduleType} ${schedule.schedule_name || 'Schedule'}</h4>
                    <p><strong>Air Date:</strong> ${airDate} | <strong>Items:</strong> ${itemCount} | <strong>Duration:</strong> ${totalDurationHours.toFixed(1)} hours</p>
                    <p><small>Created: ${createdAt}</small></p>
                </div>
                <div class="scheduling-schedule-actions">
                    <button class="button primary small" onclick="viewScheduleDetails(${schedule.id}, '${airDate}')">
                        <i class="fas fa-eye"></i> View
                    </button>
                    <button class="button secondary small" onclick="exportSchedule(${schedule.id}, '${airDate}')">
                        <i class="fas fa-download"></i> Export
                    </button>
                    <button class="button danger small" onclick="deleteSchedule(${schedule.id}, '${airDate}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            </div>
        `;
    });
    
    scheduleDisplay.innerHTML = html;
}

// Export the functions to global scope for compatibility
window.schedulingInit = schedulingInit;
window.schedulingDisplayScheduleDetails = schedulingDisplayScheduleDetails;
window.schedulingDisplayScheduleList = schedulingDisplayScheduleList;