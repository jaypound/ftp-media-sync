/**
 * Admin Module
 * Handles administration tasks, configuration management, and system tools
 */

// Admin State
const adminState = {
    backendStatus: 'checking',
    version: '1.0.0',
    uptime: '--',
    configLoaded: false,
    databaseStats: {
        totalAnalyses: 0,
        totalSchedules: 0,
        dbSize: '0 MB'
    }
};

// Initialize Admin Module
function adminInit() {
    console.log('Initializing Admin module...');
    
    // Check backend status
    adminCheckBackendStatus();
    
    // Set up periodic status checks
    setInterval(adminCheckBackendStatus, 30000); // Check every 30 seconds
    
    // Load initial stats
    adminLoadDatabaseStats();
    
    // Update AppState
    AppState.setModule('admin', adminState);
}

// Check backend status
async function adminCheckBackendStatus() {
    try {
        const response = await window.API.get('/status');
        if (response.success) {
            adminState.backendStatus = 'online';
            adminState.version = response.version || '1.0.0';
            adminState.uptime = response.uptime || '--';
            adminUpdateStatusDisplay();
        }
    } catch (error) {
        adminState.backendStatus = 'offline';
        adminUpdateStatusDisplay();
    }
}

// Update status display
function adminUpdateStatusDisplay() {
    const statusEl = document.getElementById('backendStatus');
    if (statusEl) {
        const statusClass = adminState.backendStatus === 'online' ? 'online' : 'offline';
        const statusIcon = adminState.backendStatus === 'online' ? 'fa-check-circle' : 'fa-times-circle';
        const statusText = adminState.backendStatus.charAt(0).toUpperCase() + adminState.backendStatus.slice(1);
        
        statusEl.innerHTML = `<span class="admin-status-indicator ${statusClass}"><i class="fas ${statusIcon}"></i> ${statusText}</span>`;
    }
    
    const versionEl = document.getElementById('versionInfo');
    if (versionEl) versionEl.textContent = adminState.version;
    
    const uptimeEl = document.getElementById('uptimeInfo');
    if (uptimeEl) uptimeEl.textContent = adminState.uptime;
}

// Load configuration
async function adminLoadConfig() {
    const button = event.target;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    
    try {
        const response = await window.API.get('/config');
        if (response.success) {
            adminState.configLoaded = true;
            
            // Update all module states
            if (window.serversLoadConfig) window.serversLoadConfig();
            if (window.settingsLoadConfig) window.settingsLoadConfig();
            if (window.aiSettingsLoadConfig) window.aiSettingsLoadConfig();
            
            window.showNotification('Configuration loaded successfully', 'success');
        }
    } catch (error) {
        window.showNotification('Failed to load configuration', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-upload"></i> Load Config';
    }
}

// Save configuration
async function adminSaveConfig() {
    const button = event.target;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    
    try {
        // Gather config from all modules
        const config = {};
        
        // Get server config
        if (window.serversState) {
            config.source_server = {
                host: window.serversState.source.host,
                port: window.serversState.source.port,
                user: window.serversState.source.user,
                path: window.serversState.source.path
            };
            config.target_server = {
                host: window.serversState.target.host,
                port: window.serversState.target.port,
                user: window.serversState.target.user,
                path: window.serversState.target.path
            };
        }
        
        // Get sync settings
        if (window.settingsState) {
            config.sync_settings = window.settingsState;
        }
        
        // Get AI settings
        if (window.aiSettingsState) {
            config.ai_settings = {
                enabled: window.aiSettingsState.enabled,
                transcriptionOnly: window.aiSettingsState.transcriptionOnly,
                provider: window.aiSettingsState.provider,
                model: window.aiSettingsState.model,
                maxChunkSize: window.aiSettingsState.maxChunkSize
            };
        }
        
        const response = await window.API.post('/config', config);
        if (response.success) {
            window.showNotification('Configuration saved successfully', 'success');
        }
    } catch (error) {
        window.showNotification('Failed to save configuration', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-save"></i> Save Config';
    }
}

// Create sample configuration
async function adminCreateSampleConfig() {
    const button = event.target;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
    
    try {
        const response = await window.API.post('/config/create-sample');
        if (response.success) {
            window.showNotification('Sample configuration created', 'success');
            adminShowFileInfo('config.sample.json', response.path);
        }
    } catch (error) {
        window.showNotification('Failed to create sample config', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-file-code"></i> Create Sample';
    }
}

// Reset form
function adminResetForm() {
    if (!confirm('Are you sure you want to reset all form fields? This will clear any unsaved changes.')) {
        return;
    }
    
    // Reset all input fields
    document.querySelectorAll('input[type="text"], input[type="number"], input[type="password"]').forEach(input => {
        input.value = '';
    });
    
    // Reset all checkboxes
    document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.checked = false;
    });
    
    // Reset all selects
    document.querySelectorAll('select').forEach(select => {
        select.selectedIndex = 0;
    });
    
    window.showNotification('Form reset successfully', 'info');
}

// Load database stats
async function adminLoadDatabaseStats() {
    try {
        const response = await window.API.get('/admin/database-stats');
        if (response.success) {
            adminState.databaseStats = response.stats;
            adminUpdateDatabaseDisplay();
        }
    } catch (error) {
        console.error('Failed to load database stats:', error);
    }
}

// Update database display
function adminUpdateDatabaseDisplay() {
    const stats = adminState.databaseStats;
    
    // Update displayed stats
    const elements = {
        'dbAnalysesCount': stats.totalAnalyses,
        'dbSchedulesCount': stats.totalSchedules,
        'dbSize': stats.dbSize
    };
    
    Object.entries(elements).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    });
}

// Clear all analyses
async function adminClearAllAnalyses() {
    if (!confirm('Are you sure you want to delete ALL analysis data? This action cannot be undone.')) {
        return;
    }
    
    if (!confirm('This will permanently delete all AI analysis results. Are you absolutely sure?')) {
        return;
    }
    
    const button = event.target;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
    
    try {
        const response = await window.API.delete('/analyses/all');
        if (response.success) {
            window.showNotification('All analysis data deleted successfully', 'success');
            adminLoadDatabaseStats();
        }
    } catch (error) {
        window.showNotification('Failed to delete analysis data', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-trash-alt"></i> Clear All Analysis Data';
    }
}

// Show file info
function adminShowFileInfo(filename, path) {
    const infoBox = document.querySelector('.admin-file-info');
    if (infoBox) {
        infoBox.innerHTML = `
            <h4><i class="fas fa-file"></i> File Created</h4>
            <p><strong>Filename:</strong> ${filename}</p>
            <p><strong>Path:</strong> ${path}</p>
            <p><strong>Created:</strong> ${new Date().toLocaleString()}</p>
        `;
        infoBox.style.display = 'block';
    }
}

// View backend logs
async function adminViewLogs() {
    const button = event.target;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading logs...';
    
    try {
        const response = await window.API.get('/admin/logs');
        if (response.success) {
            adminDisplayLogs(response.logs);
        }
    } catch (error) {
        window.showNotification('Failed to load logs', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-file-alt"></i> View Logs';
    }
}

// Display logs
function adminDisplayLogs(logs) {
    const logViewer = document.querySelector('.admin-log-viewer');
    if (logViewer) {
        logViewer.textContent = logs || 'No logs available';
        logViewer.style.display = 'block';
        
        // Scroll to bottom
        logViewer.scrollTop = logViewer.scrollHeight;
    }
}

// Export functions to global scope
window.adminInit = adminInit;
window.adminLoadConfig = adminLoadConfig;
window.adminSaveConfig = adminSaveConfig;
window.adminCreateSampleConfig = adminCreateSampleConfig;
window.adminResetForm = adminResetForm;
window.adminClearAllAnalyses = adminClearAllAnalyses;
window.adminViewLogs = adminViewLogs;

// Legacy support
window.loadConfig = adminLoadConfig;
window.saveConfig = adminSaveConfig;
window.createSampleConfig = adminCreateSampleConfig;
window.resetForm = adminResetForm;
window.clearAllAnalyses = adminClearAllAnalyses;