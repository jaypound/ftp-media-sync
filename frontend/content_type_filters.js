// Content type filter functions for dashboard

// Content type filter for scanned files
function filterScannedFilesByContentType() {
    const filterValue = document.getElementById('scannedFilesContentTypeFilter').value;
    const sourceFilesList = document.getElementById('sourceFilesList');
    const targetFilesList = document.getElementById('targetFilesList');
    
    filterFileListByContentType(sourceFilesList, filterValue);
    filterFileListByContentType(targetFilesList, filterValue);
}

// Content type filter for comparison results
function filterComparisonByContentType() {
    const filterValue = document.getElementById('comparisonContentTypeFilter').value;
    const fileList = document.getElementById('fileList');
    
    filterFileListByContentType(fileList, filterValue);
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

// Wait for DOM and original functions to load
document.addEventListener('DOMContentLoaded', function() {
    // Override toggleScannedFiles to show/hide content type filter
    if (window.toggleScannedFiles) {
        const originalToggleScannedFiles = window.toggleScannedFiles;
        window.toggleScannedFiles = function() {
            originalToggleScannedFiles();
            const detailsContainer = document.getElementById('scannedFilesDetails');
            const contentTypeFilter = document.getElementById('scannedFilesContentTypeFilter');
            if (detailsContainer && contentTypeFilter) {
                contentTypeFilter.style.display = detailsContainer.style.display === 'none' ? 'none' : 'inline-block';
            }
        };
    }
});

// Export functions to window
window.filterScannedFilesByContentType = filterScannedFilesByContentType;
window.filterComparisonByContentType = filterComparisonByContentType;