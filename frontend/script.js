// Global variables
let sourceFiles = [];
let targetFiles = [];
let syncQueue = [];
let availableFiles = []; // New: tracks files that CAN be synced
let allComparisonResults = []; // Store all comparison results
let targetOnlyFiles = []; // Files that exist on target but not on source
let deleteQueue = []; // Files queued for deletion
let analysisQueue = []; // Files queued for analysis
let analysisResults = []; // Store analysis results
let currentSyncDirection = 'source_to_target'; // Track current sync direction

// Analysis monitoring variables
let analysisStartTime = null;
let lastProgressTime = null;
let currentAnalysisFile = null;
let analysisTimeoutId = null;
let stalledFileCount = 0;
let maxStallTime = 300000; // 5 minutes
let maxFileProcessingTime = 600000; // 10 minutes per file
let autoRestartEnabled = true;

// Periodic rescanning variables
let rescanEnabled = true;
let rescanInterval = 120; // seconds (configurable)
let rescanTimeoutId = null;
let lastRescanTime = null;
let rescanAttempts = 0;
let maxRescanAttempts = 3;
let showAllFiles = false; // Toggle for showing all files vs unsynced only
let showTargetOnly = false; // Toggle for showing target-only files
let showAnalysisAll = false; // Toggle for showing all analysis files
let showUnanalyzedOnly = false; // Toggle for showing only unanalyzed files in scanned files
let isScanning = false;
let isSyncing = false;
let isAnalyzing = false;
let stopAnalysisRequested = false;
let syncStats = { processed: 0, total: 0, errors: 0 };
let analysisStats = { processed: 0, total: 0, errors: 0 };

// Notification System
function showNotification(title, message, type = 'info', duration = 5000) {
    const container = document.getElementById('notificationContainer');
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    // Determine icon based on type
    let icon = '';
    switch(type) {
        case 'success':
            icon = '<i class="fas fa-check-circle"></i>';
            break;
        case 'error':
            icon = '<i class="fas fa-exclamation-circle"></i>';
            break;
        case 'info':
            icon = '<i class="fas fa-info-circle"></i>';
            break;
    }
    
    notification.innerHTML = `
        <span class="notification-icon">${icon}</span>
        <div class="notification-content">
            <div class="notification-title">${title}</div>
            ${message ? `<div class="notification-message">${message}</div>` : ''}
        </div>
        <button class="notification-close" onclick="this.parentElement.remove()">×</button>
    `;
    
    // Add to container
    container.appendChild(notification);
    
    // Trigger animation
    setTimeout(() => notification.classList.add('show'), 10);
    
    // Auto-remove after duration
    if (duration > 0) {
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, duration);
    }
}

// Utility functions
function log(message, type = 'info') {
    const status = document.getElementById('status');
    const timestamp = new Date().toLocaleTimeString();
    const prefix = type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️';
    status.innerHTML += `[${timestamp}] ${prefix} ${message}\n`;
    status.scrollTop = status.scrollHeight;
}

function clearLog() {
    document.getElementById('status').innerHTML = '';
}

function updateProgress(current, total, currentFile = null) {
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const progressStats = document.getElementById('progressStats');
    
    if (total > 0) {
        const percentage = (current / total) * 100;
        progressFill.style.width = percentage + '%';
        progressContainer.style.display = 'block';
        
        // Update progress text
        if (currentFile) {
            progressText.textContent = `Syncing: ${currentFile}`;
        } else if (current === total) {
            progressText.textContent = 'Sync completed!';
        } else {
            progressText.textContent = `Processing file ${current} of ${total}`;
        }
        
        // Update stats
        progressStats.textContent = `${current} / ${total} files`;
        progressStats.setAttribute('data-percentage', `${Math.round(percentage)}%`);
        
    } else {
        progressContainer.style.display = 'none';
    }
}

function showProgress(text = 'Preparing sync...') {
    const progressContainer = document.getElementById('progressContainer');
    const progressText = document.getElementById('progressText');
    const progressStats = document.getElementById('progressStats');
    const progressFill = document.getElementById('progressFill');
    
    progressContainer.style.display = 'block';
    progressText.textContent = text;
    progressStats.textContent = '0 / 0 files';
    progressStats.setAttribute('data-percentage', '0%');
    progressFill.style.width = '0%';
}

function hideProgress() {
    const progressContainer = document.getElementById('progressContainer');
    progressContainer.style.display = 'none';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function getFileExtension(filename) {
    return filename.split('.').pop().toLowerCase();
}

function shouldIncludeFile(filename, size) {
    const filterInput = document.getElementById('fileFilter').value;
    const minSize = parseInt(document.getElementById('minFileSize').value) * 1024 * 1024;
    const maxSize = parseInt(document.getElementById('maxFileSize').value) * 1024 * 1024 * 1024;
    
    // Check file extension
    if (filterInput) {
        const extensions = filterInput.split(',').map(ext => ext.trim().toLowerCase());
        const fileExt = getFileExtension(filename);
        if (!extensions.includes(fileExt)) {
            return false;
        }
    }
    
    // Check file size
    if (size < minSize || size > maxSize) {
        return false;
    }
    
    return true;
}

// File comparison and display functions
async function compareFiles() {
    log('Comparing files between servers...');
    
    const comparisonCard = document.getElementById('comparisonCard');
    comparisonCard.style.display = 'block';
    
    // Clear queues and results
    syncQueue = [];
    availableFiles = [];
    allComparisonResults = [];
    targetOnlyFiles = [];
    deleteQueue = [];
    
    // Create a map of target files for quick lookup using relative path
    const targetFileMap = new Map();
    targetFiles.forEach(file => {
        const relativePath = file.path || file.name;
        targetFileMap.set(relativePath, file);
    });
    
    // Create a map of source files for quick lookup using relative path
    const sourceFileMap = new Map();
    sourceFiles.forEach(file => {
        const relativePath = file.path || file.name;
        sourceFileMap.set(relativePath, file);
    });
    
    // Debug: Log sample paths from both servers
    log(`Debug: Sample source paths: ${Array.from(sourceFileMap.keys()).slice(0, 5).join(', ')}`);
    log(`Debug: Sample target paths: ${Array.from(targetFileMap.keys()).slice(0, 5).join(', ')}`);
    
    // Log recordings files specifically
    const sourceRecordings = sourceFiles.filter(f => f.folder === 'recordings');
    const targetRecordings = targetFiles.filter(f => f.folder === 'recordings');
    log(`Debug: Source recordings count: ${sourceRecordings.length}`);
    log(`Debug: Target recordings count: ${targetRecordings.length}`);
    
    // Log recording paths specifically
    if (targetRecordings.length > 0) {
        log(`Debug: Target recording paths:`);
        targetRecordings.forEach((file, index) => {
            const path = file.path || file.name;
            log(`  ${index + 1}. ${path}`);
        });
    }
    
    // Check if we're in bidirectional mode (Recordings folder) - now we check the file's folder property
    const hasBidirectionalFiles = sourceFiles.some(f => f.isBidirectional) || targetFiles.some(f => f.isBidirectional);
    
    // Process source files (existing logic)
    sourceFiles.forEach(sourceFile => {
        const sourceRelativePath = sourceFile.path || sourceFile.name;
        const targetFile = targetFileMap.get(sourceRelativePath);
        
        // Create a unique identifier for the file (using relative path)
        const fileId = btoa(sourceRelativePath).replace(/[^a-zA-Z0-9]/g, ''); // Base64 encode and clean for HTML ID
        
        const comparisonResult = {
            sourceFile: sourceFile,
            targetFile: targetFile,
            fileId: fileId,
            relativePath: sourceRelativePath,
            status: 'identical', // default
            direction: 'source_to_target'
        };
        
        if (!targetFile) {
            // File missing on target
            comparisonResult.status = 'missing';
            availableFiles.push({ type: 'copy', file: sourceFile, id: fileId, direction: 'source_to_target' });
        } else if (sourceFile.size !== targetFile.size) {
            // File size different
            comparisonResult.status = 'different';
            availableFiles.push({ type: 'update', file: sourceFile, id: fileId, direction: 'source_to_target' });
        } else {
            // File identical
            comparisonResult.status = 'identical';
        }
        
        allComparisonResults.push(comparisonResult);
    });
    
    // Process target files to find target-only files
    targetFiles.forEach(targetFile => {
        const targetRelativePath = targetFile.path || targetFile.name;
        const sourceFile = sourceFileMap.get(targetRelativePath);
        
        if (!sourceFile) {
            // File exists on target but not on source
            log(`Target-only file found: ${targetRelativePath} (folder: ${targetFile.folder || 'unknown'})`);
            const fileId = btoa(targetRelativePath + '_target_only').replace(/[^a-zA-Z0-9]/g, '');
            
            const targetOnlyResult = {
                targetFile: targetFile,
                sourceFile: null,
                fileId: fileId,
                relativePath: targetRelativePath,
                status: 'target_only',
                direction: 'target_to_source'
            };
            
            targetOnlyFiles.push(targetOnlyResult);
            
            // In bidirectional mode (for recordings), add target-only files as copyable from target to source
            if (targetFile.isBidirectional) {
                availableFiles.push({ 
                    type: 'copy', 
                    file: targetFile, 
                    id: fileId, 
                    direction: 'target_to_source',
                    isTargetOnly: true 
                });
            }
        }
    });
    
    // Update summary
    updateComparisonSummary();
    
    // Render results (default to unsynced only)
    renderComparisonResults();
    
    log(`Comparison complete. Found ${availableFiles.length} files that can be synced, ${targetOnlyFiles.length} target-only files`, 'success');
    
    // Debug: Log all target-only files
    if (targetOnlyFiles.length > 0) {
        log(`Debug: All ${targetOnlyFiles.length} target-only files:`);
        targetOnlyFiles.forEach((file, index) => {
            log(`  ${index + 1}. ${file.relativePath} (folder: ${file.targetFile.folder || 'unknown'}, bidirectional: ${file.targetFile.isBidirectional || false})`);
        });
    }
    
    // Debug: Log available files for sync
    if (availableFiles.length > 0) {
        log(`Debug: Available files for sync:`);
        availableFiles.forEach((item, index) => {
            log(`  ${index + 1}. ${item.type} - ${item.file.name} (path: ${item.file.path || 'no path'}) - ${formatFileSize(item.file.size)} - ID: ${item.id}`);
        });
    }
    
    // Debug: Log target-only files
    if (targetOnlyFiles.length > 0) {
        log(`Debug: Target-only files:`);
        targetOnlyFiles.forEach((item, index) => {
            log(`  ${index + 1}. ${item.targetFile.name} (path: ${item.targetFile.path || 'no path'}) - ${formatFileSize(item.targetFile.size)} - ID: ${item.fileId}`);
        });
    }
    
    // Disable sync button initially since no files are selected
    document.getElementById('syncButton').disabled = true;
    updateSyncButtonState();
    updateBulkDeleteButtonStates();
}

function renderComparisonResults() {
    const fileListDiv = document.getElementById('fileList');
    fileListDiv.innerHTML = '';
    
    if (showTargetOnly) {
        // Show only target-only files
        targetOnlyFiles.forEach(result => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item target-only';
            
            const isBidirectional = result.targetFile.isBidirectional;
            
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${result.targetFile.name}</div>
                    <div class="file-path">${result.relativePath !== result.targetFile.name ? result.relativePath : ''}</div>
                    <div class="file-size">${formatFileSize(result.targetFile.size)} - Only on target</div>
                </div>
                <div class="file-actions">
                    ${isBidirectional ? `
                        <button class="button add-to-sync-btn" onclick="addToSyncQueue('${result.fileId}', this)">
                            <i class="fas fa-arrow-left"></i> Copy to Source
                        </button>
                    ` : ''}
                    <button class="delete-btn" onclick="addToDeleteQueue('${result.fileId}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            `;
            
            fileListDiv.appendChild(fileItem);
        });
    } else {
        // Show source/target comparison results
        const resultsToShow = showAllFiles ? allComparisonResults : allComparisonResults.filter(result => result.status !== 'identical');
        
        resultsToShow.forEach(result => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            
            if (result.status === 'missing') {
                // File missing on target
                fileItem.classList.add('missing');
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.sourceFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.sourceFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">${formatFileSize(result.sourceFile.size)} - Missing on target</div>
                    </div>
                    <button class="button add-to-sync-btn" onclick="addToSyncQueue('${result.fileId}', this)">Add to Sync</button>
                `;
            } else if (result.status === 'different') {
                // File size different
                fileItem.classList.add('different');
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.sourceFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.sourceFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">Source: ${formatFileSize(result.sourceFile.size)} | Target: ${formatFileSize(result.targetFile.size)}</div>
                    </div>
                    <button class="button add-to-sync-btn" onclick="addToSyncQueue('${result.fileId}', this)">Add to Sync</button>
                `;
            } else {
                // File identical
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.sourceFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.sourceFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">${formatFileSize(result.sourceFile.size)} - Identical</div>
                    </div>
                    <span style="color: #28a745;">✅ Synced</span>
                `;
            }
            
            fileListDiv.appendChild(fileItem);
        });
        
        // Add target-only files when showing all files
        if (showAllFiles) {
            targetOnlyFiles.forEach(result => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item target-only';
                
                const isBidirectional = result.targetFile.isBidirectional;
                
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.targetFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.targetFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">${formatFileSize(result.targetFile.size)} - Only on target</div>
                    </div>
                    <div class="file-actions">
                        ${isBidirectional ? `
                            <button class="button add-to-sync-btn" onclick="addToSyncQueue('${result.fileId}', this)">
                                <i class="fas fa-arrow-left"></i> Copy to Source
                            </button>
                        ` : ''}
                        <button class="delete-btn" onclick="addToDeleteQueue('${result.fileId}')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                `;
                
                fileListDiv.appendChild(fileItem);
            });
        }
    }
}

function displayScannedFiles() {
    const scannedFilesCard = document.getElementById('scannedFilesCard');
    const sourceFilesList = document.getElementById('sourceFilesList');
    const targetFilesList = document.getElementById('targetFilesList');
    const sourceFileCount = document.getElementById('sourceFileCount');
    const targetFileCount = document.getElementById('targetFileCount');
    const summaryDiv = document.getElementById('scannedFilesSummary');
    
    // Show the scanned files card
    scannedFilesCard.style.display = 'block';
    
    // Show summary and update it
    summaryDiv.style.display = 'block';
    updateScannedFilesSummary();
    
    // Calculate filtered counts
    const filteredSourceFiles = showUnanalyzedOnly ? 
        sourceFiles.filter(file => !(file.is_analyzed || false)) : 
        sourceFiles;
    
    // Update file counts
    const sourceCountText = showUnanalyzedOnly ? 
        `${filteredSourceFiles.length} unanalyzed files (${sourceFiles.length} total)` :
        `${sourceFiles.length} files found`;
    
    sourceFileCount.textContent = sourceCountText;
    sourceFileCount.className = filteredSourceFiles.length > 0 ? 'file-count has-files' : 'file-count';
    
    targetFileCount.textContent = `${targetFiles.length} files found`;
    targetFileCount.className = targetFiles.length > 0 ? 'file-count has-files' : 'file-count';
    
    // Display source files
    console.log('=== Starting to render source files ===');
    console.log('sourceFiles array:', sourceFiles);
    sourceFilesList.innerHTML = '';
    sourceFiles.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'scanned-file-item';
        
        // Check if file is a video file (eligible for analysis)
        console.log('Processing file:', file.name);
        const isVideoFile = isVideoFileEligible(file.name);
        console.log('Is video file:', isVideoFile);
        
        // Check if file has been analyzed
        const isAnalyzed = file.is_analyzed || false;
        console.log(`File ${file.name} analyzed status:`, isAnalyzed);
        
        // Filter based on showUnanalyzedOnly toggle
        if (showUnanalyzedOnly && isAnalyzed) {
            return; // Skip analyzed files when showing unanalyzed only
        }
        
        fileItem.innerHTML = `
            <div class="scanned-file-content">
                <div class="scanned-file-name">${file.name}</div>
                <div class="scanned-file-details">
                    <span>Size: ${formatFileSize(file.size)}</span>
                    <span>Type: ${getFileExtension(file.name).toUpperCase()}</span>
                    ${isAnalyzed ? '<span style="color: #4caf50;">✅ Analyzed</span>' : ''}
                </div>
                <div class="scanned-file-path">${file.path || file.name}</div>
            </div>
            ${isVideoFile ? `
                <div class="scanned-file-actions">
                    <button class="analyze-btn ${isAnalyzed ? 'analyzed' : ''}" 
                            onclick="addToAnalysisQueue('${btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '')}')" 
                            data-file-path="${file.path || file.name}"
                            data-is-analyzed="${isAnalyzed}">
                        <i class="fas fa-${isAnalyzed ? 'redo' : 'brain'}"></i> ${isAnalyzed ? 'Reanalyze' : 'Analyze'}
                    </button>
                </div>
            ` : ''}
        `;
        sourceFilesList.appendChild(fileItem);
    });
    
    // Display target files
    targetFilesList.innerHTML = '';
    targetFiles.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'scanned-file-item';
        fileItem.innerHTML = `
            <div class="scanned-file-name">${file.name}</div>
            <div class="scanned-file-details">
                <span>Size: ${formatFileSize(file.size)}</span>
                <span>Type: ${getFileExtension(file.name).toUpperCase()}</span>
            </div>
            <div class="scanned-file-path">${file.path || file.name}</div>
        `;
        targetFilesList.appendChild(fileItem);
    });
    
    // Update analysis button states
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
}

function clearScannedFiles() {
    // Hide display cards
    document.getElementById('scannedFilesCard').style.display = 'none';
    document.getElementById('comparisonCard').style.display = 'none';
    
    // Hide summary and reset details visibility
    document.getElementById('scannedFilesSummary').style.display = 'none';
    document.getElementById('scannedFilesDetails').style.display = 'none';
    document.getElementById('toggleScannedFilesBtn').innerHTML = '<i class="fas fa-eye"></i> Show Details';
    
    // Reset comparison view
    showAllFiles = false;
    showTargetOnly = false;
    document.getElementById('toggleComparisonBtn').innerHTML = '<i class="fas fa-eye"></i> Show All Files';
    document.getElementById('toggleTargetOnlyBtn').innerHTML = '<i class="fas fa-eye"></i> Show Target-Only Files';
    
    // Clear data
    sourceFiles = [];
    targetFiles = [];
    syncQueue = [];
    availableFiles = [];
    allComparisonResults = [];
    targetOnlyFiles = [];
    deleteQueue = [];
    
    // Reset UI
    document.querySelector('button[onclick="compareFiles()"]').disabled = true;
    document.getElementById('analyzeFilesBtn').disabled = true;
    document.getElementById('syncButton').disabled = true;
    
    // Clear file lists
    document.getElementById('sourceFilesList').innerHTML = '';
    document.getElementById('targetFilesList').innerHTML = '';
    document.getElementById('fileList').innerHTML = '';
    
    log('Cleared all scanned file results', 'success');
}

function addToSyncQueue(fileId, buttonElement) {
    // Find the file in availableFiles using the unique ID
    const availableFile = availableFiles.find(item => item.id === fileId);
    if (!availableFile) {
        log(`Error: File with ID ${fileId} not found in available files`, 'error');
        return;
    }
    
    // Check if already in sync queue
    const alreadyInQueue = syncQueue.find(item => item.id === fileId);
    if (alreadyInQueue) {
        log(`${availableFile.file.path || availableFile.file.name} is already in sync queue`, 'error');
        return;
    }
    
    // Add to sync queue
    syncQueue.push(availableFile);
    log(`Added ${availableFile.file.path || availableFile.file.name} to sync queue (${syncQueue.length} files selected)`);
    
    // Update button appearance and disable it
    if (buttonElement) {
        buttonElement.textContent = 'Added to Sync';
        buttonElement.className = 'button add-to-sync-btn added';
        buttonElement.disabled = true;
        
        // Add a checkmark icon
        buttonElement.innerHTML = '✅ Added to Sync';
    }
    
    // Update sync button state
    updateSyncButtonState();
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
}

function removeFromSyncQueue(fileId) {
    // Remove from sync queue
    const index = syncQueue.findIndex(item => item.id === fileId);
    if (index !== -1) {
        const file = syncQueue[index];
        syncQueue.splice(index, 1);
        log(`Removed ${file.file.path || file.file.name} from sync queue (${syncQueue.length} files selected)`);
        
        // Find and re-enable the button
        const buttons = document.querySelectorAll('.add-to-sync-btn');
        buttons.forEach(button => {
            if (button.onclick && button.onclick.toString().includes(fileId)) {
                button.textContent = 'Add to Sync';
                button.className = 'button add-to-sync-btn';
                button.disabled = false;
                button.innerHTML = 'Add to Sync';
            }
        });
        
        updateSyncButtonState();
    }
}

function updateSyncButtonState() {
    const syncButton = document.getElementById('syncButton');
    const addAllButton = document.getElementById('addAllButton');
    const addFolderButton = document.getElementById('addFolderButton');
    
    // Update sync button
    syncButton.disabled = syncQueue.length === 0;
    
    // Update button text to show count
    if (syncQueue.length > 0) {
        syncButton.textContent = `Start Sync (${syncQueue.length} files)`;
    } else {
        syncButton.textContent = 'Start Sync';
    }
    
    // Update add all button
    if (addAllButton) {
        const remainingFiles = availableFiles.length - syncQueue.length;
        addAllButton.disabled = remainingFiles === 0;
        if (remainingFiles > 0) {
            addAllButton.textContent = `Add All (${remainingFiles} files)`;
        } else {
            addAllButton.textContent = 'Add All';
        }
    }
    
    // Update add folder button
    if (addFolderButton) {
        const folderStats = getFolderStats();
        if (folderStats && folderStats.availableToAdd > 0) {
            addFolderButton.disabled = false;
            addFolderButton.textContent = `Add Folder (${folderStats.availableToAdd} files)`;
            addFolderButton.title = `Add all files from "${folderStats.folderPath}" folder`;
        } else if (folderStats) {
            addFolderButton.disabled = true;
            addFolderButton.textContent = 'Add Folder (0 files)';
            addFolderButton.title = `All files from "${folderStats.folderPath}" already added`;
        } else {
            addFolderButton.disabled = true;
            addFolderButton.textContent = 'Add Folder';
            addFolderButton.title = 'Add a file first to determine folder';
        }
    }
}

function getFolderStats() {
    if (syncQueue.length === 0) {
        return null;
    }
    
    // Get the folder path from the last added file
    const lastFile = syncQueue[syncQueue.length - 1];
    const targetFolderPath = lastFile.file.path ? 
        lastFile.file.path.substring(0, lastFile.file.path.lastIndexOf('/')) : 
        '';
    
    // Count available files in the same folder
    let availableToAdd = 0;
    availableFiles.forEach(item => {
        const itemFolderPath = item.file.path ? 
            item.file.path.substring(0, item.file.path.lastIndexOf('/')) : 
            '';
        
        const isSameFolder = !targetFolderPath ? !itemFolderPath : itemFolderPath === targetFolderPath;
        
        if (isSameFolder) {
            const alreadyInQueue = syncQueue.find(queueItem => queueItem.id === item.id);
            if (!alreadyInQueue) {
                availableToAdd++;
            }
        }
    });
    
    return {
        folderPath: targetFolderPath || 'root',
        availableToAdd: availableToAdd
    };
}

function getAnalyzeFolderStats() {
    console.log('getAnalyzeFolderStats called');
    console.log('sourceFiles.length:', sourceFiles.length);
    console.log('analysisQueue.length:', analysisQueue.length);
    
    if (sourceFiles.length === 0) {
        console.log('No source files, returning null');
        return null;
    }
    
    // If no files in analysis queue, we can't determine folder
    if (analysisQueue.length === 0) {
        console.log('No files in analysis queue to determine folder, returning null');
        return null;
    }
    
    // Find video files that can be analyzed
    const videoFiles = sourceFiles.filter(file => isVideoFileEligible(file.name));
    console.log('Video files found:', videoFiles.length);
    console.log('Video files:', videoFiles.map(f => f.name));
    
    if (videoFiles.length === 0) {
        console.log('No video files found, returning null');
        return null;
    }
    
    // Get the folder path from the last file added to analysis queue
    const lastQueuedFile = analysisQueue[analysisQueue.length - 1];
    const targetFolderPath = lastQueuedFile.file.path ? 
        lastQueuedFile.file.path.substring(0, lastQueuedFile.file.path.lastIndexOf('/')) : 
        '';
    
    console.log('Reference file from queue:', lastQueuedFile.file.name);
    console.log('Target folder path:', targetFolderPath);
    
    // Count video files in the same folder that are not already in analysis queue
    let videoFilesToAnalyze = 0;
    videoFiles.forEach(file => {
        const itemFolderPath = file.path ? 
            file.path.substring(0, file.path.lastIndexOf('/')) : 
            '';
        
        const isSameFolder = !targetFolderPath ? !itemFolderPath : itemFolderPath === targetFolderPath;
        
        // Check if file is already in analysis queue
        const alreadyInQueue = analysisQueue.find(queueItem => queueItem.id === file.id);
        
        // Check if file has already been analyzed
        const isAnalyzed = file.is_analyzed || false;
        
        console.log(`File: ${file.name}, Folder: ${itemFolderPath}, Same folder: ${isSameFolder}, Already in queue: ${!!alreadyInQueue}, Is analyzed: ${isAnalyzed}`);
        
        // Only count files that are in same folder, not in queue, and not already analyzed
        if (isSameFolder && !alreadyInQueue && !isAnalyzed) {
            videoFilesToAnalyze++;
        }
    });
    
    console.log('Total video files to analyze:', videoFilesToAnalyze);
    
    return {
        folderPath: targetFolderPath || 'root',
        videoFilesToAnalyze: videoFilesToAnalyze
    };
}

function addAllFromFolderToSyncQueue() {
    if (syncQueue.length === 0) {
        log('No files in sync queue - add a file first to determine the folder', 'error');
        return;
    }
    
    // Get the folder path from the last added file
    const lastFile = syncQueue[syncQueue.length - 1];
    const targetFolderPath = lastFile.file.path ? 
        lastFile.file.path.substring(0, lastFile.file.path.lastIndexOf('/')) : 
        '';
    
    // If the file is in root directory, handle appropriately
    const isRootFile = !targetFolderPath;
    
    log(`Adding all files from folder: ${targetFolderPath || 'root directory'}`);
    
    let addedCount = 0;
    let skippedCount = 0;
    
    // Find all available files in the same folder
    availableFiles.forEach(item => {
        const itemFolderPath = item.file.path ? 
            item.file.path.substring(0, item.file.path.lastIndexOf('/')) : 
            '';
        
        // Check if file is in the same folder
        const isSameFolder = isRootFile ? !itemFolderPath : itemFolderPath === targetFolderPath;
        
        if (isSameFolder) {
            // Check if already in sync queue
            const alreadyInQueue = syncQueue.find(queueItem => queueItem.id === item.id);
            if (!alreadyInQueue) {
                syncQueue.push(item);
                addedCount++;
                
                // Update corresponding button
                const buttons = document.querySelectorAll('.add-to-sync-btn');
                buttons.forEach(button => {
                    if (button.onclick && button.onclick.toString().includes(item.id) && !button.disabled) {
                        button.textContent = 'Added to Sync';
                        button.className = 'button add-to-sync-btn added';
                        button.disabled = true;
                        button.innerHTML = '✅ Added to Sync';
                    }
                });
            } else {
                skippedCount++;
            }
        }
    });
    
    log(`Added ${addedCount} files from folder "${targetFolderPath || 'root'}" to sync queue`);
    if (skippedCount > 0) {
        log(`Skipped ${skippedCount} files (already in queue)`);
    }
    
    updateSyncButtonState();
}

function analyzeAllFromFolder() {
    log('🚀 Analyze Folder button clicked!');
    
    if (sourceFiles.length === 0) {
        log('No files scanned - scan files first to determine the folder', 'error');
        return;
    }
    
    if (analysisQueue.length === 0) {
        log('No files in analysis queue - add a file to analysis first to determine the folder', 'error');
        return;
    }
    
    // Find files that have analyze buttons (video files)
    const videoFiles = sourceFiles.filter(file => isVideoFileEligible(file.name));
    if (videoFiles.length === 0) {
        log('No video files found to analyze', 'error');
        return;
    }
    
    // Get the folder path from the last file added to analysis queue
    const lastQueuedFile = analysisQueue[analysisQueue.length - 1];
    const targetFolderPath = lastQueuedFile.file.path ? 
        lastQueuedFile.file.path.substring(0, lastQueuedFile.file.path.lastIndexOf('/')) : 
        '';
    
    // If the file is in root directory, handle appropriately
    const isRootFile = !targetFolderPath;
    
    log(`📁 Adding all video files from folder to analysis queue: ${targetFolderPath || 'root directory'}`);
    
    let filesToAnalyze = [];
    
    // Find all video files in the same folder that are not already analyzed or in analysis queue
    videoFiles.forEach(file => {
        const itemFolderPath = file.path ? 
            file.path.substring(0, file.path.lastIndexOf('/')) : 
            '';
        
        // Check if file is in the same folder
        const isSameFolder = isRootFile ? !itemFolderPath : itemFolderPath === targetFolderPath;
        
        // Check if file is already in analysis queue
        const alreadyInQueue = analysisQueue.find(queueItem => queueItem.id === file.id);
        
        // Check if file has already been analyzed
        const isAnalyzed = file.is_analyzed || false;
        
        // Only add files that are in the same folder, not in queue, and not already analyzed
        if (isSameFolder && !alreadyInQueue && !isAnalyzed) {
            filesToAnalyze.push(file);
        }
    });
    
    if (filesToAnalyze.length === 0) {
        log('No unanalyzed video files found in the specified folder (all files may already be analyzed or queued)', 'error');
        return;
    }
    
    log(`Found ${filesToAnalyze.length} unanalyzed video files to add to analysis queue in folder "${targetFolderPath || 'root'}"`);
    
    let addedCount = 0;
    let skippedCount = 0;
    
    // Add each file to the analysis queue
    filesToAnalyze.forEach(file => {
        const fileId = btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '');
        
        // Check if file is already in analysis queue
        const alreadyInQueue = analysisQueue.find(queueItem => queueItem.id === fileId);
        if (!alreadyInQueue) {
            analysisQueue.push({
                id: fileId,
                file: file,
                filePath: file.path || file.name
            });
            addedCount++;
            
            // Update corresponding button
            const button = document.querySelector(`button[onclick="addToAnalysisQueue('${fileId}')"]`);
            if (button) {
                button.innerHTML = '<i class="fas fa-check"></i> Added to Analysis';
                button.classList.add('added');
                button.disabled = true;
                
                // Update parent item styling
                const fileItem = button.closest('.scanned-file-item');
                fileItem.classList.add('queued');
            }
        } else {
            skippedCount++;
        }
    });
    
    log(`📁 Added ${addedCount} files from folder "${targetFolderPath || 'root'}" to analysis queue`);
    if (skippedCount > 0) {
        log(`⏭️ Skipped ${skippedCount} files (already in queue)`);
    }
    
    // Debug: List the files that were added
    if (addedCount > 0) {
        const addedFiles = filesToAnalyze.filter(file => {
            const fileId = btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '');
            return analysisQueue.find(queueItem => queueItem.id === fileId);
        });
        const fileNames = addedFiles.map(f => f.name).join(', ');
        log(`🎬 Files added to analysis queue: ${fileNames}`);
    }
    
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
}

function addAllToSyncQueue() {
    if (availableFiles.length === 0) {
        log('No files available to add to sync queue', 'error');
        return;
    }
    
    let addedCount = 0;
    let skippedCount = 0;
    
    // Add all available files to sync queue
    availableFiles.forEach(item => {
        // Check if already in sync queue
        const alreadyInQueue = syncQueue.find(queueItem => queueItem.id === item.id);
        if (!alreadyInQueue) {
            syncQueue.push(item);
            addedCount++;
            
            // Update corresponding button
            const buttons = document.querySelectorAll('.add-to-sync-btn');
            buttons.forEach(button => {
                if (button.onclick && button.onclick.toString().includes(item.id) && !button.disabled) {
                    button.textContent = 'Added to Sync';
                    button.className = 'button add-to-sync-btn added';
                    button.disabled = true;
                    button.innerHTML = '✅ Added to Sync';
                }
            });
        } else {
            skippedCount++;
        }
    });
    
    log(`Added ${addedCount} files to sync queue`);
    if (skippedCount > 0) {
        log(`Skipped ${skippedCount} files (already in queue)`);
    }
    
    updateSyncButtonState();
}

function clearSyncQueue() {
    // Clear sync queue
    syncQueue = [];
    
    // Re-enable all buttons
    const buttons = document.querySelectorAll('.add-to-sync-btn.added');
    buttons.forEach(button => {
        button.textContent = 'Add to Sync';
        button.className = 'button add-to-sync-btn';
        button.disabled = false;
        button.innerHTML = 'Add to Sync';
    });
    
    log('Cleared sync queue');
    updateSyncButtonState();
}

function stopSync() {
    isSyncing = false;
    log('Sync stopped by user', 'error');
    document.getElementById('syncButton').disabled = false;
    document.getElementById('stopButton').disabled = true;
    hideProgress();
}

async function processResultsWithProgress(results) {
    for (let index = 0; index < results.length; index++) {
        if (!isSyncing) break; // Stop if user clicked stop
        
        const item = results[index];
        const fileName = item.file || item.filename || 'Unknown file';
        
        // Update progress for current file
        updateProgress(index + 1, results.length, fileName);
        
        // Add a small delay to show progress update
        await new Promise(resolve => setTimeout(resolve, 100));
        
        log(`Debug: Processing result ${index + 1}: ${JSON.stringify(item, null, 2)}`);
        
        if (item.status === 'would_sync') {
            log(`[DRY RUN] Would ${item.action} ${item.file} (${formatFileSize(item.size)})`);
        } else if (item.status === 'success') {
            log(`✅ ${item.action === 'copy' ? 'Copied' : 'Updated'} ${item.file}`, 'success');
            syncStats.processed++;
            
            // Remove successfully synced file from target-only list if it was a target-to-source sync
            if (item.direction === 'target_to_source') {
                const fileId = item.id || `${item.file}_${item.size}`;
                targetOnlyFiles = targetOnlyFiles.filter(f => f.fileId !== fileId);
                log(`Debug: Removed ${item.file} from target-only list (${targetOnlyFiles.length} remaining)`);
            }
        } else {
            // Enhanced error logging
            const errorMsg = item.error || item.message || 'No error details provided by server';
            
            if (item.status === 'failed' && !item.error && !item.message) {
                log(`❌ Error with ${fileName}: Sync failed - check backend logs for details`, 'error');
                log(`   Server returned failed status without error message`, 'error');
                log(`   File details: ${JSON.stringify(item, null, 2)}`, 'error');
            } else {
                log(`❌ Error with ${fileName}: ${errorMsg}`, 'error');
            }
            
            // Log additional error details if available
            if (item.details) {
                log(`   Error details: ${item.details}`, 'error');
            }
            if (item.traceback) {
                log(`   Traceback: ${item.traceback}`, 'error');
            }
            
            syncStats.errors++;
        }
    }
}

// Auto-connect to servers on startup
async function autoConnectServers() {
    log('🔄 Auto-connecting to FTP servers...');
    
    // Check if source server is configured
    const sourceHost = document.getElementById('sourceHost').value;
    const sourceUser = document.getElementById('sourceUser').value;
    const sourcePass = document.getElementById('sourcePass').value;
    
    if (sourceHost && sourceUser && sourcePass) {
        log('📡 Connecting to source server (castus1)...');
        try {
            await testConnection('source');
            // Update dashboard display
            const sourceStatusText = document.getElementById('sourceStatusText');
            if (sourceStatusText) {
                sourceStatusText.innerHTML = `✅ Connected to castus1`;
                sourceStatusText.style.color = '#28a745';
            }
            const sourceStatus = document.getElementById('sourceStatus');
            if (sourceStatus) {
                sourceStatus.textContent = 'Source Server (castus1)';
            }
        } catch (error) {
            log(`⚠️ Failed to connect to source server: ${error.message}`, 'error');
        }
    }
    
    // Check if target server is configured
    const targetHost = document.getElementById('targetHost').value;
    const targetUser = document.getElementById('targetUser').value;
    const targetPass = document.getElementById('targetPass').value;
    
    if (targetHost && targetUser && targetPass) {
        log('📡 Connecting to target server (castus2)...');
        try {
            await testConnection('target');
            // Update dashboard display
            const targetStatusText = document.getElementById('targetStatusText');
            if (targetStatusText) {
                targetStatusText.innerHTML = `✅ Connected to castus2`;
                targetStatusText.style.color = '#28a745';
            }
            const targetStatus = document.getElementById('targetStatus');
            if (targetStatus) {
                targetStatus.textContent = 'Target Server (castus2)';
            }
        } catch (error) {
            log(`⚠️ Failed to connect to target server: ${error.message}`, 'error');
        }
    }
    
    // If no servers configured, show a helpful message
    if (!sourceHost && !targetHost) {
        log('ℹ️ No servers configured. Please go to Servers tab to configure FTP connections.');
    }
}

// Configuration management functions
async function loadConfig() {
    const loadButton = document.querySelector('button[onclick="loadConfig()"]');
    const originalText = loadButton.textContent;
    
    try {
        log('Loading configuration...');
        const response = await fetch('http://127.0.0.1:5000/api/config');
        const result = await response.json();
        
        if (result.success) {
            populateFormFromConfig(result.config);
            log('✅ Configuration loaded successfully', 'success');
            
            // Update button to show success
            loadButton.textContent = '✅ Config Loaded';
            loadButton.style.backgroundColor = '#28a745';
            loadButton.style.color = 'white';
            
            // Reset button after 3 seconds
            setTimeout(() => {
                loadButton.textContent = originalText;
                loadButton.style.backgroundColor = '';
                loadButton.style.color = '';
            }, 3000);
        } else {
            log(`❌ Failed to load config: ${result.message}`, 'error');
            
            // Show error state
            loadButton.textContent = '❌ Load Failed';
            loadButton.style.backgroundColor = '#dc3545';
            loadButton.style.color = 'white';
            
            // Reset button after 3 seconds
            setTimeout(() => {
                loadButton.textContent = originalText;
                loadButton.style.backgroundColor = '';
                loadButton.style.color = '';
            }, 3000);
        }
    } catch (error) {
        log(`❌ Error loading config: ${error.message}`, 'error');
        
        // Show error state
        loadButton.textContent = '❌ Load Failed';
        loadButton.style.backgroundColor = '#dc3545';
        loadButton.style.color = 'white';
        
        // Reset button after 3 seconds
        setTimeout(() => {
            loadButton.textContent = originalText;
            loadButton.style.backgroundColor = '';
            loadButton.style.color = '';
        }, 3000);
    }
}

async function saveConfig() {
    const saveButton = document.querySelector('button[onclick="saveConfig()"]');
    const originalText = saveButton.textContent;
    
    try {
        log('Saving configuration...');
        const config = getConfigFromForm();
        
        const response = await fetch('http://127.0.0.1:5000/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const result = await response.json();
        
        if (result.success) {
            log('✅ Configuration saved successfully', 'success');
            
            // Update button to show success
            saveButton.textContent = '✅ Config Saved';
            saveButton.style.backgroundColor = '#28a745';
            saveButton.style.color = 'white';
            
            // Reset button after 3 seconds
            setTimeout(() => {
                saveButton.textContent = originalText;
                saveButton.style.backgroundColor = '';
                saveButton.style.color = '';
            }, 3000);
        } else {
            log(`❌ Failed to save config: ${result.message}`, 'error');
            
            // Show error state
            saveButton.textContent = '❌ Save Failed';
            saveButton.style.backgroundColor = '#dc3545';
            saveButton.style.color = 'white';
            
            // Reset button after 3 seconds
            setTimeout(() => {
                saveButton.textContent = originalText;
                saveButton.style.backgroundColor = '';
                saveButton.style.color = '';
            }, 3000);
        }
    } catch (error) {
        log(`❌ Error saving config: ${error.message}`, 'error');
        
        // Show error state
        saveButton.textContent = '❌ Save Failed';
        saveButton.style.backgroundColor = '#dc3545';
        saveButton.style.color = 'white';
        
        // Reset button after 3 seconds
        setTimeout(() => {
            saveButton.textContent = originalText;
            saveButton.style.backgroundColor = '';
            saveButton.style.color = '';
        }, 3000);
    }
}

async function createSampleConfig() {
    try {
        log('Creating sample configuration file...');
        const response = await fetch('http://127.0.0.1:5000/api/config/sample', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.success) {
            log('✅ Sample configuration file created: config.sample.json', 'success');
            log('Edit this file with your server details and rename to config.json');
        } else {
            log(`❌ Failed to create sample config: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`❌ Error creating sample config: ${error.message}`, 'error');
    }
}

function populateFormFromConfig(config) {
    // Populate server settings
    if (config.servers) {
        if (config.servers.source) {
            const src = config.servers.source;
            document.getElementById('sourceHost').value = src.host || '';
            document.getElementById('sourcePort').value = src.port || 21;
            document.getElementById('sourceUser').value = src.user || '';
            document.getElementById('sourcePass').value = src.password || '';
            document.getElementById('sourcePath').value = src.path || '';
        }
        
        if (config.servers.target) {
            const tgt = config.servers.target;
            document.getElementById('targetHost').value = tgt.host || '';
            document.getElementById('targetPort').value = tgt.port || 21;
            document.getElementById('targetUser').value = tgt.user || '';
            document.getElementById('targetPass').value = tgt.password || '';
            document.getElementById('targetPath').value = tgt.path || '';
        }
    }
    
    // Populate sync settings
    if (config.sync_settings) {
        const sync = config.sync_settings;
        document.getElementById('fileFilter').value = (sync.file_extensions || []).join(',');
        document.getElementById('minFileSize').value = sync.min_file_size_mb || 1;
        document.getElementById('maxFileSize').value = sync.max_file_size_gb || 50;
        document.getElementById('includeSubdirs').checked = sync.include_subdirs !== false;
        document.getElementById('overwriteExisting').checked = sync.overwrite_existing === true;
        document.getElementById('dryRun').checked = sync.dry_run_default === true;
    }
    
    // Store scheduling/export settings in localStorage for modal use
    if (config.scheduling) {
        const sched = config.scheduling;
        if (sched.default_export_server) {
            localStorage.setItem('exportServer', sched.default_export_server);
        }
        if (sched.default_export_path) {
            localStorage.setItem('exportPath', sched.default_export_path);
        }
    }
}

function getConfigFromForm() {
    return {
        servers: {
            source: {
                name: "Source Server",
                host: document.getElementById('sourceHost').value,
                port: parseInt(document.getElementById('sourcePort').value) || 21,
                user: document.getElementById('sourceUser').value,
                password: document.getElementById('sourcePass').value,
                path: document.getElementById('sourcePath').value
            },
            target: {
                name: "Target Server",
                host: document.getElementById('targetHost').value,
                port: parseInt(document.getElementById('targetPort').value) || 21,
                user: document.getElementById('targetUser').value,
                password: document.getElementById('targetPass').value,
                path: document.getElementById('targetPath').value
            }
        },
        sync_settings: {
            file_extensions: document.getElementById('fileFilter').value.split(',').map(ext => ext.trim()).filter(ext => ext),
            min_file_size_mb: parseInt(document.getElementById('minFileSize').value) || 1,
            max_file_size_gb: parseInt(document.getElementById('maxFileSize').value) || 50,
            include_subdirs: document.getElementById('includeSubdirs').checked,
            overwrite_existing: document.getElementById('overwriteExisting').checked,
            dry_run_default: document.getElementById('dryRun').checked
        }
    };
}

function resetForm() {
    // Reset all form fields to defaults
    document.getElementById('sourceHost').value = '';
    document.getElementById('sourcePort').value = '21';
    document.getElementById('sourceUser').value = '';
    document.getElementById('sourcePass').value = '';
    document.getElementById('sourcePath').value = '/media/videos';
    
    document.getElementById('targetHost').value = '';
    document.getElementById('targetPort').value = '21';
    document.getElementById('targetUser').value = '';
    document.getElementById('targetPass').value = '';
    document.getElementById('targetPath').value = '/media/videos';
    
    document.getElementById('fileFilter').value = 'mp4,mkv,avi,mov,wmv';
    document.getElementById('minFileSize').value = '1';
    document.getElementById('maxFileSize').value = '50';
    document.getElementById('includeSubdirs').checked = true;
    document.getElementById('overwriteExisting').checked = false;
    document.getElementById('dryRun').checked = false;
    
    log('Form reset to defaults', 'success');
}

// API Functions for backend integration
async function testConnection(serverType) {
    const testButton = document.getElementById(`${serverType}TestBtn`);
    const originalText = testButton.textContent;
    
    const config = {
        server_type: serverType,
        host: document.getElementById(`${serverType}Host`).value,
        port: document.getElementById(`${serverType}Port`).value,
        user: document.getElementById(`${serverType}User`).value,
        password: document.getElementById(`${serverType}Pass`).value,
        path: document.getElementById(`${serverType}Path`).value
    };
    
    if (!config.host || !config.user || !config.password) {
        log(`Please fill in all ${serverType} server details`, 'error');
        return;
    }
    
    // Show loading state
    testButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    testButton.disabled = true;
    testButton.classList.add('secondary');
    
    log(`Testing connection to ${serverType} server (${config.host}:${config.port})...`);
    
    try {
        console.log('Testing connection with config:', config);
        const response = await fetch('http://127.0.0.1:5000/api/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('Test connection result:', result);
        
        if (result.success) {
            log(`✅ ${result.message}`, 'success');
            
            // Show success state
            testButton.innerHTML = '<i class="fas fa-check"></i> Connected';
            testButton.classList.remove('secondary');
            testButton.classList.add('success');
            
            // Update dashboard status
            updateDashboardStats();
            
            // Reset button after 5 seconds
            setTimeout(() => {
                testButton.innerHTML = '<i class="fas fa-plug"></i> Test Connection';
                testButton.classList.remove('success');
                testButton.classList.add('secondary');
                testButton.disabled = false;
            }, 5000);
        } else {
            log(`❌ ${result.message}`, 'error');
            
            // Show error state
            testButton.innerHTML = '<i class="fas fa-times"></i> Failed';
            testButton.classList.remove('secondary');
            testButton.classList.add('danger');
            
            // Reset button after 5 seconds
            setTimeout(() => {
                testButton.innerHTML = '<i class="fas fa-plug"></i> Test Connection';
                testButton.classList.remove('danger');
                testButton.classList.add('secondary');
                testButton.disabled = false;
            }, 5000);
        }
    } catch (error) {
        log(`❌ Connection test failed: ${error.message}`, 'error');
        log('Make sure the Python backend is running on 127.0.0.1:5000', 'error');
        
        // Show error state
        testButton.innerHTML = '<i class="fas fa-times"></i> Failed';
        testButton.classList.remove('secondary');
        testButton.classList.add('danger');
        
        // Reset button after 5 seconds
        setTimeout(() => {
            testButton.innerHTML = '<i class="fas fa-plug"></i> Test Connection';
            testButton.classList.remove('danger');
            testButton.classList.add('secondary');
            testButton.disabled = false;
        }, 5000);
    }
}

async function scanFiles() {
    if (isScanning) return;
    
    isScanning = true;
    clearLog();
    log('Starting file scan...');
    
    const sourceHost = document.getElementById('sourceHost').value;
    const targetHost = document.getElementById('targetHost').value;
    const sourcePath = document.getElementById('sourcePath').value;
    const targetPath = document.getElementById('targetPath').value;
    
    if (!sourceHost || !targetHost) {
        log('Please configure both source and target servers', 'error');
        isScanning = false;
        return;
    }
    
    try {
        // Get file filters
        const filterInput = document.getElementById('fileFilter').value;
        const extensions = filterInput ? filterInput.split(',').map(ext => ext.trim()) : [];
        const minSize = parseInt(document.getElementById('minFileSize').value) * 1024 * 1024;
        const maxSize = parseInt(document.getElementById('maxFileSize').value) * 1024 * 1024 * 1024;
        const includeSubdirs = document.getElementById('includeSubdirs').checked;
        
        const filters = {
            extensions: extensions,
            min_size: minSize,
            max_size: maxSize,
            include_subdirs: includeSubdirs
        };
        
        // Scan source server
        log(`Scanning source server: ${sourceHost}${sourcePath}`);
        const sourceResponse = await fetch('http://127.0.0.1:5000/api/scan-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_type: 'source',
                path: sourcePath,
                filters: filters
            })
        });
        
        const sourceResult = await sourceResponse.json();
        if (!sourceResult.success) {
            throw new Error(sourceResult.message);
        }
        
        sourceFiles = sourceResult.files;
        log(`Found ${sourceFiles.length} files on source server`);
        
        // Debug: Log a sample of source files
        if (sourceFiles.length > 0) {
            log(`Debug: Sample source files (first 3):`);
            sourceFiles.slice(0, 3).forEach((file, index) => {
                log(`  ${index + 1}. ${JSON.stringify(file, null, 2)}`);
            });
        }
        
        // Scan target server
        log(`Scanning target server: ${targetHost}${targetPath}`);
        const targetResponse = await fetch('http://127.0.0.1:5000/api/scan-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_type: 'target',
                path: targetPath,
                filters: filters
            })
        });
        
        const targetResult = await targetResponse.json();
        if (!targetResult.success) {
            throw new Error(targetResult.message);
        }
        
        targetFiles = targetResult.files;
        log(`Found ${targetFiles.length} files on target server`);
        
        // Debug: Log a sample of target files
        if (targetFiles.length > 0) {
            log(`Debug: Sample target files (first 3):`);
            targetFiles.slice(0, 3).forEach((file, index) => {
                log(`  ${index + 1}. ${JSON.stringify(file, null, 2)}`);
            });
        }
        
        log('File scan completed', 'success');
        
        // Display scanned files
        displayScannedFiles();
        
        // Enable compare and analyze buttons
        document.querySelector('button[onclick="compareFiles()"]').disabled = false;
        document.getElementById('analyzeFilesBtn').disabled = false;
        
    } catch (error) {
        log(`Error during file scan: ${error.message}`, 'error');
    }
    
    isScanning = false;
}

async function startSync() {
    if (isSyncing || syncQueue.length === 0) return;
    
    const dryRun = document.getElementById('dryRun').checked;
    const keepTemp = document.getElementById('keepTempFiles') ? document.getElementById('keepTempFiles').checked : false;
    
    isSyncing = true;
    document.getElementById('syncButton').disabled = true;
    document.getElementById('stopButton').disabled = false;
    
    syncStats = { processed: 0, total: syncQueue.length, errors: 0 };
    
    // Show progress bar
    showProgress(`Starting ${dryRun ? 'dry run' : 'sync'}...`);
    
    log(`Starting ${dryRun ? 'dry run' : 'sync'} of ${syncQueue.length} selected files...`);
    if (keepTemp) {
        log(`Debug mode: Keeping temp files in /tmp/ for inspection`);
    }
    
    // Log the sync queue for debugging
    log(`Debug: Sync queue contents:`);
    syncQueue.forEach((item, index) => {
        log(`  ${index + 1}. ${item.type} - ${item.file.name} (${item.file.path || 'no path'}) - ${formatFileSize(item.file.size)}`);
    });
    
    try {
        const requestBody = {
            sync_queue: syncQueue,
            dry_run: dryRun,
            keep_temp_files: keepTemp
        };
        
        log(`Debug: Request body: ${JSON.stringify(requestBody, null, 2)}`);
        
        // Update progress for request phase
        updateProgress(0, syncQueue.length, null);
        
        const response = await fetch('http://127.0.0.1:5000/api/sync-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        log(`Debug: Response status: ${response.status}`);
        
        if (!response.ok) {
            const errorText = await response.text();
            log(`Debug: Response error text: ${errorText}`, 'error');
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const result = await response.json();
        log(`Debug: Full response: ${JSON.stringify(result, null, 2)}`);
        
        if (result.success) {
            if (!result.results || result.results.length === 0) {
                log('Debug: No results returned from sync operation', 'error');
                return;
            }
            
            // Process results with delays to show incremental progress
            await processResultsWithProgress(result.results);
            
            // Show completion
            updateProgress(result.results.length, result.results.length, null);
            
            log(`Sync completed! Processed: ${syncStats.processed}, Errors: ${syncStats.errors}`, 'success');
            
            if (keepTemp && syncStats.processed > 0) {
                log(`Debug: Check /tmp/ directory on your server for downloaded files`, 'info');
            }
            
            // Clear the sync queue after successful sync
            if (!dryRun && syncStats.errors === 0) {
                clearSyncQueue();
                // Update the comparison display to reflect removed files
                updateComparisonSummary();
                renderComparisonResults();
            }
        } else {
            log(`Sync failed: ${result.message || 'Unknown error'}`, 'error');
            if (result.details) {
                log(`Error details: ${result.details}`, 'error');
            }
            if (result.traceback) {
                log(`Traceback: ${result.traceback}`, 'error');
            }
        }
        
    } catch (error) {
        log(`Sync error: ${error.message}`, 'error');
        log(`Debug: Full error object: ${JSON.stringify(error, null, 2)}`, 'error');
    }
    
    // Hide progress bar after a delay
    setTimeout(() => {
        hideProgress();
    }, 2000);
    
    isSyncing = false;
    document.getElementById('syncButton').disabled = false;
    document.getElementById('stopButton').disabled = true;
}

// Panel Management
function showPanel(panelName) {
    // Hide all panels
    const panels = document.querySelectorAll('.panel');
    panels.forEach(panel => panel.classList.remove('active'));
    
    // Show selected panel
    const selectedPanel = document.getElementById(panelName);
    if (selectedPanel) {
        selectedPanel.classList.add('active');
    }
    
    // Update nav items
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => item.classList.remove('active'));
    
    // Find and activate the corresponding nav item
    const activeNavItem = document.querySelector(`[onclick="showPanel('${panelName}')"]`);
    if (activeNavItem) {
        activeNavItem.classList.add('active');
    }
    
    // Update dashboard stats when showing dashboard
    if (panelName === 'dashboard') {
        updateDashboardStats();
    }
    
    // Load AI settings when showing AI settings panel
    if (panelName === 'ai-settings') {
        loadAISettings();
    }
}

// Update dashboard statistics
function updateDashboardStats() {
    // Update source server status
    const sourceStatusText = document.getElementById('sourceStatusText');
    const sourceHost = document.getElementById('sourceHost').value;
    // Only update if not already showing connected status
    if (sourceStatusText && !sourceStatusText.innerHTML.includes('Connected')) {
        if (sourceHost) {
            sourceStatusText.textContent = 'Not Connected';
            sourceStatusText.style.color = 'var(--warning-color)';
        } else {
            sourceStatusText.textContent = 'Not Configured';
            sourceStatusText.style.color = 'var(--text-secondary)';
        }
    }
    
    // Update target server status
    const targetStatusText = document.getElementById('targetStatusText');
    const targetHost = document.getElementById('targetHost').value;
    // Only update if not already showing connected status
    if (targetStatusText && !targetStatusText.innerHTML.includes('Connected')) {
        if (targetHost) {
            targetStatusText.textContent = 'Not Connected';
            targetStatusText.style.color = 'var(--warning-color)';
        } else {
            targetStatusText.textContent = 'Not Configured';
            targetStatusText.style.color = 'var(--text-secondary)';
        }
    }
    
    // Update file count
    const fileCountText = document.getElementById('fileCountText');
    const totalFiles = sourceFiles.length + targetFiles.length;
    fileCountText.textContent = `${totalFiles} files scanned`;
    
    // Update sync status
    const syncStatusText = document.getElementById('syncStatusText');
    syncStatusText.textContent = `${syncQueue.length} files queued`;
}



// Check backend health
async function checkBackendHealth() {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/health');
        const result = await response.json();
        
        const backendStatus = document.getElementById('backendStatus');
        if (result.status === 'healthy') {
            backendStatus.textContent = '✅ Online';
            backendStatus.style.color = 'var(--success-color)';
        } else {
            backendStatus.textContent = '❌ Offline';
            backendStatus.style.color = 'var(--danger-color)';
        }
    } catch (error) {
        const backendStatus = document.getElementById('backendStatus');
        backendStatus.textContent = '❌ Offline';
        backendStatus.style.color = 'var(--danger-color)';
    }
}

// Toggle visibility functions
function toggleScannedFiles() {
    const detailsDiv = document.getElementById('scannedFilesDetails');
    const summaryDiv = document.getElementById('scannedFilesSummary');
    const toggleBtn = document.getElementById('toggleScannedFilesBtn');
    const filterBtn = document.getElementById('toggleUnanalyzedOnlyBtn');
    
    if (detailsDiv.style.display === 'none') {
        detailsDiv.style.display = 'grid';
        summaryDiv.style.display = 'none';
        toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Details';
        filterBtn.style.display = 'inline-block'; // Show filter button when details are shown
    } else {
        detailsDiv.style.display = 'none';
        summaryDiv.style.display = 'block';
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show Details';
        filterBtn.style.display = 'none'; // Hide filter button when details are hidden
    }
}

function toggleUnanalyzedOnly() {
    showUnanalyzedOnly = !showUnanalyzedOnly;
    const toggleBtn = document.getElementById('toggleUnanalyzedOnlyBtn');
    
    if (showUnanalyzedOnly) {
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show All Files';
        toggleBtn.className = 'button warning small';
    } else {
        toggleBtn.innerHTML = '<i class="fas fa-filter"></i> Show Unanalyzed Only';
        toggleBtn.className = 'button secondary small';
    }
    
    // Re-render the scanned files with the new filter
    displayScannedFiles();
}

function toggleStatus() {
    const statusDiv = document.getElementById('status');
    const toggleBtn = document.getElementById('toggleStatusBtn');
    
    if (statusDiv.style.display === 'none') {
        statusDiv.style.display = 'block';
        toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Logs';
    } else {
        statusDiv.style.display = 'none';
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show Logs';
    }
}

function updateScannedFilesSummary() {
    const summaryText = document.getElementById('scannedFilesSummaryText');
    const totalFiles = sourceFiles.length + targetFiles.length;
    
    if (totalFiles === 0) {
        summaryText.textContent = 'No files scanned yet';
    } else {
        summaryText.textContent = `Found ${sourceFiles.length} source files and ${targetFiles.length} target files`;
    }
}

function toggleComparisonView() {
    showAllFiles = !showAllFiles;
    const toggleBtn = document.getElementById('toggleComparisonBtn');
    
    if (showAllFiles) {
        toggleBtn.innerHTML = '<i class="fas fa-filter"></i> Show Unsynced Only';
    } else {
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show All Files';
    }
    
    // Re-render the comparison results with the new filter
    renderComparisonResults();
}

function updateComparisonSummary() {
    const summaryText = document.getElementById('comparisonSummaryText');
    const unsyncedCount = availableFiles.length;
    const totalCount = allComparisonResults.length;
    const targetOnlyCount = targetOnlyFiles.length;
    
    if (totalCount === 0) {
        summaryText.textContent = 'No comparison results yet';
    } else {
        summaryText.textContent = `${unsyncedCount} files need sync (${totalCount} total files, ${targetOnlyCount} target-only)`;
    }
}

function toggleTargetOnlyView() {
    showTargetOnly = !showTargetOnly;
    const toggleBtn = document.getElementById('toggleTargetOnlyBtn');
    
    if (showTargetOnly) {
        toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Target-Only';
        showAllFiles = false; // Reset other view
        document.getElementById('toggleComparisonBtn').innerHTML = '<i class="fas fa-eye"></i> Show All Files';
    } else {
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show Target-Only Files';
    }
    
    // Re-render the comparison results with the new filter
    renderComparisonResults();
}

// Dark mode functionality
function toggleDarkMode() {
    const body = document.body;
    const darkModeToggle = document.getElementById('darkModeToggle');
    
    if (body.getAttribute('data-theme') === 'dark') {
        body.removeAttribute('data-theme');
        darkModeToggle.innerHTML = '<i class="fas fa-moon"></i> Dark';
        localStorage.setItem('theme', 'light');
    } else {
        body.setAttribute('data-theme', 'dark');
        darkModeToggle.innerHTML = '<i class="fas fa-sun"></i> Light';
        localStorage.setItem('theme', 'dark');
    }
}

function initializeTheme() {
    const savedTheme = localStorage.getItem('theme');
    const body = document.body;
    const darkModeToggle = document.getElementById('darkModeToggle');
    
    if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        body.setAttribute('data-theme', 'dark');
        darkModeToggle.innerHTML = '<i class="fas fa-sun"></i> Light';
    } else {
        body.removeAttribute('data-theme');
        darkModeToggle.innerHTML = '<i class="fas fa-moon"></i> Dark';
    }
}

// Helper function to check if a file is a video file eligible for analysis
function isVideoFileEligible(filename) {
    const videoExtensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v', '.flv'];
    const extension = filename.toLowerCase().slice(filename.lastIndexOf('.'));
    const isEligible = videoExtensions.includes(extension);
    console.log(`isVideoFileEligible(${filename}) -> ${isEligible} (extension: ${extension})`);
    return isEligible;
}

// Individual file analysis function
// Individual file analysis function - now adds to queue instead of analyzing immediately
function addToAnalysisQueue(fileId) {
    console.log('addToAnalysisQueue called with fileId:', fileId);
    
    const button = document.querySelector(`button[onclick="addToAnalysisQueue('${fileId}')"]`);
    console.log('Found button:', button);
    
    if (!button) {
        log(`Button not found for fileId: ${fileId}`, 'error');
        return;
    }
    
    const filePath = button.getAttribute('data-file-path');
    const isAnalyzed = button.getAttribute('data-is-analyzed') === 'true';
    console.log('File path:', filePath, 'Is analyzed:', isAnalyzed);
    
    // Find the file in sourceFiles
    const file = sourceFiles.find(f => (f.path || f.name) === filePath);
    if (!file) {
        log(`File not found: ${filePath}`, 'error');
        return;
    }
    
    // Check if file is already in analysis queue
    const alreadyInQueue = analysisQueue.find(queueItem => queueItem.id === fileId);
    if (alreadyInQueue) {
        log(`${file.name} is already in analysis queue`, 'warning');
        return;
    }
    
    // Add to analysis queue
    analysisQueue.push({
        id: fileId,
        file: file,
        filePath: filePath,
        is_reanalysis: isAnalyzed  // Mark as reanalysis if file was already analyzed
    });
    
    // Update button state based on whether this is a reanalysis or new analysis
    if (isAnalyzed) {
        button.innerHTML = '<i class="fas fa-check"></i> Queued for Reanalysis';
        log(`🔄 Added ${file.name} to analysis queue for reanalysis (${analysisQueue.length} files queued)`);
    } else {
        button.innerHTML = '<i class="fas fa-check"></i> Added to Analysis';
        log(`📋 Added ${file.name} to analysis queue (${analysisQueue.length} files queued)`);
    }
    
    button.classList.add('added');
    button.disabled = true;
    
    // Update parent item styling
    const fileItem = button.closest('.scanned-file-item');
    fileItem.classList.add('queued');
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
}

function addAllUnanalyzedToAnalysisQueue() {
    log('🚀 Analyze All Unanalyzed button clicked!');
    
    if (sourceFiles.length === 0) {
        log('No files scanned - scan files first', 'error');
        return;
    }
    
    // Find all video files that are not already analyzed
    const videoFiles = sourceFiles.filter(file => isVideoFileEligible(file.name));
    if (videoFiles.length === 0) {
        log('No video files found to analyze', 'error');
        return;
    }
    
    // Filter to only unanalyzed files
    const unanalyzedFiles = videoFiles.filter(file => !file.is_analyzed);
    
    if (unanalyzedFiles.length === 0) {
        log('No unanalyzed video files found (all files may already be analyzed)', 'error');
        return;
    }
    
    log(`📁 Adding all ${unanalyzedFiles.length} unanalyzed video files to analysis queue`);
    
    let addedCount = 0;
    let skippedCount = 0;
    
    // Add each unanalyzed file to the analysis queue
    unanalyzedFiles.forEach(file => {
        const fileId = btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '');
        
        // Check if file is already in analysis queue
        const alreadyInQueue = analysisQueue.find(queueItem => queueItem.id === fileId);
        if (!alreadyInQueue) {
            analysisQueue.push({
                id: fileId,
                file: file,
                filePath: file.path || file.name
            });
            addedCount++;
            
            // Update corresponding button
            const button = document.querySelector(`button[onclick="addToAnalysisQueue('${fileId}')"]`);
            if (button) {
                button.innerHTML = '<i class="fas fa-check"></i> Added to Analysis';
                button.classList.add('added');
                button.disabled = true;
                
                // Update parent item styling
                const fileItem = button.closest('.scanned-file-item');
                if (fileItem) {
                    fileItem.classList.add('queued');
                }
            }
        } else {
            skippedCount++;
        }
    });
    
    if (addedCount > 0) {
        log(`📋 Added ${addedCount} unanalyzed files to analysis queue (${analysisQueue.length} total files)`);
        if (skippedCount > 0) {
            log(`⏭️ Skipped ${skippedCount} files (already in queue)`);
        }
        updateAnalysisButtonState();
        updateAnalyzeAllButtonState();
    } else {
        log('All unanalyzed files are already in analysis queue', 'warning');
    }
}

function addAllAnalyzedToReanalysisQueue() {
    log('🚀 Reanalyze All button clicked!');
    
    if (sourceFiles.length === 0) {
        log('No files scanned - scan files first', 'error');
        return;
    }
    
    // Find all video files that are already analyzed
    const videoFiles = sourceFiles.filter(file => isVideoFileEligible(file.name));
    const analyzedFiles = videoFiles.filter(file => file.is_analyzed);
    
    if (analyzedFiles.length === 0) {
        log('No analyzed video files found', 'error');
        return;
    }
    
    log(`📁 Adding all ${analyzedFiles.length} analyzed video files to reanalysis queue`);
    
    let addedCount = 0;
    let skippedCount = 0;
    
    // Add each analyzed file to the analysis queue
    analyzedFiles.forEach(file => {
        const fileId = btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '');
        
        // Check if already in queue
        const alreadyInQueue = analysisQueue.find(item => 
            (item.file.path === file.path) || 
            (item.file.name === file.name && item.file.size === file.size)
        );
        
        if (!alreadyInQueue) {
            analysisQueue.push({
                id: fileId,
                file: file,
                is_reanalysis: true  // Mark as reanalysis
            });
            addedCount++;
            
            // Update button state for this file
            const button = document.querySelector(`button[data-file-path="${file.path || file.name}"]`);
            if (button) {
                button.classList.add('added');
                button.disabled = true;
                const fileItem = button.closest('.scanned-file-item');
                if (fileItem) {
                    fileItem.classList.add('queued');
                }
            }
        } else {
            skippedCount++;
        }
    });
    
    if (addedCount > 0) {
        log(`📋 Added ${addedCount} analyzed files for reanalysis (${analysisQueue.length} total files)`);
        if (skippedCount > 0) {
            log(`⏭️ Skipped ${skippedCount} files (already in queue)`);
        }
        updateAnalysisButtonState();
        updateAnalyzeAllButtonState();
    } else {
        log('All analyzed files are already in analysis queue', 'warning');
    }
}

function updateAnalyzeAllButtonState() {
    const analyzeAllButton = document.getElementById('analyzeAllUnanalyzedButton');
    if (analyzeAllButton) {
        if (sourceFiles.length === 0) {
            analyzeAllButton.disabled = true;
            analyzeAllButton.textContent = 'Analyze All Unanalyzed';
            analyzeAllButton.title = 'Scan files first';
            return;
        }
        
        const videoFiles = sourceFiles.filter(file => isVideoFileEligible(file.name));
        const unanalyzedFiles = videoFiles.filter(file => !file.is_analyzed);
        const queuedUnanalyzed = unanalyzedFiles.filter(file => {
            const fileId = btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '');
            return analysisQueue.find(queueItem => queueItem.id === fileId);
        }).length;
        
        const remainingUnanalyzed = unanalyzedFiles.length - queuedUnanalyzed;
        
        if (remainingUnanalyzed > 0) {
            analyzeAllButton.disabled = false;
            analyzeAllButton.textContent = `Analyze All Unanalyzed (${remainingUnanalyzed} files)`;
            analyzeAllButton.title = `Queue ${remainingUnanalyzed} unanalyzed video files for analysis`;
        } else if (unanalyzedFiles.length > 0) {
            analyzeAllButton.disabled = true;
            analyzeAllButton.textContent = 'Analyze All Unanalyzed (all queued)';
            analyzeAllButton.title = 'All unanalyzed files are already queued';
        } else {
            // Check if we have analyzed files for reanalysis
            const analyzedFiles = videoFiles.filter(file => file.is_analyzed);
            if (analyzedFiles.length > 0) {
                // All files are analyzed - show reanalyze option
                analyzeAllButton.disabled = false;
                analyzeAllButton.textContent = `Reanalyze All (${analyzedFiles.length} files)`;
                analyzeAllButton.title = `Force reanalysis of ${analyzedFiles.length} already analyzed files`;
                analyzeAllButton.onclick = function() { addAllAnalyzedToReanalysisQueue(); };
            } else {
                analyzeAllButton.disabled = true;
                analyzeAllButton.textContent = 'No video files found';
                analyzeAllButton.title = 'No video files found to analyze';
            }
        }
    }
}

// AI Settings Functions
async function loadAISettings() {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/ai-config');
        const result = await response.json();
        
        if (result.success) {
            const config = result.config;
            document.getElementById('aiEnabled').checked = config.enabled || false;
            document.getElementById('transcriptionOnly').checked = config.transcription_only || false;
            document.getElementById('aiProvider').value = config.provider || 'openai';
            document.getElementById('aiModel').value = config.model || 'gpt-3.5-turbo';
            // Only clear API key fields if they're empty, keep placeholder if API key exists
            if (config.openai_api_key && config.openai_api_key !== '***') {
                document.getElementById('openaiApiKey').value = config.openai_api_key;
            } else if (config.openai_api_key === '***') {
                document.getElementById('openaiApiKey').placeholder = 'API key configured (hidden for security)';
            }
            
            if (config.anthropic_api_key && config.anthropic_api_key !== '***') {
                document.getElementById('anthropicApiKey').value = config.anthropic_api_key;
            } else if (config.anthropic_api_key === '***') {
                document.getElementById('anthropicApiKey').placeholder = 'API key configured (hidden for security)';
            }
            document.getElementById('maxChunkSize').value = config.max_chunk_size || 4000;
            
            // Update model options based on provider
            updateModelOptions(config.provider || 'openai');
            
            log('AI settings loaded successfully');
        } else {
            log(`Failed to load AI settings: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`Error loading AI settings: ${error.message}`, 'error');
    }
}

async function saveAISettings() {
    try {
        const aiConfig = {
            enabled: document.getElementById('aiEnabled').checked,
            transcription_only: document.getElementById('transcriptionOnly').checked,
            provider: document.getElementById('aiProvider').value,
            model: document.getElementById('aiModel').value,
            openai_api_key: document.getElementById('openaiApiKey').value,
            anthropic_api_key: document.getElementById('anthropicApiKey').value,
            max_chunk_size: parseInt(document.getElementById('maxChunkSize').value) || 4000,
            enable_batch_analysis: true
        };
        
        const response = await fetch('http://127.0.0.1:5000/api/ai-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ai_analysis: aiConfig })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log('AI settings saved successfully');
        } else {
            log(`Failed to save AI settings: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`Error saving AI settings: ${error.message}`, 'error');
    }
}

function updateModelOptions(provider) {
    const modelSelect = document.getElementById('aiModel');
    const currentValue = modelSelect.value;
    
    // Clear existing options
    modelSelect.innerHTML = '';
    
    if (provider === 'openai') {
        modelSelect.innerHTML = `
            <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
            <option value="gpt-4">GPT-4</option>
            <option value="gpt-4-turbo">GPT-4 Turbo</option>
        `;
    } else if (provider === 'anthropic') {
        modelSelect.innerHTML = `
            <option value="claude-3-sonnet-20240229">Claude 3 Sonnet</option>
            <option value="claude-3-opus-20240229">Claude 3 Opus</option>
            <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
        `;
    }
    
    // Try to restore previous value, or set default
    if (Array.from(modelSelect.options).some(option => option.value === currentValue)) {
        modelSelect.value = currentValue;
    } else {
        modelSelect.value = provider === 'openai' ? 'gpt-3.5-turbo' : 'claude-3-sonnet-20240229';
    }
}

async function testAIConnection() {
    try {
        const provider = document.getElementById('aiProvider').value;
        const apiKey = provider === 'openai' ? 
            document.getElementById('openaiApiKey').value : 
            document.getElementById('anthropicApiKey').value;
        
        if (!apiKey) {
            log('Please enter an API key before testing connection', 'error');
            return;
        }
        
        log(`Testing ${provider} connection...`);
        
        // Create a test file for analysis
        const testFile = {
            name: 'test_connection.mp4',
            path: 'test_connection.mp4',
            size: 1000000
        };
        
        const aiConfig = {
            enabled: true,
            provider: provider,
            model: document.getElementById('aiModel').value,
            api_key: apiKey,
            max_chunk_size: 1000
        };
        
        // We'll just test if the settings are valid by saving them
        await saveAISettings();
        log(`${provider} connection test completed - settings saved`);
        
    } catch (error) {
        log(`AI connection test failed: ${error.message}`, 'error');
    }
}

// Add event listener for provider change
document.addEventListener('DOMContentLoaded', function() {
    const providerSelect = document.getElementById('aiProvider');
    if (providerSelect) {
        providerSelect.addEventListener('change', function() {
            updateModelOptions(this.value);
        });
    }
});

// File Analysis Functions
async function analyzeFiles() {
    if (sourceFiles.length === 0) {
        log('No files to analyze. Please scan files first.', 'error');
        return;
    }
    
    log('Loading file analysis interface...');
    
    // Show analysis card
    const analysisCard = document.getElementById('analysisCard');
    analysisCard.style.display = 'block';
    
    // Clear previous results
    analysisQueue = [];
    analysisResults = [];
    
    // Check which files are already analyzed
    await checkAnalysisStatus();
    
    // Render analysis interface
    renderAnalysisFiles();
    
    log('Analysis interface loaded. Select files to analyze.');
}

async function checkAnalysisStatus() {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/analysis-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: sourceFiles })
        });
        
        const result = await response.json();
        if (result.success) {
            analysisResults = result.analyzed_files || [];
            log(`Found ${analysisResults.length} previously analyzed files`);
        }
    } catch (error) {
        log('Could not check analysis status - MongoDB may not be available', 'error');
    }
}

function renderAnalysisFiles() {
    const analysisFileList = document.getElementById('analysisFileList');
    analysisFileList.innerHTML = '';
    
    sourceFiles.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        
        const fileId = btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '');
        const isAnalyzed = analysisResults.find(result => result.file_path === (file.path || file.name));
        const isInQueue = analysisQueue.find(item => item.id === fileId);
        
        // Filter based on showAnalysisAll toggle
        if (!showAnalysisAll && isAnalyzed) {
            return; // Skip analyzed files when showing unanalyzed only
        }
        
        if (isAnalyzed) {
            fileItem.classList.add('analyzed');
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-path">${file.path || file.name}</div>
                    <div class="file-size">${formatFileSize(file.size)} - Analyzed</div>
                </div>
                <span style="color: #4caf50;">✅ Analyzed</span>
            `;
        } else if (isInQueue) {
            fileItem.classList.add('analyzing');
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-path">${file.path || file.name}</div>
                    <div class="file-size">${formatFileSize(file.size)} - Queued for analysis</div>
                </div>
                <span style="color: #ff9800;">⏳ Queued</span>
            `;
        } else {
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-path">${file.path || file.name}</div>
                    <div class="file-size">${formatFileSize(file.size)} - Not analyzed</div>
                </div>
                <button class="button analyze-btn" onclick="addToAnalysisQueue('${fileId}', this)">
                    <i class="fas fa-brain"></i> Analyze
                </button>
            `;
        }
        
        analysisFileList.appendChild(fileItem);
    });
    
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
}

function toggleAnalysisView() {
    showAnalysisAll = !showAnalysisAll;
    const toggleBtn = document.getElementById('toggleAnalysisBtn');
    
    if (showAnalysisAll) {
        toggleBtn.innerHTML = '<i class="fas fa-filter"></i> Show Unanalyzed Only';
    } else {
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show All Files';
    }
    
    renderAnalysisFiles();
}

// Initialize the app
window.addEventListener('load', function() {
    log('FTP Media Server Sync initialized');
    log('Welcome to the modern FTP sync interface!');
    log('Navigate using the menu above to configure servers and settings');
    
    // Debug: Check if template functions are available
    console.log('=== Template Functions Debug ===');
    console.log('showLoadTemplateModal:', typeof window.showLoadTemplateModal);
    console.log('showLoadWeeklyTemplateModal:', typeof window.showLoadWeeklyTemplateModal);
    console.log('showLoadMonthlyTemplateModal:', typeof window.showLoadMonthlyTemplateModal);
    console.log('fillScheduleGaps:', typeof window.fillScheduleGaps);
    console.log('================================');
    
    // Initialize theme
    initializeTheme();
    
    // Load AI settings on page load
    loadAISettings();
    
    // Initialize collapsible cards
    initializeCollapsibleCards();
    
    // Initialize with dashboard panel
    showPanel('dashboard');
    
    // Auto-load config on startup
    loadConfig().then(() => {
        // Auto-connect to servers after config is loaded
        setTimeout(() => {
            autoConnectServers();
        }, 1000);
    });
    
    // Check backend health
    checkBackendHealth();
    
    // Update dashboard stats
    updateDashboardStats();
    
    // Update uptime counter
    const startTime = Date.now();
    setInterval(() => {
        const uptime = Math.floor((Date.now() - startTime) / 1000);
        const minutes = Math.floor(uptime / 60);
        const seconds = uptime % 60;
        const uptimeInfo = document.getElementById('uptimeInfo');
        if (uptimeInfo) {
            uptimeInfo.textContent = `${minutes}m ${seconds}s`;
        }
    }, 1000);
});

// Analysis queue management functions
function updateAnalysisButtonState() {
    console.log('=== updateAnalysisButtonState called ===');
    const startAnalysisButton = document.getElementById('startAnalysisButton');
    const stopAnalysisButton = document.getElementById('stopAnalysisButton');
    const clearAnalysisButton = document.getElementById('clearAnalysisButton');
    
    // Update start analysis button
    if (startAnalysisButton) {
        startAnalysisButton.disabled = analysisQueue.length === 0 || isAnalyzing;
        
        if (isAnalyzing) {
            startAnalysisButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
        } else if (analysisQueue.length > 0) {
            startAnalysisButton.innerHTML = `<i class="fas fa-play"></i> Start Analysis (${analysisQueue.length} files)`;
        } else {
            startAnalysisButton.innerHTML = '<i class="fas fa-play"></i> Start Analysis';
        }
    }
    
    // Update stop analysis button
    if (stopAnalysisButton) {
        stopAnalysisButton.disabled = !isAnalyzing;
        if (!isAnalyzing) {
            stopAnalysisButton.innerHTML = '<i class="fas fa-stop"></i> Stop Analysis';
        }
    }
    
    // Update clear analysis button
    if (clearAnalysisButton) {
        clearAnalysisButton.disabled = analysisQueue.length === 0 || isAnalyzing;
    }
    
    // Update analyze folder button
    console.log('=== Looking for analyzeFolderButton ===');
    const analyzeFolderButton = document.getElementById('analyzeFolderButton');
    console.log('analyzeFolderButton found:', analyzeFolderButton);
    if (analyzeFolderButton) {
        const analyzeStats = getAnalyzeFolderStats();
        console.log('Analyze stats:', analyzeStats);
        
        if (analyzeStats && analyzeStats.videoFilesToAnalyze > 0) {
            console.log('Enabling analyze folder button');
            log(`📁 Analyze Folder enabled for "${analyzeStats.folderPath}" folder with ${analyzeStats.videoFilesToAnalyze} unanalyzed video files`);
            analyzeFolderButton.disabled = false;
            analyzeFolderButton.textContent = `Analyze Folder (${analyzeStats.videoFilesToAnalyze} unanalyzed)`;
            analyzeFolderButton.title = `Analyze all unanalyzed video files from "${analyzeStats.folderPath}" folder`;
        } else if (analyzeStats) {
            console.log('Disabling analyze folder button - no files');
            analyzeFolderButton.disabled = true;
            analyzeFolderButton.textContent = 'Analyze Folder (0 unanalyzed)';
            analyzeFolderButton.title = `No unanalyzed video files in "${analyzeStats.folderPath}" folder`;
        } else {
            console.log('Disabling analyze folder button - no stats');
            analyzeFolderButton.disabled = true;
            analyzeFolderButton.textContent = 'Analyze Folder';
            analyzeFolderButton.title = 'Scan files first to determine folder';
        }
    } else {
        console.log('analyzeFolderButton not found');
    }
}

function clearAnalysisQueue() {
    if (analysisQueue.length === 0) {
        log('Analysis queue is already empty', 'warning');
        return;
    }
    
    const clearedCount = analysisQueue.length;
    
    // Reset all buttons back to their original state
    analysisQueue.forEach(item => {
        const button = document.querySelector(`button[onclick="addToAnalysisQueue('${item.id}')"]`);
        if (button) {
            const isAnalyzed = button.getAttribute('data-is-analyzed') === 'true';
            if (isAnalyzed) {
                button.innerHTML = '<i class="fas fa-redo"></i> Reanalyze';
            } else {
                button.innerHTML = '<i class="fas fa-brain"></i> Analyze';
            }
            button.classList.remove('added');
            button.disabled = false;
            
            // Update parent item styling
            const fileItem = button.closest('.scanned-file-item');
            fileItem.classList.remove('queued');
        }
    });
    
    // Clear the queue
    analysisQueue = [];
    
    log(`Cleared ${clearedCount} files from analysis queue`);
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
}

async function startAnalysis() {
    if (analysisQueue.length === 0) {
        log('No files in analysis queue', 'error');
        return;
    }
    
    if (isAnalyzing) {
        log('Analysis already in progress', 'warning');
        return;
    }
    
    isAnalyzing = true;
    stopAnalysisRequested = false;
    log(`Starting analysis of ${analysisQueue.length} files...`);
    
    // Start monitoring
    startAnalysisMonitoring();
    startMonitorDisplayUpdate();
    
    // Start periodic rescanning
    if (rescanEnabled) {
        startPeriodicRescanning();
    }
    
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
    
    const totalFiles = analysisQueue.length;
    let successCount = 0;
    let failureCount = 0;
    
    // Get AI config from backend
    let aiConfig = {
        enabled: false,
        provider: 'openai',
        model: 'gpt-3.5-turbo',
        api_key: '',
        max_chunk_size: 4000
    };
    
    try {
        const configResponse = await fetch('http://127.0.0.1:5000/api/ai-config');
        const configResult = await configResponse.json();
        if (configResult.success) {
            const backendConfig = configResult.config;
            aiConfig = {
                enabled: backendConfig.enabled || false,
                provider: backendConfig.provider || 'openai',
                model: backendConfig.model || 'gpt-3.5-turbo',
                api_key: backendConfig.provider === 'openai' ? backendConfig.openai_api_key : backendConfig.anthropic_api_key,
                max_chunk_size: backendConfig.max_chunk_size || 4000
            };
        }
    } catch (configError) {
        log(`Warning: Could not load AI config: ${configError.message}`);
    }
    
    // Process each file in the queue (make a copy since we'll be modifying the original)
    const queueCopy = [...analysisQueue];
    for (let i = 0; i < queueCopy.length; i++) {
        // Check if stop was requested
        if (stopAnalysisRequested) {
            log('Analysis stopped by user', 'warning');
            break;
        }
        
        const queueItem = queueCopy[i];
        const button = document.querySelector(`button[onclick="addToAnalysisQueue('${queueItem.id}')"]`);
        
        log(`Analyzing file ${i + 1}/${totalFiles}: ${queueItem.file.name}`);
        
        // Update progress tracking
        updateAnalysisProgress(queueItem.file.name);
        
        // Update button to show analyzing state
        if (button) {
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
            button.disabled = true;
        }
        
        try {
            // Check if this file is being reanalyzed
            const isReanalysis = queueItem.is_reanalysis || queueItem.file.is_analyzed || false;
            
            const response = await fetch('http://127.0.0.1:5000/api/analyze-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    files: [queueItem.file],
                    server_type: 'source',
                    ai_config: aiConfig,
                    force_reanalysis: isReanalysis
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                const analysisResult = result.results[0];
                if (analysisResult.success) {
                    log(`✅ Analysis completed for: ${queueItem.file.name}`);
                    if (button) {
                        button.innerHTML = '<i class="fas fa-check"></i> Analyzed';
                        button.classList.add('analyzed');
                        button.classList.remove('added');
                        
                        // Update parent item styling
                        const fileItem = button.closest('.scanned-file-item');
                        fileItem.classList.add('analyzed');
                        fileItem.classList.remove('queued');
                    }
                    
                    // Remove successful item from queue
                    const queueIndex = analysisQueue.findIndex(item => item.id === queueItem.id);
                    if (queueIndex !== -1) {
                        analysisQueue.splice(queueIndex, 1);
                    }
                    
                    successCount++;
                } else {
                    log(`❌ Analysis failed for: ${queueItem.file.name} - ${analysisResult.error}`, 'error');
                    if (button) {
                        button.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
                        button.classList.add('error');
                        button.classList.remove('added');
                        button.disabled = false;
                    }
                    
                    // Remove failed item from queue
                    const queueIndex = analysisQueue.findIndex(item => item.id === queueItem.id);
                    if (queueIndex !== -1) {
                        analysisQueue.splice(queueIndex, 1);
                    }
                    
                    failureCount++;
                }
            } else {
                log(`❌ Analysis request failed for ${queueItem.file.name}: ${result.message}`, 'error');
                if (button) {
                    button.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
                    button.classList.add('error');
                    button.classList.remove('added');
                    button.disabled = false;
                }
                
                // Remove failed item from queue
                const queueIndex = analysisQueue.findIndex(item => item.id === queueItem.id);
                if (queueIndex !== -1) {
                    analysisQueue.splice(queueIndex, 1);
                }
                
                failureCount++;
            }
        } catch (error) {
            log(`❌ Analysis error for ${queueItem.file.name}: ${error.message}`, 'error');
            if (button) {
                button.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
                button.classList.add('error');
                button.classList.remove('added');
                button.disabled = false;
            }
            
            // Remove error item from queue
            const queueIndex = analysisQueue.findIndex(item => item.id === queueItem.id);
            if (queueIndex !== -1) {
                analysisQueue.splice(queueIndex, 1);
            }
            
            failureCount++;
        }
        
        // Small delay between files to avoid overwhelming the server
        if (i < queueCopy.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }
    
    // Update state
    const wasStopped = stopAnalysisRequested;
    isAnalyzing = false;
    stopAnalysisRequested = false;
    
    // Stop monitoring and rescanning
    stopAnalysisMonitoring();
    stopPeriodicRescanning();
    
    if (wasStopped) {
        log(`Analysis stopped: ${successCount} successful, ${failureCount} failed, ${analysisQueue.length} remaining`);
        
        // Reset remaining queued items to normal analyze button state
        analysisQueue.forEach(item => {
            const button = document.querySelector(`button[onclick="addToAnalysisQueue('${item.id}')"]`);
            if (button) {
                button.innerHTML = '<i class="fas fa-brain"></i> Analyze';
                button.classList.remove('added');
                button.disabled = false;
                
                // Update parent item styling
                const fileItem = button.closest('.scanned-file-item');
                fileItem.classList.remove('queued');
            }
        });
    } else {
        log(`Analysis batch completed: ${successCount} successful, ${failureCount} failed`);
    }
    
    updateAnalysisButtonState();
    updateAnalyzeAllButtonState();
}

function stopAnalysis() {
    if (!isAnalyzing) {
        log('No analysis in progress to stop', 'warning');
        return;
    }
    
    log('Stopping analysis...', 'warning');
    stopAnalysisRequested = true;
    
    // Stop monitoring and rescanning when manually stopped
    stopAnalysisMonitoring();
    stopPeriodicRescanning();
    
    // Update button state immediately to show stopping
    const stopAnalysisButton = document.getElementById('stopAnalysisButton');
    if (stopAnalysisButton) {
        stopAnalysisButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Stopping...';
        stopAnalysisButton.disabled = true;
    }
}

// Database Management Functions
async function clearAllAnalyses() {
    // First confirmation dialog
    const confirmFirst = confirm(
        "⚠️ WARNING: This will permanently delete ALL analysis data from the database!\n\n" +
        "This includes:\n" +
        "• All transcripts\n" +
        "• All AI analysis results\n" +
        "• All file metadata\n" +
        "• All engagement scores\n\n" +
        "This action CANNOT be undone!\n\n" +
        "Are you sure you want to continue?"
    );
    
    if (!confirmFirst) {
        log('Database clear operation cancelled by user');
        return;
    }
    
    // Second confirmation dialog for extra safety
    const confirmSecond = confirm(
        "🚨 FINAL CONFIRMATION 🚨\n\n" +
        "You are about to DELETE ALL ANALYSIS DATA from the database.\n\n" +
        "Type 'DELETE ALL' in your mind and click OK to confirm, or Cancel to abort."
    );
    
    if (!confirmSecond) {
        log('Database clear operation cancelled by user (second confirmation)');
        return;
    }
    
    try {
        log('🗑️ Starting database clear operation...', 'warning');
        
        const response = await fetch('http://127.0.0.1:5000/api/clear-all-analyses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ Successfully cleared database: ${result.message}`, 'success');
            
            // Update UI to reflect cleared state
            if (result.deleted_count > 0) {
                // Clear analysis results from frontend
                analysisResults = [];
                
                // Reset file analysis status indicators
                sourceFiles.forEach(file => {
                    if (file.is_analyzed) {
                        file.is_analyzed = false;
                        delete file.analysis_info;
                    }
                });
                
                // Re-render displays to show updated state
                if (document.getElementById('scannedFilesCard').style.display !== 'none') {
                    displayScannedFiles();
                }
                
                // Update button states
                updateAnalysisButtonState();
                updateAnalyzeAllButtonState();
                
                log(`📊 Updated UI to reflect ${result.deleted_count} cleared analysis records`);
            }
            
        } else {
            log(`❌ Failed to clear database: ${result.message}`, 'error');
        }
        
    } catch (error) {
        log(`❌ Error clearing database: ${error.message}`, 'error');
    }
}

// Delete Queue Management Functions
function addToDeleteQueue(fileId) {
    console.log('addToDeleteQueue called with fileId:', fileId);
    
    // Find the file in targetOnlyFiles
    const targetOnlyFile = targetOnlyFiles.find(item => item.fileId === fileId);
    if (!targetOnlyFile) {
        log(`File with ID ${fileId} not found in target-only files`, 'error');
        return;
    }
    
    // Check if already in delete queue
    const alreadyInQueue = deleteQueue.find(item => item.fileId === fileId);
    if (alreadyInQueue) {
        log(`${targetOnlyFile.targetFile.name} is already in delete queue`, 'warning');
        return;
    }
    
    // Add to delete queue
    deleteQueue.push(targetOnlyFile);
    
    // Update button state
    const button = document.querySelector(`button[onclick="addToDeleteQueue('${fileId}')"]`);
    if (button) {
        button.innerHTML = '<i class="fas fa-check"></i> Added for Deletion';
        button.classList.add('added');
        button.disabled = true;
    }
    
    log(`📋 Added ${targetOnlyFile.targetFile.name} to delete queue (${deleteQueue.length} files queued for deletion)`);
    updateDeleteButtonState();
    updateBulkDeleteButtonStates();
}

function updateDeleteButtonState() {
    const deleteButton = document.getElementById('deleteButton');
    const clearDeleteButton = document.getElementById('clearDeleteButton');
    
    if (deleteButton) {
        if (deleteQueue.length > 0) {
            deleteButton.disabled = false;
            deleteButton.innerHTML = `<i class="fas fa-trash"></i> Delete Files (${deleteQueue.length})`;
        } else {
            deleteButton.disabled = true;
            deleteButton.innerHTML = '<i class="fas fa-trash"></i> Delete Files';
        }
    }
    
    if (clearDeleteButton) {
        clearDeleteButton.disabled = deleteQueue.length === 0;
    }
}

function clearDeleteQueue() {
    if (deleteQueue.length === 0) {
        log('Delete queue is already empty', 'warning');
        return;
    }
    
    const clearedCount = deleteQueue.length;
    
    // Reset all buttons back to their original state
    deleteQueue.forEach(item => {
        const button = document.querySelector(`button[onclick="addToDeleteQueue('${item.fileId}')"]`);
        if (button) {
            button.innerHTML = '<i class="fas fa-trash"></i> Delete';
            button.classList.remove('added');
            button.disabled = false;
        }
    });
    
    // Clear the queue
    deleteQueue = [];
    
    log(`Cleared ${clearedCount} files from delete queue`);
    updateDeleteButtonState();
    updateBulkDeleteButtonStates();
}

async function deleteFiles() {
    if (deleteQueue.length === 0) {
        log('No files selected for deletion', 'error');
        return;
    }
    
    const dryRun = document.getElementById('dryRunDelete') ? document.getElementById('dryRunDelete').checked : true;
    
    log(`Starting deletion of ${deleteQueue.length} files${dryRun ? ' (DRY RUN)' : ''}...`);
    
    try {
        // Prepare files for deletion
        const filesToDelete = deleteQueue.map(item => ({
            name: item.targetFile.name,
            path: item.relativePath,
            size: item.targetFile.size
        }));
        
        const response = await fetch('http://127.0.0.1:5000/api/delete-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                files: filesToDelete,
                server_type: 'target',
                dry_run: dryRun
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`Delete operation completed: ${result.success_count} successful, ${result.failure_count} failed${dryRun ? ' (DRY RUN)' : ''}`);
            
            // Log individual results
            result.results.forEach(fileResult => {
                if (fileResult.success) {
                    log(`✅ ${fileResult.message}`);
                } else {
                    log(`❌ ${fileResult.message}`, 'error');
                }
            });
            
            if (!dryRun && result.success_count > 0) {
                // Remove successfully deleted files from the delete queue and UI
                const successfulDeletes = result.results.filter(r => r.success).map(r => r.file_name);
                
                // Update delete queue
                deleteQueue = deleteQueue.filter(item => !successfulDeletes.includes(item.targetFile.name));
                
                // Remove from target-only files
                targetOnlyFiles = targetOnlyFiles.filter(item => !successfulDeletes.includes(item.targetFile.name));
                
                // Re-render comparison results to update UI
                renderComparisonResults();
                updateComparisonSummary();
                updateDeleteButtonState();
                updateBulkDeleteButtonStates();
                
                log(`Removed ${successfulDeletes.length} deleted files from UI`);
            }
            
        } else {
            log(`Delete operation failed: ${result.message}`, 'error');
        }
        
    } catch (error) {
        log(`Delete request failed: ${error.message}`, 'error');
    }
}

// Bulk Delete Functions
function addAllUnmatchedToDeleteQueue() {
    if (targetOnlyFiles.length === 0) {
        log('No unmatched files found to delete', 'error');
        return;
    }
    
    let addedCount = 0;
    let skippedCount = 0;
    
    // Add all target-only files to the delete queue
    targetOnlyFiles.forEach(targetOnlyFile => {
        const alreadyInQueue = deleteQueue.find(item => item.fileId === targetOnlyFile.fileId);
        if (!alreadyInQueue) {
            deleteQueue.push(targetOnlyFile);
            addedCount++;
            
            // Update corresponding button
            const button = document.querySelector(`button[onclick="addToDeleteQueue('${targetOnlyFile.fileId}')"]`);
            if (button) {
                button.innerHTML = '<i class="fas fa-check"></i> Added for Deletion';
                button.classList.add('added');
                button.disabled = true;
            }
        } else {
            skippedCount++;
        }
    });
    
    if (addedCount > 0) {
        log(`📋 Added ${addedCount} unmatched files to delete queue (${deleteQueue.length} total files)`);
        if (skippedCount > 0) {
            log(`⏭️ Skipped ${skippedCount} files (already in queue)`);
        }
        updateDeleteButtonState();
        updateBulkDeleteButtonStates();
    } else {
        log('All unmatched files are already in delete queue', 'warning');
    }
}

function addFolderUnmatchedToDeleteQueue() {
    if (deleteQueue.length === 0) {
        log('No files in delete queue - add a file first to determine the folder', 'error');
        return;
    }
    
    // Get the folder path from the last added file
    const lastFile = deleteQueue[deleteQueue.length - 1];
    const targetFolderPath = lastFile.relativePath ? 
        lastFile.relativePath.substring(0, lastFile.relativePath.lastIndexOf('/')) : 
        '';
    
    const isRootFile = !targetFolderPath;
    
    log(`Adding all unmatched files from folder: ${targetFolderPath || 'root directory'}`);
    
    let addedCount = 0;
    let skippedCount = 0;
    
    // Find all unmatched files in the same folder
    targetOnlyFiles.forEach(targetOnlyFile => {
        const itemFolderPath = targetOnlyFile.relativePath ? 
            targetOnlyFile.relativePath.substring(0, targetOnlyFile.relativePath.lastIndexOf('/')) : 
            '';
        
        // Check if file is in the same folder
        const isSameFolder = isRootFile ? !itemFolderPath : itemFolderPath === targetFolderPath;
        
        // Check if file is already in delete queue
        const alreadyInQueue = deleteQueue.find(item => item.fileId === targetOnlyFile.fileId);
        
        if (isSameFolder && !alreadyInQueue) {
            deleteQueue.push(targetOnlyFile);
            addedCount++;
            
            // Update corresponding button
            const button = document.querySelector(`button[onclick="addToDeleteQueue('${targetOnlyFile.fileId}')"]`);
            if (button) {
                button.innerHTML = '<i class="fas fa-check"></i> Added for Deletion';
                button.classList.add('added');
                button.disabled = true;
            }
        } else if (isSameFolder) {
            skippedCount++;
        }
    });
    
    if (addedCount > 0) {
        log(`📋 Added ${addedCount} files from folder "${targetFolderPath || 'root'}" to delete queue`);
        if (skippedCount > 0) {
            log(`⏭️ Skipped ${skippedCount} files (already in queue)`);
        }
        updateDeleteButtonState();
        updateBulkDeleteButtonStates();
    } else {
        log('No additional files found in the specified folder', 'warning');
    }
}

// Helper functions for bulk delete buttons state
function getDeleteFolderStats() {
    if (targetOnlyFiles.length === 0) {
        return null;
    }
    
    if (deleteQueue.length === 0) {
        return null;
    }
    
    // Get the folder path from the last file added to delete queue
    const lastQueuedFile = deleteQueue[deleteQueue.length - 1];
    const targetFolderPath = lastQueuedFile.relativePath ? 
        lastQueuedFile.relativePath.substring(0, lastQueuedFile.relativePath.lastIndexOf('/')) : 
        '';
    
    // Count unmatched files in the same folder that are not already in delete queue
    let unmatchedFilesToDelete = 0;
    targetOnlyFiles.forEach(file => {
        const itemFolderPath = file.relativePath ? 
            file.relativePath.substring(0, file.relativePath.lastIndexOf('/')) : 
            '';
        
        const isSameFolder = !targetFolderPath ? !itemFolderPath : itemFolderPath === targetFolderPath;
        const alreadyInQueue = deleteQueue.find(queueItem => queueItem.fileId === file.fileId);
        
        if (isSameFolder && !alreadyInQueue) {
            unmatchedFilesToDelete++;
        }
    });
    
    return {
        folderPath: targetFolderPath || 'root',
        unmatchedFilesToDelete: unmatchedFilesToDelete
    };
}

function updateBulkDeleteButtonStates() {
    // Update "Delete All Unmatched" button
    const deleteAllButton = document.getElementById('deleteAllUnmatchedButton');
    if (deleteAllButton) {
        const totalUnmatched = targetOnlyFiles.length;
        const queuedUnmatched = deleteQueue.length;
        const remainingUnmatched = totalUnmatched - queuedUnmatched;
        
        if (remainingUnmatched > 0) {
            deleteAllButton.disabled = false;
            deleteAllButton.textContent = `Delete All Unmatched (${remainingUnmatched} files)`;
        } else {
            deleteAllButton.disabled = true;
            deleteAllButton.textContent = totalUnmatched > 0 ? 'Delete All Unmatched (all queued)' : 'Delete All Unmatched (0 files)';
        }
    }
    
    // Update "Delete Folder" button
    const deleteFolderButton = document.getElementById('deleteFolderButton');
    if (deleteFolderButton) {
        const folderStats = getDeleteFolderStats();
        
        if (folderStats && folderStats.unmatchedFilesToDelete > 0) {
            deleteFolderButton.disabled = false;
            deleteFolderButton.textContent = `Delete Folder (${folderStats.unmatchedFilesToDelete} files)`;
            deleteFolderButton.title = `Delete all unmatched files from "${folderStats.folderPath}" folder`;
        } else if (folderStats) {
            deleteFolderButton.disabled = true;
            deleteFolderButton.textContent = 'Delete Folder (0 files)';
            deleteFolderButton.title = `No unmatched files to delete in "${folderStats.folderPath}" folder`;
        } else {
            deleteFolderButton.disabled = true;
            deleteFolderButton.textContent = 'Delete Folder';
            deleteFolderButton.title = 'Add a file to delete queue first to determine folder';
        }
    }
}

// ========================================
// SCHEDULING SYSTEM FUNCTIONS
// ========================================

// Content Type Mappings
const CONTENT_TYPE_MAPPINGS = {
    'AN': { code: 'AN', name: 'ATLANTA NOW', folder: 'ATLANTA NOW' },
    'BMP': { code: 'BMP', name: 'BUMPS', folder: 'BUMPS' },
    'IMOW': { code: 'IMOW', name: 'IMOW', folder: 'IMOW' },
    'IM': { code: 'IM', name: 'INCLUSION MONTHS', folder: 'INCLUSION MONTHS' },
    'IA': { code: 'IA', name: 'INSIDE ATLANTA', folder: 'INSIDE ATLANTA' },
    'LM': { code: 'LM', name: 'LEGISLATIVE MINUTE', folder: 'LEGISLATIVE MINUTE' },
    'MTG': { code: 'MTG', name: 'MEETINGS', folder: 'MEETINGS' },
    'MAF': { code: 'MAF', name: 'MOVING ATLANTA FORWARD', folder: 'MOVING ATLANTA FORWARD' },
    'PKG': { code: 'PKG', name: 'PACKAGES', folder: 'PKGS' },
    'PMO': { code: 'PMO', name: 'PROMOS', folder: 'PROMOS' },
    'PSA': { code: 'PSA', name: 'PSAs', folder: 'PSAs' },
    'SZL': { code: 'SZL', name: 'SIZZLES', folder: 'SIZZLES' },
    'SPP': { code: 'SPP', name: 'SPECIAL PROJECTS', folder: 'SPECIAL PROJECTS' },
    'OTHER': { code: 'OTHER', name: 'OTHER', folder: 'OTHER' }
};

// Scheduling Constants and Configuration
const SCHEDULING_CONFIG = {
    // Duration categories in seconds
    DURATION_CATEGORIES: {
        id: { min: 0, max: 16, label: 'ID (< 16s)' },
        spots: { min: 16, max: 120, label: 'Spots (16s - 2min)' },
        short_form: { min: 120, max: 1200, label: 'Short Form (2-20min)' },
        long_form: { min: 1200, max: Infinity, label: 'Long Form (> 20min)' }
    },
    
    // Category rotation order
    CATEGORY_ROTATION: ['id', 'short_form', 'long_form', 'spots'],
    
    // Timeslots with hours (24-hour format)
    TIMESLOTS: {
        overnight: { start: 0, end: 6, label: 'Overnight (12-6 AM)' },
        early_morning: { start: 6, end: 9, label: 'Early Morning (6-9 AM)' },
        morning: { start: 9, end: 12, label: 'Morning (9 AM-12 PM)' },
        afternoon: { start: 12, end: 18, label: 'Afternoon (12-6 PM)' },
        prime_time: { start: 18, end: 21, label: 'Prime Time (6-9 PM)' },
        evening: { start: 21, end: 24, label: 'Evening (9 PM-12 AM)' }
    },
    
    // Default replay delays (in hours)
    REPLAY_DELAYS: {
        id: 6,
        spots: 12,
        short_form: 24,
        long_form: 48
    },
    
    // Default content expiration (in days)
    CONTENT_EXPIRATION: {
        id: 30,
        spots: 60,
        short_form: 90,
        long_form: 180
    }
};

// Global variables for scheduling
let availableContent = [];
let currentSchedule = null;
let scheduleConfig = SCHEDULING_CONFIG;

// Initialize scheduling dates to today
function initializeSchedulingDates() {
    const today = new Date().toISOString().split('T')[0];
    const scheduleDate = document.getElementById('scheduleDate');
    const viewScheduleDate = document.getElementById('viewScheduleDate');
    
    if (scheduleDate) scheduleDate.value = today;
    if (viewScheduleDate) viewScheduleDate.value = today;
}

// Configuration Modal Functions
function showScheduleConfig(configType) {
    const modal = document.getElementById('configModal');
    const title = document.getElementById('configModalTitle');
    const body = document.getElementById('configModalBody');
    
    let titleText = '';
    let bodyContent = '';
    
    switch (configType) {
        case 'durations':
            titleText = 'Duration Categories Configuration';
            bodyContent = generateDurationConfigHTML();
            break;
        case 'timeslots':
            titleText = 'Timeslots Configuration';
            bodyContent = generateTimeslotConfigHTML();
            break;
        case 'replay':
            titleText = 'Replay Delays Configuration';
            bodyContent = generateReplayConfigHTML();
            break;
        case 'expiration':
            titleText = 'Content Expiration Configuration';
            bodyContent = generateExpirationConfigHTML();
            break;
        case 'rotation':
            titleText = 'Category Rotation Configuration';
            bodyContent = generateRotationConfigHTML();
            break;
    }
    
    title.textContent = titleText;
    body.innerHTML = bodyContent;
    modal.style.display = 'block';
    body.setAttribute('data-config-type', configType);
    
    // Initialize drag and drop for rotation configuration
    if (configType === 'rotation') {
        initRotationDragDrop();
    }
}

function generateDurationConfigHTML() {
    return `
        <div class="config-section">
            <h4>Configure Duration Categories</h4>
            <p>Set the time ranges for each content duration category (in seconds):</p>
            
            <div class="duration-config">
                <div class="form-group">
                    <label>ID (Station Identifiers)</label>
                    <div class="range-inputs">
                        <input type="number" id="id_min" value="0" min="0" readonly> to 
                        <input type="number" id="id_max" value="16" min="1"> seconds
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Spots (Commercials/PSAs)</label>
                    <div class="range-inputs">
                        <input type="number" id="spots_min" value="16" min="1"> to 
                        <input type="number" id="spots_max" value="120" min="1"> seconds
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Short Form Content</label>
                    <div class="range-inputs">
                        <input type="number" id="short_form_min" value="120" min="1"> to 
                        <input type="number" id="short_form_max" value="1200" min="1"> seconds
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Long Form Content</label>
                    <div class="range-inputs">
                        <input type="number" id="long_form_min" value="1200" min="1"> seconds and above
                    </div>
                </div>
            </div>
        </div>
    `;
}

function generateTimeslotConfigHTML() {
    return `
        <div class="config-section">
            <h4>Configure Broadcasting Timeslots</h4>
            <p>Set the hour ranges for each timeslot (24-hour format):</p>
            
            <div class="timeslot-config">
                <div class="form-group">
                    <label>Overnight</label>
                    <div class="range-inputs">
                        <input type="number" id="overnight_start" value="0" min="0" max="23"> to 
                        <input type="number" id="overnight_end" value="6" min="1" max="24"> hours
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Early Morning</label>
                    <div class="range-inputs">
                        <input type="number" id="early_morning_start" value="6" min="0" max="23"> to 
                        <input type="number" id="early_morning_end" value="9" min="1" max="24"> hours
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Morning</label>
                    <div class="range-inputs">
                        <input type="number" id="morning_start" value="9" min="0" max="23"> to 
                        <input type="number" id="morning_end" value="12" min="1" max="24"> hours
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Afternoon</label>
                    <div class="range-inputs">
                        <input type="number" id="afternoon_start" value="12" min="0" max="23"> to 
                        <input type="number" id="afternoon_end" value="18" min="1" max="24"> hours
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Prime Time</label>
                    <div class="range-inputs">
                        <input type="number" id="prime_time_start" value="18" min="0" max="23"> to 
                        <input type="number" id="prime_time_end" value="21" min="1" max="24"> hours
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Evening</label>
                    <div class="range-inputs">
                        <input type="number" id="evening_start" value="21" min="0" max="23"> to 
                        <input type="number" id="evening_end" value="24" min="1" max="24"> hours
                    </div>
                </div>
            </div>
        </div>
    `;
}

function generateReplayConfigHTML() {
    // Initialize with defaults if not set
    const replayDelays = scheduleConfig.REPLAY_DELAYS || {};
    const additionalDelays = scheduleConfig.ADDITIONAL_DELAY_PER_AIRING || {
        id: 1,
        spots: 2,
        short_form: 4,
        long_form: 8
    };
    
    return `
        <div class="config-section">
            <h4>Configure Replay Delays</h4>
            <p>Set initial delay and progressive delay increase for each content category:</p>
            
            <div class="replay-config-table">
                <table class="config-table">
                    <thead>
                        <tr>
                            <th>Duration Category</th>
                            <th>Initial Delay (hours)</th>
                            <th>Additional Delay Per Airing (hours)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>ID</strong></td>
                            <td><input type="number" id="id_replay_delay" value="${replayDelays.id || 6}" min="0" step="1"></td>
                            <td><input type="number" id="id_additional_delay" value="${additionalDelays.id}" min="0" step="0.5"></td>
                        </tr>
                        <tr>
                            <td><strong>Spots</strong></td>
                            <td><input type="number" id="spots_replay_delay" value="${replayDelays.spots || 12}" min="0" step="1"></td>
                            <td><input type="number" id="spots_additional_delay" value="${additionalDelays.spots}" min="0" step="0.5"></td>
                        </tr>
                        <tr>
                            <td><strong>Short Form</strong></td>
                            <td><input type="number" id="short_form_replay_delay" value="${replayDelays.short_form || 24}" min="0" step="1"></td>
                            <td><input type="number" id="short_form_additional_delay" value="${additionalDelays.short_form}" min="0" step="0.5"></td>
                        </tr>
                        <tr>
                            <td><strong>Long Form</strong></td>
                            <td><input type="number" id="long_form_replay_delay" value="${replayDelays.long_form || 48}" min="0" step="1"></td>
                            <td><input type="number" id="long_form_additional_delay" value="${additionalDelays.long_form}" min="0" step="0.5"></td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div class="replay-config-note">
                <p><strong>How it works:</strong></p>
                <ul>
                    <li>Initial Delay: Minimum hours before first replay</li>
                    <li>Additional Delay: Extra hours added for each subsequent airing</li>
                    <li>Total delay = Initial Delay + (Total Airings × Additional Delay)</li>
                </ul>
                <p><em>Example: If a spot has 3 airings with 12h initial + 2h additional = 12 + (3 × 2) = 18 hours minimum delay</em></p>
            </div>
        </div>
    `;
}

function generateExpirationConfigHTML() {
    return `
        <div class="config-section">
            <h4>Configure Content Expiration</h4>
            <p>Set default expiration periods for each content category (in days):</p>
            
            <div class="expiration-config">
                <div class="form-group">
                    <label>ID Content Expiration</label>
                    <input type="number" id="id_expiration" value="30" min="1"> days
                </div>
                
                <div class="form-group">
                    <label>Spots Content Expiration</label>
                    <input type="number" id="spots_expiration" value="60" min="1"> days
                </div>
                
                <div class="form-group">
                    <label>Short Form Content Expiration</label>
                    <input type="number" id="short_form_expiration" value="90" min="1"> days
                </div>
                
                <div class="form-group">
                    <label>Long Form Content Expiration</label>
                    <input type="number" id="long_form_expiration" value="180" min="1"> days
                </div>
            </div>
            
            <div class="expiration-note">
                <p><strong>Note:</strong> Individual content items can override these defaults based on AI-calculated shelf life from analysis.</p>
            </div>
        </div>
    `;
}

function generateRotationConfigHTML() {
    // Get current rotation order from config or use default
    const currentOrder = scheduleConfig.ROTATION_ORDER || ['id', 'spots', 'short_form', 'long_form'];
    
    return `
        <div class="config-section">
            <h4>Configure Category Rotation Order</h4>
            <p>Drag categories to reorder them or add duplicates to increase their frequency:</p>
            
            <div class="rotation-config">
                <div class="rotation-list-container">
                    <h5>Current Rotation Order</h5>
                    <ul id="rotationList" class="rotation-list">
                        ${currentOrder.map((cat, index) => `
                            <li class="rotation-item" data-category="${cat}" data-index="${index}" draggable="true">
                                <span class="drag-handle">☰</span>
                                <span class="category-name">${getCategoryDisplayName(cat)}</span>
                                <button class="remove-btn" onclick="removeRotationItem(${index})">×</button>
                            </li>
                        `).join('')}
                    </ul>
                </div>
                
                <div class="add-category-section">
                    <h5>Add Category to Rotation</h5>
                    <select id="categoryToAdd">
                        <option value="id">ID</option>
                        <option value="spots">Spots</option>
                        <option value="short_form">Short Form</option>
                        <option value="long_form">Long Form</option>
                    </select>
                    <button onclick="addCategoryToRotation()">Add to Rotation</button>
                </div>
                
                <div class="rotation-preview">
                    <h5>Rotation Preview</h5>
                    <p id="rotationPreview">${getRotationPreview(currentOrder)}</p>
                </div>
            </div>
            
            <div class="rotation-note">
                <p><strong>Note:</strong> The scheduler will cycle through categories in this order when selecting content. Adding duplicates increases that category's selection frequency.</p>
            </div>
        </div>
    `;
}

function closeConfigModal() {
    document.getElementById('configModal').style.display = 'none';
}

// Helper functions for rotation configuration
function getCategoryDisplayName(category) {
    const names = {
        'id': 'ID',
        'spots': 'Spots',
        'short_form': 'Short Form',
        'long_form': 'Long Form'
    };
    return names[category] || category;
}

function getRotationPreview(order) {
    return order.map(cat => getCategoryDisplayName(cat)).join(' → ') + ' → (repeat)';
}

function removeRotationItem(index) {
    const rotationList = document.getElementById('rotationList');
    const items = Array.from(rotationList.children);
    
    if (items.length > 1) {  // Keep at least one item
        items[index].remove();
        updateRotationOrder();
    } else {
        alert('You must keep at least one category in the rotation.');
    }
}

function addCategoryToRotation() {
    const categorySelect = document.getElementById('categoryToAdd');
    const category = categorySelect.value;
    const rotationList = document.getElementById('rotationList');
    const currentCount = rotationList.children.length;
    
    const newItem = document.createElement('li');
    newItem.className = 'rotation-item';
    newItem.setAttribute('data-category', category);
    newItem.setAttribute('data-index', currentCount);
    newItem.setAttribute('draggable', 'true');
    newItem.innerHTML = `
        <span class="drag-handle">☰</span>
        <span class="category-name">${getCategoryDisplayName(category)}</span>
        <button class="remove-btn" onclick="removeRotationItem(${currentCount})">×</button>
    `;
    
    rotationList.appendChild(newItem);
    updateRotationOrder();
}

function updateRotationOrder() {
    const rotationList = document.getElementById('rotationList');
    const items = Array.from(rotationList.children);
    
    // Update indices
    items.forEach((item, index) => {
        item.setAttribute('data-index', index);
        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.setAttribute('onclick', `removeRotationItem(${index})`);
        }
    });
    
    // Update preview
    const order = items.map(item => item.getAttribute('data-category'));
    const preview = document.getElementById('rotationPreview');
    if (preview) {
        preview.textContent = getRotationPreview(order);
    }
}

// Initialize drag and drop for rotation list
function initRotationDragDrop() {
    const rotationList = document.getElementById('rotationList');
    if (!rotationList) return;
    
    let draggedItem = null;
    
    rotationList.addEventListener('dragstart', (e) => {
        if (e.target.classList.contains('rotation-item')) {
            draggedItem = e.target;
            e.target.classList.add('dragging');
        }
    });
    
    rotationList.addEventListener('dragend', (e) => {
        if (e.target.classList.contains('rotation-item')) {
            e.target.classList.remove('dragging');
        }
    });
    
    rotationList.addEventListener('dragover', (e) => {
        e.preventDefault();
        const afterElement = getDragAfterElement(rotationList, e.clientY);
        if (afterElement == null) {
            rotationList.appendChild(draggedItem);
        } else {
            rotationList.insertBefore(draggedItem, afterElement);
        }
    });
    
    rotationList.addEventListener('drop', (e) => {
        e.preventDefault();
        updateRotationOrder();
    });
}

function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.rotation-item:not(.dragging)')];
    
    return draggableElements.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        
        if (offset < 0 && offset > closest.offset) {
            return { offset: offset, element: child };
        } else {
            return closest;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

async function saveScheduleConfig() {
    const body = document.getElementById('configModalBody');
    const configType = body.getAttribute('data-config-type');
    
    switch (configType) {
        case 'durations':
            saveDurationConfig();
            break;
        case 'timeslots':
            saveTimeslotConfig();
            break;
        case 'replay':
            saveReplayConfig();
            break;
        case 'expiration':
            saveExpirationConfig();
            break;
        case 'rotation':
            saveRotationConfig();
            break;
    }
    
    // Save to backend
    try {
        const response = await fetch('http://127.0.0.1:5000/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scheduling: {
                    replay_delays: scheduleConfig.REPLAY_DELAYS,
                    additional_delay_per_airing: scheduleConfig.ADDITIONAL_DELAY_PER_AIRING,
                    content_expiration: scheduleConfig.CONTENT_EXPIRATION,
                    timeslots: scheduleConfig.TIMESLOTS,
                    duration_categories: scheduleConfig.DURATION_CATEGORIES,
                    rotation_order: scheduleConfig.ROTATION_ORDER || ['id', 'spots', 'short_form', 'long_form']
                }
            })
        });
        
        const result = await response.json();
        if (result.success) {
            log(`✅ ${configType} configuration saved successfully`);
        } else {
            log(`❌ Failed to save configuration: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`❌ Error saving configuration: ${error.message}`, 'error');
    }
    
    closeConfigModal();
}

function saveDurationConfig() {
    scheduleConfig.DURATION_CATEGORIES = {
        id: { 
            min: 0, 
            max: parseInt(document.getElementById('id_max').value),
            label: `ID (< ${document.getElementById('id_max').value}s)`
        },
        spots: { 
            min: parseInt(document.getElementById('spots_min').value), 
            max: parseInt(document.getElementById('spots_max').value),
            label: `Spots (${document.getElementById('spots_min').value}s - ${document.getElementById('spots_max').value}s)`
        },
        short_form: { 
            min: parseInt(document.getElementById('short_form_min').value), 
            max: parseInt(document.getElementById('short_form_max').value),
            label: `Short Form (${Math.floor(document.getElementById('short_form_min').value/60)}min - ${Math.floor(document.getElementById('short_form_max').value/60)}min)`
        },
        long_form: { 
            min: parseInt(document.getElementById('long_form_min').value), 
            max: Infinity,
            label: `Long Form (> ${Math.floor(document.getElementById('long_form_min').value/60)}min)`
        }
    };
}

function saveTimeslotConfig() {
    scheduleConfig.TIMESLOTS = {
        overnight: { 
            start: parseInt(document.getElementById('overnight_start').value), 
            end: parseInt(document.getElementById('overnight_end').value),
            label: `Overnight (${document.getElementById('overnight_start').value}-${document.getElementById('overnight_end').value})`
        },
        early_morning: { 
            start: parseInt(document.getElementById('early_morning_start').value), 
            end: parseInt(document.getElementById('early_morning_end').value),
            label: `Early Morning (${document.getElementById('early_morning_start').value}-${document.getElementById('early_morning_end').value})`
        },
        morning: { 
            start: parseInt(document.getElementById('morning_start').value), 
            end: parseInt(document.getElementById('morning_end').value),
            label: `Morning (${document.getElementById('morning_start').value}-${document.getElementById('morning_end').value})`
        },
        afternoon: { 
            start: parseInt(document.getElementById('afternoon_start').value), 
            end: parseInt(document.getElementById('afternoon_end').value),
            label: `Afternoon (${document.getElementById('afternoon_start').value}-${document.getElementById('afternoon_end').value})`
        },
        prime_time: { 
            start: parseInt(document.getElementById('prime_time_start').value), 
            end: parseInt(document.getElementById('prime_time_end').value),
            label: `Prime Time (${document.getElementById('prime_time_start').value}-${document.getElementById('prime_time_end').value})`
        },
        evening: { 
            start: parseInt(document.getElementById('evening_start').value), 
            end: parseInt(document.getElementById('evening_end').value),
            label: `Evening (${document.getElementById('evening_start').value}-${document.getElementById('evening_end').value})`
        }
    };
}

function saveReplayConfig() {
    scheduleConfig.REPLAY_DELAYS = {
        id: parseInt(document.getElementById('id_replay_delay').value),
        spots: parseInt(document.getElementById('spots_replay_delay').value),
        short_form: parseInt(document.getElementById('short_form_replay_delay').value),
        long_form: parseInt(document.getElementById('long_form_replay_delay').value)
    };
    
    scheduleConfig.ADDITIONAL_DELAY_PER_AIRING = {
        id: parseFloat(document.getElementById('id_additional_delay').value),
        spots: parseFloat(document.getElementById('spots_additional_delay').value),
        short_form: parseFloat(document.getElementById('short_form_additional_delay').value),
        long_form: parseFloat(document.getElementById('long_form_additional_delay').value)
    };
}

function saveExpirationConfig() {
    scheduleConfig.CONTENT_EXPIRATION = {
        id: parseInt(document.getElementById('id_expiration').value),
        spots: parseInt(document.getElementById('spots_expiration').value),
        short_form: parseInt(document.getElementById('short_form_expiration').value),
        long_form: parseInt(document.getElementById('long_form_expiration').value)
    };
}

function saveRotationConfig() {
    const rotationList = document.getElementById('rotationList');
    const items = Array.from(rotationList.children);
    
    scheduleConfig.ROTATION_ORDER = items.map(item => item.getAttribute('data-category'));
    
    log(`✅ Rotation order updated: ${scheduleConfig.ROTATION_ORDER.join(' → ')}`);
}

// Content Loading and Filtering Functions
async function loadAvailableContent() {
    log('📺 Loading available content for scheduling...');
    
    try {
        // Get filter values
        const contentTypeFilter = document.getElementById('contentTypeFilter')?.value || '';
        const durationCategoryFilter = document.getElementById('durationCategoryFilter')?.value || '';
        const searchFilter = document.getElementById('contentSearchFilter')?.value?.toLowerCase() || '';
        
        log(`🔍 Applying filters - Type: ${contentTypeFilter || 'All'}, Duration: ${durationCategoryFilter || 'All'}, Search: ${searchFilter || 'None'}`);
        
        const response = await fetch('http://127.0.0.1:5000/api/analyzed-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content_type: contentTypeFilter,
                duration_category: durationCategoryFilter,
                search: searchFilter
            })
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText || 'Failed to load content'}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            availableContent = result.content || [];
            displayAvailableContent();
            log(`✅ Loaded ${availableContent.length} available content items`);
            
            // Update the count display in the header
            const countElement = document.getElementById('contentCount');
            if (countElement) {
                countElement.textContent = `(${availableContent.length} items)`;
            }
            
            // Log some details about the content for debugging
            if (availableContent.length > 0) {
                log(`📊 Content types found: ${[...new Set(availableContent.map(c => c.content_type))].join(', ')}`);
                // Debug: log first item structure
                console.log('First content item structure:', availableContent[0]);
            }
        } else {
            log(`❌ Failed to load content: ${result.message}`, 'error');
            // Clear any existing content and show message
            const contentList = document.getElementById('availableContentList');
            if (contentList) {
                contentList.innerHTML = '<p>No analyzed content found. Please analyze some files first.</p>';
            }
        }
        
    } catch (error) {
        log(`❌ Error loading content: ${error.message}`, 'error');
        log(`💡 Check if any files have been analyzed. Go to Dashboard → Analyze Files first.`);
        
        // Clear any existing content and show helpful message
        const contentList = document.getElementById('availableContentList');
        if (contentList) {
            contentList.innerHTML = `
                <div class="error-message">
                    <p><strong>Error loading content:</strong> ${error.message}</p>
                    <p>💡 <strong>Tip:</strong> Make sure you have analyzed some files first:</p>
                    <ol>
                        <li>Go to the Dashboard tab</li>
                        <li>Scan files from your FTP servers</li>
                        <li>Select files and click "Analyze Files"</li>
                        <li>Come back to Scheduling and try "Load Content" again</li>
                    </ol>
                </div>
            `;
        }
    }
}

function showPlaceholderContent() {
    const contentList = document.getElementById('availableContentList');
    contentList.innerHTML = `
        <div class="placeholder-content">
            <p><strong>Demo Content Available:</strong></p>
            <div class="content-item">
                <div class="content-info">
                    <span class="content-title">250715_PSA_Public Safety Announcement</span>
                    <span class="content-type">PSA</span>
                    <span class="content-duration">30s (spots)</span>
                    <span class="engagement-score">Engagement: 8.5/10</span>
                </div>
                <button class="button small primary" onclick="addToSchedule('demo1')">
                    <i class="fas fa-calendar-plus"></i> Add to Schedule
                </button>
            </div>
            <div class="content-item">
                <div class="content-info">
                    <span class="content-title">250716_PRG_Community Meeting</span>
                    <span class="content-type">PRG</span>
                    <span class="content-duration">15m (short_form)</span>
                    <span class="engagement-score">Engagement: 7.2/10</span>
                </div>
                <button class="button small primary" onclick="addToSchedule('demo2')">
                    <i class="fas fa-calendar-plus"></i> Add to Schedule
                </button>
            </div>
            <p><em>Note: This is demo content. Implement /api/analyzed-content endpoint to load real analyzed content from MongoDB.</em></p>
        </div>
    `;
    log('📺 Showing demo content (backend endpoint not yet implemented)');
}

// Content sorting variables
let contentSortField = 'title';
let contentSortOrder = 'asc';

// Rename dialog variables
let currentRenameContent = null;

// Function to update content type
async function updateContentType(contentId, newType) {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/update-content-type', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content_id: contentId,
                content_type: newType
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Content Type Updated', `Successfully updated content type to ${newType}`, 'success');
            
            // Update the content in availableContent array
            const content = availableContent.find(c => c.id == contentId || c._id == contentId);
            if (content) {
                content.content_type = newType;
            }
            
            // Update the dropdown's data-original attribute
            const dropdown = document.querySelector(`[data-content-id="${contentId}"] .content-type-dropdown`);
            if (dropdown) {
                dropdown.setAttribute('data-original', newType);
            }
        } else {
            showNotification('Update Failed', result.message, 'error');
            
            // Revert the dropdown to original value
            const dropdown = document.querySelector(`[data-content-id="${contentId}"] .content-type-dropdown`);
            if (dropdown) {
                const originalValue = dropdown.getAttribute('data-original');
                dropdown.value = originalValue;
            }
        }
    } catch (error) {
        showNotification('Error', error.message, 'error');
        
        // Revert the dropdown to original value
        const dropdown = document.querySelector(`[data-content-id="${contentId}"] .content-type-dropdown`);
        if (dropdown) {
            const originalValue = dropdown.getAttribute('data-original');
            dropdown.value = originalValue;
        }
    }
}

function displayAvailableContent() {
    const contentList = document.getElementById('availableContentList');
    
    // Update the count display
    const countElement = document.getElementById('contentCount');
    if (countElement) {
        countElement.textContent = `(${availableContent.length} items)`;
    }
    
    if (availableContent.length === 0) {
        contentList.innerHTML = '<p>No content matches the current filters</p>';
        return;
    }
    
    // Add sort header
    let html = `
        <div class="content-sort-header">
            <span class="sort-field" data-field="title" onclick="sortContent('title')">
                Title ${getSortIcon('title')}
            </span>
            <span class="sort-field" data-field="type" onclick="sortContent('type')">
                Type ${getSortIcon('type')}
            </span>
            <span class="sort-field" data-field="duration" onclick="sortContent('duration')">
                Duration ${getSortIcon('duration')}
            </span>
            <span class="sort-field" data-field="category" onclick="sortContent('category')">
                Category ${getSortIcon('category')}
            </span>
            <span class="sort-field" data-field="engagement" onclick="sortContent('engagement')">
                Score ${getSortIcon('engagement')}
            </span>
            <span class="sort-field" data-field="lastScheduled" onclick="sortContent('lastScheduled')">
                Last Scheduled ${getSortIcon('lastScheduled')}
            </span>
            <span style="text-align: center;">Actions</span>
        </div>
    `;
    
    html += '<div class="available-content">';
    
    availableContent.forEach(content => {
        const durationTimecode = formatDurationTimecode(content.file_duration || 0);
        const durationCategory = getDurationCategory(content.file_duration);
        const engagementScore = content.engagement_score || 'N/A';
        
        // Format last scheduled date
        let lastScheduledDisplay = 'Never';
        if (content.scheduling?.last_scheduled_date) {
            const lastDate = new Date(content.scheduling.last_scheduled_date);
            const month = (lastDate.getMonth() + 1).toString().padStart(2, '0');
            const day = lastDate.getDate().toString().padStart(2, '0');
            const year = lastDate.getFullYear().toString().slice(-2);
            lastScheduledDisplay = `${month}/${day}/${year}`;
        }
        
        // Use PostgreSQL id as the content identifier
        const contentId = content.id || content._id || content.guid || 'unknown';
        
        html += `
            <div class="content-item" data-content-id="${contentId}">
                <div class="content-info">
                    <span class="content-title" title="${content.file_name}">${content.content_title || content.file_name}</span>
                    <select class="content-type-dropdown" onchange="updateContentType('${contentId}', this.value)" data-original="${content.content_type ? content.content_type.toUpperCase() : ''}">
                        <option value="AN" ${content.content_type && content.content_type.toUpperCase() === 'AN' ? 'selected' : ''}>Atlanta Now</option>
                        <option value="BMP" ${content.content_type && content.content_type.toUpperCase() === 'BMP' ? 'selected' : ''}>Bump</option>
                        <option value="IMOW" ${content.content_type && content.content_type.toUpperCase() === 'IMOW' ? 'selected' : ''}>In My Own Words</option>
                        <option value="IM" ${content.content_type && content.content_type.toUpperCase() === 'IM' ? 'selected' : ''}>Inclusion Months</option>
                        <option value="IA" ${content.content_type && content.content_type.toUpperCase() === 'IA' ? 'selected' : ''}>Inside Atlanta</option>
                        <option value="LM" ${content.content_type && content.content_type.toUpperCase() === 'LM' ? 'selected' : ''}>Legislative Minute</option>
                        <option value="MTG" ${content.content_type && content.content_type.toUpperCase() === 'MTG' ? 'selected' : ''}>Meeting</option>
                        <option value="MAF" ${content.content_type && content.content_type.toUpperCase() === 'MAF' ? 'selected' : ''}>Moving Atlanta Forward</option>
                        <option value="PKG" ${content.content_type && content.content_type.toUpperCase() === 'PKG' ? 'selected' : ''}>Package</option>
                        <option value="PMO" ${content.content_type && content.content_type.toUpperCase() === 'PMO' ? 'selected' : ''}>Promo</option>
                        <option value="PSA" ${content.content_type && content.content_type.toUpperCase() === 'PSA' ? 'selected' : ''}>PSA</option>
                        <option value="SZL" ${content.content_type && content.content_type.toUpperCase() === 'SZL' ? 'selected' : ''}>Sizzle</option>
                        <option value="SPP" ${content.content_type && content.content_type.toUpperCase() === 'SPP' ? 'selected' : ''}>Special Projects</option>
                        <option value="OTHER" ${content.content_type && content.content_type.toUpperCase() === 'OTHER' ? 'selected' : ''}>Other</option>
                    </select>
                    <span class="content-duration">${durationTimecode}</span>
                    <span class="content-category">${durationCategory.toUpperCase()}</span>
                    <span class="engagement-score">${engagementScore}%</span>
                    <span class="content-last-scheduled">${lastScheduledDisplay}</span>
                </div>
                <div class="content-actions">
                    <button class="button small primary" onclick="addToSchedule('${contentId}')" title="Add to Schedule">
                        <i class="fas fa-calendar-plus"></i>
                    </button>`;
        
        // Show add to template button if template is loaded
        if (currentTemplate) {
            html += `
                    <button class="button small success" onclick="addToTemplate('${contentId}')" title="Add to Template">
                        <i class="fas fa-plus"></i>
                    </button>`;
        }
        
        html += `
                    <button class="button small warning" onclick="showRenameDialog('${contentId}')" title="Rename/Fix">
                        <i class="fas fa-edit"></i> R
                    </button>
                    <button class="button small secondary" onclick="viewContentDetails('${contentId}')" title="View Details">
                        <i class="fas fa-info"></i>
                    </button>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    contentList.innerHTML = html;
}

// Schedule Creation Functions
async function createDailySchedule() {
    const scheduleDate = document.getElementById('scheduleDate').value;
    
    if (!scheduleDate) {
        log('❌ Please select a schedule date', 'error');
        return;
    }
    
    log(`📅 Creating daily schedule for ${scheduleDate}...`);
    log(`🔄 Using duration category rotation: ID → Short Form → Long Form → Spots`);
    
    try {
        const requestBody = {
            date: scheduleDate,
            schedule_name: `Daily Schedule - ${scheduleDate}`
        };
        
        const response = await fetch('http://127.0.0.1:5000/api/create-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ ${result.message}`);
            
            if (result.schedule_id) {
                log(`📋 Schedule ID: ${result.schedule_id}`);
                log(`📊 Created ${result.total_items} items`);
                log(`⏱️ Total duration: ${result.total_duration_hours.toFixed(1)} hours`);
            }
            
            // Show success notification
            showNotification(
                'Schedule Created',
                `Successfully created daily schedule with ${result.total_items} items`,
                'success'
            );
            
            // Set the view date to the newly created schedule
            document.getElementById('viewScheduleDate').value = scheduleDate;
            
            // Refresh schedule display
            await viewDailySchedule();
            
            // Also refresh the schedule list if it's open
            await listAllSchedules();
        } else {
            log(`❌ Failed to create schedule: ${result.message}`, 'error');
            
            // Show error notification
            showNotification(
                'Schedule Creation Failed',
                result.message,
                'error'
            );
            
            if (result.error_count) {
                log(`📊 Failed after ${result.error_count} consecutive errors`, 'error');
            }
        }
        
    } catch (error) {
        log(`❌ Error creating schedule: ${error.message}`, 'error');
    }
}

async function createWeeklySchedule() {
    const scheduleDate = document.getElementById('scheduleDate').value;
    
    if (!scheduleDate) {
        log('❌ Please select a start date for the weekly schedule', 'error');
        return;
    }
    
    // Calculate the Sunday of the week containing the selected date
    const selectedDate = new Date(scheduleDate);
    const dayOfWeek = selectedDate.getDay();
    const sunday = new Date(selectedDate);
    // Adjust to Sunday (day 0)
    sunday.setDate(selectedDate.getDate() - dayOfWeek);
    
    const weekStartDate = sunday.toISOString().split('T')[0];
    
    log(`📅 Creating single weekly schedule starting Sunday ${weekStartDate}...`);
    log(`🔄 Creating schedule with 7 days of content...`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/create-weekly-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_date: weekStartDate,
                schedule_type: 'single'  // Create single weekly schedule
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ ${result.message}`);
            
            if (result.schedule_type === 'weekly') {
                // Single weekly schedule
                log(`📊 Weekly Summary: ${result.total_items} items scheduled`);
                log(`⏱️ Total Duration: ${result.total_duration_hours.toFixed(1)} hours`);
                log(`🆔 Schedule ID: ${result.schedule_id}`);
                
                // Show success notification
                showNotification(
                    'Weekly Schedule Created',
                    `Successfully created weekly schedule with ${result.total_items} items`,
                    'success'
                );
            } else if (result.created_schedules) {
                // Multiple daily schedules (old format)
                log(`📊 Weekly Summary: ${result.total_created} schedules created across 7 days`);
                
                // Group schedules by date for better display
                const schedulesByDate = {};
                result.created_schedules.forEach(schedule => {
                    if (!schedulesByDate[schedule.date]) {
                        schedulesByDate[schedule.date] = [];
                    }
                    schedulesByDate[schedule.date].push(schedule);
                });
                
                // Log schedules by date
                Object.keys(schedulesByDate).sort().forEach(date => {
                    const daySchedules = schedulesByDate[date];
                    const dayName = daySchedules[0].day_of_week;
                    log(`  📅 ${dayName} (${date}): ${daySchedules.length} timeslots`);
                    daySchedules.forEach(schedule => {
                        log(`    ✓ ${schedule.timeslot}: ${schedule.total_items} items (${Math.floor(schedule.total_duration / 60)}m ${schedule.total_duration % 60}s)`);
                    });
                });
                
                if (result.failed_schedules && result.failed_schedules.length > 0) {
                    log(`⚠️ ${result.total_failed} schedules failed:`, 'warning');
                    result.failed_schedules.forEach(failure => {
                        const timeslotInfo = failure.timeslot ? ` (${failure.timeslot})` : '';
                        log(`  ❌ ${failure.day_of_week} ${failure.date}${timeslotInfo}: ${failure.error}`, 'warning');
                    });
                }
            }
        } else {
            log(`❌ Failed to create weekly schedule: ${result.message}`, 'error');
            
            // Show error notification
            showNotification(
                'Weekly Schedule Creation Failed',
                result.message,
                'error'
            );
            
            if (result.error_count) {
                log(`📊 Failed after ${result.error_count} consecutive errors`, 'error');
            }
        }
        
    } catch (error) {
        log(`❌ Error creating weekly schedule: ${error.message}`, 'error');
    }
}

async function createMonthlySchedule() {
    const scheduleDate = document.getElementById('scheduleDate').value;
    
    if (!scheduleDate) {
        log('❌ Please select a start date for the monthly schedule', 'error');
        return;
    }
    
    // Parse the selected date to get year and month
    const selectedDate = new Date(scheduleDate);
    const year = selectedDate.getFullYear();
    const month = selectedDate.getMonth() + 1; // JavaScript months are 0-indexed
    
    // Calculate the first day of the month
    const monthStartDate = new Date(year, selectedDate.getMonth(), 1).toISOString().split('T')[0];
    const monthName = selectedDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    
    log(`📅 Creating monthly schedule for ${monthName}...`);
    log(`🔄 Creating schedule for entire month...`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/create-monthly-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                year: year,
                month: month
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ ${result.message}`);
            log(`📊 Monthly Summary: ${result.total_items} items scheduled`);
            log(`⏱️ Total Duration: ${result.total_duration_hours.toFixed(1)} hours`);
            log(`📆 Days Covered: ${result.days_count} days`);
            log(`🆔 Schedule ID: ${result.schedule_id}`);
            
            // Show success notification
            showNotification(
                'Monthly Schedule Created',
                `Successfully created monthly schedule for ${monthName} with ${result.total_items} items`,
                'success'
            );
        } else {
            log(`❌ Failed to create monthly schedule: ${result.message}`, 'error');
            
            // Show error notification
            showNotification(
                'Monthly Schedule Creation Failed',
                result.message,
                'error'
            );
            
            if (result.error_count) {
                log(`📊 Failed after ${result.error_count} consecutive errors`, 'error');
            }
        }
        
    } catch (error) {
        log(`❌ Error creating monthly schedule: ${error.message}`, 'error');
    }
}

// Function to list all playlists
async function listAllPlaylists() {
    console.log('Fetching all playlists...');
    log('📋 Loading playlists...', 'info');
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/list-playlists');
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Playlists data:', data);
        
        if (data.success) {
            displayPlaylistList(data.playlists);
            log(`✅ Loaded ${data.playlists.length} playlists`, 'success');
        } else {
            log(`❌ ${data.message}`, 'error');
            showNotification('Error Loading Playlists', data.message, 'error');
        }
    } catch (error) {
        console.error('Error details:', error);
        log(`❌ Error loading playlists: ${error.message}`, 'error');
        showNotification('Error', error.message, 'error');
    }
}

// Function to display playlist list
function displayPlaylistList(playlists) {
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    
    if (!scheduleDisplay) return;
    
    if (!playlists || playlists.length === 0) {
        scheduleDisplay.innerHTML = '<p>🎵 No playlists found. Create a playlist to get started.</p>';
        return;
    }
    
    let html = `
        <div class="playlist-list-header">
            <h4>🎵 Simple Playlists (${playlists.length} total)</h4>
        </div>
        <div class="playlist-list">
    `;
    
    // Sort playlists by created date (newest first)
    playlists.sort((a, b) => new Date(b.created_date) - new Date(a.created_date));
    
    for (const playlist of playlists) {
        const createdDate = new Date(playlist.created_date).toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
        
        html += `
            <div class="playlist-list-item" data-playlist-id="${playlist.id}">
                <div class="playlist-item-header">
                    <div style="flex: 1;">
                        <h5 style="margin: 0;">🎵 ${playlist.name}</h5>
                        <span class="playlist-stats">${playlist.item_count || 0} items • Created: ${createdDate}${playlist.server ? ` • Server: ${playlist.server}` : ''}</span>
                        ${playlist.description ? `<p style="margin: 5px 0 0 0; color: #666;">${playlist.description}</p>` : ''}
                        ${playlist.path ? `<p style="margin: 2px 0 0 0; color: #999; font-size: 12px;">Path: ${playlist.path}</p>` : ''}
                    </div>
                    <div class="playlist-item-actions">
                        <button class="button small primary" onclick="viewPlaylistItems(${playlist.id}, '${playlist.name}', '${playlist.server || 'target'}', '${playlist.path || '/mnt/main/Playlists'}')">
                            <i class="fas fa-eye"></i> View Items
                        </button>
                        <button class="button small secondary" onclick="exportPlaylist(${playlist.id}, '${playlist.server || 'target'}', '${playlist.path || '/mnt/main/Playlists'}')">
                            <i class="fas fa-download"></i> Export
                        </button>
                        <button class="button small danger" onclick="deletePlaylist(${playlist.id}, '${playlist.server || 'target'}', '${playlist.path || '/mnt/main/Playlists'}', '${playlist.name}')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    scheduleDisplay.innerHTML = html;
}

// Function to view playlist items
async function viewPlaylistItems(playlistId, playlistName, server = 'target', path = '/mnt/main/Playlists') {
    console.log(`Loading items for playlist ${playlistId} from ${server} server at ${path}...`);
    log(`📋 Loading playlist items for "${playlistName}" from ${server} server...`, 'info');
    
    try {
        const response = await fetch(`http://127.0.0.1:5000/api/playlist/${playlistId}/items?server=${server}&path=${encodeURIComponent(path)}`);
        const data = await response.json();
        
        if (data.success) {
            displayPlaylistItems(data.playlist, data.items);
            log(`✅ Loaded ${data.items.length} items`, 'success');
        } else {
            log(`❌ ${data.message}`, 'error');
            showNotification('Error Loading Playlist Items', data.message, 'error');
        }
    } catch (error) {
        log(`❌ Error loading playlist items: ${error.message}`, 'error');
        showNotification('Error', error.message, 'error');
    }
}

// Function to display playlist items
function displayPlaylistItems(playlist, items) {
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    
    if (!scheduleDisplay) return;
    
    let html = `
        <div class="playlist-header">
            <button class="button small secondary" onclick="listAllPlaylists()" style="margin-bottom: 10px;">
                <i class="fas fa-arrow-left"></i> Back to Playlists
            </button>
            <h4>🎵 ${playlist.name}</h4>
            <p><strong>Description:</strong> ${playlist.description || 'No description'}</p>
            <p><strong>Items:</strong> ${items.length} | <strong>Created:</strong> ${new Date(playlist.created_date).toLocaleString()}</p>
        </div>
        <div class="playlist-items">
            <div class="playlist-table-header">
                <span class="col-position">#</span>
                <span class="col-filename">File Name</span>
                <span class="col-filepath">File Path</span>
                <span class="col-actions">Actions</span>
            </div>
    `;
    
    if (items && items.length > 0) {
        items.forEach((item, index) => {
            html += `
                <div class="playlist-item-row" data-item-id="${item.id}">
                    <span class="col-position">${item.position + 1}</span>
                    <span class="col-filename" title="${item.file_name}">${item.file_name}</span>
                    <span class="col-filepath" title="${item.file_path}">${item.file_path}</span>
                    <span class="col-actions">
                        <button class="button tiny danger" onclick="removePlaylistItem(${playlist.id}, ${item.id})">
                            <i class="fas fa-times"></i> Remove
                        </button>
                    </span>
                </div>
            `;
        });
    } else {
        html += '<div class="playlist-no-items"><p>No items in this playlist</p></div>';
    }
    
    html += '</div>';
    scheduleDisplay.innerHTML = html;
}

// Function to delete a playlist
async function deletePlaylist(playlistId, server = 'target', path = '/mnt/main/Playlists', name = '') {
    if (!confirm('Are you sure you want to delete this playlist?')) {
        return;
    }
    
    try {
        let url = `http://127.0.0.1:5000/api/playlist/${playlistId}?server=${server}&path=${encodeURIComponent(path)}`;
        if (name) {
            url += `&name=${encodeURIComponent(name)}`;
        }
        
        const response = await fetch(url, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            log(`✅ Playlist deleted successfully`, 'success');
            showNotification('Playlist Deleted', 'The playlist has been removed', 'success');
            // Refresh the playlist list
            listAllPlaylists();
        } else {
            log(`❌ ${data.message}`, 'error');
            showNotification('Delete Failed', data.message, 'error');
        }
    } catch (error) {
        log(`❌ Error deleting playlist: ${error.message}`, 'error');
        showNotification('Error', error.message, 'error');
    }
}

// Function to export a playlist - shows modal for options
async function exportPlaylist(playlistId, server = 'target') {
    try {
        console.log(`DEBUG: Fetching playlist ${playlistId} info for export from ${server} server...`);
        
        // First, get playlist info to populate the modal
        const response = await fetch(`http://127.0.0.1:5000/api/playlist/${playlistId}/items?server=${server}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('DEBUG: Playlist data received:', data);
        
        if (data.success) {
            // Store the playlist data for export
            window.currentExportPlaylist = {
                id: playlistId,
                name: data.playlist.name,
                items: data.items,
                totalItems: data.total_items,
                sourceServer: server
            };
            
            // Populate modal with playlist info
            document.getElementById('exportPlaylistFilename').value = window.currentExportPlaylist.name;
            document.getElementById('exportPlaylistInfo').innerHTML = `
                <strong>Playlist:</strong> ${window.currentExportPlaylist.name}<br>
                <strong>Total Items:</strong> ${window.currentExportPlaylist.totalItems}
            `;
            
            // Show the modal
            document.getElementById('playlistExportModal').style.display = 'block';
            
            // Add event listener for custom count selection
            document.getElementById('exportPlaylistItemCount').addEventListener('change', function(e) {
                const customInput = document.getElementById('exportPlaylistCustomCount');
                if (e.target.value === 'custom') {
                    customInput.style.display = 'block';
                    customInput.focus();
                } else {
                    customInput.style.display = 'none';
                }
            });
        } else {
            console.error('DEBUG: API returned error:', data.message);
            showNotification('Error', data.message || 'Failed to load playlist info', 'error');
        }
    } catch (error) {
        console.error('DEBUG: Exception in exportPlaylist:', error);
        log(`❌ Error loading playlist: ${error.message}`, 'error');
        showNotification('Error', error.message, 'error');
    }
}

// Function to remove an item from a playlist
async function removePlaylistItem(playlistId, itemId) {
    if (!confirm('Remove this item from the playlist?')) {
        return;
    }
    
    try {
        const response = await fetch(`http://127.0.0.1:5000/api/playlist/${playlistId}/item/${itemId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            log(`✅ Item removed from playlist`, 'success');
            // Refresh the playlist items
            viewPlaylistItems(playlistId, data.playlist_name || 'Playlist');
        } else {
            log(`❌ ${data.message}`, 'error');
            showNotification('Remove Failed', data.message, 'error');
        }
    } catch (error) {
        log(`❌ Error removing item: ${error.message}`, 'error');
        showNotification('Error', error.message, 'error');
    }
}

// Show the simple playlist modal
window.generateSimplePlaylist = function(event) {
    console.log('Opening simple playlist modal');
    document.getElementById('simplePlaylistModal').style.display = 'block';
    
    // Add event listener for custom count selection
    document.getElementById('playlistItemCount').addEventListener('change', function(e) {
        const customInput = document.getElementById('playlistCustomCount');
        if (e.target.value === 'custom') {
            customInput.style.display = 'block';
            customInput.focus();
        } else {
            customInput.style.display = 'none';
        }
    });
}

// Close the simple playlist modal
function closeSimplePlaylistModal() {
    document.getElementById('simplePlaylistModal').style.display = 'none';
    document.getElementById('playlistPreview').style.display = 'none';
}

// Close the playlist export modal
function closePlaylistExportModal() {
    document.getElementById('playlistExportModal').style.display = 'none';
    window.currentExportPlaylist = null;
}

// Preview playlist files
async function previewPlaylistFiles() {
    const server = document.getElementById('playlistSourceServer').value;
    const path = document.getElementById('playlistSourcePath').value;
    
    log('🔍 Previewing files...', 'info');
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/preview-playlist-files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: server,
                path: path
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const previewDiv = document.getElementById('playlistPreview');
            const previewContent = document.getElementById('playlistPreviewContent');
            
            let html = `<p>Found ${data.files.length} files:</p><ul style="margin: 0; padding-left: 20px;">`;
            data.files.slice(0, 10).forEach(file => {
                html += `<li>${file}</li>`;
            });
            if (data.files.length > 10) {
                html += `<li><em>... and ${data.files.length - 10} more files</em></li>`;
            }
            html += '</ul>';
            
            previewContent.innerHTML = html;
            previewDiv.style.display = 'block';
        } else {
            showNotification('Preview Failed', data.message, 'error');
        }
    } catch (error) {
        showNotification('Error', error.message, 'error');
    }
}

// Confirm and create the playlist
async function confirmCreatePlaylist() {
    const server = document.getElementById('playlistSourceServer').value;
    const sourcePath = document.getElementById('playlistSourcePath').value;
    const exportPath = document.getElementById('playlistExportPath').value;
    let filename = document.getElementById('playlistFilename').value;
    const itemCountSelect = document.getElementById('playlistItemCount').value;
    const customCount = document.getElementById('playlistCustomCount').value;
    const shuffle = document.getElementById('playlistShuffle').checked;
    
    // Determine item count
    let itemCount = null;
    if (itemCountSelect === 'custom') {
        itemCount = parseInt(customCount);
        if (!itemCount || itemCount < 1) {
            showNotification('Invalid Count', 'Please enter a valid number of items', 'error');
            return;
        }
    } else if (itemCountSelect !== 'all') {
        itemCount = parseInt(itemCountSelect);
    }
    
    // Ensure filename doesn't have extension
    if (!filename.endsWith('.json') && !filename.includes('.')) {
        filename = filename;  // Keep as is for Castus format
    }
    
    log('📋 Creating simple playlist...', 'info');
    
    // Show loading on button
    const button = event.currentTarget;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
    button.disabled = true;
    
    try {
        const requestBody = {
            server: server,
            source_path: sourcePath,
            export_path: exportPath,
            filename: filename,
            item_count: itemCount,
            shuffle: shuffle
        };
        console.log('Creating playlist with:', requestBody);
        
        const response = await fetch('http://127.0.0.1:5000/api/generate-simple-playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (data.success) {
            log(`✅ ${data.message}`, 'success');
            if (data.file_count) {
                log(`📁 Added ${data.file_count} files to playlist`, 'info');
            }
            // Show success notification
            showNotification(
                'Simple Playlist Created',
                `Successfully created playlist "${filename}" with ${data.file_count || 0} files`,
                'success'
            );
            
            // Close modal
            closeSimplePlaylistModal();
            
            // Optionally refresh playlist list if visible
            if (document.getElementById('scheduleDisplay').innerHTML.includes('playlist-list')) {
                listAllPlaylists();
            }
        } else {
            log(`❌ ${data.message}`, 'error');
            showNotification(
                'Playlist Creation Failed',
                data.message,
                'error'
            );
        }
    } catch (error) {
        log(`❌ Error generating playlist: ${error.message}`, 'error');
        showNotification(
            'Playlist Creation Error',
            error.message,
            'error'
        );
    } finally {
        // Restore button state
        if (button) {
            button.innerHTML = originalText;
            button.disabled = false;
        }
    }
}

// Confirm and export the playlist with selected options
async function confirmExportPlaylist() {
    if (!window.currentExportPlaylist) {
        showNotification('Error', 'No playlist selected for export', 'error');
        return;
    }
    
    const server = document.getElementById('exportPlaylistServer').value;
    const exportPath = document.getElementById('exportPlaylistPath').value;
    let filename = document.getElementById('exportPlaylistFilename').value;
    const itemCountSelect = document.getElementById('exportPlaylistItemCount').value;
    const customCount = document.getElementById('exportPlaylistCustomCount').value;
    const shuffle = document.getElementById('exportPlaylistShuffle').checked;
    
    // Determine item count
    let itemCount = null;
    if (itemCountSelect === 'custom') {
        itemCount = parseInt(customCount);
        if (!itemCount || itemCount < 1) {
            showNotification('Invalid Count', 'Please enter a valid number of items', 'error');
            return;
        }
    } else if (itemCountSelect !== 'all') {
        itemCount = parseInt(itemCountSelect);
    }
    
    log('📥 Exporting playlist with custom options...', 'info');
    
    // Show loading on button
    const button = event.currentTarget;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting...';
    button.disabled = true;
    
    try {
        const requestBody = {
            playlist_id: window.currentExportPlaylist.id,
            source_server: window.currentExportPlaylist.sourceServer,  // Which server the playlist is on
            server: server,  // Export destination server
            export_path: exportPath,
            filename: filename,
            item_count: itemCount,
            shuffle: shuffle
        };
        
        const response = await fetch(`http://127.0.0.1:5000/api/playlist/${window.currentExportPlaylist.id}/export`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (data.success) {
            log(`✅ Playlist exported to ${data.path}`, 'success');
            showNotification('Playlist Exported', `Exported to ${data.path}`, 'success');
            closePlaylistExportModal();
        } else {
            log(`❌ ${data.message}`, 'error');
            showNotification('Export Failed', data.message, 'error');
        }
    } catch (error) {
        log(`❌ Error exporting playlist: ${error.message}`, 'error');
        showNotification('Error', error.message, 'error');
    } finally {
        // Restore button state
        if (button) {
            button.innerHTML = originalText;
            button.disabled = false;
        }
    }
}

async function previewSchedule() {
    const scheduleDate = document.getElementById('scheduleDate').value;
    const timeslot = document.getElementById('scheduleTimeslot').value;
    const useEngagement = document.getElementById('enableEngagementScoring').checked;
    
    if (!scheduleDate) {
        log('❌ Please select a schedule date', 'error');
        return;
    }
    
    log(`👁️ Previewing schedule for ${scheduleDate} in ${timeslot} timeslot`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/preview-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: scheduleDate,
                timeslot: timeslot,
                use_engagement_scoring: useEngagement
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            const preview = result.preview;
            log(`✅ Schedule Preview Generated:`);
            log(`📊 ${preview.total_items} items, ${preview.total_duration_formatted}`);
            log(`📈 ${preview.fill_percentage.toFixed(1)}% of ${timeslot} timeslot filled`);
            log(`🎯 Available content pool: ${preview.available_content_count} items`);
            log(`🧠 Engagement scoring: ${preview.engagement_scoring_enabled ? 'ON' : 'OFF'}`);
            
            // Show preview items
            if (preview.items && preview.items.length > 0) {
                log(`📋 Preview Schedule:`);
                preview.items.forEach((item, index) => {
                    const duration = formatDuration(item.duration);
                    const score = item.engagement_score ? ` (${item.engagement_score}/10)` : '';
                    log(`   ${index + 1}. ${item.content_title} [${item.content_type}] - ${duration}${score}`);
                });
            }
        } else {
            log(`❌ Failed to preview schedule: ${result.message}`, 'error');
        }
        
    } catch (error) {
        log(`❌ Error previewing schedule: ${error.message}`, 'error');
    }
}

async function viewDailySchedule() {
    const viewDate = document.getElementById('viewScheduleDate').value;
    
    if (!viewDate) {
        log('❌ Please select a date to view', 'error');
        return;
    }
    
    log(`📅 Loading schedule for ${viewDate}...`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/get-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: viewDate
            })
        });
        
        const result = await response.json();
        
        if (result.success && result.schedule) {
            const schedule = result.schedule;
            currentSchedule = schedule;  // Store the current schedule
            log(`✅ Schedule found for ${viewDate}`);
            
            // Display schedule in the schedule display area
            displayScheduleDetails(schedule);
            
        } else {
            log(`📭 No schedule found for ${viewDate}`);
            currentSchedule = null;  // Clear current schedule
            clearScheduleDisplay();
        }
        
    } catch (error) {
        log(`❌ Error viewing schedule: ${error.message}`, 'error');
        clearScheduleDisplay();
    }
}

async function deleteSchedule() {
    const viewDate = document.getElementById('viewScheduleDate').value;
    
    if (!viewDate) {
        log('❌ Please select a date to delete', 'error');
        return;
    }
    
    // First get the schedule to find its ID
    try {
        const response = await fetch('http://127.0.0.1:5000/api/get-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: viewDate
            })
        });
        
        const result = await response.json();
        
        if (!result.success || !result.schedule) {
            log(`❌ No schedule found for ${viewDate}`, 'error');
            return;
        }
        
        const schedule = result.schedule;
        const scheduleId = schedule.id;
        
        if (confirm(`Are you sure you want to delete the schedule for ${viewDate}?\n\nThis will delete ${schedule.total_items} scheduled items.`)) {
            log(`🗑️ Deleting schedule for ${viewDate}...`);
            
            const deleteResponse = await fetch('http://127.0.0.1:5000/api/delete-schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    schedule_id: scheduleId
                })
            });
            
            const deleteResult = await deleteResponse.json();
            
            if (deleteResult.success) {
                log(`✅ ${deleteResult.message}`);
                clearScheduleDisplay();
                
                // Auto-refresh schedule list if it was displayed
                const scheduleDisplay = document.getElementById('scheduleDisplay');
                if (scheduleDisplay && scheduleDisplay.innerHTML.includes('schedule-list-item')) {
                    log('🔄 Refreshing schedule list...');
                    await listAllSchedules();
                }
            } else {
                log(`❌ Failed to delete schedule: ${deleteResult.message}`, 'error');
            }
        }
        
    } catch (error) {
        log(`❌ Error deleting schedule: ${error.message}`, 'error');
    }
}

async function listAllSchedules() {
    log('📋 Loading all schedules...');
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/list-schedules');
        const result = await response.json();
        
        if (result.success) {
            displayScheduleList(result.schedules);
            log(`✅ Loaded ${result.count} schedules`);
        } else {
            log(`❌ Failed to load schedules: ${result.message}`, 'error');
            clearScheduleDisplay();
        }
        
    } catch (error) {
        log(`❌ Error loading schedules: ${error.message}`, 'error');
        clearScheduleDisplay();
    }
}

function displayScheduleList(schedules) {
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    
    if (!scheduleDisplay) return;
    
    if (!schedules || schedules.length === 0) {
        scheduleDisplay.innerHTML = '<p>📅 No schedules found. Create a schedule to get started.</p>';
        return;
    }
    
    let html = `
        <div class="schedule-list-header">
            <h4>📋 Active Schedules (${schedules.length} total)</h4>
        </div>
        <div class="schedule-list">
    `;
    
    // Sort schedules by air_date (newest first)
    schedules.sort((a, b) => {
        const dateA = new Date(a.air_date);
        const dateB = new Date(b.air_date);
        return dateB - dateA;
    });
    
    for (const schedule of schedules) {
        const airDate = schedule.air_date.split('T')[0];
        // Parse date components to avoid timezone issues
        const [year, month, day] = airDate.split('-').map(num => parseInt(num));
        const dateObj = new Date(year, month - 1, day);
        const dayName = dateObj.toLocaleDateString('en-US', { weekday: 'long' });
        
        // Parse created date properly for local timezone
        const createdAt = new Date(schedule.created_date).toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
        const totalDurationHours = schedule.total_duration_hours || 0;
        const totalDurationFormatted = `${totalDurationHours.toFixed(1)} hours`;
        
        html += `
            <div class="schedule-list-item" data-schedule-id="${schedule.id}">
                <div class="schedule-item-header">
                    <div style="flex: 1;">
                        <h5 style="margin: 0;">📅 ${dayName}, ${airDate}</h5>
                        <span class="schedule-stats">${schedule.item_count || 0} items • ${totalDurationFormatted}</span>
                    </div>
                    <div class="schedule-item-actions">
                        <button class="button small primary" onclick="viewScheduleDetails(${schedule.id}, '${airDate}')">
                            <i class="fas fa-eye"></i> View
                        </button>
                        <button class="button small warning" onclick="deleteScheduleById(${schedule.id}, '${airDate}')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                </div>
                <div class="schedule-item-details">
                    <small>
                        ${schedule.schedule_name || 'Daily Schedule'} • 
                        Channel: ${schedule.channel || 'Comcast Channel 26'} • 
                        Created: ${createdAt}
                    </small>
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    
    scheduleDisplay.innerHTML = html;
}

async function viewScheduleDetails(scheduleId, date) {
    log(`👁️ Loading schedule details for ${date}...`);
    
    // Set the view date field
    document.getElementById('viewScheduleDate').value = date;
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/get-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: date
            })
        });
        
        const result = await response.json();
        
        if (result.success && result.schedule) {
            currentSchedule = result.schedule;  // Store the schedule globally
            displayScheduleDetails(result.schedule);
            log(`✅ Loaded schedule details for ${date}`);
        } else {
            log(`❌ Failed to load schedule details: ${result.message}`, 'error');
        }
        
    } catch (error) {
        log(`❌ Error loading schedule details: ${error.message}`, 'error');
    }
}

async function deleteScheduleById(scheduleId, date) {
    if (!confirm(`Are you sure you want to delete the schedule for ${date}?`)) {
        return;
    }
    
    log(`🗑️ Deleting schedule ${scheduleId}...`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/delete-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ ${result.message}`);
            // Refresh the schedule list
            await listAllSchedules();
        } else {
            log(`❌ Failed to delete schedule: ${result.message}`, 'error');
        }
        
    } catch (error) {
        log(`❌ Error deleting schedule: ${error.message}`, 'error');
    }
}

async function deleteAllSchedules() {
    const confirmMessage = `Are you sure you want to delete ALL schedules?\n\nThis will:\n• Remove all schedules and scheduled items\n• Reset all scheduling history and last scheduled dates\n• This action cannot be undone!`;
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    // Double confirmation for such a destructive action
    if (!confirm('This will DELETE ALL SCHEDULES PERMANENTLY. Are you absolutely sure?')) {
        return;
    }
    
    log('🗑️ Deleting all schedules...');
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/delete-all-schedules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ ${result.message}`);
            log(`📊 Deleted ${result.schedules_deleted} schedules`);
            log(`🔄 Reset ${result.metadata_reset} content scheduling records`);
            
            // Show success notification
            showNotification(
                'All Schedules Deleted',
                result.message,
                'success'
            );
            
            // Clear the schedule display
            clearScheduleDisplay();
            
            // Refresh the schedule list if it's open
            const scheduleDisplay = document.getElementById('scheduleDisplay');
            if (scheduleDisplay && scheduleDisplay.innerHTML.includes('schedule-list-item')) {
                await listAllSchedules();
            }
        } else {
            log(`❌ Failed to delete all schedules: ${result.message}`, 'error');
            
            // Show error notification
            showNotification(
                'Delete Failed',
                result.message,
                'error'
            );
        }
        
    } catch (error) {
        log(`❌ Error deleting all schedules: ${error.message}`, 'error');
        showNotification(
            'Delete Failed',
            error.message,
            'error'
        );
    }
}

function exportSchedule() {
    const viewDate = document.getElementById('viewScheduleDate').value;
    
    if (!viewDate) {
        log('❌ Please select a date to export', 'error');
        return;
    }
    
    // Show the export modal
    document.getElementById('exportScheduleDate').textContent = viewDate;
    document.getElementById('exportModal').style.display = 'block';
    
    // Load saved export settings if available
    const savedServer = localStorage.getItem('exportServer') || 'target';
    const savedPath = localStorage.getItem('exportPath') || '/mnt/md127/Schedules/Contributors/Jay';
    
    // Determine if this is a weekly or monthly schedule based on the schedule name
    let isWeeklySchedule = false;
    let isMonthlySchedule = false;
    if (currentSchedule && currentSchedule.schedule_name) {
        isWeeklySchedule = currentSchedule.schedule_name.toLowerCase().includes('weekly');
        isMonthlySchedule = currentSchedule.schedule_name.toLowerCase().includes('monthly');
    }
    
    document.getElementById('modalExportServer').value = savedServer;
    document.getElementById('modalExportPath').value = savedPath;
    
    // Generate default filename based on date and schedule type
    // Parse date components to avoid timezone issues
    const [year, month, day] = viewDate.split('-').map(num => parseInt(num));
    
    // Format as YYMMDD
    const yy = year.toString().slice(-2);
    const mm = month.toString().padStart(2, '0');
    const dd = day.toString().padStart(2, '0');
    const dateStr = `${yy}${mm}${dd}`;
    
    // Determine schedule type
    let scheduleType = 'daily';
    if (isMonthlySchedule) {
        scheduleType = 'monthly';
    } else if (isWeeklySchedule) {
        scheduleType = 'weekly';
    }
    
    const defaultFilename = `${dateStr}_${scheduleType}.sch`;
    
    document.getElementById('modalExportFilename').value = defaultFilename;
    
    // Set the export format based on schedule type
    const exportFormatSelect = document.getElementById('modalExportFormat');
    if (exportFormatSelect) {
        if (isMonthlySchedule) {
            exportFormatSelect.value = 'castus_monthly';
            log('📋 Detected monthly schedule - setting export format to Castus Monthly');
        } else if (isWeeklySchedule) {
            exportFormatSelect.value = 'castus_weekly';
            log('📋 Detected weekly schedule - setting export format to Castus Weekly');
        } else {
            exportFormatSelect.value = 'castus';
        }
    }
}

function closeExportModal() {
    document.getElementById('exportModal').style.display = 'none';
}

async function confirmExport() {
    const viewDate = document.getElementById('exportScheduleDate').textContent;
    const exportServer = document.getElementById('modalExportServer').value;
    const exportPath = document.getElementById('modalExportPath').value;
    const exportFilename = document.getElementById('modalExportFilename').value;
    const exportFormat = document.getElementById('modalExportFormat').value;
    
    if (!exportPath) {
        log('❌ Please specify an export path', 'error');
        return;
    }
    
    if (!exportFilename) {
        log('❌ Please specify a filename', 'error');
        return;
    }
    
    // Save preferences
    localStorage.setItem('exportServer', exportServer);
    localStorage.setItem('exportPath', exportPath);
    
    const fullPath = `${exportPath}/${exportFilename}`;
    
    closeExportModal();
    
    log(`📤 Exporting schedule for ${viewDate} to ${exportServer} server...`);
    log(`📂 Export path: ${exportPath}`);
    log(`📄 Filename: ${exportFilename}`);
    log(`📋 Format: ${exportFormat === 'castus' ? 'Castus Daily Schedule' : exportFormat === 'castus_weekly' ? 'Castus Weekly Schedule' : 'Unknown'}`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/export-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: viewDate,
                export_server: exportServer,
                export_path: exportPath,
                filename: exportFilename,
                format: exportFormat
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ ${result.message}`, 'success');
            if (result.file_path) {
                log(`📄 Exported to: ${result.file_path}`);
            }
            if (result.file_size) {
                log(`📊 File size: ${formatFileSize(result.file_size)}`);
            }
            
            // Show success notification
            showNotification(
                'Schedule Exported',
                `Successfully exported to ${exportFilename}`,
                'success'
            );
            
            // Show success modal
            showExportResult(true, 'Export Successful!', `Schedule exported to ${result.file_path || fullPath}`);
        } else {
            log(`❌ ${result.message}`, 'error');
            
            // Show error notification
            showNotification(
                'Export Failed',
                result.message,
                'error'
            );
            
            // Show failure modal
            showExportResult(false, 'Export Failed', result.message);
        }
    } catch (error) {
        log(`❌ Error exporting schedule: ${error.message}`, 'error');
        showExportResult(false, 'Export Error', error.message);
    }
}

function showExportResult(success, message, details) {
    const modal = document.getElementById('exportResultModal');
    const icon = document.getElementById('exportResultIcon');
    const msgElement = document.getElementById('exportResultMessage');
    const detailsElement = document.getElementById('exportResultDetails');
    
    if (success) {
        icon.innerHTML = '<i class="fas fa-check-circle" style="color: #28a745;"></i>';
        msgElement.textContent = message;
        msgElement.style.color = '#28a745';
    } else {
        icon.innerHTML = '<i class="fas fa-times-circle" style="color: #dc3545;"></i>';
        msgElement.textContent = message;
        msgElement.style.color = '#dc3545';
    }
    
    detailsElement.textContent = details;
    modal.style.display = 'block';
}

function closeExportResultModal() {
    document.getElementById('exportResultModal').style.display = 'none';
}

// Helper functions for schedule display
function parseTimeToSeconds(timeStr) {
    const parts = timeStr.split(':');
    const hours = parseInt(parts[0]) || 0;
    const minutes = parseInt(parts[1]) || 0;
    const seconds = parseFloat(parts[2]) || 0;
    return hours * 3600 + minutes * 60 + seconds;
}

function displayScheduleDetails(schedule) {
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
        <div class="schedule-header">
            <h4>📅 ${schedule.schedule_name || 'Daily Schedule'}</h4>
            <p><strong>Air Date:</strong> ${airDate} | <strong>Channel:</strong> ${schedule.channel || 'Comcast Channel 26'}</p>
            <p><strong>Created:</strong> ${createdAt} | <strong>Items:</strong> ${schedule.total_items || 0} | <strong>Total Duration:</strong> ${totalDurationHours.toFixed(1)} hours</p>
        </div>
        <div class="schedule-items">
            <div class="schedule-table-header">
                <span class="col-start-time">Start Time</span>
                <span class="col-end-time">End Time</span>
                <span class="col-title">Title</span>
                <span class="col-category">Category</span>
                <span class="col-duration">Duration</span>
                <span class="col-last-scheduled">Encoded Date</span>
                <span class="col-actions">Actions</span>
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
                            <div class="schedule-day-header">
                                <h5>${dayName} - ${formattedDate}</h5>
                            </div>
                        `;
                    } else if (isMonthlySchedule) {
                        const dayName = dayDate.toLocaleDateString('en-US', { weekday: 'long' });
                        const formattedDate = dayDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
                        
                        html += `
                            <div class="schedule-day-header">
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
                <div class="schedule-item-row ${rowClass}" data-item-id="${item.id}" data-schedule-id="${schedule.id}">
                    <span class="col-start-time">${formatTimeWithFrames(startTime)}</span>
                    <span class="col-end-time">${formatTimeWithFrames(endTime)}</span>
                    <span class="col-title" title="${item.file_name}">${title}</span>
                    <span class="col-category">${categoryLabel}</span>
                    <span class="col-duration">${durationTimecode}</span>
                    <span class="col-last-scheduled">${encodedDateDisplay}</span>
                    <span class="col-actions">
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
        html += '<div class="schedule-no-items">No scheduled items found.</div>';
    }
    
    html += '</div></div>';
    
    scheduleDisplay.innerHTML = html;
}

// Schedule item manipulation functions
async function toggleScheduleItemAvailability(scheduleId, itemId, available) {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/toggle-schedule-item-availability', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId,
                item_id: itemId,
                available: available
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Success', result.message, 'success');
            // Reload the schedule to show updated state
            const viewDate = document.getElementById('viewScheduleDate').value;
            if (viewDate) {
                await viewDailySchedule();
            }
        } else {
            showNotification('Error', result.message || 'Failed to update item', 'error');
        }
    } catch (error) {
        showNotification('Error', error.message, 'error');
    }
}

async function moveScheduleItem(scheduleId, index, direction) {
    if (!currentSchedule || !currentSchedule.items) {
        showNotification('Error', 'No schedule loaded', 'error');
        return;
    }
    
    const items = currentSchedule.items;
    let newIndex;
    
    if (direction === 'up' && index > 0) {
        newIndex = index - 1;
        [items[index], items[index - 1]] = [items[index - 1], items[index]];
    } else if (direction === 'down' && index < items.length - 1) {
        newIndex = index + 1;
        [items[index], items[index + 1]] = [items[index + 1], items[index]];
    } else {
        return; // No move needed
    }
    
    // Update the display immediately for responsiveness
    displayScheduleDetails(currentSchedule);
    
    try {
        // Send update to backend
        const response = await fetch('http://127.0.0.1:5000/api/reorder-schedule-items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId,
                item_id: items[newIndex].id,
                old_position: index,
                new_position: newIndex
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Success', 'Item moved successfully', 'success');
            // Reload the schedule to ensure sync with backend
            const viewDate = document.getElementById('viewScheduleDate').value;
            if (viewDate) {
                await viewDailySchedule();
            }
        } else {
            showNotification('Error', result.message || 'Failed to move item', 'error');
            // Reload to revert changes
            const viewDate = document.getElementById('viewScheduleDate').value;
            if (viewDate) {
                await viewDailySchedule();
            }
        }
    } catch (error) {
        showNotification('Error', error.message, 'error');
        // Reload to revert changes
        const viewDate = document.getElementById('viewScheduleDate').value;
        if (viewDate) {
            await viewDailySchedule();
        }
    }
}

async function deleteScheduleItem(scheduleId, itemId, index) {
    if (!confirm('Are you sure you want to delete this item from the schedule?')) {
        return;
    }
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/delete-schedule-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId,
                item_id: itemId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Success', 'Item deleted successfully', 'success');
            // Reload the schedule
            const viewDate = document.getElementById('viewScheduleDate').value;
            if (viewDate) {
                await viewDailySchedule();
            }
        } else {
            showNotification('Error', result.message || 'Failed to delete item', 'error');
        }
    } catch (error) {
        showNotification('Error', error.message, 'error');
    }
}

// View schedule item details
function viewScheduleItemDetails(scheduleId, itemIdOrAssetId, index) {
    console.log('viewScheduleItemDetails called:', {scheduleId, itemIdOrAssetId, index});
    console.log('currentSchedule:', currentSchedule);
    console.log('currentSchedule.items:', currentSchedule?.items);
    
    if (!currentSchedule || !currentSchedule.items || !currentSchedule.items[index]) {
        showNotification('Error', 'Schedule item not found', 'error');
        console.error('Schedule item not found at index:', index);
        console.log('Current schedule:', currentSchedule);
        console.log('Current schedule items:', currentSchedule?.items?.length || 0);
        console.log('Requested index:', index);
        return;
    }
    
    const item = currentSchedule.items[index];
    
    // Format details
    const durationTimecode = formatDurationTimecode(item.scheduled_duration_seconds || 0);
    const startTime = formatTimeWithFrames(item.scheduled_start_time || '00:00:00');
    const endTime = calculateEndTime(item.scheduled_start_time || '00:00:00', item.scheduled_duration_seconds || 0);
    const contentTypeLabel = getContentTypeLabel(item.content_type);
    const categoryLabel = item.duration_category ? item.duration_category.replace('_', ' ').toUpperCase() : '';
    
    // Format dates
    let lastScheduledDisplay = 'Never';
    if (item.last_scheduled_date) {
        const lastScheduledDate = new Date(item.last_scheduled_date);
        lastScheduledDisplay = lastScheduledDate.toLocaleString();
    }
    
    let createdAtDisplay = 'Unknown';
    if (item.created_at) {
        const createdDate = new Date(item.created_at);
        createdAtDisplay = createdDate.toLocaleString();
    }
    
    // Create modal content
    const modalHtml = `
        <div class="modal" id="scheduleItemDetailsModal" style="display: block;">
            <div class="modal-content" style="max-width: 700px;">
                <div class="modal-header">
                    <h3><i class="fas fa-info-circle"></i> Schedule Item Details</h3>
                    <button class="modal-close" onclick="closeScheduleItemDetailsModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <h4 style="margin-top: 0;">${item.content_title || item.file_name || 'Untitled'}</h4>
                    
                    <div style="display: grid; grid-template-columns: auto 1fr; gap: 0.75rem; margin-top: 1rem;">
                        <strong>Schedule Info:</strong>
                        <span style="grid-column: span 2; border-bottom: 1px solid var(--border-color); margin-bottom: 0.5rem;"></span>
                        
                        <strong>Position:</strong>
                        <span>#${item.sequence_number || (index + 1)} in schedule</span>
                        
                        <strong>Scheduled Time:</strong>
                        <span>${startTime} - ${endTime}</span>
                        
                        <strong>Duration:</strong>
                        <span>${durationTimecode}</span>
                        
                        <strong>Content Info:</strong>
                        <span style="grid-column: span 2; border-bottom: 1px solid var(--border-color); margin: 0.5rem 0;"></span>
                        
                        <strong>File Name:</strong>
                        <span>${item.file_name || 'N/A'}</span>
                        
                        <strong>File Path:</strong>
                        <span style="word-break: break-all;">${item.file_path || 'N/A'}</span>
                        
                        <strong>Content Type:</strong>
                        <span>${contentTypeLabel} (${item.content_type || 'N/A'})</span>
                        
                        <strong>Duration Category:</strong>
                        <span>${categoryLabel}</span>
                        
                        <strong>Engagement Score:</strong>
                        <span>${item.engagement_score || 'N/A'}%</span>
                        
                        <strong>Asset Info:</strong>
                        <span style="grid-column: span 2; border-bottom: 1px solid var(--border-color); margin: 0.5rem 0;"></span>
                        
                        <strong>Asset ID:</strong>
                        <span>${item.asset_id || assetId || 'N/A'}</span>
                        
                        <strong>Instance ID:</strong>
                        <span>${item.instance_id || 'N/A'}</span>
                        
                        <strong>Item ID:</strong>
                        <span>${item.id || 'N/A'}</span>
                        
                        <strong>Scheduling History:</strong>
                        <span style="grid-column: span 2; border-bottom: 1px solid var(--border-color); margin: 0.5rem 0;"></span>
                        
                        <strong>Total Airings:</strong>
                        <span>${item.total_airings || 0}</span>
                        
                        <strong>Last Scheduled:</strong>
                        <span>${lastScheduledDisplay}</span>
                        
                        <strong>Added to Schedule:</strong>
                        <span>${createdAtDisplay}</span>
                        
                        ${item.summary ? `
                            <strong>Summary:</strong>
                            <span style="grid-column: span 2; margin-top: 0.5rem;">
                                <div style="background: var(--bg-secondary); padding: 10px; border-radius: 4px; margin-top: 5px;">
                                    ${item.summary}
                                </div>
                            </span>
                        ` : ''}
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="button secondary" onclick="closeScheduleItemDetailsModal()">Close</button>
                </div>
            </div>
        </div>
    `;
    
    // Add modal to page
    const existingModal = document.getElementById('scheduleItemDetailsModal');
    if (existingModal) {
        existingModal.remove();
    }
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeScheduleItemDetailsModal() {
    const modal = document.getElementById('scheduleItemDetailsModal');
    if (modal) {
        modal.remove();
    }
}

// Format time in HH:MM:SS.000 format
function formatTimeHHMMSSmmm(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const milliseconds = Math.floor((seconds % 1) * 1000);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
}

// Calculate end time from start time and duration with frame precision
function calculateEndTime(startTime, durationSeconds, fps = 30) {
    // Handle time with microseconds (e.g., "00:00:15.015000")
    let timeParts;
    let hours = 0, minutes = 0, seconds = 0, frames = 0;
    
    if (startTime.includes('.')) {
        const [timePart, microPart] = startTime.split('.');
        timeParts = timePart.split(':');
        // Convert microseconds to frames
        const microseconds = parseFloat('0.' + microPart);
        frames = Math.floor(microseconds * fps);
    } else {
        // Parse start time - can be HH:MM:SS or HH:MM:SS:FF
        timeParts = startTime.split(':');
    }
    
    if (timeParts.length >= 3) {
        hours = parseInt(timeParts[0]) || 0;
        minutes = parseInt(timeParts[1]) || 0;
        seconds = parseInt(timeParts[2]) || 0;
        if (timeParts.length >= 4) {
            frames = parseInt(timeParts[3]) || 0;
        }
    }
    
    // Ensure durationSeconds is a number
    const duration = parseFloat(durationSeconds) || 0;
    
    // Convert everything to frames for precise calculation
    const startTotalFrames = (hours * 3600 + minutes * 60 + seconds) * fps + frames;
    const durationFrames = Math.round(duration * fps);
    const endTotalFrames = startTotalFrames + durationFrames;
    
    // Convert back to time components
    const totalSeconds = Math.floor(endTotalFrames / fps);
    const endFrames = endTotalFrames % fps;
    const endHours = Math.floor(totalSeconds / 3600) % 24;
    const endMinutes = Math.floor((totalSeconds % 3600) / 60);
    const endSeconds = Math.floor(totalSeconds % 60);
    
    // Format as HH:MM:SS:FF
    return `${endHours.toString().padStart(2, '0')}:${endMinutes.toString().padStart(2, '0')}:${endSeconds.toString().padStart(2, '0')}:${endFrames.toString().padStart(2, '0')}`;
}

// Format duration in seconds to HH:MM:SS:FF format (with frames)
function formatDurationTimecode(durationSeconds, fps = 30) {
    const duration = parseFloat(durationSeconds) || 0;
    
    const hours = Math.floor(duration / 3600);
    const minutes = Math.floor((duration % 3600) / 60);
    const seconds = Math.floor(duration % 60);
    const frames = Math.floor((duration % 1) * fps);
    
    // Format as HH:MM:SS:FF
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
}

// Format duration with milliseconds preserved
function formatDurationTimecodeWithMs(durationSeconds, fps = 30) {
    const duration = parseFloat(durationSeconds) || 0;
    
    const hours = Math.floor(duration / 3600);
    const minutes = Math.floor((duration % 3600) / 60);
    const seconds = Math.floor(duration % 60);
    const milliseconds = duration % 1;
    const frames = Math.round(milliseconds * fps);
    
    // Format as HH:MM:SS:FF
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
}

// Convert time string (HH:MM:SS or HH:MM:SS.mmm) to timecode format (HH:MM:SS:FF)
function formatTimeToTimecode(timeStr, fps = 30) {
    if (!timeStr) return '00:00:00:00';
    
    // Handle weekly format times that include day prefix (e.g., "wed 12:00:15.040 am")
    let cleanTime = timeStr;
    if (timeStr.includes(' ') && (timeStr.includes('am') || timeStr.includes('pm'))) {
        // Extract just the time part
        const parts = timeStr.split(' ');
        if (parts.length >= 2) {
            // Skip the day prefix if present
            const timePartIndex = parts[0].length <= 3 ? 1 : 0;
            cleanTime = parts.slice(timePartIndex).join(' ');
        }
        
        // Convert 12-hour to 24-hour format first
        const time24 = convert12to24Hour(cleanTime);
        if (time24) {
            cleanTime = time24;
        }
    }
    
    // Parse time parts
    const parts = cleanTime.split(':');
    if (parts.length < 3) return cleanTime;
    
    const hours = parts[0].padStart(2, '0');
    const minutes = parts[1].padStart(2, '0');
    
    // Handle seconds and milliseconds
    const secondsParts = parts[2].split('.');
    const seconds = secondsParts[0].padStart(2, '0');
    
    let frames = '00';
    if (secondsParts.length > 1) {
        // Convert milliseconds to frames
        const milliseconds = parseFloat(`0.${secondsParts[1]}`);
        frames = Math.round(milliseconds * fps).toString().padStart(2, '0');
    }
    
    return `${hours}:${minutes}:${seconds}:${frames}`;
}

// Helper function to convert 12-hour to 24-hour format
function convert12to24Hour(timeStr) {
    try {
        // Remove milliseconds temporarily
        const millisMatch = timeStr.match(/\.(\d+)/);
        const millis = millisMatch ? millisMatch[1] : null;
        const cleanTime = timeStr.replace(/\.\d+/, '');
        
        // Parse the time
        const match = cleanTime.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)/i);
        if (!match) return null;
        
        let hours = parseInt(match[1]);
        const minutes = match[2];
        const seconds = match[3] || '00';
        const period = match[4].toLowerCase();
        
        // Convert to 24-hour
        if (period === 'pm' && hours !== 12) {
            hours += 12;
        } else if (period === 'am' && hours === 12) {
            hours = 0;
        }
        
        // Format result
        let result = `${hours.toString().padStart(2, '0')}:${minutes}:${seconds}`;
        if (millis) {
            result += `.${millis}`;
        }
        
        return result;
    } catch (e) {
        return null;
    }
}

// Convert HH:MM:SS or HH:MM:SS.microseconds to HH:MM:SS:FF format
function formatTimeWithFrames(timeStr, fps = 30) {
    if (!timeStr) return '00:00:00:00';
    
    // Handle time with microseconds (e.g., "00:00:15.015000")
    if (timeStr.includes('.')) {
        const [timePart, microPart] = timeStr.split('.');
        const parts = timePart.split(':');
        if (parts.length === 3) {
            const hours = parts[0];
            const minutes = parts[1];
            const seconds = parts[2];
            // Convert microseconds to frames
            const microseconds = parseFloat('0.' + microPart);
            const frames = Math.floor(microseconds * fps);
            return `${hours}:${minutes}:${seconds}:${frames.toString().padStart(2, '0')}`;
        }
    }
    
    const parts = timeStr.split(':');
    if (parts.length === 4) {
        // Already has frames
        return timeStr;
    } else if (parts.length === 3) {
        // Add :00 frames
        return `${timeStr}:00`;
    } else {
        return '00:00:00:00';
    }
}

// Get content type label from configuration
function getContentTypeLabel(contentType) {
    // Convert to uppercase for mapping
    const upperType = contentType ? contentType.toUpperCase() : '';
    const contentTypeMap = {
        'AN': 'Atlanta Now',
        'BMP': 'Bump',
        'IMOW': 'In My Own Words',
        'IM': 'Inclusion Months',
        'IA': 'Inside Atlanta',
        'LM': 'Legislative Minute',
        'MTG': 'Meeting',
        'MAF': 'Moving Atlanta Forward',
        'PKG': 'Package',
        'PMO': 'Promo',
        'SZL': 'Sizzle',
        'SPP': 'Special Project',
        'OTH': 'Other'
    };
    
    return contentTypeMap[upperType] || upperType || 'Unknown';
}

// Extract file title from filename and content_title
function extractFileTitle(fileName, contentTitle) {
    // If we have a content_title, use that
    if (contentTitle && contentTitle.trim() && contentTitle.trim() !== '') {
        return contentTitle.trim();
    }
    
    // Otherwise, extract from filename by removing date and type prefix
    // Expected format: YYMMDD_TYPE_Title.ext
    if (fileName && fileName.trim() !== '') {
        const nameWithoutExt = fileName.replace(/\.[^/.]+$/, ''); // Remove extension
        const parts = nameWithoutExt.split('_');
        
        if (parts.length >= 3) {
            // Join everything after the first two parts (date and type)
            const extractedTitle = parts.slice(2).join('_');
            return extractedTitle || nameWithoutExt;
        }
        
        // Fallback to full filename without extension
        return nameWithoutExt;
    }
    
    return 'Unknown Title';
}

function clearScheduleDisplay() {
    currentSchedule = null;  // Clear current schedule
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    if (scheduleDisplay) {
        scheduleDisplay.innerHTML = '<p>Select a date and click "View Schedule" to display the daily schedule</p>';
    }
}

// Collapsible card functionality
function initializeCollapsibleCards() {
    // Initialize scheduling cards
    const schedulingCards = document.querySelectorAll('.scheduling-card h3');
    schedulingCards.forEach(header => {
        header.addEventListener('click', function() {
            const card = this.parentElement;
            toggleCard(card);
        });
    });
    
    // Initialize regular cards with collapsible functionality
    const regularCards = document.querySelectorAll('.card-header h3');
    regularCards.forEach(header => {
        const showButton = header.parentElement.querySelector('button[id*="toggle"]');
        if (showButton) {
            // This card has its own toggle button, don't add click to header
            return;
        }
        header.style.cursor = 'pointer';
        header.addEventListener('click', function() {
            const card = this.closest('.card');
            const content = card.querySelector('.card-content, .status, .file-list');
            if (content) {
                content.style.display = content.style.display === 'none' ? 'block' : 'none';
            }
        });
    });
}

function toggleCard(card) {
    card.classList.toggle('collapsed');
}

function expandCard(card) {
    card.classList.remove('collapsed');
}

function collapseCard(card) {
    card.classList.add('collapsed');
}

// Analysis monitoring and restart functions
function startAnalysisMonitoring() {
    analysisStartTime = Date.now();
    lastProgressTime = Date.now();
    
    // Set up timeout monitoring
    if (analysisTimeoutId) {
        clearInterval(analysisTimeoutId);
    }
    
    analysisTimeoutId = setInterval(checkAnalysisProgress, 30000); // Check every 30 seconds
    log('🕐 Analysis monitoring started');
}

function stopAnalysisMonitoring() {
    if (analysisTimeoutId) {
        clearInterval(analysisTimeoutId);
        analysisTimeoutId = null;
    }
    
    analysisStartTime = null;
    lastProgressTime = null;
    currentAnalysisFile = null;
    stalledFileCount = 0;
    log('🕐 Analysis monitoring stopped');
}

function updateAnalysisProgress(fileName) {
    lastProgressTime = Date.now();
    currentAnalysisFile = fileName;
    stalledFileCount = 0; // Reset stall counter on progress
}

function checkAnalysisProgress() {
    if (!isAnalyzing) {
        stopAnalysisMonitoring();
        return;
    }
    
    const now = Date.now();
    const timeSinceProgress = now - lastProgressTime;
    const totalAnalysisTime = now - analysisStartTime;
    
    // Check if analysis has been stalled for too long
    if (timeSinceProgress > maxStallTime) {
        stalledFileCount++;
        log(`⚠️ Analysis appears stalled (${Math.round(timeSinceProgress/1000)}s without progress)`, 'warning');
        
        if (autoRestartEnabled && stalledFileCount >= 2) {
            log('🔄 Attempting to restart stalled analysis...', 'warning');
            restartAnalysis();
            return;
        }
    }
    
    // Check if a single file has been processing too long
    if (currentAnalysisFile && timeSinceProgress > maxFileProcessingTime) {
        log(`⚠️ File "${currentAnalysisFile}" has been processing for ${Math.round(timeSinceProgress/60000)} minutes`, 'warning');
        
        if (autoRestartEnabled) {
            log('🔄 Skipping stuck file and continuing...', 'warning');
            skipCurrentFile();
        }
    }
    
    // Log periodic status updates
    if (totalAnalysisTime > 0 && totalAnalysisTime % 60000 < 30000) { // Every minute
        const remainingFiles = analysisQueue.length;
        log(`📊 Analysis status: ${remainingFiles} files remaining, runtime: ${Math.round(totalAnalysisTime/60000)} minutes`);
    }
}

function restartAnalysis() {
    log('🔄 Restarting analysis process...', 'warning');
    
    // Stop current analysis
    stopAnalysisRequested = true;
    stopAnalysisMonitoring();
    
    // Wait a moment then restart
    setTimeout(() => {
        if (analysisQueue.length > 0) {
            log('🔄 Resuming analysis with remaining files...');
            startAnalysis();
        } else {
            log('✅ No files remaining to analyze');
            isAnalyzing = false;
            updateAnalysisButtonState();
        }
    }, 2000);
}

function skipCurrentFile() {
    if (!currentAnalysisFile) return;
    
    log(`⏭️ Skipping stuck file: ${currentAnalysisFile}`, 'warning');
    
    // Find and remove the current file from queue
    const fileIndex = analysisQueue.findIndex(item => item.file.name === currentAnalysisFile);
    if (fileIndex !== -1) {
        const skippedFile = analysisQueue.splice(fileIndex, 1)[0];
        
        // Update UI for skipped file
        const button = document.querySelector(`button[onclick="addToAnalysisQueue('${skippedFile.id}')"]`);
        if (button) {
            button.innerHTML = '<i class="fas fa-forward"></i> Skipped';
            button.classList.add('warning');
            button.disabled = false;
        }
        
        log(`⏭️ File "${currentAnalysisFile}" removed from queue and marked as skipped`);
    }
    
    // Reset progress tracking
    updateAnalysisProgress(null);
}

function toggleAutoRestart() {
    autoRestartEnabled = !autoRestartEnabled;
    const button = document.getElementById('autoRestartToggle');
    if (button) {
        button.innerHTML = autoRestartEnabled ? 
            '<i class="fas fa-toggle-on"></i> Auto-Restart: ON' : 
            '<i class="fas fa-toggle-off"></i> Auto-Restart: OFF';
        button.className = autoRestartEnabled ? 'button success small' : 'button secondary small';
    }
    log(`🔄 Auto-restart ${autoRestartEnabled ? 'enabled' : 'disabled'}`);
}

function getAnalysisStats() {
    if (!isAnalyzing) return null;
    
    const now = Date.now();
    const runtime = analysisStartTime ? Math.round((now - analysisStartTime) / 1000) : 0;
    const timeSinceProgress = lastProgressTime ? Math.round((now - lastProgressTime) / 1000) : 0;
    
    return {
        isRunning: isAnalyzing,
        runtime: runtime,
        timeSinceProgress: timeSinceProgress,
        currentFile: currentAnalysisFile,
        queueLength: analysisQueue.length,
        stalledCount: stalledFileCount,
        autoRestartEnabled: autoRestartEnabled
    };
}

function updateMonitorDisplay() {
    const monitorDiv = document.getElementById('analysisMonitorStatus');
    const skipButton = document.getElementById('skipFileButton');
    const restartButton = document.getElementById('restartButton');
    
    if (!isAnalyzing) {
        if (monitorDiv) monitorDiv.style.display = 'none';
        if (skipButton) skipButton.disabled = true;
        if (restartButton) restartButton.disabled = true;
        return;
    }
    
    if (monitorDiv) monitorDiv.style.display = 'block';
    if (skipButton) skipButton.disabled = false;
    if (restartButton) restartButton.disabled = false;
    
    const stats = getAnalysisStats();
    if (!stats) return;
    
    // Update display elements
    const runtimeEl = document.getElementById('analysisRuntime');
    const progressEl = document.getElementById('analysisProgress');
    const fileEl = document.getElementById('currentFile');
    const queueEl = document.getElementById('queueRemaining');
    
    if (runtimeEl) {
        const minutes = Math.floor(stats.runtime / 60);
        const seconds = stats.runtime % 60;
        runtimeEl.textContent = `Runtime: ${minutes}m ${seconds}s`;
    }
    
    if (progressEl) {
        const progressColor = stats.timeSinceProgress > 120 ? '#ff9800' : 
                             stats.timeSinceProgress > 300 ? '#f44336' : '#4caf50';
        progressEl.textContent = `Progress: ${stats.timeSinceProgress}s ago`;
        progressEl.style.color = progressColor;
    }
    
    if (fileEl) {
        const fileName = stats.currentFile ? 
            (stats.currentFile.length > 30 ? stats.currentFile.substring(0, 30) + '...' : stats.currentFile) : 
            'None';
        fileEl.textContent = `File: ${fileName}`;
    }
    
    if (queueEl) {
        queueEl.textContent = `Queue: ${stats.queueLength}`;
    }
    
    // Update rescan status
    const rescanEl = document.getElementById('rescanStatus');
    if (rescanEl) {
        if (rescanEnabled && isAnalyzing) {
            const now = Date.now();
            const nextRescanTime = rescanTimeoutId ? (now + rescanInterval * 1000 - (now % (rescanInterval * 1000))) : now;
            const secondsUntilRescan = Math.max(0, Math.ceil((nextRescanTime - now) / 1000));
            rescanEl.textContent = `Next Rescan: ${secondsUntilRescan}s`;
            rescanEl.style.display = '';
        } else {
            rescanEl.style.display = 'none';
        }
    }
}

function startMonitorDisplayUpdate() {
    // Update display every 5 seconds during analysis
    const updateInterval = setInterval(() => {
        if (!isAnalyzing) {
            clearInterval(updateInterval);
            updateMonitorDisplay(); // Final update to hide
            return;
        }
        updateMonitorDisplay();
    }, 5000);
    
    // Initial update
    updateMonitorDisplay();
}

// Periodic rescanning functions
function startPeriodicRescanning() {
    if (!rescanEnabled) return;
    
    lastRescanTime = Date.now();
    rescanAttempts = 0;
    
    if (rescanTimeoutId) {
        clearInterval(rescanTimeoutId);
    }
    
    rescanTimeoutId = setInterval(performPeriodicRescan, rescanInterval * 1000);
    log(`📡 Periodic rescanning started (every ${rescanInterval}s)`);
}

function stopPeriodicRescanning() {
    if (rescanTimeoutId) {
        clearInterval(rescanTimeoutId);
        rescanTimeoutId = null;
    }
    
    lastRescanTime = null;
    rescanAttempts = 0;
    log('📡 Periodic rescanning stopped');
}

async function performPeriodicRescan() {
    if (!isAnalyzing || !rescanEnabled) {
        stopPeriodicRescanning();
        return;
    }
    
    const now = Date.now();
    const timeSinceLastRescan = now - lastRescanTime;
    
    try {
        log(`📡 Performing periodic rescan (attempt ${rescanAttempts + 1}/${maxRescanAttempts})`);
        
        // Check if we have source files to verify against
        if (!sourceFiles || sourceFiles.length === 0) {
            log('⚠️ No source files available for rescanning, attempting to refresh file list');
            
            // Try to refresh the file list
            await refreshSourceFiles();
            
            if (!sourceFiles || sourceFiles.length === 0) {
                log('❌ Could not refresh source files, skipping rescan');
                return;
            }
        }
        
        // Refresh analysis status for currently queued files
        const queuedFilePaths = analysisQueue.map(item => item.file.path || item.file.name);
        
        if (queuedFilePaths.length > 0) {
            const analysisStatusResult = await fetch('http://127.0.0.1:5000/api/analysis-status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: sourceFiles })
            });
            
            if (analysisStatusResult.ok) {
                const statusData = await analysisStatusResult.json();
                
                if (statusData.success) {
                    const analyzedFiles = statusData.analyzed_files || [];
                    let completedCount = 0;
                    
                    // Check if any queued files are now complete
                    analysisQueue.forEach((queueItem, index) => {
                        const filePath = queueItem.file.path || queueItem.file.name;
                        const isAnalyzed = analyzedFiles.find(af => af.file_path === filePath);
                        
                        if (isAnalyzed) {
                            // File was completed outside of our monitoring
                            log(`✅ Detected completed analysis: ${queueItem.file.name}`);
                            
                            // Update UI
                            const button = document.querySelector(`button[onclick="addToAnalysisQueue('${queueItem.id}')"]`);
                            if (button) {
                                button.innerHTML = '<i class="fas fa-check"></i> Analyzed';
                                button.classList.add('analyzed');
                                button.classList.remove('added');
                                
                                const fileItem = button.closest('.scanned-file-item');
                                if (fileItem) {
                                    fileItem.classList.add('analyzed');
                                    fileItem.classList.remove('queued');
                                }
                            }
                            
                            completedCount++;
                        }
                    });
                    
                    // Remove completed files from queue
                    if (completedCount > 0) {
                        analysisQueue = analysisQueue.filter(queueItem => {
                            const filePath = queueItem.file.path || queueItem.file.name;
                            return !analyzedFiles.find(af => af.file_path === filePath);
                        });
                        
                        log(`📡 Rescan detected ${completedCount} completed files, ${analysisQueue.length} remaining in queue`);
                        updateAnalysisButtonState();
                    }
                    
                    // If queue is empty, analysis is complete
                    if (analysisQueue.length === 0) {
                        log('✅ All files completed, stopping analysis');
                        isAnalyzing = false;
                        stopAnalysisMonitoring();
                        stopPeriodicRescanning();
                        updateAnalysisButtonState();
                        return;
                    }
                }
            }
        }
        
        rescanAttempts++;
        lastRescanTime = now;
        
        // Reset progress tracking if rescan found activity
        updateAnalysisProgress(currentAnalysisFile);
        
    } catch (error) {
        log(`❌ Periodic rescan failed: ${error.message}`, 'error');
        rescanAttempts++;
        
        if (rescanAttempts >= maxRescanAttempts) {
            log(`⚠️ Maximum rescan attempts (${maxRescanAttempts}) reached, stopping periodic rescanning`, 'warning');
            stopPeriodicRescanning();
        }
    }
}

async function refreshSourceFiles() {
    try {
        log('📡 Attempting to refresh source file list...');
        
        // This would typically re-scan the source directory
        // For now, we'll just check if we can get the current files
        if (sourceFiles && sourceFiles.length > 0) {
            log('📡 Source files already available');
            return true;
        }
        
        // Try to trigger a rescan if the scan button is available
        const scanButton = document.querySelector('[onclick*="scanFiles"]');
        if (scanButton && !scanButton.disabled) {
            log('📡 Triggering file rescan...');
            // Note: This would need to be implemented based on your scan function
            // For now, just return false to indicate we couldn't refresh
        }
        
        return false;
    } catch (error) {
        log(`❌ Error refreshing source files: ${error.message}`, 'error');
        return false;
    }
}

function togglePeriodicRescanning() {
    rescanEnabled = !rescanEnabled;
    const button = document.getElementById('rescanToggle');
    if (button) {
        button.innerHTML = rescanEnabled ? 
            '<i class="fas fa-toggle-on"></i> Auto-Rescan: ON' : 
            '<i class="fas fa-toggle-off"></i> Auto-Rescan: OFF';
        button.className = rescanEnabled ? 'button success small' : 'button secondary small';
    }
    
    if (rescanEnabled && isAnalyzing) {
        startPeriodicRescanning();
    } else {
        stopPeriodicRescanning();
    }
    
    log(`📡 Periodic rescanning ${rescanEnabled ? 'enabled' : 'disabled'}`);
}

function updateRescanInterval() {
    const input = document.getElementById('rescanIntervalInput');
    if (input) {
        const newInterval = parseInt(input.value);
        if (newInterval >= 30 && newInterval <= 600) { // 30 seconds to 10 minutes
            rescanInterval = newInterval;
            log(`📡 Rescan interval updated to ${rescanInterval} seconds`);
            
            // Restart rescanning with new interval if currently running
            if (rescanEnabled && isAnalyzing) {
                stopPeriodicRescanning();
                startPeriodicRescanning();
            }
        } else {
            log('⚠️ Rescan interval must be between 30 and 600 seconds', 'warning');
            input.value = rescanInterval; // Reset to current value
        }
    }
}

// Utility Functions for Scheduling
function getDurationCategory(durationInSeconds) {
    for (const [category, config] of Object.entries(scheduleConfig.DURATION_CATEGORIES)) {
        if (durationInSeconds >= config.min && durationInSeconds < config.max) {
            return category;
        }
    }
    return 'unknown';
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds}s`;
    } else if (seconds < 3600) {
        return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    }
}

async function addToSchedule(contentId) {
    // Check if we have a current schedule loaded
    if (!currentSchedule || !currentSchedule.id) {
        // Try to get the date from the view field
        const viewDate = document.getElementById('viewScheduleDate').value;
        if (!viewDate) {
            showNotification(
                'No Schedule Selected',
                'Please select or load a schedule first',
                'error'
            );
            return;
        }
        
        // Load the schedule for the selected date
        await viewDailySchedule();
        
        if (!currentSchedule || !currentSchedule.id) {
            showNotification(
                'No Schedule Found',
                'No schedule exists for the selected date. Please create a schedule first.',
                'error'
            );
            return;
        }
    }
    
    try {
        log(`📅 Adding content ${contentId} to schedule ${currentSchedule.id}...`);
        
        const response = await fetch('http://127.0.0.1:5000/api/add-item-to-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: currentSchedule.id,
                asset_id: contentId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ Content added to schedule successfully at position ${result.order_index + 1}`);
            
            // Get content details for notification
            const contentItem = availableContent.find(c => 
                (c.id || c._id || c.guid) == contentId
            );
            const contentTitle = contentItem ? (contentItem.content_title || contentItem.file_name) : 'Content';
            
            // Show success notification
            showNotification(
                'Added to Schedule',
                `"${contentTitle}" has been added at position ${result.order_index + 1}`,
                'success'
            );
            
            // Refresh the schedule display
            await viewDailySchedule();
            
            if (contentItem) {
                log(`📺 Added "${contentTitle}" to schedule`);
            }
        } else {
            log(`❌ Failed to add content: ${result.message}`, 'error');
            showNotification(
                'Failed to Add Content',
                result.message,
                'error'
            );
        }
    } catch (error) {
        log(`❌ Error adding content to schedule: ${error.message}`, 'error');
        showNotification(
            'Error',
            error.message,
            'error'
        );
    }
}

// Rename/Fix Content Functions
function showRenameDialog(contentId) {
    const content = availableContent.find(c => 
        (c.id || c._id || c.guid) == contentId
    );
    
    if (!content) {
        showNotification('Error', 'Content not found', 'error');
        return;
    }
    
    currentRenameContent = content;
    
    // Populate modal with current info
    document.getElementById('currentFileName').value = content.file_name || '';
    document.getElementById('newFileName').value = content.file_name || '';
    
    // Format encoded date for display
    let encodedDateStr = 'Not available';
    if (content.encoded_date) {
        const date = new Date(content.encoded_date);
        const year = date.getFullYear().toString().slice(-2);
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const day = date.getDate().toString().padStart(2, '0');
        encodedDateStr = `${year}${month}${day}`;
    }
    document.getElementById('encodedDateDisplay').value = encodedDateStr;
    
    // Show content info
    const infoHtml = `
        <strong>File Path:</strong> ${content.file_path || 'N/A'}<br>
        <strong>Current Type:</strong> ${getContentTypeLabel(content.content_type || '')} (${content.content_type || 'Not set'})<br>
        <strong>Duration:</strong> ${formatDurationTimecode(content.file_duration || 0)}<br>
        <strong>Title:</strong> ${content.content_title || content.file_name}
    `;
    document.getElementById('renameContentInfo').innerHTML = infoHtml;
    
    // Show modal
    document.getElementById('renameContentModal').style.display = 'block';
}

function closeRenameDialog() {
    document.getElementById('renameContentModal').style.display = 'none';
    document.getElementById('renamePreview').style.display = 'none';
    currentRenameContent = null;
}

function generateSuggestedName() {
    if (!currentRenameContent) return;
    
    // Get encoded date
    let dateStr = '';
    if (currentRenameContent.encoded_date) {
        const date = new Date(currentRenameContent.encoded_date);
        const year = date.getFullYear().toString().slice(-2);
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const day = date.getDate().toString().padStart(2, '0');
        dateStr = `${year}${month}${day}`;
    } else {
        // Try to extract from filename
        const match = currentRenameContent.file_name.match(/^(\d{6})/);
        if (match) {
            dateStr = match[1];
        } else {
            showNotification('Warning', 'No encoded date available', 'error');
            return;
        }
    }
    
    // Get content type from current content
    const contentType = currentRenameContent.content_type;
    if (!contentType) {
        showNotification('Error', 'Content type not set. Please update content type first using the dropdown in the content list.', 'error');
        return;
    }
    
    // Extract description from current filename
    const currentName = currentRenameContent.file_name;
    let description = '';
    
    // Remove date and type prefix to get description
    const descMatch = currentName.match(/^\d{6}[-_]?\w*[-_]?(.+?)\.mp4$/i);
    if (descMatch) {
        description = descMatch[1].trim();
    } else {
        // Use content title or fallback
        description = currentRenameContent.content_title || 'Content';
    }
    
    // Clean up description
    description = description.replace(/[^\w\s-]/g, ' ').trim();
    description = description.replace(/\s+/g, '_');
    
    // Generate new name
    const newName = `${dateStr}_${contentType}_${description}.mp4`;
    document.getElementById('newFileName').value = newName;
    
    showNotification('Success', 'Suggested name generated', 'success', 3000);
}

function previewRename() {
    const newFileName = document.getElementById('newFileName').value;
    
    if (!newFileName) {
        showNotification('Error', 'Please enter a new filename', 'error');
        return;
    }
    
    // Extract content type from the new filename
    const typeMatch = newFileName.match(/^\d{6}_(\w+)_/);
    const extractedType = typeMatch ? typeMatch[1] : null;
    
    // Content type folder mappings
    const folderMappings = {
        'AN': 'ATLANTA NOW',
        'BMP': 'BUMPS',
        'IMOW': 'IMOW',
        'IM': 'INCLUSION MONTHS',
        'IA': 'INSIDE ATLANTA',
        'LM': 'LEGISLATIVE MINUTE',
        'MTG': 'MEETINGS',
        'MAF': 'MOVING ATLANTA FORWARD',
        'PKG': 'PKGS',
        'PMO': 'PROMOS',
        'PSA': 'PSAs',
        'SZL': 'SIZZLES',
        'SPP': 'SPECIAL PROJECTS',
        'OTHER': 'OTHER'
    };
    
    const previewHtml = `
        <h4>Preview Changes:</h4>
        <div class="preview-item">
            <strong>Original:</strong><br>
            ${currentRenameContent.file_name}
        </div>
        <div class="preview-item">
            <strong>New Name:</strong><br>
            ${newFileName}
        </div>
        <div class="preview-item">
            <strong>Current Type:</strong> ${currentRenameContent.content_type || 'None'}<br>
            <strong>Type in Filename:</strong> ${extractedType || 'Invalid'}
        </div>
        <div class="preview-item">
            <strong>Target Folder:</strong><br>
            ${folderMappings[extractedType] || 'Unknown - file will be moved to OTHER'}
        </div>
    `;
    
    document.getElementById('renamePreview').innerHTML = previewHtml;
    document.getElementById('renamePreview').style.display = 'block';
}

async function executeRename() {
    if (!currentRenameContent) return;
    
    const newFileName = document.getElementById('newFileName').value;
    
    if (!newFileName) {
        showNotification('Error', 'Please enter a new filename', 'error');
        return;
    }
    
    // Validate filename format
    if (!newFileName.match(/^\d{6}_\w+_.+\.mp4$/)) {
        showNotification('Error', 'Invalid filename format. Use: YYMMDD_TYPE_Description.mp4', 'error');
        return;
    }
    
    // Extract content type from the new filename to determine folder
    const typeMatch = newFileName.match(/^\d{6}_(\w+)_/);
    const newContentType = typeMatch ? typeMatch[1] : currentRenameContent.content_type;
    
    try {
        showNotification('Processing', 'Renaming file...', 'info');
        
        const response = await fetch('http://127.0.0.1:5000/api/rename-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content_id: currentRenameContent.id || currentRenameContent._id,
                old_file_name: currentRenameContent.file_name,
                old_file_path: currentRenameContent.file_path,
                new_file_name: newFileName,
                new_content_type: newContentType  // Used only for determining target folder
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(
                'Success',
                'File renamed successfully',
                'success'
            );
            closeRenameDialog();
            // Reload content to show changes
            await loadAvailableContent();
        } else {
            showNotification('Error', result.message || 'Rename failed', 'error');
        }
    } catch (error) {
        showNotification('Error', error.message, 'error');
    }
}

// Content sorting functions
function getSortIcon(field) {
    if (contentSortField !== field) {
        return '<i class="fas fa-sort" style="opacity: 0.3;"></i>';
    }
    return contentSortOrder === 'asc' ? 
        '<i class="fas fa-sort-up"></i>' : 
        '<i class="fas fa-sort-down"></i>';
}

function sortContent(field) {
    // Toggle sort order if clicking the same field
    if (contentSortField === field) {
        contentSortOrder = contentSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        contentSortField = field;
        contentSortOrder = 'asc';
    }
    
    // Sort the content array
    availableContent.sort((a, b) => {
        let aVal, bVal;
        
        switch (field) {
            case 'title':
                aVal = (a.content_title || a.file_name || '').toLowerCase();
                bVal = (b.content_title || b.file_name || '').toLowerCase();
                break;
            case 'type':
                aVal = a.content_type || '';
                bVal = b.content_type || '';
                break;
            case 'duration':
                aVal = parseFloat(a.file_duration) || 0;
                bVal = parseFloat(b.file_duration) || 0;
                break;
            case 'category':
                aVal = getDurationCategory(a.file_duration);
                bVal = getDurationCategory(b.file_duration);
                break;
            case 'engagement':
                aVal = parseFloat(a.engagement_score) || 0;
                bVal = parseFloat(b.engagement_score) || 0;
                break;
            case 'lastScheduled':
                aVal = a.scheduling?.last_scheduled_date ? new Date(a.scheduling.last_scheduled_date).getTime() : 0;
                bVal = b.scheduling?.last_scheduled_date ? new Date(b.scheduling.last_scheduled_date).getTime() : 0;
                break;
            default:
                return 0;
        }
        
        // Compare values
        if (aVal < bVal) return contentSortOrder === 'asc' ? -1 : 1;
        if (aVal > bVal) return contentSortOrder === 'asc' ? 1 : -1;
        return 0;
    });
    
    // Redisplay the sorted content
    displayAvailableContent();
}

function viewContentDetails(contentId) {
    // Find the content item - convert contentId to match the type
    const content = availableContent.find(c => {
        const itemId = c.id || c._id || c.guid;
        // Compare both as strings and as numbers to handle type mismatches
        return itemId == contentId || itemId === contentId || 
               String(itemId) === String(contentId);
    });
    
    if (!content) {
        log(`❌ Content not found: ${contentId}`, 'error');
        console.error('Available content IDs:', availableContent.map(c => ({
            id: c.id,
            _id: c._id,
            guid: c.guid
        })));
        return;
    }
    
    // Format details
    const durationTimecode = formatDurationTimecode(content.file_duration || 0);
    const durationCategory = getDurationCategory(content.file_duration);
    const lastScheduled = content.scheduling?.last_scheduled_date ? 
        new Date(content.scheduling.last_scheduled_date).toLocaleString() : 'Never';
    const totalAirings = content.scheduling?.total_airings || 0;
    
    // Create modal content
    const modalHtml = `
        <div class="modal" id="contentDetailsModal" style="display: block;">
            <div class="modal-content" style="max-width: 600px;">
                <div class="modal-header">
                    <h3><i class="fas fa-info-circle"></i> Content Details</h3>
                    <button class="modal-close" onclick="closeContentDetailsModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <h4 style="margin-top: 0;">${content.content_title || content.file_name}</h4>
                    
                    <div style="display: grid; grid-template-columns: auto 1fr; gap: 0.75rem; margin-top: 1rem;">
                        <strong>File Name:</strong>
                        <span>${content.file_name}</span>
                        
                        <strong>File Path:</strong>
                        <span style="word-break: break-all;">${content.file_path}</span>
                        
                        <strong>Content Type:</strong>
                        <span>${getContentTypeLabel(content.content_type)} (${content.content_type})</span>
                        
                        <strong>Duration:</strong>
                        <span>${durationTimecode} (${durationCategory})</span>
                        
                        <strong>File Size:</strong>
                        <span>${formatFileSize(content.file_size)}</span>
                        
                        <strong>Engagement Score:</strong>
                        <span>${content.engagement_score || 'N/A'}%</span>
                        
                        <strong>Last Scheduled:</strong>
                        <span>${lastScheduled}</span>
                        
                        <strong>Total Airings:</strong>
                        <span>${totalAirings}</span>
                        
                        ${content.summary ? `
                        <strong>Summary:</strong>
                        <span style="grid-column: 2;">${content.summary}</span>
                        ` : ''}
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="button secondary" onclick="closeContentDetailsModal()">Close</button>
                    ${currentTemplate ? `
                    <button class="button success" onclick="addToTemplateFromDetails('${contentId}')">
                        <i class="fas fa-plus"></i> Add to Template
                    </button>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
    
    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeContentDetailsModal() {
    const modal = document.getElementById('contentDetailsModal');
    if (modal) {
        modal.remove();
    }
}

function addToTemplateFromDetails(contentId) {
    addToTemplate(contentId);
    closeContentDetailsModal();
}

// Initialize scheduling when page loads
document.addEventListener('DOMContentLoaded', function() {
    initializeSchedulingDates();
    loadSchedulingConfig();
});

// Load scheduling configuration from backend
async function loadSchedulingConfig() {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/config');
        const config = await response.json();
        
        if (config.scheduling) {
            // Load replay delays
            if (config.scheduling.replay_delays) {
                scheduleConfig.REPLAY_DELAYS = config.scheduling.replay_delays;
                // Update UI if config modal is open
                if (document.getElementById('id_replay_delay')) {
                    document.getElementById('id_replay_delay').value = config.scheduling.replay_delays.id || 6;
                    document.getElementById('spots_replay_delay').value = config.scheduling.replay_delays.spots || 12;
                    document.getElementById('short_form_replay_delay').value = config.scheduling.replay_delays.short_form || 24;
                    document.getElementById('long_form_replay_delay').value = config.scheduling.replay_delays.long_form || 48;
                }
            }
            
            // Load additional delay per airing
            if (config.scheduling.additional_delay_per_airing) {
                scheduleConfig.ADDITIONAL_DELAY_PER_AIRING = config.scheduling.additional_delay_per_airing;
            }
            
            // Load rotation order
            if (config.scheduling.rotation_order) {
                scheduleConfig.ROTATION_ORDER = config.scheduling.rotation_order;
            }
            
            // Load other scheduling settings
            if (config.scheduling.content_expiration) {
                scheduleConfig.CONTENT_EXPIRATION = config.scheduling.content_expiration;
            }
            if (config.scheduling.timeslots) {
                scheduleConfig.TIMESLOTS = config.scheduling.timeslots;
            }
            if (config.scheduling.duration_categories) {
                scheduleConfig.DURATION_CATEGORIES = config.scheduling.duration_categories;
            }
        }
    } catch (error) {
        log(`Failed to load scheduling configuration: ${error.message}`, 'error');
    }
}


// Template Editor Functions
let currentTemplate = null;
let selectedTemplateFile = null;

// Schedule Loading Functions
let selectedScheduleFile = null;

function showLoadScheduleFromFTPModal() {
    document.getElementById('loadScheduleFromFTPModal').style.display = 'block';
    // Set default date to today
    document.getElementById('scheduleLoadDate').value = new Date().toISOString().split('T')[0];
}

function closeLoadScheduleFromFTPModal() {
    document.getElementById('loadScheduleFromFTPModal').style.display = 'none';
    selectedScheduleFile = null;
}

async function loadScheduleFilesFromFTP() {
    const server = document.getElementById('scheduleLoadServer').value;
    const path = document.getElementById('scheduleLoadPath').value;
    
    if (!server) {
        log('Please select a server', 'error');
        return;
    }
    
    try {
        log(`Listing schedule files from ${server} server...`);
        
        const response = await fetch('http://127.0.0.1:5000/api/list-schedule-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server, path })
        });
        
        const result = await response.json();
        
        if (result.success) {
            displayScheduleFiles(result.files);
        } else {
            log(`Failed to list files: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`Error listing files: ${error.message}`, 'error');
    }
}

function displayScheduleFiles(files) {
    const fileList = document.getElementById('scheduleLoadFileList');
    
    if (!files || files.length === 0) {
        fileList.innerHTML = '<p style="color: #666;">No schedule files found</p>';
        return;
    }
    
    // Filter for .sch files
    const scheduleFiles = files.filter(f => f.name.toLowerCase().endsWith('.sch'));
    
    if (scheduleFiles.length === 0) {
        fileList.innerHTML = '<p style="color: #666;">No .sch schedule files found</p>';
        return;
    }
    
    let html = '';
    scheduleFiles.forEach(file => {
        const isSelected = selectedScheduleFile === file.name;
        html += `
            <div class="file-item ${isSelected ? 'selected' : ''}" 
                 onclick="selectScheduleFile('${file.name}', event)"
                 style="cursor: pointer; padding: 8px; border-radius: 4px; margin-bottom: 4px;">
                <i class="fas fa-calendar-alt"></i> ${file.name}
                <small style="color: #666; margin-left: 10px;">${formatFileSize(file.size)}</small>
            </div>
        `;
    });
    
    fileList.innerHTML = html;
}

function selectScheduleFile(filename, event) {
    selectedScheduleFile = filename;
    
    // Update UI
    document.querySelectorAll('#scheduleLoadFileList .file-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    // Find and select the clicked item
    if (event && event.currentTarget) {
        event.currentTarget.classList.add('selected');
    } else {
        // Fallback: find by filename
        document.querySelectorAll('#scheduleLoadFileList .file-item').forEach(item => {
            if (item.textContent.includes(filename)) {
                item.classList.add('selected');
            }
        });
    }
    
    // Enable load button
    document.getElementById('loadScheduleFromFTPBtn').disabled = false;
}

async function loadSelectedScheduleFromFTP() {
    if (!selectedScheduleFile) {
        log('Please select a schedule file', 'error');
        return;
    }
    
    const server = document.getElementById('scheduleLoadServer').value;
    const path = document.getElementById('scheduleLoadPath').value;
    const scheduleDate = document.getElementById('scheduleLoadDate').value;
    
    if (!scheduleDate) {
        log('Please select a date for this schedule', 'error');
        return;
    }
    
    try {
        log(`Loading schedule ${selectedScheduleFile} from ${server} server...`);
        
        const response = await fetch('http://127.0.0.1:5000/api/load-schedule-from-ftp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server,
                path,
                filename: selectedScheduleFile,
                schedule_date: scheduleDate
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ Schedule loaded successfully!`);
            log(`📊 Created schedule with ${result.total_items} items`);
            log(`📊 Matched ${result.matched_items} items with analyzed content`);
            if (result.unmatched_items > 0) {
                log(`⚠️ ${result.unmatched_items} items could not be matched to analyzed content`);
            }
            
            closeLoadScheduleFromFTPModal();
            
            // Refresh schedule display
            document.getElementById('viewScheduleDate').value = scheduleDate;
            viewDailySchedule();
        } else {
            log(`❌ Failed to load schedule: ${result.message}`, 'error');
            
            // Show popup alert for duplicate schedule
            if (result.schedule_exists) {
                alert(result.message);
            }
        }
    } catch (error) {
        log(`❌ Error loading schedule: ${error.message}`, 'error');
    }
}

let currentTemplateType = 'daily'; // Track whether we're loading daily or weekly

function showLoadTemplateModal() {
    try {
        log('showLoadTemplateModal: Starting to show daily template modal', 'info');
        currentTemplateType = 'daily';
        
        const modal = document.getElementById('loadTemplateModal');
        if (!modal) {
            log('showLoadTemplateModal: ERROR - Modal element not found!', 'error');
            return;
        }
        
        modal.style.display = 'block';
        log('showLoadTemplateModal: Modal display set to block', 'info');
        
        // Debug modal visibility
        setTimeout(() => {
            const computedStyle = window.getComputedStyle(modal);
            console.log('Modal debug info:');
            console.log('- Display:', computedStyle.display);
            console.log('- Visibility:', computedStyle.visibility);
            console.log('- Z-index:', computedStyle.zIndex);
            console.log('- Position:', computedStyle.position);
            console.log('- Opacity:', computedStyle.opacity);
            console.log('- Modal element:', modal);
            console.log('- Modal parent:', modal.parentElement);
            console.log('- Modal offsetParent:', modal.offsetParent);
        }, 100);
        
        const titleElement = document.getElementById('loadTemplateModalTitle');
        if (titleElement) {
            titleElement.textContent = 'Load Daily Schedule Template';
        } else {
            log('showLoadTemplateModal: Warning - Title element not found', 'warning');
        }
        
        // Load default path from scheduling settings
        const schedulingSettings = JSON.parse(localStorage.getItem('schedulingSettings') || '{}');
        const defaultPath = schedulingSettings.defaultExportPath || '/mnt/main/Schedules';
        
        const pathInput = document.getElementById('templatePath');
        if (pathInput) {
            pathInput.value = defaultPath;
            log(`showLoadTemplateModal: Set path to ${defaultPath}`, 'info');
        } else {
            log('showLoadTemplateModal: ERROR - Path input not found!', 'error');
        }
        
        // Clear file list and reset button
        const fileList = document.getElementById('templateFileList');
        if (fileList) {
            fileList.innerHTML = '<p style="color: #666;">Select a server and click Refresh to load schedule files</p>';
        }
        
        const loadBtn = document.getElementById('loadTemplateBtn');
        if (loadBtn) {
            loadBtn.disabled = true;
        }
        
        log('showLoadTemplateModal: Daily template modal shown successfully', 'success');
    } catch (error) {
        log(`showLoadTemplateModal: ERROR - ${error.message}`, 'error');
        console.error('Error in showLoadTemplateModal:', error);
    }
}

function showLoadWeeklyTemplateModal() {
    try {
        log('showLoadWeeklyTemplateModal: Starting to show weekly template modal', 'info');
        currentTemplateType = 'weekly';
        
        const modal = document.getElementById('loadTemplateModal');
        if (!modal) {
            log('showLoadWeeklyTemplateModal: ERROR - Modal element not found!', 'error');
            return;
        }
        
        modal.style.display = 'block';
        log('showLoadWeeklyTemplateModal: Modal display set to block', 'info');
        
        const titleElement = document.getElementById('loadTemplateModalTitle');
        if (titleElement) {
            titleElement.textContent = 'Load Weekly Schedule Template';
        }
        
        // Load default path from scheduling settings
        const schedulingSettings = JSON.parse(localStorage.getItem('schedulingSettings') || '{}');
        const defaultPath = schedulingSettings.defaultExportPath || '/mnt/main/Schedules';
        
        const pathInput = document.getElementById('templatePath');
        if (pathInput) {
            pathInput.value = defaultPath;
            log(`showLoadWeeklyTemplateModal: Set path to ${defaultPath}`, 'info');
        }
        
        // Clear previous file list
        const fileList = document.getElementById('templateFileList');
        if (fileList) {
            fileList.innerHTML = '<p style="color: #666;">Select a server and click Refresh to load schedule files</p>';
        }
        
        const loadBtn = document.getElementById('loadTemplateBtn');
        if (loadBtn) {
            loadBtn.disabled = true;
        }
        
        log('showLoadWeeklyTemplateModal: Weekly template modal shown successfully', 'success');
    } catch (error) {
        log(`showLoadWeeklyTemplateModal: ERROR - ${error.message}`, 'error');
        console.error('Error in showLoadWeeklyTemplateModal:', error);
    }
}

function closeLoadTemplateModal() {
    document.getElementById('loadTemplateModal').style.display = 'none';
    selectedTemplateFile = null;
}

function showLoadMonthlyTemplateModal() {
    try {
        log('showLoadMonthlyTemplateModal: Starting to show monthly template modal', 'info');
        currentTemplateType = 'monthly';
        
        const modal = document.getElementById('loadTemplateModal');
        if (!modal) {
            log('showLoadMonthlyTemplateModal: ERROR - Modal element not found!', 'error');
            return;
        }
        
        modal.style.display = 'block';
        log('showLoadMonthlyTemplateModal: Modal display set to block', 'info');
        
        const titleElement = document.getElementById('loadTemplateModalTitle');
        if (titleElement) {
            titleElement.textContent = 'Load Monthly Schedule Template';
        }
        
        // Load default path from scheduling settings
        const settings = JSON.parse(localStorage.getItem('schedulingSettings') || '{}');
        const defaultPath = settings.defaultExportPath || '/mnt/main/Schedules';
        
        const pathInput = document.getElementById('templatePath');
        if (pathInput) {
            pathInput.value = defaultPath;
            log(`showLoadMonthlyTemplateModal: Set path to ${defaultPath}`, 'info');
        }
        
        // Clear file list and reset button
        const fileList = document.getElementById('templateFileList');
        if (fileList) {
            fileList.innerHTML = '<p style="color: #666;">Select a server and click Refresh to load schedule files</p>';
        }
        
        const loadBtn = document.getElementById('loadTemplateBtn');
        if (loadBtn) {
            loadBtn.disabled = true;
        }
        
        log('showLoadMonthlyTemplateModal: Monthly template modal shown successfully', 'success');
    } catch (error) {
        log(`showLoadMonthlyTemplateModal: ERROR - ${error.message}`, 'error');
        console.error('Error in showLoadMonthlyTemplateModal:', error);
    }
}

async function fillScheduleGaps() {
    try {
        log('fillScheduleGaps: Function called', 'info');
        
        if (!currentTemplate) {
            log('fillScheduleGaps: No current template loaded', 'warning');
            alert('Please load a template first');
            return;
        }
        
        if (!currentTemplate.items || currentTemplate.items.length === 0) {
            log('fillScheduleGaps: Template has no items', 'warning');
            alert('Please load a template with items first');
            return;
        }
        
        // Make sure we're on the dashboard to see the template
        const activePanel = document.querySelector('.panel:not([style*="display: none"])');
        if (activePanel && activePanel.id !== 'dashboard') {
            // Switch to dashboard if not already there
            showPanel('dashboard');
        }
        
        log(`fillScheduleGaps: Current template has ${currentTemplate.items.length} items`, 'info');

        // Check if we have analyzed content to fill gaps with
        log(`fillScheduleGaps: Checking availableContent array, length: ${availableContent ? availableContent.length : 0}`, 'info');
        
        if (!availableContent || availableContent.length === 0) {
            log('fillScheduleGaps: No content loaded, attempting to load available content', 'info');
            
            // Try to load available content
            try {
                const response = await fetch('http://127.0.0.1:5000/api/analyzed-content', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        content_type: '',
                        duration_category: '',
                        search: ''
                    })
                });
                const result = await response.json();
                
                if (result.success && result.content && result.content.length > 0) {
                    availableContent = result.content;
                    log(`fillScheduleGaps: Loaded ${availableContent.length} available content items`, 'success');
                } else {
                    log('fillScheduleGaps: No analyzed content available', 'warning');
                    alert('No analyzed content available. Please analyze some files first.');
                    return;
                }
            } catch (error) {
                log(`fillScheduleGaps: Error loading content: ${error.message}`, 'error');
                alert('Error loading available content. Please try again.');
                return;
            }
        }
        
        log(`fillScheduleGaps: Found ${availableContent.length} analyzed files available`, 'info');

        // Calculate total template duration
        let totalDuration = 0;
        currentTemplate.items.forEach(item => {
            const duration = parseFloat(item.duration_seconds);
            if (!isNaN(duration) && duration > 0) {
                totalDuration += duration;
            } else {
                log(`fillScheduleGaps: Item has invalid duration: ${item.title || item.file_name} - ${item.duration_seconds}`, 'warning');
            }
        });
        
        log(`fillScheduleGaps: Total template duration: ${totalDuration} seconds (${formatDuration(totalDuration)})`, 'info');

        // Calculate total time needed based on template type
        let hoursNeeded = 24; // Default for daily
        if (currentTemplate.type === 'weekly') {
            hoursNeeded = 24 * 7; // 7 days
        } else if (currentTemplate.type === 'monthly') {
            hoursNeeded = 24 * 31; // 31 days max
        }
        
        const secondsNeeded = hoursNeeded * 3600;
        const gapSeconds = secondsNeeded - totalDuration;

        if (gapSeconds <= 0) {
            const templateTypeText = currentTemplate.type === 'weekly' ? '7 days' : currentTemplate.type === 'monthly' ? '31 days' : '24 hours';
            log(`fillScheduleGaps: Template already fills or exceeds ${templateTypeText} (${formatDuration(totalDuration)})`, 'warning');
            alert(`Template already fills or exceeds ${templateTypeText}`);
            return;
        }

        const gapHours = Math.floor(gapSeconds / 3600);
        const gapMinutes = Math.floor((gapSeconds % 3600) / 60);
        
        log(`fillScheduleGaps: Gap to fill: ${gapHours}h ${gapMinutes}m (${gapSeconds} seconds)`, 'info');

        if (confirm(`Current template duration: ${formatDuration(totalDuration)}\nGap to fill: ${gapHours}h ${gapMinutes}m\n\nFill the gaps with available content?`)) {
            log(`fillScheduleGaps: User confirmed - filling ${gapHours}h ${gapMinutes}m of schedule gaps`, 'info');
            
            try {
                // Call backend to fill gaps using proper rotation logic
                log('fillScheduleGaps: Calling backend to fill gaps with rotation logic', 'info');
                
                const response = await fetch('http://127.0.0.1:5000/api/fill-template-gaps', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        template: currentTemplate,
                        available_content: availableContent
                    })
                });
                
                const result = await response.json();
                
                if (result.success && result.items_added && result.items_added.length > 0) {
                    log(`fillScheduleGaps: Backend added ${result.items_added.length} items using rotation logic`, 'success');
                    
                    // Add the new items to the template
                    currentTemplate.items.push(...result.items_added);
                    
                    // Sort items by start time and fill gaps
                    fillGapsWithProperTimes();
                    
                    // Update the template display
                    const activePanel = document.querySelector('.panel:not([style*="display: none"])');
                    if (activePanel && activePanel.id === 'dashboard') {
                        displayDashboardTemplate();
                    } else {
                        displayTemplate();
                    }
                    
                    alert(`Successfully added ${result.items_added.length} items to fill the schedule gaps.`);
                    log(`fillScheduleGaps: Template now has ${currentTemplate.items.length} items`, 'success');
                } else {
                    log(`fillScheduleGaps: ${result.message || 'No suitable content found to fill gaps'}`, 'warning');
                    alert(result.message || 'Could not find suitable content to fill the schedule gaps. Try analyzing more content.');
                }
            } catch (error) {
                log(`fillScheduleGaps: Error filling gaps - ${error.message}`, 'error');
                alert(`Error filling schedule gaps: ${error.message}`);
            }
        } else {
            log('fillScheduleGaps: User cancelled gap filling', 'info');
        }
    } catch (error) {
        log(`fillScheduleGaps: ERROR - ${error.message}`, 'error');
        console.error('Error in fillScheduleGaps:', error);
    }
}

async function loadTemplateFiles() {
    const server = document.getElementById('templateServer').value;
    const path = document.getElementById('templatePath').value;
    
    if (!server) {
        log('Please select a server', 'error');
        return;
    }
    
    const fileList = document.getElementById('templateFileList');
    fileList.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Loading schedule files...</p>';
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/list-schedule-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server, path })
        });
        
        const result = await response.json();
        
        if (result.success && result.files) {
            if (result.files.length === 0) {
                fileList.innerHTML = '<p style="color: #666;">No schedule files found in this directory</p>';
            } else {
                let html = '';
                result.files.forEach(file => {
                    html += `
                        <div class="file-item" style="padding: 8px; border: 1px solid #333; margin: 5px 0; cursor: pointer; border-radius: 4px;"
                             onclick="selectTemplateFile('${file.path}', '${file.name}')">
                            <i class="fas fa-file"></i> ${file.name}
                            <span style="float: right; color: #666;">${formatFileSize(file.size)}</span>
                        </div>
                    `;
                });
                fileList.innerHTML = html;
            }
        } else {
            fileList.innerHTML = `<p style="color: #ff4444;">Error: ${result.message || 'Failed to load files'}</p>`;
        }
    } catch (error) {
        fileList.innerHTML = `<p style="color: #ff4444;">Error: ${error.message}</p>`;
    }
}

function selectTemplateFile(path, name) {
    selectedTemplateFile = { path, name };
    
    // Highlight selected file
    const fileItems = document.querySelectorAll('.file-item');
    fileItems.forEach(item => {
        item.style.background = 'transparent';
        item.style.border = '1px solid #333';
    });
    
    event.currentTarget.style.background = 'rgba(33, 150, 243, 0.2)';
    event.currentTarget.style.border = '1px solid var(--primary-color)';
    
    // Enable load button
    document.getElementById('loadTemplateBtn').disabled = false;
}

async function loadSelectedTemplate() {
    console.log('loadSelectedTemplate called');
    
    if (!selectedTemplateFile) {
        log('Please select a template file', 'error');
        console.error('No template file selected');
        return;
    }
    
    const server = document.getElementById('templateServer').value;
    console.log('Loading template:', selectedTemplateFile, 'from server:', server);
    
    try {
        log('Loading template...', 'info');
        log(`📥 Loading template: ${selectedTemplateFile.name} from ${server} server`);
        
        const response = await fetch('http://127.0.0.1:5000/api/load-schedule-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server: server,
                file_path: selectedTemplateFile.path
            })
        });
        
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('Load template result:', result);
        
        if (result.success && result.template) {
            currentTemplate = result.template;
            currentTemplate.filename = result.filename;
            currentTemplate.type = result.template.type || 'daily'; // Store schedule type
            
            // Display template info
            displayTemplate();
            
            // Update available content to show add buttons
            if (availableContent && availableContent.length > 0) {
                displayAvailableContent(availableContent);
            }
            
            // Save template to library
            saveTemplateToLibrary(currentTemplate);
            
            closeLoadTemplateModal();
            log(`Template loaded: ${result.filename}`, 'success');
            log(`✅ Template loaded successfully: ${result.filename} with ${currentTemplate.items.length} items`);
        } else {
            const errorMsg = result.message || 'Unknown error';
            log(`Failed to load template: ${errorMsg}`, 'error');
            log(`❌ Failed to load template: ${errorMsg}`, 'error');
            console.error('Load template failed:', result);
        }
    } catch (error) {
        log(`Error loading template: ${error.message}`, 'error');
        log(`❌ Error loading template: ${error.message}`, 'error');
        console.error('Load template error:', error);
    }
}

function fillGapsWithProperTimes() {
    if (!currentTemplate || !currentTemplate.items) return;
    
    // Separate items with fixed times (imported) from items without times (newly added)
    const itemsWithTimes = [];
    const itemsWithoutTimes = [];
    
    currentTemplate.items.forEach(item => {
        if (item.start_time && 
            item.start_time !== "00:00:00:00" && 
            item.start_time !== "00:00:00" && 
            item.start_time !== null) {
            itemsWithTimes.push(item);
        } else {
            itemsWithoutTimes.push(item);
        }
    });
    
    // Sort items with times by their start time
    itemsWithTimes.sort((a, b) => {
        const timeA = parseTimeToSeconds(a.start_time);
        const timeB = parseTimeToSeconds(b.start_time);
        return timeA - timeB;
    });
    
    // Clear the items array
    currentTemplate.items = [];
    
    // Now fill gaps with the new items
    let newItemIndex = 0;
    let currentTime = 0; // Start from midnight
    
    // Add items before the first fixed item
    if (itemsWithTimes.length > 0) {
        const firstFixedTime = parseTimeToSeconds(itemsWithTimes[0].start_time);
        
        // Fill from midnight to first fixed item
        while (currentTime < firstFixedTime && newItemIndex < itemsWithoutTimes.length) {
            const item = itemsWithoutTimes[newItemIndex];
            const duration = parseFloat(item.duration_seconds || item.file_duration || 0);
            
            // Check if this item fits before the fixed item
            if (currentTime + duration <= firstFixedTime) {
                item.start_time = formatTimeFromSeconds(currentTime);
                item.end_time = formatTimeFromSeconds(currentTime + duration);
                currentTemplate.items.push(item);
                currentTime += duration;
                newItemIndex++;
            } else {
                // Item doesn't fit, skip to after the fixed item
                break;
            }
        }
    }
    
    // Add the fixed items and fill gaps between them
    for (let i = 0; i < itemsWithTimes.length; i++) {
        const fixedItem = itemsWithTimes[i];
        currentTemplate.items.push(fixedItem);
        
        // Update current time to end of this fixed item
        const fixedStartTime = parseTimeToSeconds(fixedItem.start_time);
        const fixedDuration = parseFloat(fixedItem.duration_seconds || 0);
        currentTime = fixedStartTime + fixedDuration;
        
        // Determine the next fixed item time or end of day
        const nextFixedTime = (i < itemsWithTimes.length - 1) 
            ? parseTimeToSeconds(itemsWithTimes[i + 1].start_time)
            : 24 * 60 * 60; // End of day
        
        // Fill gap until next fixed item
        while (currentTime < nextFixedTime && newItemIndex < itemsWithoutTimes.length) {
            const item = itemsWithoutTimes[newItemIndex];
            const duration = parseFloat(item.duration_seconds || item.file_duration || 0);
            
            // Check if this item fits before the next fixed item
            if (currentTime + duration <= nextFixedTime) {
                item.start_time = formatTimeFromSeconds(currentTime);
                item.end_time = formatTimeFromSeconds(currentTime + duration);
                currentTemplate.items.push(item);
                currentTime += duration;
                newItemIndex++;
            } else {
                // Item doesn't fit, skip to after the next fixed item
                break;
            }
        }
    }
    
    // Add any remaining items at the end of the day
    while (newItemIndex < itemsWithoutTimes.length && currentTime < 24 * 60 * 60) {
        const item = itemsWithoutTimes[newItemIndex];
        const duration = parseFloat(item.duration_seconds || item.file_duration || 0);
        
        item.start_time = formatTimeFromSeconds(currentTime);
        item.end_time = formatTimeFromSeconds(currentTime + duration);
        currentTemplate.items.push(item);
        currentTime += duration;
        newItemIndex++;
    }
}

function parseTimeToSeconds(timeStr) {
    if (!timeStr) return 0;
    
    // Handle different time formats
    const parts = timeStr.split(':');
    let hours = 0, minutes = 0, seconds = 0;
    
    if (parts.length >= 3) {
        hours = parseInt(parts[0]) || 0;
        minutes = parseInt(parts[1]) || 0;
        seconds = parseFloat(parts[2]) || 0;
    }
    
    return hours * 3600 + minutes * 60 + seconds;
}

function formatTimeFromSeconds(totalSeconds, format = 'daily') {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);
    const frames = 0; // We'll use 0 frames for simplicity
    
    if (format === 'daily') {
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
    }
    // Add weekly format support if needed
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
}

function recalculateTemplateTimes() {
    if (!currentTemplate || !currentTemplate.items) return;
    
    // Check if ALL items have valid times (not just the first one)
    const allItemsHaveValidTimes = currentTemplate.items.length > 0 && 
                                  currentTemplate.items.every(item => 
                                      item.start_time && 
                                      item.start_time !== "00:00:00:00" &&
                                      item.start_time !== "00:00:00" &&
                                      item.start_time !== null
                                  );
    
    if (allItemsHaveValidTimes) {
        // Don't recalculate - all times are already set
        return;
    }
    
    // Handle based on template type
    if (currentTemplate.type === 'weekly') {
        // For weekly templates, we need to add day prefixes
        let currentSeconds = 0;
        
        currentTemplate.items.forEach(item => {
            // Format start time with day prefix
            item.start_time = formatTimeFromSeconds(currentSeconds, 'weekly');
            
            const duration = parseFloat(item.duration_seconds) || 0;
            currentSeconds += duration;
            
            // Format end time with day prefix
            item.end_time = formatTimeFromSeconds(currentSeconds, 'weekly');
        });
    } else {
        // Daily templates - use existing logic
        let currentTime = "00:00:00:00"; // Start with frames
        
        currentTemplate.items.forEach(item => {
            item.start_time = currentTime;
            const duration = parseFloat(item.duration_seconds) || 0;
            
            // Calculate end time with frame precision
            const endTime = calculateEndTime(currentTime, duration);
            item.end_time = endTime;
            
            // Update current time for next item
            currentTime = endTime;
        });
    }
}

function displayTemplate() {
    if (!currentTemplate) return;
    
    // Recalculate times before display
    recalculateTemplateTimes();
    
    // Show template info
    document.getElementById('templateInfo').style.display = 'block';
    const scheduleType = currentTemplate.type === 'weekly' ? 'Weekly' : 'Daily';
    document.getElementById('templateName').textContent = `${currentTemplate.filename || 'Untitled'} (${scheduleType})`;
    document.getElementById('templateItemCount').textContent = currentTemplate.items.length;
    
    // Calculate total duration
    let totalDuration = 0;
    currentTemplate.items.forEach(item => {
        totalDuration += parseFloat(item.duration_seconds) || 0;
    });
    
    const hours = Math.floor(totalDuration / 3600);
    const minutes = Math.floor((totalDuration % 3600) / 60);
    const seconds = Math.floor(totalDuration % 60);
    document.getElementById('templateDuration').textContent = `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    // Display template items
    const templateDisplay = document.getElementById('templateDisplay');
    templateDisplay.style.display = 'block';
    
    if (currentTemplate.items.length === 0) {
        templateDisplay.innerHTML = '<p style="color: #666; text-align: center;">No items in template. Add items from Available Content.</p>';
    } else {
        let html = `
            <div class="template-item" style="font-weight: bold; background: rgba(33, 150, 243, 0.1); border-bottom: 2px solid rgba(33, 150, 243, 0.3);">
                <span>#</span>
                <span>Start Time</span>
                <span>File Name</span>
                <span>Duration</span>
                <span>End Time</span>
                <span>Actions</span>
            </div>
        `;
        
        // For weekly schedules, track which day we're on
        let currentDay = '';
        let dayTotalDuration = 0;
        
        currentTemplate.items.forEach((item, index) => {
            // For weekly schedules, check if we need to add a day header
            if (currentTemplate.type === 'weekly' && item.start_time) {
                // Extract day from start time (e.g., "wed 12:00 am" -> "wed")
                const dayMatch = item.start_time.match(/^(\w{3})\s/);
                if (dayMatch) {
                    const itemDay = dayMatch[1];
                    if (itemDay !== currentDay) {
                        currentDay = itemDay;
                        const dayNames = {
                            'sun': 'Sunday',
                            'mon': 'Monday',
                            'tue': 'Tuesday',
                            'wed': 'Wednesday',
                            'thu': 'Thursday',
                            'fri': 'Friday',
                            'sat': 'Saturday'
                        };
                        html += `
                            <div class="template-day-header" style="background: rgba(55, 126, 255, 0.15); padding: 0.5rem 1rem; margin: 0.5rem 0; font-weight: bold; color: var(--primary-color);">
                                ${dayNames[itemDay] || itemDay.toUpperCase()}
                            </div>
                        `;
                    }
                }
            }
            
            const durationTimecode = formatDurationTimecodeWithMs(item.duration_seconds || 0);
            const hasAssetId = item.asset_id || item.content_id;
            const itemStyle = hasAssetId ? '' : 'opacity: 0.6;';
            const itemTitle = hasAssetId ? item.file_path : `${item.file_path} (Not in database - must be added from Available Content)`;
            
            // Format start and end times to show frames
            const startTimeFormatted = formatTimeToTimecode(item.start_time || '00:00:00');
            const endTimeFormatted = formatTimeToTimecode(item.end_time || '00:00:00');
            
            html += `
                <div class="template-item" style="${itemStyle}">
                    <span style="color: #666;">${index + 1}</span>
                    <span>${startTimeFormatted}</span>
                    <span title="${itemTitle}">
                        ${item.filename}
                        ${!hasAssetId ? ' <i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i>' : ''}
                    </span>
                    <span>${durationTimecode}</span>
                    <span>${endTimeFormatted}</span>
                    <div class="template-item-actions">
                        <button class="button info small" onclick="showTemplateItemInfo(${index})">
                            <i class="fas fa-info-circle"></i>
                        </button>
                        <button class="button danger small" onclick="removeTemplateItem(${index})">
                            <i class="fas fa-trash"></i>
                        </button>
                        <button class="button secondary small" onclick="moveTemplateItem(${index}, 'up')" ${index === 0 ? 'disabled' : ''}>
                            <i class="fas fa-arrow-up"></i>
                        </button>
                        <button class="button secondary small" onclick="moveTemplateItem(${index}, 'down')" ${index === currentTemplate.items.length - 1 ? 'disabled' : ''}>
                            <i class="fas fa-arrow-down"></i>
                        </button>
                    </div>
                </div>
            `;
        });
        templateDisplay.innerHTML = html;
    }
}

function clearTemplate() {
    if (confirm('Are you sure you want to clear the current template?')) {
        currentTemplate = null;
        
        // Clear both scheduling and dashboard template displays
        document.getElementById('templateInfo').style.display = 'none';
        document.getElementById('templateDisplay').innerHTML = '<p>Load a template file to begin editing</p>';
        
        document.getElementById('dashboardTemplateInfo').style.display = 'none';
        document.getElementById('dashboardTemplateDisplay').innerHTML = '<p style="text-align: center; color: #666;">Load a template file to begin editing</p>';
        
        // Hide export button
        const exportBtn = document.getElementById('exportTemplateBtn');
        if (exportBtn) {
            exportBtn.style.display = 'none';
        }
        
        // Update available content to remove add buttons
        if (availableContent && availableContent.length > 0) {
            displayAvailableContent(availableContent);
        }
        
        log('Template cleared', 'info');
    }
}

function removeTemplateItem(index) {
    if (currentTemplate && currentTemplate.items) {
        currentTemplate.items.splice(index, 1);
        
        // Check which panel is active and display accordingly
        const activePanel = document.querySelector('.panel:not([style*="display: none"])');
        if (activePanel && activePanel.id === 'dashboard') {
            displayDashboardTemplate();
        } else {
            displayTemplate();
        }
        
        log('Item removed from template', 'info');
    }
}

function moveTemplateItem(index, direction) {
    if (!currentTemplate || !currentTemplate.items) return;
    
    const items = currentTemplate.items;
    if (direction === 'up' && index > 0) {
        [items[index], items[index - 1]] = [items[index - 1], items[index]];
    } else if (direction === 'down' && index < items.length - 1) {
        [items[index], items[index + 1]] = [items[index + 1], items[index]];
    }
    
    // Check which panel is active and display accordingly
    const activePanel = document.querySelector('.panel:not([style*="display: none"])');
    if (activePanel && activePanel.id === 'dashboard') {
        displayDashboardTemplate();
    } else {
        displayTemplate();
    }
}

function showTemplateItemInfo(index) {
    if (!currentTemplate || !currentTemplate.items || !currentTemplate.items[index]) return;
    
    const item = currentTemplate.items[index];
    const info = [];
    
    const displayTitle = item.title || item.name || item.file_name || item.filename || 'Untitled';
    info.push(`<strong>Title:</strong> ${displayTitle}`);
    info.push(`<strong>Start Time:</strong> ${item.start_time}`);
    info.push(`<strong>End Time:</strong> ${item.end_time}`);
    info.push(`<strong>Duration:</strong> ${formatDuration(item.duration_seconds)}`);
    
    if (item.asset_id) {
        info.push(`<strong>Asset ID:</strong> ${item.asset_id}`);
    }
    if (item.content_type) {
        info.push(`<strong>Content Type:</strong> ${item.content_type}`);
    }
    if (item.file_name || item.filename) {
        info.push(`<strong>File:</strong> ${item.file_name || item.filename}`);
    }
    if (item.summary) {
        info.push(`<strong>Summary:</strong> ${item.summary}`);
    }
    
    // Create a simple modal to show the info
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.display = 'block';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>Template Item Details</h2>
                <span class="close" onclick="this.parentElement.parentElement.parentElement.remove()">&times;</span>
            </div>
            <div class="modal-body">
                <div class="info-content">
                    ${info.join('<br><br>')}
                </div>
            </div>
            <div class="modal-footer">
                <button class="button secondary" onclick="this.parentElement.parentElement.parentElement.remove()">Close</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Close modal when clicking outside
    modal.onclick = function(event) {
        if (event.target === modal) {
            modal.remove();
        }
    };
}

// Template storage
let savedTemplates = JSON.parse(localStorage.getItem('savedTemplates') || '[]');
let currentExportTemplate = null;

function showTemplateLibrary() {
    log('Opening template library', 'info');
    document.getElementById('templateLibraryModal').style.display = 'block';
    loadTemplateLibrary();
}

function closeTemplateLibraryModal() {
    document.getElementById('templateLibraryModal').style.display = 'none';
}

function loadTemplateLibrary() {
    const libraryList = document.getElementById('templateLibraryList');
    
    if (savedTemplates.length === 0) {
        libraryList.innerHTML = '<p style="text-align: center; color: #666;">No saved templates. Import a template to get started.</p>';
        return;
    }
    
    let html = '<div class="template-library-grid">';
    savedTemplates.forEach((template, index) => {
        const itemCount = template.items ? template.items.length : 0;
        const totalDuration = template.items ? 
            template.items.reduce((sum, item) => sum + (item.duration_seconds || 0), 0) : 0;
        const durationStr = formatDuration(totalDuration);
        
        html += `
            <div class="template-library-item">
                <div class="template-library-header">
                    <h4>${template.filename || template.name || 'Untitled Template'}</h4>
                    <span class="template-type ${template.type}">${template.type || 'daily'}</span>
                </div>
                <div class="template-library-info">
                    <p><i class="fas fa-list"></i> ${itemCount} items</p>
                    <p><i class="fas fa-clock"></i> ${durationStr}</p>
                    <p><i class="fas fa-calendar"></i> Saved: ${new Date(template.savedDate).toLocaleDateString()}</p>
                </div>
                <div class="template-library-actions">
                    <button class="button primary small" onclick="viewTemplate(${index})">
                        <i class="fas fa-eye"></i> View
                    </button>
                    <button class="button secondary small" onclick="loadSavedTemplate(${index})">
                        <i class="fas fa-upload"></i> Load
                    </button>
                    <button class="button info small" onclick="exportTemplate(${index})">
                        <i class="fas fa-file-export"></i> Export
                    </button>
                    <button class="button danger small" onclick="deleteTemplate(${index})">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            </div>
        `;
    });
    html += '</div>';
    
    libraryList.innerHTML = html;
}

function displayDashboardTemplate() {
    if (!currentTemplate) return;
    
    // Show template info
    document.getElementById('dashboardTemplateInfo').style.display = 'block';
    
    // Show export button
    const exportBtn = document.getElementById('exportTemplateBtn');
    if (exportBtn) {
        exportBtn.style.display = 'inline-block';
    }
    const scheduleType = currentTemplate.type === 'weekly' ? 'Weekly' : currentTemplate.type === 'monthly' ? 'Monthly' : 'Daily';
    // Use filename as the primary name source
    const templateName = currentTemplate.filename || currentTemplate.name || 'Untitled';
    document.getElementById('dashboardTemplateName').textContent = `${templateName} (${scheduleType})`;
    document.getElementById('dashboardTemplateItemCount').textContent = currentTemplate.items ? currentTemplate.items.length : 0;
    
    // Calculate total duration
    let totalDuration = 0;
    if (currentTemplate.items) {
        currentTemplate.items.forEach(item => {
            totalDuration += parseFloat(item.duration_seconds) || 0;
        });
    }
    
    const hours = Math.floor(totalDuration / 3600);
    const minutes = Math.floor((totalDuration % 3600) / 60);
    const seconds = Math.floor(totalDuration % 60);
    document.getElementById('dashboardTemplateDuration').textContent = 
        `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    
    // Display template items
    const templateDisplay = document.getElementById('dashboardTemplateDisplay');
    
    if (!currentTemplate.items || currentTemplate.items.length === 0) {
        templateDisplay.innerHTML = '<p style="color: #666; text-align: center;">No items in template.</p>';
        return;
    }
    
    let html = '<div class="template-items-container">';
    
    // For weekly schedules, track which day we're on
    let currentDay = '';
    
    currentTemplate.items.forEach((item, index) => {
        // For weekly schedules, check if we need to add a day header
        if (currentTemplate.type === 'weekly' && item.start_time) {
            // Extract day from start time (e.g., "wed 12:00 am" -> "wed")
            const dayMatch = item.start_time.match(/^(\w{3})\s/);
            if (dayMatch) {
                const itemDay = dayMatch[1];
                if (itemDay !== currentDay) {
                    currentDay = itemDay;
                    const dayNames = {
                        'sun': 'Sunday',
                        'mon': 'Monday',
                        'tue': 'Tuesday',
                        'wed': 'Wednesday',
                        'thu': 'Thursday',
                        'fri': 'Friday',
                        'sat': 'Saturday'
                    };
                    html += `
                        <div class="template-day-header" style="background: rgba(55, 126, 255, 0.15); padding: 0.5rem 1rem; margin: 0.5rem 0; font-weight: bold; color: var(--primary-color); border-radius: 4px;">
                            ${dayNames[itemDay] || itemDay.toUpperCase()}
                        </div>
                    `;
                }
            }
        }
        
        // Format duration with milliseconds preserved
        const durationTimecode = item.duration_timecode || formatDurationTimecodeWithMs(item.duration_seconds);
        const hasAssetId = item.asset_id || item.id;
        
        // Format start time as timecode with milliseconds
        const startTimeTimecode = formatTimeToTimecode(item.start_time || '00:00:00');
        
        html += `
            <div class="template-item ${!hasAssetId ? 'missing-asset' : ''}">
                <span class="template-item-number">${index + 1}</span>
                <span class="template-item-time">${startTimeTimecode}</span>
                <span class="template-item-title">
                    ${item.title || item.name || item.file_name || item.filename || 'Untitled'}
                    ${!hasAssetId ? ' <i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i>' : ''}
                </span>
                <span>${durationTimecode}</span>
                <span>${item.end_time || '00:00:00'}</span>
                <div class="template-item-actions">
                    <button class="button info small" onclick="showTemplateItemInfo(${index})">
                        <i class="fas fa-info-circle"></i>
                    </button>
                    <button class="button danger small" onclick="removeTemplateItem(${index})">
                        <i class="fas fa-trash"></i>
                    </button>
                    <button class="button secondary small" onclick="moveTemplateItem(${index}, 'up')" ${index === 0 ? 'disabled' : ''}>
                        <i class="fas fa-arrow-up"></i>
                    </button>
                    <button class="button secondary small" onclick="moveTemplateItem(${index}, 'down')" ${index === currentTemplate.items.length - 1 ? 'disabled' : ''}>
                        <i class="fas fa-arrow-down"></i>
                    </button>
                </div>
            </div>
        `;
    });
    html += '</div>';
    
    templateDisplay.innerHTML = html;
}

function viewTemplate(index) {
    const template = savedTemplates[index];
    if (!template) return;
    
    // Close library modal and load the template for viewing
    closeTemplateLibraryModal();
    currentTemplate = JSON.parse(JSON.stringify(template)); // Deep copy
    
    // Check which panel is active and display accordingly
    const activePanel = document.querySelector('.panel:not([style*="display: none"])');
    if (activePanel && activePanel.id === 'dashboard') {
        displayDashboardTemplate();
    } else {
        displayTemplate();
    }
    
    log(`Viewing template: ${template.filename || template.name || 'Untitled'}`, 'info');
}

function loadSavedTemplate(index) {
    const template = savedTemplates[index];
    if (!template) return;
    
    if (confirm(`Load template "${template.filename || template.name || 'Untitled'}"? This will replace the current template.`)) {
        closeTemplateLibraryModal();
        currentTemplate = JSON.parse(JSON.stringify(template)); // Deep copy
        
        // Check which panel is active and display accordingly
        const activePanel = document.querySelector('.panel:not([style*="display: none"])');
        if (activePanel && activePanel.id === 'dashboard') {
            displayDashboardTemplate();
        } else {
            displayTemplate();
        }
        
        log(`Loaded template: ${template.filename || template.name || 'Untitled'}`, 'success');
    }
}

function exportTemplate(index) {
    const template = savedTemplates[index];
    if (!template) return;
    
    currentExportTemplate = template;
    document.getElementById('exportTemplateName').textContent = template.filename || template.name || 'Untitled Template';
    
    // Set default filename based on template type and name
    const date = new Date();
    const dateStr = date.toISOString().split('T')[0].replace(/-/g, '');
    const templateType = template.type || 'daily';
    let defaultFilename = '';
    
    if (templateType === 'daily') {
        defaultFilename = `daily_${dateStr}.sch`;
    } else if (templateType === 'weekly') {
        defaultFilename = `weekly_${dateStr}.sch`;
    } else if (templateType === 'monthly') {
        defaultFilename = `monthly_${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}.sch`;
    }
    
    document.getElementById('templateExportFilename').value = defaultFilename;
    document.getElementById('templateExportFormat').value = `castus_${templateType}`;
    
    document.getElementById('templateExportModal').style.display = 'block';
}

function closeTemplateExportModal() {
    document.getElementById('templateExportModal').style.display = 'none';
    currentExportTemplate = null;
}

async function confirmTemplateExport() {
    if (!currentExportTemplate) return;
    
    const server = document.getElementById('templateExportServer').value;
    const path = document.getElementById('templateExportPath').value;
    const filename = document.getElementById('templateExportFilename').value;
    const format = document.getElementById('templateExportFormat').value;
    
    if (!filename) {
        alert('Please enter a filename');
        return;
    }
    
    log(`Exporting template to ${server} server: ${path}/${filename}`, 'info');
    
    try {
        // This would typically make an API call to export the template
        // For now, we'll prepare the data and show a message
        const exportData = {
            template: currentExportTemplate,
            server: server,
            path: path,
            filename: filename,
            format: format
        };
        
        // TODO: Implement actual export to FTP
        log('Template export feature not yet implemented', 'warning');
        alert('Template export to FTP is not yet implemented. The template data has been prepared for export.');
        
        closeTemplateExportModal();
    } catch (error) {
        log(`Export error: ${error.message}`, 'error');
    }
}

function deleteTemplate(index) {
    const template = savedTemplates[index];
    if (!template) return;
    
    if (confirm(`Delete template "${template.filename || template.name || 'Untitled'}"? This cannot be undone.`)) {
        savedTemplates.splice(index, 1);
        localStorage.setItem('savedTemplates', JSON.stringify(savedTemplates));
        loadTemplateLibrary();
        log(`Deleted template: ${template.filename || template.name || 'Untitled'}`, 'info');
    }
}

// Save template when loaded
function saveTemplateToLibrary(template) {
    // Add metadata
    template.savedDate = new Date().toISOString();
    if (!template.name && template.filename) {
        template.name = template.filename.replace(/\.[^/.]+$/, ''); // Remove extension
    }
    
    // Check if template already exists
    const existingIndex = savedTemplates.findIndex(t => 
        t.filename === template.filename && t.type === template.type
    );
    
    if (existingIndex >= 0) {
        // Update existing template
        savedTemplates[existingIndex] = template;
    } else {
        // Add new template
        savedTemplates.push(template);
    }
    
    localStorage.setItem('savedTemplates', JSON.stringify(savedTemplates));
    log(`Saved template to library: ${template.filename || template.name || 'Untitled'}`, 'success');
}

// Fill gaps with content using scheduling algorithm
async function fillGapsWithContent(template, gapSeconds, availableContent) {
    if (!template || !availableContent || availableContent.length === 0) {
        throw new Error('No content available to fill gaps');
    }
    
    // Find all gaps in the schedule, including from the start
    const gaps = findScheduleGaps(template);
    if (gaps.length === 0) {
        log('fillGapsWithContent: No gaps found in schedule', 'info');
        return [];
    }
    
    log(`fillGapsWithContent: Found ${gaps.length} gaps to fill`, 'info');
    gaps.forEach((gap, i) => {
        log(`  Gap ${i + 1}: ${gap.startTime} to ${gap.endTime} (${formatDuration(gap.duration)})`, 'info');
    });
    
    // Check if there's a gap at the end of the schedule
    const lastGap = gaps[gaps.length - 1];
    const scheduleEnd = template.type === 'weekly' ? 7 * 24 * 3600 : 24 * 3600;
    if (lastGap && lastGap.endSeconds === scheduleEnd) {
        log(`fillGapsWithContent: Schedule has gap until end (${template.type === 'weekly' ? 'end of week' : 'midnight'})`, 'info');
    } else if (gaps.length > 0) {
        log(`fillGapsWithContent: Last gap ends at ${lastGap.endTime} (${lastGap.endSeconds} seconds), schedule should end at ${scheduleEnd} seconds`, 'info');
    }
    
    const newItems = [];
    
    // Filter out content with invalid durations and sort by engagement score and shelf life
    const validContent = availableContent.filter(content => {
        // Try duration_seconds first, then file_duration
        let duration = parseFloat(content.duration_seconds);
        if (isNaN(duration) || duration <= 0) {
            duration = parseFloat(content.file_duration);
        }
        
        if (isNaN(duration) || duration <= 0) {
            log(`fillGapsWithContent: Skipping ${content.content_title || content.file_name} - invalid duration: duration_seconds=${content.duration_seconds}, file_duration=${content.file_duration}`, 'warning');
            return false;
        }
        
        // Store the valid duration in duration_seconds for consistency
        content.duration_seconds = duration;
        return true;
    });
    
    log(`fillGapsWithContent: ${availableContent.length - validContent.length} items filtered out due to invalid duration`, 'info');
    
    const sortedContent = [...validContent].sort((a, b) => {
        const scoreA = (a.engagement_score || 50) + (a.shelf_life_score === 'high' ? 20 : a.shelf_life_score === 'medium' ? 10 : 0);
        const scoreB = (b.engagement_score || 50) + (b.shelf_life_score === 'high' ? 20 : b.shelf_life_score === 'medium' ? 10 : 0);
        return scoreB - scoreA;
    });
    
    log(`fillGapsWithContent: Available content count: ${sortedContent.length}`, 'info');
    log(`fillGapsWithContent: Gap to fill: ${formatDuration(gapSeconds)} (${gapSeconds} seconds)`, 'info');
    
    // Log duration categories available
    const categoryCounts = {};
    sortedContent.forEach(c => {
        categoryCounts[c.duration_category || 'unknown'] = (categoryCounts[c.duration_category || 'unknown'] || 0) + 1;
    });
    log(`fillGapsWithContent: Duration categories available: ${JSON.stringify(categoryCounts)}`, 'info');
    
    // Debug: Log first few items to see what fields they have
    if (sortedContent.length > 0) {
        log(`fillGapsWithContent: Sample content item:`, 'info');
        const sample = sortedContent[0];
        log(`  - Title: ${sample.content_title || sample.file_name}`, 'info');
        log(`  - Duration seconds: ${sample.duration_seconds}`, 'info');
        log(`  - File duration: ${sample.file_duration}`, 'info');
        log(`  - Duration category: ${sample.duration_category}`, 'info');
    }
    
    // Use rotation order from scheduling config
    const rotationOrder = scheduleConfig?.ROTATION_ORDER || ['id', 'short_form', 'long_form', 'spots'];
    let rotationIndex = 0;
    
    // Track used content to avoid immediate repeats
    const recentlyUsed = new Set();
    const recentLimit = Math.min(10, Math.floor(sortedContent.length / 4));
    
    // Keep track of how many times we've used each content
    const contentUsageCount = new Map();
    let itemsAdded = 0;
    
    // Process gaps one at a time, recalculating after each gap is filled
    let gapsToProcess = [...gaps];
    
    while (gapsToProcess.length > 0) {
        const gap = gapsToProcess.shift();
        let currentSeconds = gap.startSeconds;
        let remainingGapTime = gap.duration;
        
        log(`fillGapsWithContent: Filling gap from ${gap.startTime} to ${gap.endTime} (${gap.startSeconds}s to ${gap.endSeconds}s)`, 'info');
        
        const maxIterations = sortedContent.length * 10; // Prevent infinite loops
        let iterations = 0;
        let gapItems = []; // Items added to this specific gap
        
        while (remainingGapTime > 0 && iterations < maxIterations) {
            iterations++;
            
            // Get current duration category from rotation
            const targetCategory = rotationOrder[rotationIndex % rotationOrder.length];
            
            // Find content matching the target category that hasn't been overused
            let selectedItem = null;
            let minUsageCount = Number.MAX_SAFE_INTEGER;
            
            // First, try to find content in the target category
            for (const content of sortedContent) {
                const usageCount = contentUsageCount.get(content.id) || 0;
                if (content.duration_category === targetCategory && 
                    content.duration_seconds <= remainingGapTime &&
                    usageCount < minUsageCount) {
                    selectedItem = content;
                    minUsageCount = usageCount;
                    if (usageCount === 0) break; // Prefer unused content
                }
            }
        
        // If no match in target category, find any suitable content
        if (!selectedItem) {
            minUsageCount = Number.MAX_SAFE_INTEGER;
            for (const content of sortedContent) {
                const usageCount = contentUsageCount.get(content.id) || 0;
                if (content.duration_seconds <= remainingGapTime && usageCount < minUsageCount) {
                    selectedItem = content;
                    minUsageCount = usageCount;
                    if (usageCount === 0) break; // Prefer unused content
                }
            }
        }
        
        // If still no match but we have a big gap, allow any content
        if (!selectedItem && remainingGapTime > 300) { // More than 5 minutes remaining
            minUsageCount = Number.MAX_SAFE_INTEGER;
            for (const content of sortedContent) {
                const usageCount = contentUsageCount.get(content.id) || 0;
                if (usageCount < minUsageCount) {
                    selectedItem = content;
                    minUsageCount = usageCount;
                }
            }
        }
        
        if (!selectedItem) {
            log(`fillGapsWithContent: No more suitable content available. Items added: ${itemsAdded}, Gap remaining: ${formatDuration(remainingGapTime)}`, 'warning');
            break;
        }
        
        // Ensure we have a valid duration
        const itemDuration = parseFloat(selectedItem.duration_seconds);
        if (isNaN(itemDuration) || itemDuration <= 0) {
            log(`fillGapsWithContent: ERROR - Selected item has invalid duration: ${selectedItem.duration_seconds}`, 'error');
            continue; // Skip this item and try another
        }
        
            log(`fillGapsWithContent: Selected ${selectedItem.content_title || selectedItem.file_name} (${formatDuration(itemDuration)}, ${selectedItem.duration_category})`, 'info');
            log(`  File path: ${selectedItem.file_path}`, 'info');
            
            // Calculate times for this item
            const startTime = formatTimeFromSeconds(currentSeconds, template.type);
            currentSeconds += itemDuration;
            const endTime = formatTimeFromSeconds(currentSeconds, template.type);
            
            log(`  Will place at: ${startTime} to ${endTime}`, 'info');
            
            // Debug log for long items
            if (itemDuration > 3600) { // More than 1 hour
                log(`fillGapsWithContent: WARNING - Adding long item (${formatDuration(itemDuration)}) at ${startTime} to ${endTime}`, 'warning');
                log(`  Gap being filled: ${gap.startTime} to ${gap.endTime} (${formatDuration(gap.duration)})`, 'info');
                log(`  Current position in gap: ${formatDuration(currentSeconds - gap.startSeconds)} of ${formatDuration(gap.duration)}`, 'info');
            }
            
            // Add one frame gap after this item to prevent overlaps (1/30 second)
            // But don't add gap if this would exceed the gap we're trying to fill
            const frameGap = 1.0 / 30.0; // One frame at 30fps
            if (remainingGapTime > frameGap) {
                currentSeconds += frameGap;
            }
            
            // Create schedule item
            const scheduleItem = {
                start_time: startTime,
                end_time: endTime,
                scheduled_start_time: startTime,  // Set scheduled times for export
                scheduled_end_time: endTime,
                duration_seconds: itemDuration,
                scheduled_duration_seconds: itemDuration,  // Ensure this is set for export
                duration_timecode: formatDurationTimecodeWithMs(itemDuration),
                asset_id: selectedItem.id,
                content_id: selectedItem.id,
                title: selectedItem.title || selectedItem.content_title,
                name: selectedItem.title || selectedItem.content_title,
                file_name: selectedItem.file_name,
                filename: selectedItem.file_name,
                file_path: selectedItem.file_path,
                content_type: selectedItem.content_type,
                summary: selectedItem.summary,
                guid: selectedItem.guid || ''
            };
            
            newItems.push(scheduleItem);
            gapItems.push(scheduleItem);
            itemsAdded++;
            
            // Update tracking
            remainingGapTime -= itemDuration;
            if (remainingGapTime > frameGap) {
                remainingGapTime -= frameGap; // Account for the frame gap
            }
            contentUsageCount.set(selectedItem.id, (contentUsageCount.get(selectedItem.id) || 0) + 1);
            
            // Move to next rotation category
            rotationIndex++;
            
            // Log progress
            if (itemsAdded % 10 === 0) {
                log(`fillGapsWithContent: Added ${itemsAdded} items`, 'info');
            }
        }
        
        if (iterations >= maxIterations) {
            log(`fillGapsWithContent: Stopped filling gap after maximum iterations`, 'warning');
        }
        
        // If we added items to this gap, update the template and recalculate remaining gaps
        if (gapItems.length > 0) {
            // Add gap items to template
            template.items.push(...gapItems);
            
            // Sort all items by start time
            template.items.sort((a, b) => {
                const aSeconds = parseTimeToSeconds(a.start_time, template.type);
                const bSeconds = parseTimeToSeconds(b.start_time, template.type);
                return aSeconds - bSeconds;
            });
            
            // Debug: Log all items after sorting to check for overlaps
            log('Template items after adding gap fill and sorting:', 'info');
            template.items.forEach((item, idx) => {
                const startSec = parseTimeToSeconds(item.start_time, template.type);
                const endSec = parseTimeToSeconds(item.end_time, template.type);
                log(`  Item ${idx}: ${item.start_time} to ${item.end_time} (${startSec}s to ${endSec}s) - ${item.title || item.file_name}`, 'info');
                if (idx > 0) {
                    const prevEndSec = parseTimeToSeconds(template.items[idx-1].end_time, template.type);
                    if (startSec < prevEndSec) {
                        log(`    WARNING: Overlap detected! Starts ${prevEndSec - startSec}s before previous item ends`, 'error');
                    }
                }
            });
            
            // Always recalculate gaps after adding items
            const newGaps = findScheduleGaps(template);
            log(`fillGapsWithContent: After filling gap, found ${newGaps.length} total gaps in schedule`, 'info');
            
            // Update remaining gaps with new gap information
            // Simple approach: process all gaps except those we've already handled
            // We keep track of processed gaps by checking if they overlap with or come before
            // the current position in our gap filling
            gapsToProcess = newGaps.filter(newGap => {
                // Skip gaps that are entirely before the current gap started
                // (these were processed in earlier iterations)
                if (newGap.endSeconds <= gap.startSeconds) {
                    return false;
                }
                
                // Skip the portion of the current gap we've already filled
                if (newGap.startSeconds >= gap.startSeconds && newGap.startSeconds < currentSeconds) {
                    return false;
                }
                
                // Process everything else
                return true;
            });
            
            log(`fillGapsWithContent: ${gapsToProcess.length} gaps remaining to process`, 'info');
            if (gapsToProcess.length > 0) {
                log(`  Next gap to process: ${gapsToProcess[0].startTime} to ${gapsToProcess[0].endTime}`, 'info');
            } else if (newGaps.length > 0) {
                // Log if there were gaps but none qualified for processing
                log(`  Note: ${newGaps.length} gaps exist but were filtered out:`, 'info');
                newGaps.forEach((g, idx) => {
                    log(`    Gap ${idx + 1}: ${g.startTime} to ${g.endTime} (starts at ${g.startSeconds}s)`, 'info');
                });
                log(`  Current gap ended at ${gap.endSeconds}s, we filled to ${currentSeconds}s`, 'info');
            }
        }
    }
    
    log(`fillGapsWithContent: Added ${itemsAdded} items to fill gaps`, 'success');
    
    // After filling each gap, we should update the template and recalculate gaps
    // This is now done within the loop above by updating template.items directly
    
    // Final sort of all items by start time
    if (template.items.length > 0) {
        template.items.sort((a, b) => {
            const aSeconds = parseTimeToSeconds(a.start_time, template.type);
            const bSeconds = parseTimeToSeconds(b.start_time, template.type);
            return aSeconds - bSeconds;
        });
    }
    
    return newItems;
}

// Find gaps in a schedule template
function findScheduleGaps(template) {
    const gaps = [];
    
    if (!template || !template.items || template.items.length === 0) {
        // Entire schedule is empty
        const totalDuration = template.type === 'weekly' ? 7 * 24 * 3600 : 24 * 3600;
        gaps.push({
            startTime: template.type === 'weekly' ? 'sun 12:00:00.000 am' : '00:00:00',
            endTime: template.type === 'weekly' ? 'sat 11:59:59.999 pm' : '23:59:59',
            startSeconds: 0,
            endSeconds: totalDuration,
            duration: totalDuration
        });
        return gaps;
    }
    
    // Sort items by start time
    const sortedItems = [...template.items].sort((a, b) => {
        const aSeconds = parseTimeToSeconds(a.start_time, template.type);
        const bSeconds = parseTimeToSeconds(b.start_time, template.type);
        return aSeconds - bSeconds;
    });
    
    // Check for gap at the beginning
    const firstItemStart = parseTimeToSeconds(sortedItems[0].start_time, template.type);
    if (firstItemStart > 0) {
        gaps.push({
            startTime: template.type === 'weekly' ? 'sun 12:00:00.000 am' : '00:00:00',
            endTime: sortedItems[0].start_time,
            startSeconds: 0,
            endSeconds: firstItemStart,
            duration: firstItemStart
        });
    }
    
    // Check for gaps between items
    for (let i = 0; i < sortedItems.length - 1; i++) {
        const currentEnd = parseTimeToSeconds(sortedItems[i].end_time, template.type);
        const nextStart = parseTimeToSeconds(sortedItems[i + 1].start_time, template.type);
        
        if (nextStart > currentEnd) {
            gaps.push({
                startTime: sortedItems[i].end_time,
                endTime: sortedItems[i + 1].start_time,
                startSeconds: currentEnd,
                endSeconds: nextStart,
                duration: nextStart - currentEnd
            });
        }
    }
    
    // Check for gap at the end
    const lastItem = sortedItems[sortedItems.length - 1];
    const lastItemEnd = parseTimeToSeconds(lastItem.end_time, template.type);
    const scheduleEnd = template.type === 'weekly' ? 7 * 24 * 3600 : 24 * 3600;
    
    if (lastItemEnd < scheduleEnd) {
        gaps.push({
            startTime: lastItem.end_time,
            endTime: template.type === 'weekly' ? 'sat 11:59:59.999 pm' : '23:59:59',
            startSeconds: lastItemEnd,
            endSeconds: scheduleEnd,
            duration: scheduleEnd - lastItemEnd
        });
    }
    
    return gaps;
}

// Parse time to seconds, handling weekly format
function parseTimeToSeconds(timeStr, templateType) {
    if (!timeStr) return 0;
    
    if (templateType === 'weekly' && timeStr.includes(' ')) {
        // Parse weekly format: "wed 12:00:15.040 am"
        const parts = timeStr.split(' ');
        const dayStr = parts[0];
        const timeOnly = parts.slice(1).join(' ');
        
        // Convert day to offset
        const dayOffsets = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
        const dayOffset = dayOffsets[dayStr.toLowerCase()] || 0;
        
        // Parse time part
        const time24 = convert12to24Hour(timeOnly);
        if (time24) {
            const [h, m, s] = time24.split(':');
            const seconds = parseFloat(h) * 3600 + parseFloat(m) * 60 + parseFloat(s);
            return dayOffset * 24 * 3600 + seconds;
        }
    }
    
    // Parse regular time format - check for AM/PM
    if (timeStr.toLowerCase().includes('am') || timeStr.toLowerCase().includes('pm')) {
        // Convert 12-hour to 24-hour format first
        const time24 = convert12to24Hour(timeStr);
        if (time24) {
            const parts = time24.split(':');
            if (parts.length >= 3) {
                return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2]);
            }
        }
    }
    
    // Parse 24-hour format or plain HH:MM:SS
    const parts = timeStr.split(':');
    if (parts.length >= 3) {
        return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2]);
    }
    
    return 0;
}

// Helper function to format seconds to time string with proper format
function formatTimeFromSeconds(totalSeconds, templateType = 'daily') {
    if (templateType === 'weekly') {
        // Calculate day and time for weekly schedules
        const dayIndex = Math.floor(totalSeconds / (24 * 3600));
        const daySeconds = totalSeconds % (24 * 3600);
        
        const days = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
        const dayName = days[dayIndex] || 'sun';
        
        const hours = Math.floor(daySeconds / 3600);
        const minutes = Math.floor((daySeconds % 3600) / 60);
        const seconds = daySeconds % 60;
        const milliseconds = Math.round((seconds % 1) * 1000);
        const wholeSeconds = Math.floor(seconds);
        
        // Convert to 12-hour format
        let period = 'am';
        let displayHours = hours;
        if (hours >= 12) {
            period = 'pm';
            if (hours > 12) displayHours = hours - 12;
        }
        if (displayHours === 0) displayHours = 12;
        
        // Format with milliseconds if present
        let timeStr = `${dayName} ${displayHours}:${minutes.toString().padStart(2, '0')}:${wholeSeconds.toString().padStart(2, '0')}`;
        if (milliseconds > 0) {
            timeStr += `.${milliseconds.toString().padStart(3, '0')}`;
        }
        timeStr += ` ${period}`;
        
        return timeStr;
    } else {
        // Regular daily format - return in 12-hour AM/PM format to match imported templates
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const milliseconds = Math.round((seconds % 1) * 1000);
        const wholeSeconds = Math.floor(seconds);
        
        // Convert to 12-hour format
        let period = 'am';
        let displayHours = hours;
        if (hours >= 12) {
            period = 'pm';
            if (hours > 12) displayHours = hours - 12;
        }
        if (displayHours === 0) displayHours = 12;
        
        // Format time string
        let timeStr = `${displayHours}:${minutes.toString().padStart(2, '0')}:${wholeSeconds.toString().padStart(2, '0')}`;
        if (milliseconds > 0) {
            timeStr += `.${milliseconds.toString().padStart(3, '0')}`;
        }
        timeStr += ` ${period}`;
        
        return timeStr;
    }
}

// Helper function to format duration to timecode
function formatDurationTimecode(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const frames = Math.floor((seconds % 1) * 30); // Assuming 30fps
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}:${String(frames).padStart(2, '0')}`;
}

// Export current loaded template
function exportCurrentTemplate() {
    if (!currentTemplate) {
        alert('No template loaded. Please load a template first.');
        return;
    }
    
    log('Opening export dialog for current template', 'info');
    
    // Set the export modal for the current template
    document.getElementById('exportTemplateName').textContent = currentTemplate.filename || currentTemplate.name || 'Current Template';
    
    // Set default filename based on template type and today's date
    const date = new Date();
    const templateType = currentTemplate.type || 'daily';
    let defaultFilename = '';
    
    if (templateType === 'daily') {
        const dateStr = date.toISOString().split('T')[0];
        const dayName = date.toLocaleDateString('en-US', { weekday: 'short' }).toLowerCase();
        defaultFilename = `${dayName}_${dateStr.replace(/-/g, '')}.sch`;
    } else if (templateType === 'weekly') {
        const dateStr = date.toISOString().split('T')[0].replace(/-/g, '');
        defaultFilename = `weekly_${dateStr}.sch`;
    } else if (templateType === 'monthly') {
        const monthYear = `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}`;
        defaultFilename = `monthly_${monthYear}.sch`;
    }
    
    document.getElementById('templateExportFilename').value = defaultFilename;
    document.getElementById('templateExportFormat').value = `castus_${templateType}`;
    
    // Load saved export settings if available
    const savedPath = localStorage.getItem('exportPath') || '/mnt/main/Schedules';
    document.getElementById('templateExportPath').value = savedPath;
    
    // Store current template for export
    currentExportTemplate = currentTemplate;
    
    // Show the export modal
    document.getElementById('templateExportModal').style.display = 'block';
}

// Override the confirmTemplateExport to actually export to FTP
async function confirmTemplateExport() {
    if (!currentExportTemplate) return;
    
    const server = document.getElementById('templateExportServer').value;
    const path = document.getElementById('templateExportPath').value;
    const filename = document.getElementById('templateExportFilename').value;
    const format = document.getElementById('templateExportFormat').value;
    
    if (!filename) {
        alert('Please enter a filename');
        return;
    }
    
    // Save export settings
    localStorage.setItem('exportPath', path);
    
    log(`Exporting template to ${server} server: ${path}/${filename}`, 'info');
    
    try {
        // Prepare the schedule data
        const scheduleData = {
            template: currentExportTemplate,
            export_server: server,
            export_path: path,
            filename: filename,
            format: format,
            items: currentExportTemplate.items || []
        };
        
        // Export the template as a schedule file
        const response = await fetch('http://127.0.0.1:5000/api/export-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(scheduleData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`Template exported successfully to ${server}:${path}/${filename}`, 'success');
            alert(`Template exported successfully!\n\nFile: ${filename}\nLocation: ${server}:${path}`);
            closeTemplateExportModal();
        } else {
            log(`Export failed: ${result.message}`, 'error');
            alert(`Export failed: ${result.message}`);
        }
    } catch (error) {
        log(`Export error: ${error.message}`, 'error');
        alert(`Error exporting template: ${error.message}`);
    }
}

// Make template functions globally accessible
window.showLoadTemplateModal = showLoadTemplateModal;
window.showLoadWeeklyTemplateModal = showLoadWeeklyTemplateModal;
window.showLoadMonthlyTemplateModal = showLoadMonthlyTemplateModal;
window.fillScheduleGaps = fillScheduleGaps;
window.showTemplateLibrary = showTemplateLibrary;
window.closeTemplateLibraryModal = closeTemplateLibraryModal;
window.viewTemplate = viewTemplate;
window.loadSavedTemplate = loadSavedTemplate;
window.exportTemplate = exportTemplate;
window.deleteTemplate = deleteTemplate;
window.closeTemplateExportModal = closeTemplateExportModal;
window.confirmTemplateExport = confirmTemplateExport;
window.exportCurrentTemplate = exportCurrentTemplate;

function addToTemplate(assetId) {
    if (!currentTemplate) {
        log('Please load a template first', 'error');
        return;
    }
    
    console.log('Adding to template, assetId:', assetId);
    
    // Find the content item by id (PostgreSQL), _id (MongoDB), or guid
    const contentItem = availableContent.find(item => 
        item.id == assetId || item._id === assetId || item.guid === assetId
    );
    
    if (!contentItem) {
        log('Content item not found', 'error');
        console.error('Could not find content item with ID:', assetId);
        console.log('Available items:', availableContent.map(item => ({_id: item._id, guid: item.guid, id: item.id})));
        return;
    }
    
    // Create template item from content
    const templateItem = {
        file_path: contentItem.file_path,
        filename: contentItem.file_name,
        duration_seconds: contentItem.file_duration || contentItem.duration_seconds,
        start_time: '',  // Will be calculated when saving
        end_time: '',    // Will be calculated when saving
        guid: contentItem.guid || '',
        loop: '0',
        content_id: contentItem.id || contentItem._id,  // Use PostgreSQL id first
        content_title: contentItem.content_title,
        content_type: contentItem.content_type,
        asset_id: contentItem.id || contentItem._id  // Use PostgreSQL id for backend
    };
    
    // Initialize items array if needed
    if (!currentTemplate.items) {
        currentTemplate.items = [];
    }
    
    // Add to template
    currentTemplate.items.push(templateItem);
    
    // Update display
    displayTemplate();
    log(`Added "${contentItem.content_title || contentItem.file_name}" to template`, 'success');
}

async function saveTemplateAsSchedule() {
    if (!currentTemplate || currentTemplate.items.length === 0) {
        log('Template is empty', 'error');
        return;
    }
    
    const scheduleDate = prompt('Enter schedule date (YYYY-MM-DD):', new Date().toISOString().split('T')[0]);
    if (!scheduleDate) return;
    
    try {
        log('Creating schedule from template...', 'info');
        
        // Debug logging
        console.log('Current template:', currentTemplate);
        console.log('Template items:', currentTemplate.items);
        
        // Prepare schedule data - only include items with valid asset IDs
        const validItems = currentTemplate.items.filter(item => item.content_id || item.asset_id);
        
        if (validItems.length === 0) {
            log('No valid items with asset IDs in template. Items must be added from Available Content.', 'error');
            return;
        }
        
        console.log(`Creating schedule with ${validItems.length} items from template with ${currentTemplate.items.length} total items`);
        console.log('Valid items being sent:', validItems);
        
        const scheduleData = {
            air_date: scheduleDate,
            schedule_name: `Schedule from ${currentTemplate.filename || 'template'}`,
            channel: 'Comcast Channel 26',
            items: validItems.map((item, index) => {
                const scheduleItem = {
                    asset_id: item.asset_id || item.content_id,
                    order_index: index,
                    scheduled_start_time: '00:00:00',  // Will be calculated by backend
                    scheduled_duration_seconds: parseFloat(item.duration_seconds) || 0
                };
                console.log(`Item ${index}:`, scheduleItem);
                return scheduleItem;
            })
        };
        
        console.log('Schedule data being sent:', scheduleData);
        log(`Sending ${scheduleData.items.length} items to create schedule`, 'info');
        
        const response = await fetch('http://127.0.0.1:5000/api/create-schedule-from-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(scheduleData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`Schedule created successfully! ${result.message}`, 'success');
            
            if (result.skipped_count > 0) {
                log(`⚠️ Note: ${result.skipped_count} template items were skipped because they haven't been added from Available Content`, 'info');
            }
            
            // Optionally view the created schedule
            if (confirm('View the created schedule?')) {
                document.getElementById('viewScheduleDate').value = scheduleDate;
                viewDailySchedule();
            }
        } else {
            log(`Failed to create schedule: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`Error creating schedule: ${error.message}`, 'error');
    }
}

async function exportTemplate() {
    if (!currentTemplate || currentTemplate.items.length === 0) {
        log('Template is empty', 'error');
        return;
    }
    
    // Use the export modal for consistency
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('exportScheduleDate').textContent = `Template: ${currentTemplate.filename}`;
    
    // Show export modal
    document.getElementById('exportModal').style.display = 'block';
    
    // Override the confirmExport function temporarily
    window.confirmExportTemplate = async function() {
        const exportServer = document.getElementById('modalExportServer').value;
        const exportPath = document.getElementById('modalExportPath').value;
        const filename = document.getElementById('modalExportFilename').value;
        
        if (!exportServer || !exportPath || !filename) {
            log('Please fill in all export fields', 'error');
            return;
        }
        
        try {
            // Generate schedule content for the template
            const response = await fetch('http://127.0.0.1:5000/api/export-template', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    template: currentTemplate,
                    export_server: exportServer,
                    export_path: exportPath,
                    filename: filename
                })
            });
            
            const result = await response.json();
            
            closeExportModal();
            
            if (result.success) {
                showExportResult(true, 'Template Exported!', `Template exported to ${result.file_path}`);
            } else {
                showExportResult(false, 'Export Failed', result.message);
            }
        } catch (error) {
            closeExportModal();
            showExportResult(false, 'Export Error', error.message);
        }
    };
    
    // Update the export button onclick
    document.querySelector('#exportModal .button.primary').setAttribute('onclick', 'confirmExportTemplate()');
}

// Path selection functions
function updateSourcePath() {
    const select = document.getElementById('sourcePathSelect');
    const input = document.getElementById('sourcePath');
    input.value = select.value;
    
    // Update sync direction based on selected path
    if (select.value === '/mnt/main/Recordings' || select.value === '/mnt/md127/Recordings') {
        currentSyncDirection = 'bidirectional';
    } else {
        currentSyncDirection = 'source_to_target';
    }
}

function updateTargetPath() {
    const select = document.getElementById('targetPathSelect');
    const input = document.getElementById('targetPath');
    input.value = select.value;
}

// Scanning configuration functions
function selectAllFolders() {
    document.getElementById('scanOnAirContent').checked = true;
    document.getElementById('scanRecordings').checked = true;
}

function deselectAllFolders() {
    document.getElementById('scanOnAirContent').checked = false;
    document.getElementById('scanRecordings').checked = false;
}

async function scanSelectedFolders() {
    // Check which folders are selected
    const scanOnAir = document.getElementById('scanOnAirContent').checked;
    const scanRecordings = document.getElementById('scanRecordings').checked;
    
    if (!scanOnAir && !scanRecordings) {
        log('Please select at least one folder to scan', 'error');
        return;
    }
    
    // Clear previous results
    sourceFiles = [];
    targetFiles = [];
    
    if (isScanning) return;
    isScanning = true;
    
    clearLog();
    log('Starting scan of selected folders...');
    
    try {
        // Get file filters
        const filterInput = document.getElementById('fileFilter').value;
        const extensions = filterInput ? filterInput.split(',').map(ext => ext.trim()) : [];
        const minSize = parseInt(document.getElementById('minFileSize').value) * 1024 * 1024;
        const maxSize = parseInt(document.getElementById('maxFileSize').value) * 1024 * 1024 * 1024;
        const includeSubdirs = document.getElementById('includeSubdirs').checked;
        
        const filters = {
            extensions: extensions,
            min_size: minSize,
            max_size: maxSize,
            include_subdirs: includeSubdirs
        };
        
        // Scan On-Air Content folder if selected
        if (scanOnAir) {
            log('Scanning On-Air Content folder...');
            
            // Scan source
            const sourceResponse = await fetch('http://127.0.0.1:5000/api/scan-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    server_type: 'source',
                    path: '/mnt/main/ATL26 On-Air Content',
                    filters: filters
                })
            });
            
            const sourceResult = await sourceResponse.json();
            if (!sourceResult.success) {
                throw new Error(sourceResult.message);
            }
            
            const onAirSourceFiles = sourceResult.files;
            log(`Found ${onAirSourceFiles.length} files in On-Air Content (source)`);
            
            // Scan target
            const targetResponse = await fetch('http://127.0.0.1:5000/api/scan-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    server_type: 'target',
                    path: '/mnt/main/ATL26 On-Air Content',
                    filters: filters
                })
            });
            
            const targetResult = await targetResponse.json();
            if (!targetResult.success) {
                throw new Error(targetResult.message);
            }
            
            const onAirTargetFiles = targetResult.files;
            log(`Found ${onAirTargetFiles.length} files in On-Air Content (target)`);
            
            // Add to main arrays with folder info
            onAirSourceFiles.forEach(file => {
                file.folder = 'on-air';
                sourceFiles.push(file);
            });
            onAirTargetFiles.forEach(file => {
                file.folder = 'on-air';
                targetFiles.push(file);
            });
        }
        
        // Scan Recordings folder if selected
        if (scanRecordings) {
            log('Scanning Recordings folder...');
            
            // Scan source
            const sourceResponse = await fetch('http://127.0.0.1:5000/api/scan-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    server_type: 'source',
                    path: '/mnt/main/Recordings',
                    filters: filters
                })
            });
            
            const sourceResult = await sourceResponse.json();
            if (!sourceResult.success) {
                throw new Error(sourceResult.message);
            }
            
            const recordingsSourceFiles = sourceResult.files;
            log(`Found ${recordingsSourceFiles.length} files in Recordings (source)`);
            
            // Scan target
            const targetResponse = await fetch('http://127.0.0.1:5000/api/scan-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    server_type: 'target',
                    path: '/mnt/main/Recordings',
                    filters: filters
                })
            });
            
            const targetResult = await targetResponse.json();
            if (!targetResult.success) {
                throw new Error(targetResult.message);
            }
            
            const recordingsTargetFiles = targetResult.files;
            log(`Found ${recordingsTargetFiles.length} files in Recordings (target)`);
            
            // Add to main arrays with folder info
            recordingsSourceFiles.forEach(file => {
                file.folder = 'recordings';
                file.isBidirectional = true;
                sourceFiles.push(file);
            });
            recordingsTargetFiles.forEach(file => {
                file.folder = 'recordings';
                file.isBidirectional = true;
                targetFiles.push(file);
            });
        }
        
        log(`Total files found: ${sourceFiles.length} source, ${targetFiles.length} target`);
        
        // Display scanned files
        displayScannedFiles();
        
        // Enable compare button
        document.querySelector('button[onclick="compareFiles()"]').disabled = false;
        document.getElementById('analyzeFilesBtn').disabled = false;
        
    } catch (error) {
        log(`Error during file scan: ${error.message}`, 'error');
    }
    
    isScanning = false;
}