// Content type filter functions for dashboard

// Content type filter for scanned files
function filterScannedFilesByContentType() {
    const filterValue = document.getElementById('scannedFilesContentTypeFilter').value;
    const sourceFilesList = document.getElementById('sourceFilesList');
    const targetFilesList = document.getElementById('targetFilesList');
    
    filterFileListByContentType(sourceFilesList, filterValue);
    filterFileListByContentType(targetFilesList, filterValue);
    
    // If search is active, reapply search with new filter
    const searchInput = document.getElementById('scannedFilesSearchInput');
    if (searchInput && searchInput.value) {
        searchScannedFiles();
    }
}

// Content type filter for comparison results
function filterComparisonByContentType() {
    // Re-render comparison results which will apply the content type filter
    if (typeof renderComparisonResults === 'function') {
        renderComparisonResults();
    }
}

// Helper function to filter file lists by content type
function filterFileListByContentType(container, contentType) {
    if (!container) return;
    
    // Handle both file-item (comparison) and scanned-file-item (scanned files)
    const fileItems = container.querySelectorAll('.file-item, .scanned-file-item');
    let visibleCount = 0;
    
    fileItems.forEach(item => {
        const fileName = item.querySelector('.file-name')?.textContent || '';
        
        if (!contentType) {
            // Show all files if no filter selected
            item.style.display = '';
            visibleCount++;
        } else {
            // Check if filename contains the content type pattern
            const pattern = `_${contentType}_`;
            if (fileName.includes(pattern)) {
                item.style.display = '';
                visibleCount++;
            } else {
                item.style.display = 'none';
            }
        }
    });
    
    // Update file counts if they exist
    const parentSection = container.closest('.dashboard-scanned-files-section, .scanned-files-section');
    if (parentSection) {
        const fileCount = parentSection.querySelector('.dashboard-file-count, .file-count');
        if (fileCount && contentType) {
            const originalText = fileCount.textContent;
            const match = originalText.match(/(\d+) files? found/);
            if (match) {
                fileCount.textContent = `${visibleCount} files shown (filtered from ${match[1]})`;
            }
        } else if (fileCount && !contentType) {
            // Restore original count when filter is cleared
            const match = fileCount.textContent.match(/filtered from (\d+)/);
            if (match) {
                fileCount.textContent = `${match[1]} files found`;
            }
        }
    }
}

// Search functionality for scanned files
function searchScannedFiles() {
    const searchInput = document.getElementById('scannedFilesSearchInput');
    const searchTerm = searchInput.value.toLowerCase().trim();
    
    // If user is searching and details are hidden, open them
    if (searchTerm) {
        const detailsDiv = document.getElementById('scannedFilesDetails');
        const summaryDiv = document.getElementById('scannedFilesSummary');
        const toggleBtn = document.getElementById('toggleScannedFilesBtn');
        
        if (detailsDiv && detailsDiv.style.display === 'none') {
            // Open the details view
            detailsDiv.style.display = 'grid';
            if (summaryDiv) summaryDiv.style.display = 'none';
            if (toggleBtn) {
                toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Details';
            }
            
            // Show the unanalyzed filter button if it exists
            const filterBtn = document.getElementById('toggleUnanalyzedOnlyBtn');
            if (filterBtn) {
                filterBtn.style.display = 'inline-block';
            }
            
            // Ensure content type filter is visible
            const contentTypeFilter = document.getElementById('scannedFilesContentTypeFilter');
            if (contentTypeFilter) {
                contentTypeFilter.style.display = 'inline-block';
            }
        }
    }
    
    const sourceFilesList = document.getElementById('sourceFilesList');
    const targetFilesList = document.getElementById('targetFilesList');
    
    // Get current content type filter
    const contentTypeFilterValue = document.getElementById('scannedFilesContentTypeFilter')?.value || '';
    
    // Search both source and target files
    searchFileList(sourceFilesList, searchTerm, contentTypeFilterValue);
    searchFileList(targetFilesList, searchTerm, contentTypeFilterValue);
}

// Helper function to search within a file list
function searchFileList(container, searchTerm, contentTypeFilter) {
    if (!container) return;
    
    const fileItems = container.querySelectorAll('.scanned-file-item');
    let visibleCount = 0;
    let totalCount = 0;
    
    fileItems.forEach(item => {
        const fileName = item.querySelector('.file-name')?.textContent || '';
        const filePath = item.querySelector('.file-path')?.textContent || '';
        
        // Check content type filter first
        let matchesContentType = true;
        if (contentTypeFilter) {
            const pattern = `_${contentTypeFilter}_`;
            matchesContentType = fileName.includes(pattern);
        }
        
        // Only count items that match content type filter
        if (matchesContentType) {
            totalCount++;
            
            // Search in both filename and path
            const searchText = (fileName + ' ' + filePath).toLowerCase();
            
            if (!searchTerm || searchText.includes(searchTerm)) {
                item.style.display = '';
                visibleCount++;
            } else {
                item.style.display = 'none';
            }
        } else {
            // Hide items that don't match content type filter
            item.style.display = 'none';
        }
    });
    
    // Update file count
    const parentSection = container.closest('.dashboard-scanned-files-section, .scanned-files-section');
    if (parentSection) {
        const fileCount = parentSection.querySelector('.dashboard-file-count, .file-count');
        if (fileCount) {
            if (searchTerm) {
                fileCount.textContent = `${visibleCount} files found (${totalCount} total)`;
            } else {
                // Get original count from data attribute or current text
                const originalText = fileCount.getAttribute('data-original-text') || fileCount.textContent;
                fileCount.textContent = originalText;
            }
        }
    }
}

// Clear search function
function clearScannedFilesSearch() {
    const searchInput = document.getElementById('scannedFilesSearchInput');
    searchInput.value = '';
    searchScannedFiles();
    searchInput.focus();
}

// Wait for DOM and original functions to load
document.addEventListener('DOMContentLoaded', function() {
    // Override toggleScannedFiles to show/hide content type filter only
    if (window.toggleScannedFiles) {
        const originalToggleScannedFiles = window.toggleScannedFiles;
        window.toggleScannedFiles = function() {
            originalToggleScannedFiles();
            const detailsContainer = document.getElementById('scannedFilesDetails');
            const contentTypeFilter = document.getElementById('scannedFilesContentTypeFilter');
            
            if (detailsContainer) {
                const isVisible = detailsContainer.style.display !== 'none';
                
                if (contentTypeFilter) {
                    contentTypeFilter.style.display = isVisible ? 'inline-block' : 'none';
                }
                // Note: Search container visibility is now managed in script.js
            }
        };
    }
});

// Export functions to window
window.filterScannedFilesByContentType = filterScannedFilesByContentType;
window.filterComparisonByContentType = filterComparisonByContentType;
window.searchScannedFiles = searchScannedFiles;
window.clearScannedFilesSearch = clearScannedFilesSearch;