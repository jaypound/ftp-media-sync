/**
 * Settings Module
 * Handles sync settings and file filtering options
 */

// Settings State
const settingsState = {
    fileFilter: 'mp4,mkv,avi,mov,wmv',
    minFileSize: 1,
    maxFileSize: 50,
    includeSubdirs: true,
    overwriteExisting: false,
    dryRun: false,
    dryRunDelete: true,
    keepTempFiles: false,
    autoSave: true
};

// Initialize Settings Module
function settingsInit() {
    console.log('Initializing Settings module...');
    
    // Load saved settings
    settingsLoadConfig();
    
    // Set up event listeners
    settingsSetupEventListeners();
    
    // Update AppState
    AppState.setModule('settings', settingsState);
}

// Set up event listeners
function settingsSetupEventListeners() {
    // Text inputs
    const textInputs = [
        'fileFilter',
        'minFileSize',
        'maxFileSize'
    ];
    
    textInputs.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', settingsHandleInputChange);
        }
    });
    
    // Checkboxes
    const checkboxes = [
        'includeSubdirs',
        'overwriteExisting',
        'dryRun',
        'dryRunDelete',
        'keepTempFiles'
    ];
    
    checkboxes.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', settingsHandleCheckboxChange);
        }
    });
}

// Load configuration
async function settingsLoadConfig() {
    try {
        const response = await window.API.get('/config');
        if (response.success && response.config) {
            const config = response.config;
            
            // Update settings from config
            if (config.sync_settings) {
                Object.assign(settingsState, config.sync_settings);
            }
            
            // Update UI
            settingsUpdateUI();
        }
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

// Update UI with current settings
function settingsUpdateUI() {
    // Update text inputs
    const fileFilterInput = document.getElementById('fileFilter');
    if (fileFilterInput) fileFilterInput.value = settingsState.fileFilter;
    
    const minSizeInput = document.getElementById('minFileSize');
    if (minSizeInput) minSizeInput.value = settingsState.minFileSize;
    
    const maxSizeInput = document.getElementById('maxFileSize');
    if (maxSizeInput) maxSizeInput.value = settingsState.maxFileSize;
    
    // Update checkboxes
    const checkboxes = [
        'includeSubdirs',
        'overwriteExisting',
        'dryRun',
        'dryRunDelete',
        'keepTempFiles'
    ];
    
    checkboxes.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.checked = settingsState[id];
        }
    });
}

// Handle input changes
function settingsHandleInputChange(event) {
    const input = event.target;
    const id = input.id;
    let value = input.value;
    
    // Handle numeric inputs
    if (id === 'minFileSize' || id === 'maxFileSize') {
        value = parseFloat(value) || 0;
        
        // Validate min/max relationship
        if (id === 'minFileSize' && value > settingsState.maxFileSize) {
            value = settingsState.maxFileSize;
            input.value = value;
            window.showNotification('Minimum size cannot exceed maximum size', 'warning');
        } else if (id === 'maxFileSize' && value < settingsState.minFileSize) {
            value = settingsState.minFileSize;
            input.value = value;
            window.showNotification('Maximum size cannot be less than minimum size', 'warning');
        }
    }
    
    // Update state
    settingsState[id] = value;
    
    // Auto-save if enabled
    if (settingsState.autoSave) {
        settingsSaveConfig();
    }
    
    // Update AppState
    AppState.setModule('settings', settingsState);
}

// Handle checkbox changes
function settingsHandleCheckboxChange(event) {
    const checkbox = event.target;
    const id = checkbox.id;
    
    // Update state
    settingsState[id] = checkbox.checked;
    
    // Special handling for dry run options
    if (id === 'dryRun' && checkbox.checked) {
        window.showNotification('Dry run mode enabled - no actual changes will be made', 'info');
    }
    
    // Auto-save if enabled
    if (settingsState.autoSave) {
        settingsSaveConfig();
    }
    
    // Update AppState
    AppState.setModule('settings', settingsState);
}

// Save configuration
async function settingsSaveConfig() {
    try {
        const config = {
            sync_settings: {
                fileFilter: settingsState.fileFilter,
                minFileSize: settingsState.minFileSize,
                maxFileSize: settingsState.maxFileSize,
                includeSubdirs: settingsState.includeSubdirs,
                overwriteExisting: settingsState.overwriteExisting,
                dryRun: settingsState.dryRun,
                dryRunDelete: settingsState.dryRunDelete,
                keepTempFiles: settingsState.keepTempFiles
            }
        };
        
        await window.API.post('/config', config);
        console.log('Settings saved successfully');
    } catch (error) {
        console.error('Failed to save settings:', error);
        window.showNotification('Failed to save settings', 'error');
    }
}

// Get file extensions as array
function settingsGetFileExtensions() {
    return settingsState.fileFilter
        .split(',')
        .map(ext => ext.trim())
        .filter(ext => ext.length > 0);
}

// Get size limits in bytes
function settingsGetSizeLimits() {
    return {
        minBytes: settingsState.minFileSize * 1024 * 1024, // MB to bytes
        maxBytes: settingsState.maxFileSize * 1024 * 1024 * 1024 // GB to bytes
    };
}

// Export functions to global scope
window.settingsInit = settingsInit;
window.settingsGetFileExtensions = settingsGetFileExtensions;
window.settingsGetSizeLimits = settingsGetSizeLimits;
window.settingsSaveConfig = settingsSaveConfig;