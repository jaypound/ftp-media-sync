// Global variables
let sourceFiles = [];
let targetFiles = [];
let syncQueue = [];
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

function updateProgress(current, total) {
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    
    if (total > 0) {
        const percentage = (current / total) * 100;
        progressFill.style.width = percentage + '%';
        progressBar.style.display = 'block';
    } else {
        progressBar.style.display = 'none';
    }
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
    
    const fileListDiv = document.getElementById('fileList');
    const comparisonCard = document.getElementById('comparisonCard');
    fileListDiv.innerHTML = '';
    comparisonCard.style.display = 'block';
    
    syncQueue = [];
    
    // Create a map of target files for quick lookup
    const targetFileMap = new Map();
    targetFiles.forEach(file => {
        targetFileMap.set(file.name, file);
    });
    
    sourceFiles.forEach(sourceFile => {
        const targetFile = targetFileMap.get(sourceFile.name);
        
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        
        if (!targetFile) {
            // File missing on target
            fileItem.classList.add('missing');
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${sourceFile.name}</div>
                    <div class="file-size">${formatFileSize(sourceFile.size)} - Missing on target</div>
                </div>
                <button class="button" onclick="addToSyncQueue('${sourceFile.name}')">Add to Sync</button>
            `;
            syncQueue.push({ type: 'copy', file: sourceFile });
        } else if (sourceFile.size !== targetFile.size) {
            // File size different
            fileItem.classList.add('different');
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${sourceFile.name}</div>
                    <div class="file-size">Source: ${formatFileSize(sourceFile.size)} | Target: ${formatFileSize(targetFile.size)}</div>
                </div>
                <button class="button" onclick="addToSyncQueue('${sourceFile.name}')">Update</button>
            `;
            syncQueue.push({ type: 'update', file: sourceFile });
        } else {
            // File identical
            fileItem.innerHTML = `
                <div class="file-info">
                    <div class="file-name">${sourceFile.name}</div>
                    <div class="file-size">${formatFileSize(sourceFile.size)} - Identical</div>
                </div>
                <span style="color: #28a745;">✅ Synced</span>
            `;
        }
        
        fileListDiv.appendChild(fileItem);
    });
    
    log(`Comparison complete. Found ${syncQueue.length} files to sync`, 'success');
    
    // Enable sync button if there are files to sync
    document.getElementById('syncButton').disabled = syncQueue.length === 0;
}

function displayScannedFiles() {
    const scannedFilesCard = document.getElementById('scannedFilesCard');
    const sourceFilesList = document.getElementById('sourceFilesList');
    const targetFilesList = document.getElementById('targetFilesList');
    const sourceFileCount = document.getElementById('sourceFileCount');
    const targetFileCount = document.getElementById('targetFileCount');
    
    // Show the scanned files card
    scannedFilesCard.style.display = 'block';
    
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
            <div class="scanned-file-path">${file.path}</div>
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
            <div class="scanned-file-path">${file.path}</div>
        `;
        targetFilesList.appendChild(fileItem);
    });
}

function clearScannedFiles() {
    // Hide display cards
    document.getElementById('scannedFilesCard').style.display = 'none';
    document.getElementById('comparisonCard').style.display = 'none';
    
    // Clear data
    sourceFiles = [];
    targetFiles = [];
    syncQueue = [];
    
    // Reset UI
    document.querySelector('button[onclick="compareFiles()"]').disabled = true;
    document.getElementById('syncButton').disabled = true;
    
    // Clear file lists
    document.getElementById('sourceFilesList').innerHTML = '';
    document.getElementById('targetFilesList').innerHTML = '';
    document.getElementById('fileList').innerHTML = '';
    
    log('Cleared all scanned file results', 'success');
}

function addToSyncQueue(filename) {
    log(`Added ${filename} to sync queue`);
}

function stopSync() {
    isSyncing = false;
    log('Sync stopped by user', 'error');
    document.getElementById('syncButton').disabled = false;
    document.getElementById('stopButton').disabled = true;
}

// Configuration management functions
async function loadConfig() {
    try {
        log('Loading configuration...');
        const response = await fetch('http://127.0.0.1:5000/api/config');
        const result = await response.json();
        
        if (result.success) {
            populateFormFromConfig(result.config);
            log('✅ Configuration loaded successfully', 'success');
        } else {
            log(`❌ Failed to load config: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`❌ Error loading config: ${error.message}`, 'error');
    }
}

async function saveConfig() {
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
        } else {
            log(`❌ Failed to save config: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`❌ Error saving config: ${error.message}`, 'error');
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
            document.getElementById('sourcePath').value = src.path || '';
            // Note: passwords are not loaded for security
        }
        
        if (config.servers.target) {
            const tgt = config.servers.target;
            document.getElementById('targetHost').value = tgt.host || '';
            document.getElementById('targetPort').value = tgt.port || 21;
            document.getElementById('targetUser').value = tgt.user || '';
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
    const config = {
        server_type: serverType,
        host: document.getElementById(`${serverType}Host`).value,
        port: document.getElementById(`${serverType}Port`).value,
        user: document.getElementById(`${serverType}User`).value,
        password: document.getElementById(`${serverType}Pass`).value
    };
    
    if (!config.host || !config.user || !config.password) {
        log(`Please fill in all ${serverType} server details`, 'error');
        return;
    }
    
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
        } else {
            log(`❌ ${result.message}`, 'error');
        }
    } catch (error) {
        log(`❌ Connection test failed: ${error.message}`, 'error');
        log('Make sure the Python backend is running on 127.0.0.1:5000', 'error');
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
    
    isSyncing = true;
    document.getElementById('syncButton').disabled = true;
    document.getElementById('stopButton').disabled = false;
    
    syncStats = { processed: 0, total: syncQueue.length, errors: 0 };
    
    log(`Starting ${dryRun ? 'dry run' : 'sync'} of ${syncQueue.length} files...`);
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/sync-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sync_queue: syncQueue,
                dry_run: dryRun
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            result.results.forEach((item, index) => {
                updateProgress(index + 1, result.results.length);
                
                if (item.status === 'would_sync') {
                    log(`[DRY RUN] Would ${item.action} ${item.file} (${formatFileSize(item.size)})`);
                } else if (item.status === 'success') {
                    log(`✅ ${item.action === 'copy' ? 'Copied' : 'Updated'} ${item.file}`, 'success');
                    syncStats.processed++;
                } else {
                    log(`❌ Error with ${item.file}: ${item.error || 'Unknown error'}`, 'error');
                    syncStats.errors++;
                }
            });
            
            log(`Sync completed! Processed: ${syncStats.processed}, Errors: ${syncStats.errors}`, 'success');
        } else {
            log(`Sync failed: ${result.message}`, 'error');
        }
        
    } catch (error) {
        log(`Sync error: ${error.message}`, 'error');
    }
    
    isSyncing = false;
    document.getElementById('syncButton').disabled = false;
    document.getElementById('stopButton').disabled = true;
}

// Initialize the app
window.addEventListener('load', function() {
    log('FTP Media Server Sync initialized');
    log('Click "Load Config" to load saved settings, or configure manually');
    log('Use "Save Config" to remember your settings for next time');
    
    // Auto-load config on startup
    loadConfig();
});