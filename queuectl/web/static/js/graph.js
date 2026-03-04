// Dependency Graph Visualization with D3.js

let svg, g, zoom, simulation;
let nodes = [], links = [];

// Color mapping for job states
const stateColors = {
    'completed': '#10b981',
    'processing': '#3b82f6',
    'pending': '#fbbf24',
    'failed': '#ef4444',
    'cancelled': '#6b7280',
    'dead': '#4b5563'
};

// Initialize the graph
function initGraph() {
    const width = document.getElementById('graph-svg').clientWidth;
    const height = 700;

    svg = d3.select('#graph-svg')
        .attr('width', width)
        .attr('height', height);

    // Clear existing content
    svg.selectAll('*').remove();

    // Create zoom behavior
    zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);

    // Create main group
    g = svg.append('g');

    // Create arrow marker for links
    svg.append('defs').append('marker')
        .attr('id', 'arrowhead')
        .attr('viewBox', '-0 -5 10 10')
        .attr('refX', 25)
        .attr('refY', 0)
        .attr('orient', 'auto')
        .attr('markerWidth', 8)
        .attr('markerHeight', 8)
        .append('svg:path')
        .attr('d', 'M 0,-5 L 10,0 L 0,5')
        .attr('class', 'link-arrow');

    // Create force simulation
    simulation = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(150))
        .force('charge', d3.forceManyBody().strength(-500))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(50));
}

// Load graph data from API
async function loadGraph() {
    try {
        // Get all jobs
        const response = await fetch('/api/jobs?limit=1000');
        const jobs = await response.json();

        // Build nodes
        nodes = jobs.map(job => ({
            id: job.id,
            label: job.command.substring(0, 20) + (job.command.length > 20 ? '...' : ''),
            state: job.state,
            fullData: job
        }));

        // Build links from dependencies
        links = [];
        for (const job of jobs) {
            if (job.dependencies) {
                const deps = JSON.parse(job.dependencies || '[]');
                deps.forEach(depId => {
                    links.push({
                        source: depId,
                        target: job.id
                    });
                });
            }
        }

        // Also fetch from dependency API
        const depsResponse = await fetch('/api/dependencies/blocked');
        const blocked = await depsResponse.json();
        
        blocked.forEach(job => {
            job.dependencies.forEach(depId => {
                // Avoid duplicates
                if (!links.find(l => l.source === depId && l.target === job.id)) {
                    links.push({
                        source: depId,
                        target: job.id
                    });
                }
            });
        });

        renderGraph();
    } catch (error) {
        console.error('Error loading graph:', error);
    }
}

// Render the graph
function renderGraph() {
    if (!g) initGraph();

    // Clear existing elements
    g.selectAll('.link').remove();
    g.selectAll('.node').remove();

    // Create links
    const link = g.append('g')
        .selectAll('.link')
        .data(links)
        .enter()
        .append('line')
        .attr('class', 'link')
        .attr('stroke', '#64748b')
        .attr('marker-end', 'url(#arrowhead)');

    // Create nodes
    const node = g.append('g')
        .selectAll('.node')
        .data(nodes)
        .enter()
        .append('g')
        .attr('class', 'node')
        .call(d3.drag()
            .on('start', dragStarted)
            .on('drag', dragged)
            .on('end', dragEnded))
        .on('click', showJobDetails);

    // Add circles to nodes
    node.append('circle')
        .attr('r', 20)
        .attr('fill', d => stateColors[d.state] || '#6b7280')
        .attr('stroke', '#fff');

    // Add labels to nodes
    node.append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .attr('fill', '#f1f5f9')
        .text(d => d.label);

    // Update simulation
    simulation
        .nodes(nodes)
        .on('tick', ticked);

    simulation.force('link')
        .links(links);

    simulation.alpha(1).restart();

    function ticked() {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node
            .attr('transform', d => `translate(${d.x},${d.y})`);
    }
}

// Drag functions
function dragStarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragEnded(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

// Show job details in side panel
function showJobDetails(event, d) {
    const panel = document.getElementById('detailsPanel');
    const content = document.getElementById('panelContent');

    const job = d.fullData;

    content.innerHTML = `
        <h3 style="margin-bottom: 1rem; color: var(--text-primary);">Job Details</h3>
        
        <div style="margin-bottom: 1.5rem;">
            <div style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 0.25rem;">ID</div>
            <code style="color: var(--text-primary);">${job.id}</code>
        </div>

        <div style="margin-bottom: 1.5rem;">
            <div style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 0.25rem;">Command</div>
            <div style="color: var(--text-primary); word-break: break-all;">${job.command}</div>
        </div>

        <div style="margin-bottom: 1.5rem;">
            <div style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 0.25rem;">State</div>
            <span class="badge badge-${job.state}">${job.state}</span>
        </div>

        <div style="margin-bottom: 1.5rem;">
            <div style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 0.25rem;">Priority</div>
            <span class="priority-badge priority-${job.priority_name}">${job.priority_name}</span>
        </div>

        <div style="margin-bottom: 1.5rem;">
            <div style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 0.25rem;">Attempts</div>
            <div style="color: var(--text-primary);">${job.attempts} / ${job.max_retries}</div>
        </div>

        <div style="margin-bottom: 1.5rem;">
            <div style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 0.25rem;">Created</div>
            <div style="color: var(--text-primary);">${new Date(job.created_at).toLocaleString()}</div>
        </div>

        <div style="display: flex; gap: 0.5rem; flex-direction: column;">
            <a href="/logs/${job.id}" class="btn btn-primary" style="text-align: center;">
                <span class="icon">📜</span> View Logs
            </a>
            <button class="btn btn-secondary" onclick="cancelJob('${job.id}')">
                <span class="icon">❌</span> Cancel Job
            </button>
        </div>
    `;

    panel.classList.add('open');
}

function closePanel() {
    document.getElementById('detailsPanel').classList.remove('open');
}

// Control functions
function resetZoom() {
    svg.transition().duration(750).call(
        zoom.transform,
        d3.zoomIdentity
    );
}

function fitToScreen() {
    const bounds = g.node().getBBox();
    const parent = svg.node().parentElement;
    const fullWidth = parent.clientWidth;
    const fullHeight = 700;
    const width = bounds.width;
    const height = bounds.height;
    const midX = bounds.x + width / 2;
    const midY = bounds.y + height / 2;

    if (width === 0 || height === 0) return;

    const scale = 0.9 / Math.max(width / fullWidth, height / fullHeight);
    const translate = [fullWidth / 2 - scale * midX, fullHeight / 2 - scale * midY];

    svg.transition().duration(750).call(
        zoom.transform,
        d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
    );
}

function exportGraph() {
    const svgElement = document.getElementById('graph-svg');
    const serializer = new XMLSerializer();
    const svgString = serializer.serializeToString(svgElement);
    const blob = new Blob([svgString], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'dependency-graph.svg';
    a.click();
    URL.revokeObjectURL(url);
}

async function cancelJob(jobId) {
    if (!confirm('Are you sure you want to cancel this job?')) return;

    try {
        const response = await fetch(`/api/jobs/${jobId}/cancel`, {
            method: 'POST'
        });
        const result = await response.json();

        if (result.success) {
            alert('Job cancelled successfully');
            closePanel();
            loadGraph();
        } else {
            alert('Failed to cancel job: ' + result.message);
        }
    } catch (error) {
        alert('Error cancelling job: ' + error.message);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initGraph();
    loadGraph();

    // Auto-refresh every 10 seconds
    setInterval(loadGraph, 10000);
});
