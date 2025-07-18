// Mock data
const sourceFiles = [
    { id: '1', name: 'video1.mp4', path: '/folder1/video1.mp4' },
    { id: '2', name: 'video2.mkv', path: '/folder1/video2.mkv' },
    { id: '3', name: 'video3.avi', path: '/folder2/video3.avi' },
    { id: '4', name: 'video4.mov', path: '/folder1/video4.mov' },
    { id: '5', name: 'document.txt', path: '/folder1/document.txt' }
];

// Simulate analysis queue with one file from folder1
const analysisQueue = [
    { id: '1', file: { id: '1', name: 'video1.mp4', path: '/folder1/video1.mp4' } }
];

function isVideoFileEligible(filename) {
    const videoExtensions = ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'm4v', 'flv'];
    const ext = filename.split('.').pop().toLowerCase();
    return videoExtensions.includes(ext);
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
        
        console.log(`File: ${file.name}, Folder: ${itemFolderPath}, Same folder: ${isSameFolder}, Already in queue: ${!!alreadyInQueue}`);
        
        if (isSameFolder && !alreadyInQueue) {
            videoFilesToAnalyze++;
        }
    });
    
    console.log('Total video files to analyze:', videoFilesToAnalyze);
    
    return {
        folderPath: targetFolderPath || 'root',
        videoFilesToAnalyze: videoFilesToAnalyze
    };
}

// Test the updated logic
console.log('=== Testing Updated Logic ===');
const result = getAnalyzeFolderStats();
console.log('Final result:', result);
console.log('Expected: Should show 2 files (video2.mkv and video4.mov) since video1.mp4 is already in queue');