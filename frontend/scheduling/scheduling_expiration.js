/**
 * Scheduling Content Expiration Module
 * Handles content expiration dates and shelf life management
 */

// Expiration State
const schedulingExpirationState = {
    shelfLifeSettings: {
        'AN': { short: 7, medium: 14, long: 30 },
        'BMP': { short: 30, medium: 60, long: 90 },
        'IMOW': { short: 90, medium: 180, long: 365 },
        'IM': { short: 90, medium: 180, long: 365 },
        'IA': { short: 30, medium: 60, long: 90 },
        'LM': { short: 7, medium: 14, long: 30 },
        'MTG': { short: 180, medium: 365, long: 730 },
        'MAF': { short: 30, medium: 60, long: 90 },
        'PKG': { short: 30, medium: 60, long: 90 },
        'PMO': { short: 7, medium: 14, long: 30 },
        'PSA': { short: 30, medium: 60, long: 90 },
        'SZL': { short: 7, medium: 14, long: 30 },
        'SPP': { short: 90, medium: 180, long: 365 },
        'OTHER': { short: 30, medium: 60, long: 90 }
    },
    contentTypeLabels: {
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
    },
    expirationStats: {
        active: 0,
        expired: 0,
        total: 0
    }
};

// Initialize Expiration Module
function schedulingExpirationInit() {
    console.log('Initializing Scheduling Expiration module...');
    
    // Load saved shelf life settings if available
    schedulingLoadShelfLifeSettings();
    
    // Store the original display function
    let originalDisplayAvailableContent = null;
    
    // TEMPORARILY DISABLED - Override displayAvailableContent after a delay to ensure it's defined
    // setTimeout(() => {
    //     if (window.displayAvailableContent && !originalDisplayAvailableContent) {
    //         originalDisplayAvailableContent = window.displayAvailableContent;
    //         window.displayAvailableContent = function() {
    //             try {
    //                 // Try to use our enhanced version
    //                 schedulingDisplayAvailableContentWithExpiration.call(this);
    //             } catch (error) {
    //                 console.error('Error in enhanced display, falling back to original:', error);
    //                 // Fall back to original if there's an error
    //                 if (originalDisplayAvailableContent) {
    //                     originalDisplayAvailableContent.call(this);
    //                 }
    //             }
    //         };
    //         console.log('Successfully overrode displayAvailableContent');
    //         
    //         // If content is already loaded, display it with the new function
    //         if (window.availableContent && window.availableContent.length > 0) {
    //             console.log('Content already loaded, displaying with expiration view');
    //             window.displayAvailableContent();
    //         }
    //     }
    // }, 500); // Increased delay to ensure everything is loaded
}

// Load shelf life settings from localStorage
function schedulingLoadShelfLifeSettings() {
    try {
        const saved = localStorage.getItem('shelfLifeSettings');
        if (saved) {
            schedulingExpirationState.shelfLifeSettings = JSON.parse(saved);
        }
    } catch (e) {
        console.error('Error loading shelf life settings:', e);
    }
}

// Save shelf life settings to localStorage
function schedulingSaveShelfLifeSettings() {
    try {
        localStorage.setItem('shelfLifeSettings', JSON.stringify(schedulingExpirationState.shelfLifeSettings));
    } catch (e) {
        console.error('Error saving shelf life settings:', e);
    }
}

// Display available content with expiration dates instead of last scheduled
function schedulingDisplayAvailableContentWithExpiration() {
    console.log('schedulingDisplayAvailableContentWithExpiration called');
    const contentList = document.getElementById('availableContentList');
    
    if (!contentList) {
        console.error('availableContentList element not found');
        return;
    }
    
    console.log('Available content:', window.availableContent);
    
    // Update the count display
    const countElement = document.getElementById('contentCount');
    if (countElement && window.availableContent) {
        countElement.textContent = `(${window.availableContent.length} items)`;
    }
    
    if (!window.availableContent || window.availableContent.length === 0) {
        contentList.innerHTML = '<p>No content matches the current filters</p>';
        return;
    }
    
    // Check if helper functions exist
    const getSortIconFunc = window.getSortIcon || function(field) { return ''; };
    
    // Add sort header with Expiration column
    let html = `
        <div class="content-header">
            <span class="sort-field" data-field="title" onclick="sortContent('title')">
                Title ${getSortIconFunc('title')}
            </span>
            <span class="sort-field" data-field="type" onclick="sortContent('type')">
                Type ${getSortIconFunc('type')}
            </span>
            <span class="sort-field" data-field="duration" onclick="sortContent('duration')">
                Duration ${getSortIconFunc('duration')}
            </span>
            <span class="sort-field" data-field="engagement" onclick="sortContent('engagement')">
                Score ${getSortIconFunc('engagement')}
            </span>
            <span class="sort-field" data-field="expiration" onclick="schedulingSortByExpiration()">
                Expiration ${getSortIconFunc('expiration')}
            </span>
            <span style="text-align: center;">Actions</span>
        </div>
    `;
    
    // Check if helper functions exist
    const getContentTypeLabelFunc = window.getContentTypeLabel || function(type) { return type || 'Unknown'; };
    const formatDurationTimecodeFunc = window.formatDurationTimecode || function(duration) { 
        const hours = Math.floor(duration / 3600);
        const minutes = Math.floor((duration % 3600) / 60);
        const seconds = Math.floor(duration % 60);
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    };
    const getDurationCategoryFunc = window.getDurationCategory || function(duration) {
        if (duration < 900) return 'short';
        if (duration < 1800) return 'medium';
        if (duration < 3600) return 'long';
        return 'extra_long';
    };
    
    // Display each content item with expiration
    window.availableContent.forEach(content => {
        const contentId = content.id || content._id || content.guid;
        const contentTypeLabel = getContentTypeLabelFunc(content.content_type);
        const durationTimecode = formatDurationTimecodeFunc(content.file_duration);
        const durationCategory = getDurationCategoryFunc(content.file_duration);
        const engagementScore = content.engagement_score || 'N/A';
        
        // Format expiration date
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
        
        // Check if it's in current template
        const isInTemplate = window.currentTemplate && window.currentTemplate.items && 
            window.currentTemplate.items.some(item => {
                const itemId = item.id || item._id || item.guid || item.asset_id;
                return itemId == contentId || itemId === contentId || 
                       String(itemId) === String(contentId);
            });
        
        html += `
            <div class="content-item ${isInTemplate ? 'in-template' : ''}" data-content-id="${contentId}">
                <span class="content-title" title="${content.file_name}">${content.title || content.content_title || content.file_name || 'Untitled'}</span>
                <span class="content-type">${contentTypeLabel}</span>
                <span class="duration-category ${durationCategory.toLowerCase()}">${durationTimecode}</span>
                <span class="engagement-score">${engagementScore}%</span>
                <span class="expiration-date ${expirationClass}">${expirationDisplay}</span>
                <span class="content-actions">
                    <button class="button primary small" onclick="viewContentDetails('${contentId}')" title="View details">
                        <i class="fas fa-info"></i>
                    </button>
                    ${isInTemplate ? 
                        `<button class="button secondary small" disabled title="Already in template">
                            <i class="fas fa-check"></i>
                        </button>` :
                        `<button class="button success small" onclick="addToTemplate('${contentId}')" title="Add to template">
                            <i class="fas fa-plus"></i>
                        </button>`
                    }
                </span>
            </div>
        `;
    });
    
    contentList.innerHTML = html;
}

// Sort content by expiration date
function schedulingSortByExpiration() {
    if (!window.availableContent) return;
    
    // Toggle sort direction
    if (!window.contentSortField || window.contentSortField !== 'expiration') {
        window.contentSortField = 'expiration';
        window.contentSortDirection = 'asc';
    } else {
        window.contentSortDirection = window.contentSortDirection === 'asc' ? 'desc' : 'asc';
    }
    
    window.availableContent.sort((a, b) => {
        const aExpiry = a.scheduling?.content_expiry_date ? new Date(a.scheduling.content_expiry_date).getTime() : Number.MAX_SAFE_INTEGER;
        const bExpiry = b.scheduling?.content_expiry_date ? new Date(b.scheduling.content_expiry_date).getTime() : Number.MAX_SAFE_INTEGER;
        
        if (window.contentSortDirection === 'asc') {
            return aExpiry - bExpiry;
        } else {
            return bExpiry - aExpiry;
        }
    });
    
    schedulingDisplayAvailableContentWithExpiration();
}

// Show the content expiration modal
function schedulingShowExpirationModal() {
    const modal = document.getElementById('contentExpirationModal');
    if (!modal) {
        console.error('Content expiration modal not found');
        return;
    }
    
    // Populate the shelf life grid with current settings
    schedulingPopulateShelfLifeGrid();
    
    modal.style.display = 'block';
}

// Close the content expiration modal
function schedulingCloseExpirationModal() {
    const modal = document.getElementById('contentExpirationModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Populate the shelf life grid in the modal
function schedulingPopulateShelfLifeGrid() {
    const gridContainer = document.getElementById('shelfLifeGrid');
    if (!gridContainer) return;
    
    let html = `
        <div class="scheduling-shelf-life-grid">
            <div class="scheduling-grid-header">
                <div></div>
                <div>Short</div>
                <div>Medium</div>
                <div>Long</div>
            </div>
    `;
    
    const contentTypes = Object.keys(schedulingExpirationState.contentTypeLabels);
    
    contentTypes.forEach(contentType => {
        const label = schedulingExpirationState.contentTypeLabels[contentType];
        const settings = schedulingExpirationState.shelfLifeSettings[contentType] || { short: 30, medium: 60, long: 90 };
        
        html += `
            <div class="scheduling-grid-row">
                <div class="scheduling-grid-label">${label}</div>
                <div><input type="number" id="shelf_${contentType}_short" value="${settings.short}" min="1" max="9999" class="scheduling-days-input"> days</div>
                <div><input type="number" id="shelf_${contentType}_medium" value="${settings.medium}" min="1" max="9999" class="scheduling-days-input"> days</div>
                <div><input type="number" id="shelf_${contentType}_long" value="${settings.long}" min="1" max="9999" class="scheduling-days-input"> days</div>
            </div>
        `;
    });
    
    html += '</div>';
    gridContainer.innerHTML = html;
}

// Save shelf life settings from the modal
function schedulingSaveShelfLifeFromModal() {
    const contentTypes = Object.keys(schedulingExpirationState.contentTypeLabels);
    const shelfLifeTypes = ['short', 'medium', 'long'];
    
    contentTypes.forEach(contentType => {
        shelfLifeTypes.forEach(type => {
            const input = document.getElementById(`shelf_${contentType}_${type}`);
            if (input) {
                if (!schedulingExpirationState.shelfLifeSettings[contentType]) {
                    schedulingExpirationState.shelfLifeSettings[contentType] = {};
                }
                schedulingExpirationState.shelfLifeSettings[contentType][type] = parseInt(input.value) || 1;
            }
        });
    });
    
    schedulingSaveShelfLifeSettings();
    
    if (window.showNotification) {
        window.showNotification('Shelf life settings saved', 'success');
    }
}

// Calculate and set content expiration dates based on encode date and shelf life
async function schedulingSetContentExpiration() {
    try {
        // First save the shelf life settings
        schedulingSaveShelfLifeFromModal();
        
        const response = await fetch('http://127.0.0.1:5000/api/set-content-expiration', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                shelf_life_settings: schedulingExpirationState.shelfLifeSettings
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            if (window.showNotification) {
                window.showNotification(`Updated expiration dates for ${result.updated_count} content items`, 'success');
            }
            
            // Reload available content to show new expiration dates
            if (window.loadAvailableContent) {
                window.loadAvailableContent();
            }
            
            schedulingCloseExpirationModal();
        } else {
            if (window.showNotification) {
                window.showNotification(`Failed to set expiration dates: ${result.message}`, 'error');
            }
        }
    } catch (error) {
        console.error('Error setting content expiration:', error);
        if (window.showNotification) {
            window.showNotification('Error setting content expiration', 'error');
        }
    }
}

// Get active and expired content counts
async function schedulingGetContentCounts() {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/content-expiration-stats');
        const result = await response.json();
        
        if (result.success) {
            schedulingExpirationState.expirationStats = result.stats;
            
            // Display the stats
            const statsHtml = `
                <div class="scheduling-expiration-stats">
                    <h3>Content Expiration Statistics</h3>
                    <div class="scheduling-stats-grid">
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Total Content</div>
                            <div class="scheduling-stat-value total">${result.stats.total}</div>
                        </div>
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Total Hours</div>
                            <div class="scheduling-stat-value total">${result.stats.total_hours || 0}h</div>
                        </div>
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Active Content</div>
                            <div class="scheduling-stat-value active">${result.stats.active}</div>
                        </div>
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Active Hours</div>
                            <div class="scheduling-stat-value active">${result.stats.active_hours || 0}h</div>
                        </div>
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Expired Content</div>
                            <div class="scheduling-stat-value expired">${result.stats.expired}</div>
                        </div>
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Expired Hours</div>
                            <div class="scheduling-stat-value expired">${result.stats.expired_hours || 0}h</div>
                        </div>
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Expiring Soon (7 days)</div>
                            <div class="scheduling-stat-value warning">${result.stats.expiring_soon || 0}</div>
                        </div>
                        <div class="scheduling-stat-item">
                            <div class="scheduling-stat-label">Days of Content</div>
                            <div class="scheduling-stat-value info">${(result.stats.total_hours / 24).toFixed(1)}d</div>
                        </div>
                    </div>
                </div>
            `;
            
            // Show in a modal or update a stats container
            const statsContainer = document.getElementById('expirationStatsContainer');
            if (statsContainer) {
                statsContainer.innerHTML = statsHtml;
                statsContainer.style.display = 'block';
            } else {
                // Create a simple modal to show stats
                const modalHtml = `
                    <div class="modal" id="expirationStatsModal" style="display: block;">
                        <div class="modal-content" style="max-width: 500px;">
                            <div class="modal-header">
                                <h3>Content Expiration Statistics</h3>
                                <button class="modal-close" onclick="document.getElementById('expirationStatsModal').remove()">&times;</button>
                            </div>
                            <div class="modal-body">
                                ${statsHtml}
                            </div>
                            <div class="modal-footer">
                                <button class="button secondary" onclick="document.getElementById('expirationStatsModal').remove()">Close</button>
                            </div>
                        </div>
                    </div>
                `;
                document.body.insertAdjacentHTML('beforeend', modalHtml);
            }
        } else {
            if (window.showNotification) {
                window.showNotification(`Failed to get expiration stats: ${result.message}`, 'error');
            }
        }
    } catch (error) {
        console.error('Error getting content counts:', error);
        if (window.showNotification) {
            window.showNotification('Error getting content statistics', 'error');
        }
    }
}

// Clear all expiration dates
async function schedulingClearAllExpirations() {
    if (!confirm('Are you sure you want to clear ALL expiration dates? This will make all content permanently available.')) {
        return;
    }
    
    try {
        const response = await fetch('http://127.0.0.1:5000/api/clear-content-expirations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            if (window.showNotification) {
                window.showNotification(`Cleared expiration dates for ${result.cleared_count} content items`, 'success');
            }
            
            // Reload available content to show updated state
            if (window.loadAvailableContent) {
                window.loadAvailableContent();
            }
            
            schedulingCloseExpirationModal();
        } else {
            if (window.showNotification) {
                window.showNotification(`Failed to clear expiration dates: ${result.message}`, 'error');
            }
        }
    } catch (error) {
        console.error('Error clearing expiration dates:', error);
        if (window.showNotification) {
            window.showNotification('Error clearing expiration dates', 'error');
        }
    }
}

// Export functions to global scope
window.schedulingExpirationInit = schedulingExpirationInit;
window.schedulingShowExpirationModal = schedulingShowExpirationModal;
window.schedulingCloseExpirationModal = schedulingCloseExpirationModal;
window.schedulingSetContentExpiration = schedulingSetContentExpiration;
window.schedulingGetContentCounts = schedulingGetContentCounts;
window.schedulingSortByExpiration = schedulingSortByExpiration;
window.schedulingDisplayAvailableContentWithExpiration = schedulingDisplayAvailableContentWithExpiration;
window.schedulingClearAllExpirations = schedulingClearAllExpirations;

// Initialize when loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedulingExpirationInit);
} else {
    schedulingExpirationInit();
}