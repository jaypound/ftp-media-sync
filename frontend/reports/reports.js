/**
 * Reports Module
 * Provides various analytical reports for content and scheduling
 */

const reportsState = {
    availableReports: [
        {
            id: 'schedule-analysis',
            name: 'Schedule Analysis Report',
            description: 'Comprehensive analysis of what content is scheduled and why',
            icon: 'fas fa-calendar-check',
            requiresScheduleId: true
        },
        {
            id: 'content-rotation',
            name: 'Content Rotation Report',
            description: 'Analysis of content rotation patterns and replay delays',
            icon: 'fas fa-sync-alt',
            requiresDateRange: true,
            status: 'coming-soon'
        },
        {
            id: 'content-performance',
            name: 'Content Performance Report',
            description: 'Engagement scores and content effectiveness metrics',
            icon: 'fas fa-chart-line',
            requiresDateRange: true,
            status: 'coming-soon'
        },
        {
            id: 'expiring-content',
            name: 'Expiring Content Report',
            description: 'Content approaching expiration dates',
            icon: 'fas fa-exclamation-triangle',
            status: 'coming-soon'
        }
    ],
    currentReport: null,
    reportData: null,
    loading: false
};

// Initialize Reports Module
function reportsInit() {
    console.log('Initializing Reports module...');
    
    // Update AppState
    AppState.setModule('reports', reportsState);
    
    // Display available reports
    reportsDisplayMenu();
}

// Display reports menu
function reportsDisplayMenu() {
    const container = document.getElementById('reportsContainer');
    if (!container) return;
    
    let html = `
        <div class="reports-menu">
            <div class="reports-header">
                <h2><i class="fas fa-chart-bar"></i> Analytics Reports</h2>
                <p class="reports-subtitle">Generate detailed reports to analyze your content and scheduling</p>
            </div>
            <div class="reports-grid">
    `;
    
    reportsState.availableReports.forEach(report => {
        const isComingSoon = report.status === 'coming-soon';
        const cardClass = isComingSoon ? 'report-card coming-soon' : 'report-card';
        
        html += `
            <div class="${cardClass}" onclick="${isComingSoon ? '' : `reportsOpenReport('${report.id}')`}">
                <div class="report-card-icon">
                    <i class="${report.icon}"></i>
                </div>
                <div class="report-card-content">
                    <h3>${report.name}</h3>
                    <p>${report.description}</p>
                    ${isComingSoon ? '<span class="coming-soon-badge">Coming Soon</span>' : ''}
                </div>
            </div>
        `;
    });
    
    html += `
            </div>
        </div>
        <div id="reportContent" class="report-content" style="display: none;">
            <!-- Report content will be loaded here -->
        </div>
    `;
    
    container.innerHTML = html;
}

// Open a specific report
async function reportsOpenReport(reportId) {
    const report = reportsState.availableReports.find(r => r.id === reportId);
    if (!report) return;
    
    reportsState.currentReport = report;
    
    // Show report container
    document.querySelector('.reports-menu').style.display = 'none';
    document.getElementById('reportContent').style.display = 'block';
    
    // Load report based on type
    switch (reportId) {
        case 'schedule-analysis':
            await reportsLoadScheduleAnalysis();
            break;
        default:
            window.showNotification('Report not yet implemented', 'info');
            reportsBackToMenu();
    }
}

// Load Schedule Analysis Report
async function reportsLoadScheduleAnalysis() {
    const reportContent = document.getElementById('reportContent');
    
    // First, show schedule selector
    reportContent.innerHTML = `
        <div class="report-header">
            <button class="button secondary" onclick="reportsBackToMenu()">
                <i class="fas fa-arrow-left"></i> Back to Reports
            </button>
            <h2><i class="fas fa-calendar-check"></i> Schedule Analysis Report</h2>
        </div>
        
        <div class="report-selector">
            <h3>Select a Schedule to Analyze</h3>
            <div class="schedule-selector-container">
                <select id="scheduleSelector" class="form-select">
                    <option value="">Loading schedules...</option>
                </select>
                <button class="button primary" onclick="reportsGenerateScheduleAnalysis()" disabled id="generateReportBtn">
                    <i class="fas fa-play"></i> Generate Report
                </button>
            </div>
        </div>
        
        <div id="reportResults" class="report-results" style="display: none;">
            <!-- Report results will appear here -->
        </div>
    `;
    
    // Load available schedules
    try {
        console.log('Loading schedules...');
        const response = await window.API.get('/list-schedules');
        console.log('Schedule API response:', response);
        
        if (response.schedules && response.schedules.length > 0) {
            const selector = document.getElementById('scheduleSelector');
            const generateBtn = document.getElementById('generateReportBtn');
            
            // Sort schedules by creation date (newest first)
            const schedules = response.schedules.sort((a, b) => 
                new Date(b.created_at) - new Date(a.created_at)
            );
            
            let optionsHtml = '<option value="">-- Select a Schedule --</option>';
            
            // Group schedules by type for better organization
            const weeklySchedules = schedules.filter(s => s.name.includes('Weekly'));
            const dailySchedules = schedules.filter(s => s.name.includes('Daily') && !s.name.includes('Weekly'));
            const monthlySchedules = schedules.filter(s => s.name.includes('Monthly'));
            const otherSchedules = schedules.filter(s => !s.name.includes('Weekly') && !s.name.includes('Daily') && !s.name.includes('Monthly'));
            
            // Add weekly schedules first
            if (weeklySchedules.length > 0) {
                optionsHtml += '<optgroup label="Weekly Schedules">';
                weeklySchedules.forEach(schedule => {
                    const airDate = new Date(schedule.air_date).toLocaleDateString();
                    const totalHours = schedule.total_duration ? (schedule.total_duration / 3600).toFixed(1) : '0';
                    optionsHtml += `
                        <option value="${schedule.id}">
                            ${schedule.name} - ${totalHours}h (Air: ${airDate})
                        </option>
                    `;
                });
                optionsHtml += '</optgroup>';
            }
            
            // Add daily schedules
            if (dailySchedules.length > 0) {
                optionsHtml += '<optgroup label="Daily Schedules">';
                dailySchedules.forEach(schedule => {
                    const airDate = new Date(schedule.air_date).toLocaleDateString();
                    const totalHours = schedule.total_duration ? (schedule.total_duration / 3600).toFixed(1) : '0';
                    optionsHtml += `
                        <option value="${schedule.id}">
                            ${schedule.name} - ${totalHours}h (${airDate})
                        </option>
                    `;
                });
                optionsHtml += '</optgroup>';
            }
            
            // Add monthly schedules
            if (monthlySchedules.length > 0) {
                optionsHtml += '<optgroup label="Monthly Schedules">';
                monthlySchedules.forEach(schedule => {
                    const airDate = new Date(schedule.air_date).toLocaleDateString();
                    optionsHtml += `
                        <option value="${schedule.id}">
                            ${schedule.name} (${airDate})
                        </option>
                    `;
                });
                optionsHtml += '</optgroup>';
            }
            
            // Add other schedules
            if (otherSchedules.length > 0) {
                optionsHtml += '<optgroup label="Other Schedules">';
                otherSchedules.forEach(schedule => {
                    const airDate = new Date(schedule.air_date).toLocaleDateString();
                    optionsHtml += `
                        <option value="${schedule.id}">
                            ${schedule.name} (${airDate})
                        </option>
                    `;
                });
                optionsHtml += '</optgroup>';
            }
            
            selector.innerHTML = optionsHtml;
            selector.onchange = () => {
                generateBtn.disabled = !selector.value;
            };
        } else {
            // No schedules found
            const selector = document.getElementById('scheduleSelector');
            selector.innerHTML = '<option value="">No schedules found</option>';
        }
    } catch (error) {
        console.error('Failed to load schedules:', error);
        console.error('Error details:', {
            message: error.message,
            stack: error.stack,
            type: error.name
        });
        window.showNotification(`Failed to load schedules: ${error.message}`, 'error');
        const selector = document.getElementById('scheduleSelector');
        selector.innerHTML = '<option value="">Error loading schedules</option>';
    }
}

// Generate Schedule Analysis Report
async function reportsGenerateScheduleAnalysis() {
    const scheduleId = document.getElementById('scheduleSelector').value;
    if (!scheduleId) return;
    
    const resultsDiv = document.getElementById('reportResults');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div class="report-loading">
            <i class="fas fa-spinner fa-spin"></i> Generating report...
        </div>
    `;
    
    try {
        const response = await window.API.post('/generate-report', {
            report_type: 'schedule-analysis',
            schedule_id: parseInt(scheduleId)
        });
        
        if (response.success) {
            reportsDisplayScheduleAnalysisResults(response.data);
        } else {
            throw new Error(response.message || 'Failed to generate report');
        }
    } catch (error) {
        console.error('Report generation failed:', error);
        resultsDiv.innerHTML = `
            <div class="report-error">
                <i class="fas fa-exclamation-circle"></i> 
                Failed to generate report: ${error.message}
            </div>
        `;
    }
}

// Display Schedule Analysis Results
function reportsDisplayScheduleAnalysisResults(data) {
    const resultsDiv = document.getElementById('reportResults');
    
    let html = `
        <div class="report-results-content">
            <div class="report-timestamp">
                Generated: ${new Date().toLocaleString()}
            </div>
    `;
    
    // Overview Section
    html += `
        <div class="report-section">
            <h3>Schedule Overview</h3>
            <div class="report-stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${data.overview.total_items}</div>
                    <div class="stat-label">Total Items</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${typeof data.overview.total_hours === 'number' ? data.overview.total_hours.toFixed(1) : '0.0'}h</div>
                    <div class="stat-label">Total Duration</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.overview.unique_content}</div>
                    <div class="stat-label">Unique Content</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.overview.air_date}</div>
                    <div class="stat-label">Air Date</div>
                </div>
            </div>
        </div>
    `;
    
    // Category Distribution
    html += `
        <div class="report-section">
            <h3>Content by Duration Category</h3>
            <table class="report-table">
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Count</th>
                        <th>Unique</th>
                        <th>Hours</th>
                        <th>Percentage</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    data.category_distribution.forEach(cat => {
        const totalHours = parseFloat(cat.total_hours) || 0;
        const overviewHours = parseFloat(data.overview.total_hours) || 1;
        const percentage = ((totalHours / overviewHours) * 100).toFixed(1);
        html += `
            <tr>
                <td><span class="category-badge ${cat.category}">${cat.category}</span></td>
                <td>${cat.count}</td>
                <td>${cat.unique_content}</td>
                <td>${totalHours.toFixed(1)}</td>
                <td>
                    <div class="percentage-bar">
                        <div class="percentage-fill" style="width: ${percentage}%"></div>
                        <span>${percentage}%</span>
                    </div>
                </td>
            </tr>
        `;
    });
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    // Most Scheduled Content
    if (data.most_scheduled && data.most_scheduled.length > 0) {
        html += `
            <div class="report-section">
                <h3>Most Frequently Scheduled</h3>
                <table class="report-table">
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Type</th>
                            <th>Category</th>
                            <th>Times</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        data.most_scheduled.forEach(item => {
            html += `
                <tr>
                    <td class="content-title">${item.title}</td>
                    <td><span class="type-badge">${item.type}</span></td>
                    <td><span class="category-badge ${item.category}">${item.category}</span></td>
                    <td>${item.count}</td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    // Available but Not Scheduled
    if (data.not_scheduled && data.not_scheduled.length > 0) {
        html += `
            <div class="report-section">
                <h3>Available Content Not Scheduled</h3>
                <div class="report-note">
                    These items were available but not selected during rotation
                </div>
                <table class="report-table">
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Type</th>
                            <th>Category</th>
                            <th>Last Aired</th>
                            <th>Reason</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        data.not_scheduled.forEach(item => {
            html += `
                <tr>
                    <td class="content-title">${item.title}</td>
                    <td><span class="type-badge">${item.type}</span></td>
                    <td><span class="category-badge ${item.category}">${item.category}</span></td>
                    <td>${item.last_scheduled || 'Never'}</td>
                    <td>${item.reason || 'Not selected in rotation'}</td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    html += `
            <div class="report-actions">
                <button class="button secondary" onclick="reportsExportToCSV()">
                    <i class="fas fa-download"></i> Export to CSV
                </button>
                <button class="button secondary" onclick="reportsPrint()">
                    <i class="fas fa-print"></i> Print Report
                </button>
            </div>
        </div>
    `;
    
    resultsDiv.innerHTML = html;
}

// Back to reports menu
function reportsBackToMenu() {
    document.querySelector('.reports-menu').style.display = 'block';
    document.getElementById('reportContent').style.display = 'none';
    reportsState.currentReport = null;
}

// Export report to CSV
function reportsExportToCSV() {
    // TODO: Implement CSV export
    window.showNotification('CSV export coming soon', 'info');
}

// Print report
function reportsPrint() {
    window.print();
}

// Export functions
window.reportsInit = reportsInit;
window.reportsOpenReport = reportsOpenReport;
window.reportsGenerateScheduleAnalysis = reportsGenerateScheduleAnalysis;
window.reportsBackToMenu = reportsBackToMenu;
window.reportsExportToCSV = reportsExportToCSV;
window.reportsPrint = reportsPrint;