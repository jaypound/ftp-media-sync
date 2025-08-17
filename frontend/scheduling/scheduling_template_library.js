/**
 * Scheduling Template Library Module
 * Handles saved template library functionality
 */

// Template Library State
const schedulingTemplateLibraryState = {
    savedTemplates: [],
    currentViewIndex: null
};

// Initialize Template Library Module
function schedulingTemplateLibraryInit() {
    console.log('Initializing Scheduling Template Library module...');
    
    // Load saved templates from localStorage
    schedulingLoadSavedTemplates();
    
    // Override legacy functions
    if (window.viewTemplate) {
        window.viewTemplate = schedulingViewTemplate;
    }
    if (window.loadSavedTemplate) {
        window.loadSavedTemplate = schedulingLoadSavedTemplate;
    }
    if (window.loadTemplateLibrary) {
        window.loadTemplateLibrary = schedulingLoadTemplateLibrary;
    }
    if (window.showTemplateLibrary) {
        window.showTemplateLibrary = schedulingShowTemplateLibrary;
    }
    if (window.closeTemplateLibraryModal) {
        window.closeTemplateLibraryModal = schedulingCloseTemplateLibraryModal;
    }
    if (window.exportTemplate) {
        window.exportTemplate = schedulingExportTemplate;
    }
    if (window.deleteTemplate) {
        window.deleteTemplate = schedulingDeleteTemplate;
    }
}

// Load saved templates from localStorage
function schedulingLoadSavedTemplates() {
    try {
        // Test if localStorage is available
        const testKey = '__localStorage_test__';
        localStorage.setItem(testKey, 'test');
        localStorage.removeItem(testKey);
        
        const saved = localStorage.getItem('savedTemplates');
        if (saved) {
            schedulingTemplateLibraryState.savedTemplates = JSON.parse(saved);
        }
    } catch (e) {
        console.warn('localStorage is not available (possibly in Incognito mode):', e.message);
        schedulingTemplateLibraryState.savedTemplates = [];
        
        // Show a warning if we're in the template library
        if (document.getElementById('templateLibraryModal') && document.getElementById('templateLibraryModal').style.display === 'block') {
            const libraryList = document.getElementById('templateLibraryList');
            if (libraryList) {
                libraryList.innerHTML = '<p style="text-align: center; color: #ff6b6b; padding: 20px;">Template Library is not available in Incognito/Private browsing mode.<br>Please use a regular browser window to save and load templates.</p>';
            }
        }
    }
}

// View a template from the library
function schedulingViewTemplate(index) {
    const template = schedulingTemplateLibraryState.savedTemplates[index];
    if (!template) {
        console.error('Template not found at index:', index);
        return;
    }
    
    schedulingTemplateLibraryState.currentViewIndex = index;
    
    // Display the template
    if (window.schedulingDisplayTemplate) {
        window.schedulingDisplayTemplate(template);
    } else if (window.displayTemplate) {
        window.displayTemplate(template);
    }
    
    // Close the library modal
    const modal = document.getElementById('templateLibraryModal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    console.log('Viewing template:', template.filename || 'Untitled');
}

// Load a saved template into the current session
function schedulingLoadSavedTemplate(index) {
    const template = schedulingTemplateLibraryState.savedTemplates[index];
    if (!template) {
        console.error('Template not found at index:', index);
        return;
    }
    
    // Set as current template
    schedulingTemplateLibraryState.currentViewIndex = index;
    
    // Update global state - always set it
    window.currentTemplate = template;
    console.log('Template loaded from library to window.currentTemplate:', window.currentTemplate);
    
    // Display the template
    if (window.schedulingDisplayTemplate) {
        window.schedulingDisplayTemplate(template);
    } else if (window.displayTemplate) {
        window.displayTemplate(template);
    }
    
    // Show export button
    const exportBtn = document.getElementById('exportTemplateBtn');
    if (exportBtn) {
        exportBtn.style.display = 'inline-block';
    }
    
    // Close the library modal
    const modal = document.getElementById('templateLibraryModal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    // Show notification
    if (window.showNotification) {
        window.showNotification(`Loaded template: ${template.filename || 'Untitled'}`, 'success');
    }
    
    console.log('Loaded template:', template.filename || 'Untitled');
}

// Load and display the template library
function schedulingLoadTemplateLibrary() {
    const libraryList = document.getElementById('templateLibraryList');
    if (!libraryList) {
        console.error('Template library list element not found');
        return;
    }
    
    // Check if localStorage is available
    try {
        const testKey = '__localStorage_test__';
        localStorage.setItem(testKey, 'test');
        localStorage.removeItem(testKey);
    } catch (e) {
        libraryList.innerHTML = '<p style="text-align: center; color: #ff6b6b; padding: 20px;">Template Library is not available in Incognito/Private browsing mode.<br>Please use a regular browser window to save and load templates.</p>';
        return;
    }
    
    // Reload saved templates
    schedulingLoadSavedTemplates();
    const savedTemplates = schedulingTemplateLibraryState.savedTemplates;
    
    if (!savedTemplates || savedTemplates.length === 0) {
        libraryList.innerHTML = '<p style="text-align: center; color: #666;">No saved templates found</p>';
        return;
    }
    
    // Sort templates by save date (newest first)
    const sortedTemplates = [...savedTemplates].sort((a, b) => {
        const dateA = new Date(a.savedAt || 0);
        const dateB = new Date(b.savedAt || 0);
        return dateB - dateA;
    });
    
    let html = '';
    sortedTemplates.forEach((template, index) => {
        const originalIndex = savedTemplates.indexOf(template);
        const savedDate = template.savedAt ? new Date(template.savedAt).toLocaleDateString() : 'Unknown';
        const itemCount = template.items ? template.items.length : 0;
        const templateType = template.type === 'weekly' ? 'Weekly' : template.type === 'monthly' ? 'Monthly' : 'Daily';
        
        html += `
            <div class="template-library-item">
                <div class="template-library-info">
                    <h4>${template.filename || template.name || 'Untitled Template'}</h4>
                    <p><strong>Type:</strong> ${templateType} | <strong>Items:</strong> ${itemCount} | <strong>Saved:</strong> ${savedDate}</p>
                </div>
                <div class="template-library-actions">
                    <button class="button primary small" onclick="schedulingViewTemplate(${originalIndex})">
                        <i class="fas fa-eye"></i> View
                    </button>
                    <button class="button success small" onclick="schedulingLoadSavedTemplate(${originalIndex})">
                        <i class="fas fa-file-download"></i> Load
                    </button>
                    <button class="button secondary small" onclick="exportTemplate(${originalIndex})">
                        <i class="fas fa-file-export"></i> Export
                    </button>
                    <button class="button danger small" onclick="deleteTemplate(${originalIndex})">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            </div>
        `;
    });
    
    libraryList.innerHTML = html;
}

// Show the template library modal
function schedulingShowTemplateLibrary() {
    console.log('Opening scheduling template library');
    
    const modal = document.getElementById('templateLibraryModal');
    if (!modal) {
        console.error('Template library modal not found!');
        return;
    }
    
    modal.style.display = 'block';
    
    // Load the library
    schedulingLoadTemplateLibrary();
    
    // Ensure close button works
    const closeBtn = modal.querySelector('.modal-close');
    if (closeBtn) {
        closeBtn.onclick = function() {
            modal.style.display = 'none';
        };
    }
}

// Close the template library modal
function schedulingCloseTemplateLibraryModal() {
    console.log('Closing scheduling template library modal');
    
    const modal = document.getElementById('templateLibraryModal');
    if (modal) {
        modal.style.display = 'none';
        modal.style.visibility = 'hidden';
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden', 'true');
    }
}

// Export a template from the library
function schedulingExportTemplate(index) {
    const template = schedulingTemplateLibraryState.savedTemplates[index];
    if (!template) {
        console.error('Template not found at index:', index);
        return;
    }
    
    // Set current export template
    if (window.currentExportTemplate !== undefined) {
        window.currentExportTemplate = template;
    }
    
    // Update export modal
    const exportTemplateNameEl = document.getElementById('exportTemplateName');
    if (exportTemplateNameEl) {
        exportTemplateNameEl.textContent = template.filename || template.name || 'Untitled Template';
    }
    
    // Set default filename
    const date = new Date();
    const dateStr = date.toISOString().split('T')[0].replace(/-/g, '');
    const templateType = template.type || 'daily';
    let defaultFilename = '';
    
    if (templateType === 'daily') {
        defaultFilename = `daily_${dateStr}.sch`;
    } else if (templateType === 'weekly') {
        defaultFilename = `weekly_${dateStr}.sch`;
    } else if (templateType === 'monthly') {
        defaultFilename = `monthly_${dateStr}.sch`;
    }
    
    const exportFilenameEl = document.getElementById('exportFilename');
    if (exportFilenameEl) {
        exportFilenameEl.value = defaultFilename;
    }
    
    // Show export modal
    const exportModal = document.getElementById('templateExportModal');
    if (exportModal) {
        exportModal.style.display = 'block';
    }
    
    console.log('Exporting template:', template.filename || 'Untitled');
}

// Delete a template from the library
function schedulingDeleteTemplate(index) {
    const template = schedulingTemplateLibraryState.savedTemplates[index];
    if (!template) {
        console.error('Template not found at index:', index);
        return;
    }
    
    if (confirm(`Delete template "${template.filename || template.name || 'Untitled'}"? This cannot be undone.`)) {
        // Remove from state
        schedulingTemplateLibraryState.savedTemplates.splice(index, 1);
        
        // Save to localStorage
        localStorage.setItem('savedTemplates', JSON.stringify(schedulingTemplateLibraryState.savedTemplates));
        
        // Reload the library display
        schedulingLoadTemplateLibrary();
        
        // Show notification
        if (window.showNotification) {
            window.showNotification(`Deleted template: ${template.filename || template.name || 'Untitled'}`, 'info');
        }
        
        console.log('Deleted template:', template.filename || 'Untitled');
    }
}

// Export functions to global scope
window.schedulingTemplateLibraryInit = schedulingTemplateLibraryInit;
window.schedulingViewTemplate = schedulingViewTemplate;
window.schedulingLoadSavedTemplate = schedulingLoadSavedTemplate;
window.schedulingLoadTemplateLibrary = schedulingLoadTemplateLibrary;
window.schedulingShowTemplateLibrary = schedulingShowTemplateLibrary;
window.schedulingCloseTemplateLibraryModal = schedulingCloseTemplateLibraryModal;
window.schedulingExportTemplate = schedulingExportTemplate;
window.schedulingDeleteTemplate = schedulingDeleteTemplate;

// Initialize when loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedulingTemplateLibraryInit);
} else {
    schedulingTemplateLibraryInit();
}