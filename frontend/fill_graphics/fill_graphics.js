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
    canGenerate: false
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
    console.log(`  Region 1 selected: ${fillGraphicsState.region1.selected.length} files`);
    console.log(`  Region 2 selected: ${fillGraphicsState.region2.selected}`);
    console.log(`  Region 3 selected: ${fillGraphicsState.region3.selected.length} files`);
    
    const canGenerate = 
        fillGraphicsState.region1.selected.length > 0 &&
        fillGraphicsState.region2.selected !== null &&
        fillGraphicsState.region3.selected.length > 0;
    
    console.log(`  Can generate: ${canGenerate}`);
    
    fillGraphicsState.canGenerate = canGenerate;
    
    const button = document.getElementById('generateProjectBtn');
    if (button) {
        console.log(`  Button found, setting disabled to: ${!canGenerate}`);
        button.disabled = !canGenerate;
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
        const requestData = {
            project_name: projectName,
            export_path: pathInput.value,
            export_server: serverSelect.value,
            slide_duration: slideDuration,
            region1_files: fillGraphicsState.region1.selected,
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

// Format file size
function fillGraphicsFormatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Export functions to global scope
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