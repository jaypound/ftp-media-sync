// Global variables
let sourceFiles = [];
let targetFiles = [];
let syncQueue = [];
let availableFiles = []; // New: tracks files that CAN be synced
let allComparisonResults = []; // Store all comparison results
let targetOnlyFiles = []; // Files that exist on target but not on source
let showAllFiles = false; // Toggle for showing all files vs unsynced only
let showTargetOnly = false; // Toggle for showing target-only files
let isScanning = false;
let isSyncing = false;
let syncStats = { processed: 0, total: 0, errors: 0 };

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
                <span style="color: #0288d1;">📁 Target Only</span>
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
                    <span style="color: #0288d1;">📁 Target Only</span>
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
    sourceFilesList.innerHTML = '';
    sourceFiles.forEach(file => {
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
    
    // Reset UI
    document.querySelector('button[onclick="compareFiles()"]').disabled = true;
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
        
        // Enable compare button
        document.querySelector('button[onclick="compareFiles()"]').disabled = false;
        
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

// Initialize the app
window.addEventListener('load', function() {
    log('FTP Media Server Sync initialized');
    log('Welcome to the modern FTP sync interface!');
    log('Navigate using the menu above to configure servers and settings');
    
    // Initialize theme
    initializeTheme();
    
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