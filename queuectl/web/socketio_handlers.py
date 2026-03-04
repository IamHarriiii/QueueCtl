"""
WebSocket event handlers for real-time log streaming.

These handlers require flask-socketio to be installed.
They are registered by app.py when SocketIO is available.
"""
import time
import threading

# These globals are injected by register_socketio_handlers()
socketio = None
storage = None
queue = None
active_streams = {}


def register_socketio_handlers(sio, app, storage_instance, queue_instance):
    """Register SocketIO event handlers with the given app context."""
    global socketio, storage, queue
    socketio = sio
    storage = storage_instance
    queue = queue_instance

    from flask_socketio import emit, join_room, leave_room
    from flask import request, render_template

    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        print(f'Client connected: {request.sid}')
        emit('connected', {'message': 'Connected to Queuectl'})

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        print(f'Client disconnected: {request.sid}')
        if request.sid in active_streams:
            active_streams[request.sid]['active'] = False
            del active_streams[request.sid]

    @socketio.on('subscribe_job')
    def handle_subscribe_job(data):
        """Subscribe to real-time updates for a specific job"""
        job_id = data.get('job_id')

        if not job_id:
            emit('error', {'message': 'job_id is required'})
            return

        join_room(f'job_{job_id}')

        job = queue_instance.get_job(job_id)
        if job:
            emit('job_update', job.to_dict())
            if job.state == 'processing':
                _start_log_stream(job_id, request.sid)
        else:
            emit('error', {'message': 'Job not found'})

    @socketio.on('unsubscribe_job')
    def handle_unsubscribe_job(data):
        """Unsubscribe from job updates"""
        job_id = data.get('job_id')
        if job_id:
            leave_room(f'job_{job_id}')
            if request.sid in active_streams:
                active_streams[request.sid]['active'] = False

    @app.route('/logs/<job_id>')
    def logs_page(job_id):
        """Job logs viewer page"""
        return render_template('logs.html', job_id=job_id)


def _start_log_stream(job_id, client_id):
    """Start streaming job logs to client in a background thread."""

    def stream_logs():
        last_stdout_len = 0
        last_stderr_len = 0
        active_streams[client_id] = {'active': True, 'job_id': job_id}

        while active_streams.get(client_id, {}).get('active', False):
            job_data = storage.get_job(job_id)
            if not job_data:
                break

            stdout = job_data.get('stdout', '') or ''
            if len(stdout) > last_stdout_len:
                new_output = stdout[last_stdout_len:]
                socketio.emit('log_output', {
                    'job_id': job_id,
                    'stream': 'stdout',
                    'data': new_output
                }, room=f'job_{job_id}')
                last_stdout_len = len(stdout)

            stderr = job_data.get('stderr', '') or ''
            if len(stderr) > last_stderr_len:
                new_output = stderr[last_stderr_len:]
                socketio.emit('log_output', {
                    'job_id': job_id,
                    'stream': 'stderr',
                    'data': new_output
                }, room=f'job_{job_id}')
                last_stderr_len = len(stderr)

            if job_data['state'] not in ['processing', 'pending']:
                socketio.emit('job_complete', {
                    'job_id': job_id,
                    'state': job_data['state'],
                    'exit_code': job_data.get('exit_code')
                }, room=f'job_{job_id}')
                break

            time.sleep(0.5)

        if client_id in active_streams:
            del active_streams[client_id]

    thread = threading.Thread(target=stream_logs)
    thread.daemon = True
    thread.start()
