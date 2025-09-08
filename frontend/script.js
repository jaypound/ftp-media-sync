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
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${type}`;
    logEntry.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${prefix} ${message}`;
    status.appendChild(logEntry);
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
    const targetFileByNameMap = new Map();
    const duplicateTargetNames = new Set();
    
    targetFiles.forEach(file => {
        const relativePath = file.path || file.name;
        targetFileMap.set(relativePath, file);
        
        // Track duplicate names
        if (targetFileByNameMap.has(file.name)) {
            duplicateTargetNames.add(file.name);
            console.log(`Duplicate target file name: ${file.name}`);
            console.log(`  Path 1: ${targetFileByNameMap.get(file.name).path}`);
            console.log(`  Path 2: ${file.path}`);
        }
        targetFileByNameMap.set(file.name, file);
    });
    
    // Create a map of source files for quick lookup using relative path
    const sourceFileMap = new Map();
    const sourceFileByNameMap = new Map();
    const duplicateSourceNames = new Set();
    
    sourceFiles.forEach(file => {
        const relativePath = file.path || file.name;
        sourceFileMap.set(relativePath, file);
        
        // Track duplicate names
        if (sourceFileByNameMap.has(file.name)) {
            duplicateSourceNames.add(file.name);
            console.log(`Duplicate source file name: ${file.name}`);
            console.log(`  Path 1: ${sourceFileByNameMap.get(file.name).path}`);
            console.log(`  Path 2: ${file.path}`);
        }
        sourceFileByNameMap.set(file.name, file);
    });
    
    if (duplicateTargetNames.size > 0) {
        console.log(`Found ${duplicateTargetNames.size} duplicate file names in target`);
    }
    if (duplicateSourceNames.size > 0) {
        console.log(`Found ${duplicateSourceNames.size} duplicate file names in source`);
    }
    
    // Debug: Log sample paths from both servers
    console.log('Source file count:', sourceFiles.length);
    console.log('Target file count:', targetFiles.length);
    console.log('Source map size:', sourceFileMap.size);
    console.log('Target map size:', targetFileMap.size);
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
        // Try to find target file by path first, then by name
        let targetFile = targetFileMap.get(sourceRelativePath);
        if (!targetFile && sourceFile.path !== sourceFile.name) {
            // Try matching by name only if path lookup failed
            targetFile = targetFileByNameMap.get(sourceFile.name);
            if (targetFile) {
                log(`Matched ${sourceFile.name} by filename (path mismatch: source='${sourceRelativePath}' vs target='${targetFile.path || targetFile.name}')`);
            }
        }
        
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
    console.log(`Processing ${targetFiles.length} target files to find target-only files`);
    let targetOnlyCount = 0;
    
    targetFiles.forEach(targetFile => {
        const targetRelativePath = targetFile.path || targetFile.name;
        // Try to find source file by path first, then by name
        let sourceFile = sourceFileMap.get(targetRelativePath);
        let matchedBy = sourceFile ? 'path' : null;
        
        if (!sourceFile && targetFile.path !== targetFile.name) {
            // Try matching by name only if path lookup failed
            sourceFile = sourceFileByNameMap.get(targetFile.name);
            if (sourceFile) {
                matchedBy = 'name';
                console.log(`Matched ${targetFile.name} by NAME ONLY - Target path: '${targetRelativePath}' vs Source path: '${sourceFile.path || sourceFile.name}'`);
                log(`Matched ${targetFile.name} by filename for target-only check (path mismatch: target='${targetRelativePath}' vs source='${sourceFile.path || sourceFile.name}')`);
            }
        }
        
        if (!sourceFile) {
            targetOnlyCount++;
            // File exists on target but not on source
            console.log(`Target-only file #${targetOnlyCount}: ${targetRelativePath}`, targetFile);
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
            
            // Add ALL target-only files as copyable from target to source
            availableFiles.push({ 
                type: 'copy', 
                file: targetFile, 
                id: fileId, 
                direction: 'target_to_source',
                isTargetOnly: true 
            });
        }
    });
    
    // Update summary
    updateComparisonSummary();
    
    // Render results (default to unsynced only)
    renderComparisonResults();
    
    console.log(`Final targetOnlyCount: ${targetOnlyCount}`);
    console.log(`targetOnlyFiles array length: ${targetOnlyFiles.length}`);
    console.log('targetOnlyFiles:', targetOnlyFiles);
    
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
        fileListDiv.classList.remove('dashboard-comparison-container');
        targetOnlyFiles.forEach(result => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item target-only';
            
            const isBidirectional = result.targetFile.isBidirectional;
            const isInQueue = syncQueue.find(item => item.id === result.fileId);
            const isInDeleteQueue = deleteQueue.find(item => item.fileId === result.fileId);
            
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${result.targetFile.name}</div>
                    <div class="file-path">${result.relativePath !== result.targetFile.name ? result.relativePath : ''}</div>
                    <div class="file-size">${formatFileSize(result.targetFile.size)} - Only on target</div>
                </div>
                <div class="file-actions">
                    <button class="button add-to-sync-btn ${isInQueue ? 'added' : ''}" 
                            onclick="addToSyncQueue('${result.fileId}', this)"
                            ${isInQueue ? 'disabled' : ''}>
                        ${isInQueue ? '<i class="fas fa-check"></i> Added to Sync' : '<i class="fas fa-arrow-left"></i> Copy to Source'}
                    </button>
                    <button class="delete-btn ${isInDeleteQueue ? 'added' : ''}" 
                            onclick="addToDeleteQueue('${result.fileId}')"
                            ${isInDeleteQueue ? 'disabled' : ''}>
                        <i class="fas fa-trash"></i> ${isInDeleteQueue ? 'Marked for Deletion' : 'Delete'}
                    </button>
                </div>
            `;
            
            fileListDiv.appendChild(fileItem);
        });
    } else {
        // Show source/target comparison results in side-by-side layout
        fileListDiv.classList.add('dashboard-comparison-container');
        
        // Create sections for side-by-side layout
        const sourceSection = document.createElement('div');
        sourceSection.className = 'dashboard-comparison-section';
        sourceSection.innerHTML = '<h4><i class="fas fa-exchange-alt"></i> Source/Target Differences</h4>';
        
        const targetSection = document.createElement('div');
        targetSection.className = 'dashboard-comparison-section';
        targetSection.innerHTML = '<h4><i class="fas fa-folder-plus"></i> Target-Only Files</h4>';
        
        // Add files that need syncing to source section
        const resultsToShow = showAllFiles ? allComparisonResults : allComparisonResults.filter(result => 
            result.status !== 'identical' || result.justSynced
        );
        let hasSourceDifferences = false;
        
        console.log('Rendering comparison results:', {
            totalResults: allComparisonResults.length,
            resultsToShow: resultsToShow.length,
            syncQueue: syncQueue.length,
            availableFiles: availableFiles.length,
            justSyncedCount: allComparisonResults.filter(r => r.justSynced).length,
            identicalCount: allComparisonResults.filter(r => r.status === 'identical').length
        });
        
        resultsToShow.forEach(result => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            
            if (result.status === 'missing') {
                hasSourceDifferences = true;
                // File missing on target
                fileItem.classList.add('missing');
                const isInQueue = syncQueue.find(item => item.id === result.fileId);
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.sourceFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.sourceFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">${formatFileSize(result.sourceFile.size)} - Missing on target</div>
                    </div>
                    <div class="file-actions">
                        <button class="button add-to-sync-btn ${isInQueue ? 'added' : ''}" 
                                onclick="addToSyncQueue('${result.fileId}', this)"
                                ${isInQueue ? 'disabled' : ''}>
                            ${isInQueue ? '<i class="fas fa-check"></i> Added to Sync' : 'Add to Sync'}
                        </button>
                        <button class="delete-btn" 
                                onclick="addToDeleteQueue('${result.fileId}')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                `;
            } else if (result.status === 'different') {
                hasSourceDifferences = true;
                // File size different
                fileItem.classList.add('different');
                const isInQueue = syncQueue.find(item => item.id === result.fileId);
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.sourceFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.sourceFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">Source: ${formatFileSize(result.sourceFile.size)} | Target: ${formatFileSize(result.targetFile.size)}</div>
                    </div>
                    <div class="file-actions">
                        <button class="button add-to-sync-btn ${isInQueue ? 'added' : ''}" 
                                onclick="addToSyncQueue('${result.fileId}', this)"
                                ${isInQueue ? 'disabled' : ''}>
                            ${isInQueue ? '<i class="fas fa-check"></i> Added to Sync' : 'Add to Sync'}
                        </button>
                        <button class="delete-btn" 
                                onclick="addToDeleteQueue('${result.fileId}')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                `;
            } else {
                // File identical or just synced
                const syncedText = result.justSynced ? 'Just Synced' : 'Identical';
                fileItem.classList.add('synced');
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.sourceFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.sourceFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">${formatFileSize(result.sourceFile.size)} - ${syncedText}</div>
                    </div>
                    <span style="color: #28a745;">✅ Synced</span>
                `;
            }
            
            sourceSection.appendChild(fileItem);
        });
        
        // Add placeholder if no source differences
        if (!hasSourceDifferences && !showAllFiles) {
            const placeholder = document.createElement('div');
            placeholder.className = 'dashboard-empty-state';
            placeholder.innerHTML = '<p style="color: #666; text-align: center;">All files are in sync</p>';
            sourceSection.appendChild(placeholder);
        }
        
        // Add target-only files to target section
        if (targetOnlyFiles.length > 0) {
            targetOnlyFiles.forEach(result => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item target-only';
                
                const isBidirectional = result.targetFile.isBidirectional;
                const isInQueue = syncQueue.find(item => item.id === result.fileId);
                const isInDeleteQueue = deleteQueue.find(item => item.fileId === result.fileId);
                
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.targetFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.targetFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">${formatFileSize(result.targetFile.size)} - Only on target</div>
                    </div>
                    <div class="file-actions">
                        <button class="button add-to-sync-btn ${isInQueue ? 'added' : ''}" 
                                onclick="addToSyncQueue('${result.fileId}', this)"
                                ${isInQueue ? 'disabled' : ''}>
                            ${isInQueue ? '<i class="fas fa-check"></i> Added to Sync' : '<i class="fas fa-arrow-left"></i> Copy to Source'}
                        </button>
                        <button class="delete-btn ${isInDeleteQueue ? 'added' : ''}" 
                                onclick="addToDeleteQueue('${result.fileId}')"
                                ${isInDeleteQueue ? 'disabled' : ''}>
                            <i class="fas fa-trash"></i> ${isInDeleteQueue ? 'Marked for Deletion' : 'Delete'}
                        </button>
                    </div>
                `;
                
                targetSection.appendChild(fileItem);
            });
        } else {
            const placeholder = document.createElement('div');
            placeholder.className = 'dashboard-empty-state';
            placeholder.innerHTML = '<p style="color: #666; text-align: center;">No target-only files</p>';
            targetSection.appendChild(placeholder);
        }
        
        // Append both sections to the container
        fileListDiv.appendChild(sourceSection);
        fileListDiv.appendChild(targetSection);
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
    
    // Show search container immediately when card is shown
    const searchContainer = document.getElementById('scannedFilesSearchContainer');
    if (searchContainer) {
        searchContainer.style.display = 'inline-flex';
    }
    
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
    sourceFileCount.setAttribute('data-original-text', sourceCountText);
    sourceFileCount.className = filteredSourceFiles.length > 0 ? 'file-count has-files' : 'file-count';
    
    targetFileCount.textContent = `${targetFiles.length} files found`;
    targetFileCount.setAttribute('data-original-text', `${targetFiles.length} files found`);
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
            <div class="file-info">
                <div class="file-name">${file.name}</div>
                <div class="file-size">${formatFileSize(file.size)}</div>
                <div class="file-path">${file.path || file.name}</div>
            </div>
            <div class="file-actions">
                ${isAnalyzed ? '<span class="analyzed-status">✅ Analyzed</span>' : ''}
                ${isVideoFile ? `
                    <button class="button analyze-btn ${isAnalyzed ? 'analyzed' : ''}" 
                            onclick="addToAnalysisQueue('${btoa(file.path || file.name).replace(/[^a-zA-Z0-9]/g, '')}')" 
                            data-file-path="${file.path || file.name}"
                            data-is-analyzed="${isAnalyzed}">
                        <i class="fas fa-${isAnalyzed ? 'redo' : 'brain'}"></i> ${isAnalyzed ? 'Reanalyze' : 'Analyze'}
                    </button>
                ` : ''}
            </div>
        `;
        sourceFilesList.appendChild(fileItem);
    });
    
    // Display target files
    targetFilesList.innerHTML = '';
    targetFiles.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'scanned-file-item';
        fileItem.innerHTML = `
            <div class="file-info">
                <div class="file-name">${file.name}</div>
                <div class="file-size">${formatFileSize(file.size)}</div>
                <div class="file-path">${file.path || file.name}</div>
            </div>
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
    
    // Update dashboard stats to show new sync queue count
    updateDashboardStats();
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
        updateDashboardStats();
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
    
    // Don't reset buttons here - let renderComparisonResults handle the UI update
    // This preserves the synced state of files
    
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
            
            // Remove successfully synced file from the appropriate lists
            const fileId = item.id;
            const fileName = item.file;
            
            // Debug logging
            console.log('Sync success - updating UI for:', {
                fileId: fileId,
                fileName: fileName,
                direction: item.direction
            });
            
            // Remove from available files
            const beforeCount = availableFiles.length;
            availableFiles = availableFiles.filter(f => f.id !== fileId);
            console.log(`Available files: ${beforeCount} -> ${availableFiles.length}`);
            
            // Update comparison results to mark as synced
            let updatedCount = 0;
            allComparisonResults = allComparisonResults.map(result => {
                if (result.fileId === fileId || result.relativePath === fileName || result.sourceFile?.name === fileName) {
                    console.log('Marking comparison result as synced:', {
                        before: result.status,
                        fileId: result.fileId,
                        fileName: result.sourceFile?.name
                    });
                    result.status = 'identical'; // Mark as synced
                    result.justSynced = true; // Add flag for UI indication
                    updatedCount++;
                }
                return result;
            });
            console.log(`Updated ${updatedCount} comparison results to synced status`);
            
            // Update the UI immediately for this specific file
            console.log('Calling updateFileItemUI for:', fileId, fileName);
            updateFileItemUI(fileId, fileName, 'synced');
            
            // Also try to update by finding the correct result
            const resultToUpdate = allComparisonResults.find(r => 
                r.fileId === fileId || 
                r.relativePath === fileName || 
                r.sourceFile?.name === fileName
            );
            console.log('Found result to update:', resultToUpdate);
            
            // For source-to-target syncs, add the file to targetFiles array
            if (item.direction === 'source_to_target' || !item.direction) {
                // Find the source file details
                const sourceFile = sourceFiles.find(f => f.name === fileName || f.path === item.file);
                if (sourceFile) {
                    // Add to target files if not already there
                    if (!targetFiles.find(f => f.name === fileName)) {
                        targetFiles.push({
                            name: sourceFile.name,
                            size: sourceFile.size,
                            path: sourceFile.path
                        });
                    }
                }
            }
            
            // Remove from target-only list if it was a target-to-source sync
            if (item.direction === 'target_to_source') {
                targetOnlyFiles = targetOnlyFiles.filter(f => f.fileId !== fileId);
                log(`Debug: Removed ${item.file} from target-only list (${targetOnlyFiles.length} remaining)`);
            }
            
            // Remove from sync queue
            syncQueue = syncQueue.filter(q => q.id !== fileId);
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
        const result = await window.API.get('/config');
        
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
        
        const result = await window.API.post('/config', config);
        
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
        const result = await window.API.post('/config/sample');
        
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
        const response = await fetch('/api/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        
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
        const sourceResponse = await fetch('/api/scan-files', {
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
        const targetResponse = await fetch('/api/scan-files', {
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
        
        // Update dashboard stats to show file count
        updateDashboardStats();
        
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
        
        const response = await fetch('/api/sync-files', {
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
            
            // Clear the sync queue and update UI after successful sync
            if (!dryRun && syncStats.errors === 0) {
                // First update the data, then clear queue and render
                console.log('Sync complete - updating UI');
                console.log('Available files before:', availableFiles.length);
                console.log('All comparison results:', allComparisonResults.length);
                console.log('Synced files (justSynced=true):', allComparisonResults.filter(r => r.justSynced).length);
                
                clearSyncQueue();
                // Update the comparison display to reflect removed files
                updateComparisonSummary();
                
                // Force a re-render to show synced status
                setTimeout(() => {
                    console.log('Rendering comparison results with synced items');
                    renderComparisonResults();
                    // Update dashboard stats to reflect new file counts
                    updateDashboardStats();
                    // Update the file counts in the scanned files display
                    updateScannedFileCounts();
                    // Update the server file counts based on synced files
                    updateServerFileCounts();
                }, 100);
                
                // Show notification of successful sync
                showNotification('Sync Complete', `Successfully synced ${syncStats.processed} files`, 'success');
            } else if (dryRun && syncStats.errors === 0) {
                // For dry run, show what would have been done
                showNotification('Dry Run Complete', `Would have synced ${syncStats.processed} files`, 'info');
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
    document.getElementById('stopButton').disabled = true;
    
    // Update sync button state based on whether there are items in the queue
    updateSyncButtonState();
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
    
    // Show/hide Meeting Trimmer based on panel - show on dashboard
    const meetingTrimmerCard = document.getElementById('meetingTrimmerCard');
    if (meetingTrimmerCard) {
        meetingTrimmerCard.style.display = (panelName === 'dashboard') ? 'block' : 'none';
    }
    
    // Show/hide Status & Logs based on panel - only show on dashboard
    const statusLogsCard = document.querySelector('.card:has(.fa-terminal)');
    if (statusLogsCard) {
        statusLogsCard.style.display = (panelName === 'dashboard') ? 'block' : 'none';
    }
    
    // Update AppState current panel
    if (window.AppState) {
        window.AppState.setCurrentPanel(panelName);
    }
    
    // Dispatch custom event for panel change
    window.dispatchEvent(new CustomEvent('panelChanged', { detail: { panel: panelName } }));
    
    // Panel-specific actions
    switch(panelName) {
        case 'dashboard':
            if (window.dashboardUpdateStats) {
                window.dashboardUpdateStats();
            } else {
                updateDashboardStats(); // Legacy fallback
            }
            break;
        case 'ai-settings':
            loadAISettings();
            break;
        case 'scheduling':
            // Module will handle its own initialization
            break;
        case 'servers':
            // Module will handle its own initialization
            break;
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
        const result = await window.API.get('/health');
        
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
    const contentTypeFilter = document.getElementById('scannedFilesContentTypeFilter');
    
    if (detailsDiv.style.display === 'none') {
        detailsDiv.style.display = 'grid';
        summaryDiv.style.display = 'none';
        toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Details';
        filterBtn.style.display = 'inline-block'; // Show filter button when details are shown
        
        // Show content type filter when details are shown
        if (contentTypeFilter) {
            contentTypeFilter.style.display = 'inline-block';
        }
    } else {
        detailsDiv.style.display = 'none';
        summaryDiv.style.display = 'block';
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show Details';
        filterBtn.style.display = 'none'; // Hide filter button when details are hidden
        
        // Hide content type filter when details are hidden
        if (contentTypeFilter) {
            contentTypeFilter.style.display = 'none';
        }
        // Note: Search container stays visible
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
    
    if (body.classList.contains('dark-mode')) {
        body.classList.remove('dark-mode');
        darkModeToggle.innerHTML = '<i class="fas fa-moon"></i> Dark';
        localStorage.setItem('theme', 'light');
    } else {
        body.classList.add('dark-mode');
        darkModeToggle.innerHTML = '<i class="fas fa-sun"></i> Light';
        localStorage.setItem('theme', 'dark');
    }
}

function initializeTheme() {
    const savedTheme = localStorage.getItem('theme');
    const body = document.body;
    const darkModeToggle = document.getElementById('darkModeToggle');
    
    if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        body.classList.add('dark-mode');
        darkModeToggle.innerHTML = '<i class="fas fa-sun"></i> Light';
    } else {
        body.classList.remove('dark-mode');
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
        const result = await window.API.get('/ai-config');
        
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
            // Load Ollama URL if configured
            if (config.ollama_url) {
                document.getElementById('ollamaUrl').value = config.ollama_url;
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
            ollama_url: document.getElementById('ollamaUrl').value,
            max_chunk_size: parseInt(document.getElementById('maxChunkSize').value) || 4000,
            enable_batch_analysis: true
        };
        
        const response = await fetch('/api/ai-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ai_analysis: aiConfig })
        });
        
        
        
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
    const ollamaUrlGroup = document.getElementById('ollamaUrlGroup');
    
    // Clear existing options
    modelSelect.innerHTML = '';
    
    // Show/hide Ollama URL field
    if (ollamaUrlGroup) {
        ollamaUrlGroup.style.display = provider === 'ollama' ? 'block' : 'none';
    }
    
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
    } else if (provider === 'ollama') {
        // Common Ollama models
        modelSelect.innerHTML = `
            <option value="llama2">Llama 2</option>
            <option value="llama3">Llama 3</option>
            <option value="mistral">Mistral</option>
            <option value="mixtral">Mixtral</option>
            <option value="codellama">Code Llama</option>
            <option value="phi">Phi</option>
            <option value="neural-chat">Neural Chat</option>
            <option value="starling-lm">Starling LM</option>
            <option value="orca-mini">Orca Mini</option>
        `;
    }
    
    // Try to restore previous value, or set default
    if (Array.from(modelSelect.options).some(option => option.value === currentValue)) {
        modelSelect.value = currentValue;
    } else {
        if (provider === 'openai') {
            modelSelect.value = 'gpt-3.5-turbo';
        } else if (provider === 'anthropic') {
            modelSelect.value = 'claude-3-sonnet-20240229';
        } else if (provider === 'ollama') {
            modelSelect.value = 'llama2';
        }
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
    
    // Add backup event listeners for template library modal close buttons
    const templateLibraryCloseBtn = document.querySelector('#templateLibraryModal .modal-close');
    const templateLibraryCloseFooterBtn = document.querySelector('#templateLibraryModal .modal-footer .button.secondary');
    
    if (templateLibraryCloseBtn) {
        templateLibraryCloseBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Template library X button clicked (event listener)');
            closeTemplateLibraryModal();
        });
    }
    
    if (templateLibraryCloseFooterBtn) {
        templateLibraryCloseFooterBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Template library Close button clicked (event listener)');
            closeTemplateLibraryModal();
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
        const response = await fetch('/api/analysis-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: sourceFiles })
        });
        
        
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
        const configResponse = await fetch('/api/ai-config');
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
            
            const response = await fetch('/api/analyze-files', {
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
        
        const response = await fetch('/api/clear-all-analyses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        
        
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
let currentDeleteFile = null; // Store the current file being deleted

function addToDeleteQueue(fileId) {
    console.log('addToDeleteQueue called with fileId:', fileId);
    
    // Find the file in targetOnlyFiles
    const targetOnlyFile = targetOnlyFiles.find(item => item.fileId === fileId);
    if (!targetOnlyFile) {
        // Try to find in all comparison results (for files that exist on both servers)
        const comparisonResult = allComparisonResults.find(item => item.fileId === fileId);
        if (!comparisonResult) {
            log(`File with ID ${fileId} not found`, 'error');
            return;
        }
        // Show delete options modal for files that exist on both servers
        showDeleteOptionsModal(comparisonResult);
        return;
    }
    
    // For target-only files, show delete options modal
    showDeleteOptionsModal(targetOnlyFile);
}

function showDeleteOptionsModal(fileInfo) {
    currentDeleteFile = fileInfo;
    
    // Populate modal with file info
    const fileName = fileInfo.targetFile?.name || fileInfo.sourceFile?.name || 'Unknown';
    const filePath = fileInfo.relativePath || fileInfo.targetFile?.path || fileInfo.sourceFile?.path || '';
    const fileSize = fileInfo.targetFile?.size || fileInfo.sourceFile?.size || 0;
    
    document.getElementById('deleteFileName').textContent = fileName;
    document.getElementById('deleteFilePath').textContent = filePath;
    document.getElementById('deleteFileSize').textContent = formatFileSize(fileSize);
    
    // Set checkbox states based on where the file exists
    const sourceCheckbox = document.getElementById('deleteFromSource');
    const targetCheckbox = document.getElementById('deleteFromTarget');
    
    // Enable/disable checkboxes based on file existence
    if (fileInfo.sourceFile) {
        sourceCheckbox.disabled = false;
        sourceCheckbox.parentElement.style.opacity = '1';
    } else {
        sourceCheckbox.disabled = true;
        sourceCheckbox.checked = false;
        sourceCheckbox.parentElement.style.opacity = '0.5';
    }
    
    if (fileInfo.targetFile) {
        targetCheckbox.disabled = false;
        targetCheckbox.parentElement.style.opacity = '1';
        targetCheckbox.checked = true; // Default to target
    } else {
        targetCheckbox.disabled = true;
        targetCheckbox.checked = false;
        targetCheckbox.parentElement.style.opacity = '0.5';
    }
    
    // Show modal
    document.getElementById('deleteOptionsModal').style.display = 'block';
}

function closeDeleteOptionsModal() {
    document.getElementById('deleteOptionsModal').style.display = 'none';
    currentDeleteFile = null;
}

async function confirmDeleteWithOptions() {
    if (!currentDeleteFile) return;
    
    const deleteFromSource = document.getElementById('deleteFromSource').checked;
    const deleteFromTarget = document.getElementById('deleteFromTarget').checked;
    const dryRun = document.getElementById('deleteOptionsDryRun').checked;
    
    if (!deleteFromSource && !deleteFromTarget) {
        window.showNotification('Please select at least one server to delete from', 'warning');
        return;
    }
    
    const servers = [];
    if (deleteFromSource) servers.push('source');
    if (deleteFromTarget) servers.push('target');
    
    // Store fileId before closing modal
    const fileId = currentDeleteFile.fileId;
    const fileDetails = { ...currentDeleteFile };
    
    closeDeleteOptionsModal();
    
    // Add to delete queue with server info
    const queueItem = {
        ...fileDetails,
        deleteServers: servers,
        dryRun: dryRun
    };
    
    // Check if already in delete queue
    const alreadyInQueue = fileId ? 
        deleteQueue.find(item => item.fileId === fileId) : null;
    if (alreadyInQueue) {
        // Update existing entry
        alreadyInQueue.deleteServers = servers;
        alreadyInQueue.dryRun = dryRun;
    } else {
        // Add new entry
        deleteQueue.push(queueItem);
    }
    
    // Update button state
    if (fileId) {
        const button = document.querySelector(`button[onclick="addToDeleteQueue('${fileId}')"]`);
        if (button) {
            const serverText = servers.length === 2 ? 'both' : servers[0];
            button.innerHTML = `<i class="fas fa-check"></i> Delete from ${serverText}`;
            button.classList.add('added');
            button.disabled = true;
        }
    }
    
    const serverText = servers.join(' & ');
    log(`📋 Added ${fileDetails.targetFile?.name || fileDetails.sourceFile?.name} to delete queue (delete from ${serverText})`);
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
    
    // Group files by server and dry run status
    const deleteOperations = {};
    
    deleteQueue.forEach(item => {
        const servers = item.deleteServers || ['target'];
        const dryRun = item.dryRun !== undefined ? item.dryRun : 
            (document.getElementById('dryRunDelete') ? document.getElementById('dryRunDelete').checked : true);
        
        servers.forEach(server => {
            const key = `${server}_${dryRun}`;
            if (!deleteOperations[key]) {
                deleteOperations[key] = {
                    server: server,
                    dryRun: dryRun,
                    files: []
                };
            }
            
            // Prepare file info based on which server we're deleting from
            const fileInfo = {
                name: item.targetFile?.name || item.sourceFile?.name,
                path: (server === 'target' && item.targetFile?.full_path) || 
                      (server === 'source' && item.sourceFile?.full_path) || 
                      item.relativePath,
                size: item.targetFile?.size || item.sourceFile?.size || 0,
                fileId: item.fileId
            };
            
            deleteOperations[key].files.push(fileInfo);
        });
    });
    
    log(`Starting deletion across ${Object.keys(deleteOperations).length} server operation(s)...`);
    
    let totalSuccess = 0;
    let totalFailure = 0;
    const allResults = [];
    
    // Execute delete operations
    for (const [key, operation] of Object.entries(deleteOperations)) {
        const { server, dryRun, files } = operation;
        
        log(`Deleting ${files.length} files from ${server} server${dryRun ? ' (DRY RUN)' : ''}...`);
        
        try {
            const response = await fetch('/api/delete-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    files: files,
                    server_type: server,
                    dry_run: dryRun
                })
            });
            
            const result = await response.json();
            allResults.push(...(result.results || []));
            
            if (result.success) {
                totalSuccess += result.success_count || 0;
                totalFailure += result.failure_count || 0;
                
                log(`Delete operation on ${server} completed: ${result.success_count} successful, ${result.failure_count} failed${dryRun ? ' (DRY RUN)' : ''}`);
                
                // Log individual results
                result.results.forEach(fileResult => {
                    if (fileResult.success) {
                        log(`✅ [${server}] ${fileResult.message}`);
                    } else {
                        log(`❌ [${server}] ${fileResult.message}`, 'error');
                    }
                });
            } else {
                log(`Delete operation on ${server} failed: ${result.message}`, 'error');
                totalFailure += files.length;
            }
        } catch (error) {
            log(`Delete request to ${server} failed: ${error.message}`, 'error');
            totalFailure += operation.files.length;
        }
    }
    
    // Process results after all operations complete
    log(`All delete operations completed: ${totalSuccess} successful, ${totalFailure} failed`);
    
    // Remove successfully deleted files from UI
    const successfulDeletes = new Set();
    allResults.forEach(result => {
        if (result.success && !result.dry_run) {
            successfulDeletes.add(result.file_name);
        }
    });
    
    if (successfulDeletes.size > 0) {
        // Update delete queue
        deleteQueue = deleteQueue.filter(item => {
            const fileName = item.targetFile?.name || item.sourceFile?.name;
            return !successfulDeletes.has(fileName);
        });
        
        // Update file lists based on which servers files were deleted from
        allResults.forEach(result => {
            if (result.success && !result.dry_run) {
                const server = result.server || 'target';
                const fileName = result.file_name;
                
                if (server === 'source' || server === 'both') {
                    sourceFiles = sourceFiles.filter(f => f.name !== fileName);
                }
                if (server === 'target' || server === 'both') {
                    targetFiles = targetFiles.filter(f => f.name !== fileName);
                    targetOnlyFiles = targetOnlyFiles.filter(item => item.targetFile.name !== fileName);
                }
            }
        });
        
        // Re-render UI
        displayScannedFiles();
        renderComparisonResults();
        updateComparisonSummary();
        updateDeleteButtonState();
        updateBulkDeleteButtonStates();
        updateDashboardStats();
        
        log(`Removed ${successfulDeletes.size} deleted files from UI`);
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
            // Use the new scheduling expiration modal instead
            if (window.schedulingShowExpirationModal) {
                window.schedulingShowExpirationModal();
                return;
            } else {
                titleText = 'Content Expiration Configuration';
                bodyContent = generateExpirationConfigHTML();
            }
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
                        <option value="" disabled>──────────</option>
                        <option value="AN">Atlanta Now</option>
                        <option value="BMP">Bumps</option>
                        <option value="IMOW">IMOW</option>
                        <option value="IM">Inclusion Months</option>
                        <option value="IA">Inside Atlanta</option>
                        <option value="LM">Legislative Minute</option>
                        <option value="MTG">Meetings</option>
                        <option value="MAF">Moving Atlanta Forward</option>
                        <option value="PKG">Packages</option>
                        <option value="PMO">Promos</option>
                        <option value="PSA">PSAs</option>
                        <option value="SZL">Sizzles</option>
                        <option value="SPP">Special Projects</option>
                        <option value="OTHER">Other</option>
                    </select>
                    <button onclick="addCategoryToRotation()">Add to Rotation</button>
                </div>
                
                <div class="rotation-preview">
                    <h5>Rotation Preview</h5>
                    <p id="rotationPreview">${getRotationPreview(currentOrder)}</p>
                </div>
            </div>
            
            <div class="rotation-note">
                <p><strong>Note:</strong> The scheduler will cycle through categories in this order when selecting content. You can use duration categories (ID, Spots, Short Form, Long Form) or specific content types. Adding duplicates increases that category's selection frequency.</p>
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
        // Duration categories
        'id': 'ID',
        'spots': 'Spots',
        'short_form': 'Short Form',
        'long_form': 'Long Form',
        // Content type categories
        'AN': 'Atlanta Now',
        'BMP': 'Bumps',
        'IMOW': 'IMOW',
        'IM': 'Inclusion Months',
        'IA': 'Inside Atlanta',
        'LM': 'Legislative Minute',
        'MTG': 'Meetings',
        'MAF': 'Moving Atlanta Forward',
        'PKG': 'Packages',
        'PMO': 'Promos',
        'PSA': 'PSAs',
        'SZL': 'Sizzles',
        'SPP': 'Special Projects',
        'OTHER': 'Other'
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
        const result = await window.API.post('/config', {
            scheduling: {
                replay_delays: scheduleConfig.REPLAY_DELAYS,
                additional_delay_per_airing: scheduleConfig.ADDITIONAL_DELAY_PER_AIRING,
                content_expiration: scheduleConfig.CONTENT_EXPIRATION,
                timeslots: scheduleConfig.TIMESLOTS,
                duration_categories: scheduleConfig.DURATION_CATEGORIES,
                rotation_order: scheduleConfig.ROTATION_ORDER || ['id', 'spots', 'short_form', 'long_form']
            }
        });
        
        if (result.success) {
            log(`✅ ${configType} configuration saved successfully`);
            // Show success notification
            showNotification(`${configType.charAt(0).toUpperCase() + configType.slice(1)} configuration saved permanently`, 'success');
        } else {
            log(`❌ Failed to save configuration: ${result.message}`, 'error');
            showNotification(`Failed to save configuration: ${result.message}`, 'error');
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
        
        const response = await fetch('/api/analyzed-content', {
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
        const response = await fetch('/api/update-content-type', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content_id: contentId,
                content_type: newType
            })
        });
        
        if (!response.ok) {
            throw new Error(`Failed to update content type: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Content Type Updated', `Successfully updated content type to ${newType}`, 'success');
            
            // Update the content in availableContent array
            const content = availableContent.find(c => c._id == contentId || c.id == contentId);
            if (content) {
                content.content_type = newType.toLowerCase();
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
    
    if (!contentList) {
        console.error('availableContentList element not found!');
        return;
    }
    
    console.log('Displaying available content:', availableContent.length, 'items');
    
    // Update the count display
    const countElement = document.getElementById('contentCount');
    if (countElement) {
        countElement.textContent = `(${availableContent.length} items)`;
    }
    
    if (availableContent.length === 0) {
        contentList.innerHTML = '<p>No content matches the current filters</p>';
        return;
    }
    
    console.log('Building HTML for content display...');
    
    // Add sort header
    let html = `
        <div class="content-header">
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
            <span class="sort-field" data-field="expiration" onclick="sortContent('expiration')">
                Expiration ${getSortIcon('expiration')}
            </span>
            <span style="text-align: center;">Actions</span>
        </div>
    `;
    
    html += '<div class="available-content">';
    
    availableContent.forEach(content => {
        const durationTimecode = formatDurationTimecode(content.file_duration || 0);
        const durationCategory = getDurationCategory(content.file_duration);
        const engagementScore = content.engagement_score || 'N/A';
        
        // Format expiration date
        // NOTE: Expired content is shown for informational purposes only
        // The backend will prevent scheduling expired content based on the air date
        let expirationDisplay = 'Not Set';
        let expirationClass = '';
        if (content.scheduling?.content_expiry_date) {
            const expiryDate = new Date(content.scheduling.content_expiry_date);
            const today = new Date();
            const daysUntilExpiry = Math.floor((expiryDate - today) / (1000 * 60 * 60 * 24));
            
            if (daysUntilExpiry < 0) {
                expirationDisplay = 'Expired';
                expirationClass = 'expired';
            } else if (daysUntilExpiry <= 7) {
                expirationDisplay = `${daysUntilExpiry}d`;
                expirationClass = 'expiring-soon';
            } else if (daysUntilExpiry <= 30) {
                expirationDisplay = `${daysUntilExpiry}d`;
                expirationClass = 'expiring';
            } else {
                const month = (expiryDate.getMonth() + 1).toString().padStart(2, '0');
                const day = expiryDate.getDate().toString().padStart(2, '0');
                const year = expiryDate.getFullYear().toString().slice(-2);
                expirationDisplay = `${month}/${day}/${year}`;
                expirationClass = '';
            }
        }
        
        // Use MongoDB _id as the content identifier (prioritize _id over id)
        const contentId = content._id || content.id || content.guid || 'unknown';
        
        html += `
            <div class="content-item" data-content-id="${contentId}">
                <span class="content-title" title="${content.file_name}">${content.file_name ? content.file_name.replace(/\.[^/.]+$/, '') : (content.content_title || 'Unknown')}</span>
                <select class="content-type" onchange="updateContentType('${contentId}', this.value)" data-original="${content.content_type ? content.content_type.toUpperCase() : ''}">
                    <option value="PSA" ${content.content_type && content.content_type.toUpperCase() === 'PSA' ? 'selected' : ''}>PSA</option>
                    <option value="AN" ${content.content_type && content.content_type.toUpperCase() === 'AN' ? 'selected' : ''}>AN</option>
                    <option value="ATLD" ${content.content_type && content.content_type.toUpperCase() === 'ATLD' ? 'selected' : ''}>ATLD</option>
                    <option value="BMP" ${content.content_type && content.content_type.toUpperCase() === 'BMP' ? 'selected' : ''}>BMP</option>
                    <option value="IMOW" ${content.content_type && content.content_type.toUpperCase() === 'IMOW' ? 'selected' : ''}>IMOW</option>
                    <option value="IM" ${content.content_type && content.content_type.toUpperCase() === 'IM' ? 'selected' : ''}>IM</option>
                    <option value="IA" ${content.content_type && content.content_type.toUpperCase() === 'IA' ? 'selected' : ''}>IA</option>
                    <option value="LM" ${content.content_type && content.content_type.toUpperCase() === 'LM' ? 'selected' : ''}>LM</option>
                    <option value="MTG" ${content.content_type && content.content_type.toUpperCase() === 'MTG' ? 'selected' : ''}>MTG</option>
                    <option value="MAF" ${content.content_type && content.content_type.toUpperCase() === 'MAF' ? 'selected' : ''}>MAF</option>
                    <option value="PKG" ${content.content_type && content.content_type.toUpperCase() === 'PKG' ? 'selected' : ''}>PKG</option>
                    <option value="PMO" ${content.content_type && content.content_type.toUpperCase() === 'PMO' ? 'selected' : ''}>PMO</option>
                    <option value="SZL" ${content.content_type && content.content_type.toUpperCase() === 'SZL' ? 'selected' : ''}>SZL</option>
                    <option value="SPP" ${content.content_type && content.content_type.toUpperCase() === 'SPP' ? 'selected' : ''}>SPP</option>
                    <option value="OTHER" ${content.content_type && content.content_type.toUpperCase() === 'OTHER' ? 'selected' : ''}>OTHER</option>
                </select>
                <span class="content-duration">${durationTimecode}</span>
                <span class="content-category">${durationCategory.toUpperCase()}</span>
                <span class="content-score">${engagementScore}%</span>
                <span class="content-expiration ${expirationClass}">${expirationDisplay}</span>
                <div class="content-actions">
                    <button class="button small info" onclick="syncContentExpiration('${contentId}')" title="Sync Expiration from Castus">
                        <i class="fas fa-sync"></i>
                    </button>
                    <button class="button small primary" onclick="schedulingEditExpiration('${contentId}', '${content.scheduling?.content_expiry_date || ''}')" title="Edit Expiration Date">
                        <i class="fas fa-calendar-alt"></i>
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
                    <button class="button small danger" onclick="showContentDeleteOptionsModal('${contentId}')" title="Delete Options">
                        <i class="fas fa-trash"></i>
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
        
        const response = await fetch('/api/create-schedule', {
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
        const response = await fetch('/api/create-weekly-schedule', {
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
        const response = await fetch('/api/create-monthly-schedule', {
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
        const result = await window.API.get('/');
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        
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
        const response = await fetch(`/api/playlist/${playlistId}/items?server=${server}&path=${encodeURIComponent(path)}`);
        
        
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
        let url = `/api/playlist/${playlistId}?server=${server}&path=${encodeURIComponent(path)}`;
        if (name) {
            url += `&name=${encodeURIComponent(name)}`;
        }
        
        const response = await fetch(url, {
            method: 'DELETE'
        });
        
        
        
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
        const response = await fetch(`/api/playlist/${playlistId}/items?server=${server}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        
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
        const response = await fetch(`/api/playlist/${playlistId}/item/${itemId}`, {
            method: 'DELETE'
        });
        
        
        
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
        const response = await fetch('/api/preview-playlist-files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: server,
                path: path
            })
        });
        
        
        
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
        
        const response = await fetch('/api/generate-simple-playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        
        
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
        
        const response = await fetch(`/api/playlist/${window.currentExportPlaylist.id}/export`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        
        
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
        const response = await fetch('/api/preview-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: scheduleDate,
                timeslot: timeslot,
                use_engagement_scoring: useEngagement
            })
        });
        
        
        
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
        const response = await fetch('/api/get-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: viewDate
            })
        });
        
        
        
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
        const result = await window.API.post('/get-schedule', {
            date: viewDate
        });
        
        if (!result.success || !result.schedule) {
            log(`❌ No schedule found for ${viewDate}`, 'error');
            return;
        }
        
        const schedule = result.schedule;
        const scheduleId = schedule.id;
        
        if (confirm(`Are you sure you want to delete the schedule for ${viewDate}?\n\nThis will delete ${schedule.total_items} scheduled items.`)) {
            log(`🗑️ Deleting schedule for ${viewDate}...`);
            
            const deleteResult = await window.API.post('/delete-schedule', {
                schedule_id: scheduleId
            });
            
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
        const result = await window.API.get('/list-schedules');
        
        
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
    // Delegate to the new scheduling module function
    if (window.schedulingDisplayScheduleList) {
        window.schedulingDisplayScheduleList(schedules);
        return;
    }
    
    // Fallback to old implementation
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
            <div class="schedule-list-item compact" data-schedule-id="${schedule.id}">
                <div class="schedule-item-content">
                    <div class="schedule-date">
                        <span class="schedule-icon">📅</span>
                        <strong>${dayName}, ${airDate}</strong>
                    </div>
                    <div class="schedule-info">
                        <span class="schedule-stat">${schedule.total_items || 0} items</span>
                        <span class="schedule-separator">•</span>
                        <span class="schedule-stat">${totalDurationFormatted}</span>
                        <span class="schedule-separator">•</span>
                        <span class="schedule-stat">Created ${createdAt}</span>
                    </div>
                    <div class="schedule-actions">
                        <button class="button small primary" onclick="viewScheduleDetails(${schedule.id}, '${airDate}')" title="View Schedule">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="button small secondary" onclick="exportSchedule(${schedule.id})" title="Export Schedule">
                            <i class="fas fa-download"></i>
                        </button>
                        <button class="button small danger" onclick="deleteScheduleById(${schedule.id}, '${airDate}')" title="Delete Schedule">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
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
        const result = await window.API.post('/get-schedule', {
            date: date
        });
        
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
        const result = await window.API.post('/delete-schedule', {
            schedule_id: scheduleId
        });
        
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
        const result = await window.API.post('/delete-all-schedules');
        
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
            
            // Clear any cached schedules
            currentSchedule = null;
            
            // Clear the schedule display
            clearScheduleDisplay();
            
            // Force refresh the schedule list - always show empty list after deletion
            const scheduleDisplay = document.getElementById('scheduleDisplay');
            if (scheduleDisplay) {
                // Clear any existing content first
                scheduleDisplay.innerHTML = '<p style="color: #666; text-align: center;">No schedules found. All schedules have been deleted.</p>';
                
                // Then refresh to ensure we're showing current state
                setTimeout(async () => {
                    await listAllSchedules();
                }, 100);
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
    if (!currentSchedule) {
        log('❌ No schedule loaded to export', 'error');
        return;
    }
    
    // Use the actual schedule's air_date, not the view date
    const scheduleDate = currentSchedule.air_date ? currentSchedule.air_date.split('T')[0] : '';
    
    if (!scheduleDate) {
        log('❌ Schedule has no air date', 'error');
        return;
    }
    
    // Show the export modal
    document.getElementById('exportScheduleDate').textContent = scheduleDate;
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
    
    // Generate default filename based on schedule's air date and type
    // Parse date components to avoid timezone issues
    const [year, month, day] = scheduleDate.split('-').map(num => parseInt(num));
    
    // Format as YY_MM_DD_HHMM
    const now = new Date();
    const yy = year.toString().slice(-2);
    const mm = month.toString().padStart(2, '0');
    const dd = day.toString().padStart(2, '0');
    const hh = now.getHours().toString().padStart(2, '0');
    const min = now.getMinutes().toString().padStart(2, '0');
    const dateStr = `${yy}_${mm}_${dd}_${hh}${min}`;
    
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
    const exportDate = document.getElementById('exportScheduleDate').textContent;
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
    
    log(`📤 Exporting schedule for ${exportDate} to ${exportServer} server...`);
    log(`📂 Export path: ${exportPath}`);
    log(`📄 Filename: ${exportFilename}`);
    log(`📋 Format: ${exportFormat === 'castus' ? 'Castus Daily Schedule' : exportFormat === 'castus_weekly' ? 'Castus Weekly Schedule' : 'Unknown'}`);
    
    try {
        const response = await fetch('/api/export-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: exportDate,
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
    // Delegate to the new scheduling module function
    if (window.schedulingDisplayScheduleDetails) {
        window.schedulingDisplayScheduleDetails(schedule);
        return;
    }
    
    // Fallback to old implementation
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
            
            // Check if this is a live input item
            let title = '';
            let categoryLabel = '';
            let metadata = item.metadata;
            
            // Parse metadata if it's a string
            if (typeof metadata === 'string') {
                try {
                    metadata = JSON.parse(metadata);
                } catch (e) {
                    metadata = null;
                }
            }
            
            if (metadata && metadata.is_live_input) {
                // This is a live input item
                title = metadata.title || 'Live Input';
                categoryLabel = 'LIVE';
            } else {
                // Regular content item
                title = item.content_title || item.file_name || 'Untitled';
                categoryLabel = item.duration_category ? item.duration_category.replace('_', ' ').toUpperCase() : '';
            }
            
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
        const response = await fetch('/api/toggle-schedule-item-availability', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId,
                item_id: itemId,
                available: available
            })
        });
        
        
        
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
        const response = await fetch('/api/reorder-schedule-items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId,
                item_id: items[newIndex].id,
                old_position: index,
                new_position: newIndex
            })
        });
        
        
        
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
        const response = await fetch('/api/delete-schedule-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId,
                item_id: itemId
            })
        });
        
        
        
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

// Calculate end time from start time and duration with millisecond precision
function calculateEndTime(startTime, durationSeconds, fps = 30) {
    // Handle time with microseconds (e.g., "00:00:15.015000")
    let timeParts;
    let hours = 0, minutes = 0, seconds = 0, milliseconds = 0;
    
    if (startTime.includes('.')) {
        const [timePart, microPart] = startTime.split('.');
        timeParts = timePart.split(':');
        // Convert microseconds to milliseconds
        const microStr = microPart.padEnd(6, '0'); // Ensure 6 digits
        milliseconds = Math.round(parseInt(microStr) / 1000);
    } else {
        // Parse start time - can be HH:MM:SS or HH:MM:SS:FF
        timeParts = startTime.split(':');
        // If we have frames (4th part), convert to milliseconds
        if (timeParts.length >= 4) {
            const frames = parseInt(timeParts[3]) || 0;
            milliseconds = Math.round((frames / fps) * 1000);
        }
    }
    
    if (timeParts.length >= 3) {
        hours = parseInt(timeParts[0]) || 0;
        minutes = parseInt(timeParts[1]) || 0;
        seconds = parseInt(timeParts[2]) || 0;
    }
    
    // Ensure durationSeconds is a number
    const duration = parseFloat(durationSeconds) || 0;
    
    // Convert everything to milliseconds for precise calculation
    const startTotalMs = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds;
    const durationMs = Math.round(duration * 1000);
    const endTotalMs = startTotalMs + durationMs;
    
    // Convert back to time components
    const totalSeconds = Math.floor(endTotalMs / 1000);
    const endMilliseconds = endTotalMs % 1000;
    const endHours = Math.floor(totalSeconds / 3600) % 24;
    const endMinutes = Math.floor((totalSeconds % 3600) / 60);
    const endSeconds = Math.floor(totalSeconds % 60);
    
    // Format as HH:MM:SS.mmm (with milliseconds)
    return `${endHours.toString().padStart(2, '0')}:${endMinutes.toString().padStart(2, '0')}:${endSeconds.toString().padStart(2, '0')}.${endMilliseconds.toString().padStart(3, '0')}`;
}

// Format duration in seconds to HH:MM:SS.mmm format (with milliseconds)
function formatDurationTimecode(durationSeconds, fps = 30) {
    const duration = parseFloat(durationSeconds) || 0;
    
    const hours = Math.floor(duration / 3600);
    const minutes = Math.floor((duration % 3600) / 60);
    const seconds = Math.floor(duration % 60);
    const milliseconds = Math.round((duration % 1) * 1000);
    
    // Format as HH:MM:SS.mmm
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
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
        // Add frames
        return timeStr + ':00';
    }
    
    return '00:00:00:00';
}

// Convert HH:MM:SS or HH:MM:SS.microseconds to HH:MM:SS.000 format (with milliseconds)
function formatTimeWithMilliseconds(timeStr) {
    if (!timeStr) return '00:00:00.000';
    
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
    
    let millis = '000';
    if (secondsParts.length > 1) {
        // Extract milliseconds, handling microsecond format
        const fracPart = secondsParts[1];
        if (fracPart.length >= 3) {
            millis = fracPart.substring(0, 3);
        } else {
            millis = fracPart.padEnd(3, '0');
        }
    }
    
    return `${hours}:${minutes}:${seconds}.${millis}`;
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
            const analysisStatusResult = await fetch('/api/analysis-status', {
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
        
        const response = await fetch('/api/add-item-to-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: currentSchedule.id,
                asset_id: contentId
            })
        });
        
        
        
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
        (c._id || c.id || c.guid) == contentId
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
        
        const response = await fetch('/api/rename-content', {
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
            case 'expiration':
                aVal = a.scheduling?.content_expiry_date ? new Date(a.scheduling.content_expiry_date).getTime() : Number.MAX_SAFE_INTEGER;
                bVal = b.scheduling?.content_expiry_date ? new Date(b.scheduling.content_expiry_date).getTime() : Number.MAX_SAFE_INTEGER;
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

// Helper function to extract creation date from filename (YYMMDD format)
function getCreationDateFromFilename(filename) {
    if (!filename || filename.length < 6) {
        return null;
    }
    
    // Extract first 6 characters
    const dateStr = filename.substring(0, 6);
    
    // Check if it's a valid date format (all digits)
    if (!/^\d{6}$/.test(dateStr)) {
        return null;
    }
    
    // Parse YY, MM, DD
    const yy = parseInt(dateStr.substring(0, 2));
    const mm = parseInt(dateStr.substring(2, 4));
    const dd = parseInt(dateStr.substring(4, 6));
    
    // Validate month and day ranges
    if (mm < 1 || mm > 12 || dd < 1 || dd > 31) {
        return null;
    }
    
    // Determine century (assume 2000s for 00-30, 1900s for 31-99)
    const year = yy <= 30 ? 2000 + yy : 1900 + yy;
    
    try {
        const date = new Date(year, mm - 1, dd);
        // Verify the date is valid (e.g., not Feb 31)
        if (date.getMonth() !== mm - 1 || date.getDate() !== dd) {
            return null;
        }
        return date;
    } catch (e) {
        return null;
    }
}

// Helper function to get effective creation date (encoded date or from filename)
function getEffectiveCreationDate(content) {
    // Use encoded date if available
    if (content.encoded_date) {
        return new Date(content.encoded_date);
    }
    
    // Try to extract from filename
    if (content.file_name) {
        const dateFromFilename = getCreationDateFromFilename(content.file_name);
        if (dateFromFilename) {
            return dateFromFilename;
        }
    }
    
    return null;
}

// Helper function to format expiration date with status
function formatExpirationDate(expiryDate) {
    if (!expiryDate) {
        return 'Not Set';
    }
    
    const expiry = new Date(expiryDate);
    const today = new Date();
    const daysUntilExpiry = Math.floor((expiry - today) / (1000 * 60 * 60 * 24));
    
    const formattedDate = expiry.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
    
    if (daysUntilExpiry < 0) {
        return `<span style="color: var(--danger-color, #dc3545); font-weight: 600;">Expired (${formattedDate})</span>`;
    } else if (daysUntilExpiry === 0) {
        return `<span style="color: var(--danger-color, #dc3545); font-weight: 600;">Expires Today</span>`;
    } else if (daysUntilExpiry <= 7) {
        return `<span style="color: var(--warning-color, #ff9800); font-weight: 600;">Expires in ${daysUntilExpiry} day${daysUntilExpiry > 1 ? 's' : ''} (${formattedDate})</span>`;
    } else if (daysUntilExpiry <= 30) {
        return `<span style="color: var(--info-color, #2196f3);">Expires in ${daysUntilExpiry} days (${formattedDate})</span>`;
    } else {
        return `${formattedDate} (${daysUntilExpiry} days)`;
    }
}

// Helper function to format creation date with source info
function formatCreationDate(content) {
    const creationDate = getEffectiveCreationDate(content);
    
    if (!creationDate) {
        return 'Unknown';
    }
    
    const formattedDate = creationDate.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
    
    // Indicate source of date
    if (content.encoded_date) {
        return formattedDate + ' (from metadata)';
    } else if (content.file_name) {
        return formattedDate + ' (from filename)';
    }
    
    return formattedDate;
}

// Helper function to get shelf life information
function getShelfLifeInfo(content) {
    const creationDate = getEffectiveCreationDate(content);
    
    if (!creationDate) {
        return 'Unknown (no creation date)';
    }
    
    const expiryDate = content.scheduling?.content_expiry_date ? new Date(content.scheduling.content_expiry_date) : null;
    
    if (!expiryDate) {
        return 'Not calculated';
    }
    
    // Calculate the shelf life in days
    const shelfLifeDays = Math.round((expiryDate - creationDate) / (1000 * 60 * 60 * 24));
    
    // Determine shelf life category
    let shelfLifeCategory = 'Custom';
    const durationCategory = getDurationCategory(content.file_duration);
    
    // Check against standard shelf life values
    if (durationCategory === 'short') {
        if (shelfLifeDays === 7) shelfLifeCategory = 'Short';
        else if (shelfLifeDays === 14) shelfLifeCategory = 'Medium';
        else if (shelfLifeDays === 30) shelfLifeCategory = 'Long';
    } else if (durationCategory === 'medium') {
        if (shelfLifeDays === 30) shelfLifeCategory = 'Short';
        else if (shelfLifeDays === 60) shelfLifeCategory = 'Medium';
        else if (shelfLifeDays === 90) shelfLifeCategory = 'Long';
    } else if (durationCategory === 'long') {
        if (shelfLifeDays === 90) shelfLifeCategory = 'Short';
        else if (shelfLifeDays === 180) shelfLifeCategory = 'Medium';
        else if (shelfLifeDays === 365) shelfLifeCategory = 'Long';
    } else if (durationCategory === 'extra_long') {
        if (shelfLifeDays === 180) shelfLifeCategory = 'Short';
        else if (shelfLifeDays === 365) shelfLifeCategory = 'Medium';
        else if (shelfLifeDays === 730) shelfLifeCategory = 'Long';
    }
    
    return `${shelfLifeCategory} (${shelfLifeDays} days from encode date)`;
}

// Track the current content being deleted
let currentDeleteContent = null;

// Show content delete options modal
function showContentDeleteOptionsModal(contentId) {
    console.log('showContentDeleteOptionsModal called with contentId:', contentId);
    console.log('Available content items:', availableContent.length);
    
    // Find the content item
    const content = availableContent.find(c => {
        const itemId = c._id || c.id || c.guid;
        return itemId == contentId || itemId === contentId || String(itemId) === String(contentId);
    });
    
    console.log('Found content:', content);
    
    if (!content) {
        window.showNotification('Content not found', 'error');
        return;
    }
    
    currentDeleteContent = content;
    console.log('currentDeleteContent set to:', currentDeleteContent);
    
    // Populate modal with content info
    document.getElementById('deleteContentTitle').textContent = content.content_title || content.title || content.file_name || 'Untitled';
    document.getElementById('deleteContentPath').textContent = content.file_path || content.filePath || 'N/A';
    document.getElementById('deleteContentDuration').textContent = formatDuration(content.file_duration || content.duration || content.duration_seconds || 0);
    document.getElementById('deleteContentCategory').textContent = content.duration_category || content.category || 'N/A';
    
    // Reset options
    document.querySelector('input[name="deleteContentOption"][value="database-only"]').checked = true;
    document.getElementById('contentDeleteServersOptions').style.display = 'none';
    document.getElementById('deleteContentFromSource').checked = false;
    document.getElementById('deleteContentFromTarget').checked = true;
    document.getElementById('contentDeleteDryRun').checked = true;
    
    // Add event listener for radio button changes
    const radioButtons = document.querySelectorAll('input[name="deleteContentOption"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            const serversOptions = document.getElementById('contentDeleteServersOptions');
            if (this.value === 'database-and-files') {
                serversOptions.style.display = 'block';
            } else {
                serversOptions.style.display = 'none';
            }
        });
    });
    
    // Show modal
    document.getElementById('contentDeleteOptionsModal').style.display = 'block';
}

// Close content delete options modal
function closeContentDeleteOptionsModal() {
    document.getElementById('contentDeleteOptionsModal').style.display = 'none';
    currentDeleteContent = null;
}

// Confirm content deletion with options
async function confirmContentDeleteWithOptions() {
    console.log('confirmContentDeleteWithOptions called');
    console.log('currentDeleteContent:', currentDeleteContent);
    
    if (!currentDeleteContent) {
        console.error('No currentDeleteContent set!');
        window.showNotification('No content selected', 'error');
        return;
    }
    
    const deleteOption = document.querySelector('input[name="deleteContentOption"]:checked').value;
    const dryRun = document.getElementById('contentDeleteDryRun').checked;
    
    console.log('Delete option selected:', deleteOption);
    console.log('Dry run:', dryRun);
    
    if (deleteOption === 'database-only') {
        // Original database-only deletion
        const contentToDelete = currentDeleteContent;
        const contentId = contentToDelete._id || contentToDelete.id || contentToDelete.guid;
        console.log('Database-only deletion for ID:', contentId);
        closeContentDeleteOptionsModal();
        await deleteContentFromDatabase(contentId);
    } else {
        // Database and files deletion
        const deleteFromSource = document.getElementById('deleteContentFromSource').checked;
        const deleteFromTarget = document.getElementById('deleteContentFromTarget').checked;
        
        if (!deleteFromSource && !deleteFromTarget) {
            window.showNotification('Please select at least one server to delete from', 'warning');
            return;
        }
        
        const servers = [];
        if (deleteFromSource) servers.push('source');
        if (deleteFromTarget) servers.push('target');
        
        const contentToDelete = currentDeleteContent;
        closeContentDeleteOptionsModal();
        
        // Call the enhanced delete endpoint
        await deleteContentWithFiles(contentToDelete, servers, dryRun);
    }
}

// Enhanced delete function that deletes both database and files
async function deleteContentWithFiles(content, servers, dryRun) {
    if (!content) {
        window.showNotification('No content selected', 'error');
        return;
    }
    
    const contentId = content._id || content.id || content.guid;
    const filePath = content.file_path || content.filePath || content.path;
    
    console.log('Content object:', content);
    console.log('File path to delete:', filePath);
    
    if (!confirm(`This will delete "${content.title || content.content_title}" from the database and the actual file from ${servers.join(' and ')} server(s). This action cannot be undone! Are you sure?`)) {
        return;
    }
    
    try {
        // First delete from database
        console.log('Deleting content with ID:', contentId);
        const dbResponse = await fetch(`/api/content/${contentId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        console.log('Delete response status:', dbResponse.status);
        
        if (!dbResponse.ok) {
            const errorText = await dbResponse.text();
            console.error('Delete failed. Response:', errorText);
            throw new Error(`Failed to delete from database: ${dbResponse.statusText} - ${errorText}`);
        }
        
        const dbResult = await dbResponse.json();
        console.log('Delete result:', dbResult);
        
        if (dbResult.success) {
            // Database deletion successful, now delete files
            if (filePath) {
                const fileResponse = await fetch('/api/delete-files', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        files: [{
                            path: filePath,
                            servers: servers
                        }],
                        dry_run: dryRun
                    })
                });
                
                if (!fileResponse.ok) {
                    throw new Error(`Failed to delete files: ${fileResponse.statusText}`);
                }
                
                const fileResult = await fileResponse.json();
                
                if (fileResult.results && fileResult.results.length > 0) {
                    const successCount = fileResult.results.filter(r => r.status === 'success').length;
                    const failCount = fileResult.results.filter(r => r.status === 'error').length;
                    
                    let message = `Database entry deleted. `;
                    if (dryRun) {
                        message += `Dry run: Would attempt to delete from ${servers.length} server(s)`;
                    } else {
                        if (successCount > 0) {
                            message += `Files deleted from ${successCount} server(s)`;
                        } else if (failCount > 0) {
                            message += `File deletion failed: File not found on ${failCount} server(s)`;
                        }
                    }
                    
                    // Add details about specific errors
                    if (failCount > 0 && !dryRun) {
                        const failedResults = fileResult.results.filter(r => r.status === 'error');
                        if (failedResults.length > 0 && failedResults[0].message) {
                            console.log('File deletion errors:', failedResults);
                        }
                    }
                    
                    window.showNotification(message, failCount > 0 ? 'warning' : 'success');
                } else {
                    window.showNotification('Database entry deleted, but no file operations performed', 'warning');
                }
            } else {
                window.showNotification('Database entry deleted (no file path associated)', 'success');
            }
            
            // Remove from local array and refresh display
            const index = availableContent.findIndex(c => {
                const itemId = c._id || c.id || c.guid;
                return itemId == contentId || itemId === contentId || String(itemId) === String(contentId);
            });
            if (index > -1) {
                availableContent.splice(index, 1);
            }
            displayAvailableContent();
            
        } else {
            window.showNotification('Failed to delete from database', 'error');
        }
        
    } catch (error) {
        console.error('Error deleting content:', error);
        window.showNotification(`Error: ${error.message}`, 'error');
    }
}

async function deleteContentFromDatabase(contentId) {
    console.log('deleteContentFromDatabase called with ID:', contentId);
    const content = availableContent.find(c => {
        const itemId = c._id || c.id || c.guid;
        return itemId == contentId || itemId === contentId || 
               String(itemId) === String(contentId);
    });
    
    console.log('Found content for deletion:', content);
    
    if (!content) {
        alert('Content not found');
        return;
    }
    
    const confirmMsg = `Are you sure you want to delete the database entry for:\n\n"${content.file_name || content.content_title || 'Unknown'}"\n\nThis will remove the content analysis data but will NOT delete the actual file.`;
    
    if (!confirm(confirmMsg)) {
        return;
    }
    
    try {
        console.log('Sending DELETE request for content ID:', contentId);
        const response = await fetch(`/api/content/${contentId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        console.log('Delete response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Delete failed:', errorText);
            throw new Error(`Failed to delete content: ${response.statusText}`);
        }
        
        const result = await response.json();
        console.log('Delete result:', result);
        
        if (result.success) {
            // Remove from local array
            const index = availableContent.findIndex(c => {
                const itemId = c._id || c.id || c.guid;
                return itemId == contentId || itemId === contentId || 
                       String(itemId) === String(contentId);
            });
            console.log('Found item at index:', index);
            if (index > -1) {
                availableContent.splice(index, 1);
                console.log('Removed item from array. New length:', availableContent.length);
            }
            
            // Refresh display
            displayAvailableContent();
            
            log(`✅ Database entry deleted for: ${content.file_name || content.content_title}`, 'success');
        } else {
            alert(`Failed to delete database entry: ${result.message || 'Unknown error'}`);
            log(`❌ Failed to delete database entry: ${result.message}`, 'error');
        }
    } catch (error) {
        console.error('Error deleting content:', error);
        alert(`Error deleting database entry: ${error.message}`);
        log(`❌ Error deleting content: ${error.message}`, 'error');
    }
}

// Sync content expiration from Castus metadata
async function syncContentExpiration(contentId) {
    console.log('syncContentExpiration called for:', contentId);
    
    // Find the content item
    const content = availableContent.find(c => {
        const itemId = c._id || c.id || c.guid;
        return itemId == contentId || itemId === contentId || String(itemId) === String(contentId);
    });
    
    if (!content) {
        showNotification('Content not found', 'error');
        return;
    }
    
    // Show loading notification
    showNotification('Syncing expiration metadata...', 'info', 10000);
    
    try {
        const response = await fetch('/api/sync-castus-expiration', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                asset_id: content.id || content._id,
                file_path: content.file_path || `${content.file_name}`,
                server: 'source'
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(
                'Expiration Synced',
                `Successfully synced expiration: ${result.message}`,
                'success',
                5000
            );
            
            // Update the content item with new expiration
            if (!content.scheduling) {
                content.scheduling = {};
            }
            content.scheduling.content_expiry_date = result.expiration_date;
            content.scheduling.metadata_synced_at = new Date().toISOString();
            
            // Refresh the display
            displayAvailableContent();
            
        } else {
            showNotification(
                'Sync Failed',
                result.message || 'Failed to sync expiration metadata',
                'error'
            );
        }
        
    } catch (error) {
        console.error('Error syncing expiration:', error);
        showNotification(
            'Error',
            `Failed to sync: ${error.message}`,
            'error'
        );
    }
}

function viewContentDetails(contentId) {
    // Find the content item - convert contentId to match the type
    const content = availableContent.find(c => {
        const itemId = c._id || c.id || c.guid;
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
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <select id="detailsContentType" class="content-type form-control" style="margin: 0; background-color: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color);">
                                <option value="PSA" ${content.content_type && content.content_type.toUpperCase() === 'PSA' ? 'selected' : ''}>PSA</option>
                                <option value="AN" ${content.content_type && content.content_type.toUpperCase() === 'AN' ? 'selected' : ''}>AN</option>
                                <option value="ATLD" ${content.content_type && content.content_type.toUpperCase() === 'ATLD' ? 'selected' : ''}>ATLD</option>
                                <option value="BMP" ${content.content_type && content.content_type.toUpperCase() === 'BMP' ? 'selected' : ''}>BMP</option>
                                <option value="IMOW" ${content.content_type && content.content_type.toUpperCase() === 'IMOW' ? 'selected' : ''}>IMOW</option>
                                <option value="IM" ${content.content_type && content.content_type.toUpperCase() === 'IM' ? 'selected' : ''}>IM</option>
                                <option value="IA" ${content.content_type && content.content_type.toUpperCase() === 'IA' ? 'selected' : ''}>IA</option>
                                <option value="LM" ${content.content_type && content.content_type.toUpperCase() === 'LM' ? 'selected' : ''}>LM</option>
                                <option value="MTG" ${content.content_type && content.content_type.toUpperCase() === 'MTG' ? 'selected' : ''}>MTG</option>
                                <option value="MAF" ${content.content_type && content.content_type.toUpperCase() === 'MAF' ? 'selected' : ''}>MAF</option>
                                <option value="PKG" ${content.content_type && content.content_type.toUpperCase() === 'PKG' ? 'selected' : ''}>PKG</option>
                                <option value="PMO" ${content.content_type && content.content_type.toUpperCase() === 'PMO' ? 'selected' : ''}>PMO</option>
                                <option value="SZL" ${content.content_type && content.content_type.toUpperCase() === 'SZL' ? 'selected' : ''}>SZL</option>
                                <option value="SPP" ${content.content_type && content.content_type.toUpperCase() === 'SPP' ? 'selected' : ''}>SPP</option>
                                <option value="OTHER" ${content.content_type && content.content_type.toUpperCase() === 'OTHER' ? 'selected' : ''}>OTHER</option>
                            </select>
                            <button class="button small primary" onclick="updateContentTypeFromDetails('${contentId}')">
                                <i class="fas fa-save"></i> Update
                            </button>
                        </div>
                        
                        <strong>Duration:</strong>
                        <span>${durationTimecode} (${durationCategory})</span>
                        
                        <strong>File Size:</strong>
                        <span>${formatFileSize(content.file_size)}</span>
                        
                        <strong>Engagement Score:</strong>
                        <span>${content.engagement_score || 'N/A'}%</span>
                        
                        <strong>Creation Date:</strong>
                        <span>${formatCreationDate(content)}</span>
                        
                        <strong>Last Scheduled:</strong>
                        <span>${lastScheduled}</span>
                        
                        <strong>Total Airings:</strong>
                        <span>${totalAirings}</span>
                        
                        <strong>Expiration Date:</strong>
                        <span>${formatExpirationDate(content.scheduling?.content_expiry_date)}</span>
                        
                        <strong>Shelf Life:</strong>
                        <span>${getShelfLifeInfo(content)}</span>
                        
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

// Update content type from details modal
async function updateContentTypeFromDetails(contentId) {
    const newType = document.getElementById('detailsContentType').value;
    
    // Find the content item
    const content = availableContent.find(c => {
        const itemId = c._id || c.id || c.guid;
        return itemId == contentId || itemId === contentId || String(itemId) === String(contentId);
    });
    
    if (!content) {
        window.showNotification('Content not found', 'error');
        return;
    }
    
    // Call the existing updateContentType function
    await updateContentType(contentId, newType);
    
    // Update the modal to reflect the change
    content.content_type = newType.toLowerCase();
    
    // Close and reopen the modal to refresh the display
    closeContentDetailsModal();
    viewContentDetails(contentId);
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
        const response = await window.API.get('/config');
        const config = response.success ? response.config : response;
        
        if (config && config.scheduling) {
            console.log('Loading scheduling configuration:', config.scheduling);
            
            // Load replay delays
            if (config.scheduling.replay_delays) {
                scheduleConfig.REPLAY_DELAYS = config.scheduling.replay_delays;
                console.log('Loaded replay delays:', scheduleConfig.REPLAY_DELAYS);
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
        
        const response = await fetch('/api/list-schedule-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server, path })
        });
        
        
        
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
        
        const response = await fetch('/api/load-schedule-from-ftp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server,
                path,
                filename: selectedScheduleFile,
                schedule_date: scheduleDate
            })
        });
        
        
        
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
        
        // Debug logging
        console.log('fillScheduleGaps debug:');
        console.log('  currentTemplate:', currentTemplate);
        console.log('  window.currentTemplate:', window.currentTemplate);
        console.log('  window.schedulingTemplateState:', window.schedulingTemplateState);
        console.log('  schedulingTemplateState.currentTemplate:', window.schedulingTemplateState?.currentTemplate);
        
        // Check both global currentTemplate and scheduling module's template
        if (!currentTemplate && !window.currentTemplate) {
            // Try to get template from scheduling module
            if (window.schedulingTemplateState && window.schedulingTemplateState.currentTemplate) {
                currentTemplate = window.schedulingTemplateState.currentTemplate;
                window.currentTemplate = currentTemplate; // Also set global
                log('fillScheduleGaps: Using template from scheduling module', 'info');
            } else {
                log('fillScheduleGaps: No current template loaded', 'warning');
                alert('Please load a template first');
                return;
            }
        } else if (window.currentTemplate && !currentTemplate) {
            // Use window.currentTemplate if available
            currentTemplate = window.currentTemplate;
            log('fillScheduleGaps: Using window.currentTemplate', 'info');
        }
        
        // Ensure currentTemplate is set for the rest of the function
        if (!currentTemplate && window.currentTemplate) {
            currentTemplate = window.currentTemplate;
        }
        
        if (!currentTemplate.items || currentTemplate.items.length === 0) {
            log('fillScheduleGaps: Template has no items', 'warning');
            alert('Please load a template with items first');
            return;
        }
        
        // Debug: Log current template items at the very start
        console.log('=== fillScheduleGaps START - currentTemplate state ===');
        console.log('  Type:', currentTemplate.type);
        console.log('  Total items:', currentTemplate.items.length);
        console.log('  First 3 items:');
        currentTemplate.items.slice(0, 3).forEach((item, idx) => {
            console.log(`    Item ${idx}: start_time="${item.start_time}", title="${item.title || item.file_name}"`);
        });
        
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
                const response = await fetch('/api/analyzed-content', {
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
                
                // First, clean the template to only include items with valid start times
                // For weekly templates, ensure items have day prefixes
                const cleanTemplate = {
                    ...currentTemplate,
                    items: currentTemplate.items.filter(item => {
                        if (!item.start_time || item.start_time === "00:00:00:00" || 
                            item.start_time === "00:00:00" || item.start_time === null) {
                            return false;
                        }
                        
                        // For weekly templates, warn if no day prefix but still include the item
                        if (currentTemplate.type === 'weekly' && !item.start_time.toString().includes(' ')) {
                            console.warn(`Weekly template item missing day prefix: "${item.start_time}"`);
                        }
                        
                        return true;
                    })
                };
                
                console.log(`Cleaned template has ${cleanTemplate.items.length} items with valid times (from ${currentTemplate.items.length} total)`);
                console.log('First 3 items being sent:');
                cleanTemplate.items.slice(0, 3).forEach((item, idx) => {
                    console.log(`  Item ${idx}: start_time="${item.start_time}", title="${item.title || item.file_name}"`);
                });
                
                // Debug: Show all items in cleanTemplate before gap calculation
                console.log('Items in cleanTemplate before gap calculation:');
                cleanTemplate.items.forEach((item, idx) => {
                    const startSeconds = currentTemplate.type === 'weekly' && item.start_time.includes(' ') 
                        ? parseWeeklyTimeToSeconds(item.start_time) 
                        : parseTimeToSeconds(item.start_time);
                    const isGap = item.is_gap ? ' [GAP ITEM]' : '';
                    console.log(`  ${idx}: "${item.title || item.file_name}" at ${item.start_time} (${startSeconds/3600}h)${isGap}`);
                    if (item.is_gap) {
                        console.log(`    Gap details: type="${item.gap_type}", duration=${item.duration_seconds}s`);
                    }
                });
                
                // Calculate the actual gaps to fill
                console.log('=== GAP CALCULATION DEBUG ===');
                console.log('Template items before gap calculation:', cleanTemplate.items.length);
                
                // Log ALL items to see what's being passed
                cleanTemplate.items.forEach((item, idx) => {
                    const itemStart = parseTimeToSeconds(item.start_time);
                    console.log(`Item ${idx}: "${item.title || item.content_title || item.file_name}" at ${item.start_time} (${(itemStart/3600).toFixed(2)}h), is_gap=${item.is_gap}`);
                });
                
                const gaps = calculateScheduleGaps(cleanTemplate);
                console.log('Raw gaps from calculateScheduleGaps:', JSON.stringify(gaps));
                console.log('Calculated gaps to fill:', gaps);
                console.log('Gap details:');
                gaps.forEach((gap, idx) => {
                    console.log(`  Gap ${idx + 1}: ${(gap.start/3600).toFixed(2)}h - ${(gap.end/3600).toFixed(2)}h (${((gap.end - gap.start)/3600).toFixed(2)}h)`);
                });
                
                // Debug: Check if there are any gap items that should split these gaps
                const gapItems = cleanTemplate.items.filter(item => {
                    if (item.is_gap === true) return true;
                    const title = (item.title || item.content_title || '').toLowerCase();
                    return title.includes('schedule gap') || title.includes('transition');
                });
                console.log(`Gap items in template: ${gapItems.length}`);
                gapItems.forEach(gapItem => {
                    const gapStart = parseTimeToSeconds(gapItem.start_time);
                    const gapEnd = gapStart + parseFloat(gapItem.duration_seconds || 0);
                    console.log(`  Gap item: "${gapItem.title}" at ${(gapStart/3600).toFixed(2)}h - ${(gapEnd/3600).toFixed(2)}h, is_gap=${gapItem.is_gap}`);
                    
                    // Check which gaps this gap item should split
                    gaps.forEach((gap, idx) => {
                        if (gapStart >= gap.start && gapStart < gap.end) {
                            console.log(`    WARNING: Gap item at ${(gapStart/3600).toFixed(2)}h falls within Gap ${idx + 1}!`);
                            console.log(`    This gap should have been split!`);
                            console.log(`    Expected: Gap 1: ${(gap.start/3600).toFixed(2)}h-${(gapStart/3600).toFixed(2)}h, Gap 2: ${(gapEnd/3600).toFixed(2)}h-${(gap.end/3600).toFixed(2)}h`);
                        }
                    });
                });
                
                console.log('=== END GAP DEBUG ===');
                
                // Check if there are any meaningful gaps to fill
                const totalGapTime = gaps.reduce((sum, gap) => sum + (gap.end - gap.start), 0);
                if (totalGapTime < 60) { // Less than 1 minute of gaps
                    alert('The schedule is already full. There are no significant gaps to fill.');
                    log('fillScheduleGaps: Schedule is already full, no gaps to fill', 'info');
                    return;
                }
                
                // Validate gaps don't contain any fixed items (excluding gap items)
                let invalidGaps = false;
                gaps.forEach((gap, gapIdx) => {
                    cleanTemplate.items.forEach(item => {
                        // Skip gap items in validation
                        if (item.is_gap === true) {
                            return;
                        }
                        
                        // Also skip items that look like gaps based on title
                        const title = (item.title || item.content_title || '').toLowerCase();
                        if (title.includes('schedule gap') || title.includes('transition')) {
                            console.log(`Skipping gap item in validation: "${item.title || item.content_title}"`);
                            return;
                        }
                        
                        const itemStart = currentTemplate.type === 'weekly' && item.start_time.includes(' ')
                            ? parseWeeklyTimeToSeconds(item.start_time)
                            : parseTimeToSeconds(item.start_time);
                        
                        if (itemStart > gap.start && itemStart < gap.end) {
                            console.error(`ERROR: Gap ${gapIdx + 1} (${gap.start/3600}h-${gap.end/3600}h) contains fixed item at ${itemStart/3600}h!`);
                            console.error(`  Item: "${item.title || item.file_name}" at ${item.start_time}`);
                            console.error(`  This will cause overlap issues. Gap calculation is incorrect.`);
                            invalidGaps = true;
                        }
                    });
                });
                
                if (invalidGaps) {
                    alert('Error: Gap calculation found overlapping items. This may be due to items without proper time formatting. Please check the template and try again.');
                    return;
                }
                
                // MANUAL GAP SPLITTING FALLBACK
                // If gaps aren't properly split, do it manually here
                console.log('=== MANUAL GAP SPLIT CHECK ===');
                const manuallySplitGaps = [];
                
                gaps.forEach((gap, idx) => {
                    console.log(`Checking gap ${idx + 1}: ${(gap.start/3600).toFixed(2)}h - ${(gap.end/3600).toFixed(2)}h`);
                    
                    // Find ALL gap items that fall within this gap
                    const gapItemsInRange = [];
                    cleanTemplate.items.forEach(item => {
                        const title = (item.title || item.content_title || '').toLowerCase();
                        if (item.is_gap === true || title.includes('schedule gap') || title.includes('transition')) {
                            const itemStart = parseTimeToSeconds(item.start_time);
                            const itemEnd = itemStart + parseFloat(item.duration_seconds || 0);
                            
                            if (itemStart >= gap.start && itemStart < gap.end) {
                                gapItemsInRange.push({
                                    start: itemStart,
                                    end: itemEnd,
                                    title: item.title || item.content_title
                                });
                                console.log(`  Found gap item within: "${item.title || item.content_title}" at ${(itemStart/3600).toFixed(2)}h`);
                            }
                        }
                    });
                    
                    // If no gap items in this gap, keep it as-is
                    if (gapItemsInRange.length === 0) {
                        manuallySplitGaps.push(gap);
                        console.log(`  No gap items found, keeping gap as-is`);
                    } else {
                        // Sort gap items by start time
                        gapItemsInRange.sort((a, b) => a.start - b.start);
                        
                        // Split the gap around each gap item
                        let currentStart = gap.start;
                        
                        gapItemsInRange.forEach(gapItem => {
                            if (currentStart < gapItem.start) {
                                manuallySplitGaps.push({
                                    start: currentStart,
                                    end: gapItem.start
                                });
                                console.log(`  Created split gap: ${(currentStart/3600).toFixed(2)}h - ${(gapItem.start/3600).toFixed(2)}h`);
                            }
                            currentStart = gapItem.end;
                        });
                        
                        // Add remaining gap after last gap item
                        if (currentStart < gap.end) {
                            manuallySplitGaps.push({
                                start: currentStart,
                                end: gap.end
                            });
                            console.log(`  Created split gap: ${(currentStart/3600).toFixed(2)}h - ${(gap.end/3600).toFixed(2)}h`);
                        }
                    }
                });
                
                console.log(`Final gaps after manual split: ${manuallySplitGaps.length} gaps`);
                manuallySplitGaps.forEach((gap, idx) => {
                    console.log(`  Final gap ${idx + 1}: ${(gap.start/3600).toFixed(2)}h - ${(gap.end/3600).toFixed(2)}h`);
                });
                console.log('=== END MANUAL SPLIT ===');
                
                const response = await fetch('/api/fill-template-gaps', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        template: cleanTemplate,
                        available_content: availableContent,
                        gaps: manuallySplitGaps  // Use manually split gaps
                    })
                });
                
                const result = await response.json();
                
                if (result.success && result.items_added && result.items_added.length > 0) {
                    log(`fillScheduleGaps: Backend added ${result.items_added.length} items using rotation logic`, 'success');
                    
                    // Log the state before adding items
                    console.log('Before adding new items:', cleanTemplate.items.length, 'fixed items');
                    
                    // Preserve all original items (including gap items) and add new items
                    // Note: cleanTemplate already includes gap items since they have valid start_times
                    currentTemplate.items = [...cleanTemplate.items, ...result.items_added];
                    
                    console.log('After adding new items:', currentTemplate.items.length, 'items');
                    
                    // Debug: Log before fillGapsWithProperTimes
                    console.log('Before fillGapsWithProperTimes - First 3 items:');
                    currentTemplate.items.slice(0, 3).forEach((item, idx) => {
                        console.log(`  Item ${idx}: start_time="${item.start_time}", title="${item.title || item.file_name}"`);
                    });
                    
                    // Sort items by start time and fill gaps
                    fillGapsWithProperTimes();
                    
                    console.log('After fillGapsWithProperTimes:', currentTemplate.items.length, 'items');
                    console.log('After fillGapsWithProperTimes - First 3 items:');
                    currentTemplate.items.slice(0, 3).forEach((item, idx) => {
                        console.log(`  Item ${idx}: start_time="${item.start_time}", title="${item.title || item.file_name}"`);
                    });
                    
                    // Update all template references
                    window.currentTemplate = currentTemplate;
                    
                    // Update the scheduling template state if in scheduling module
                    if (window.schedulingTemplateState) {
                        window.schedulingTemplateState.currentTemplate = currentTemplate;
                        window.schedulingTemplateState.templateLoaded = true;
                    }
                    
                    // Update the template display
                    console.log('About to update template display with', currentTemplate.items.length, 'items');
                    
                    try {
                        const activePanel = document.querySelector('.panel:not([style*="display: none"])');
                        console.log('Active panel:', activePanel ? activePanel.id : 'none');
                        
                        if (activePanel && activePanel.id === 'dashboard') {
                            // Only call dashboard display if we're actually in dashboard
                            if (document.getElementById('templateInfo')) {
                                console.log('Calling displayDashboardTemplate');
                                displayDashboardTemplate();
                            }
                        } else if (activePanel && activePanel.id === 'scheduling') {
                            // Use scheduling module's display function
                            console.log('Active panel is scheduling, calling schedulingDisplayTemplate');
                            if (window.schedulingDisplayTemplate) {
                                window.schedulingDisplayTemplate(currentTemplate);
                            } else {
                                console.error('schedulingDisplayTemplate not found');
                            }
                        } else {
                            // Fallback to generic display
                            console.log('Using fallback display method');
                            if (window.schedulingDisplayTemplate) {
                                window.schedulingDisplayTemplate(currentTemplate);
                            } else if (window.displayTemplate) {
                                window.displayTemplate(currentTemplate);
                            }
                        }
                    } catch (displayError) {
                        console.error('Error updating template display:', displayError);
                        console.error('Stack trace:', displayError.stack);
                    }
                    
                    alert(`Successfully added ${result.items_added.length} items to fill the schedule gaps.`);
                    log(`fillScheduleGaps: Template now has ${currentTemplate.items.length} items`, 'success');
                    
                    // Force a refresh of the display
                    console.log('Forcing display refresh with', currentTemplate.items.length, 'items');
                    if (window.schedulingDisplayTemplate) {
                        window.schedulingDisplayTemplate(currentTemplate);
                    }
                } else {
                    log(`fillScheduleGaps: ${result.message || 'No suitable content found to fill gaps'}`, 'warning');
                    
                    // Check if we have overlap details
                    if (result.overlap_details) {
                        const details = result.overlap_details;
                        const detailMsg = `\n\nOverlap Details:\n` +
                            `- New item: "${details.new_item.title}" (${details.new_item.start_hours.toFixed(2)}h - ${details.new_item.end_hours.toFixed(2)}h)\n` +
                            `- Original item: "${details.original_item.title}" at ${details.original_item.start_time} (${details.original_item.start_hours.toFixed(2)}h - ${details.original_item.end_hours.toFixed(2)}h)\n` +
                            `- Gap was: ${details.gap.start_hours.toFixed(2)}h - ${details.gap.end_hours.toFixed(2)}h`;
                        alert(result.message + detailMsg);
                        console.error('Overlap detected:', details);
                    } else if (result.verification_errors) {
                        const errorMsg = result.message + '\n\nVerification Errors:\n' + result.verification_errors.join('\n');
                        alert(errorMsg);
                        console.error('Verification failed:', result.verification_errors);
                    } else {
                        alert(result.message || 'Could not find suitable content to fill the schedule gaps. Try analyzing more content.');
                    }
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
        const response = await fetch('/api/list-schedule-files', {
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
        
        const response = await fetch('/api/load-schedule-template', {
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
            // Debug: Check what we received from backend
            console.log('Raw template from backend - first 3 items:');
            result.template.items.slice(0, 3).forEach((item, idx) => {
                console.log(`  Item ${idx}: start_time="${item.start_time}"`);
            });
            
            currentTemplate = result.template;
            currentTemplate.filename = result.filename;
            currentTemplate.type = result.template.type || 'daily'; // Store schedule type
            
            // Debug: Log loaded template items
            console.log('Template loaded with type:', currentTemplate.type);
            console.log('First 3 items after loading:');
            currentTemplate.items.slice(0, 3).forEach((item, idx) => {
                console.log(`  Item ${idx}: start_time="${item.start_time}", title="${item.title || item.file_name}"`);
            });
            
            // Display template info
            displayTemplate();
            
            // Debug: Log items after displayTemplate
            console.log('First 3 items after displayTemplate:');
            currentTemplate.items.slice(0, 3).forEach((item, idx) => {
                console.log(`  Item ${idx}: start_time="${item.start_time}", title="${item.title || item.file_name}"`);
            });
            
            // Dispatch event for scheduling module
            window.dispatchEvent(new CustomEvent('templateLoaded', {
                detail: { template: currentTemplate }
            }));
            
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

function calculateScheduleGaps(template) {
    console.log('calculateScheduleGaps: Starting gap calculation');
    
    if (!template || !template.items || template.items.length === 0) {
        // No items, entire week is a gap
        if (template.type === 'weekly') {
            return [{
                start: 0,
                end: 7 * 24 * 3600,
                day: 'all'
            }];
        } else {
            return [{
                start: 0,
                end: 24 * 3600,
                day: 'daily'
            }];
        }
    }
    
    const gaps = [];
    const isWeekly = template.type === 'weekly';
    
    // First, log all original items with times
    console.log('=== CRITICAL GAP DETECTION DEBUG ===');
    console.log('Original items with times:');
    template.items.forEach((item, idx) => {
        const title = item.title || item.content_title || item.file_name || 'Unknown';
        const titleLower = title.toLowerCase();
        const isGapByTitle = titleLower.includes('schedule gap') || titleLower.includes('transition');
        
        console.log(`  Item ${idx}: "${title}"`);
        console.log(`    - start_time: ${item.start_time}`);
        console.log(`    - is_gap property: ${item.is_gap} (type: ${typeof item.is_gap})`);
        console.log(`    - title contains 'schedule gap' or 'transition': ${isGapByTitle}`);
        console.log(`    - duration: ${item.duration_seconds}s`);
        
        if (item.start_time) {
            if (item.is_gap === true || isGapByTitle) {
                console.log(`    >>> THIS IS A GAP ITEM (detected by: ${item.is_gap === true ? 'is_gap flag' : 'title match'})`);
            }
        } else {
            console.warn(`    >>> NO START TIME!`);
        }
    });
    console.log('=== END CRITICAL DEBUG ===');
    
    // Count items with valid times (excluding gaps)
    const itemsWithTimes = template.items.filter(item => item.start_time && item.start_time !== "00:00:00" && !item.is_gap).length;
    const gapCount = template.items.filter(item => item.is_gap).length;
    console.log(`Total items: ${template.items.length}, Items with valid times (excluding gaps): ${itemsWithTimes}, Gap items: ${gapCount}`);
    
    // For weekly templates with daily-formatted times, we should warn the user
    if (isWeekly) {
        const itemsWithTimes = template.items.filter(item => item.start_time);
        const allDailyFormat = itemsWithTimes.every(item => !item.start_time.toString().includes(' '));
        
        if (allDailyFormat && itemsWithTimes.length > 0) {
            console.warn('WARNING: Weekly template has daily-formatted times. All meetings appear to be on same day!');
            console.warn('This will cause overlaps. Please update the template to include day prefixes (e.g., "mon 08:00:00")');
        }
    }
    // Sort ALL items by start time (including gaps)
    // We need to include gaps to properly split time ranges around them
    console.log(`Template has ${template.items.length} total items`);
    console.log(`Items with start_time: ${template.items.filter(item => item.start_time).length}`);
    console.log(`Gap items with start_time: ${template.items.filter(item => item.start_time && item.is_gap).length}`);
    
    // Log items before filtering to debug
    console.log(`Items before filtering (showing is_gap property):`, 
        template.items.map(item => ({
            title: item.title || item.content_title || item.file_name,
            start_time: item.start_time,
            is_gap: item.is_gap,
            has_start_time: !!item.start_time
        }))
    );
    
    const sortedItems = [...template.items]
        .filter(item => item.start_time)
        .sort((a, b) => {
        if (isWeekly) {
            // Check if times have day prefix
            const hasDay_a = a.start_time && a.start_time.toString().includes(' ');
            const hasDay_b = b.start_time && b.start_time.toString().includes(' ');
            
            let timeA, timeB;
            if (hasDay_a) {
                timeA = parseWeeklyTimeToSeconds(a.start_time);
            } else {
                // Daily time in weekly template - treat as time on first day (Sunday)
                timeA = parseTimeToSeconds(a.start_time);
            }
            
            if (hasDay_b) {
                timeB = parseWeeklyTimeToSeconds(b.start_time);
            } else {
                // Daily time in weekly template - treat as time on first day (Sunday)
                timeB = parseTimeToSeconds(b.start_time);
            }
            
            return timeA - timeB;
        } else {
            const timeA = parseTimeToSeconds(a.start_time);
            const timeB = parseTimeToSeconds(b.start_time);
            return timeA - timeB;
        }
    });
    
    console.log(`Sorted ${sortedItems.length} items with start times`);
    
    let lastEndTime = 0;
    
    // Find gaps between items
    sortedItems.forEach((item, idx) => {
        let itemStartTime, itemEndTime;
        
        console.log(`\nProcessing sorted item ${idx}:`);
        console.log(`  Title: "${item.title || item.file_name}"`);
        console.log(`  Start time: ${item.start_time}`);
        console.log(`  Duration: ${item.duration_seconds}s`);
        
        if (isWeekly) {
            // Check if time has day prefix
            const hasDay = item.start_time && item.start_time.toString().includes(' ');
            
            if (hasDay) {
                itemStartTime = parseWeeklyTimeToSeconds(item.start_time);
            } else {
                // Daily time in weekly template - treat as time on first day
                itemStartTime = parseTimeToSeconds(item.start_time);
            }
            
            // Calculate end time from duration
            const duration = parseFloat(item.duration_seconds || 0);
            itemEndTime = itemStartTime + duration;
        } else {
            itemStartTime = parseTimeToSeconds(item.start_time);
            const duration = parseFloat(item.duration_seconds || 0);
            itemEndTime = itemStartTime + duration;
        }
        
        console.log(`  Calculated times: start=${itemStartTime}s (${itemStartTime/3600}h), end=${itemEndTime}s (${itemEndTime/3600}h)`);
        console.log(`  Last end time was: ${lastEndTime}s (${lastEndTime/3600}h)`);
        
        // If there's a gap before this item
        if (itemStartTime > lastEndTime + 0.001) { // Add small tolerance for floating point
            const gap = {
                // Round to 3 decimal places to avoid floating point precision issues
                start: Math.round(lastEndTime * 1000) / 1000,
                end: Math.round(itemStartTime * 1000) / 1000
            };
            gaps.push(gap);
            console.log(`Gap found: ${gap.start/3600}h - ${gap.end/3600}h (${(gap.end-gap.start)/3600}h duration)`);
        } else if (itemStartTime < lastEndTime - 0.001) {
            // Items overlap!
            console.warn(`WARNING: Items overlap! Previous item ends at ${lastEndTime/3600}h but current item starts at ${itemStartTime/3600}h`);
            console.warn(`  Previous item extends ${(lastEndTime - itemStartTime)/3600}h into current item`);
        }
        
        console.log(`Item "${item.title || item.file_name}" occupies ${itemStartTime/3600}h - ${itemEndTime/3600}h`);
        // Round to avoid floating point accumulation errors
        lastEndTime = Math.round(Math.max(lastEndTime, itemEndTime) * 1000) / 1000;
    });
    
    // Check for gap at the end
    const targetDuration = isWeekly ? (7 * 24 * 3600) : (24 * 3600);
    if (lastEndTime < targetDuration - 0.001) { // Add small tolerance
        gaps.push({
            // Round to 3 decimal places
            start: Math.round(lastEndTime * 1000) / 1000,
            end: targetDuration
        });
        console.log(`Final gap: ${gaps[gaps.length-1].start/3600}h - ${targetDuration/3600}h (${(targetDuration-gaps[gaps.length-1].start)/3600}h duration)`);
    }
    
    console.log(`Total gaps found: ${gaps.length}`);
    
    // Post-process gaps to exclude any time occupied by gap items
    // Also check for items that look like gaps based on title/content_title
    console.log('=== CHECKING FOR GAP ITEMS IN sortedItems ===');
    console.log(`sortedItems has ${sortedItems.length} items`);
    
    const gapItems = sortedItems.filter(item => {
        // Check is_gap flag first
        const hasGapFlag = item.is_gap === true;
        
        // Fallback: check if title indicates it's a gap
        const title = (item.title || item.content_title || item.file_name || '').toLowerCase();
        const isGapByTitle = title.includes('schedule gap') || title.includes('transition');
        
        // Debug each item
        console.log(`  Checking: "${item.title || item.content_title || item.file_name}" - is_gap=${item.is_gap}, title_match=${isGapByTitle}`);
        
        if (isGapByTitle && !hasGapFlag) {
            console.log(`    >>> IMPORTANT: Found gap item by title but is_gap=${item.is_gap}: "${item.title || item.content_title}"`);
        }
        
        return hasGapFlag || isGapByTitle;
    });
    
    console.log(`=== FOUND ${gapItems.length} GAP ITEMS ===`);
    console.log(`Found ${gapItems.length} gap items to exclude from gaps:`, gapItems.map(g => ({
        title: g.title || g.content_title,
        start_time: g.start_time,
        duration: g.duration_seconds,
        is_gap: g.is_gap,
        detected_by: g.is_gap === true ? 'is_gap flag' : 'title match'
    })));
    const processedGaps = [];
    
    gaps.forEach((gap, idx) => {
        console.log(`  Gap ${idx + 1}: ${gap.start/3600}h - ${gap.end/3600}h`);
        
        // Check if any gap items fall within this gap
        let currentGapStart = gap.start;
        let gapWasSplit = false;
        
        // Sort gap items by start time within this gap
        const gapItemsInRange = gapItems.filter(item => {
            let itemStart;
            if (isWeekly && item.start_time && item.start_time.toString().includes(' ')) {
                itemStart = parseWeeklyTimeToSeconds(item.start_time);
            } else {
                itemStart = parseTimeToSeconds(item.start_time);
            }
            const itemEnd = itemStart + parseFloat(item.duration_seconds || 0);
            
            // Check if gap item overlaps with this gap
            return itemStart < gap.end && itemEnd > gap.start;
        }).sort((a, b) => {
            const aStart = isWeekly && a.start_time.toString().includes(' ') 
                ? parseWeeklyTimeToSeconds(a.start_time) 
                : parseTimeToSeconds(a.start_time);
            const bStart = isWeekly && b.start_time.toString().includes(' ') 
                ? parseWeeklyTimeToSeconds(b.start_time) 
                : parseTimeToSeconds(b.start_time);
            return aStart - bStart;
        });
        
        if (gapItemsInRange.length > 0) {
            console.log(`  Gap contains ${gapItemsInRange.length} gap item(s)`);
            
            gapItemsInRange.forEach(gapItem => {
                const itemStart = isWeekly && gapItem.start_time.toString().includes(' ') 
                    ? parseWeeklyTimeToSeconds(gapItem.start_time) 
                    : parseTimeToSeconds(gapItem.start_time);
                const itemEnd = itemStart + parseFloat(gapItem.duration_seconds || 0);
                
                console.log(`    Gap item "${gapItem.title}" at ${itemStart/3600}h-${itemEnd/3600}h`);
                
                // If there's a gap before the gap item, add it
                if (currentGapStart < itemStart) {
                    processedGaps.push({
                        start: currentGapStart,
                        end: itemStart
                    });
                    console.log(`    Created sub-gap: ${currentGapStart/3600}h-${itemStart/3600}h`);
                    gapWasSplit = true;
                }
                
                // Move past the gap item
                currentGapStart = itemEnd;
            });
            
            // If there's remaining gap after the last gap item
            if (currentGapStart < gap.end) {
                processedGaps.push({
                    start: currentGapStart,
                    end: gap.end
                });
                console.log(`    Created sub-gap: ${currentGapStart/3600}h-${gap.end/3600}h`);
            }
        } else {
            // No gap items in this gap, keep it as-is
            processedGaps.push(gap);
        }
    });
    
    console.log(`Processed gaps: ${processedGaps.length} fillable gaps after excluding gap items`);
    processedGaps.forEach((gap, idx) => {
        console.log(`  Fillable gap ${idx + 1}: ${gap.start/3600}h - ${gap.end/3600}h (${(gap.end-gap.start)/3600}h)`);
    });
    
    return processedGaps;
}

function fillGapsWithProperTimes() {
    if (!currentTemplate || !currentTemplate.items) return;
    
    const isWeekly = currentTemplate.type === 'weekly';
    
    // ALL existing template items should be preserved
    const existingItems = [];
    const newItemsToAdd = [];
    
    console.log('fillGapsWithProperTimes: Total items before:', currentTemplate.items.length);
    
    currentTemplate.items.forEach((item, index) => {
        // Debug logging
        console.log(`Examining item ${index}:`, {
            title: item.title || item.file_name,
            start_time: item.start_time,
            is_fixed_time: item.is_fixed_time,
            has_start_time: !!item.start_time
        });
        
        // Check if this is a fixed-time item (like imported meetings) that must be preserved
        // Also check for "Live Input" items which are always fixed-time events
        // Also check for gap items which must stay at their designated times
        if (item.is_fixed_time === true || 
            item.is_live_input === true || 
            item.title?.startsWith('Live Input') ||
            item.is_gap === true ||
            item.title?.toLowerCase().includes('schedule gap')) {
            // This is a fixed-time item (imported meeting, live event, gap item, etc) - MUST preserve it
            existingItems.push({item: item, originalIndex: index});
            console.log('✓ Fixed-time item:', item.title || item.file_name, 'at', item.start_time);
        } else if (!item.start_time || 
                   item.start_time === "00:00:00:00" || 
                   item.start_time === "00:00:00" || 
                   item.start_time === null) {
            // This is a newly added item without a time yet
            newItemsToAdd.push(item);
            console.log('➕ New item to add:', item.title || item.file_name);
        } else {
            // This is a previously scheduled item that can be rescheduled if needed
            newItemsToAdd.push(item);
            console.log('♻️ Reschedulable item:', item.title || item.file_name, 'at', item.start_time);
        }
    });
    
    console.log('Existing template items:', existingItems.length, 'New items to schedule:', newItemsToAdd.length);
    
    // Log the available content for filling
    if (newItemsToAdd.length > 0) {
        console.log('\nAvailable content for gap filling:');
        newItemsToAdd.slice(0, 5).forEach((item, idx) => {
            const duration = parseFloat(item.duration_seconds || item.file_duration || 0);
            console.log(`  ${idx}: "${item.title || item.file_name}" - ${formatTimeFromSeconds(duration)} (${duration}s)`);
        });
        if (newItemsToAdd.length > 5) {
            console.log(`  ... and ${newItemsToAdd.length - 5} more items`);
        }
    }
    
    // Sort existing items by their start time
    existingItems.sort((a, b) => {
        if (isWeekly) {
            const timeA = parseWeeklyTimeToSeconds(a.item.start_time);
            const timeB = parseWeeklyTimeToSeconds(b.item.start_time);
            return timeA - timeB;
        } else {
            const timeA = parseTimeToSeconds(a.item.start_time);
            const timeB = parseTimeToSeconds(b.item.start_time);
            return timeA - timeB;
        }
    });
    
    // Build new array preserving all existing items and filling gaps with new items
    const finalItemsArray = [];
    
    if (isWeekly) {
        fillWeeklyGapsPreservingExisting(existingItems, newItemsToAdd, finalItemsArray);
    } else {
        fillDailyGapsPreservingExisting(existingItems, newItemsToAdd, finalItemsArray);
    }
    
    // Replace the items array with our properly ordered array
    currentTemplate.items = finalItemsArray;
    
    console.log('fillGapsWithProperTimes: Total items after:', currentTemplate.items.length);
}

function fillWeeklyGapsPreservingExisting(existingItems, newItemsToAdd, finalItemsArray) {
    const days = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
    let newItemIndex = 0;
    const frameGap = 1.0 / 29.976; // One frame at 29.976 fps
    
    // Process each day
    for (let dayIndex = 0; dayIndex < 7; dayIndex++) {
        const dayName = days[dayIndex];
        let currentDayTime = 0; // Start from midnight of this day
        
        // Get existing items for this day only
        const dayExistingItems = existingItems.filter(wrapper => {
            const itemDay = extractDayFromWeeklyTime(wrapper.item.start_time);
            return itemDay === dayName;
        });
        
        // Sort existing items for this day by time
        dayExistingItems.sort((a, b) => {
            const timeA = extractTimeFromWeeklyTime(a.item.start_time);
            const timeB = extractTimeFromWeeklyTime(b.item.start_time);
            return timeA - timeB;
        });
        
        // Process each existing item for this day
        for (let i = 0; i < dayExistingItems.length; i++) {
            const existingItem = dayExistingItems[i].item;
            const existingStartTime = extractTimeFromWeeklyTime(existingItem.start_time);
            
            // Fill gap before this existing item
            const gapEndTime = existingStartTime;
            
            while (currentDayTime < gapEndTime && newItemIndex < newItemsToAdd.length) {
                let foundFittingItem = false;
                
                // Try to find an item that fits in the remaining gap
                for (let j = newItemIndex; j < newItemsToAdd.length; j++) {
                    const newItem = newItemsToAdd[j];
                    const duration = parseFloat(newItem.duration_seconds || newItem.file_duration || 0);
                    
                    // Check if this item fits in the remaining gap (with frame gap)
                    if (currentDayTime + duration + frameGap <= gapEndTime) {
                        newItem.start_time = formatWeeklyTime(dayName, currentDayTime);
                        newItem.end_time = formatWeeklyTime(dayName, currentDayTime + duration);
                        finalItemsArray.push(newItem);
                        currentDayTime += duration + frameGap;
                        
                        // Remove this item from the array by swapping with newItemIndex and incrementing
                        if (j !== newItemIndex) {
                            newItemsToAdd[j] = newItemsToAdd[newItemIndex];
                        }
                        newItemIndex++;
                        foundFittingItem = true;
                        break;
                    }
                }
                
                // If no item fits, we're done trying to fill this gap
                if (!foundFittingItem) {
                    const remainingGap = gapEndTime - currentDayTime;
                    if (remainingGap > 600) { // Log gaps larger than 10 minutes
                        console.warn(`⚠️ Gap of ${formatTimeFromSeconds(remainingGap)} remains before "${existingItem.title || existingItem.file_name}" at ${existingItem.start_time}`);
                    } else if (remainingGap > 60) { // Gaps between 1-10 minutes are acceptable
                        console.log(`Acceptable gap of ${formatTimeFromSeconds(remainingGap)} before "${existingItem.title || existingItem.file_name}" at ${existingItem.start_time}`);
                    }
                    break;
                }
            }
            
            // Add the existing item (preserve it exactly as is)
            finalItemsArray.push(existingItem);
            
            // Update current time to end of existing item
            const existingDuration = parseFloat(existingItem.duration_seconds || existingItem.file_duration || 0);
            currentDayTime = existingStartTime + existingDuration + frameGap;
        }
        
        // Fill remaining time in this day after all existing items
        while (currentDayTime < 24 * 3600 && newItemIndex < newItemsToAdd.length) {
            const newItem = newItemsToAdd[newItemIndex];
            const duration = parseFloat(newItem.duration_seconds || newItem.file_duration || 0);
            
            // Check if item fits within remaining day time
            if (currentDayTime + duration + frameGap <= 24 * 3600) {
                newItem.start_time = formatWeeklyTime(dayName, currentDayTime);
                newItem.end_time = formatWeeklyTime(dayName, currentDayTime + duration);
                finalItemsArray.push(newItem);
                currentDayTime += duration + frameGap;
                newItemIndex++;
            } else {
                // Item doesn't fit in remaining time today, skip to next day
                break;
            }
        }
        
        // Log any remaining gap at end of this day
        const remainingDayTime = 24 * 3600 - currentDayTime;
        if (remainingDayTime > 600) { // Log gaps larger than 10 minutes
            console.warn(`⚠️ Gap of ${formatTimeFromSeconds(remainingDayTime)} remains at end of ${dayName}`);
        } else if (remainingDayTime > 60) { // Gaps between 1-10 minutes are acceptable
            console.log(`Acceptable gap of ${formatTimeFromSeconds(remainingDayTime)} at end of ${dayName}`);
        }
    }
}

function fillWeeklyGaps(itemsWithTimes, itemsWithoutTimes, newItemsArray) {
    const days = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
    let newItemIndex = 0;
    const frameGap = 1.0 / 29.976; // One frame at 29.976 fps (approximately 0.033367 seconds)
    
    // Process each day separately
    for (let dayIndex = 0; dayIndex < 7; dayIndex++) {
        const dayName = days[dayIndex];
        let currentDayTime = 0; // Start from midnight of this day
        console.log(`Processing ${dayName}, starting with item index ${newItemIndex}`);
        
        // Get fixed items for this day only
        const dayFixedItems = itemsWithTimes.filter(wrapper => {
            const itemDay = extractDayFromWeeklyTime(wrapper.item.start_time);
            return itemDay === dayName;
        });
        
        // Sort fixed items for this day by time
        dayFixedItems.sort((a, b) => {
            const timeA = extractTimeFromWeeklyTime(a.item.start_time);
            const timeB = extractTimeFromWeeklyTime(b.item.start_time);
            return timeA - timeB;
        });
        
        // Fill gaps for this day
        for (let i = 0; i <= dayFixedItems.length; i++) {
            let gapEnd;
            
            if (i < dayFixedItems.length) {
                // Gap ends at the next fixed item
                gapEnd = extractTimeFromWeeklyTime(dayFixedItems[i].item.start_time);
            } else {
                // Gap ends at midnight (24 hours)
                gapEnd = 24 * 3600;
            }
            
            // Fill the gap
            while (currentDayTime < gapEnd && newItemIndex < itemsWithoutTimes.length) {
                const item = itemsWithoutTimes[newItemIndex];
                const duration = parseFloat(item.duration_seconds || item.file_duration || 0);
                
                // Check if item fits within this day (don't cross midnight) including frame gap
                if (currentDayTime + duration + frameGap <= gapEnd && currentDayTime + duration + frameGap <= 24 * 3600) {
                    item.start_time = formatWeeklyTime(dayName, currentDayTime);
                    item.end_time = formatWeeklyTime(dayName, currentDayTime + duration);
                    newItemsArray.push(item);
                    currentDayTime += duration + frameGap; // Add frame gap after item
                    newItemIndex++;
                } else {
                    // Item doesn't fit in remaining time today
                    console.log(`Item doesn't fit in ${dayName}, duration ${duration}, remaining time ${gapEnd - currentDayTime}`);
                    // Skip to next day
                    break;
                }
            }
            
            // Add the fixed item (if not the last iteration)
            if (i < dayFixedItems.length) {
                // Push the ORIGINAL item, not a copy, to preserve all properties
                const fixedItem = dayFixedItems[i].item;
                console.log('Adding fixed item:', fixedItem.title || fixedItem.file_name, 'at', fixedItem.start_time);
                newItemsArray.push(fixedItem);
                // Update current time to after this fixed item plus frame gap
                const fixedStartTime = extractTimeFromWeeklyTime(fixedItem.start_time);
                const fixedDuration = parseFloat(fixedItem.duration_seconds || 0);
                currentDayTime = fixedStartTime + fixedDuration + frameGap;
            }
        }
    }
}

function fillDailyGapsPreservingExisting(existingItems, newItemsToAdd, finalItemsArray) {
    // Fill gaps between existing items with new content
    let newItemIndex = 0;
    let currentTime = 0; // Start from midnight
    const frameGap = 1.0 / 29.976; // One frame at 29.976 fps
    
    // Process each existing item and fill gaps before it
    for (let i = 0; i < existingItems.length; i++) {
        const existingItem = existingItems[i].item;
        const existingStartTime = parseTimeToSeconds(existingItem.start_time);
        
        console.log(`\n📍 Processing fixed item ${i}: "${existingItem.title}" at ${existingItem.start_time} (${existingStartTime}s)`);
        console.log(`   Current time position: ${formatTimeFromSeconds(currentTime)} (${currentTime}s)`);
        
        // Fill gap before this existing item
        const gapEndTime = existingStartTime;
        const skippedItems = [];
        
        while (currentTime < gapEndTime && newItemIndex < newItemsToAdd.length) {
            let foundFittingItem = false;
            
            // Try to find an item that fits in the remaining gap
            for (let j = newItemIndex; j < newItemsToAdd.length; j++) {
                const newItem = newItemsToAdd[j];
                const duration = parseFloat(newItem.duration_seconds || newItem.file_duration || 0);
                
                // Check if this item fits in the remaining gap (with frame gap)
                if (currentTime + duration + frameGap <= gapEndTime) {
                    newItem.start_time = formatTimeFromSeconds(currentTime);
                    newItem.end_time = formatTimeFromSeconds(currentTime + duration);
                    finalItemsArray.push(newItem);
                    currentTime += duration + frameGap;
                    
                    // Remove this item from the array by swapping with newItemIndex and incrementing
                    if (j !== newItemIndex) {
                        newItemsToAdd[j] = newItemsToAdd[newItemIndex];
                    }
                    newItemIndex++;
                    foundFittingItem = true;
                    break;
                }
            }
            
            // If no item fits, we're done trying to fill this gap
            if (!foundFittingItem) {
                const remainingGap = gapEndTime - currentTime;
                if (remainingGap > 600) { // Log gaps larger than 10 minutes
                    console.warn(`⚠️ Gap of ${formatTimeFromSeconds(remainingGap)} remains before "${existingItem.title || existingItem.file_name}" at ${existingItem.start_time}`);
                } else if (remainingGap > 60) { // Gaps between 1-10 minutes are acceptable
                    console.log(`Acceptable gap of ${formatTimeFromSeconds(remainingGap)} before "${existingItem.title || existingItem.file_name}" at ${existingItem.start_time}`);
                }
                break;
            }
        }
        
        // Add the existing item (preserve it exactly as is)
        finalItemsArray.push(existingItem);
        console.log(`   ✓ Added fixed item to final array`);
        
        // Update current time to end of existing item
        let existingDuration = parseFloat(existingItem.duration_seconds || existingItem.file_duration || 0);
        
        // If duration is 0 but we have end_time, calculate duration
        if (existingDuration === 0 && existingItem.end_time) {
            const endTime = parseTimeToSeconds(existingItem.end_time);
            existingDuration = endTime - existingStartTime;
            console.log(`   Calculated duration from end_time: ${existingDuration}s`);
        }
        
        currentTime = existingStartTime + existingDuration + frameGap;
        console.log(`   Duration: ${existingDuration}s, New current time: ${formatTimeFromSeconds(currentTime)} (${currentTime}s)`);
    }
    
    // Fill any remaining time after the last existing item
    const endOfDay = 24 * 60 * 60;
    while (currentTime < endOfDay && newItemIndex < newItemsToAdd.length) {
        let foundFittingItem = false;
        
        // Try to find an item that fits in the remaining time
        for (let j = newItemIndex; j < newItemsToAdd.length; j++) {
            const newItem = newItemsToAdd[j];
            const duration = parseFloat(newItem.duration_seconds || newItem.file_duration || 0);
            
            // Check if this item fits in the remaining day time
            if (currentTime + duration + frameGap <= endOfDay) {
                newItem.start_time = formatTimeFromSeconds(currentTime);
                newItem.end_time = formatTimeFromSeconds(currentTime + duration);
                finalItemsArray.push(newItem);
                currentTime += duration + frameGap;
                
                // Remove this item from the array by swapping with newItemIndex and incrementing
                if (j !== newItemIndex) {
                    newItemsToAdd[j] = newItemsToAdd[newItemIndex];
                }
                newItemIndex++;
                foundFittingItem = true;
                break;
            }
        }
        
        // If no item fits, we're done
        if (!foundFittingItem) {
            const remainingTime = endOfDay - currentTime;
            if (remainingTime > 600) { // Log gaps larger than 10 minutes
                console.warn(`⚠️ Gap of ${formatTimeFromSeconds(remainingTime)} remains at end of day starting at ${formatTimeFromSeconds(currentTime)}`);
            } else if (remainingTime > 60) { // Gaps between 1-10 minutes are acceptable
                console.log(`Acceptable gap of ${formatTimeFromSeconds(remainingTime)} at end of day starting at ${formatTimeFromSeconds(currentTime)}`);
            }
            break;
        }
    }
}

function fillDailyGaps(itemsWithTimes, itemsWithoutTimes, newItemsArray) {
    // Now fill gaps with the new items
    let newItemIndex = 0;
    let currentTime = 0; // Start from midnight
    const frameGap = 1.0 / 29.976; // One frame at 29.976 fps (approximately 0.033367 seconds)
    
    // Add items before the first fixed item
    if (itemsWithTimes.length > 0) {
        const firstFixedTime = parseTimeToSeconds(itemsWithTimes[0].item.start_time);
        
        // Fill from midnight to first fixed item
        while (currentTime < firstFixedTime && newItemIndex < itemsWithoutTimes.length) {
            const item = itemsWithoutTimes[newItemIndex];
            const duration = parseFloat(item.duration_seconds || item.file_duration || 0);
            
            // Check if this item fits before the fixed item (including frame gap)
            if (currentTime + duration + frameGap <= firstFixedTime) {
                item.start_time = formatTimeFromSeconds(currentTime);
                item.end_time = formatTimeFromSeconds(currentTime + duration);
                newItemsArray.push(item);
                currentTime += duration + frameGap; // Add frame gap after item
                newItemIndex++;
            } else {
                // Item doesn't fit, skip to after the fixed item
                break;
            }
        }
    }
    
    // Add the fixed items and fill gaps between them
    for (let i = 0; i < itemsWithTimes.length; i++) {
        const fixedItem = itemsWithTimes[i].item;
        newItemsArray.push(fixedItem);
        
        // Update current time to end of this fixed item
        const fixedStartTime = parseTimeToSeconds(fixedItem.start_time);
        const fixedDuration = parseFloat(fixedItem.duration_seconds || 0);
        currentTime = fixedStartTime + fixedDuration + frameGap; // Add frame gap after fixed item
        
        // Determine the next fixed item time or end of day
        const nextFixedTime = (i < itemsWithTimes.length - 1) 
            ? parseTimeToSeconds(itemsWithTimes[i + 1].item.start_time)
            : 24 * 60 * 60; // End of day
        
        // Fill gap until next fixed item
        while (currentTime < nextFixedTime && newItemIndex < itemsWithoutTimes.length) {
            const item = itemsWithoutTimes[newItemIndex];
            const duration = parseFloat(item.duration_seconds || item.file_duration || 0);
            
            // Check if this item fits before the next fixed item (including frame gap)
            if (currentTime + duration + frameGap <= nextFixedTime) {
                item.start_time = formatTimeFromSeconds(currentTime);
                item.end_time = formatTimeFromSeconds(currentTime + duration);
                newItemsArray.push(item);
                currentTime += duration + frameGap; // Add frame gap after item
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
        newItemsArray.push(item);
        currentTime += duration + frameGap; // Add frame gap after item
        newItemIndex++;
    }
}

function parseWeeklyTimeToSeconds(timeStr) {
    if (!timeStr) return 0;
    
    // Parse "mon 8:00 am" or "mon 08:00:00" format
    const days = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
    const parts = timeStr.toLowerCase().split(' ');
    if (parts.length < 2) return 0;
    
    const dayIndex = days.indexOf(parts[0]);
    if (dayIndex === -1) return 0;
    
    // Get the time part (could be "8:00" with "am" separate, or "8:00am" together, or "08:00:00" in 24h format)
    let timePart = parts[1];
    let isPM = false;
    let is24HourFormat = false;
    
    // Check if it's 24-hour format (has seconds or is in HH:MM:SS format)
    if (timePart.split(':').length === 3 || (timePart.split(':').length === 2 && !timePart.includes('am') && !timePart.includes('pm') && parts.length === 2)) {
        is24HourFormat = true;
    }
    
    if (!is24HourFormat) {
        // 12-hour format with AM/PM
        if (parts.length > 2 && (parts[2] === 'am' || parts[2] === 'pm')) {
            isPM = parts[2] === 'pm';
        } else if (timePart.includes('am') || timePart.includes('pm')) {
            isPM = timePart.includes('pm');
            timePart = timePart.replace(/am|pm/i, '').trim();
        }
    }
    
    const timeParts = timePart.split(':');
    let hours = parseInt(timeParts[0]) || 0;
    const minutes = parseInt(timeParts[1]) || 0;
    // Parse seconds as float to preserve milliseconds
    let seconds = 0;
    if (timeParts.length > 2) {
        // Remove milliseconds temporarily if they exist (e.g., "45.123")
        const secPart = timeParts[2].split('.');
        seconds = parseFloat(timeParts[2]) || 0;
    }
    
    // Convert to 24-hour format if needed
    if (!is24HourFormat) {
        if (isPM && hours !== 12) hours += 12;
        if (!isPM && hours === 12) hours = 0;
    }
    // For 24-hour format, hours are already correct (12 means noon, not midnight)
    
    // Total seconds from start of week
    return (dayIndex * 24 * 3600) + (hours * 3600) + (minutes * 60) + seconds;
}

function extractDayFromWeeklyTime(timeStr) {
    if (!timeStr) return '';
    const parts = timeStr.toLowerCase().split(' ');
    return parts[0] || '';
}

function extractTimeFromWeeklyTime(timeStr) {
    if (!timeStr) return 0;
    
    // Parse "mon 8:00 am" format - get just the time portion in seconds
    const parts = timeStr.toLowerCase().split(' ');
    if (parts.length < 2) return 0;
    
    let timePart = parts[1];
    let isPM = false;
    
    if (parts.length > 2 && (parts[2] === 'am' || parts[2] === 'pm')) {
        isPM = parts[2] === 'pm';
    } else if (timePart.includes('am') || timePart.includes('pm')) {
        isPM = timePart.includes('pm');
        timePart = timePart.replace(/am|pm/i, '').trim();
    }
    
    const timeParts = timePart.split(':');
    let hours = parseInt(timeParts[0]) || 0;
    const minutes = parseInt(timeParts[1]) || 0;
    const seconds = parseFloat(timeParts[2]) || 0;
    
    // Convert to 24-hour format
    if (isPM && hours !== 12) hours += 12;
    if (!isPM && hours === 12) hours = 0;
    
    return (hours * 3600) + (minutes * 60) + seconds;
}

function formatWeeklyTime(dayName, totalSeconds) {
    // Ensure seconds are within a single day
    const daySeconds = totalSeconds % (24 * 3600);
    
    const hours = Math.floor(daySeconds / 3600);
    const minutes = Math.floor((daySeconds % 3600) / 60);
    const wholeSeconds = Math.floor(daySeconds % 60);
    const milliseconds = Math.round((daySeconds % 1) * 1000);
    
    // Convert to 12-hour format
    let displayHours = hours;
    let period = 'am';
    
    if (hours >= 12) {
        period = 'pm';
        if (hours > 12) displayHours = hours - 12;
    }
    if (displayHours === 0) displayHours = 12;
    
    return `${dayName} ${displayHours}:${minutes.toString().padStart(2, '0')}:${wholeSeconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')} ${period}`;
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
    } else if (parts.length === 2) {
        // Handle HH:MM format (like "17:00")
        hours = parseInt(parts[0]) || 0;
        minutes = parseInt(parts[1]) || 0;
        seconds = 0;
    } else if (parts.length === 1) {
        // Handle just hours
        hours = parseInt(parts[0]) || 0;
        minutes = 0;
        seconds = 0;
    }
    
    return hours * 3600 + minutes * 60 + seconds;
}

function formatTimeFromSeconds(totalSeconds, format = 'daily') {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const wholeSeconds = Math.floor(totalSeconds % 60);
    const milliseconds = Math.round((totalSeconds % 1) * 1000);
    
    // Format with milliseconds instead of frames
    if (format === 'daily') {
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${wholeSeconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
    }
    // Add weekly format support if needed
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${wholeSeconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
}

function recalculateTemplateTimes() {
    if (!currentTemplate || !currentTemplate.items) return;
    
    console.log('recalculateTemplateTimes called for', currentTemplate.type, 'template');
    
    // For weekly templates, check if items already have day prefixes
    if (currentTemplate.type === 'weekly') {
        const hasAnyDayPrefix = currentTemplate.items.some(item => 
            item.start_time && item.start_time.toString().includes(' ')
        );
        
        if (hasAnyDayPrefix) {
            console.log('Weekly template already has day prefixes - skipping recalculation');
            return;
        }
    }
    
    // Check if ALL items have valid times (not just the first one)
    const allItemsHaveValidTimes = currentTemplate.items.length > 0 && 
                                  currentTemplate.items.every(item => 
                                      item.start_time && 
                                      item.start_time !== "00:00:00:00" &&
                                      item.start_time !== "00:00:00" &&
                                      item.start_time !== null
                                  );
    
    if (allItemsHaveValidTimes) {
        console.log('All items have valid times - skipping recalculation');
        // Don't recalculate - all times are already set
        return;
    }
    
    // Handle based on template type
    if (currentTemplate.type === 'weekly') {
        // For weekly templates, only recalculate items that don't have times
        let currentSeconds = 0;
        
        currentTemplate.items.forEach(item => {
            // If item already has a valid time with day prefix, skip it
            if (item.start_time && item.start_time.toString().includes(' ')) {
                // Item has day prefix, calculate currentSeconds from its end time
                const startSeconds = parseWeeklyTimeToSeconds(item.start_time);
                const duration = parseFloat(item.duration_seconds) || 0;
                currentSeconds = startSeconds + duration;
                
                // Ensure end_time also has day prefix if needed
                if (!item.end_time || !item.end_time.toString().includes(' ')) {
                    item.end_time = formatTimeFromSeconds(currentSeconds, 'weekly');
                }
            } else {
                // No valid time, calculate it
                item.start_time = formatTimeFromSeconds(currentSeconds, 'weekly');
                
                const duration = parseFloat(item.duration_seconds) || 0;
                currentSeconds += duration;
                
                item.end_time = formatTimeFromSeconds(currentSeconds, 'weekly');
            }
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
    
    // Check if we need to recalculate times
    // For weekly templates, only recalculate if times don't have day prefixes
    let needsRecalculation = false;
    if (currentTemplate.type === 'weekly' && currentTemplate.items && currentTemplate.items.length > 0) {
        // Check if any item is missing day prefix
        const dayPrefixes = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
        needsRecalculation = currentTemplate.items.some(item => {
            if (!item.start_time) return true;
            const hasPrefix = dayPrefixes.some(day => item.start_time.toLowerCase().startsWith(day));
            return !hasPrefix;
        });
    } else {
        // For daily templates, always recalculate
        needsRecalculation = true;
    }
    
    if (needsRecalculation) {
        recalculateTemplateTimes();
    }
    
    // Show template info
    const templateInfoEl = document.getElementById('dashboardTemplateInfo');
    if (templateInfoEl) {
        templateInfoEl.style.display = 'block';
    }
    const scheduleType = currentTemplate.type === 'weekly' ? 'Weekly' : 'Daily';
    const templateNameEl = document.getElementById('dashboardTemplateName');
    if (templateNameEl) {
        templateNameEl.textContent = `${currentTemplate.filename || 'Untitled'} (${scheduleType})`;
    }
    const templateItemCountEl = document.getElementById('dashboardTemplateItemCount');
    if (templateItemCountEl) {
        templateItemCountEl.textContent = currentTemplate.items.length;
    }
    
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
            <div class="template-item header">
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
            const itemTitle = hasAssetId ? item.file_path : `${item.file_path} (Not in database - must be added from Available Content)`;
            
            // Check if this is a Live Input item
            const isLiveInput = item.filename && item.filename.toLowerCase().includes('live input');
            const itemClasses = isLiveInput ? 'template-item live-input' : 'template-item';
            
            // Format start and end times to show milliseconds
            const startTimeFormatted = formatTimeWithMilliseconds(item.start_time || '00:00:00');
            const endTimeFormatted = formatTimeWithMilliseconds(item.end_time || '00:00:00');
            
            html += `
                <div class="${itemClasses}" ${!hasAssetId ? 'style="opacity: 0.6;"' : ''}>
                    <span class="template-item-index">${index + 1}</span>
                    <span class="template-item-time">${startTimeFormatted}</span>
                    <span class="template-item-title" title="${itemTitle}">
                        ${item.filename}
                        ${!hasAssetId ? ' <i class="fas fa-exclamation-triangle warning-icon"></i>' : ''}
                    </span>
                    <span class="template-item-duration">${durationTimecode}</span>
                    <span class="template-item-end">${endTimeFormatted}</span>
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
        
        const dashboardTemplateInfo = document.getElementById('dashboardTemplateInfo');
        if (dashboardTemplateInfo) {
            dashboardTemplateInfo.style.display = 'none';
        }
        const dashboardTemplateDisplay = document.getElementById('dashboardTemplateDisplay');
        if (dashboardTemplateDisplay) {
            dashboardTemplateDisplay.innerHTML = '<p style="text-align: center; color: #666;">Load a template file to begin editing</p>';
        }
        
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
    const modal = document.getElementById('templateLibraryModal');
    if (!modal) {
        console.error('Template library modal not found!');
        return;
    }
    
    modal.style.display = 'block';
    loadTemplateLibrary();
    
    // Add click handlers directly when showing the modal
    setTimeout(() => {
        // Find and attach to close button (X)
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            console.log('Attaching click handler to X button');
            console.log('X button element:', closeBtn);
            console.log('X button HTML:', closeBtn.outerHTML);
            console.log('X button onclick before:', closeBtn.onclick);
            
            // Remove any existing onclick attribute
            closeBtn.removeAttribute('onclick');
            
            // Add event listener instead of onclick
            closeBtn.addEventListener('click', function(e) {
                console.log('X button clicked via addEventListener');
                console.log('Event:', e);
                console.log('Event target:', e.target);
                
                try {
                    if (e) {
                        e.preventDefault();
                        e.stopPropagation();
                    }
                    closeTemplateLibraryModal();
                } catch (error) {
                    console.error('Error in X button click handler:', error);
                    // Force close
                    const modalToClose = document.getElementById('templateLibraryModal');
                    if (modalToClose) {
                        modalToClose.style.display = 'none';
                    }
                }
            }, true); // Use capture phase
            
            // Also try direct onclick as backup
            closeBtn.onclick = function() {
                console.log('X button clicked via direct onclick');
                closeTemplateLibraryModal();
                return false;
            };
        } else {
            console.error('X button not found in template library modal');
        }
        
        // Find and attach to Close button
        const closeFooterBtn = modal.querySelector('.modal-footer button.secondary');
        if (closeFooterBtn) {
            console.log('Attaching click handler to Close button');
            closeFooterBtn.onclick = function(e) {
                console.log('Close button clicked via onclick');
                e.preventDefault();
                e.stopPropagation();
                closeTemplateLibraryModal();
                return false;
            };
        } else {
            console.error('Close button not found in template library modal');
        }
        
        // Also add click outside modal to close
        modal.onclick = function(e) {
            if (e.target === modal) {
                console.log('Clicked outside modal content');
                closeTemplateLibraryModal();
            }
        };
    }, 100);
}

function closeTemplateLibraryModal() {
    console.log('closeTemplateLibraryModal called');
    const modal = document.getElementById('templateLibraryModal');
    if (modal) {
        // Force hide with multiple methods
        modal.style.display = 'none';
        modal.style.visibility = 'hidden';
        modal.classList.remove('active');
        modal.setAttribute('style', 'display: none !important');
        
        console.log('Template library modal closed');
        console.log('Modal display style after closing:', window.getComputedStyle(modal).display);
        
        // Also remove any backdrop if exists
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) {
            backdrop.remove();
        }
        
        // Clear any event handlers that might be interfering
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.onclick = null;
        }
        const closeFooterBtn = modal.querySelector('.modal-footer button.secondary');
        if (closeFooterBtn) {
            closeFooterBtn.onclick = null;
        }
        modal.onclick = null;
    } else {
        console.error('Template library modal not found!');
    }
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
    const templateInfo = document.getElementById('dashboardTemplateInfo');
    if (templateInfo) {
        templateInfo.style.display = 'block';
    }
    
    // Show export button
    const exportBtn = document.getElementById('exportTemplateBtn');
    if (exportBtn) {
        exportBtn.style.display = 'inline-block';
    }
    const scheduleType = currentTemplate.type === 'weekly' ? 'Weekly' : currentTemplate.type === 'monthly' ? 'Monthly' : 'Daily';
    // Use filename as the primary name source
    const templateName = currentTemplate.filename || currentTemplate.name || 'Untitled';
    
    const templateNameEl = document.getElementById('dashboardTemplateName');
    if (templateNameEl) {
        templateNameEl.textContent = `${templateName} (${scheduleType})`;
    }
    
    const itemCountEl = document.getElementById('dashboardTemplateItemCount');
    if (itemCountEl) {
        itemCountEl.textContent = currentTemplate.items ? currentTemplate.items.length : 0;
    }
    
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
    
    const durationEl = document.getElementById('dashboardTemplateDuration');
    if (durationEl) {
        durationEl.textContent = 
            `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    
    // Display template items
    const templateDisplay = document.getElementById('dashboardTemplateDisplay');
    
    if (!templateDisplay) {
        // If dashboard elements don't exist, we might be in scheduling panel, just return
        return;
    }
    
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
        
        // Format start and end times with milliseconds
        const startTimeTimecode = formatTimeWithMilliseconds(item.start_time || '00:00:00');
        const endTimeTimecode = formatTimeWithMilliseconds(item.end_time || '00:00:00');
        
        html += `
            <div class="template-item ${!hasAssetId ? 'missing-asset' : ''}">
                <span class="template-item-index">${index + 1}</span>
                <span class="template-item-time">${startTimeTimecode}</span>
                <span class="template-item-title">
                    ${item.title || item.name || item.file_name || item.filename || 'Untitled'}
                    ${!hasAssetId ? ' <i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i>' : ''}
                </span>
                <span class="template-item-duration">${durationTimecode}</span>
                <span class="template-item-end">${endTimeTimecode}</span>
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

// Delete all templates from library
function deleteAllTemplates() {
    if (savedTemplates.length === 0) {
        showNotification('No templates to delete', 'info');
        return;
    }
    
    if (confirm(`Delete all ${savedTemplates.length} templates? This cannot be undone.`)) {
        savedTemplates = [];
        localStorage.setItem('savedTemplates', JSON.stringify(savedTemplates));
        loadTemplateLibrary();
        log('All templates deleted from library', 'info');
        showNotification('All templates deleted', 'success');
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
    
    // Sort ALL items by start time (including gaps)
    // We need gaps to properly calculate time ranges
    const sortedItems = [...template.items]
        .sort((a, b) => {
            const aSeconds = parseTimeToSeconds(a.start_time, template.type);
            const bSeconds = parseTimeToSeconds(b.start_time, template.type);
            return aSeconds - bSeconds;
        });
    
    // If all items are gaps, treat as empty schedule
    if (sortedItems.length === 0) {
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
        // Calculate end time (gap items don't have end_time property)
        const currentItem = sortedItems[i];
        const currentStart = parseTimeToSeconds(currentItem.start_time, template.type);
        const currentDuration = parseFloat(currentItem.duration_seconds || 0);
        const currentEnd = currentItem.end_time 
            ? parseTimeToSeconds(currentItem.end_time, template.type)
            : currentStart + currentDuration;
        const nextStart = parseTimeToSeconds(sortedItems[i + 1].start_time, template.type);
        
        if (nextStart > currentEnd) {
            gaps.push({
                startTime: currentItem.end_time || formatTimeFromSeconds(currentEnd, template.type),
                endTime: sortedItems[i + 1].start_time,
                startSeconds: currentEnd,
                endSeconds: nextStart,
                duration: nextStart - currentEnd
            });
        }
    }
    
    // Check for gap at the end
    const lastItem = sortedItems[sortedItems.length - 1];
    const lastItemStart = parseTimeToSeconds(lastItem.start_time, template.type);
    const lastItemDuration = parseFloat(lastItem.duration_seconds || 0);
    const lastItemEnd = lastItem.end_time 
        ? parseTimeToSeconds(lastItem.end_time, template.type)
        : lastItemStart + lastItemDuration;
    const scheduleEnd = template.type === 'weekly' ? 7 * 24 * 3600 : 24 * 3600;
    
    if (lastItemEnd < scheduleEnd) {
        gaps.push({
            startTime: lastItem.end_time || formatTimeFromSeconds(lastItemEnd, template.type),
            endTime: template.type === 'weekly' ? 'sat 11:59:59.999 pm' : '23:59:59',
            startSeconds: lastItemEnd,
            endSeconds: scheduleEnd,
            duration: scheduleEnd - lastItemEnd
        });
    }
    
    // Post-process gaps to exclude any time occupied by gap items
    // Also check for items that look like gaps based on title/content_title
    const gapItems = sortedItems.filter(item => {
        // Check is_gap flag first
        if (item.is_gap === true) return true;
        
        // Fallback: check if title indicates it's a gap
        const title = (item.title || item.content_title || '').toLowerCase();
        const isGapByTitle = title.includes('schedule gap') || title.includes('transition');
        
        return isGapByTitle;
    });
    const processedGaps = [];
    
    gaps.forEach(gap => {
        let currentGapStart = gap.startSeconds;
        
        // Find gap items within this gap
        const gapItemsInRange = gapItems.filter(item => {
            const itemStart = parseTimeToSeconds(item.start_time, template.type);
            const itemDuration = parseFloat(item.duration_seconds || 0);
            const itemEnd = itemStart + itemDuration;
            return itemStart < gap.endSeconds && itemEnd > gap.startSeconds;
        }).sort((a, b) => {
            const aStart = parseTimeToSeconds(a.start_time, template.type);
            const bStart = parseTimeToSeconds(b.start_time, template.type);
            return aStart - bStart;
        });
        
        if (gapItemsInRange.length > 0) {
            gapItemsInRange.forEach(gapItem => {
                const itemStart = parseTimeToSeconds(gapItem.start_time, template.type);
                const itemDuration = parseFloat(gapItem.duration_seconds || 0);
                const itemEnd = itemStart + itemDuration;
                
                // If there's a gap before the gap item, add it
                if (currentGapStart < itemStart) {
                    processedGaps.push({
                        startTime: gap.startTime,
                        endTime: gapItem.start_time,
                        startSeconds: currentGapStart,
                        endSeconds: itemStart,
                        duration: itemStart - currentGapStart
                    });
                }
                
                // Move past the gap item
                currentGapStart = itemEnd;
            });
            
            // If there's remaining gap after the last gap item
            if (currentGapStart < gap.endSeconds) {
                processedGaps.push({
                    startTime: sortedItems.find(i => {
                        const itemStart = parseTimeToSeconds(i.start_time, template.type);
                        const itemDuration = parseFloat(i.duration_seconds || 0);
                        const itemEnd = i.end_time 
                            ? parseTimeToSeconds(i.end_time, template.type)
                            : itemStart + itemDuration;
                        return itemEnd === currentGapStart;
                    })?.end_time || formatTimeFromSeconds(currentGapStart, template.type),
                    endTime: gap.endTime,
                    startSeconds: currentGapStart,
                    endSeconds: gap.endSeconds,
                    duration: gap.endSeconds - currentGapStart
                });
            }
        } else {
            // No gap items in this gap, keep it as-is
            processedGaps.push(gap);
        }
    });
    
    return processedGaps;
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
    // Check if we should use 24-hour format by looking at existing template items
    let use24HourFormat = false;
    if (window.currentTemplate && window.currentTemplate.items) {
        // Check first few items with valid start times
        for (let i = 0; i < Math.min(5, window.currentTemplate.items.length); i++) {
            const item = window.currentTemplate.items[i];
            if (item.start_time && typeof item.start_time === 'string') {
                // If the time doesn't contain 'am' or 'pm', it's 24-hour format
                if (!item.start_time.toLowerCase().includes('am') && !item.start_time.toLowerCase().includes('pm')) {
                    use24HourFormat = true;
                    break;
                }
            }
        }
    }
    
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
        // Regular daily format
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const milliseconds = Math.round((seconds % 1) * 1000);
        const wholeSeconds = Math.floor(seconds);
        
        if (use24HourFormat) {
            // Return in 24-hour format to match the template
            let timeStr = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${wholeSeconds.toString().padStart(2, '0')}`;
            if (milliseconds > 0) {
                timeStr += `.${milliseconds.toString().padStart(3, '0')}`;
            }
            return timeStr;
        } else {
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
        const response = await fetch('/api/export-template', {
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

// Add Schedule Gap function - creates an intentional gap in the schedule
async function addScheduleGap() {
    try {
        log('addScheduleGap: Function called', 'info');
        
        // Get current template
        let currentTemplate = null;
        if (window.scheduling && window.scheduling.getCurrentTemplate) {
            currentTemplate = window.scheduling.getCurrentTemplate();
        } else if (window.currentTemplate) {
            currentTemplate = window.currentTemplate;
        }
        
        if (!currentTemplate) {
            alert('Please load a template first');
            return;
        }
        
        if (!currentTemplate.items || currentTemplate.items.length === 0) {
            alert('The template is empty. Add some content before creating gaps.');
            return;
        }
        
        // Create modal for gap input
        const isWeekly = currentTemplate.type === 'weekly';
        
        const modalHtml = `
            <div id="scheduleGapModal" class="modal" style="display: block;">
                <div class="modal-content" style="max-width: 400px;">
                    <div class="modal-header">
                        <h3>Add Schedule Gap</h3>
                        <button class="close-button" onclick="document.getElementById('scheduleGapModal').remove()">&times;</button>
                    </div>
                    <div class="modal-body">
                        <p>Create an intentional gap in the schedule where no content will be scheduled.</p>
                        
                        ${isWeekly ? `
                        <div class="form-group">
                            <label>Day of Week:</label>
                            <select id="gapDayOfWeek" class="form-control">
                                <option value="sun">Sunday</option>
                                <option value="mon">Monday</option>
                                <option value="tue">Tuesday</option>
                                <option value="wed">Wednesday</option>
                                <option value="thu">Thursday</option>
                                <option value="fri">Friday</option>
                                <option value="sat">Saturday</option>
                            </select>
                        </div>
                        ` : ''}
                        
                        <div class="form-group">
                            <label>Gap Start Time:</label>
                            <input type="time" id="gapStartTime" value="17:00" class="form-control">
                            <small class="form-text">Default: 5:00 PM</small>
                        </div>
                        
                        <div class="form-group">
                            <label>Gap Duration (minutes):</label>
                            <input type="number" id="gapDuration" value="5" min="1" max="60" class="form-control">
                            <small class="form-text">Default: 5 minutes</small>
                        </div>
                        
                        <div class="form-group">
                            <label>Gap Type:</label>
                            <select id="gapType" class="form-control">
                                <option value="transition">Transition Gap (for schedule changes)</option>
                                <option value="maintenance">Maintenance Window</option>
                                <option value="custom">Custom Gap</option>
                            </select>
                        </div>
                        
                        <div class="form-actions" style="margin-top: 20px;">
                            <button class="button primary" onclick="confirmAddScheduleGap()">Add Gap</button>
                            <button class="button secondary" onclick="document.getElementById('scheduleGapModal').remove()">Cancel</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
    } catch (error) {
        log(`addScheduleGap: ERROR - ${error.message}`, 'error');
        console.error('Error in addScheduleGap:', error);
        alert(`Error: ${error.message}`);
    }
}

// Confirm and add the schedule gap
async function confirmAddScheduleGap() {
    try {
        const startTime = document.getElementById('gapStartTime').value;
        const duration = parseInt(document.getElementById('gapDuration').value);
        const gapType = document.getElementById('gapType').value;
        
        if (!startTime || !duration) {
            alert('Please enter both start time and duration');
            return;
        }
        
        // Get current template
        let currentTemplate = null;
        if (window.scheduling && window.scheduling.getCurrentTemplate) {
            currentTemplate = window.scheduling.getCurrentTemplate();
        } else if (window.currentTemplate) {
            currentTemplate = window.currentTemplate;
        }
        
        if (!currentTemplate) {
            alert('Template not found');
            return;
        }
        
        // Handle weekly schedules
        const isWeekly = currentTemplate.type === 'weekly';
        let formattedStartTime = startTime;
        
        if (isWeekly) {
            const dayOfWeek = document.getElementById('gapDayOfWeek').value;
            if (!dayOfWeek) {
                alert('Please select a day of week');
                return;
            }
            // Format time for weekly schedule (e.g., "mon 17:00")
            const [hours, minutes] = startTime.split(':');
            const hour12 = hours % 12 || 12;
            const ampm = hours >= 12 ? 'pm' : 'am';
            formattedStartTime = `${dayOfWeek} ${hour12}:${minutes} ${ampm}`;
        } else {
            // For daily templates, format time to match existing items
            // Check if template uses 12-hour or 24-hour format by looking at existing items
            let use12HourFormat = false;
            if (currentTemplate.items && currentTemplate.items.length > 0) {
                // Check if any existing item has AM/PM
                const firstItemTime = currentTemplate.items[0].start_time || '';
                use12HourFormat = firstItemTime.toLowerCase().includes('am') || firstItemTime.toLowerCase().includes('pm');
            }
            
            if (use12HourFormat) {
                // Convert to 12-hour format with AM/PM
                const [hours, minutes] = startTime.split(':');
                const hour = parseInt(hours);
                const hour12 = hour % 12 || 12;
                const ampm = hour >= 12 ? 'pm' : 'am';
                formattedStartTime = `${hour12.toString().padStart(2, '0')}:${minutes.padStart(2, '0')} ${ampm}`;
            } else {
                // Use 24-hour format with seconds and milliseconds to match existing format
                const [hours, minutes] = startTime.split(':');
                formattedStartTime = `${hours.padStart(2, '0')}:${minutes.padStart(2, '0')}:00.000`;
            }
        }
        
        // Convert time to seconds
        const [hours, minutes] = startTime.split(':').map(Number);
        const startSeconds = hours * 3600 + minutes * 60;
        const endSeconds = startSeconds + (duration * 60);
        
        // Add gap as a special item in the template
        const gapItem = {
            id: 'gap_' + Date.now(),
            title: `Schedule Gap (${gapType})`,
            content_title: `Schedule Gap - ${duration} minutes`,
            start_time: formattedStartTime,
            duration_seconds: duration * 60,
            is_gap: true,
            gap_type: gapType,
            file_name: '',
            file_path: '',
            asset_id: null
        };
        
        // Find the right position to insert the gap
        let insertIndex = currentTemplate.items.length;
        for (let i = 0; i < currentTemplate.items.length; i++) {
            const item = currentTemplate.items[i];
            const itemStartSeconds = parseTimeToSeconds(item.start_time, currentTemplate.type);
            if (itemStartSeconds > startSeconds) {
                insertIndex = i;
                break;
            }
        }
        
        // Insert the gap
        currentTemplate.items.splice(insertIndex, 0, gapItem);
        
        // Recalculate times
        recalculateTemplateTimes();
        
        // Update display
        if (window.scheduling && window.scheduling.displayTemplate) {
            window.scheduling.displayTemplate(currentTemplate);
        } else if (window.displayTemplate) {
            window.displayTemplate(currentTemplate);
        }
        
        // Close modal
        document.getElementById('scheduleGapModal').remove();
        
        log(`Schedule gap added: ${startTime} for ${duration} minutes`, 'success');
        showNotification('Success', `Added ${duration}-minute gap at ${startTime}`, 'success');
        
    } catch (error) {
        log(`confirmAddScheduleGap: ERROR - ${error.message}`, 'error');
        console.error('Error confirming schedule gap:', error);
        alert(`Error adding gap: ${error.message}`);
    }
}

// Make template functions globally accessible
window.showLoadTemplateModal = showLoadTemplateModal;
window.showLoadWeeklyTemplateModal = showLoadWeeklyTemplateModal;
window.showLoadMonthlyTemplateModal = showLoadMonthlyTemplateModal;
window.fillScheduleGaps = fillScheduleGaps;
window.addScheduleGap = addScheduleGap;
window.confirmAddScheduleGap = confirmAddScheduleGap;
window.showTemplateLibrary = showTemplateLibrary;
window.closeTemplateLibraryModal = closeTemplateLibraryModal;
window.viewTemplate = viewTemplate;
window.loadSavedTemplate = loadSavedTemplate;
window.exportTemplate = exportTemplate;
window.deleteTemplate = deleteTemplate;

// Make content loading functions globally accessible
window.loadAvailableContent = loadAvailableContent;
window.sortContent = sortContent;
window.getSortIcon = getSortIcon;
window.viewContentDetails = viewContentDetails;
window.addToTemplate = addToTemplate;
window.getContentTypeLabel = getContentTypeLabel;
window.formatDurationTimecode = formatDurationTimecode;
window.getDurationCategory = getDurationCategory;
window.closeTemplateExportModal = closeTemplateExportModal;
window.confirmTemplateExport = confirmTemplateExport;
window.exportCurrentTemplate = exportCurrentTemplate;
window.createScheduleFromTemplate = createScheduleFromTemplate;

async function createScheduleFromTemplate() {
    // Get current template from all possible locations
    let template = window.currentTemplate || 
                  (window.schedulingTemplateState && window.schedulingTemplateState.currentTemplate) ||
                  schedulingTemplateState.currentTemplate;
    
    if (!template || !template.items || template.items.length === 0) {
        alert('No template loaded. Please load a template first.');
        return;
    }
    
    // First, validate that all files exist on the FTP servers
    log('Validating template files...', 'info');
    
    try {
        const validateResponse = await fetch('/api/validate-template-files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                items: template.items
            })
        });
        
        const validateResult = await validateResponse.json();
        
        if (validateResult.success && validateResult.missing_files && validateResult.missing_files.length > 0) {
            // Show missing files modal
            window.missingFilesData = {
                missing_files: validateResult.missing_files,
                template: template,
                callback: () => continueCreateSchedule(template)
            };
            
            showMissingFilesModal(validateResult.missing_files);
            return;
        }
        
        // If no missing files, continue with creation
        continueCreateSchedule(template);
        
    } catch (error) {
        console.error('Error validating template files:', error);
        alert('Error validating template files. Please check your connection and try again.');
    }
}

async function continueCreateSchedule(template) {
    // Get appropriate default date based on template type
    const today = new Date();
    let defaultDate = today.toISOString().split('T')[0];
    let datePromptMessage = 'Enter the air date for this schedule (YYYY-MM-DD):';
    
    if (template.type === 'weekly') {
        // For weekly templates, suggest the next Sunday
        const daysUntilSunday = (7 - today.getDay()) % 7;
        const nextSunday = new Date(today);
        nextSunday.setDate(today.getDate() + (daysUntilSunday || 7)); // If today is Sunday, get next Sunday
        defaultDate = nextSunday.toISOString().split('T')[0];
        datePromptMessage = 'Enter any date in the week (schedule will start on Sunday of that week) (YYYY-MM-DD):';
    }
    
    // Prompt for air date
    const airDate = prompt(datePromptMessage, defaultDate);
    if (!airDate) {
        return; // User cancelled
    }
    
    // Validate date format
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (!dateRegex.test(airDate)) {
        alert('Invalid date format. Please use YYYY-MM-DD format.');
        return;
    }
    
    // Generate default name based on template type
    let defaultScheduleName;
    if (template.type === 'weekly') {
        // Calculate the Sunday and Saturday for the week
        // Use UTC to avoid timezone issues
        const selectedDate = new Date(airDate + 'T00:00:00Z');
        const dayOfWeek = selectedDate.getUTCDay();
        const sunday = new Date(selectedDate);
        
        // If it's not already Sunday (day 0), go back to Sunday
        if (dayOfWeek !== 0) {
            sunday.setUTCDate(selectedDate.getUTCDate() - dayOfWeek);
        }
        
        const saturday = new Date(sunday);
        saturday.setUTCDate(sunday.getUTCDate() + 6);
        
        const sundayStr = sunday.toISOString().split('T')[0];
        const saturdayStr = saturday.toISOString().split('T')[0];
        defaultScheduleName = `Weekly Schedule: ${sundayStr} - ${saturdayStr}`;
    } else {
        defaultScheduleName = `Daily Schedule for ${airDate}`;
    }
    
    const scheduleName = prompt('Enter a name for this schedule:', defaultScheduleName);
    if (!scheduleName) {
        return; // User cancelled
    }
    
    log(`Creating schedule from template: ${scheduleName} for ${airDate}`, 'info');
    
    // Filter out missing files if user chose to remove them
    let itemsToCreate = template.items;
    if (window.missingFilesData && window.missingFilesData.removed_asset_ids) {
        itemsToCreate = template.items.filter(item => 
            !window.missingFilesData.removed_asset_ids.includes(item.asset_id)
        );
    }
    
    try {
        const response = await fetch('/api/create-schedule-from-template', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                air_date: airDate,
                schedule_name: scheduleName,
                channel: 'Comcast Channel 26',
                template_type: template.type || 'daily',  // Include template type
                items: itemsToCreate
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Handle both daily and weekly schedule responses
            if (result.schedule_ids) {
                // Weekly schedule created
                log(`Weekly schedule created successfully! ${result.days_created} days created`, 'success');
                alert(`Weekly schedule created successfully!\n\nSchedule: ${scheduleName}\nStart Date: ${airDate}\nDays Created: ${result.days_created}\nItems: ${result.added_count} total\n\nYou can now view these schedules in the Schedules panel.`);
            } else {
                // Daily schedule created
                log(`Schedule created successfully! Schedule ID: ${result.schedule_id}`, 'success');
                alert(`Schedule created successfully!\n\nSchedule: ${scheduleName}\nAir Date: ${airDate}\nItems: ${result.added_count}\n\nYou can now view this schedule in the Schedules panel.`);
            }
            
            // Optionally switch to schedules view
            const switchToSchedules = confirm('Would you like to switch to the Schedules panel to view the new schedule?');
            if (switchToSchedules) {
                // Switch to scheduling panel
                const schedulingBtn = document.querySelector('[onclick="showPanel(\'scheduling\')"]');
                if (schedulingBtn) {
                    schedulingBtn.click();
                }
                
                // After a short delay to ensure panel is switched, expand Schedule Management and load schedules
                setTimeout(() => {
                    // Find and expand the Schedule Management card
                    const scheduleManagementCard = Array.from(document.querySelectorAll('.scheduling-card')).find(card => {
                        const header = card.querySelector('h3');
                        return header && header.textContent.includes('Schedule Management');
                    });
                    
                    if (scheduleManagementCard && scheduleManagementCard.classList.contains('collapsed')) {
                        const header = scheduleManagementCard.querySelector('h3');
                        if (header) {
                            header.click(); // This will expand the card
                        }
                    }
                    
                    // Load the schedules list
                    if (window.listAllSchedules) {
                        window.listAllSchedules();
                    } else if (typeof listAllSchedules === 'function') {
                        listAllSchedules();
                    }
                }, 200);
            }
        } else {
            log(`Failed to create schedule: ${result.message}`, 'error');
            alert(`Failed to create schedule: ${result.message}`);
        }
    } catch (error) {
        log(`Error creating schedule: ${error.message}`, 'error');
        alert(`Error creating schedule: ${error.message}`);
    }
}

function addToTemplate(assetId) {
    if (!currentTemplate) {
        log('Please load a template first', 'error');
        return;
    }
    
    console.log('Adding to template, assetId:', assetId);
    
    // Check if item already exists in template to prevent duplicates
    if (currentTemplate.items && currentTemplate.items.length > 0) {
        const existingItem = currentTemplate.items.find(item => 
            item.asset_id == assetId || 
            item.content_id == assetId ||
            (item.guid && item.guid === assetId)
        );
        
        if (existingItem) {
            window.showNotification('This item is already in the template', 'warning');
            return;
        }
    }
    
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
        
        // Prepare schedule data - include items with valid asset IDs or live inputs
        const validItems = currentTemplate.items.filter(item => {
            // Include regular content with asset IDs
            if (item.content_id || item.asset_id) return true;
            
            // Include live inputs (they won't have asset_id but will have is_live_input flag)
            if (item.is_live_input || item.title?.startsWith('Live Input')) return true;
            
            return false;
        });
        
        if (validItems.length === 0) {
            log('No valid items in template. Items must be added from Available Content or be Live Inputs.', 'error');
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
        
        const response = await fetch('/api/create-schedule-from-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(scheduleData)
        });
        
        
        
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
            const response = await fetch('/api/export-template', {
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

// Scanning configuration functions (removed - no longer needed)

async function scanSelectedFolders() {
    // Always scan only the On-Air Content folder
    const scanOnAir = true;
    
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
            const sourceResponse = await fetch('/api/scan-files', {
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
            const targetResponse = await fetch('/api/scan-files', {
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
        
        // We no longer scan the Recordings folder
        
        log(`Total files found: ${sourceFiles.length} source, ${targetFiles.length} target`);
        
        // Display scanned files
        displayScannedFiles();
        
        // Update dashboard stats to show file count
        updateDashboardStats();
        
        // Enable compare button
        document.querySelector('button[onclick="compareFiles()"]').disabled = false;
        document.getElementById('analyzeFilesBtn').disabled = false;
        
    } catch (error) {
        log(`Error during file scan: ${error.message}`, 'error');
    }
    
    isScanning = false;
}

// Meeting Trimmer functions
let trimSettings = {
    server: 'target',
    source_path: '/mnt/main/Recordings',
    dest_path: '/mnt/main/ATL26 On-Air Content/MEETINGS',
    keep_original: true
};

let currentTrimFile = null;
let autoTrimInterval = null;
let selectedFile = null; // For enhanced trim modal

function showTrimSettings() {
    document.getElementById('trimSettingsModal').classList.add('active');
}

function closeTrimSettingsModal() {
    document.getElementById('trimSettingsModal').classList.remove('active');
}

function saveTrimSettings() {
    trimSettings.server = document.getElementById('trimServer').value;
    trimSettings.source_path = document.getElementById('trimSourcePath').value;
    trimSettings.dest_path = document.getElementById('trimDestPath').value;
    trimSettings.keep_original = document.getElementById('keepOriginal').checked;
    
    // Save to localStorage
    localStorage.setItem('trimSettings', JSON.stringify(trimSettings));
    
    closeTrimSettingsModal();
    showNotification('Trim settings saved', 'success');
}

async function refreshRecordingsList() {
    try {
        console.log('Refreshing recordings with settings:', trimSettings);
        
        const params = new URLSearchParams({
            server: trimSettings.server,
            source_path: trimSettings.source_path,
            dest_path: trimSettings.dest_path
        });
        
        console.log('Fetching from:', `/api/meeting-recordings?${params}`);
        
        const response = await fetch(`/api/meeting-recordings?${params}`);
        const data = await response.json();
        
        console.log('Response data:', data);
        
        if (data.status === 'success') {
            console.log(`Found ${data.recordings.length} recordings`);
            if (data.recordings.length === 0) {
                // Check if FTP is configured
                const configResponse = await fetch('/api/config');
                const configData = await configResponse.json();
                
                if (!configData.config || !configData.config.target || !configData.config.target.host) {
                    showNotification('Please configure the target server in the Servers tab first', 'warning');
                    displayRecordings([]);
                    return;
                }
            }
            displayRecordings(data.recordings);
        } else {
            console.error('Failed to load recordings:', data.message);
            showNotification('Failed to load recordings: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error loading recordings:', error);
        showNotification('Error loading recordings', 'error');
    }
}

function displayRecordings(recordings) {
    const container = document.getElementById('recordingsList');
    
    if (!recordings || recordings.length === 0) {
        container.innerHTML = '<div class="no-recordings">No meeting recordings found</div>';
        return;
    }
    
    container.innerHTML = recordings.map(recording => `
        <div class="recording-item">
            <div class="recording-info">
                <div class="recording-name">${recording.relative_path || recording.filename}</div>
                <div class="recording-meta">
                    <span>Duration: ${formatDuration(recording.duration)}</span>
                    <span>Size: ${formatFileSize(recording.size)}</span>
                    <span>Modified: ${new Date(recording.modified).toLocaleString()}</span>
                </div>
            </div>
            <div class="recording-actions">
                ${recording.is_trimmed 
                    ? '<span class="status-badge trimmed">Trimmed</span>' 
                    : `<button class="button primary small" onclick='openTrimAnalysisModal(${JSON.stringify(recording)})'>
                         <i class="fas fa-cut"></i> Analyze & Trim
                       </button>`
                }
            </div>
        </div>
    `).join('');
}

// Convert seconds to HH:MM:SS.S format
function secondsToTimecode(seconds) {
    if (!seconds && seconds !== 0) return 'Unknown';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = (seconds % 60).toFixed(1);
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.padStart(4, '0')}`;
}

// Open enhanced trim analysis modal
window.openTrimAnalysisModal = function(file) {
    selectedFile = file;
    selectedFile.server_type = trimSettings.server; // Add server type
    currentTrimFile = file; // Keep for backward compatibility
    
    // Update modal content with file info
    document.getElementById('trimAnalysisFilename').textContent = file.relative_path || file.path || file.filename;
    
    // Clear trim time inputs
    document.getElementById('trimAnalysisStartTime').value = '';
    document.getElementById('trimAnalysisEndTime').value = '';
    document.getElementById('trimStartTimecode').value = '';
    document.getElementById('trimEndTimecode').value = '';
    document.getElementById('trimAnalysisNewDuration').textContent = '--:--:--';
    
    // Clear detected words
    document.getElementById('startWords').textContent = 'No words detected yet';
    document.getElementById('endWords').textContent = 'No words detected yet';
    
    // Reset button states
    document.getElementById('downloadForTrimBtn').disabled = false;
    document.getElementById('downloadForTrimBtn').innerHTML = '<i class="fas fa-download"></i> Download File';
    document.getElementById('downloadForTrimBtn').classList.remove('success');
    document.getElementById('viewOriginalBtn').disabled = true;
    // Preview buttons will be enabled after download for manual trimming
    document.getElementById('previewStartBtn').disabled = true;
    document.getElementById('previewEndBtn').disabled = true;
    document.getElementById('executeTrimBtn').disabled = true;
    document.getElementById('viewTrimmedGroup').style.display = 'none';
    document.getElementById('deleteTrimmedBtn').disabled = true;
    
    // Clear any stored temp path
    if (selectedFile) {
        delete selectedFile.tempPath;
        delete selectedFile.fileSize;
    }
    
    // Hide any status messages
    const statusDiv = document.getElementById('trimAnalysisStatus');
    if (statusDiv) {
        statusDiv.style.display = 'none';
    }
    
    // Show modal
    document.getElementById('trimAnalysisModal').classList.add('active');
}

// Download file for trim operations
window.downloadForTrim = async function() {
    if (!selectedFile) return;
    
    try {
        const downloadBtn = document.getElementById('downloadForTrimBtn');
        const viewOriginalBtn = document.getElementById('viewOriginalBtn');
        
        // Disable download button and show progress
        downloadBtn.disabled = true;
        downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';
        
        showNotification('Downloading file for trim operations...', 'info');
        
        const response = await fetch('/api/download-for-trim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: selectedFile.path,
                server: trimSettings.server
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Store the temp path for later use
            selectedFile.tempPath = data.temp_path;
            selectedFile.fileSize = data.file_size;
            
            // Update UI
            downloadBtn.innerHTML = '<i class="fas fa-check"></i> Downloaded';
            downloadBtn.classList.add('success');
            viewOriginalBtn.disabled = false;
            
            // Enable preview buttons for manual trimming
            document.getElementById('previewStartBtn').disabled = false;
            document.getElementById('previewEndBtn').disabled = false;
            
            // Store duration if available
            if (data.duration) {
                selectedFile.duration = data.duration;
                // Set default end trim to last frame
                document.getElementById('trimAnalysisEndTime').value = data.duration;
                document.getElementById('trimEndTimecode').value = secondsToTimecode(data.duration);
                selectedFile.trimEnd = data.duration;
            }
            
            const sizeInMB = (data.file_size / (1024 * 1024)).toFixed(2);
            
            if (data.already_cached) {
                showNotification(`File already downloaded (${sizeInMB} MB)`, 'success');
            } else {
                showNotification(`File downloaded successfully (${sizeInMB} MB)`, 'success');
            }
        } else {
            downloadBtn.disabled = false;
            downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download File';
            showNotification(`Error: ${data.message}`, 'error');
        }
    } catch (error) {
        console.error('Error downloading file:', error);
        const downloadBtn = document.getElementById('downloadForTrimBtn');
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download File';
        showNotification('Error downloading file', 'error');
    }
};

// View original file
window.viewOriginalFile = async function() {
    if (!selectedFile) return;
    
    try {
        // Check if file has been downloaded
        if (!selectedFile.tempPath) {
            showNotification('Please download the file first', 'warning');
            return;
        }
        
        showNotification('Opening file preview...', 'info');
        
        // Open the downloaded file via the backend
        const filename = selectedFile.tempPath.split('/').pop();
        const fileUrl = window.APIConfig ? window.APIConfig.getURL(`/view-temp-file/${filename}`) : `http://127.0.0.1:5000/api/view-temp-file/${filename}`;
        window.open(fileUrl, '_blank');
        
    } catch (error) {
        console.error('Error viewing original file:', error);
        showNotification('Error viewing original file', 'error');
    }
};

// Find trim points
window.findTrimPoints = async function(useAI = false) {
    if (!selectedFile) return;
    
    try {
        const method = useAI ? 'Fast AI detection' : 'Transcription analysis';
        showNotification(`Analyzing meeting boundaries using ${method}...`, 'info');
        document.getElementById('trimStartTimecode').value = 'Analyzing...';
        document.getElementById('trimEndTimecode').value = 'Analyzing...';
        
        const response = await fetch('/api/analyze-trim-points', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: selectedFile.path,
                server: trimSettings.server,
                use_ai: useAI
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            selectedFile.trimStart = data.start_time;
            selectedFile.trimEnd = data.end_time;
            selectedFile.originalDuration = data.duration;
            
            // Update UI
            document.getElementById('trimStartTimecode').value = secondsToTimecode(data.start_time);
            document.getElementById('trimEndTimecode').value = secondsToTimecode(data.end_time);
            document.getElementById('trimAnalysisStartTime').value = data.start_time;
            document.getElementById('trimAnalysisEndTime').value = data.end_time;
            
            // Update detected words
            if (data.start_words) {
                document.getElementById('startWords').textContent = data.start_words;
            }
            if (data.end_words) {
                document.getElementById('endWords').textContent = data.end_words;
            }
            const trimmedDuration = data.end_time - data.start_time;
            if (document.getElementById('trimmedDuration')) {
                document.getElementById('trimmedDuration').textContent = secondsToTimecode(trimmedDuration);
            }
            
            // Enable preview buttons
            document.getElementById('previewStartBtn').disabled = false;
            document.getElementById('previewEndBtn').disabled = false;
            
            // Update the new duration display and enable trim button
            updateNewDuration();
            if (data.end_time > data.start_time) {
                document.getElementById('executeTrimBtn').disabled = false;
            }
            
            showNotification('Trim points found successfully', 'success');
        } else {
            showNotification(`Error: ${data.message}`, 'error');
        }
    } catch (error) {
        console.error('Error analyzing trim points:', error);
        showNotification('Error analyzing file', 'error');
        // Reset UI on error
        document.getElementById('trimStartTimecode').value = '';
        document.getElementById('trimEndTimecode').value = '';
    }
};

// Preview trim start with interactive selection
window.previewTrimStart = async function() {
    if (!selectedFile) return;
    
    // Check if file has been downloaded
    if (!selectedFile.tempPath) {
        showNotification('Please download the file first', 'warning');
        return;
    }
    
    // Open interactive video modal
    openVideoTrimModal('start');
};

// Preview trim end with interactive selection
window.previewTrimEnd = async function() {
    if (!selectedFile) return;
    
    // Check if file has been downloaded
    if (!selectedFile.tempPath) {
        showNotification('Please download the file first', 'warning');
        return;
    }
    
    // Open interactive video modal
    openVideoTrimModal('end');
};

// Trim file
window.trimFile = async function() {
    if (!selectedFile || selectedFile.trimStart === undefined || selectedFile.trimEnd === undefined) {
        showNotification('Please find trim points first', 'warning');
        return;
    }
    
    try {
        showNotification('Trimming file...', 'info');
        
        // Generate trimmed filename
        const originalName = selectedFile.relative_path || selectedFile.filename || 'recording.mp4';
        const filename = originalName.split('/').pop();
        
        // Extract date from filename (format: YYYY-MM-DD at HHMMSS)
        const dateMatch = filename.match(/(\d{4})-(\d{2})-(\d{2})\s+at\s+\d{6}\s+(.+)\.mp4$/i);
        let dateStr, title;
        
        if (dateMatch) {
            // Extract date parts and title
            const year = dateMatch[1].substr(-2); // Last 2 digits of year
            const month = dateMatch[2];
            const day = dateMatch[3];
            dateStr = `${year}${month}${day}`;
            title = dateMatch[4].trim(); // The title after the timestamp
        } else {
            // Fallback to current date if pattern doesn't match
            const date = new Date();
            dateStr = `${date.getFullYear().toString().substr(-2)}${(date.getMonth() + 1).toString().padStart(2, '0')}${date.getDate().toString().padStart(2, '0')}`;
            title = filename.replace(/\.mp4$/i, '');
        }
        
        const trimmedName = `${dateStr}_MTG_${title}.mp4`;
        
        const response = await fetch(window.API ? `${window.APIConfig.baseURL}/trim-recording` : '/api/trim-recording', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: selectedFile.path,
                server: trimSettings.server,
                start_time: selectedFile.trimStart,
                end_time: selectedFile.trimEnd,
                new_filename: trimmedName
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            selectedFile.trimmedPath = data.output_path;
            selectedFile.trimmedName = trimmedName;
            
            // Populate the filename field with the trimmed name
            document.getElementById('trimAnalysisNewFilename').value = trimmedName;
            
            // Show view trimmed button and enable final step buttons
            document.getElementById('viewTrimmedGroup').style.display = 'block';
            document.getElementById('copyCastusBtn').disabled = false;
            document.getElementById('deleteTrimmedBtn').disabled = false;
            
            showNotification('File trimmed successfully', 'success');
        } else {
            showNotification(`Error: ${data.message}`, 'error');
        }
    } catch (error) {
        console.error('Error trimming file:', error);
        showNotification('Error trimming file', 'error');
    }
};

// View trimmed file
window.viewTrimmedFile = async function() {
    if (!selectedFile || !selectedFile.trimmedPath) return;
    
    try {
        showNotification('Opening trimmed file preview...', 'info');
        
        // Open the trimmed file via the backend
        const filename = selectedFile.trimmedPath.split('/').pop();
        const fileUrl = window.APIConfig ? window.APIConfig.getURL(`/view-temp-file/${filename}`) : `http://127.0.0.1:5000/api/view-temp-file/${filename}`;
        window.open(fileUrl, '_blank');
    } catch (error) {
        console.error('Error viewing trimmed file:', error);
        showNotification('Error viewing trimmed file', 'error');
    }
};

// New function to copy to both Castus servers
window.copyToBothCastusServers = async function() {
    if (!selectedFile || !selectedFile.trimmedPath) return;
    
    try {
        // Get the filename from the input field
        const finalFilename = document.getElementById('trimAnalysisNewFilename').value;
        
        if (!finalFilename) {
            showNotification('Please enter a filename', 'error');
            return;
        }
        
        // Show initial progress
        const statusDiv = document.getElementById('trimAnalysisStatus');
        statusDiv.style.display = 'block';
        statusDiv.className = 'alert alert-info';
        document.getElementById('trimAnalysisStatusText').textContent = 'Starting copy to both Castus servers...';
        
        // Show initial notification
        showNotification(
            'Copy Started',
            'Copying trimmed file to both Castus servers...',
            'info',
            15000
        );
        
        // Track results
        const results = {
            castus1: { success: false, message: '' },
            castus2: { success: false, message: '' }
        };
        
        // Copy to Castus1 (don't delete temp file yet)
        try {
            results.castus1 = await copyToSingleServer('castus1', finalFilename, false, false);
            if (results.castus1.success) {
                showNotification(
                    'Castus1 Copy Complete',
                    `Successfully copied to Castus1: ${finalFilename}`,
                    'success',
                    5000
                );
            }
        } catch (error) {
            results.castus1.message = error.message;
        }
        
        // Copy to Castus2 (delete temp file after this copy)
        try {
            results.castus2 = await copyToSingleServer('castus2', finalFilename, false, true);
            if (results.castus2.success) {
                showNotification(
                    'Castus2 Copy Complete',
                    `Successfully copied to Castus2: ${finalFilename}`,
                    'success',
                    5000
                );
            }
        } catch (error) {
            results.castus2.message = error.message;
        }
        
        // Update status based on results
        const bothSuccess = results.castus1.success && results.castus2.success;
        const partialSuccess = results.castus1.success || results.castus2.success;
        
        if (bothSuccess) {
            statusDiv.className = 'alert alert-success';
            statusDiv.innerHTML = `<i class="fas fa-check"></i> <span id="trimAnalysisStatusText">Successfully copied to both Castus servers</span>`;
            
            showNotification(
                'Copy Complete',
                `Successfully copied ${finalFilename} to both Castus servers`,
                'success',
                5000
            );
        } else if (partialSuccess) {
            let successServer = results.castus1.success ? 'Castus1' : 'Castus2';
            let failedServer = results.castus1.success ? 'Castus2' : 'Castus1';
            let failedMessage = results.castus1.success ? results.castus2.message : results.castus1.message;
            
            statusDiv.className = 'alert alert-warning';
            statusDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> <span id="trimAnalysisStatusText">Copied to ${successServer} only. Failed on ${failedServer}: ${failedMessage}</span>`;
            
            showNotification(
                'Partial Success',
                `Copied to ${successServer} but failed on ${failedServer}`,
                'warning',
                7000
            );
        } else {
            statusDiv.className = 'alert alert-error';
            statusDiv.innerHTML = `<i class="fas fa-times"></i> <span id="trimAnalysisStatusText">Failed to copy to both servers</span>`;
            
            showNotification(
                'Copy Failed',
                'Failed to copy to both Castus servers',
                'error',
                5000
            );
        }
        
        // Always refresh the recordings list
        refreshRecordingsList();
        
    } catch (error) {
        console.error('Error in copyToBothCastusServers:', error);
        const statusDiv = document.getElementById('trimAnalysisStatus');
        statusDiv.style.display = 'block';
        statusDiv.className = 'alert alert-error';
        statusDiv.innerHTML = `<i class="fas fa-times"></i> <span id="trimAnalysisStatusText">Unexpected error: ${error.message}</span>`;
        
        showNotification(
            'Error',
            `Unexpected error: ${error.message}`,
            'error',
            5000
        );
    }
};

// Helper function to copy to a single server
async function copyToSingleServer(targetServer, finalFilename, showNotifications = true, deleteTemp = true) {
    try {
        // First check if file exists on target server
        const checkResponse = await fetch('/api/check-file-exists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: finalFilename,
                dest_folder: trimSettings.dest_path,
                server: targetServer
            })
        });
        
        const checkData = await checkResponse.json();
        
        if (checkData.exists) {
            if (!confirm(`File "${finalFilename}" already exists on ${targetServer}. Do you want to overwrite it?`)) {
                return { success: false, message: 'User cancelled overwrite' };
            }
        }
        
        // Show progress notification if enabled
        if (showNotifications) {
            showNotification(
                'Copying',
                `Copying to ${targetServer}...`,
                'info',
                10000
            );
        }
        
        const response = await fetch('/api/copy-trimmed-recording', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_path: selectedFile.trimmedPath,
                filename: finalFilename,
                dest_folder: trimSettings.dest_path,
                server: targetServer,
                keep_original: trimSettings.keep_original,
                delete_temp: deleteTemp
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            if (showNotifications) {
                showNotification(
                    'Copy Complete',
                    `Successfully copied to ${targetServer}`,
                    'success',
                    5000
                );
            }
            return { success: true, message: data.destination_path };
        } else {
            return { success: false, message: data.message || 'Unknown error' };
        }
        
    } catch (error) {
        console.error(`Error copying to ${targetServer}:`, error);
        return { success: false, message: error.message };
    }
}

// Keep the old function for backward compatibility but have it use the new one
window.copyToDestination = async function(targetServer) {
    if (!selectedFile || !selectedFile.trimmedPath) return;
    
    try {
        // Get the filename from the input field (user may have edited it)
        const finalFilename = document.getElementById('trimAnalysisNewFilename').value;
        
        if (!finalFilename) {
            showNotification('Please enter a filename', 'error');
            return;
        }
        
        // First check if file exists on target server
        const checkResponse = await fetch('/api/check-file-exists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: finalFilename,
                dest_folder: trimSettings.dest_path,
                server: targetServer
            })
        });
        
        const checkData = await checkResponse.json();
        
        if (checkData.exists) {
            if (!confirm(`File "${finalFilename}" already exists on ${targetServer}. Do you want to overwrite it?`)) {
                return;
            }
        }
        
        // Show progress
        const statusDiv = document.getElementById('trimAnalysisStatus');
        statusDiv.style.display = 'block';
        statusDiv.className = 'alert alert-info';
        document.getElementById('trimAnalysisStatusText').textContent = `Copying to ${targetServer}...`;
        
        // Show notification that copying has started
        showNotification(
            'File Copy Started',
            `Copying trimmed file to ${targetServer}...`,
            'info',
            10000 // Show for 10 seconds since copying might take time
        );
        
        const response = await fetch('/api/copy-trimmed-recording', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_path: selectedFile.trimmedPath,
                filename: finalFilename,
                dest_folder: trimSettings.dest_path,
                server: targetServer,
                keep_original: trimSettings.keep_original,
                delete_temp: deleteTemp
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            statusDiv.innerHTML = '<div class="alert alert-success"><i class="fas fa-check"></i> <span id="trimAnalysisStatusText">Successfully copied to: ' + data.destination_path + '</span></div>';
            
            // Show success notification
            showNotification(
                'Copy Complete',
                `Successfully copied to ${targetServer}: ${finalFilename}`,
                'success',
                5000
            );
            
            // Refresh the recordings list but keep modal open
            refreshRecordingsList();
        } else {
            statusDiv.innerHTML = '<div class="alert alert-error"><i class="fas fa-exclamation-triangle"></i> <span id="trimAnalysisStatusText">Failed to copy: ' + data.message + '</span></div>';
            
            // Show error notification
            showNotification(
                'Copy Failed',
                `Failed to copy to ${targetServer}: ${data.message}`,
                'error',
                5000
            );
        }
    } catch (error) {
        console.error('Error copying to destination:', error);
        const statusDiv = document.getElementById('trimAnalysisStatus');
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = '<div class="alert alert-error"><i class="fas fa-exclamation-triangle"></i> <span id="trimAnalysisStatusText">Error copying to destination</span></div>';
        
        // Show error notification
        showNotification(
            'Copy Error',
            `Error copying to ${targetServer}: ${error.message}`,
            'error',
            5000
        );
    }
};

// Delete trimmed file
window.deleteTrimmedFile = async function() {
    if (!selectedFile || !selectedFile.trimmedPath) return;
    
    if (!confirm('Are you sure you want to delete the trimmed file? This will allow you to trim again with different settings.')) {
        return;
    }
    
    try {
        // Show progress
        const statusDiv = document.getElementById('trimAnalysisStatus');
        statusDiv.style.display = 'block';
        statusDiv.className = 'alert alert-info';
        document.getElementById('trimAnalysisStatusText').textContent = 'Deleting trimmed file...';
        
        // For now, just reset the state since delete endpoint would need to be implemented
        // In a full implementation, you would call a delete API endpoint here
        selectedFile.trimmedPath = null;
        selectedFile.trimmedName = null;
        
        // Hide view trimmed button and disable buttons that require trimmed file
        document.getElementById('viewTrimmedGroup').style.display = 'none';
        document.getElementById('copyCastusBtn').disabled = true;
        document.getElementById('deleteTrimmedBtn').disabled = true;
        
        statusDiv.className = 'alert alert-success';
        document.getElementById('trimAnalysisStatusText').textContent = 'Trimmed file deleted - you can now trim again with different settings';
        
        // Clear the status after a delay
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 3000);
    } catch (error) {
        console.error('Error deleting trimmed file:', error);
        const statusDiv = document.getElementById('trimAnalysisStatus');
        statusDiv.style.display = 'block';
        statusDiv.className = 'alert alert-error';
        document.getElementById('trimAnalysisStatusText').textContent = 'Error deleting trimmed file';
    }
};

// Legacy function for backward compatibility - now opens enhanced modal
function analyzeAndTrim(recording) {
    openTrimAnalysisModal(recording);
}

window.closeTrimAnalysisModal = function() {
    document.getElementById('trimAnalysisModal').classList.remove('active');
    selectedFile = null;
    currentTrimFile = null;
}

// Video trim modal variables
let trimMode = 'start'; // 'start' or 'end'
let videoElement = null;

// Open video trim modal
function openVideoTrimModal(mode) {
    trimMode = mode;
    const modal = document.getElementById('videoTrimModal');
    videoElement = document.getElementById('trimVideo');
    
    // Set video source
    const filename = selectedFile.tempPath.split('/').pop();
    const videoUrl = window.APIConfig ? window.APIConfig.getURL(`/view-temp-file/${filename}`) : `http://127.0.0.1:5000/api/view-temp-file/${filename}`;
    videoElement.src = videoUrl;
    
    // Set initial time based on mode
    videoElement.addEventListener('loadedmetadata', function() {
        // Store video duration if not already set
        if (!selectedFile.duration || selectedFile.duration === 0) {
            selectedFile.duration = videoElement.duration;
            // Set default end trim to video duration if not already set
            if (!selectedFile.trimEnd || selectedFile.trimEnd === 0) {
                selectedFile.trimEnd = videoElement.duration;
                document.getElementById('trimAnalysisEndTime').value = videoElement.duration;
                document.getElementById('trimEndTimecode').value = secondsToTimecode(videoElement.duration);
            }
        }
        
        if (mode === 'start' && selectedFile.trimStart !== undefined) {
            videoElement.currentTime = selectedFile.trimStart;
        } else if (mode === 'end' && selectedFile.trimEnd !== undefined) {
            videoElement.currentTime = Math.max(0, selectedFile.trimEnd - 5);
        } else if (mode === 'end') {
            // For manual trimming, go near the end if no trim point set
            videoElement.currentTime = Math.max(0, videoElement.duration - 5);
        }
    });
    
    // Update button text
    document.getElementById('setTrimPointBtn').innerHTML = 
        mode === 'start' 
            ? '<i class="fas fa-cut"></i> Set as Start Point'
            : '<i class="fas fa-cut"></i> Set as End Point';
    
    // Update time display
    videoElement.addEventListener('timeupdate', updateVideoTimeDisplay);
    
    modal.classList.add('active');
}

// Close video trim modal
window.closeVideoTrimModal = function() {
    const modal = document.getElementById('videoTrimModal');
    if (videoElement) {
        videoElement.pause();
        videoElement.removeEventListener('timeupdate', updateVideoTimeDisplay);
        videoElement.src = '';
    }
    modal.classList.remove('active');
}

// Update video time display
function updateVideoTimeDisplay() {
    if (!videoElement) return;
    const currentTime = videoElement.currentTime;
    document.getElementById('currentTimeDisplay').textContent = secondsToTimecode(currentTime);
    document.getElementById('currentSecondsDisplay').textContent = `${currentTime.toFixed(1)}s`;
}

// Skip video by seconds
window.skipVideo = function(seconds) {
    if (!videoElement) return;
    videoElement.currentTime = Math.max(0, Math.min(videoElement.duration, videoElement.currentTime + seconds));
}

// Set trim point from video
window.setTrimPoint = function() {
    if (!videoElement || !selectedFile) return;
    
    const currentTime = videoElement.currentTime;
    
    if (trimMode === 'start') {
        selectedFile.trimStart = currentTime;
        document.getElementById('trimAnalysisStartTime').value = currentTime;
        document.getElementById('trimStartTimecode').value = secondsToTimecode(currentTime);
        showNotification(`Start trim point set to ${secondsToTimecode(currentTime)}`, 'success');
    } else {
        selectedFile.trimEnd = currentTime;
        document.getElementById('trimAnalysisEndTime').value = currentTime;
        document.getElementById('trimEndTimecode').value = secondsToTimecode(currentTime);
        showNotification(`End trim point set to ${secondsToTimecode(currentTime)}`, 'success');
    }
    
    // Update duration
    updateNewDuration();
    
    // Enable trim button if both points are set
    if (selectedFile.trimStart !== undefined && selectedFile.trimEnd !== undefined && 
        selectedFile.trimEnd > selectedFile.trimStart) {
        document.getElementById('executeTrimBtn').disabled = false;
    }
    
    // Close modal
    closeVideoTrimModal();
}

function updateNewDuration() {
    const startTime = parseFloat(document.getElementById('trimAnalysisStartTime').value) || 0;
    const endTime = parseFloat(document.getElementById('trimAnalysisEndTime').value) || 0;
    
    // Update timecode displays
    document.getElementById('trimStartTimecode').value = secondsToTimecode(startTime);
    document.getElementById('trimEndTimecode').value = secondsToTimecode(endTime);
    
    // Update selectedFile with manual values
    if (selectedFile) {
        selectedFile.trimStart = startTime;
        selectedFile.trimEnd = endTime;
    }
    
    if (endTime > startTime) {
        const newDuration = endTime - startTime;
        document.getElementById('trimAnalysisNewDuration').textContent = formatDuration(newDuration);
        
        // Enable trim button if we have valid trim points and file is downloaded
        if (selectedFile && selectedFile.tempPath) {
            document.getElementById('executeTrimBtn').disabled = false;
        }
    } else {
        document.getElementById('trimAnalysisNewDuration').textContent = 'Invalid trim points';
        document.getElementById('executeTrimBtn').disabled = true;
    }
}

async function executeTrim() {
    if (!selectedFile && !currentTrimFile) return;
    
    // Use selectedFile if available, otherwise fall back to currentTrimFile
    const file = selectedFile || currentTrimFile;
    
    const startTime = parseFloat(document.getElementById('trimAnalysisStartTime').value) || 0;
    const endTime = parseFloat(document.getElementById('trimAnalysisEndTime').value) || 0;
    
    if (endTime <= startTime) {
        showNotification('End time must be after start time', 'error');
        return;
    }
    
    // Generate filename if not provided
    const originalName = file.relative_path || file.filename || 'recording.mp4';
    const filename = originalName.split('/').pop();
    
    // Extract date from filename (format: YYYY-MM-DD at HHMMSS)
    const dateMatch = filename.match(/(\d{4})-(\d{2})-(\d{2})\s+at\s+\d{6}\s+(.+)\.mp4$/i);
    let dateStr, title;
    
    if (dateMatch) {
        // Extract date parts and title
        const year = dateMatch[1].substr(-2); // Last 2 digits of year
        const month = dateMatch[2];
        const day = dateMatch[3];
        dateStr = `${year}${month}${day}`;
        title = dateMatch[4].trim(); // The title after the timestamp
    } else {
        // Fallback to current date if pattern doesn't match
        const date = new Date();
        dateStr = `${date.getFullYear().toString().substr(-2)}${(date.getMonth() + 1).toString().padStart(2, '0')}${date.getDate().toString().padStart(2, '0')}`;
        title = filename.replace(/\.mp4$/i, '');
    }
    
    const newFilename = `${dateStr}_MTG_${title}.mp4`;
    
    // Update the filename field
    document.getElementById('trimAnalysisNewFilename').value = newFilename;
    
    // Show progress
    const statusDiv = document.getElementById('trimAnalysisStatus');
    statusDiv.style.display = 'block';
    statusDiv.className = 'alert alert-info';
    document.getElementById('trimAnalysisStatusText').textContent = 'Trimming file...';
    document.getElementById('executeTrimBtn').disabled = true;
    
    try {
        // Send trim request
        const response = await fetch(window.API ? `${window.APIConfig.baseURL}/trim-recording` : '/api/trim-recording', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: file.path,
                server: trimSettings.server,
                start_time: startTime,
                end_time: endTime,
                new_filename: newFilename
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Store trimmed file info
            if (selectedFile) {
                selectedFile.trimmedPath = data.output_path;
                selectedFile.trimmedName = newFilename;
            }
            
            // Show view trimmed button and enable final step buttons
            document.getElementById('viewTrimmedGroup').style.display = 'block';
            document.getElementById('copyCastusBtn').disabled = false;
            document.getElementById('deleteTrimmedBtn').disabled = false;
            
            statusDiv.innerHTML = '<div class="alert alert-success"><i class="fas fa-check"></i> <span id="trimAnalysisStatusText">File trimmed successfully! You can now view it or copy to destination.</span></div>';
            
        } else {
            statusDiv.innerHTML = '<div class="alert alert-error"><i class="fas fa-exclamation-triangle"></i> <span id="trimAnalysisStatusText">Failed to trim: ' + data.message + '</span></div>';
        }
    } catch (error) {
        console.error('Error trimming recording:', error);
        statusDiv.innerHTML = '<div class="alert alert-error"><i class="fas fa-exclamation-triangle"></i> <span id="trimAnalysisStatusText">Error trimming recording</span></div>';
    } finally {
        document.getElementById('executeTrimBtn').disabled = false;
    }
}

function toggleAutoTrim() {
    const button = document.getElementById('autoTrimToggle');
    
    if (autoTrimInterval) {
        // Stop auto-trim
        clearInterval(autoTrimInterval);
        autoTrimInterval = null;
        button.innerHTML = '<i class="fas fa-robot"></i> Auto-Trim: OFF';
        button.classList.remove('active');
        showNotification('Auto-trim disabled', 'info');
    } else {
        // Start auto-trim
        autoTrimInterval = setInterval(autoTrimCheck, 60000); // Check every minute
        button.innerHTML = '<i class="fas fa-robot"></i> Auto-Trim: ON';
        button.classList.add('active');
        showNotification('Auto-trim enabled', 'success');
        autoTrimCheck(); // Run immediately
    }
}

async function toggleRecordingsList() {
    const recordingsList = document.getElementById('recordingsList');
    const toggleBtn = event.target.closest('button');
    
    if (recordingsList.style.display === 'none') {
        recordingsList.style.display = 'block';
        toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide List';
        
        // Auto-refresh the list when showing it
        const currentContent = recordingsList.innerHTML;
        if (currentContent.includes('Click "Refresh List" to load recordings') || 
            currentContent.includes('No meeting recordings found')) {
            await refreshRecordingsList();
        }
    } else {
        recordingsList.style.display = 'none';
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show List';
    }
}

async function autoTrimCheck() {
    try {
        const result = await window.API.get('/');
        
        
        if (data.status === 'success') {
            // Find untrimmed recordings
            const untrimmed = data.recordings.filter(r => !r.is_trimmed);
            
            if (untrimmed.length > 0) {
                console.log(`Found ${untrimmed.length} untrimmed recordings`);
                
                // Trim the first untrimmed recording
                const recording = untrimmed[0];
                await trimRecording(recording.path, recording.filename);
            }
        }
    } catch (error) {
        console.error('Error in auto-trim check:', error);
    }
}

function formatDuration(seconds) {
    if (!seconds) return 'Unknown';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

function formatFileSize(bytes) {
    if (!bytes) return 'Unknown';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}

// Load trim settings on page load
document.addEventListener('DOMContentLoaded', () => {
    // Load saved trim settings
    const saved = localStorage.getItem('trimSettings');
    if (saved) {
        trimSettings = JSON.parse(saved);
        // Update all form fields
        document.getElementById('trimServer').value = trimSettings.server || 'target';
        document.getElementById('trimSourcePath').value = trimSettings.source_path || '/mnt/main/Recordings';
        document.getElementById('trimDestPath').value = trimSettings.dest_path || '/mnt/main/ATL26 On-Air Content/MEETINGS';
        document.getElementById('keepOriginal').checked = trimSettings.keep_original !== false; // Default true
    }
    
    // Initial load of recordings is commented out to prevent auto-refresh
    // refreshRecordingsList();
    
    // Add click handler for trim settings modal
    const trimModal = document.getElementById('trimSettingsModal');
    if (trimModal) {
        trimModal.addEventListener('click', (e) => {
            if (e.target === trimModal) {
                closeTrimSettingsModal();
            }
        });
    }
    
    // Add click handler for trim analysis modal
    const analysisModal = document.getElementById('trimAnalysisModal');
    if (analysisModal) {
        analysisModal.addEventListener('click', (e) => {
            if (e.target === analysisModal) {
                closeTrimAnalysisModal();
            }
        });
    }
    
    // Add event listeners for trim time inputs
    document.getElementById('trimAnalysisStartTime').addEventListener('input', updateNewDuration);
    document.getElementById('trimAnalysisEndTime').addEventListener('input', updateNewDuration);
});

// Meetings Schedule Functions
let meetings = [];
let editingMeetingId = null;

// Load meetings when panel is shown
window.addEventListener('panelChanged', (e) => {
    if (e.detail.panel === 'meetings') {
        loadMeetings();
    }
});

// Load meetings from backend
async function loadMeetings() {
    try {
        const response = await fetch('/api/meetings');
        const result = await response.json();
        
        if (result.status === 'success') {
            meetings = result.meetings || [];
            renderMeetingsTable();
        } else {
            showNotification('Error loading meetings: ' + (result.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error loading meetings:', error);
        showNotification('Error loading meetings', 'error');
    }
}

// Render meetings table
function renderMeetingsTable() {
    const tbody = document.getElementById('meetingsTableBody');
    const noMeetingsMsg = document.getElementById('noMeetingsMessage');
    
    if (meetings.length === 0) {
        tbody.innerHTML = '';
        noMeetingsMsg.style.display = 'block';
        return;
    }
    
    noMeetingsMsg.style.display = 'none';
    tbody.innerHTML = meetings.map(meeting => {
        const broadcastBadge = meeting.atl26_broadcast 
            ? '<span class="broadcast-badge">ATL26</span>'
            : '<span class="broadcast-badge no-broadcast">No</span>';
        
        return `
            <tr>
                <td>${meeting.meeting_name}</td>
                <td>${formatMeetingDate(meeting.meeting_date)}</td>
                <td>${meeting.start_time}</td>
                <td>${meeting.duration_hours} hours</td>
                <td><span class="meeting-schedule-room">${meeting.room || ''}</span></td>
                <td>${broadcastBadge}</td>
                <td>
                    <div class="meeting-actions">
                        <button class="button secondary small" onclick="editMeeting(${meeting.id})">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        <button class="button danger small" onclick="deleteMeeting(${meeting.id})">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// Format meeting date
function formatMeetingDate(dateStr) {
    // Parse date components to avoid timezone issues
    const [year, month, day] = dateStr.split('-').map(num => parseInt(num));
    // Create date using local timezone (month is 0-indexed in JS)
    const date = new Date(year, month - 1, day);
    return date.toLocaleDateString('en-US', { 
        weekday: 'long', 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    });
}

// Open add meeting modal
window.openAddMeetingModal = function() {
    editingMeetingId = null;
    document.getElementById('meetingModalTitle').textContent = 'Add Meeting';
    document.getElementById('meetingForm').reset();
    document.getElementById('meetingBroadcast').checked = true;
    document.getElementById('meetingRoom').value = '';
    document.getElementById('meetingModal').classList.add('active');
};

// Open edit meeting modal
window.editMeeting = function(meetingId) {
    const meeting = meetings.find(m => m.id === meetingId);
    if (!meeting) return;
    
    editingMeetingId = meetingId;
    document.getElementById('meetingModalTitle').textContent = 'Edit Meeting';
    document.getElementById('meetingId').value = meetingId;
    document.getElementById('meetingName').value = meeting.meeting_name;
    document.getElementById('meetingDate').value = meeting.meeting_date;
    
    // Convert 12-hour format to 24-hour format for time input
    let timeValue = meeting.start_time || '';
    if (timeValue) {
        timeValue = timeValue.trim();
        const timeMatch = timeValue.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
        if (timeMatch) {
            let hours = parseInt(timeMatch[1]);
            const minutes = timeMatch[2];
            const meridiem = timeMatch[3].toUpperCase();
            
            if (meridiem === 'PM' && hours !== 12) {
                hours += 12;
            } else if (meridiem === 'AM' && hours === 12) {
                hours = 0;
            }
            
            timeValue = `${hours.toString().padStart(2, '0')}:${minutes}`;
        }
    }
    document.getElementById('meetingTime').value = timeValue;
    
    document.getElementById('meetingDuration').value = meeting.duration_hours;
    document.getElementById('meetingRoom').value = meeting.room || '';
    document.getElementById('meetingBroadcast').checked = meeting.atl26_broadcast;
    document.getElementById('meetingModal').classList.add('active');
};

// Close meeting modal
window.closeMeetingModal = function() {
    document.getElementById('meetingModal').classList.remove('active');
    editingMeetingId = null;
};

// Save meeting
window.saveMeeting = async function() {
    // Convert 24-hour time to 12-hour format with AM/PM
    let timeValue = document.getElementById('meetingTime').value;
    if (timeValue) {
        const [hours24, minutes] = timeValue.split(':');
        let hours = parseInt(hours24);
        let meridiem = 'AM';
        
        if (hours >= 12) {
            meridiem = 'PM';
            if (hours > 12) {
                hours -= 12;
            }
        } else if (hours === 0) {
            hours = 12;
        }
        
        timeValue = `${hours}:${minutes} ${meridiem}`;
    }
    
    const formData = {
        meeting_name: document.getElementById('meetingName').value,
        meeting_date: document.getElementById('meetingDate').value,
        start_time: timeValue,
        duration_hours: parseFloat(document.getElementById('meetingDuration').value),
        room: document.getElementById('meetingRoom').value || null,
        atl26_broadcast: document.getElementById('meetingBroadcast').checked
    };
    
    if (!formData.meeting_name || !formData.meeting_date || !formData.start_time) {
        showNotification('Please fill in all required fields', 'error');
        return;
    }
    
    try {
        const url = editingMeetingId 
            ? `/api/meetings/${editingMeetingId}`
            : '/api/meetings';
        
        const method = editingMeetingId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showNotification(editingMeetingId ? 'Meeting updated' : 'Meeting created', 'success');
            closeMeetingModal();
            loadMeetings();
        } else {
            showNotification(data.message || 'Error saving meeting', 'error');
        }
    } catch (error) {
        console.error('Error saving meeting:', error);
        showNotification('Error saving meeting', 'error');
    }
};

// Delete meeting
window.deleteMeeting = async function(meetingId) {
    if (!confirm('Are you sure you want to delete this meeting?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/meetings/${meetingId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showNotification('Meeting deleted', 'success');
            loadMeetings();
        } else {
            showNotification(data.message || 'Error deleting meeting', 'error');
        }
    } catch (error) {
        console.error('Error deleting meeting:', error);
        showNotification('Error deleting meeting', 'error');
    }
};

// Import meetings from web
window.importMeetingsFromWeb = async function() {
    const importBtn = event.target;
    const importStatus = document.getElementById('importStatus');
    
    importBtn.disabled = true;
    importBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Importing...';
    importStatus.textContent = 'Fetching meetings from Atlanta City Council website...';
    
    try {
        const response = await fetch('/api/meetings/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                year: 2025,
                months: [8, 9, 10, 11, 12]
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showNotification(data.message, 'success');
            importStatus.textContent = `Imported ${data.imported} of ${data.total} meetings`;
            loadMeetings();
        } else {
            showNotification(data.message || 'Error importing meetings', 'error');
            importStatus.textContent = 'Import failed';
        }
    } catch (error) {
        console.error('Error importing meetings:', error);
        showNotification('Error importing meetings', 'error');
        importStatus.textContent = 'Import failed';
    } finally {
        importBtn.disabled = false;
        importBtn.innerHTML = '<i class="fas fa-download"></i> Import from City Council Website';
        
        // Clear status after 5 seconds
        setTimeout(() => {
            importStatus.textContent = '';
        }, 5000);
    }
};

// Import Meetings to Schedule Templates Functions
// Room to SDI mapping
const ROOM_TO_SDI_MAPPING = {
    'Council Chambers': '/mnt/main/tv/inputs/1-SDI in',
    'Committee Room 1': '/mnt/main/tv/inputs/2-SDI in',
    'Committee Room 2': '/mnt/main/tv/inputs/3-SDI in'
};

// Import Daily Meetings Modal Functions
window.importDailyMeetings = function() {
    console.log('Opening import daily meetings modal');
    const modal = document.getElementById('importDailyMeetingsModal');
    if (modal) {
        modal.style.display = 'block';
        // Set today's date as default
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('dailyMeetingDate').value = today;
        // Attach event handler
        attachDailyHandlers();
        loadDailyMeetings();
    }
};

window.closeImportDailyMeetingsModal = function() {
    document.getElementById('importDailyMeetingsModal').style.display = 'none';
};

async function loadDailyMeetings() {
    const date = document.getElementById('dailyMeetingDate').value;
    if (!date) return;
    
    console.log('Loading meetings for date:', date);
    
    try {
        const response = await fetch(`/api/meetings/by-date?date=${date}`);
        const data = await response.json();
        
        console.log('Response data:', data);
        
        const container = document.getElementById('dailyMeetingsList');
        if (data.status === 'success' && data.meetings.length > 0) {
            container.innerHTML = data.meetings.map(meeting => `
                <div class="meeting-selection-item">
                    <label>
                        <input type="checkbox" name="dailyMeeting" value="${meeting.id}" checked>
                        ${meeting.start_time} - ${meeting.meeting_name}${meeting.room ? ` (${meeting.room})` : ''}
                    </label>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p>No meetings found for this date.</p>';
        }
    } catch (error) {
        console.error('Error loading daily meetings:', error);
        document.getElementById('dailyMeetingsList').innerHTML = '<p>Error loading meetings.</p>';
    }
}

window.generateDailySchedule = async function() {
    const selectedMeetings = Array.from(document.querySelectorAll('input[name="dailyMeeting"]:checked'))
        .map(cb => cb.value);
    
    if (selectedMeetings.length === 0) {
        showNotification('Please select at least one meeting', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/generate-daily-schedule-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ meeting_ids: selectedMeetings })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Close import modal
            closeImportDailyMeetingsModal();
            
            // Process the template content to extract items
            const templateItems = parseScheduleTemplate(data.template);
            
            // Get the selected date from the input
            const selectedDate = document.getElementById('dailyMeetingDate').value;
            
            // Create a template object similar to what loadSelectedTemplate creates
            currentTemplate = {
                type: 'daily',
                filename: `daily_meetings_${selectedDate}.sch`,
                items: templateItems,
                raw_content: data.template
            };
            
            // Display the template in the current panel
            const activePanel = document.querySelector('.panel:not([style*="display: none"])');
            if (activePanel && activePanel.id === 'dashboard') {
                displayDashboardTemplate();
            } else {
                displayTemplate();
            }
            
            // Dispatch event for scheduling module to display the imported meetings
            window.dispatchEvent(new CustomEvent('templateLoaded', {
                detail: { template: currentTemplate }
            }));
            
            // Save to template library
            savedTemplates.push(JSON.parse(JSON.stringify(currentTemplate)));
            localStorage.setItem('savedTemplates', JSON.stringify(savedTemplates));
            
            log(`✅ Imported daily meetings schedule with ${templateItems.length} items`, 'success');
            showNotification(`Schedule imported successfully with ${templateItems.length} meetings`, 'success');
        } else {
            showNotification(data.message || 'Error generating schedule', 'error');
        }
    } catch (error) {
        console.error('Error generating daily schedule:', error);
        showNotification('Error generating schedule', 'error');
    }
};

// Import Weekly Meetings Modal Functions
window.importWeeklyMeetings = function() {
    console.log('Opening import weekly meetings modal');
    const modal = document.getElementById('importWeeklyMeetingsModal');
    if (modal) {
        modal.style.display = 'block';
        // Set current year and week as default
        const today = new Date();
        const currentYear = today.getFullYear();
        const currentWeek = getWeekNumber(today);
        document.getElementById('weeklyMeetingYear').value = currentYear;
        document.getElementById('weeklyMeetingWeek').value = currentWeek;
        
        // Show the date range immediately
        updateWeekDateRange(currentYear, currentWeek);
        
        // Attach event handlers
        attachWeeklyHandlers();
        
        loadWeeklyMeetings();
    }
};

window.closeImportWeeklyMeetingsModal = function() {
    document.getElementById('importWeeklyMeetingsModal').style.display = 'none';
};

function getWeekNumber(date) {
    // Calculate week number with Sunday as the first day of the week
    const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const jan1 = new Date(d.getFullYear(), 0, 1);
    const dayOfWeek = jan1.getDay(); // 0 = Sunday
    const daysToFirstSunday = dayOfWeek === 0 ? 0 : 7 - dayOfWeek;
    const firstSunday = new Date(d.getFullYear(), 0, 1 + daysToFirstSunday);
    
    // Calculate days since first Sunday
    const daysSinceFirstSunday = Math.floor((d - firstSunday) / 86400000);
    
    // If the date is before the first Sunday, it's week 1
    if (daysSinceFirstSunday < 0) {
        return 1;
    }
    
    // Calculate week number (add 1 because weeks are 1-indexed)
    return Math.floor(daysSinceFirstSunday / 7) + 1;
}

// Update the week date range display
function updateWeekDateRange(year, weekNumber) {
    const dateRangeEl = document.getElementById('weekDateRange');
    if (!dateRangeEl) return;
    
    // Calculate the first Sunday of the year
    const jan1 = new Date(year, 0, 1);
    const dayOfWeek = jan1.getDay(); // 0 = Sunday, 1 = Monday, etc.
    const daysToFirstSunday = dayOfWeek === 0 ? 0 : 7 - dayOfWeek;
    const firstSunday = new Date(year, 0, 1 + daysToFirstSunday);
    
    // Calculate the start of the requested week (Sunday)
    const weekStart = new Date(firstSunday);
    weekStart.setDate(firstSunday.getDate() + (weekNumber - 1) * 7);
    
    // Calculate the end of the week (Saturday, 6 days later)
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate() + 6);
    
    // Format the dates
    const options = { month: 'short', day: 'numeric', year: 'numeric' };
    const startStr = weekStart.toLocaleDateString('en-US', options);
    const endStr = weekEnd.toLocaleDateString('en-US', options);
    
    // Update the display
    dateRangeEl.textContent = `Week ${weekNumber}: ${startStr} - ${endStr}`;
}

async function loadWeeklyMeetings() {
    const year = document.getElementById('weeklyMeetingYear').value;
    const week = document.getElementById('weeklyMeetingWeek').value;
    
    if (!year || !week) return;
    
    // Calculate and display the date range for this week
    updateWeekDateRange(year, week);
    
    try {
        const data = await window.API.get(`/meetings/by-week?year=${year}&week=${week}`);
        
        console.log(`Loading meetings for week ${week} of ${year}:`, data);
        
        const container = document.getElementById('weeklyMeetingsList');
        if (data.status === 'success' && data.meetings.length > 0) {
            // Group meetings by day
            const meetingsByDay = {};
            const dayOrder = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
            
            data.meetings.forEach(meeting => {
                // Parse date string explicitly to avoid timezone issues
                // meeting_date is in YYYY-MM-DD format
                const [yearStr, monthStr, dayStr] = meeting.meeting_date.split('-');
                const date = new Date(parseInt(yearStr), parseInt(monthStr) - 1, parseInt(dayStr));
                const dayName = date.toLocaleDateString('en-US', { weekday: 'long' });
                if (!meetingsByDay[dayName]) meetingsByDay[dayName] = [];
                meetingsByDay[dayName].push(meeting);
            });
            
            // Sort days in proper order
            const sortedDays = Object.entries(meetingsByDay).sort(([a], [b]) => {
                return dayOrder.indexOf(a) - dayOrder.indexOf(b);
            });
            
            container.innerHTML = sortedDays.map(([day, meetings]) => `
                <div class="day-group" style="margin-bottom: 1rem;">
                    <h4 style="color: var(--primary-color); margin-bottom: 0.5rem;">${day}</h4>
                    ${meetings.map(meeting => `
                        <div class="meeting-selection-item" style="margin-left: 1rem; margin-bottom: 0.25rem;">
                            <label style="cursor: pointer; display: flex; align-items: center;">
                                <input type="checkbox" name="weeklyMeeting" value="${meeting.id}" checked style="margin-right: 0.5rem;">
                                ${meeting.start_time} - ${meeting.meeting_name}${meeting.room ? ` (${meeting.room})` : ''}
                            </label>
                        </div>
                    `).join('')}
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p style="color: #666; padding: 1rem;">No meetings found for this week.</p>';
        }
    } catch (error) {
        console.error('Error loading weekly meetings:', error);
        document.getElementById('weeklyMeetingsList').innerHTML = '<p>Error loading meetings.</p>';
    }
}

window.generateWeeklySchedule = async function() {
    const selectedMeetings = Array.from(document.querySelectorAll('input[name="weeklyMeeting"]:checked'))
        .map(cb => cb.value);
    
    if (selectedMeetings.length === 0) {
        showNotification('Please select at least one meeting', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/generate-weekly-schedule-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ meeting_ids: selectedMeetings })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            closeImportWeeklyMeetingsModal();
            
            // Process the template content to extract items
            const templateItems = parseScheduleTemplate(data.template);
            
            // Create a template object
            currentTemplate = {
                type: 'weekly',
                filename: `weekly_meetings_${new Date().toISOString().split('T')[0]}.sch`,
                items: templateItems,
                raw_content: data.template
            };
            
            // Display the template
            const activePanel = document.querySelector('.panel:not([style*="display: none"])');
            if (activePanel && activePanel.id === 'dashboard') {
                displayDashboardTemplate();
            } else {
                displayTemplate();
            }
            
            // Dispatch event for scheduling module to display the imported meetings
            window.dispatchEvent(new CustomEvent('templateLoaded', {
                detail: { template: currentTemplate }
            }));
            
            // Save to template library
            savedTemplates.push(JSON.parse(JSON.stringify(currentTemplate)));
            localStorage.setItem('savedTemplates', JSON.stringify(savedTemplates));
            
            log(`✅ Imported weekly meetings schedule with ${templateItems.length} items`, 'success');
            showNotification(`Schedule imported successfully with ${templateItems.length} meetings`, 'success');
        } else {
            showNotification(data.message || 'Error generating schedule', 'error');
        }
    } catch (error) {
        console.error('Error generating weekly schedule:', error);
        showNotification('Error generating schedule', 'error');
    }
};

// Import Monthly Meetings Modal Functions
window.importMonthlyMeetings = function() {
    console.log('Opening import monthly meetings modal');
    const modal = document.getElementById('importMonthlyMeetingsModal');
    if (modal) {
        modal.style.display = 'block';
        // Set current year and month as default
        const today = new Date();
        document.getElementById('monthlyMeetingYear').value = today.getFullYear();
        document.getElementById('monthlyMeetingMonth').value = today.getMonth() + 1;
        loadMonthlyMeetings();
    }
};

window.closeImportMonthlyMeetingsModal = function() {
    document.getElementById('importMonthlyMeetingsModal').style.display = 'none';
};

async function loadMonthlyMeetings() {
    const year = document.getElementById('monthlyMeetingYear').value;
    const month = document.getElementById('monthlyMeetingMonth').value;
    
    if (!year || !month) return;
    
    try {
        const response = await fetch(`/api/meetings/by-month?year=${year}&month=${month}`);
        const data = await response.json();
        
        const container = document.getElementById('monthlyMeetingsList');
        if (data.status === 'success' && data.meetings.length > 0) {
            container.innerHTML = data.meetings.map(meeting => {
                // Parse date components directly to avoid timezone issues
                const [year, month, day] = meeting.meeting_date.split('-').map(num => parseInt(num));
                const dayOfMonth = day;
                return `
                    <div class="meeting-selection-item">
                        <label>
                            <input type="checkbox" name="monthlyMeeting" value="${meeting.id}" checked>
                            Day ${dayOfMonth} - ${meeting.start_time} - ${meeting.meeting_name}${meeting.room ? ` (${meeting.room})` : ''}
                        </label>
                    </div>
                `;
            }).join('');
        } else {
            container.innerHTML = '<p>No meetings found for this month.</p>';
        }
    } catch (error) {
        console.error('Error loading monthly meetings:', error);
        document.getElementById('monthlyMeetingsList').innerHTML = '<p>Error loading meetings.</p>';
    }
}

window.generateMonthlySchedule = async function() {
    const selectedMeetings = Array.from(document.querySelectorAll('input[name="monthlyMeeting"]:checked'))
        .map(cb => cb.value);
    
    if (selectedMeetings.length === 0) {
        showNotification('Please select at least one meeting', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/generate-monthly-schedule-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ meeting_ids: selectedMeetings })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            closeImportMonthlyMeetingsModal();
            
            // Process the template content to extract items
            const templateItems = parseScheduleTemplate(data.template);
            
            // Create a template object
            currentTemplate = {
                type: 'monthly',
                filename: `monthly_meetings_${new Date().toISOString().split('T')[0]}.sch`,
                items: templateItems,
                raw_content: data.template
            };
            
            // Display the template
            const activePanel = document.querySelector('.panel:not([style*="display: none"])');
            if (activePanel && activePanel.id === 'dashboard') {
                displayDashboardTemplate();
            } else {
                displayTemplate();
            }
            
            // Dispatch event for scheduling module to display the imported meetings
            window.dispatchEvent(new CustomEvent('templateLoaded', {
                detail: { template: currentTemplate }
            }));
            
            // Save to template library
            savedTemplates.push(JSON.parse(JSON.stringify(currentTemplate)));
            localStorage.setItem('savedTemplates', JSON.stringify(savedTemplates));
            
            log(`✅ Imported monthly meetings schedule with ${templateItems.length} items`, 'success');
            showNotification(`Schedule imported successfully with ${templateItems.length} meetings`, 'success');
        } else {
            showNotification(data.message || 'Error generating schedule', 'error');
        }
    } catch (error) {
        console.error('Error generating monthly schedule:', error);
        showNotification('Error generating schedule', 'error');
    }
};

// Helper function to parse schedule template content into items
function parseScheduleTemplate(templateContent) {
    const items = [];
    const lines = templateContent.split('\n');
    let currentItem = null;
    
    for (const line of lines) {
        const trimmedLine = line.trim();
        
        if (trimmedLine.startsWith('item=')) {
            if (currentItem) {
                items.push(currentItem);
            }
            const filePath = trimmedLine.substring(5);
            let title = 'Live Input';
            
            // Identify SDI input sources and set appropriate titles
            if (filePath.includes('/mnt/main/tv/inputs/1-SDI')) {
                title = 'Live Input - Council Chambers';
            } else if (filePath.includes('/mnt/main/tv/inputs/2-SDI')) {
                title = 'Live Input - Committee Room 1';
            } else if (filePath.includes('/mnt/main/tv/inputs/3-SDI')) {
                title = 'Live Input - Committee Room 2';
            }
            
            currentItem = {
                file_path: filePath,
                title: title,
                duration_seconds: 0,
                is_fixed_time: true,  // Mark as fixed-time event that cannot be moved
                is_live_input: true   // Additional flag to identify live inputs
            };
        } else if (currentItem && trimmedLine.startsWith('start=')) {
            currentItem.start_time = trimmedLine.substring(6);
        } else if (currentItem && trimmedLine.startsWith('end=')) {
            currentItem.end_time = trimmedLine.substring(4);
            // Calculate duration from start and end times
            const start = parseTimeString(currentItem.start_time);
            const end = parseTimeString(currentItem.end_time);
            if (start && end) {
                currentItem.duration_seconds = (end - start);
            }
        } else if (trimmedLine === '}' && currentItem) {
            items.push(currentItem);
            currentItem = null;
        }
    }
    
    return items;
}

// Helper function to parse time string to seconds
function parseTimeString(timeStr) {
    if (!timeStr) return null;
    
    // Handle weekly format (e.g., "mon 10:00 am")
    if (timeStr.includes(' ')) {
        const parts = timeStr.split(' ');
        if (parts.length >= 3) {
            // Extract just the time part
            timeStr = parts.slice(1).join(' ');
        }
    }
    
    // Handle different time formats
    const match = timeStr.match(/(\d{1,2}):(\d{2})\s*(am|pm)/i);
    if (match) {
        let hours = parseInt(match[1]);
        const minutes = parseInt(match[2]);
        const isPM = match[3].toLowerCase() === 'pm';
        
        if (isPM && hours !== 12) hours += 12;
        if (!isPM && hours === 12) hours = 0;
        
        return hours * 3600 + minutes * 60;
    }
    
    return null;
}

// Helper function to download template
window.downloadTemplate = function(filename, content) {
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
};

// Helper function to copy template to clipboard
window.copyTemplateToClipboard = function(content) {
    navigator.clipboard.writeText(content).then(() => {
        showNotification('Template copied to clipboard', 'success');
    }).catch(err => {
        console.error('Error copying to clipboard:', err);
        showNotification('Error copying to clipboard', 'error');
    });
};

// Update date/week/month change handlers - attach them when modals are opened
window.attachDailyHandlers = function() {
    document.getElementById('dailyMeetingDate')?.addEventListener('change', loadDailyMeetings);
};

window.attachWeeklyHandlers = function() {
    document.getElementById('weeklyMeetingYear')?.addEventListener('change', loadWeeklyMeetings);
    document.getElementById('weeklyMeetingWeek')?.addEventListener('change', loadWeeklyMeetings);
};

window.attachMonthlyHandlers = function() {
    document.getElementById('monthlyMeetingYear')?.addEventListener('change', loadMonthlyMeetings);
    document.getElementById('monthlyMeetingMonth')?.addEventListener('change', loadMonthlyMeetings);
};

// Fill Graphics Functions
// These variables are still needed by the old load functions
let selectedRegion1Files = [];
let selectedRegion2File = null;
let selectedRegion3Files = [];

async function loadRegion1Graphics() {
    // Redirect to the new fill_graphics module function
    if (window.fillGraphicsLoadRegion1Graphics) {
        return window.fillGraphicsLoadRegion1Graphics();
    }
    
    // Fallback to old implementation if module not loaded
    const server = document.getElementById('region1Server').value;
    const path = document.getElementById('region1Path').value;
    const listDiv = document.getElementById('region1GraphicsList');
    
    if (!server) {
        listDiv.innerHTML = '<p class="info-text">Select a server to load graphics</p>';
        return;
    }
    
    if (!path) {
        listDiv.innerHTML = '<p class="info-text">Enter a folder path</p>';
        return;
    }
    
    listDiv.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Loading graphics...</p>';
    
    try {
        const response = await fetch('/api/list-graphics-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_type: server,
                path: path,
                extensions: ['.jpg', '.png']
            })
        });
        
        
        
        if (result.success) {
            if (result.files.length === 0) {
                listDiv.innerHTML = '<p class="info-text">No graphics files found</p>';
                return;
            }
            
            let html = '';
            result.files.forEach(file => {
                const isChecked = selectedRegion1Files.includes(file.path) ? 'checked' : '';
                html += `
                    <div class="graphics-item">
                        <input type="checkbox" id="r1_${btoa(file.path)}" value="${file.path}" ${isChecked} onchange="updateRegion1Selection(this)">
                        <label for="r1_${btoa(file.path)}">${file.name}</label>
                    </div>
                `;
            });
            
            listDiv.innerHTML = html;
            
            // Show/hide select all buttons
            document.getElementById('selectAllRegion1Btn').style.display = 'inline-block';
            document.getElementById('deselectAllRegion1Btn').style.display = 'inline-block';
        } else {
            listDiv.innerHTML = `<p class="error-text">Error: ${result.message}</p>`;
            // Hide buttons on error
            document.getElementById('selectAllRegion1Btn').style.display = 'none';
            document.getElementById('deselectAllRegion1Btn').style.display = 'none';
        }
    } catch (error) {
        listDiv.innerHTML = `<p class="error-text">Error loading graphics: ${error.message}</p>`;
        // Hide buttons on error
        document.getElementById('selectAllRegion1Btn').style.display = 'none';
        document.getElementById('deselectAllRegion1Btn').style.display = 'none';
    }
}

async function loadRegion2Graphics() {
    // Redirect to the new fill_graphics module function
    if (window.fillGraphicsLoadRegion2Graphics) {
        return window.fillGraphicsLoadRegion2Graphics();
    }
    
    // Fallback to old implementation if module not loaded
    const server = document.getElementById('region2Server').value;
    const path = document.getElementById('region2Path').value;
    const listDiv = document.getElementById('region2GraphicsList');
    
    if (!server) {
        listDiv.innerHTML = '<p class="info-text">Select a server to load graphics</p>';
        return;
    }
    
    if (!path) {
        listDiv.innerHTML = '<p class="info-text">Enter a folder path</p>';
        return;
    }
    
    listDiv.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Loading graphics...</p>';
    
    try {
        const response = await fetch('/api/list-graphics-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_type: server,
                path: path,
                extensions: ['.jpg', '.png']
            })
        });
        
        
        
        if (result.success) {
            if (result.files.length === 0) {
                listDiv.innerHTML = '<p class="info-text">No graphics files found</p>';
                return;
            }
            
            let html = '';
            result.files.forEach(file => {
                const isChecked = selectedRegion2File === file.path ? 'checked' : '';
                html += `
                    <div class="graphics-item">
                        <input type="radio" name="region2" id="r2_${btoa(file.path)}" value="${file.path}" ${isChecked} onchange="updateRegion2Selection(this)">
                        <label for="r2_${btoa(file.path)}">${file.name}</label>
                    </div>
                `;
            });
            
            listDiv.innerHTML = html;
        } else {
            listDiv.innerHTML = `<p class="error-text">Error: ${result.message}</p>`;
        }
    } catch (error) {
        listDiv.innerHTML = `<p class="error-text">Error loading graphics: ${error.message}</p>`;
    }
}

async function loadMusicFiles() {
    // Redirect to the new fill_graphics module function
    if (window.fillGraphicsLoadMusicFiles) {
        return window.fillGraphicsLoadMusicFiles();
    }
    
    // Fallback to old implementation if module not loaded
    const server = document.getElementById('region3Server').value;
    const path = document.getElementById('region3Path').value;
    const listDiv = document.getElementById('musicFilesList');
    
    if (!server) {
        listDiv.innerHTML = '<p class="info-text">Select a server to load music files</p>';
        return;
    }
    
    if (!path) {
        listDiv.innerHTML = '<p class="info-text">Enter a folder path</p>';
        return;
    }
    
    listDiv.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Loading music files...</p>';
    
    try {
        const response = await fetch('/api/list-graphics-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server_type: server,
                path: path,
                extensions: ['.mp4', '.wav']
            })
        });
        
        
        
        if (result.success) {
            if (result.files.length === 0) {
                listDiv.innerHTML = '<p class="info-text">No music files found</p>';
                return;
            }
            
            let html = '';
            result.files.forEach(file => {
                const isChecked = selectedRegion3Files.includes(file.path) ? 'checked' : '';
                html += `
                    <div class="music-item">
                        <input type="checkbox" id="r3_${btoa(file.path)}" value="${file.path}" ${isChecked} onchange="updateRegion3Selection(this)">
                        <label for="r3_${btoa(file.path)}">${file.name}</label>
                    </div>
                `;
            });
            
            listDiv.innerHTML = html;
        } else {
            listDiv.innerHTML = `<p class="error-text">Error: ${result.message}</p>`;
        }
    } catch (error) {
        listDiv.innerHTML = `<p class="error-text">Error loading music files: ${error.message}</p>`;
    }
}

function updateRegion1Selection(checkbox) {
    if (checkbox.checked) {
        if (!selectedRegion1Files.includes(checkbox.value)) {
            selectedRegion1Files.push(checkbox.value);
        }
    } else {
        selectedRegion1Files = selectedRegion1Files.filter(file => file !== checkbox.value);
    }
    updateGenerateButton();
}

function updateRegion2Selection(radio) {
    selectedRegion2File = radio.value;
    updateGenerateButton();
}

function updateRegion3Selection(checkbox) {
    if (checkbox.checked) {
        if (!selectedRegion3Files.includes(checkbox.value)) {
            selectedRegion3Files.push(checkbox.value);
        }
    } else {
        selectedRegion3Files = selectedRegion3Files.filter(file => file !== checkbox.value);
    }
    updateGenerateButton();
}

// DEPRECATED: This function is replaced by fillGraphicsUpdateGenerateButton in fill_graphics.js
/*
function updateGenerateButton() {
    const button = document.getElementById('generateProjectBtn');
    if (selectedRegion1Files.length > 0 && selectedRegion2File && selectedRegion3Files.length > 0) {
        button.disabled = false;
    } else {
        button.disabled = true;
    }
}
*/

// DEPRECATED: These functions are replaced by the fill_graphics module
/*
function showGenerateProjectModal() {
    const modal = document.getElementById('generateProjectModal');
    modal.style.display = 'block';
    
    // Update summary
    const summaryDiv = document.getElementById('projectSummary');
    let html = '<div class="project-summary-item"><strong>Region 1 (Upper):</strong> ' + selectedRegion1Files.length + ' graphics selected</div>';
    html += '<div class="project-summary-item"><strong>Region 2 (Lower):</strong> ' + (selectedRegion2File ? selectedRegion2File.split('/').pop() : 'None') + '</div>';
    html += '<div class="project-summary-item"><strong>Region 3 (Music):</strong> ' + selectedRegion3Files.length + ' music files selected</div>';
    
    summaryDiv.innerHTML = html;
}

function closeGenerateProjectModal() {
    document.getElementById('generateProjectModal').style.display = 'none';
}
*/

// DEPRECATED: This function has been replaced by fillGraphicsGenerateProjectFile in fill_graphics.js
// Commenting out to avoid conflicts with the new implementation that includes slide_duration
/*
async function generateProjectFile() {
    const projectName = document.getElementById('projectFileName').value.trim();
    const exportPath = document.getElementById('projectExportPath').value.trim();
    const exportServer = document.getElementById('projectExportServer').value;
    
    if (!projectName) {
        alert('Please enter a project file name');
        return;
    }
    
    try {
        const response = await fetch('/api/generate-prj-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                export_path: exportPath,
                export_server: exportServer,
                region1_files: selectedRegion1Files,
                region2_file: selectedRegion2File,
                region3_files: selectedRegion3Files
            })
        });
        
        
        
        if (result.success) {
            showNotification('Success', result.message, 'success');
            closeGenerateProjectModal();
            
            // Clear selections
            selectedRegion1Files = [];
            selectedRegion2File = null;
            selectedRegion3Files = [];
            
            // Reload lists to clear checkboxes
            if (document.getElementById('region1Server').value) loadRegion1Graphics();
            if (document.getElementById('region2Server').value) loadRegion2Graphics();
            if (document.getElementById('region3Server').value) loadMusicFiles();
            
            updateGenerateButton();
        } else {
            showNotification('Error', result.message, 'error');
        }
    } catch (error) {
        showNotification('Error', 'Failed to generate project file: ' + error.message, 'error');
    }
}
*/

// Select/Deselect all functions for Region 1
// DEPRECATED: These functions are now handled by the fill_graphics module
// The new functions properly manage the state and UI updates
/*
function selectAllRegion1Graphics() {
    const checkboxes = document.querySelectorAll('#region1GraphicsList input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.checked = true;
        updateRegion1Selection(checkbox);
    });
}

function deselectAllRegion1Graphics() {
    const checkboxes = document.querySelectorAll('#region1GraphicsList input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.checked = false;
        updateRegion1Selection(checkbox);
    });
}
*/

// Function to update scanned file counts after sync
function updateScannedFileCounts() {
    const sourceFileCount = document.getElementById('sourceFileCount');
    const targetFileCount = document.getElementById('targetFileCount');
    
    if (sourceFileCount) {
        sourceFileCount.textContent = `${sourceFiles.length} files found`;
        sourceFileCount.className = sourceFiles.length > 0 ? 'file-count has-files' : 'file-count';
    }
    
    if (targetFileCount) {
        targetFileCount.textContent = `${targetFiles.length} files found`;
        targetFileCount.className = targetFiles.length > 0 ? 'file-count has-files' : 'file-count';
    }
}

// Function to update server file counts based on synced files
function updateServerFileCounts() {
    console.log('Updating server file counts after sync');
    
    // Count how many files were synced to target
    const syncedToTargetCount = allComparisonResults.filter(r => r.justSynced).length;
    
    if (syncedToTargetCount > 0) {
        // Get synced files info from allComparisonResults
        const syncedFiles = allComparisonResults.filter(r => r.justSynced);
        
        // Add synced files to targetFiles array
        syncedFiles.forEach(syncedFile => {
            const fileToAdd = {
                name: syncedFile.sourceFile?.name || syncedFile.relativePath,
                size: syncedFile.sourceFile?.size || 0,
                path: syncedFile.sourceFile?.path || syncedFile.relativePath,
                relativePath: syncedFile.relativePath,
                type: syncedFile.sourceFile?.type || 'file'
            };
            
            // Check if file doesn't already exist in targetFiles
            const exists = targetFiles.some(f => f.name === fileToAdd.name);
            if (!exists) {
                targetFiles.push(fileToAdd);
                console.log(`Added ${fileToAdd.name} to targetFiles`);
            }
        });
        
        console.log(`Updated targetFiles count: ${targetFiles.length}`);
        
        // Update the file count displays
        updateScannedFileCounts();
        
        // Update the displayed file lists
        displayScannedFiles();
    }
}

// Function to update file item UI after successful sync
function updateFileItemUI(fileId, fileName, status) {
    // Find all file items that might match this file
    const fileItems = document.querySelectorAll('.file-item');
    console.log(`updateFileItemUI: Found ${fileItems.length} file items to check`);
    
    let foundMatch = false;
    
    fileItems.forEach(item => {
        // Check if this item matches by looking for the fileId in onclick handlers or data attributes
        const buttons = item.querySelectorAll('button');
        let isMatch = false;
        
        buttons.forEach(button => {
            const onclick = button.getAttribute('onclick');
            if (onclick && onclick.includes(fileId)) {
                console.log('Found match by button onclick:', onclick);
                isMatch = true;
            }
        });
        
        // Also check by file name in the file-name element
        const fileNameElement = item.querySelector('.file-name');
        if (fileNameElement && fileNameElement.textContent === fileName) {
            console.log('Found match by file name:', fileNameElement.textContent);
            isMatch = true;
        }
        
        if (isMatch && status === 'synced') {
            foundMatch = true;
            console.log('Updating matched file item');
            // Add synced class for visual feedback
            item.classList.add('synced');
            
            // Update the file info to show synced status
            const fileInfoDiv = item.querySelector('.file-info');
            if (fileInfoDiv) {
                // Add a synced indicator if not already present
                if (!item.querySelector('.sync-status')) {
                    const syncStatus = document.createElement('div');
                    syncStatus.className = 'sync-status';
                    syncStatus.innerHTML = '<i class="fas fa-check-circle"></i> Synced';
                    fileInfoDiv.appendChild(syncStatus);
                }
                
                // Update the file-size text to show synced status
                const fileSizeDiv = item.querySelector('.file-size');
                if (fileSizeDiv && !fileSizeDiv.textContent.includes('Synced')) {
                    fileSizeDiv.innerHTML = fileSizeDiv.textContent + ' - <span style="color: #4caf50;">✓ Synced</span>';
                }
            }
            
            // Disable and update the sync button
            const syncButton = item.querySelector('.add-to-sync-btn');
            if (syncButton) {
                syncButton.disabled = true;
                syncButton.innerHTML = '<i class="fas fa-check"></i> Synced';
                syncButton.classList.add('synced');
                syncButton.classList.remove('added');
            }
        }
    });
    
    if (!foundMatch) {
        console.log('WARNING: No matching file item found for:', fileId, fileName);
    }
}

// Make Fill Graphics functions available globally
window.loadRegion1Graphics = loadRegion1Graphics;
window.loadRegion2Graphics = loadRegion2Graphics;
window.loadMusicFiles = loadMusicFiles;
window.updateRegion1Selection = updateRegion1Selection;
window.updateRegion2Selection = updateRegion2Selection;
window.updateRegion3Selection = updateRegion3Selection;
// These are now handled by the fill_graphics module
// window.showGenerateProjectModal = showGenerateProjectModal;
// window.closeGenerateProjectModal = closeGenerateProjectModal;
window.generateProjectFile = generateProjectFile;

// Missing Files Modal Functions
function showMissingFilesModal(missingFiles) {
    const modal = document.getElementById('missingFilesModal');
    const listEl = document.getElementById('missingFilesList');
    
    if (!modal || !listEl) {
        console.error('Missing files modal elements not found');
        return;
    }
    
    // Clear existing content
    listEl.innerHTML = '';
    
    // Display missing files
    missingFiles.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'missing-file-item';
        fileItem.style.cssText = 'padding: 8px; margin-bottom: 5px; background-color: rgba(255,0,0,0.1); border-radius: 4px; font-size: 14px;';
        fileItem.innerHTML = `
            <strong>${file.title}</strong><br>
            <span style="color: #999; font-size: 12px;">${file.file_path}</span>
        `;
        listEl.appendChild(fileItem);
    });
    
    // Show modal
    modal.style.display = 'block';
}

function closeMissingFilesModal() {
    const modal = document.getElementById('missingFilesModal');
    if (modal) {
        modal.style.display = 'none';
    }
    // Clear data
    window.missingFilesData = null;
}

function proceedWithMissingFiles() {
    closeMissingFilesModal();
    // Continue with the original callback
    if (window.missingFilesData && window.missingFilesData.callback) {
        window.missingFilesData.callback();
    }
}

async function removeMissingFiles() {
    if (!window.missingFilesData || !window.missingFilesData.missing_files) {
        return;
    }
    
    const missingFiles = window.missingFilesData.missing_files;
    const removedAssetIds = [];
    
    // Remove each missing file from the database
    for (const file of missingFiles) {
        if (file.asset_id) {
            try {
                const response = await fetch(`/api/content/${file.asset_id}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    removedAssetIds.push(file.asset_id);
                    log(`Removed missing file from database: ${file.title}`, 'info');
                }
            } catch (error) {
                console.error(`Error removing file ${file.title}:`, error);
            }
        }
    }
    
    // Store removed asset IDs for filtering
    window.missingFilesData.removed_asset_ids = removedAssetIds;
    
    closeMissingFilesModal();
    
    // Show confirmation
    showNotification(`Removed ${removedAssetIds.length} missing files from database`, 'success');
    
    // Continue with the original callback
    if (window.missingFilesData.callback) {
        window.missingFilesData.callback();
    }
}

// Make functions available globally
window.showMissingFilesModal = showMissingFilesModal;
window.closeMissingFilesModal = closeMissingFilesModal;
window.proceedWithMissingFiles = proceedWithMissingFiles;
window.removeMissingFiles = removeMissingFiles;
window.continueCreateSchedule = continueCreateSchedule;
