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
            status: 'identical' // default
        };
        
        if (!targetFile) {
            // File missing on target
            comparisonResult.status = 'missing';
            availableFiles.push({ type: 'copy', file: sourceFile, id: fileId });
        } else if (sourceFile.size !== targetFile.size) {
            // File size different
            comparisonResult.status = 'different';
            availableFiles.push({ type: 'update', file: sourceFile, id: fileId });
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
            const fileId = btoa(targetRelativePath + '_target_only').replace(/[^a-zA-Z0-9]/g, '');
            
            const targetOnlyResult = {
                targetFile: targetFile,
                sourceFile: null,
                fileId: fileId,
                relativePath: targetRelativePath,
                status: 'target_only'
            };
            
            targetOnlyFiles.push(targetOnlyResult);
        }
    });
    
    // Update summary
    updateComparisonSummary();
    
    // Render results (default to unsynced only)
    renderComparisonResults();
    
    log(`Comparison complete. Found ${availableFiles.length} files that can be synced, ${targetOnlyFiles.length} target-only files`, 'success');
    
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
            
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${result.targetFile.name}</div>
                    <div class="file-path">${result.relativePath !== result.targetFile.name ? result.relativePath : ''}</div>
                    <div class="file-size">${formatFileSize(result.targetFile.size)} - Only on target</div>
                </div>
                <div class="file-actions">
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
                
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${result.targetFile.name}</div>
                        <div class="file-path">${result.relativePath !== result.targetFile.name ? result.relativePath : ''}</div>
                        <div class="file-size">${formatFileSize(result.targetFile.size)} - Only on target</div>
                    </div>
                    <div class="file-actions">
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
        document.getElementById('dryRun').checked = sync.dry_run_default !== false;
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
    document.getElementById('dryRun').checked = true;
    
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
        const response = await fetch('http://127.0.0.1:5000/api/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const result = await response.json();
        
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
    if (sourceHost) {
        sourceStatusText.textContent = `${sourceHost} - Ready`;
        sourceStatusText.style.color = 'var(--success-color)';
    } else {
        sourceStatusText.textContent = 'Not Configured';
        sourceStatusText.style.color = 'var(--text-secondary)';
    }
    
    // Update target server status
    const targetStatusText = document.getElementById('targetStatusText');
    const targetHost = document.getElementById('targetHost').value;
    if (targetHost) {
        targetStatusText.textContent = `${targetHost} - Ready`;
        targetStatusText.style.color = 'var(--success-color)';
    } else {
        targetStatusText.textContent = 'Not Configured';
        targetStatusText.style.color = 'var(--text-secondary)';
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
    
    // Initialize theme
    initializeTheme();
    
    // Load AI settings on page load
    loadAISettings();
    
    // Initialize collapsible cards
    initializeCollapsibleCards();
    
    // Initialize with dashboard panel
    showPanel('dashboard');
    
    // Auto-load config on startup
    loadConfig();
    
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

// Scheduling Constants and Configuration
const SCHEDULING_CONFIG = {
    // Duration categories in seconds
    DURATION_CATEGORIES: {
        id: { min: 0, max: 16, label: 'ID (< 16s)' },
        spots: { min: 16, max: 120, label: 'Spots (16s - 2min)' },
        short_form: { min: 120, max: 1200, label: 'Short Form (2-20min)' },
        long_form: { min: 1200, max: Infinity, label: 'Long Form (> 20min)' }
    },
    
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
    }
    
    title.textContent = titleText;
    body.innerHTML = bodyContent;
    modal.style.display = 'block';
    body.setAttribute('data-config-type', configType);
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
    return `
        <div class="config-section">
            <h4>Configure Replay Delays</h4>
            <p>Set minimum hours between replays for each content category:</p>
            
            <div class="replay-config">
                <div class="form-group">
                    <label>ID Replays</label>
                    <input type="number" id="id_replay_delay" value="6" min="0"> hours
                </div>
                
                <div class="form-group">
                    <label>Spots Replays</label>
                    <input type="number" id="spots_replay_delay" value="12" min="0"> hours
                </div>
                
                <div class="form-group">
                    <label>Short Form Replays</label>
                    <input type="number" id="short_form_replay_delay" value="24" min="0"> hours
                </div>
                
                <div class="form-group">
                    <label>Long Form Replays</label>
                    <input type="number" id="long_form_replay_delay" value="48" min="0"> hours
                </div>
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

function closeConfigModal() {
    document.getElementById('configModal').style.display = 'none';
}

function saveScheduleConfig() {
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
    }
    
    closeConfigModal();
    log(`✅ ${configType} configuration saved successfully`);
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
}

function saveExpirationConfig() {
    scheduleConfig.CONTENT_EXPIRATION = {
        id: parseInt(document.getElementById('id_expiration').value),
        spots: parseInt(document.getElementById('spots_expiration').value),
        short_form: parseInt(document.getElementById('short_form_expiration').value),
        long_form: parseInt(document.getElementById('long_form_expiration').value)
    };
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
            
            // Log some details about the content for debugging
            if (availableContent.length > 0) {
                log(`📊 Content types found: ${[...new Set(availableContent.map(c => c.content_type))].join(', ')}`);
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

function displayAvailableContent() {
    const contentList = document.getElementById('availableContentList');
    
    if (availableContent.length === 0) {
        contentList.innerHTML = '<p>No content matches the current filters</p>';
        return;
    }
    
    let html = '<div class="available-content">';
    
    availableContent.forEach(content => {
        const duration = formatDuration(content.file_duration);
        const durationCategory = getDurationCategory(content.file_duration);
        const engagementScore = content.engagement_score || 'N/A';
        
        // Use _id as the content identifier (ObjectId converted to string)
        const contentId = content._id || content.guid || 'unknown';
        
        html += `
            <div class="content-item" data-content-id="${contentId}">
                <div class="content-info">
                    <span class="content-title">${content.content_title || content.file_name}</span>
                    <span class="content-type">${getContentTypeLabel(content.content_type)}</span>
                    <span class="content-duration">${duration} (${durationCategory})</span>
                    <span class="engagement-score">Engagement: ${engagementScore}%</span>
                </div>
                <div class="content-actions">
                    <button class="button small primary" onclick="addToSchedule('${contentId}')">
                        <i class="fas fa-calendar-plus"></i> Add to Schedule
                    </button>
                    <button class="button small secondary" onclick="viewContentDetails('${contentId}')">
                        <i class="fas fa-info"></i> Details
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
            
            // Set the view date to the newly created schedule
            document.getElementById('viewScheduleDate').value = scheduleDate;
            
            // Refresh schedule display
            await viewDailySchedule();
            
            // Also refresh the schedule list if it's open
            await listAllSchedules();
        } else {
            log(`❌ Failed to create schedule: ${result.message}`, 'error');
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
    
    // Calculate the Monday of the week containing the selected date
    const selectedDate = new Date(scheduleDate);
    const dayOfWeek = selectedDate.getDay();
    const monday = new Date(selectedDate);
    monday.setDate(selectedDate.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));
    
    const weekStartDate = monday.toISOString().split('T')[0];
    
    log(`📅 Creating weekly schedule starting Monday ${weekStartDate}...`);
    log(`🔄 Creating schedules for 7 days...`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/create-weekly-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_date: weekStartDate
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ ${result.message}`);
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
        } else {
            log(`❌ Failed to create weekly schedule: ${result.message}`, 'error');
        }
        
    } catch (error) {
        log(`❌ Error creating weekly schedule: ${error.message}`, 'error');
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
            log(`✅ Schedule found for ${viewDate}`);
            
            // Display schedule in the schedule display area
            displayScheduleDetails(schedule);
            
        } else {
            log(`📭 No schedule found for ${viewDate}`);
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
            <h4>📋 Active Daily Schedules (${schedules.length} total)</h4>
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
        const dateObj = new Date(airDate + 'T00:00:00');
        const dayName = dateObj.toLocaleDateString('en-US', { weekday: 'long' });
        const createdAt = new Date(schedule.created_date).toLocaleString();
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
    
    document.getElementById('modalExportServer').value = savedServer;
    document.getElementById('modalExportPath').value = savedPath;
    
    // Generate default filename based on date
    const scheduleDate = new Date(viewDate);
    const dayName = scheduleDate.toLocaleDateString('en-US', { weekday: 'short' }).toLowerCase();
    const dateStr = viewDate.replace(/-/g, '');
    const defaultFilename = `${dayName}_${dateStr}.sch`;
    
    document.getElementById('modalExportFilename').value = defaultFilename;
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
    log(`📋 Format: ${exportFormat === 'castus_daily' ? 'Castus Daily Schedule' : 'Unknown'}`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/export-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: viewDate,
                export_server: exportServer,
                export_path: exportPath,
                filename: exportFilename,
                format: 'castus' // Always use castus format for now
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
            
            // Show success modal
            showExportResult(true, 'Export Successful!', `Schedule exported to ${result.file_path || fullPath}`);
        } else {
            log(`❌ ${result.message}`, 'error');
            
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
function displayScheduleDetails(schedule) {
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    
    if (!scheduleDisplay) return;
    
    const airDate = schedule.air_date ? schedule.air_date.split('T')[0] : 'Unknown';
    const createdAt = new Date(schedule.created_date || schedule.created_at).toLocaleString();
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
                <span class="col-last-scheduled">Last Scheduled</span>
            </div>
    `;
    
    if (schedule.items && schedule.items.length > 0) {
        schedule.items.forEach((item, index) => {
            const startTime = item.scheduled_start_time || '00:00:00';
            const durationSeconds = item.scheduled_duration_seconds || 0;
            
            // Calculate end time
            const endTime = calculateEndTime(startTime, durationSeconds);
            
            // Format duration as timecode
            const durationTimecode = formatDurationTimecode(durationSeconds);
            
            // Extract content type description
            const contentTypeLabel = getContentTypeLabel(item.content_type);
            
            // Use content title or file name
            const title = item.content_title || item.file_name || 'Untitled';
            const categoryLabel = item.duration_category ? item.duration_category.replace('_', ' ').toUpperCase() : '';
            
            // Format last scheduled date
            let lastScheduledDisplay = 'Never';
            if (item.last_scheduled_date) {
                const lastScheduledDate = new Date(item.last_scheduled_date);
                const month = (lastScheduledDate.getMonth() + 1).toString().padStart(2, '0');
                const day = lastScheduledDate.getDate().toString().padStart(2, '0');
                const year = lastScheduledDate.getFullYear().toString().slice(-2);
                const hours = lastScheduledDate.getHours().toString().padStart(2, '0');
                const minutes = lastScheduledDate.getMinutes().toString().padStart(2, '0');
                lastScheduledDisplay = `${month}/${day}/${year} ${hours}:${minutes}`;
            }
            
            html += `
                <div class="schedule-item-row">
                    <span class="col-start-time">${startTime}</span>
                    <span class="col-end-time">${endTime}</span>
                    <span class="col-title" title="${item.file_name}">${title}</span>
                    <span class="col-category">${categoryLabel}</span>
                    <span class="col-duration">${durationTimecode}</span>
                    <span class="col-last-scheduled">${lastScheduledDisplay}</span>
                </div>
            `;
        });
    } else {
        html += '<div class="schedule-no-items">No scheduled items found.</div>';
    }
    
    html += '</div></div>';
    
    scheduleDisplay.innerHTML = html;
}

// Format time in HH:MM:SS.000 format
function formatTimeHHMMSSmmm(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const milliseconds = Math.floor((seconds % 1) * 1000);
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
}

// Calculate end time from start time and duration
function calculateEndTime(startTime, durationSeconds) {
    // Parse start time (HH:MM:SS)
    const [hours, minutes, seconds] = startTime.split(':').map(Number);
    
    // Ensure durationSeconds is a number (handle string/decimal inputs)
    // PostgreSQL returns NUMERIC which should be converted to float in backend
    const duration = parseFloat(durationSeconds) || 0;
    
    // Convert start time to total seconds
    const startTotalSeconds = hours * 3600 + minutes * 60 + seconds;
    
    // Add duration
    let endTotalSeconds = startTotalSeconds + duration;
    
    // Calculate new time components (handle 24+ hour wraparound)
    const endHours = Math.floor(endTotalSeconds / 3600) % 24;
    const endMinutes = Math.floor((endTotalSeconds % 3600) / 60);
    const endSeconds = Math.floor(endTotalSeconds % 60);
    
    // Format as HH:MM:SS
    return `${endHours.toString().padStart(2, '0')}:${endMinutes.toString().padStart(2, '0')}:${endSeconds.toString().padStart(2, '0')}`;
}

// Format duration in seconds to H:MM:SS format
function formatDurationTimecode(durationSeconds) {
    const duration = parseFloat(durationSeconds) || 0;
    
    const hours = Math.floor(duration / 3600);
    const minutes = Math.floor((duration % 3600) / 60);
    const seconds = Math.floor(duration % 60);
    
    // Format as H:MM:SS (single digit hours, double digit minutes/seconds)
    return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

// Get content type label from configuration
function getContentTypeLabel(contentType) {
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
    
    return contentTypeMap[contentType] || contentType || 'Unknown';
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
    const scheduleDisplay = document.getElementById('scheduleDisplay');
    if (scheduleDisplay) {
        scheduleDisplay.innerHTML = '<p>Select a date and click "View Schedule" to display the daily schedule</p>';
    }
}

// Collapsible card functionality
function initializeCollapsibleCards() {
    const cards = document.querySelectorAll('.scheduling-card h3');
    cards.forEach(header => {
        header.addEventListener('click', function() {
            const card = this.parentElement;
            toggleCard(card);
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

function addToSchedule(contentId) {
    log(`📅 Adding content ${contentId} to schedule (not yet implemented)`);
}

function viewContentDetails(contentId) {
    log(`ℹ️ Viewing details for content ${contentId} (not yet implemented)`);
}

// Initialize scheduling when page loads
document.addEventListener('DOMContentLoaded', function() {
    initializeSchedulingDates();
});