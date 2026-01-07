// Meeting Promos Management JavaScript

const API_BASE = 'http://127.0.0.1:5000/api';

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

// State
let currentPromos = [];
let selectedFile = null;
let sortable = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeTheme();
    loadSettings();
    loadPromos();
    setupEventListeners();
    initializeSortable();
});

// Load settings from backend
async function loadSettings() {
    try {
        const response = await fetch(`${API_BASE}/meeting-promos/settings`);
        const data = await response.json();
        
        if (data.success && data.settings) {
            document.getElementById('prePromoEnabled').checked = data.settings.pre_meeting_enabled;
            document.getElementById('postPromoEnabled').checked = data.settings.post_meeting_enabled;
            document.getElementById('preDurationLimit').value = data.settings.pre_meeting_duration_limit || 300;
            document.getElementById('postDurationLimit').value = data.settings.post_meeting_duration_limit || 300;
        }
    } catch (error) {
        console.error('Error loading settings:', error);
        showMessage('Error loading settings', 'error');
    }
}

// Save settings
async function saveSettings() {
    const settings = {
        pre_meeting_enabled: document.getElementById('prePromoEnabled').checked,
        post_meeting_enabled: document.getElementById('postPromoEnabled').checked,
        pre_meeting_duration_limit: parseInt(document.getElementById('preDurationLimit').value),
        post_meeting_duration_limit: parseInt(document.getElementById('postDurationLimit').value)
    };
    
    try {
        const response = await fetch(`${API_BASE}/meeting-promos/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Settings saved successfully', 'success');
        } else {
            showMessage('Error saving settings: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showMessage('Error saving settings', 'error');
    }
}

// Load promos
async function loadPromos() {
    const filters = {
        type: document.querySelector('input[name="promoFilter"]:checked').value,
        active_only: !document.getElementById('showInactive').checked,
        include_expired: document.getElementById('showExpired').checked
    };
    
    const params = new URLSearchParams();
    if (filters.type !== 'all') params.append('type', filters.type);
    params.append('active_only', filters.active_only);
    params.append('include_expired', filters.include_expired);
    
    try {
        const response = await fetch(`${API_BASE}/meeting-promos?${params}`);
        const data = await response.json();
        
        if (data.success) {
            currentPromos = data.promos;
            renderPromos();
        }
    } catch (error) {
        console.error('Error loading promos:', error);
        showMessage('Error loading promos', 'error');
    }
}

// Render promos table
function renderPromos() {
    const tbody = document.getElementById('promosTableBody');
    tbody.innerHTML = '';
    
    const filterType = document.querySelector('input[name="promoFilter"]:checked').value;
    let filteredPromos = currentPromos;
    
    if (filterType !== 'all') {
        filteredPromos = currentPromos.filter(p => p.promo_type === filterType);
    }
    
    filteredPromos.forEach((promo, index) => {
        const tr = document.createElement('tr');
        tr.dataset.promoId = promo.id;
        
        const now = new Date();
        const goLive = promo.go_live_date ? new Date(promo.go_live_date) : null;
        const expiration = promo.expiration_date ? new Date(promo.expiration_date) : null;
        
        let status = 'active';
        if (!promo.is_active) {
            status = 'inactive';
        } else if (expiration && expiration < now) {
            status = 'expired';
        } else if (goLive && goLive > now) {
            status = 'pending';
        }
        
        tr.innerHTML = `
            <td class="drag-handle">☰</td>
            <td>${promo.file_name}</td>
            <td>${promo.promo_type === 'pre' ? 'Pre-Meeting' : 'Post-Meeting'}</td>
            <td>${promo.duration_seconds}s</td>
            <td>${promo.go_live_date || '-'}</td>
            <td>${promo.expiration_date || '-'}</td>
            <td><span class="status-badge ${status}">${status}</span></td>
            <td class="action-buttons">
                <button class="btn-small btn-edit" onclick="editPromo(${promo.id})">Edit</button>
                <button class="btn-small btn-toggle" onclick="togglePromo(${promo.id})">
                    ${promo.is_active ? 'Disable' : 'Enable'}
                </button>
                <button class="btn-small btn-delete" onclick="deletePromo(${promo.id})">Delete</button>
            </td>
        `;
        
        tbody.appendChild(tr);
    });
}

// Add promo from modal
async function addPromoFromModal() {
    if (!selectedFile) {
        showMessage('Please select content', 'error');
        return;
    }
    
    const promoData = {
        file_path: selectedFile.path,
        file_name: selectedFile.name,
        promo_type: document.getElementById('modalPromoType').value,
        duration_seconds: selectedFile.duration,
        go_live_date: document.getElementById('modalGoLiveDate').value || null,
        expiration_date: document.getElementById('modalExpirationDate').value || null,
        notes: document.getElementById('modalPromoNotes').value,
        is_active: true
    };
    
    try {
        const response = await fetch(`${API_BASE}/meeting-promos`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(promoData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Promo added successfully', 'success');
            closeFileBrowser();
            loadPromos();
        } else {
            showMessage('Error adding promo: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error adding promo:', error);
        showMessage('Error adding promo', 'error');
    }
}

// Edit promo
function editPromo(promoId) {
    const promo = currentPromos.find(p => p.id === promoId);
    if (!promo) return;
    
    document.getElementById('editPromoId').value = promo.id;
    document.getElementById('editFileName').value = promo.file_name;
    document.getElementById('editPromoType').value = promo.promo_type;
    document.getElementById('editDuration').value = promo.duration_seconds;
    document.getElementById('editGoLiveDate').value = promo.go_live_date || '';
    document.getElementById('editExpirationDate').value = promo.expiration_date || '';
    document.getElementById('editNotes').value = promo.notes || '';
    
    document.getElementById('editModal').style.display = 'flex';
}

// Save promo edits
async function savePromoEdits(e) {
    e.preventDefault();
    
    const promoId = document.getElementById('editPromoId').value;
    const updates = {
        promo_type: document.getElementById('editPromoType').value,
        duration_seconds: parseInt(document.getElementById('editDuration').value),
        go_live_date: document.getElementById('editGoLiveDate').value || null,
        expiration_date: document.getElementById('editExpirationDate').value || null,
        notes: document.getElementById('editNotes').value
    };
    
    try {
        const response = await fetch(`${API_BASE}/meeting-promos/${promoId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Promo updated successfully', 'success');
            document.getElementById('editModal').style.display = 'none';
            loadPromos();
        } else {
            showMessage('Error updating promo: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error updating promo:', error);
        showMessage('Error updating promo', 'error');
    }
}

// Toggle promo active status
async function togglePromo(promoId) {
    try {
        const response = await fetch(`${API_BASE}/meeting-promos/${promoId}/toggle`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Promo toggled successfully', 'success');
            loadPromos();
        } else {
            showMessage('Error toggling promo: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error toggling promo:', error);
        showMessage('Error toggling promo', 'error');
    }
}

// Delete promo
async function deletePromo(promoId) {
    if (!confirm('Are you sure you want to delete this promo?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/meeting-promos/${promoId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('Promo deleted successfully', 'success');
            loadPromos();
        } else {
            showMessage('Error deleting promo: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error deleting promo:', error);
        showMessage('Error deleting promo', 'error');
    }
}

// State for file browser
let availableContent = [];
let contentSearchTimeout = null;

// Open file browser
async function openFileBrowser() {
    const modal = document.getElementById('fileBrowserModal');
    
    // Reset selection
    selectedFile = null;
    document.getElementById('selectedContentDetails').style.display = 'none';
    
    // Clear form fields
    document.getElementById('modalGoLiveDate').value = '';
    document.getElementById('modalExpirationDate').value = '';
    document.getElementById('modalPromoNotes').value = '';
    
    // Load content
    loadAvailableContent();
    
    modal.style.display = 'flex';
}

// Load available content from API
async function loadAvailableContent() {
    const searchTerm = document.getElementById('contentSearch').value;
    const contentType = document.getElementById('contentTypeFilter').value;
    const container = document.getElementById('fileBrowserContent');
    
    // Show loading indicator
    container.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading content...</div>';
    
    try {
        const params = new URLSearchParams();
        if (searchTerm) params.append('search', searchTerm);
        if (contentType !== 'all') params.append('type', contentType);
        params.append('limit', '200');
        
        const response = await fetch(`${API_BASE}/meeting-promos/available-content?${params}`);
        const data = await response.json();
        
        if (data.success) {
            availableContent = data.content || [];
            renderContentList();
        } else {
            container.innerHTML = '<div class="error-message">Error loading content: ' + (data.message || 'Unknown error') + '</div>';
            showMessage('Error loading content: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error loading content:', error);
        container.innerHTML = '<div class="error-message">Error loading content. Please try again.</div>';
        showMessage('Error loading content', 'error');
    }
}

// Render content list
function renderContentList() {
    const container = document.getElementById('fileBrowserContent');
    
    if (availableContent.length === 0) {
        container.innerHTML = '<div class="no-content">No content found</div>';
        return;
    }
    
    container.innerHTML = availableContent.map(item => {
        // Format duration
        const duration = item.duration_seconds || item.file_duration || 0;
        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;
        const durationDisplay = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        
        return `
        <div class="file-item" data-id="${item.id}">
            <div class="file-item-info">
                <div class="file-item-name">${item.display_name || item.file_name}</div>
                <div class="file-item-meta">
                    <span><i class="fas fa-film"></i> ${item.content_type || 'Unknown'}</span>
                    <span><i class="fas fa-clock"></i> ${durationDisplay}</span>
                </div>
            </div>
        </div>
    `;
    }).join('');
    
    // Add click handlers
    container.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('click', () => selectContent(item.dataset.id));
    });
}

// Select content
function selectContent(contentId) {
    const content = availableContent.find(c => c.id == contentId);
    if (!content) return;
    
    // Update selection
    document.querySelectorAll('.file-item').forEach(item => {
        item.classList.remove('selected');
    });
    document.querySelector(`.file-item[data-id="${contentId}"]`).classList.add('selected');
    
    // Get duration in seconds
    const durationSeconds = content.duration_seconds || content.file_duration || 0;
    
    selectedFile = {
        id: content.id,
        name: content.file_name,
        path: content.file_path,
        duration: durationSeconds
    };
    
    // Format duration for display
    const minutes = Math.floor(durationSeconds / 60);
    const seconds = durationSeconds % 60;
    const durationDisplay = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    
    // Show details
    document.getElementById('selectedContentName').textContent = content.display_name || content.file_name;
    document.getElementById('selectedContentDuration').textContent = durationDisplay;
    document.getElementById('selectedContentDetails').style.display = 'block';
}

// Close file browser
function closeFileBrowser() {
    document.getElementById('fileBrowserModal').style.display = 'none';
    
    // Reset selection
    selectedFile = null;
}


// Initialize sortable
function initializeSortable() {
    const tbody = document.getElementById('promosTableBody');
    
    if (typeof Sortable !== 'undefined') {
        sortable = Sortable.create(tbody, {
            handle: '.drag-handle',
            animation: 150,
            onEnd: async function(evt) {
                const rows = tbody.querySelectorAll('tr');
                const promoIds = Array.from(rows).map(row => parseInt(row.dataset.promoId));
                
                try {
                    const response = await fetch(`${API_BASE}/meeting-promos/sort`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ promo_ids: promoIds })
                    });
                    
                    const data = await response.json();
                    
                    if (!data.success) {
                        showMessage('Error updating sort order', 'error');
                        loadPromos(); // Reload to restore original order
                    }
                } catch (error) {
                    console.error('Error updating sort order:', error);
                    showMessage('Error updating sort order', 'error');
                    loadPromos();
                }
            }
        });
    }
}

// Setup event listeners
function setupEventListeners() {
    // Settings
    document.getElementById('saveSettingsBtn').addEventListener('click', saveSettings);
    
    // Add promo
    document.getElementById('selectFileBtn').addEventListener('click', openFileBrowser);
    
    // File browser controls
    document.getElementById('contentSearch').addEventListener('input', () => {
        clearTimeout(contentSearchTimeout);
        contentSearchTimeout = setTimeout(loadAvailableContent, 300);
    });
    document.getElementById('contentTypeFilter').addEventListener('change', loadAvailableContent);
    
    // File browser buttons
    document.getElementById('confirmAddPromo').addEventListener('click', addPromoFromModal);
    document.getElementById('cancelAddPromo').addEventListener('click', closeFileBrowser);
    
    // Filters
    document.querySelectorAll('input[name="promoFilter"]').forEach(radio => {
        radio.addEventListener('change', loadPromos);
    });
    document.getElementById('showInactive').addEventListener('change', loadPromos);
    document.getElementById('showExpired').addEventListener('change', loadPromos);
    
    // Edit modal
    document.getElementById('editPromoForm').addEventListener('submit', savePromoEdits);
    document.getElementById('cancelEditBtn').addEventListener('click', () => {
        document.getElementById('editModal').style.display = 'none';
    });
    
    // Modal close buttons
    document.querySelectorAll('.modal .close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').style.display = 'none';
        });
    });
    
    // Click outside modal to close
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            e.target.style.display = 'none';
        }
    });
}

// Show status message
function showMessage(message, type) {
    const statusDiv = document.getElementById('statusMessage');
    statusDiv.textContent = message;
    statusDiv.className = 'status-message ' + type;
    statusDiv.style.display = 'block';
    
    setTimeout(() => {
        statusDiv.style.display = 'none';
    }, 3000);
}

// Load Sortable.js library
(function() {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js';
    document.head.appendChild(script);
})();