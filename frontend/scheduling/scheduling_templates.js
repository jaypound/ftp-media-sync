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
    
    schedulingTemplateState.currentTemplate = template;
    schedulingTemplateState.templateLoaded = true;
    
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
    
    const hours = Math.floor(totalDuration / 3600);
    const minutes = Math.floor((totalDuration % 3600) / 60);
    const seconds = Math.floor(totalDuration % 60);
    const durationStr = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    const templateDurationEl = document.getElementById('schedulingTemplateDuration');
    if (templateDurationEl) {
        templateDurationEl.textContent = durationStr;
    }
    
    // Display template items
    const templateDisplayEl = document.getElementById('schedulingTemplateDisplay');
    if (templateDisplayEl) {
        templateDisplayEl.innerHTML = schedulingGenerateTemplateHTML(template);
    }
    
    // Show export button if template is loaded
    const exportBtn = document.getElementById('exportTemplateBtn');
    if (exportBtn) {
        exportBtn.style.display = 'inline-block';
    }
    
    console.log('Template displayed successfully:', template.filename);
}

// Generate HTML for template display
function schedulingGenerateTemplateHTML(template) {
    if (!template || !template.items || template.items.length === 0) {
        return '<p style="text-align: center; color: #666;">No items in template</p>';
    }
    
    let html = '<div class="scheduling-template-items">';
    
    // Add day headers for weekly templates
    if (template.type === 'weekly') {
        const dayGroups = schedulingGroupItemsByDay(template.items);
        
        Object.keys(dayGroups).forEach(day => {
            html += `
                <div class="scheduling-template-day-header">
                    <h4>Day ${parseInt(day) + 1}</h4>
                </div>
            `;
            
            dayGroups[day].forEach((item, index) => {
                html += schedulingGenerateItemHTML(item, index);
            });
        });
    } else {
        // Daily template - show all items
        template.items.forEach((item, index) => {
            html += schedulingGenerateItemHTML(item, index);
        });
    }
    
    html += '</div>';
    return html;
}

// Generate HTML for a single item
function schedulingGenerateItemHTML(item, index) {
    const title = item.title || item.filename || 'Untitled';
    const startTime = item.start_time || '00:00:00';
    const duration = schedulingFormatDuration(item.duration_seconds || 0);
    const category = item.category || '';
    
    return `
        <div class="scheduling-template-item">
            <span class="scheduling-template-item-number">${index + 1}</span>
            <span class="scheduling-template-item-time">${startTime}</span>
            <span class="scheduling-template-item-title">${title}</span>
            <span class="scheduling-template-item-category">${category}</span>
            <span class="scheduling-template-item-duration">${duration}</span>
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

// Format duration in seconds to HH:MM:SS
function schedulingFormatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Export functions to global scope
window.schedulingTemplatesInit = schedulingTemplatesInit;
window.schedulingDisplayTemplate = schedulingDisplayTemplate;
window.schedulingGenerateTemplateHTML = schedulingGenerateTemplateHTML;

// Initialize when loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedulingTemplatesInit);
} else {
    schedulingTemplatesInit();
}