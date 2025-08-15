/**
 * Dashboard Module
 * Handles dashboard functionality and UI updates
 */

// Dashboard State
const dashboardState = {
    stats: {
        sourceStatus: 'Not Connected',
        targetStatus: 'Not Connected',
        fileCount: 0,
        syncQueueCount: 0
    },
    progressVisible: false,
    analysisRunning: false,
    syncRunning: false
};

// Initialize Dashboard Module
function dashboardInit() {
    console.log('Initializing Dashboard module...');
    
    // Set up event listeners
    AppState.on('panelChanged', (panel) => {
        if (panel === 'dashboard') {
            dashboardUpdateStats();
        }
    });
    
    // Initial stats update
    dashboardUpdateStats();
}

// Update dashboard statistics
async function dashboardUpdateStats() {
    try {
        // Get server status
        const sourceConnected = AppState.getModule('servers').sourceConnected || false;
        const targetConnected = AppState.getModule('servers').targetConnected || false;
        
        // Get file counts
        const scannedFiles = AppState.getModule('files').scannedFiles || { source: [], target: [] };
        const syncQueue = AppState.getModule('sync').queue || [];
        
        // Update stats
        dashboardState.stats = {
            sourceStatus: sourceConnected ? 'Connected' : 'Not Connected',
            targetStatus: targetConnected ? 'Connected' : 'Not Connected',
            fileCount: scannedFiles.source.length + scannedFiles.target.length,
            syncQueueCount: syncQueue.length
        };
        
        // Update UI
        dashboardUpdateStatsUI();
    } catch (error) {
        console.error('Failed to update dashboard stats:', error);
    }
}

// Update stats UI
function dashboardUpdateStatsUI() {
    const stats = dashboardState.stats;
    
    // Update source status
    const sourceStatusEl = document.getElementById('sourceStatusText');
    if (sourceStatusEl) {
        sourceStatusEl.textContent = stats.sourceStatus;
        sourceStatusEl.className = stats.sourceStatus === 'Connected' ? 'dashboard-status-connected' : 'dashboard-status-disconnected';
    }
    
    // Update target status
    const targetStatusEl = document.getElementById('targetStatusText');
    if (targetStatusEl) {
        targetStatusEl.textContent = stats.targetStatus;
        targetStatusEl.className = stats.targetStatus === 'Connected' ? 'dashboard-status-connected' : 'dashboard-status-disconnected';
    }
    
    // Update file count
    const fileCountEl = document.getElementById('fileCountText');
    if (fileCountEl) {
        fileCountEl.textContent = `${stats.fileCount} files`;
    }
    
    // Update sync queue
    const syncQueueEl = document.getElementById('syncStatusText');
    if (syncQueueEl) {
        syncQueueEl.textContent = `${stats.syncQueueCount} files queued`;
    }
}

// Show progress bar
function dashboardShowProgress(text = 'Processing...') {
    const progressContainer = document.getElementById('progressContainer');
    const progressText = document.getElementById('progressText');
    
    if (progressContainer) {
        progressContainer.style.display = 'block';
        dashboardState.progressVisible = true;
    }
    
    if (progressText) {
        progressText.textContent = text;
    }
}

// Update progress bar
function dashboardUpdateProgress(current, total) {
    const progressFill = document.getElementById('progressFill');
    const progressStats = document.getElementById('progressStats');
    
    if (progressFill && total > 0) {
        const percentage = Math.round((current / total) * 100);
        progressFill.style.width = `${percentage}%`;
        progressFill.textContent = `${percentage}%`;
    }
    
    if (progressStats) {
        progressStats.textContent = `${current} / ${total} files`;
    }
}

// Hide progress bar
function dashboardHideProgress() {
    const progressContainer = document.getElementById('progressContainer');
    
    if (progressContainer) {
        progressContainer.style.display = 'none';
        dashboardState.progressVisible = false;
    }
}

// Update analysis monitor
function dashboardUpdateAnalysisMonitor(data) {
    const monitor = document.getElementById('analysisMonitorStatus');
    if (!monitor) return;
    
    if (data.running) {
        monitor.style.display = 'block';
        
        // Update runtime
        const runtimeEl = document.getElementById('analysisRuntime');
        if (runtimeEl) runtimeEl.textContent = `Runtime: ${data.runtime || '0s'}`;
        
        // Update progress
        const progressEl = document.getElementById('analysisProgress');
        if (progressEl) progressEl.textContent = `Progress: ${data.lastUpdate || '0s ago'}`;
        
        // Update current file
        const fileEl = document.getElementById('currentFile');
        if (fileEl) fileEl.textContent = `File: ${data.currentFile || 'None'}`;
        
        // Update queue
        const queueEl = document.getElementById('queueRemaining');
        if (queueEl) queueEl.textContent = `Queue: ${data.queueSize || 0}`;
        
        // Update rescan status
        const rescanEl = document.getElementById('rescanStatus');
        if (rescanEl && data.rescanEnabled) {
            rescanEl.style.display = 'inline';
            rescanEl.textContent = `Next Rescan: ${data.nextRescan || '--'}`;
        }
    } else {
        monitor.style.display = 'none';
    }
}

// Handle button states
function dashboardUpdateButtonStates(states) {
    const buttons = {
        'scanButton': states.scan,
        'compareButton': states.compare,
        'analyzeFilesBtn': states.analyze,
        'syncButton': states.sync,
        'stopButton': states.stop,
        'deleteButton': states.delete
    };
    
    Object.entries(buttons).forEach(([id, enabled]) => {
        const button = document.getElementById(id);
        if (button) {
            button.disabled = !enabled;
        }
    });
}

// Export functions to global scope
window.dashboardInit = dashboardInit;
window.dashboardUpdateStats = dashboardUpdateStats;
window.dashboardShowProgress = dashboardShowProgress;
window.dashboardUpdateProgress = dashboardUpdateProgress;
window.dashboardHideProgress = dashboardHideProgress;
window.dashboardUpdateAnalysisMonitor = dashboardUpdateAnalysisMonitor;
window.dashboardUpdateButtonStates = dashboardUpdateButtonStates;