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
            id: 'content-replay-distribution',
            name: 'Content Replay Distribution',
            description: 'Bell curve showing distribution of content replay counts by duration category',
            icon: 'fas fa-chart-area',
            requiresScheduleId: true
        },
        {
            id: 'replay-heatmap',
            name: 'Replay Timeline Heat Map',
            description: 'Visual heat map showing when content is replayed throughout the day',
            icon: 'fas fa-th',
            requiresScheduleId: true
        },
        {
            id: 'replay-frequency-boxplot',
            name: 'Replay Frequency Analysis',
            description: 'Box plot showing replay frequency distribution by duration category',
            icon: 'fas fa-chart-box',
            requiresScheduleId: true
        },
        {
            id: 'content-freshness',
            name: 'Content Freshness Dashboard',
            description: 'Overview of fresh vs repeated content with key metrics',
            icon: 'fas fa-tachometer-alt',
            requiresScheduleId: true
        },
        {
            id: 'pareto-chart',
            name: 'Top Replayed Content',
            description: 'Pareto chart showing most frequently replayed content',
            icon: 'fas fa-sort-amount-down',
            requiresScheduleId: true
        },
        {
            id: 'replay-gaps',
            name: 'Time Between Replays',
            description: 'Distribution of time gaps between content replays',
            icon: 'fas fa-clock',
            requiresScheduleId: true
        },
        {
            id: 'comprehensive-analysis',
            name: 'Comprehensive Schedule Analysis',
            description: 'All-in-one detailed schedule analysis with multiple visualizations',
            icon: 'fas fa-analytics',
            requiresScheduleId: true
        },
        {
            id: 'content-diversity-dashboard',
            name: 'Content Diversity Dashboard',
            description: 'Shows available vs used content, usage rates by category, and identifies underutilized content',
            icon: 'fas fa-chart-pie',
            requiresScheduleId: true
        },
        {
            id: 'available-content',
            name: 'Available Content Report',
            description: 'Analysis of available content by duration category, showing active and expired content',
            icon: 'fas fa-database',
            requiresScheduleId: false
        },
        {
            id: 'schedule-content-search',
            name: 'Schedule Content Search',
            description: 'Search for specific content within a schedule by file name or title',
            icon: 'fas fa-search',
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
        case 'content-replay-distribution':
        case 'replay-heatmap':
        case 'replay-frequency-boxplot':
        case 'content-freshness':
        case 'pareto-chart':
        case 'replay-gaps':
        case 'comprehensive-analysis':
        case 'content-diversity-dashboard':
            await reportsLoadScheduleBasedReport(reportId);
            break;
        case 'available-content':
            await reportsLoadAvailableContent();
            break;
        case 'schedule-content-search':
            await reportsLoadScheduleContentSearch();
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

// Load schedule-based report (for new visualization reports)
async function reportsLoadScheduleBasedReport(reportId) {
    const reportContent = document.getElementById('reportContent');
    const report = reportsState.availableReports.find(r => r.id === reportId);
    
    // Show schedule selector with additional options for diversity dashboard
    const additionalOptions = reportId === 'content-diversity-dashboard' ? `
        <div class="report-options" style="margin-top: 1rem;">
            <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem;">
                <input type="checkbox" id="includeExpiredContent">
                <span>Include expired content in analysis</span>
            </label>
        </div>
    ` : '';
    
    reportContent.innerHTML = `
        <div class="report-header">
            <button class="button secondary" onclick="reportsBackToMenu()">
                <i class="fas fa-arrow-left"></i> Back to Reports
            </button>
            <h2><i class="${report.icon}"></i> ${report.name}</h2>
        </div>
        
        <div class="report-selector">
            <h3>Select a Schedule to Analyze</h3>
            <div class="schedule-selector-container">
                <select id="scheduleSelector" class="form-select">
                    <option value="">Loading schedules...</option>
                </select>
                <button class="button primary" onclick="reportsGenerateVisualization('${reportId}')" disabled id="generateReportBtn">
                    <i class="fas fa-play"></i> Generate Report
                </button>
            </div>
            ${additionalOptions}
        </div>
        
        <div id="reportResults" class="report-results" style="display: none;">
            <!-- Report results will appear here -->
        </div>
    `;
    
    // Load available schedules (reuse existing logic)
    try {
        const response = await window.API.get('/list-schedules');
        
        if (response.schedules && response.schedules.length > 0) {
            const selector = document.getElementById('scheduleSelector');
            const generateBtn = document.getElementById('generateReportBtn');
            
            // Sort schedules by creation date (newest first)
            const schedules = response.schedules.sort((a, b) => 
                new Date(b.created_at) - new Date(a.created_at)
            );
            
            let optionsHtml = '<option value="">-- Select a Schedule --</option>';
            
            // Group schedules by type
            const weeklySchedules = schedules.filter(s => s.name.includes('Weekly'));
            const dailySchedules = schedules.filter(s => s.name.includes('Daily') && !s.name.includes('Weekly'));
            const monthlySchedules = schedules.filter(s => s.name.includes('Monthly'));
            
            if (weeklySchedules.length > 0) {
                optionsHtml += '<optgroup label="Weekly Schedules">';
                weeklySchedules.forEach(schedule => {
                    const airDate = new Date(schedule.air_date).toLocaleDateString();
                    optionsHtml += `<option value="${schedule.id}">${schedule.name} (Air: ${airDate})</option>`;
                });
                optionsHtml += '</optgroup>';
            }
            
            if (dailySchedules.length > 0) {
                optionsHtml += '<optgroup label="Daily Schedules">';
                dailySchedules.forEach(schedule => {
                    const airDate = new Date(schedule.air_date).toLocaleDateString();
                    optionsHtml += `<option value="${schedule.id}">${schedule.name} (${airDate})</option>`;
                });
                optionsHtml += '</optgroup>';
            }
            
            if (monthlySchedules.length > 0) {
                optionsHtml += '<optgroup label="Monthly Schedules">';
                monthlySchedules.forEach(schedule => {
                    const airDate = new Date(schedule.air_date).toLocaleDateString();
                    optionsHtml += `<option value="${schedule.id}">${schedule.name} (${airDate})</option>`;
                });
                optionsHtml += '</optgroup>';
            }
            
            selector.innerHTML = optionsHtml;
            selector.onchange = () => {
                generateBtn.disabled = !selector.value;
            };
        }
    } catch (error) {
        console.error('Failed to load schedules:', error);
        window.showNotification(`Failed to load schedules: ${error.message}`, 'error');
    }
}

// Generate visualization report
async function reportsGenerateVisualization(reportId) {
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
        // Check if we need to include expired content (for diversity dashboard)
        let url = '/generate-report';
        const includeExpired = reportId === 'content-diversity-dashboard' && 
                              document.getElementById('includeExpiredContent')?.checked;
        
        if (includeExpired) {
            url += '?include_expired=true';
        }
        
        const response = await window.API.post(url, {
            report_type: reportId,
            schedule_id: parseInt(scheduleId)
        });
        
        if (response.success) {
            // Store the report data
            reportsState.reportData = response.data;
            reportsDisplayVisualization(reportId, response.data);
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

// Display visualization based on report type
function reportsDisplayVisualization(reportId, data) {
    const resultsDiv = document.getElementById('reportResults');
    
    // Add Chart.js if not already loaded
    if (!window.Chart) {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
        script.onload = () => {
            renderVisualization(reportId, data, resultsDiv);
        };
        document.head.appendChild(script);
    } else {
        renderVisualization(reportId, data, resultsDiv);
    }
}

// Render specific visualization
function renderVisualization(reportId, data, container) {
    let html = `
        <div class="report-actions">
            <button class="button secondary" onclick="reportsExportToCSV()">
                <i class="fas fa-download"></i> Export CSV
            </button>
            <button class="button secondary" onclick="reportsPrint()">
                <i class="fas fa-print"></i> Print
            </button>
        </div>
    `;
    
    switch (reportId) {
        case 'content-replay-distribution':
            html += renderReplayDistribution(data);
            break;
        case 'replay-heatmap':
            html += renderReplayHeatmap(data);
            break;
        case 'replay-frequency-boxplot':
            html += renderReplayBoxplot(data);
            break;
        case 'content-freshness':
            html += renderContentFreshness(data);
            break;
        case 'pareto-chart':
            html += renderParetoChart(data);
            break;
        case 'replay-gaps':
            html += renderReplayGaps(data);
            break;
        case 'comprehensive-analysis':
            html += renderComprehensiveAnalysis(data);
            break;
        case 'content-diversity-dashboard':
            html += renderContentDiversityDashboard(data);
            break;
    }
    
    container.innerHTML = html;
    
    // Initialize charts after DOM update
    setTimeout(() => {
        initializeCharts(reportId, data);
    }, 100);
}

// Render Content Replay Distribution (Bell Curve)
function renderReplayDistribution(data) {
    // Calculate total unique content and total plays
    let totalUniqueContent = 0;
    let totalPlays = 0;
    let maxReplays = 1;
    
    Object.values(data.distributions).forEach(dist => {
        totalUniqueContent += dist.stats.total_content;
        if (dist.data.length > 0) {
            const maxInCategory = Math.max(...dist.data.map(d => d.replay_count));
            maxReplays = Math.max(maxReplays, maxInCategory);
        }
    });
    
    // Check if all content is only played once
    const allSinglePlays = maxReplays === 1;
    
    // Add day selector for weekly schedules
    let daySelectorHtml = '';
    if (data.is_weekly) {
        daySelectorHtml = `
            <div class="day-selector" style="margin: 1rem 0;">
                <label style="font-weight: 600; margin-right: 0.5rem;">Filter by day:</label>
                <select id="weeklyDayFilter" onchange="reportsFilterByDay()" class="form-select" style="display: inline-block; width: auto;">
                    <option value="">All Days (Full Week)</option>
                    <option value="0">Sunday</option>
                    <option value="1">Monday</option>
                    <option value="2">Tuesday</option>
                    <option value="3">Wednesday</option>
                    <option value="4">Thursday</option>
                    <option value="5">Friday</option>
                    <option value="6">Saturday</option>
                </select>
                ${data.schedule.filtered_day !== undefined ? `<span style="margin-left: 1rem; color: #1976d2;"><i class="fas fa-info-circle"></i> Showing ${data.schedule.filtered_day_name} only</span>` : ''}
            </div>
        `;
    }
    
    return `
        <div class="report-section">
            <h3>Content Replay Distribution by Duration Category</h3>
            <p>${data.explanation || 'Shows how many times unique content items are replayed, forming a distribution curve.'}</p>
            ${daySelectorHtml}
            ${allSinglePlays ? `
                <div class="info-banner" style="background: #e3f2fd; color: #1976d2; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                    <i class="fas fa-info-circle"></i> 
                    <strong>Excellent content diversity!</strong> All ${totalUniqueContent} content items in this schedule are played exactly once. 
                    No content is repeated, which indicates optimal rotation.
                </div>
            ` : ''}
            <div class="chart-container">
                <canvas id="replayDistributionChart"></canvas>
            </div>
            <div class="stats-grid">
                ${Object.entries(data.distributions).map(([category, dist]) => {
                    const singlePlayCount = dist.data.find(d => d.replay_count === 1)?.content_count || 0;
                    const multiPlayCount = dist.stats.total_content - singlePlayCount;
                    
                    return `
                        <div class="stat-card">
                            <h4>${category.toUpperCase()}</h4>
                            <div class="stat-value">${dist.stats.total_content} items</div>
                            <div class="stat-details">
                                <span>Avg replays: ${dist.stats.mean.toFixed(1)}</span>
                                <span>Max replays: ${dist.data.length > 0 ? Math.max(...dist.data.map(d => d.replay_count)) : 1}</span>
                                ${multiPlayCount > 0 ? `<span style="color: #ff9800;">Repeated: ${multiPlayCount}</span>` : '<span style="color: #4caf50;">No repeats</span>'}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

// Render Replay Heatmap
function renderReplayHeatmap(data) {
    return `
        <div class="report-section">
            <h3>Content Replay Timeline Heatmap</h3>
            <p>Visual representation of when content is replayed throughout the ${data.is_weekly ? 'week' : 'day'}. Darker colors indicate more replays.</p>
            <div class="heatmap-container" id="replayHeatmap">
                <!-- Heatmap will be rendered here -->
            </div>
            <div class="heatmap-legend">
                <span>Less Replays</span>
                <div class="gradient"></div>
                <span>More Replays</span>
            </div>
        </div>
    `;
}

// Render Replay Frequency Boxplot
function renderReplayBoxplot(data) {
    return `
        <div class="report-section">
            <h3>Replay Frequency Analysis by Duration Category</h3>
            <p>Box plots showing the distribution of replay counts for each duration category.</p>
            <div class="chart-container">
                <canvas id="replayBoxplotChart"></canvas>
            </div>
            <div class="boxplot-stats">
                ${data.boxplot_data.map(cat => `
                    <div class="category-stat">
                        <h4>${cat.category}</h4>
                        <div class="stat-row">
                            <span>Content items:</span> <strong>${cat.count}</strong>
                        </div>
                        <div class="stat-row">
                            <span>Median replays:</span> <strong>${cat.median}</strong>
                        </div>
                        <div class="stat-row">
                            <span>Range:</span> <strong>${cat.min}-${cat.max}</strong>
                        </div>
                        ${cat.outliers.length > 0 ? `
                            <div class="stat-row outliers">
                                <span>Outliers:</span> <strong>${cat.outliers.length}</strong>
                            </div>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

// Render Content Freshness Dashboard
function renderContentFreshness(data) {
    const freshPercent = data.metrics.fresh_content_percentage.toFixed(1);
    const diversityIndex = data.metrics.content_diversity_index.toFixed(2);
    
    return `
        <div class="report-section">
            <h3>Content Freshness Dashboard</h3>
            <div class="freshness-metrics">
                <div class="metric-card primary">
                    <div class="metric-icon"><i class="fas fa-percentage"></i></div>
                    <div class="metric-value">${freshPercent}%</div>
                    <div class="metric-label">Fresh Content</div>
                </div>
                <div class="metric-card">
                    <div class="metric-icon"><i class="fas fa-film"></i></div>
                    <div class="metric-value">${data.metrics.unique_content}</div>
                    <div class="metric-label">Unique Items</div>
                </div>
                <div class="metric-card">
                    <div class="metric-icon"><i class="fas fa-th"></i></div>
                    <div class="metric-value">${data.metrics.total_slots}</div>
                    <div class="metric-label">Total Slots</div>
                </div>
                <div class="metric-card">
                    <div class="metric-icon"><i class="fas fa-chart-line"></i></div>
                    <div class="metric-value">${diversityIndex}</div>
                    <div class="metric-label">Diversity Index</div>
                </div>
            </div>
            
            <div class="charts-row">
                <div class="chart-half">
                    <h4>Replay Distribution</h4>
                    <canvas id="replayPieChart"></canvas>
                </div>
                <div class="chart-half">
                    <h4>Average Replays by Type</h4>
                    <canvas id="typeBarChart"></canvas>
                </div>
            </div>
            
            <div class="most-replayed">
                <h4>Most Replayed Content</h4>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Type</th>
                            <th>Plays</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.most_replayed.map(item => `
                            <tr>
                                <td>${item.title}</td>
                                <td><span class="type-badge">${item.type}</span></td>
                                <td>${item.play_count}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Render Pareto Chart
function renderParetoChart(data) {
    const insight = data.insights;
    return `
        <div class="report-section">
            <h3>Top Replayed Content - Pareto Analysis</h3>
            <div class="pareto-insight">
                <i class="fas fa-info-circle"></i>
                <strong>${insight.percentage_of_content_for_80_percent.toFixed(1)}%</strong> of content 
                accounts for <strong>80%</strong> of all plays
                (${insight.content_for_80_percent} out of ${insight.total_unique_content} unique items)
            </div>
            <div class="chart-container">
                <canvas id="paretoChart"></canvas>
            </div>
            <div class="pareto-table">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Title</th>
                            <th>Type</th>
                            <th>Category</th>
                            <th>Plays</th>
                            <th>% of Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.pareto_data.map(item => `
                            <tr>
                                <td>${item.rank}</td>
                                <td>${item.title}</td>
                                <td><span class="type-badge">${item.type}</span></td>
                                <td>${item.category}</td>
                                <td>${item.play_count}</td>
                                <td>${item.percentage.toFixed(1)}%</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Render Replay Gaps Distribution
function renderReplayGaps(data) {
    return `
        <div class="report-section">
            <h3>Time Between Content Replays</h3>
            <p>Distribution of time gaps between when the same content is replayed.</p>
            
            <div class="gap-violations">
                <h4>Policy Violations</h4>
                <div class="violation-cards">
                    <div class="violation-card ${data.violations.under_5min > 0 ? 'has-violations' : ''}">
                        <div class="violation-count">${data.violations.under_5min}</div>
                        <div class="violation-label">Under 5 minutes</div>
                    </div>
                    <div class="violation-card ${data.violations.under_15min > 0 ? 'has-violations' : ''}">
                        <div class="violation-count">${data.violations.under_15min}</div>
                        <div class="violation-label">Under 15 minutes</div>
                    </div>
                    <div class="violation-card ${data.violations.under_30min > 0 ? 'has-violations' : ''}">
                        <div class="violation-count">${data.violations.under_30min}</div>
                        <div class="violation-label">Under 30 minutes</div>
                    </div>
                </div>
            </div>
            
            <div class="chart-container">
                <canvas id="gapHistogramChart"></canvas>
            </div>
            
            <div class="gap-statistics">
                <h4>Statistics</h4>
                <div class="stats-row">
                    <span>Average gap:</span> <strong>${data.statistics.average_gap_minutes.toFixed(1)} minutes</strong>
                </div>
                <div class="stats-row">
                    <span>Median gap:</span> <strong>${data.statistics.median_gap_minutes.toFixed(1)} minutes</strong>
                </div>
                <div class="stats-row">
                    <span>Shortest gap:</span> <strong>${data.statistics.min_gap_minutes.toFixed(1)} minutes</strong>
                </div>
                <div class="stats-row">
                    <span>Longest gap:</span> <strong>${data.statistics.max_gap_minutes.toFixed(1)} minutes</strong>
                </div>
            </div>
        </div>
    `;
}

// Render Comprehensive Analysis
function renderComprehensiveAnalysis(data) {
    const score = data.health_score;
    const gradeClass = score.grade === 'A' ? 'grade-a' : 
                      score.grade === 'B' ? 'grade-b' : 
                      score.grade === 'C' ? 'grade-c' : 
                      score.grade === 'D' ? 'grade-d' : 'grade-f';
    
    return `
        <div class="report-section comprehensive">
            <h3>Comprehensive Schedule Analysis</h3>
            
            <div class="health-score-card ${gradeClass}">
                <div class="score-circle">
                    <div class="score-value">${score.overall}</div>
                    <div class="score-grade">${score.grade}</div>
                </div>
                <div class="score-breakdown">
                    <h4>Schedule Health Score</h4>
                    <div class="score-components">
                        <div class="component">
                            <span>Content Diversity:</span>
                            <div class="progress-bar">
                                <div class="progress" style="width: ${score.components.diversity}%"></div>
                            </div>
                            <span>${score.components.diversity.toFixed(0)}%</span>
                        </div>
                        <div class="component">
                            <span>Freshness:</span>
                            <div class="progress-bar">
                                <div class="progress" style="width: ${score.components.freshness}%"></div>
                            </div>
                            <span>${score.components.freshness.toFixed(0)}%</span>
                        </div>
                        <div class="component">
                            <span>Proper Spacing:</span>
                            <div class="progress-bar">
                                <div class="progress" style="width: ${score.components.spacing}%"></div>
                            </div>
                            <span>${score.components.spacing.toFixed(0)}%</span>
                        </div>
                        <div class="component">
                            <span>Category Balance:</span>
                            <div class="progress-bar">
                                <div class="progress" style="width: ${score.components.balance}%"></div>
                            </div>
                            <span>${score.components.balance.toFixed(0)}%</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="recommendations">
                <h4>Recommendations</h4>
                <ul>
                    ${data.recommendations.map(rec => `<li>${rec}</li>`).join('')}
                </ul>
            </div>
            
            <div class="summary-charts">
                <div class="chart-third">
                    <h4>Key Metrics</h4>
                    <div class="metric-list">
                        <div class="metric-item">
                            <span>Unique Content:</span>
                            <strong>${data.freshness_metrics.unique_content}</strong>
                        </div>
                        <div class="metric-item">
                            <span>Total Slots:</span>
                            <strong>${data.freshness_metrics.total_slots}</strong>
                        </div>
                        <div class="metric-item">
                            <span>Fresh Content:</span>
                            <strong>${data.freshness_metrics.fresh_content_percentage.toFixed(1)}%</strong>
                        </div>
                        <div class="metric-item">
                            <span>Avg Gap:</span>
                            <strong>${data.gap_statistics.average_gap_minutes.toFixed(0)}m</strong>
                        </div>
                    </div>
                </div>
                <div class="chart-third">
                    <h4>Content Distribution</h4>
                    <canvas id="comprehensiveDistChart"></canvas>
                </div>
                <div class="chart-third">
                    <h4>Top Replayed</h4>
                    <div class="top-replayed-mini">
                        ${data.top_replayed.slice(0, 5).map((item, i) => `
                            <div class="replayed-item">
                                <span class="rank">#${i + 1}</span>
                                <span class="title" title="${item.title}">${item.title}</span>
                                <span class="count">${item.play_count}x</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderContentDiversityDashboard(data) {
    const metrics = data.overall_metrics;
    const categoryUsage = data.category_usage;
    const typeUsage = data.type_usage;
    
    return `
        <div class="report-section diversity-dashboard">
            <h3>Content Diversity Dashboard</h3>
            
            <div class="overall-metrics">
                <div class="metric-card">
                    <h4>Library Usage</h4>
                    <div class="metric-value">${metrics.usage_rate.toFixed(1)}%</div>
                    <div class="metric-label">${metrics.total_used} of ${metrics.total_available} content items used</div>
                    ${metrics.include_expired && metrics.expired_count > 0 ? 
                        `<div class="metric-sublabel">${metrics.expired_count} expired, ${metrics.active_count} active</div>` : ''}
                </div>
                <div class="metric-card">
                    <h4>Diversity Score</h4>
                    <div class="metric-value">${metrics.diversity_score.toFixed(1)}%</div>
                    <div class="metric-label">Unique content per slot</div>
                </div>
            </div>
            
            <div class="usage-by-category">
                <h4>Usage by Duration Category</h4>
                <div class="usage-grid">
                    ${Object.entries(categoryUsage).map(([category, usage]) => `
                        <div class="category-usage">
                            <h5>${category.toUpperCase()}</h5>
                            <div class="usage-bar">
                                <div class="usage-fill" style="width: ${usage.usage_rate}%"></div>
                            </div>
                            <div class="usage-stats">
                                <span>${usage.usage_rate.toFixed(1)}%</span>
                                <span>${usage.used}/${usage.available}</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <div class="insights-section">
                <h4>Key Insights</h4>
                <ul class="insights-list">
                    ${data.insights.map(insight => `<li>${insight}</li>`).join('')}
                </ul>
            </div>
            
            <div class="underutilized-content">
                <h4>Never Used Content (${data.never_used.length} items)</h4>
                <div class="content-list">
                    ${data.never_used.slice(0, 10).map(item => `
                        <div class="unused-item">
                            <span class="title" title="${item.title}">${item.title}</span>
                            <span class="category">${item.category}</span>
                            <span class="days">${item.days_in_library} days in library</span>
                        </div>
                    `).join('')}
                    ${data.never_used.length > 10 ? `<div class="more-items">... and ${data.never_used.length - 10} more items</div>` : ''}
                </div>
            </div>
            
            <div class="underutilized-content">
                <h4>Underutilized Content (≤2 plays)</h4>
                <div class="content-list">
                    ${data.underutilized.slice(0, 10).map(item => `
                        <div class="unused-item">
                            <span class="title" title="${item.title}">${item.title}</span>
                            <span class="category">${item.category}</span>
                            <span class="plays">${item.play_count} plays</span>
                        </div>
                    `).join('')}
                    ${data.underutilized.length > 10 ? `<div class="more-items">... and ${data.underutilized.length - 10} more items</div>` : ''}
                </div>
            </div>
        </div>
    `;
}

// Initialize charts based on report type
function initializeCharts(reportId, data) {
    switch (reportId) {
        case 'content-replay-distribution':
            initReplayDistributionChart(data);
            break;
        case 'replay-heatmap':
            initReplayHeatmap(data);
            break;
        case 'replay-frequency-boxplot':
            initReplayBoxplotChart(data);
            break;
        case 'content-freshness':
            initFreshnessCharts(data);
            break;
        case 'pareto-chart':
            initParetoChart(data);
            break;
        case 'replay-gaps':
            initGapHistogram(data);
            break;
        case 'comprehensive-analysis':
            initComprehensiveCharts(data);
            break;
    }
}

// Chart initialization functions (stubs for now)
function initReplayDistributionChart(data) {
    const ctx = document.getElementById('replayDistributionChart').getContext('2d');
    const datasets = [];
    const colors = {
        'id': 'rgba(255, 99, 132, 0.8)',
        'spots': 'rgba(54, 162, 235, 0.8)',
        'short_form': 'rgba(255, 206, 86, 0.8)',
        'long_form': 'rgba(75, 192, 192, 0.8)'
    };
    
    // Find max replay count to set appropriate scale
    let maxReplayCount = 1;
    let maxContentCount = 0;
    
    Object.entries(data.distributions).forEach(([category, dist]) => {
        const categoryData = dist.data.map(d => ({ x: d.replay_count, y: d.content_count }));
        
        // Add data point at x=0, y=0 for better visualization if all are single plays
        if (dist.data.length === 1 && dist.data[0].replay_count === 1) {
            categoryData.unshift({ x: 0, y: 0 });
            categoryData.push({ x: 2, y: 0 });
        }
        
        datasets.push({
            label: category.toUpperCase(),
            data: categoryData,
            borderColor: colors[category] || 'rgba(153, 102, 255, 0.8)',
            backgroundColor: colors[category] || 'rgba(153, 102, 255, 0.2)',
            tension: 0.4,
            pointRadius: 4,
            pointHoverRadius: 6
        });
        
        // Track max values
        dist.data.forEach(d => {
            maxReplayCount = Math.max(maxReplayCount, d.replay_count);
            maxContentCount = Math.max(maxContentCount, d.content_count);
        });
    });
    
    new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Content Replay Distribution'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const plays = context.parsed.x;
                            const items = context.parsed.y;
                            if (plays === 0 || items === 0) return null; // Hide padding points
                            return `${context.dataset.label}: ${items} items played ${plays} time${plays > 1 ? 's' : ''}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: data.x_axis || 'Number of Plays'
                    },
                    min: 0,
                    max: Math.max(maxReplayCount + 1, 3),
                    ticks: {
                        stepSize: 1
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Number of Unique Content Items'
                    },
                    beginAtZero: true,
                    max: Math.ceil(maxContentCount * 1.2),
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

function initReplayHeatmap(data) {
    // Create heatmap using Canvas
    const container = document.getElementById('replayHeatmap');
    if (!container || !data.heatmap_data || data.heatmap_data.length === 0) {
        if (container) {
            container.innerHTML = '<p class="no-data">No replay data available for heatmap visualization.</p>';
        }
        return;
    }
    
    // Clear container
    container.innerHTML = '';
    
    // Create canvas
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    
    // Determine dimensions
    const cellSize = data.is_weekly ? 6 : 20;  // Smaller cells for weekly view
    const labelWidth = 200;
    const labelHeight = 30;
    const hours = data.max_hours || 24;
    const contentCount = Object.keys(data.content_info).length;
    
    canvas.width = labelWidth + (hours * cellSize);
    canvas.height = labelHeight + (contentCount * cellSize);
    
    // Set font
    ctx.font = '12px Arial';
    
    // Draw hour labels
    ctx.fillStyle = '#666';
    ctx.font = data.is_weekly ? '10px Arial' : '12px Arial';
    
    if (data.is_weekly) {
        // For weekly, show day markers
        const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        for (let d = 0; d < 7; d++) {
            const x = labelWidth + (d * 24 * cellSize) + (12 * cellSize);
            ctx.textAlign = 'center';
            ctx.fillText(days[d], x, labelHeight - 5);
        }
    } else {
        // For daily, show hourly labels
        for (let h = 0; h < hours; h++) {
            const x = labelWidth + (h * cellSize) + cellSize/2;
            ctx.textAlign = 'center';
            ctx.fillText(h.toString(), x, labelHeight - 5);
        }
    }
    
    // Draw content labels and heatmap cells
    const maxPlays = data.max_plays || 1;
    
    // First, draw all cells as light gray (no plays)
    ctx.fillStyle = '#f0f0f0';
    for (let i = 0; i < contentCount; i++) {
        // Draw content label
        ctx.fillStyle = '#333';
        ctx.textAlign = 'right';
        const contentInfo = data.content_info[i];
        const label = contentInfo ? contentInfo.title.substring(0, 25) : 'Unknown';
        ctx.fillText(label, labelWidth - 5, labelHeight + (i * cellSize) + cellSize/2 + 4);
        
        // Draw empty cells
        ctx.fillStyle = '#f0f0f0';
        for (let h = 0; h < hours; h++) {
            ctx.fillRect(labelWidth + (h * cellSize), labelHeight + (i * cellSize), cellSize - 1, cellSize - 1);
        }
    }
    
    // Draw actual data points
    data.heatmap_data.forEach(point => {
        const intensity = point.play_count / maxPlays;
        const hue = 240 - (intensity * 60); // Blue to red gradient
        const saturation = 50 + (intensity * 50);
        ctx.fillStyle = `hsl(${hue}, ${saturation}%, ${50 - intensity * 20}%)`;
        
        ctx.fillRect(
            labelWidth + (point.hour * cellSize),
            labelHeight + (point.content_index * cellSize),
            cellSize - 1,
            cellSize - 1
        );
    });
    
    container.appendChild(canvas);
    
    // Add tooltip functionality
    canvas.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        if (x > labelWidth && y > labelHeight) {
            const hour = Math.floor((x - labelWidth) / cellSize);
            const contentIndex = Math.floor((y - labelHeight) / cellSize);
            
            if (hour >= 0 && hour < hours && contentIndex >= 0 && contentIndex < contentCount) {
                // Find data point
                const point = data.heatmap_data.find(p => 
                    p.hour === hour && p.content_index === contentIndex
                );
                
                if (point) {
                    let timeLabel = '';
                    if (data.is_weekly) {
                        const day = Math.floor(hour / 24);
                        const hourInDay = hour % 24;
                        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
                        timeLabel = `${days[day]} ${hourInDay}:00`;
                    } else {
                        timeLabel = `Hour ${hour}`;
                    }
                    canvas.title = `${point.content_title}\n${timeLabel}: ${point.play_count} plays`;
                } else {
                    canvas.title = '';
                }
            }
        }
    });
}

function initReplayBoxplotChart(data) {
    // Implement box plot visualization
    const ctx = document.getElementById('replayBoxplotChart').getContext('2d');
    
    // Chart.js doesn't have native box plot support, so we'll use a custom approach
    console.log('Boxplot data:', data);
}

function initFreshnessCharts(data) {
    // Pie chart for replay categories
    const pieCtx = document.getElementById('replayPieChart').getContext('2d');
    new Chart(pieCtx, {
        type: 'pie',
        data: {
            labels: ['Fresh (1 play)', '2-3 plays', '4-5 plays', '6+ plays'],
            datasets: [{
                data: [
                    data.replay_categories.fresh,
                    data.replay_categories['2-3_plays'],
                    data.replay_categories['4-5_plays'],
                    data.replay_categories['6+_plays']
                ],
                backgroundColor: [
                    'rgba(75, 192, 192, 0.8)',
                    'rgba(255, 206, 86, 0.8)',
                    'rgba(255, 159, 64, 0.8)',
                    'rgba(255, 99, 132, 0.8)'
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
    
    // Bar chart for type statistics
    const barCtx = document.getElementById('typeBarChart').getContext('2d');
    const types = Object.keys(data.type_statistics);
    const avgReplays = types.map(t => data.type_statistics[t].average_replays);
    
    new Chart(barCtx, {
        type: 'bar',
        data: {
            labels: types.map(t => t.toUpperCase()),
            datasets: [{
                label: 'Average Replays',
                data: avgReplays,
                backgroundColor: 'rgba(54, 162, 235, 0.8)'
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

function initParetoChart(data) {
    const ctx = document.getElementById('paretoChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.pareto_data.map(d => `#${d.rank}`),
            datasets: [{
                type: 'bar',
                label: 'Play Count',
                data: data.pareto_data.map(d => d.play_count),
                backgroundColor: 'rgba(54, 162, 235, 0.8)',
                yAxisID: 'y'
            }, {
                type: 'line',
                label: 'Cumulative %',
                data: data.pareto_data.map(d => d.cumulative_percentage),
                borderColor: 'rgba(255, 99, 132, 1)',
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                yAxisID: 'y1'
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Play Count'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    max: 100,
                    title: {
                        display: true,
                        text: 'Cumulative %'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    });
}

function initGapHistogram(data) {
    const ctx = document.getElementById('gapHistogramChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.histogram_data.map(d => d.bin),
            datasets: [{
                label: 'Number of Gaps',
                data: data.histogram_data.map(d => d.count),
                backgroundColor: 'rgba(75, 192, 192, 0.8)'
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Distribution of Time Gaps Between Replays'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Number of Occurrences'
                    }
                }
            }
        }
    });
}

function initComprehensiveCharts(data) {
    // Implement comprehensive analysis charts
    console.log('Comprehensive data:', data);
}

// Load Available Content Report
async function reportsLoadAvailableContent() {
    const reportContent = document.getElementById('reportContent');
    
    reportContent.innerHTML = `
        <div class="report-header">
            <button class="button secondary" onclick="reportsBackToMenu()">
                <i class="fas fa-arrow-left"></i> Back to Reports
            </button>
            <h2><i class="fas fa-database"></i> Available Content Report</h2>
        </div>
        
        <div id="reportResults" class="report-results">
            <div class="report-loading">
                <i class="fas fa-spinner fa-spin"></i> Generating report...
            </div>
        </div>
    `;
    
    try {
        const response = await window.API.post('/generate-report', {
            report_type: 'available-content'
        });
        
        if (response.success) {
            reportsDisplayAvailableContentResults(response.data);
        } else {
            throw new Error(response.message || 'Failed to generate report');
        }
    } catch (error) {
        document.getElementById('reportResults').innerHTML = `
            <div class="report-error">
                <i class="fas fa-exclamation-triangle"></i> 
                ${error.message || 'Failed to generate report'}
            </div>
        `;
    }
}

// Display Available Content Results
function reportsDisplayAvailableContentResults(data) {
    const resultsDiv = document.getElementById('reportResults');
    
    // Format category names
    const categoryLabels = {
        'id': 'ID (Station IDs)',
        'spots': 'Spots (30s)',
        'short_form': 'Short Form (30s-15m)',
        'long_form': 'Long Form (15m+)'
    };
    
    let html = `
        <div class="report-results-content">
            <div class="report-timestamp">
                Generated: ${new Date(data.generated_at).toLocaleString()}
            </div>
    `;
    
    // Overview Summary
    html += `
        <div class="report-section">
            <h3>Content Overview</h3>
            <div class="report-stats-grid">
                <div class="stat-card success">
                    <div class="stat-value">${data.totals.active.count}</div>
                    <div class="stat-label">Active Content Items</div>
                    <div class="stat-sublabel">${data.totals.active.hours.toFixed(1)} hours</div>
                </div>
                <div class="stat-card danger">
                    <div class="stat-value">${data.totals.expired.count}</div>
                    <div class="stat-label">Expired Content Items</div>
                    <div class="stat-sublabel">${data.totals.expired.hours.toFixed(1)} hours</div>
                </div>
                <div class="stat-card warning">
                    <div class="stat-value">${data.totals.not_yet_live.count}</div>
                    <div class="stat-label">Not Yet Live</div>
                    <div class="stat-sublabel">${data.totals.not_yet_live.hours.toFixed(1)} hours</div>
                </div>
                <div class="stat-card info">
                    <div class="stat-value">${(data.totals.active.count + data.totals.expired.count + data.totals.not_yet_live.count)}</div>
                    <div class="stat-label">Total Content Items</div>
                    <div class="stat-sublabel">${(data.totals.active.hours + data.totals.expired.hours + data.totals.not_yet_live.hours).toFixed(1)} hours</div>
                </div>
            </div>
        </div>
    `;
    
    // Additional Statistics
    html += `
        <div class="report-section">
            <h3>Active Content Statistics</h3>
            <div class="report-stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${data.additional_stats.content_types}</div>
                    <div class="stat-label">Content Types</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.additional_stats.themes}</div>
                    <div class="stat-label">Unique Themes</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.additional_stats.avg_engagement.toFixed(0)}%</div>
                    <div class="stat-label">Avg. Engagement Score</div>
                </div>
            </div>
        </div>
    `;
    
    // Detailed Breakdown by Category
    html += `
        <div class="report-section">
            <h3>Content by Duration Category</h3>
            <div class="category-breakdown">
                <table class="report-table">
                    <thead>
                        <tr>
                            <th>Duration Category</th>
                            <th colspan="2">Active</th>
                            <th colspan="2">Expired</th>
                            <th colspan="2">Not Yet Live</th>
                            <th colspan="2">Total</th>
                        </tr>
                        <tr class="subheader">
                            <th></th>
                            <th>Count</th>
                            <th>Hours</th>
                            <th>Count</th>
                            <th>Hours</th>
                            <th>Count</th>
                            <th>Hours</th>
                            <th>Count</th>
                            <th>Hours</th>
                        </tr>
                    </thead>
                    <tbody>
    `;
    
    // Add rows for each category
    ['id', 'spots', 'short_form', 'long_form'].forEach(category => {
        const catData = data.categories[category];
        const totalCount = catData.active.count + catData.expired.count + catData.not_yet_live.count;
        const totalHours = catData.active.hours + catData.expired.hours + catData.not_yet_live.hours;
        
        html += `
            <tr>
                <td class="category-name">${categoryLabels[category]}</td>
                <td class="active">${catData.active.count}</td>
                <td class="active">${catData.active.hours.toFixed(1)}</td>
                <td class="expired">${catData.expired.count}</td>
                <td class="expired">${catData.expired.hours.toFixed(1)}</td>
                <td class="not-yet-live">${catData.not_yet_live.count}</td>
                <td class="not-yet-live">${catData.not_yet_live.hours.toFixed(1)}</td>
                <td class="total">${totalCount}</td>
                <td class="total">${totalHours.toFixed(1)}</td>
            </tr>
        `;
    });
    
    html += `
                    </tbody>
                    <tfoot>
                        <tr class="total-row">
                            <td>Total</td>
                            <td class="active">${data.totals.active.count}</td>
                            <td class="active">${data.totals.active.hours.toFixed(1)}</td>
                            <td class="expired">${data.totals.expired.count}</td>
                            <td class="expired">${data.totals.expired.hours.toFixed(1)}</td>
                            <td class="not-yet-live">${data.totals.not_yet_live.count}</td>
                            <td class="not-yet-live">${data.totals.not_yet_live.hours.toFixed(1)}</td>
                            <td class="total">${data.totals.active.count + data.totals.expired.count + data.totals.not_yet_live.count}</td>
                            <td class="total">${(data.totals.active.hours + data.totals.expired.hours + data.totals.not_yet_live.hours).toFixed(1)}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    `;
    
    // Visual Charts section removed per user request
    
    // Add export buttons
    html += `
        <div class="report-actions">
            <button class="button primary" onclick="reportsExportToCSV()">
                <i class="fas fa-file-csv"></i> Export to CSV
            </button>
            <button class="button secondary" onclick="reportsPrint()">
                <i class="fas fa-print"></i> Print Report
            </button>
        </div>
    `;
    
    html += '</div>';
    resultsDiv.innerHTML = html;
    
    // Charts removed per user request - no initialization needed
}

// Load Schedule Content Search Report
async function reportsLoadScheduleContentSearch() {
    const reportContent = document.getElementById('reportContent');
    
    // First, show schedule selector
    reportContent.innerHTML = `
        <div class="report-header">
            <button class="button secondary" onclick="reportsBackToMenu()">
                <i class="fas fa-arrow-left"></i> Back to Reports
            </button>
            <h2><i class="fas fa-search"></i> Schedule Content Search</h2>
        </div>
        
        <div class="report-selector">
            <h3>Select Schedule</h3>
            <div class="schedule-selector-container">
                <select id="scheduleSelect" class="form-select">
                    <option value="">Loading schedules...</option>
                </select>
            </div>
        </div>
        
        <div id="searchContainer" style="display: none;" class="report-selector">
            <h3>Search Content</h3>
            <div class="search-input-container">
                <input type="text" id="searchInput" class="form-input" placeholder="Enter search term (e.g., file name, title, content type)">
                <button class="button primary" onclick="reportsSearchScheduleContent()">
                    <i class="fas fa-search"></i> Search
                </button>
            </div>
        </div>
        
        <div id="reportResults" class="report-results" style="display: none;">
        </div>
    `;
    
    // Load available schedules
    try {
        const response = await window.API.get('/schedules/list');
        
        if (response.success && response.schedules) {
            const select = document.getElementById('scheduleSelect');
            const schedules = response.schedules.sort((a, b) => 
                new Date(b.schedule_date) - new Date(a.schedule_date)
            );
            
            if (schedules.length === 0) {
                select.innerHTML = '<option value="">No schedules available</option>';
            } else {
                select.innerHTML = '<option value="">Select a schedule...</option>';
                schedules.forEach(schedule => {
                    const date = new Date(schedule.schedule_date);
                    const createdAt = schedule.created_at ? new Date(schedule.created_at) : null;
                    const option = document.createElement('option');
                    option.value = schedule.id;
                    
                    // Format the display text with creation time
                    let displayText = `${date.toLocaleDateString()} - ${schedule.schedule_name || 'Unnamed Schedule'} (${schedule.total_items} items)`;
                    if (createdAt) {
                        displayText += ` - Created: ${createdAt.toLocaleDateString()} ${createdAt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}`;
                    }
                    option.textContent = displayText;
                    select.appendChild(option);
                });
                
                // Add change event listener
                select.addEventListener('change', function() {
                    const searchContainer = document.getElementById('searchContainer');
                    const resultsDiv = document.getElementById('reportResults');
                    if (this.value) {
                        searchContainer.style.display = 'block';
                        resultsDiv.style.display = 'none';
                        document.getElementById('searchInput').value = '';
                        document.getElementById('searchInput').focus();
                    } else {
                        searchContainer.style.display = 'none';
                        resultsDiv.style.display = 'none';
                    }
                });
            }
        } else {
            document.getElementById('scheduleSelect').innerHTML = '<option value="">Failed to load schedules</option>';
        }
    } catch (error) {
        console.error('Error loading schedules:', error);
        document.getElementById('scheduleSelect').innerHTML = '<option value="">Error loading schedules</option>';
    }
}

// Search Schedule Content
async function reportsSearchScheduleContent() {
    const scheduleId = document.getElementById('scheduleSelect').value;
    const searchTerm = document.getElementById('searchInput').value.trim();
    
    if (!scheduleId) {
        alert('Please select a schedule first');
        return;
    }
    
    if (!searchTerm) {
        alert('Please enter a search term');
        return;
    }
    
    const resultsDiv = document.getElementById('reportResults');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div class="report-loading">
            <i class="fas fa-spinner fa-spin"></i> Searching schedule content...
        </div>
    `;
    
    try {
        const response = await window.API.post('/generate-report', {
            report_type: 'schedule-content-search',
            schedule_id: scheduleId,
            search_term: searchTerm
        });
        
        if (response.success) {
            reportsDisplayScheduleContentSearchResults(response.data);
        } else {
            throw new Error(response.message || 'Failed to search schedule');
        }
    } catch (error) {
        resultsDiv.innerHTML = `
            <div class="report-error">
                <i class="fas fa-exclamation-triangle"></i> 
                ${error.message || 'Failed to search schedule content'}
            </div>
        `;
    }
}

// Display Schedule Content Search Results
function reportsDisplayScheduleContentSearchResults(data) {
    const resultsDiv = document.getElementById('reportResults');
    
    let html = `
        <div class="report-results-content">
            <div class="report-timestamp">
                Search Term: "<strong>${data.search_term}</strong>" | 
                Schedule: ${data.schedule_name || 'Unnamed'} (${new Date(data.schedule_date).toLocaleDateString()})
            </div>
    `;
    
    if (data.matches.length === 0) {
        html += `
            <div class="report-note">
                <i class="fas fa-info-circle"></i> No content found matching "${data.search_term}"
            </div>
        `;
    } else {
        html += `
            <div class="report-section">
                <h3>Search Results (${data.matches.length} items found)</h3>
                <table class="report-table">
                    <thead>
                        <tr>
                            <th>File Name</th>
                            <th>Content Title</th>
                            <th>Day</th>
                            <th>Start Time</th>
                            <th>Duration</th>
                            <th>Type</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        // Format and display each match
        data.matches.forEach(item => {
            // Parse scheduled time - this is the correct datetime from backend
            const scheduledTime = new Date(item.scheduled_start);
            const dayOfWeek = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][scheduledTime.getDay()];
            const timeStr = scheduledTime.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit', 
                second: '2-digit',
                hour12: false 
            });
            
            // Format duration
            const duration = item.scheduled_duration_seconds;
            const hours = Math.floor(duration / 3600);
            const minutes = Math.floor((duration % 3600) / 60);
            const seconds = Math.floor(duration % 60);
            let durationStr = '';
            if (hours > 0) durationStr += `${hours}h `;
            if (minutes > 0) durationStr += `${minutes}m `;
            durationStr += `${seconds}s`;
            
            // Highlight search term in file name and title
            const highlightTerm = (text) => {
                if (!text) return '';
                const regex = new RegExp(`(${data.search_term})`, 'gi');
                return text.replace(regex, '<mark>$1</mark>');
            };
            
            html += `
                <tr>
                    <td>${highlightTerm(item.file_name)}</td>
                    <td>${highlightTerm(item.content_title || '')}</td>
                    <td>${dayOfWeek}</td>
                    <td>${timeStr}</td>
                    <td>${durationStr}</td>
                    <td><span class="category-badge ${item.duration_category}">${item.duration_category || 'N/A'}</span></td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
        
        // Summary statistics
        html += `
            <div class="report-section">
                <h3>Summary</h3>
                <div class="report-stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${data.matches.length}</div>
                        <div class="stat-label">Total Matches</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${data.unique_days}</div>
                        <div class="stat-label">Days with Matches</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${typeof data.total_duration_hours === 'number' ? data.total_duration_hours.toFixed(1) : '0.0'}</div>
                        <div class="stat-label">Total Hours</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Add export button if there are results
    if (data.matches.length > 0) {
        html += `
            <div class="report-actions">
                <button class="button primary" onclick="reportsExportScheduleSearchToCSV()">
                    <i class="fas fa-file-csv"></i> Export to CSV
                </button>
                <button class="button secondary" onclick="reportsPrint()">
                    <i class="fas fa-print"></i> Print Report
                </button>
            </div>
        `;
    }
    
    html += '</div>';
    resultsDiv.innerHTML = html;
    
    // Store data for export
    window.currentReportData = data;
}

// Export Schedule Search to CSV
function reportsExportScheduleSearchToCSV() {
    if (!window.currentReportData) return;
    
    const data = window.currentReportData;
    let csv = 'File Name,Content Title,Day,Start Date,Start Time,Duration (seconds),Duration Category\n';
    
    data.matches.forEach(item => {
        const scheduledTime = new Date(item.scheduled_start);
        const dayOfWeek = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][scheduledTime.getDay()];
        const dateStr = scheduledTime.toLocaleDateString();
        const timeStr = scheduledTime.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: false 
        });
        
        csv += `"${item.file_name}","${item.content_title || ''}","${dayOfWeek}","${dateStr}","${timeStr}",${item.scheduled_duration_seconds},"${item.duration_category || ''}"\n`;
    });
    
    // Download CSV
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `schedule_content_search_${data.search_term.replace(/[^a-z0-9]/gi, '_')}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
}

// Initialize Available Content Charts
function initAvailableContentCharts(data) {
    // Active Content by Category Chart
    const activeCtx = document.getElementById('activeContentChart').getContext('2d');
    new Chart(activeCtx, {
        type: 'bar',
        data: {
            labels: ['ID', 'Spots', 'Short Form', 'Long Form'],
            datasets: [{
                label: 'Hours',
                data: [
                    data.categories.id.active.hours,
                    data.categories.spots.active.hours,
                    data.categories.short_form.active.hours,
                    data.categories.long_form.active.hours
                ],
                backgroundColor: '#28a745'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Hours of Content'
                    }
                }
            }
        }
    });
    
    // Content Status Distribution Chart
    const statusCtx = document.getElementById('contentStatusChart').getContext('2d');
    new Chart(statusCtx, {
        type: 'doughnut',
        data: {
            labels: ['Active', 'Expired', 'Not Yet Live'],
            datasets: [{
                data: [
                    data.totals.active.count,
                    data.totals.expired.count,
                    data.totals.not_yet_live.count
                ],
                backgroundColor: ['#28a745', '#dc3545', '#ffc107']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} items (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
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

// Filter by day for weekly schedules
async function reportsFilterByDay() {
    const daySelect = document.getElementById('weeklyDayFilter');
    if (!daySelect) return;
    
    const selectedDay = daySelect.value;
    
    // Get the schedule ID from the report data or state
    const scheduleId = reportsState.reportData?.schedule?.id;
    
    if (!scheduleId) {
        console.error('No schedule ID found in report data');
        return;
    }
    
    // Show loading state
    const reportResults = document.getElementById('reportResults');
    reportResults.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Regenerating report...</div>';
    
    try {
        // Determine current report type
        const currentReportId = reportsState.currentReport.id;
        
        // Build request with day filter
        let requestData = {
            report_type: currentReportId,
            schedule_id: parseInt(scheduleId)
        };
        
        // Add day filter to URL params
        let url = '/generate-report';
        if (selectedDay) {
            url += `?day=${selectedDay}`;
        }
        
        const response = await window.API.post(url, requestData);
        
        if (response.success) {
            // Store the updated report data
            reportsState.reportData = response.data;
            renderVisualization(currentReportId, response.data, reportResults);
        } else {
            reportResults.innerHTML = `<div class="error">Failed to generate report: ${response.message || 'Unknown error'}</div>`;
        }
    } catch (error) {
        console.error('Error filtering report:', error);
        reportResults.innerHTML = '<div class="error">Failed to regenerate report</div>';
    }
}

// Export functions
window.reportsInit = reportsInit;
window.reportsOpenReport = reportsOpenReport;
window.reportsGenerateScheduleAnalysis = reportsGenerateScheduleAnalysis;
window.reportsGenerateVisualization = reportsGenerateVisualization;
window.reportsLoadScheduleBasedReport = reportsLoadScheduleBasedReport;
window.reportsBackToMenu = reportsBackToMenu;
window.reportsExportToCSV = reportsExportToCSV;
window.reportsPrint = reportsPrint;
window.reportsFilterByDay = reportsFilterByDay;