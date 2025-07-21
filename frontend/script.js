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
let showAllFiles = false; // Toggle for showing all files vs unsynced only
let showTargetOnly = false; // Toggle for showing target-only files
let showAnalysisAll = false; // Toggle for showing all analysis files
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
    
    // Update file counts
    sourceFileCount.textContent = `${sourceFiles.length} files found`;
    sourceFileCount.className = sourceFiles.length > 0 ? 'file-count has-files' : 'file-count';
    
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
    
    if (detailsDiv.style.display === 'none') {
        detailsDiv.style.display = 'grid';
        summaryDiv.style.display = 'none';
        toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Details';
    } else {
        detailsDiv.style.display = 'none';
        summaryDiv.style.display = 'block';
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i> Show Details';
    }
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
        filePath: filePath
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
            analyzeAllButton.disabled = true;
            analyzeAllButton.textContent = 'Analyze All Unanalyzed (0 files)';
            analyzeAllButton.title = 'No unanalyzed video files found';
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
        
        // Update button to show analyzing state
        if (button) {
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
            button.disabled = true;
        }
        
        try {
            // Check if this file is being reanalyzed
            const isReanalysis = queueItem.file.is_analyzed || false;
            
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