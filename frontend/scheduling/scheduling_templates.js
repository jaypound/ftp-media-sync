/**
 * Scheduling Templates Module
 * Handles template loading and display for scheduling
 */

// Template State
const schedulingTemplateState = {
    currentTemplate: null,
    templateLoaded: false
};

// Initialize Templates Module
function schedulingTemplatesInit() {
    console.log('Initializing Scheduling Templates module...');
    
    // Expose state to global scope
    window.schedulingTemplateState = schedulingTemplateState;
    
    // Override the legacy displayTemplate function
    if (window.displayTemplate) {
        window.displayTemplate = schedulingDisplayTemplate;
    }
}

// Display template with proper element handling
function schedulingDisplayTemplate(template) {
    if (!template) {
        console.error('No template provided to display');
        return;
    }
    
    console.log('schedulingDisplayTemplate called with template containing', template.items ? template.items.length : 0, 'items');
    
    schedulingTemplateState.currentTemplate = template;
    schedulingTemplateState.templateLoaded = true;
    
    // Ensure global currentTemplate is updated
    window.currentTemplate = template;
    console.log('Template set in window.currentTemplate:', window.currentTemplate);
    
    // Update template info display
    const templateInfoEl = document.getElementById('schedulingTemplateInfo');
    if (templateInfoEl) {
        templateInfoEl.style.display = 'block';
    }
    
    // Update template name
    const scheduleType = template.type === 'weekly' ? 'Weekly' : 'Daily';
    const templateNameEl = document.getElementById('schedulingTemplateName');
    if (templateNameEl) {
        templateNameEl.textContent = `${template.filename || 'Untitled'} (${scheduleType})`;
    }
    
    // Update item count
    const templateItemCountEl = document.getElementById('schedulingTemplateItemCount');
    if (templateItemCountEl) {
        templateItemCountEl.textContent = template.items ? template.items.length : 0;
    }
    
    // Calculate and update total duration
    let totalDuration = 0;
    if (template.items && Array.isArray(template.items)) {
        template.items.forEach(item => {
            totalDuration += parseFloat(item.duration_seconds) || 0;
        });
    }
    
    // Round the total duration to avoid floating point precision issues
    totalDuration = Math.round(totalDuration * 1000) / 1000;
    
    const hours = Math.floor(totalDuration / 3600);
    const minutes = Math.floor((totalDuration % 3600) / 60);
    const seconds = Math.round(totalDuration % 60);
    const durationStr = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    const templateDurationEl = document.getElementById('schedulingTemplateDuration');
    if (templateDurationEl) {
        templateDurationEl.textContent = durationStr;
    }
    
    // Display template items
    const templateDisplayEl = document.getElementById('schedulingTemplateDisplay');
    if (templateDisplayEl) {
        console.log('Found template display element, generating HTML for', template.items.length, 'items');
        const html = schedulingGenerateTemplateHTML(template);
        console.log('Generated HTML length:', html.length, 'characters');
        templateDisplayEl.innerHTML = html;
        console.log('HTML set to element');
    } else {
        console.error('schedulingTemplateDisplay element not found!')
    }
    
    // Show export and create schedule buttons if template is loaded
    const exportBtn = document.getElementById('exportTemplateBtn');
    if (exportBtn) {
        exportBtn.style.display = 'inline-block';
    }
    
    const createScheduleBtn = document.getElementById('createScheduleBtn');
    if (createScheduleBtn) {
        createScheduleBtn.style.display = 'inline-block';
    }
    
    console.log('Template displayed successfully:', template.filename);
}

// Generate HTML for template display
function schedulingGenerateTemplateHTML(template) {
    if (!template || !template.items || template.items.length === 0) {
        return '<p class="scheduling-template-empty">No items in template</p>';
    }
    
    console.log('schedulingGenerateTemplateHTML: Generating HTML for', template.items.length, 'items');
    
    let html = '<div class="scheduling-template-items">';
    
    // Add day headers for weekly templates
    if (template.type === 'weekly') {
        // Group items by day based on start_time prefix
        const dayGroups = {};
        const dayNames = {
            'sun': 'Sunday',
            'mon': 'Monday',
            'tue': 'Tuesday',
            'wed': 'Wednesday',
            'thu': 'Thursday',
            'fri': 'Friday',
            'sat': 'Saturday'
        };
        const dayOrder = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
        
        // Group items by day prefix in start_time
        template.items.forEach((item, globalIndex) => {
            // Extract day from start_time (e.g., "mon 01:00 pm" -> "mon")
            let dayPrefix = 'unknown';
            if (item.start_time) {
                const dayMatch = item.start_time.toLowerCase().match(/^(\w{3})\s/);
                if (dayMatch) {
                    dayPrefix = dayMatch[1];
                }
            }
            
            if (!dayGroups[dayPrefix]) {
                dayGroups[dayPrefix] = [];
            }
            dayGroups[dayPrefix].push({item: item, globalIndex: globalIndex});
        });
        
        // Display items grouped by day in order
        dayOrder.forEach(day => {
            if (dayGroups[day] && dayGroups[day].length > 0) {
                html += `
                    <div class="scheduling-template-day-header">
                        <h4>${dayNames[day]}</h4>
                    </div>
                `;
                
                dayGroups[day].forEach((itemData, index) => {
                    html += schedulingGenerateItemHTML(itemData.item, itemData.globalIndex + 1);
                });
            }
        });
        
        // Handle any items without recognized day prefix
        if (dayGroups['unknown'] && dayGroups['unknown'].length > 0) {
            html += `
                <div class="scheduling-template-day-header">
                    <h4>Unscheduled</h4>
                </div>
            `;
            dayGroups['unknown'].forEach((itemData, index) => {
                html += schedulingGenerateItemHTML(itemData.item, itemData.globalIndex + 1);
            });
        }
    } else {
        // Daily template - show all items
        console.log('Processing daily template items...');
        template.items.forEach((item, index) => {
            html += schedulingGenerateItemHTML(item, index + 1);
        });
    }
    
    html += '</div>';
    return html;
}

// Generate HTML for a single item
function schedulingGenerateItemHTML(item, index) {
    // Try multiple fields for title - prefer content_title over filename
    let title = item.content_title || item.title || item.filename || item.file_name || 'Untitled';
    
    // If we're using filename/file_name, remove the extension
    if (!item.content_title && !item.title && (item.filename || item.file_name)) {
        const filename = item.filename || item.file_name;
        const lastDotIndex = filename.lastIndexOf('.');
        if (lastDotIndex > 0) {
            title = filename.substring(0, lastDotIndex);
        } else {
            title = filename;
        }
    }
    
    // For weekly templates, display the time without the day prefix (it's already in the header)
    let displayTime = item.start_time || '00:00:00';
    if (item.template_type === 'weekly' || item.has_day_prefix) {
        // Extract just the time part from weekly format (e.g., "mon 01:00 pm" -> "01:00 pm")
        const timeMatch = displayTime.match(/^\w{3}\s+(.+)$/);
        if (timeMatch) {
            displayTime = timeMatch[1];
        }
    }
    
    // Format time with milliseconds if formatTimeWithMilliseconds function is available
    const startTime = typeof formatTimeWithMilliseconds === 'function' 
        ? formatTimeWithMilliseconds(displayTime)
        : displayTime;
    
    // Calculate duration from start_time and end_time if both are available
    let durationSeconds = item.duration_seconds || item.file_duration || 0;
    if (item.start_time && item.end_time) {
        try {
            // Use the calculateDurationFromTimes function if available
            if (typeof calculateDurationFromTimes === 'function') {
                durationSeconds = calculateDurationFromTimes(item.start_time, item.end_time);
            } else {
                // Fallback calculation for weekly templates
                const startSec = parseTimeToSeconds(item.start_time, item.template_type || 'daily');
                const endSec = parseTimeToSeconds(item.end_time, item.template_type || 'daily');
                if (endSec >= startSec) {
                    durationSeconds = endSec - startSec;
                }
            }
        } catch (e) {
            console.warn('Failed to calculate duration from times:', e);
            // Fall back to stored duration
        }
    }
    
    const duration = schedulingFormatDuration(durationSeconds);
    const category = item.category || item.duration_category || 'NO CATEGORY';
    
    return `
        <div class="scheduling-template-item">
            <span class="scheduling-template-item-number">${index}</span>
            <span class="scheduling-template-item-time">${startTime}</span>
            <span class="scheduling-template-item-title" title="${title}">${title}</span>
            <span class="scheduling-template-item-duration">${duration}</span>
            <span class="scheduling-template-item-category">${category}</span>
        </div>
    `;
}

// Group items by day for weekly templates
function schedulingGroupItemsByDay(items) {
    const groups = {};
    
    items.forEach(item => {
        const day = item.day || 0;
        if (!groups[day]) {
            groups[day] = [];
        }
        groups[day].push(item);
    });
    
    return groups;
}

// Format duration in seconds to HH:MM:SS.mmm with milliseconds
function schedulingFormatDuration(seconds) {
    const duration = parseFloat(seconds) || 0;
    const hours = Math.floor(duration / 3600);
    const minutes = Math.floor((duration % 3600) / 60);
    const secs = Math.floor(duration % 60);
    const milliseconds = Math.round((duration % 1) * 1000);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
}

// Format time string to ensure it has milliseconds (HH:MM:SS.mmm)
function formatTimeWithMilliseconds(timeStr) {
    if (!timeStr) return '00:00:00.000';
    
    // If already has milliseconds, return as is
    if (timeStr.includes('.')) {
        return timeStr;
    }
    
    // Add .000 milliseconds if missing
    return timeStr + '.000';
}

// Calculate duration from start and end times
function calculateDurationFromTimes(startTime, endTime) {
    if (!startTime || !endTime) return 0;
    
    // Parse times for weekly format
    const dayMap = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
    let startDay = null, endDay = null;
    let startTimeOnly = startTime;
    let endTimeOnly = endTime;
    
    // Extract day prefixes if present
    if (startTime.includes(' ')) {
        const parts = startTime.split(' ', 1);
        if (dayMap.hasOwnProperty(parts[0].toLowerCase())) {
            startDay = dayMap[parts[0].toLowerCase()];
            startTimeOnly = startTime.substring(parts[0].length + 1);
        }
    }
    
    if (endTime.includes(' ')) {
        const parts = endTime.split(' ', 1);
        if (dayMap.hasOwnProperty(parts[0].toLowerCase())) {
            endDay = dayMap[parts[0].toLowerCase()];
            endTimeOnly = endTime.substring(parts[0].length + 1);
        }
    }
    
    // Convert times to seconds
    const startSec = parseTimeToSecondsSimple(startTimeOnly);
    const endSec = parseTimeToSecondsSimple(endTimeOnly);
    
    // Calculate day difference if we have day prefixes
    let dayDiff = 0;
    if (startDay !== null && endDay !== null) {
        dayDiff = endDay - startDay;
        if (dayDiff < 0) dayDiff += 7; // Wrap around week
    } else if (endSec < startSec) {
        // No day prefixes but end time is before start time, assume next day
        dayDiff = 1;
    }
    
    // Calculate total duration
    return (dayDiff * 24 * 3600) + endSec - startSec;
}

// Simple time parser for HH:MM:SS or HH:MM:SS.mmm format with AM/PM support
function parseTimeToSecondsSimple(timeStr) {
    if (!timeStr) return 0;
    
    // Handle AM/PM format
    const isPM = timeStr.toLowerCase().includes('pm');
    const isAM = timeStr.toLowerCase().includes('am');
    
    // Remove AM/PM and trim
    let cleanTime = timeStr.replace(/\s*(am|pm)\s*/i, '').trim();
    
    // Split time and milliseconds
    let milliseconds = 0;
    if (cleanTime.includes('.')) {
        const parts = cleanTime.split('.');
        cleanTime = parts[0];
        milliseconds = parseFloat('0.' + parts[1]) || 0;
    }
    
    // Parse time components
    const parts = cleanTime.split(':');
    let hours = parseInt(parts[0]) || 0;
    const minutes = parseInt(parts[1]) || 0;
    const seconds = parseFloat(parts[2]) || 0;
    
    // Adjust for AM/PM
    if (isPM && hours < 12) hours += 12;
    if (isAM && hours === 12) hours = 0;
    
    return hours * 3600 + minutes * 60 + seconds + milliseconds;
}

// Export functions to global scope
window.schedulingTemplatesInit = schedulingTemplatesInit;
window.schedulingDisplayTemplate = schedulingDisplayTemplate;
window.schedulingGenerateTemplateHTML = schedulingGenerateTemplateHTML;
window.formatTimeWithMilliseconds = formatTimeWithMilliseconds;
window.calculateDurationFromTimes = calculateDurationFromTimes;

// Hook into global template loading
window.addEventListener('templateLoaded', function(event) {
    console.log('Scheduling module: template loaded event received');
    if (event.detail && event.detail.template) {
        schedulingDisplayTemplate(event.detail.template);
    }
});

// Initialize when loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedulingTemplatesInit);
} else {
    schedulingTemplatesInit();
}