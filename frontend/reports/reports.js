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
            await reportsLoadScheduleBasedReport(reportId);
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
    
    // Show schedule selector
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
        const response = await window.API.post('/generate-report', {
            report_type: reportId,
            schedule_id: parseInt(scheduleId)
        });
        
        if (response.success) {
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
    
    return `
        <div class="report-section">
            <h3>Content Replay Distribution by Duration Category</h3>
            <p>Shows how many times unique content items are replayed, forming a distribution curve.</p>
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
            <p>Visual representation of when content is replayed throughout the day. Darker colors indicate more replays.</p>
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
                        text: 'Number of Plays'
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
    // Implement heatmap visualization
    // This would require a heatmap library or custom implementation
    console.log('Heatmap data:', data);
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
window.reportsGenerateVisualization = reportsGenerateVisualization;
window.reportsLoadScheduleBasedReport = reportsLoadScheduleBasedReport;
window.reportsBackToMenu = reportsBackToMenu;
window.reportsExportToCSV = reportsExportToCSV;
window.reportsPrint = reportsPrint;