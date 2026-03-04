// Queuectl Dashboard JavaScript

let chart = null;

// Fetch and update dashboard data
async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateStats(data);
    } catch (error) {
        console.error('Error fetching status:', error);
    }
}

async function fetchMetrics() {
    try {
        const response = await fetch('/api/metrics?period=24');
        const data = await response.json();
        updateMetrics(data);
    } catch (error) {
        console.error('Error fetching metrics:', error);
    }
}

async function fetchJobs() {
    try {
        const response = await fetch('/api/jobs?limit=10');
        const jobs = await response.json();
        updateRecentActivity(jobs);
    } catch (error) {
        console.error('Error fetching jobs:', error);
    }
}

function updateStats(data) {
    const jobs = data.jobs;
    
    document.getElementById('stat-pending').textContent = jobs.pending || 0;
    document.getElementById('stat-processing').textContent = jobs.processing || 0;
    document.getElementById('stat-completed').textContent = jobs.completed || 0;
    document.getElementById('stat-failed').textContent = jobs.failed || 0;
    document.getElementById('stat-workers').textContent = data.active_workers || 0;
    document.getElementById('stat-total').textContent = data.total_jobs || 0;
    
    updateChart(jobs);
}

function updateChart(jobs) {
    const ctx = document.getElementById('jobDistChart');
    
    if (chart) {
        chart.destroy();
    }
    
    chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Pending', 'Processing', 'Completed', 'Failed', 'Dead'],
            datasets: [{
                data: [
                    jobs.pending || 0,
                    jobs.processing || 0,
                    jobs.completed || 0,
                    jobs.failed || 0,
                    jobs.dead || 0
                ],
                backgroundColor: [
                    'rgba(251, 191, 36, 0.8)',
                    'rgba(59, 130, 246, 0.8)',
                    'rgba(16, 185, 129, 0.8)',
                    'rgba(239, 68, 68, 0.8)',
                    'rgba(107, 114, 128, 0.8)'
                ],
                borderColor: [
                    'rgba(251, 191, 36, 1)',
                    'rgba(59, 130, 246, 1)',
                    'rgba(16, 185, 129, 1)',
                    'rgba(239, 68, 68, 1)',
                    'rgba(107, 114, 128, 1)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#f1f5f9',
                        padding: 15,
                        font: {
                            size: 12
                        }
                    }
                }
            }
        }
    });
}

function updateMetrics(data) {
    const stats = data.job_stats;
    
    document.getElementById('metric-processed').textContent = stats.jobs_processed || 0;
    document.getElementById('metric-success-rate').textContent = (stats.success_rate || 0) + '%';
    document.getElementById('metric-avg-time').textContent = (stats.avg_execution_time || 0).toFixed(2) + 's';
    document.getElementById('metric-avg-retries').textContent = (stats.avg_retries || 0).toFixed(2);
}

function updateRecentActivity(jobs) {
    const container = document.getElementById('recentActivity');
    
    if (jobs.length === 0) {
        container.innerHTML = `
            <div class="activity-item">
                <div class="activity-icon">📭</div>
                <div class="activity-content">
                    <div class="activity-title">No recent jobs</div>
                    <div class="activity-time">Queue is empty</div>
                </div>
            </div>
        `;
        return;
    }
    
    const stateIcons = {
        'pending': '⏳',
        'processing': '⚙️',
        'completed': '✅',
        'failed': '❌',
        'dead': '💀',
        'cancelled': '🚫'
    };
    
    container.innerHTML = jobs.map(job => {
        const icon = stateIcons[job.state] || '📄';
        const timeAgo = getTimeAgo(job.updated_at);
        const command = job.command.length > 40 ? job.command.substring(0, 40) + '...' : job.command;
        
        return `
            <div class="activity-item">
                <div class="activity-icon">${icon}</div>
                <div class="activity-content">
                    <div class="activity-title">${command}</div>
                    <div class="activity-time">${job.state} • ${timeAgo}</div>
                </div>
            </div>
        `;
    }).join('');
}

function getTimeAgo(timestamp) {
    if (!timestamp) return 'Unknown';
    
    const now = new Date();
    const then = new Date(timestamp);
    const seconds = Math.floor((now - then) / 1000);
    
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
    if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
    return Math.floor(seconds / 86400) + 'd ago';
}

function refreshData() {
    fetchStatus();
    fetchMetrics();
    fetchJobs();
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    refreshData();
    
    // Auto-refresh every 5 seconds
    setInterval(refreshData, 5000);
});
