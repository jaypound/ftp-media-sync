/**
 * Fill Graphics Module
 * Handles creation of slideshow project files with graphics and music
 */

// Fill Graphics State
const fillGraphicsState = {
    region1: {
        server: '',
        path: '/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION',
        files: [],
        selected: []
    },
    region2: {
        server: '',
        path: '/mnt/main/Graphics',
        files: [],
        selected: null
    },
    region3: {
        server: '',
        path: '/mnt/main/Music',
        files: [],
        selected: []
    },
    canGenerate: false,
    databaseMode: true,  // Start in database mode
    databaseGraphics: [],
    selectedGraphicIds: []
};

// Initialize Fill Graphics Module
function fillGraphicsInit() {
    console.log('Initializing Fill Graphics module...');
    
    // Set up event listeners
    fillGraphicsSetupEventListeners();
    
    // Update initial state
    fillGraphicsUpdateGenerateButton();
    
    // Update AppState
    AppState.setModule('fill_graphics', fillGraphicsState);
    
    // Initialize database view
    if (fillGraphicsState.databaseMode) {
        const dbCard = document.getElementById('databaseGraphicsCard');
        const region1Card = document.querySelector('.fill-graphics-region1-card');
        if (dbCard) {
            dbCard.style.display = 'block';
        }
        if (region1Card) {
            region1Card.classList.add('fill-graphics-region-hidden');
        }
        fillGraphicsLoadFromDatabase();
    }
}

// Set up event listeners
function fillGraphicsSetupEventListeners() {
    // Path change listeners
    ['region1Path', 'region2Path', 'region3Path'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', fillGraphicsHandlePathChange);
        }
    });
    
    // Server change listeners
    ['region1Server', 'region2Server', 'region3Server'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', fillGraphicsHandleServerChange);
        }
    });
}

// Handle path change
function fillGraphicsHandlePathChange(event) {
    const input = event.target;
    const regionNum = parseInt(input.id.match(/region(\d)/)[1]);
    fillGraphicsState[`region${regionNum}`].path = input.value;
    
    // Reload files if server is selected
    if (fillGraphicsState[`region${regionNum}`].server) {
        fillGraphicsLoadFiles(regionNum);
    }
}

// Handle server change
function fillGraphicsHandleServerChange(event) {
    const select = event.target;
    const regionNum = parseInt(select.id.match(/region(\d)/)[1]);
    console.log(`DEBUG: Server change for region ${regionNum}, server: ${select.value}`);
    fillGraphicsState[`region${regionNum}`].server = select.value;
    
    // Load files for selected server
    if (select.value) {
        fillGraphicsLoadFiles(regionNum);
    }
}

// Load graphics files for region 1
async function fillGraphicsLoadRegion1Graphics() {
    // Sync state from DOM
    const serverEl = document.getElementById('region1Server');
    const pathEl = document.getElementById('region1Path');
    if (serverEl) fillGraphicsState.region1.server = serverEl.value;
    if (pathEl) fillGraphicsState.region1.path = pathEl.value;
    
    await fillGraphicsLoadFiles(1);
}

// Load graphics files for region 2
async function fillGraphicsLoadRegion2Graphics() {
    // Sync state from DOM
    const serverEl = document.getElementById('region2Server');
    const pathEl = document.getElementById('region2Path');
    if (serverEl) fillGraphicsState.region2.server = serverEl.value;
    if (pathEl) fillGraphicsState.region2.path = pathEl.value;
    
    await fillGraphicsLoadFiles(2);
}

// Load music files
async function fillGraphicsLoadMusicFiles() {
    // Sync state from DOM
    const serverEl = document.getElementById('region3Server');
    const pathEl = document.getElementById('region3Path');
    if (serverEl) fillGraphicsState.region3.server = serverEl.value;
    if (pathEl) fillGraphicsState.region3.path = pathEl.value;
    
    await fillGraphicsLoadFiles(3);
}

// Generic file loader
async function fillGraphicsLoadFiles(regionNum) {
    console.log(`DEBUG: Loading files for region ${regionNum}`);
    
    const region = fillGraphicsState[`region${regionNum}`];
    if (!region.server || !region.path) {
        console.log(`DEBUG: No server or path for region ${regionNum}`);
        return;
    }
    
    const listElement = document.getElementById(
        regionNum === 1 ? 'region1GraphicsList' :
        regionNum === 2 ? 'region2GraphicsList' :
        'musicFilesList'
    );
    
    if (listElement) {
        listElement.innerHTML = '<div class="fill-graphics-loading"><i class="fas fa-spinner fa-spin"></i> Loading files...</div>';
    }
    
    try {
        const response = await window.API.post('/list-files', {
            server: region.server,
            path: region.path,
            extensions: regionNum === 3 ? ['mp4', 'wav'] : ['jpg', 'png']
        });
        
        if (response.success) {
            // Sort files by creation date (newest first) for region 1 (graphics)
            if (regionNum === 1) {
                response.files.sort((a, b) => {
                    // Sort by creation time, newest first
                    // Try ctime (creation time) first, then fall back to mtime
                    const aTime = a.ctime || a.mtime;
                    const bTime = b.ctime || b.mtime;
                    
                    if (aTime && bTime) {
                        return new Date(bTime) - new Date(aTime);
                    }
                    // Fall back to reverse alphabetical if no timestamps
                    return b.name.localeCompare(a.name);
                });
                console.log('Sorted region 1 files by creation date (newest first)');
            }
            
            region.files = response.files;
            fillGraphicsDisplayFiles(regionNum, response.files);
            
            // Show/hide select all buttons for region 1
            if (regionNum == 1) {
                const selectAllBtn = document.getElementById('selectAllRegion1Btn');
                const deselectAllBtn = document.getElementById('deselectAllRegion1Btn');
                if (selectAllBtn) selectAllBtn.style.display = response.files.length > 0 ? 'inline-block' : 'none';
                if (deselectAllBtn) deselectAllBtn.style.display = response.files.length > 0 ? 'inline-block' : 'none';
            }
        }
    } catch (error) {
        console.error(`Failed to load files for region ${regionNum}:`, error);
        if (listElement) {
            listElement.innerHTML = '<div class="fill-graphics-empty"><i class="fas fa-exclamation-circle"></i><p>Failed to load files</p></div>';
        }
    }
}

// Display files
function fillGraphicsDisplayFiles(regionNum, files) {
    const elementId = regionNum === 1 ? 'region1GraphicsList' :
                      regionNum === 2 ? 'region2GraphicsList' :
                      'musicFilesList';
    
    console.log(`DEBUG: Displaying files for region ${regionNum} in element ${elementId}`);
    console.log(`DEBUG: Found ${files.length} files`);
    
    const listElement = document.getElementById(elementId);
    
    if (!listElement) {
        console.error(`ERROR: Could not find element with ID ${elementId}`);
        return;
    }
    
    if (files.length === 0) {
        listElement.innerHTML = '<div class="fill-graphics-empty"><i class="fas fa-folder-open"></i><p>No files found</p></div>';
        return;
    }
    
    let html = '';
    
    files.forEach((file, index) => {
        const isSelected = regionNum == 1 ? 
            fillGraphicsState.region1.selected.includes(file.name) :
            regionNum == 2 ?
            fillGraphicsState.region2.selected === file.name :
            fillGraphicsState.region3.selected.includes(file.name);
        
        const iconClass = regionNum == 3 ? 'music' : 'image';
        const iconType = regionNum == 3 ? 'fa-music' : 'fa-image';
        
        html += `
            <div class="fill-graphics-file-item ${isSelected ? 'selected' : ''}" 
                 onclick="fillGraphicsToggleFile(${regionNum}, '${file.name}', ${index})">
                <input type="${regionNum == 2 ? 'radio' : 'checkbox'}" 
                       class="fill-graphics-file-checkbox"
                       ${isSelected ? 'checked' : ''}
                       name="${regionNum == 2 ? 'region2File' : ''}">
                <i class="fas ${iconType} fill-graphics-file-icon ${iconClass}"></i>
                <div class="fill-graphics-file-info">
                    <div class="fill-graphics-file-name">${file.name}</div>
                    <div class="fill-graphics-file-details">${fillGraphicsFormatFileSize(file.size)}</div>
                </div>
            </div>
        `;
    });
    
    listElement.innerHTML = html;
}

// Toggle file selection
function fillGraphicsToggleFile(regionNum, filename, index) {
    const region = fillGraphicsState[`region${regionNum}`];
    
    if (regionNum == 2) {
        // Radio button behavior for region 2
        region.selected = region.selected === filename ? null : filename;
    } else {
        // Checkbox behavior for regions 1 and 3
        const selectedIndex = region.selected.indexOf(filename);
        if (selectedIndex > -1) {
            region.selected.splice(selectedIndex, 1);
        } else {
            region.selected.push(filename);
        }
    }
    
    // Refresh display
    fillGraphicsDisplayFiles(regionNum, region.files);
    
    // Update generate button state
    fillGraphicsUpdateGenerateButton();
}

// Select all region 1 graphics
function fillGraphicsSelectAllRegion1Graphics() {
    fillGraphicsState.region1.selected = fillGraphicsState.region1.files.map(f => f.name);
    fillGraphicsDisplayFiles(1, fillGraphicsState.region1.files);
    fillGraphicsUpdateGenerateButton();
}

// Deselect all region 1 graphics
function fillGraphicsDeselectAllRegion1Graphics() {
    fillGraphicsState.region1.selected = [];
    fillGraphicsDisplayFiles(1, fillGraphicsState.region1.files);
    fillGraphicsUpdateGenerateButton();
}

// Update generate button state
function fillGraphicsUpdateGenerateButton() {
    console.log('DEBUG: Updating generate button state');
    console.log(`  Database mode: ${fillGraphicsState.databaseMode}`);
    
    let canGenerate = false;
    
    if (fillGraphicsState.databaseMode) {
        // In database mode, require selected graphics and music files
        console.log(`  Selected graphics: ${fillGraphicsState.selectedGraphicIds.length}`);
        console.log(`  Region 2 selected: ${fillGraphicsState.region2.selected}`);
        console.log(`  Region 3 selected: ${fillGraphicsState.region3.selected.length} files`);
        console.log(`  Active graphics in DB: ${fillGraphicsState.databaseGraphics.filter(g => g.status === 'active').length}`);
        
        canGenerate = 
            fillGraphicsState.selectedGraphicIds.length > 0 &&  // Must have selected graphics
            fillGraphicsState.region3.selected.length > 0;
    } else {
        // Manual mode - require all three regions
        console.log(`  Region 1 selected: ${fillGraphicsState.region1.selected.length} files`);
        console.log(`  Region 2 selected: ${fillGraphicsState.region2.selected}`);
        console.log(`  Region 3 selected: ${fillGraphicsState.region3.selected.length} files`);
        
        canGenerate = 
            fillGraphicsState.region1.selected.length > 0 &&
            fillGraphicsState.region2.selected !== null &&
            fillGraphicsState.region3.selected.length > 0;
    }
    
    console.log(`  Can generate: ${canGenerate}`);
    
    fillGraphicsState.canGenerate = canGenerate;
    
    const projectButton = document.getElementById('generateProjectBtn');
    if (projectButton) {
        console.log(`  Project button found, setting disabled to: ${!canGenerate}`);
        projectButton.disabled = !canGenerate;
    }
    
    const videoButton = document.getElementById('generateVideoBtn');
    if (videoButton) {
        console.log(`  Video button found, setting disabled to: ${!canGenerate}`);
        videoButton.disabled = !canGenerate;
    }
}

// Show generate project modal
function fillGraphicsShowGenerateProjectModal() {
    if (!fillGraphicsState.canGenerate) return;
    
    console.log('DEBUG: Opening generate modal with state:', {
        region1: fillGraphicsState.region1.selected,
        region2: fillGraphicsState.region2.selected,
        region3: fillGraphicsState.region3.selected
    });
    
    // Update summary in modal
    const summaryEl = document.getElementById('projectSummary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <p><strong>Region 1 (Upper Graphics):</strong> ${fillGraphicsState.region1.selected.length} files selected</p>
            <p><strong>Region 2 (Lower Graphics):</strong> ${fillGraphicsState.region2.selected || 'None'}</p>
            <p><strong>Region 3 (Music):</strong> ${fillGraphicsState.region3.selected.length} files selected</p>
        `;
    }
    
    // Show modal
    const modal = document.getElementById('generateProjectModal');
    if (modal) modal.style.display = 'block';
}

// Generate project file
async function fillGraphicsGenerateProjectFile(event) {
    const nameInput = document.getElementById('projectFileName');
    const pathInput = document.getElementById('projectExportPath');
    const serverSelect = document.getElementById('projectExportServer');
    const durationInput = document.getElementById('slideDuration');
    
    if (!nameInput || !pathInput || !serverSelect || !durationInput) return;
    
    const projectName = nameInput.value.trim();
    if (!projectName) {
        window.showNotification('Please enter a project name', 'warning');
        return;
    }
    
    const slideDuration = parseInt(durationInput.value) || 5;
    
    console.log('DEBUG: Slide duration input value:', durationInput.value);
    console.log('DEBUG: Parsed slide duration:', slideDuration);
    
    // Get button from event or find it by ID
    const button = event && event.target ? event.target : document.querySelector('.modal-footer .button.primary');
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
    
    try {
        console.log('DEBUG: Sending request with slide_duration:', slideDuration);
        
        // Get region1 files in sorted order (newest first by creation date)
        const sortedRegion1Files = fillGraphicsState.region1.files
            .filter(file => fillGraphicsState.region1.selected.includes(file.name))
            .sort((a, b) => {
                // Same sorting logic as when loading - newest first by creation date
                const aTime = a.ctime || a.mtime;
                const bTime = b.ctime || b.mtime;
                
                if (aTime && bTime) {
                    return new Date(bTime) - new Date(aTime);
                }
                return b.name.localeCompare(a.name);
            })
            .map(file => file.name);
        
        console.log('Region 1 files for project (sorted newest first):', sortedRegion1Files);
        
        const requestData = {
            project_name: projectName,
            export_path: pathInput.value,
            export_server: serverSelect.value,
            slide_duration: slideDuration,
            region1_files: sortedRegion1Files,
            region1_path: fillGraphicsState.region1.path,
            region2_file: fillGraphicsState.region2.selected,
            region2_path: fillGraphicsState.region2.path,
            region3_files: fillGraphicsState.region3.selected,
            region3_path: fillGraphicsState.region3.path
        };
        
        console.log('DEBUG: Request data:', requestData);
        const response = await window.API.post('/generate-prj-file', requestData);
        console.log('DEBUG: Response received:', response);
        
        if (response && response.success) {
            window.showNotification('Project file generated successfully!', 'success');
            fillGraphicsCloseGenerateProjectModal();
            
            // Reset selections
            fillGraphicsState.region1.selected = [];
            fillGraphicsState.region2.selected = null;
            fillGraphicsState.region3.selected = [];
            
            // Refresh displays
            fillGraphicsDisplayFiles(1, fillGraphicsState.region1.files);
            fillGraphicsDisplayFiles(2, fillGraphicsState.region2.files);
            fillGraphicsDisplayFiles(3, fillGraphicsState.region3.files);
            fillGraphicsUpdateGenerateButton();
        } else {
            console.error('DEBUG: Generate failed:', response);
            window.showNotification(`Failed to generate project: ${response.message || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('DEBUG: Generate error:', error);
        window.showNotification(`Failed to generate project: ${error.message}`, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-file-export"></i> Generate & Export';
        }
    }
}

// Close generate project modal
function fillGraphicsCloseGenerateProjectModal() {
    const modal = document.getElementById('generateProjectModal');
    if (modal) modal.style.display = 'none';
}

// Show generate video modal
function fillGraphicsShowGenerateVideoModal() {
    if (!fillGraphicsState.canGenerate) return;
    
    console.log('DEBUG: Opening generate video modal with state:', {
        region1: fillGraphicsState.region1.selected,
        region2: fillGraphicsState.region2.selected,
        region3: fillGraphicsState.region3.selected
    });
    
    // Update summary in modal
    const summaryEl = document.getElementById('videoSummary');
    if (summaryEl) {
        if (fillGraphicsState.databaseMode) {
            const selectedCount = fillGraphicsState.selectedGraphicIds.length;
            const totalActive = fillGraphicsState.databaseGraphics.filter(g => g.status === 'active').length;
            summaryEl.innerHTML = `
                <p><strong>Region 1 (Upper Graphics):</strong> ${selectedCount} graphics selected (from ${totalActive} active)</p>
                <p><strong>Region 2 (Lower Graphics):</strong> ${fillGraphicsState.region2.selected || 'None'}</p>
                <p><strong>Region 3 (Music):</strong> ${fillGraphicsState.region3.selected.length} files selected</p>
            `;
        } else {
            summaryEl.innerHTML = `
                <p><strong>Region 1 (Upper Graphics):</strong> ${fillGraphicsState.region1.selected.length} files selected</p>
                <p><strong>Region 2 (Lower Graphics):</strong> ${fillGraphicsState.region2.selected || 'None'}</p>
                <p><strong>Region 3 (Music):</strong> ${fillGraphicsState.region3.selected.length} files selected</p>
            `;
        }
    }
    
    // Set default filename with format: YYMMDD_<sort type>_<duration>
    const fileNameInput = document.getElementById('videoFileName');
    if (fileNameInput) {
        const now = new Date();
        const year = (now.getFullYear() % 100).toString().padStart(2, '0');
        const month = (now.getMonth() + 1).toString().padStart(2, '0');
        const day = now.getDate().toString().padStart(2, '0');
        const sortOrder = document.getElementById('videoSortOrder').value || 'newest';
        const duration = document.getElementById('videoMaxLength').value || '360';
        const sortType = sortOrder.toUpperCase();
        fileNameInput.value = `${year}${month}${day}_${sortType}_${duration}`;
    }
    
    // Show modal
    const modal = document.getElementById('generateVideoModal');
    if (modal) modal.style.display = 'block';
}

// Generate video file
async function fillGraphicsGenerateVideoFile() {
    let fileName = document.getElementById('videoFileName').value.trim();
    const exportPath = document.getElementById('videoExportPath').value.trim();
    const exportToSource = document.getElementById('videoExportToSource').checked;
    const exportToTarget = document.getElementById('videoExportToTarget').checked;
    const videoFormat = document.getElementById('videoFormat').value;
    const maxLength = parseInt(document.getElementById('videoMaxLength').value) || 360;
    const sortOrder = document.getElementById('videoSortOrder').value || 'newest';
    
    if (!fileName) {
        window.showNotification('Please enter a video file name', 'error');
        return;
    }
    
    // Ensure filename has the correct extension
    const extension = `.${videoFormat}`;
    if (!fileName.toLowerCase().endsWith(extension)) {
        fileName += extension;
    }
    
    if (!exportToSource && !exportToTarget) {
        window.showNotification('Please select at least one server to export to', 'error');
        return;
    }
    
    // Get the generate button and show spinner
    const button = document.querySelector('#generateVideoModal .button.primary');
    if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
    }
    
    // Check if we're in database mode
    if (fillGraphicsState.databaseMode) {
        // Use the database-aware endpoint
        try {
            const response = await window.API.post('/default-graphics/generate-video', {
                file_name: fileName,
                export_path: exportPath,
                export_to_source: exportToSource,
                export_to_target: exportToTarget,
                video_format: videoFormat,
                max_length: maxLength,
                sort_order: sortOrder,
                graphic_ids: fillGraphicsState.selectedGraphicIds,  // Send selected graphics IDs
                region2_file: fillGraphicsState.region2.selected,
                region2_path: fillGraphicsState.region2.path,
                region3_files: fillGraphicsState.region3.selected,
                region3_path: fillGraphicsState.region3.path
            });
            
            if (response && response.success) {
                window.showNotification('Video generated successfully!', 'success');
                fillGraphicsCloseGenerateVideoModal();
                
                // Reload graphics to update usage stats
                fillGraphicsLoadFromDatabase();
                
                // Reset selections
                fillGraphicsState.selectedGraphicIds = [];  // Reset selected graphics
                fillGraphicsState.region2.selected = null;
                fillGraphicsState.region3.selected = [];
                
                // Refresh displays
                fillGraphicsDisplayFiles(2, fillGraphicsState.region2.files);
                fillGraphicsDisplayFiles(3, fillGraphicsState.region3.files);
                fillGraphicsUpdateGenerateButton();
            } else {
                window.showNotification(`Failed to generate video: ${response.message || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            console.error('Video generation error:', error);
            window.showNotification(`Failed to generate video: ${error.message}`, 'error');
        } finally {
            // Restore button state
            if (button) {
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-video"></i> Generate & Export';
            }
        }
        return;
    }
    
    // Button spinner is already shown above
    
    try {
        // Get region1 files in sorted order based on user selection
        let sortedRegion1Files = fillGraphicsState.region1.files
            .filter(file => fillGraphicsState.region1.selected.includes(file.name));
        
        // Apply sort order
        switch(sortOrder) {
            case 'newest':
                sortedRegion1Files.sort((a, b) => {
                    const aTime = a.ctime || a.mtime;
                    const bTime = b.ctime || b.mtime;
                    if (aTime && bTime) {
                        return new Date(bTime) - new Date(aTime);
                    }
                    return b.name.localeCompare(a.name);
                });
                break;
            case 'oldest':
                sortedRegion1Files.sort((a, b) => {
                    const aTime = a.ctime || a.mtime;
                    const bTime = b.ctime || b.mtime;
                    if (aTime && bTime) {
                        return new Date(aTime) - new Date(bTime);
                    }
                    return a.name.localeCompare(b.name);
                });
                break;
            case 'random':
                // Fisher-Yates shuffle
                for (let i = sortedRegion1Files.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [sortedRegion1Files[i], sortedRegion1Files[j]] = [sortedRegion1Files[j], sortedRegion1Files[i]];
                }
                break;
            case 'alphabetical':
                sortedRegion1Files.sort((a, b) => a.name.localeCompare(b.name));
                break;
        }
        
        sortedRegion1Files = sortedRegion1Files.map(file => file.name);
        
        console.log(`Region 1 files for video (sorted ${sortOrder}):`, sortedRegion1Files);
        
        const requestData = {
            file_name: fileName,
            export_path: exportPath,
            export_to_source: exportToSource,
            export_to_target: exportToTarget,
            video_format: videoFormat,
            max_length: maxLength,
            region1_server: fillGraphicsState.region1.server,
            region1_path: fillGraphicsState.region1.path,
            region1_files: sortedRegion1Files,
            region2_server: fillGraphicsState.region2.server,
            region2_path: fillGraphicsState.region2.path,
            region2_file: fillGraphicsState.region2.selected,
            region3_server: fillGraphicsState.region3.server,
            region3_path: fillGraphicsState.region3.path,
            region3_files: fillGraphicsState.region3.selected
        };
        
        console.log('DEBUG: Video generation request data:', requestData);
        const response = await window.API.post('/generate-video', requestData);
        console.log('DEBUG: Response received:', response);
        
        if (response && response.success) {
            window.showNotification('Video generation started successfully!', 'success');
            fillGraphicsCloseGenerateVideoModal();
            
            // Reset selections
            fillGraphicsState.region1.selected = [];
            fillGraphicsState.region2.selected = null;
            fillGraphicsState.region3.selected = [];
            
            // Refresh displays
            fillGraphicsDisplayFiles(1, fillGraphicsState.region1.files);
            fillGraphicsDisplayFiles(2, fillGraphicsState.region2.files);
            fillGraphicsDisplayFiles(3, fillGraphicsState.region3.files);
            fillGraphicsUpdateGenerateButton();
        } else {
            console.error('DEBUG: Video generation failed:', response);
            window.showNotification(`Failed to generate video: ${response.message || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('DEBUG: Video generation error:', error);
        window.showNotification(`Failed to generate video: ${error.message}`, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-video"></i> Generate & Export';
        }
    }
}

// Close generate video modal
function fillGraphicsCloseGenerateVideoModal() {
    const modal = document.getElementById('generateVideoModal');
    if (modal) modal.style.display = 'none';
}

// Format file size
function fillGraphicsFormatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Database-related functions

// Scan DEFAULT ROTATION folder and add to database
async function fillGraphicsScanFolder() {
    console.log('Scanning DEFAULT ROTATION folder...');
    
    try {
        const response = await window.API.post('/default-graphics/scan', {
            server: 'source',
            path: '/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION'
        });
        
        if (response.success) {
            window.showNotification(response.message, 'success');
            // Reload graphics from database
            fillGraphicsLoadFromDatabase();
        } else {
            window.showNotification(response.message || 'Failed to scan folder', 'error');
        }
    } catch (error) {
        console.error('Scan error:', error);
        window.showNotification('Failed to scan folder', 'error');
    }
}

// Load graphics from database
async function fillGraphicsLoadFromDatabase() {
    const statusFilter = document.getElementById('graphicsStatusFilter')?.value || 'active';
    
    try {
        const response = await window.API.get(`/default-graphics?status=${statusFilter}`);
        
        if (response.success) {
            fillGraphicsState.databaseGraphics = response.graphics;
            fillGraphicsDisplayDatabaseGraphics(response.graphics);
            
            // Update active count
            const activeCount = response.graphics.filter(g => g.status === 'active').length;
            const countEl = document.getElementById('activeGraphicsCount');
            if (countEl) {
                countEl.textContent = `${activeCount} active`;
            }
            
            // Update generate button state
            fillGraphicsUpdateGenerateButton();
        }
    } catch (error) {
        console.error('Failed to load graphics:', error);
        window.showNotification('Failed to load graphics from database', 'error');
    }
}

// Helper function to format dates properly handling timezone
function fillGraphicsFormatDate(dateString) {
    if (!dateString) return '';
    
    // For date-only strings (YYYY-MM-DD), parse as local date, not UTC
    if (dateString.match(/^\d{4}-\d{2}-\d{2}$/)) {
        const [year, month, day] = dateString.split('-');
        const date = new Date(year, month - 1, day);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        });
    }
    
    // For full datetime strings, use regular parsing
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// Display database graphics in a table
function fillGraphicsDisplayDatabaseGraphics(graphics) {
    const container = document.getElementById('databaseGraphicsList');
    if (!container) return;
    
    if (graphics.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666;">No graphics found. Click "Scan DEFAULT ROTATION Folder" to import graphics.</p>';
        return;
    }
    
    let html = `
        <table class="graphics-table" style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr>
                    <th style="width: 30px;"><input type="checkbox" onchange="fillGraphicsToggleSelectAll(this)"></th>
                    <th>File Name</th>
                    <th>Start Date</th>
                    <th>End Date</th>
                    <th>Days Left</th>
                    <th>Status</th>
                    <th>Last Used</th>
                    <th>Used Count</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    graphics.forEach(graphic => {
        const isSelected = fillGraphicsState.selectedGraphicIds.includes(graphic.id);
        const statusClass = graphic.status === 'active' ? 'badge-success' : 
                          graphic.status === 'expired' ? 'badge-danger' : 
                          graphic.status === 'pending' ? 'badge-info' : 
                          graphic.status === 'missing' ? 'badge-warning' : 'badge-secondary';
        
        const daysLeft = graphic.days_remaining !== null ? 
            (graphic.days_remaining > 0 ? `${graphic.days_remaining} days` : 'Expired') : 
            'No limit';
        
        html += `
            <tr class="${isSelected ? 'selected' : ''}">
                <td><input type="checkbox" ${isSelected ? 'checked' : ''} onchange="fillGraphicsToggleSelection(${graphic.id})"></td>
                <td>${graphic.file_name}</td>
                <td>${graphic.start_date ? fillGraphicsFormatDate(graphic.start_date) : '-'}</td>
                <td>${graphic.end_date ? fillGraphicsFormatDate(graphic.end_date) : 'No expiry'}</td>
                <td>${daysLeft}</td>
                <td><span class="badge ${statusClass}">${graphic.status}</span></td>
                <td>${graphic.last_included ? fillGraphicsFormatDate(graphic.last_included) : 'Never'}</td>
                <td>${graphic.include_count || 0}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

// Toggle graphic selection
function fillGraphicsToggleSelection(graphicId) {
    const index = fillGraphicsState.selectedGraphicIds.indexOf(graphicId);
    if (index > -1) {
        fillGraphicsState.selectedGraphicIds.splice(index, 1);
    } else {
        fillGraphicsState.selectedGraphicIds.push(graphicId);
    }
    fillGraphicsDisplayDatabaseGraphics(fillGraphicsState.databaseGraphics);
    fillGraphicsUpdateGenerateButton();  // Update button state
}

// Toggle select all graphics
function fillGraphicsToggleSelectAll(checkbox) {
    if (checkbox.checked) {
        fillGraphicsState.selectedGraphicIds = fillGraphicsState.databaseGraphics.map(g => g.id);
    } else {
        fillGraphicsState.selectedGraphicIds = [];
    }
    fillGraphicsDisplayDatabaseGraphics(fillGraphicsState.databaseGraphics);
    fillGraphicsUpdateGenerateButton();  // Update button state
}

// Delete selected graphics
async function fillGraphicsDeleteSelected() {
    const selectedCount = fillGraphicsState.selectedGraphicIds.length;
    if (selectedCount === 0) {
        window.showNotification('Please select at least one graphic to delete', 'warning');
        return;
    }
    
    // Get selected graphics info
    const selectedGraphics = fillGraphicsState.databaseGraphics.filter(g => 
        fillGraphicsState.selectedGraphicIds.includes(g.id)
    );
    
    const confirmMessage = `Are you sure you want to delete ${selectedCount} graphic${selectedCount > 1 ? 's' : ''}?\n\nThis will permanently remove them from the database.`;
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    try {
        const response = await window.API.post('/default-graphics/batch-delete', {
            ids: fillGraphicsState.selectedGraphicIds
        });
        
        if (response.success) {
            window.showNotification(`Deleted ${response.deleted} graphics successfully`, 'success');
            fillGraphicsState.selectedGraphicIds = [];
            fillGraphicsLoadFromDatabase();
        } else {
            window.showNotification(`Failed to delete graphics: ${response.message}`, 'error');
        }
    } catch (error) {
        console.error('Error deleting graphics:', error);
        window.showNotification(`Failed to delete graphics: ${error.message}`, 'error');
    }
}

// Show date edit modal
function fillGraphicsEditSelectedDates() {
    const selectedCount = fillGraphicsState.selectedGraphicIds.length;
    if (selectedCount === 0) {
        window.showNotification('Please select at least one graphic to edit', 'warning');
        return;
    }
    
    // Update modal with selected graphics info
    const countEl = document.getElementById('selectedGraphicsCount');
    if (countEl) {
        countEl.textContent = `${selectedCount} graphic${selectedCount > 1 ? 's' : ''} selected`;
    }
    
    // Show selected graphics list
    const listEl = document.getElementById('selectedGraphicsList');
    if (listEl) {
        const selectedGraphics = fillGraphicsState.databaseGraphics.filter(g => 
            fillGraphicsState.selectedGraphicIds.includes(g.id)
        );
        listEl.innerHTML = selectedGraphics.map(g => `• ${g.file_name}`).join('<br>');
    }
    
    // Clear form fields
    document.getElementById('editStartDate').value = '';
    document.getElementById('editEndDate').value = '';
    document.getElementById('editGraphicStatus').value = '';
    document.getElementById('editGraphicNotes').value = '';
    
    // Show modal
    document.getElementById('graphicsDateEditModal').style.display = 'block';
}

// Save date edits
async function fillGraphicsSaveDateEdits() {
    const updates = {};
    
    const startDate = document.getElementById('editStartDate').value;
    const endDate = document.getElementById('editEndDate').value;
    const status = document.getElementById('editGraphicStatus').value;
    const notes = document.getElementById('editGraphicNotes').value;
    
    if (startDate) updates.start_date = startDate;
    if (endDate !== '') updates.end_date = endDate || null;
    if (status) updates.status = status;
    if (notes) updates.notes = notes;
    
    if (Object.keys(updates).length === 0) {
        window.showNotification('No changes to save', 'warning');
        return;
    }
    
    try {
        const response = await window.API.post('/default-graphics/batch-update', {
            ids: fillGraphicsState.selectedGraphicIds,
            updates: updates
        });
        
        if (response.success) {
            window.showNotification(response.message, 'success');
            fillGraphicsCloseDateEditModal();
            fillGraphicsLoadFromDatabase();
            fillGraphicsState.selectedGraphicIds = [];
        } else {
            window.showNotification(response.message || 'Failed to update graphics', 'error');
        }
    } catch (error) {
        console.error('Update error:', error);
        window.showNotification('Failed to update graphics', 'error');
    }
}

// Show generation history
async function fillGraphicsShowHistory() {
    try {
        const response = await window.API.get('/default-graphics/history?limit=20');
        
        if (response.success) {
            fillGraphicsDisplayHistory(response.history);
            document.getElementById('graphicsHistoryModal').style.display = 'block';
        }
    } catch (error) {
        console.error('Failed to load history:', error);
        window.showNotification('Failed to load generation history', 'error');
    }
}

// Display generation history
function fillGraphicsDisplayHistory(history) {
    const container = document.getElementById('graphicsHistoryContent');
    if (!container) return;
    
    if (history.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666;">No generation history found.</p>';
        return;
    }
    
    let html = `
        <table class="history-table" style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>File Name</th>
                    <th>Graphics</th>
                    <th>Duration</th>
                    <th>Format</th>
                    <th>Server</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    history.forEach(record => {
        const genDate = new Date(record.generation_date);
        const duration = record.total_duration ? `${Math.floor(record.total_duration / 60)}:${Math.floor(record.total_duration % 60).toString().padStart(2, '0')}` : '-';
        
        html += `
            <tr>
                <td>${genDate.toLocaleString()}</td>
                <td>${record.file_name}</td>
                <td>${record.graphics_count || 0}</td>
                <td>${duration}</td>
                <td>${record.video_format || 'mp4'}</td>
                <td>${record.export_server || '-'}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

// Toggle between database and manual mode
function fillGraphicsToggleView() {
    fillGraphicsState.databaseMode = !fillGraphicsState.databaseMode;
    
    const dbCard = document.getElementById('databaseGraphicsCard');
    const toggleBtn = document.querySelector('.card-header-actions button');
    const region1Card = document.querySelector('.fill-graphics-region1-card');
    
    if (fillGraphicsState.databaseMode) {
        dbCard.style.display = 'block';
        if (region1Card) {
            region1Card.classList.add('fill-graphics-region-hidden');
        }
        toggleBtn.innerHTML = '<i class="fas fa-exchange-alt"></i> Switch to Manual Mode';
        fillGraphicsLoadFromDatabase();
    } else {
        dbCard.style.display = 'none';
        if (region1Card) {
            region1Card.classList.remove('fill-graphics-region-hidden');
        }
        toggleBtn.innerHTML = '<i class="fas fa-exchange-alt"></i> Switch to Database Mode';
    }
    
    // Update generate button state
    fillGraphicsUpdateGenerateButton();
}

// Refresh graphics
function fillGraphicsRefresh() {
    fillGraphicsLoadFromDatabase();
}

// Close modals
function fillGraphicsCloseDateEditModal() {
    document.getElementById('graphicsDateEditModal').style.display = 'none';
}

function fillGraphicsCloseHistoryModal() {
    document.getElementById('graphicsHistoryModal').style.display = 'none';
}

// Function to update video filename based on current settings
function fillGraphicsUpdateVideoFilename() {
    const fileNameInput = document.getElementById('videoFileName');
    const sortOrderSelect = document.getElementById('videoSortOrder');
    const maxLengthInput = document.getElementById('videoMaxLength');
    
    if (fileNameInput && sortOrderSelect && maxLengthInput) {
        const now = new Date();
        const year = (now.getFullYear() % 100).toString().padStart(2, '0');
        const month = (now.getMonth() + 1).toString().padStart(2, '0');
        const day = now.getDate().toString().padStart(2, '0');
        const sortType = sortOrderSelect.value.toUpperCase();
        const duration = maxLengthInput.value;
        fileNameInput.value = `${year}${month}${day}_${sortType}_${duration}`;
    }
}

// Export functions to global scope
window.fillGraphicsUpdateVideoFilename = fillGraphicsUpdateVideoFilename;
window.fillGraphicsInit = fillGraphicsInit;
window.fillGraphicsLoadRegion1Graphics = fillGraphicsLoadRegion1Graphics;
window.fillGraphicsLoadRegion2Graphics = fillGraphicsLoadRegion2Graphics;
window.fillGraphicsLoadMusicFiles = fillGraphicsLoadMusicFiles;
window.fillGraphicsToggleFile = fillGraphicsToggleFile;
window.fillGraphicsSelectAllRegion1Graphics = fillGraphicsSelectAllRegion1Graphics;
window.fillGraphicsDeselectAllRegion1Graphics = fillGraphicsDeselectAllRegion1Graphics;
window.fillGraphicsShowGenerateProjectModal = fillGraphicsShowGenerateProjectModal;
window.fillGraphicsGenerateProjectFile = fillGraphicsGenerateProjectFile;
window.fillGraphicsCloseGenerateProjectModal = fillGraphicsCloseGenerateProjectModal;
window.fillGraphicsShowGenerateVideoModal = fillGraphicsShowGenerateVideoModal;
window.fillGraphicsGenerateVideoFile = fillGraphicsGenerateVideoFile;
window.fillGraphicsCloseGenerateVideoModal = fillGraphicsCloseGenerateVideoModal;

// Export new database functions
window.fillGraphicsScanFolder = fillGraphicsScanFolder;
window.fillGraphicsLoadFromDatabase = fillGraphicsLoadFromDatabase;
window.fillGraphicsToggleSelection = fillGraphicsToggleSelection;
window.fillGraphicsToggleSelectAll = fillGraphicsToggleSelectAll;
window.fillGraphicsEditSelectedDates = fillGraphicsEditSelectedDates;
window.fillGraphicsDeleteSelected = fillGraphicsDeleteSelected;
window.fillGraphicsSaveDateEdits = fillGraphicsSaveDateEdits;
window.fillGraphicsShowHistory = fillGraphicsShowHistory;
window.fillGraphicsToggleView = fillGraphicsToggleView;
window.fillGraphicsRefresh = fillGraphicsRefresh;
window.fillGraphicsCloseDateEditModal = fillGraphicsCloseDateEditModal;
window.fillGraphicsCloseHistoryModal = fillGraphicsCloseHistoryModal;

// Legacy support
window.loadRegion1Graphics = fillGraphicsLoadRegion1Graphics;
window.loadRegion2Graphics = fillGraphicsLoadRegion2Graphics;
window.loadMusicFiles = fillGraphicsLoadMusicFiles;
window.selectAllRegion1Graphics = fillGraphicsSelectAllRegion1Graphics;
window.deselectAllRegion1Graphics = fillGraphicsDeselectAllRegion1Graphics;
window.showGenerateProjectModal = fillGraphicsShowGenerateProjectModal;
window.generateProjectFile = fillGraphicsGenerateProjectFile;
window.closeGenerateProjectModal = fillGraphicsCloseGenerateProjectModal;
window.updateGenerateButton = fillGraphicsUpdateGenerateButton;

// Auto Generation Functions
async function autoGenerationLoadStatus() {
    // Only proceed if we're on a page with auto generation UI
    const autoGenCard = document.querySelector('.auto-generation-card');
    if (!autoGenCard) {
        return; // Silently exit if not on the right page
    }
    
    try {
        const response = await fetch('/api/auto-generation/status');
        const result = await response.json();
        
        if (result.success) {
            const status = result.status;
            
            // Update status display
            const statusEl = document.getElementById('autoGenerationStatus');
            const hostEl = document.getElementById('autoGenerationHost');
            const lastGenEl = document.getElementById('autoGenerationLastGen');
            
            // Determine overall status
            let statusText = 'Inactive';
            let statusClass = 'inactive';
            
            if (!status.is_backend_host) {
                statusText = 'Not Backend Host';
                statusClass = 'error';
            } else if (!status.enabled) {
                statusText = 'Disabled';
                statusClass = 'inactive';
            } else if (!status.current_time_valid) {
                statusText = 'Outside Active Hours';
                statusClass = 'inactive';
            } else {
                statusText = 'Active';
                statusClass = 'active';
            }
            
            statusEl.textContent = statusText;
            statusEl.className = `status-indicator ${statusClass}`;
            
            // Update host info
            hostEl.textContent = `${status.hostname}${status.is_backend_host ? ' (Backend)' : ''}`;
            
            // Update last generation
            if (status.last_generation && status.last_generation.meeting) {
                const genTime = new Date(status.last_generation.time);
                const timeStr = genTime.toLocaleString();
                lastGenEl.textContent = `${status.last_generation.meeting} - ${timeStr}`;
            } else {
                lastGenEl.textContent = 'Never';
            }
            
            // Load config for checkbox
            const configResponse = await fetch('/api/auto-generation/config');
            const configResult = await configResponse.json();
            
            if (configResult.success) {
                const checkbox = document.getElementById('autoGenerationEnabled');
                checkbox.checked = configResult.config.enabled;
                checkbox.disabled = !status.is_backend_host;
                
                // Update toggle text
                const toggleText = document.getElementById('autoGenerationToggleText');
                if (toggleText) {
                    toggleText.textContent = configResult.config.enabled ? 'ON' : 'OFF';
                    toggleText.style.color = configResult.config.enabled ? '#4CAF50' : '#666';
                }
                
                if (!status.is_backend_host) {
                    checkbox.parentElement.title = 'Only available on backend host';
                }
            }
        }
    } catch (error) {
        console.error('Error loading auto generation status:', error);
        // Only show notification if we're on the fill graphics page
        if (document.querySelector('.auto-generation-card')) {
            showNotification('Error loading auto generation status', 'error');
        }
    }
}

async function autoGenerationToggle() {
    try {
        const checkbox = document.getElementById('autoGenerationEnabled');
        const enabled = checkbox.checked;
        
        const response = await fetch('/api/auto-generation/config', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                enabled: enabled
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(`Auto generation ${enabled ? 'enabled' : 'disabled'}`, 'success');
            // Update toggle text
            const toggleText = document.getElementById('autoGenerationToggleText');
            if (toggleText) {
                toggleText.textContent = enabled ? 'ON' : 'OFF';
                toggleText.style.color = enabled ? '#4CAF50' : '#666';
            }
            autoGenerationRefreshStatus();
        } else {
            showNotification('Failed to update auto generation setting', 'error');
            // Revert checkbox
            checkbox.checked = !enabled;
        }
    } catch (error) {
        console.error('Error toggling auto generation:', error);
        showNotification('Error updating auto generation setting', 'error');
        // Revert checkbox
        const checkbox = document.getElementById('autoGenerationEnabled');
        checkbox.checked = !checkbox.checked;
    }
}

function autoGenerationRefreshStatus() {
    autoGenerationLoadStatus();
}

async function autoGenerationShowHistory() {
    try {
        const response = await fetch('/api/auto-generation/history');
        const result = await response.json();
        
        if (result.success) {
            // Create modal content
            let historyHtml = `
                <div class="modal" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000;">
                    <div class="modal-content" style="max-width: 900px; background-color: var(--card-background, #fff); border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <div class="modal-header" style="padding: 20px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center;">
                            <h2 style="margin: 0;">Auto Generation History</h2>
                            <button class="modal-close" onclick="this.closest('.modal').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">&times;</button>
                        </div>
                        <div class="modal-body" style="max-height: 600px; overflow-y: auto; padding: 20px;">
                            <table class="data-table" style="width: 100%; border-collapse: collapse;">
                                <thead>
                                    <tr style="background-color: #f5f5f5;">
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Meeting</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Date</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Time</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Generated</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Status</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Export</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Sort Order</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Duration</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Graphics</th>
                                        <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Video File</th>
                                    </tr>
                                </thead>
                                <tbody>
            `;
            
            if (!result.history || result.history.length === 0) {
                historyHtml += '<tr><td colspan="10" style="text-align: center;">No auto-generated videos yet</td></tr>';
            } else {
                result.history.forEach(item => {
                    const meetingDate = new Date(item.meeting_date);
                    const genTime = new Date(item.generation_timestamp);
                    const statusClass = item.status === 'completed' ? 'success' : 
                                      item.status === 'failed' ? 'danger' : 'warning';
                    
                    historyHtml += `
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.meeting_name}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${meetingDate.toLocaleDateString()}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.start_time}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${genTime.toLocaleString()}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;"><span class="badge badge-${statusClass}" style="padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; background-color: ${statusClass === 'success' ? '#d4edda' : statusClass === 'danger' ? '#f8d7da' : '#fff3cd'}; color: ${statusClass === 'success' ? '#155724' : statusClass === 'danger' ? '#721c24' : '#856404'};">${item.status}</span></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${formatExportStatus(item)}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.sort_order || '-'}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.duration_seconds ? formatDuration(item.duration_seconds) : '-'}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.graphics_count || '-'}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;" ${item.file_path ? `title="${item.file_path}"` : ''}>${item.video_file_name || '-'}</td>
                        </tr>
                    `;
                    
                    if (item.error_message) {
                        historyHtml += `
                            <tr>
                                <td colspan="10" class="error-message">
                                    <small>Error: ${item.error_message}</small>
                                </td>
                            </tr>
                        `;
                    }
                });
            }
            
            historyHtml += `
                                </tbody>
                            </table>
                        </div>
                        <div class="modal-footer" style="padding: 20px; border-top: 1px solid #ddd; text-align: right;">
                            <button class="button secondary" onclick="this.closest('.modal').remove()">Close</button>
                        </div>
                    </div>
                </div>
            `;
            
            // Remove any existing modal first
            const existingModal = document.querySelector('.modal');
            if (existingModal) {
                existingModal.remove();
            }
            
            document.body.insertAdjacentHTML('beforeend', historyHtml);
        } else {
            console.error('Failed to load history:', result.error || 'Unknown error');
            showNotification('Failed to load generation history', 'error');
        }
    } catch (error) {
        console.error('Error loading auto generation history:', error);
        showNotification('Error loading history', 'error');
    }
}

function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function formatExportStatus(item) {
    let status = '';
    
    // Check source export
    if (item.source_export_status === 'success') {
        status += '<span style="color: #28a745; font-weight: 600;">✓ Source</span>';
    } else if (item.source_export_status === 'failed') {
        status += '<span style="color: #dc3545; font-weight: 600;">✗ Source</span>';
    } else if (item.source_export_status === 'pending') {
        status += '<span style="color: #ffc107; font-weight: 600;">⏳ Source</span>';
    }
    
    // Add separator if both statuses exist
    if (item.source_export_status !== 'skipped' && item.target_export_status !== 'skipped') {
        status += '<br>';
    }
    
    // Check target export
    if (item.target_export_status === 'success') {
        status += '<span style="color: #28a745; font-weight: 600;">✓ Target</span>';
    } else if (item.target_export_status === 'failed') {
        status += '<span style="color: #dc3545; font-weight: 600;">✗ Target</span>';
    } else if (item.target_export_status === 'pending') {
        status += '<span style="color: #ffc107; font-weight: 600;">⏳ Target</span>';
    }
    
    // If no exports, show none
    if (!status) {
        status = '<span style="color: #6c757d;">None</span>';
    }
    
    return status;
}

// Export auto generation functions
window.autoGenerationToggle = autoGenerationToggle;
window.autoGenerationRefreshStatus = autoGenerationRefreshStatus;
window.autoGenerationShowHistory = autoGenerationShowHistory;

// Load status when module initializes
if (document.querySelector('.auto-generation-card')) {
    autoGenerationLoadStatus();
    
    // Make the auto generation card collapsible
    const autoGenHeader = document.querySelector('.auto-generation-card .card-header h3');
    if (autoGenHeader) {
        autoGenHeader.addEventListener('click', function() {
            const card = this.closest('.auto-generation-card');
            card.classList.toggle('collapsed');
        });
    }
}