"""
Flask web application for queuectl dashboard
Provides real-time monitoring and management interface with WebSocket support
Features: API token authentication, real-time updates, job management
"""
from flask import Flask, render_template, jsonify, request, abort
from flask_cors import CORS
import os
import sys
import json
import time
import threading
import logging
from pathlib import Path
from functools import wraps

# Add parent directory to path for imports
parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from queuectl.storage import Storage
from queuectl.config import Config
from queuectl.queue import Queue
from queuectl.models import Job, JobState, JobPriority
from queuectl.dependencies import DependencyResolver
from queuectl.metrics import MetricsTracker

logger = logging.getLogger('queuectl.web')

# Initialize Flask app
app = Flask(__name__)
CORS(app)

try:
    from flask_socketio import SocketIO, emit
    socketio = SocketIO(app, cors_allowed_origins="*")
except ImportError:
    socketio = None

# Initialize components
storage = Storage()
config = Config(storage)
queue = Queue(storage, config)
deps = DependencyResolver(storage)
metrics = MetricsTracker(storage)

# Track active log streams
active_streams = {}

# API Token from environment
API_TOKEN = os.environ.get('QUEUECTL_API_TOKEN', None)


def require_auth(f):
    """Decorator to require API token authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_TOKEN:
            auth = request.headers.get('Authorization', '')
            if not auth.startswith('Bearer ') or auth[7:] != API_TOKEN:
                return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ============================================================================
# HTTP Routes
# ============================================================================

@app.route('/')
def index():
    """Dashboard home page"""
    return render_template('dashboard.html')


@app.route('/jobs')
def jobs_page():
    """Jobs list page"""
    return render_template('jobs.html')


@app.route('/logs/<job_id>')
def logs_page(job_id):
    """Job logs viewer page"""
    return render_template('logs.html', job_id=job_id)


@app.route('/api/status')
@require_auth
def api_status():
    """Get queue status"""
    status = queue.get_status()
    status['config'] = config.get_all()
    return jsonify(status)


@app.route('/api/jobs')
@require_auth
def api_jobs():
    """Get jobs list with optional filtering"""
    state = request.args.get('state')
    priority = request.args.get('priority')
    tag = request.args.get('tag')
    pool = request.args.get('pool')
    limit = int(request.args.get('limit', 50))
    
    jobs_list = storage.list_jobs(state=state, tags=tag, pool=pool)
    
    # Filter by priority
    if priority:
        priority_int = JobPriority.from_string(priority)
        jobs_list = [j for j in jobs_list if j.get('priority') == priority_int]
    
    jobs_list = jobs_list[:limit]
    
    return jsonify({
        'jobs': jobs_list,
        'total': len(jobs_list)
    })


@app.route('/api/jobs/<job_id>')
@require_auth
def api_job_detail(job_id):
    """Get detailed job information"""
    job_data = storage.get_job(job_id)
    
    if not job_data:
        return jsonify({'error': 'Job not found'}), 404
    
    # Add dependency info
    try:
        dep_list = deps.get_dependencies(job_id)
        dependents = deps.get_dependents(job_id)
        job_data['dependency_info'] = {
            'depends_on': dep_list,
            'depended_by': dependents,
            'dependencies_met': deps.are_dependencies_met(job_id)
        }
    except Exception:
        job_data['dependency_info'] = None
    
    # Add audit trail
    try:
        job_data['audit_trail'] = storage.get_audit_log(job_id)
    except Exception:
        job_data['audit_trail'] = []
    
    return jsonify(job_data)


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
@require_auth
def api_cancel_job(job_id):
    """Cancel a job"""
    success = storage.cancel_job(job_id)
    if success:
        return jsonify({'success': True, 'message': f'Job {job_id} cancelled'})
    return jsonify({'success': False, 'message': 'Failed to cancel job'}), 400


@app.route('/api/jobs/<job_id>/retry', methods=['POST'])
@require_auth
def api_retry_job(job_id):
    """Retry a job from DLQ"""
    success = queue.retry_job(job_id)
    if success:
        return jsonify({'success': True, 'message': f'Job {job_id} retried'})
    return jsonify({'success': False, 'message': 'Failed to retry job'}), 400


@app.route('/api/metrics')
@require_auth
def api_metrics():
    """Get metrics data"""
    period = int(request.args.get('period', 24))
    
    stats = metrics.get_job_stats(period_hours=period)
    worker_util = metrics.get_worker_utilization(period_hours=period)
    queue_depth = metrics.get_queue_depth_over_time(period_hours=period)
    
    return jsonify({
        'stats': stats,
        'worker_utilization': worker_util,
        'queue_depth': queue_depth
    })


@app.route('/api/dependencies/<job_id>')
@require_auth
def api_dependency_tree(job_id):
    """Get dependency tree for a job"""
    tree = deps.get_dependency_tree(job_id)
    return jsonify(tree)


@app.route('/api/blocked')
@require_auth
def api_blocked_jobs():
    """Get jobs blocked by dependencies"""
    blocked = deps.get_blocked_jobs()
    return jsonify({'blocked_jobs': blocked})


@app.route('/api/audit/<job_id>')
@require_auth
def api_audit(job_id):
    """Get audit trail for a job"""
    trail = storage.get_audit_log(job_id)
    return jsonify({'audit_trail': trail})


# ============================================================================
# WebSocket Event Handlers
# ============================================================================

if socketio:
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        logger.debug(f"Client connected: {request.sid}")
        emit('connected', {'status': 'connected'})


    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        client_id = request.sid
        if client_id in active_streams:
            active_streams[client_id]['active'] = False
            del active_streams[client_id]
        logger.debug(f"Client disconnected: {client_id}")


    @socketio.on('subscribe_job')
    def handle_subscribe_job(data):
        """Subscribe to real-time updates for a specific job"""
        job_id = data.get('job_id')
        client_id = request.sid
        
        if not job_id:
            emit('error', {'message': 'job_id is required'})
            return
        
        job_data = storage.get_job(job_id)
        if not job_data:
            emit('error', {'message': f'Job {job_id} not found'})
            return
        
        emit('job_update', job_data)
        start_log_stream(job_id, client_id)


    @socketio.on('unsubscribe_job')
    def handle_unsubscribe_job(data):
        """Unsubscribe from job updates"""
        client_id = request.sid
        if client_id in active_streams:
            active_streams[client_id]['active'] = False
            del active_streams[client_id]
        emit('unsubscribed', {'status': 'unsubscribed'})


def start_log_stream(job_id, client_id):
    """Start streaming job logs to client"""
    def stream_logs():
        last_state = None
        last_stdout = None
        
        stream_info = active_streams.get(client_id, {})
        
        while stream_info.get('active', False):
            job_data = storage.get_job(job_id)
            if not job_data:
                break
            
            current_state = job_data.get('state')
            current_stdout = job_data.get('stdout')
            
            if current_state != last_state or current_stdout != last_stdout:
                if socketio:
                    socketio.emit('job_update', job_data, to=client_id)
                    
                    if current_stdout and current_stdout != last_stdout:
                        new_output = current_stdout
                        if last_stdout:
                            new_output = current_stdout[len(last_stdout):]
                        
                        if new_output:
                            socketio.emit('log_output', {
                                'job_id': job_id,
                                'output': new_output,
                                'stream': 'stdout'
                            }, to=client_id)
                
                last_state = current_state
                last_stdout = current_stdout
                
                if current_state in ['completed', 'failed', 'dead', 'cancelled']:
                    if job_data.get('stderr'):
                        if socketio:
                            socketio.emit('log_output', {
                                'job_id': job_id,
                                'output': job_data['stderr'],
                                'stream': 'stderr'
                            }, to=client_id)
                    break
            
            time.sleep(1)
    
    # Store stream info
    active_streams[client_id] = {
        'job_id': job_id,
        'active': True
    }
    
    thread = threading.Thread(target=stream_logs, daemon=True)
    thread.start()


# ============================================================================
# Server Runner
# ============================================================================

def run_dashboard(host='0.0.0.0', port=5000, debug=False):
    """Run the dashboard server"""
    auth_status = "enabled (set QUEUECTL_API_TOKEN)" if API_TOKEN else "disabled"
    logger.info(f"Starting dashboard on {host}:{port} (auth: {auth_status})")
    
    if socketio:
        socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
    else:
        app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_dashboard(debug=True)
