
# WebSocket event handlers for real-time log streaming

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f'Client connected: {request.sid}')
    emit('connected', {'message': 'Connected to Queuectl'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f'Client disconnected: {request.sid}')
    # Clean up any active streams for this client
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
    
    # Join room for this job
    join_room(f'job_{job_id}')
    
    # Send initial job data
    job = queue.get_job(job_id)
    if job:
        emit('job_update', job.to_dict())
        
        # Start streaming logs if job is processing
        if job.state == 'processing':
            start_log_stream(job_id, request.sid)
    else:
        emit('error', {'message': 'Job not found'})


@socketio.on('unsubscribe_job')
def handle_unsubscribe_job(data):
    """Unsubscribe from job updates"""
    job_id = data.get('job_id')
    
    if job_id:
        leave_room(f'job_{job_id}')
        
        # Stop log stream if active
        if request.sid in active_streams:
            active_streams[request.sid]['active'] = False


def start_log_stream(job_id, client_id):
    """Start streaming job logs to client"""
    
    def stream_logs():
        """Background thread to stream logs"""
        last_stdout_len = 0
        last_stderr_len = 0
        
        active_streams[client_id] = {'active': True, 'job_id': job_id}
        
        while active_streams.get(client_id, {}).get('active', False):
            # Get current job state
            job_data = storage.get_job(job_id)
            
            if not job_data:
                break
            
            # Stream stdout updates
            stdout = job_data.get('stdout', '') or ''
            if len(stdout) > last_stdout_len:
                new_output = stdout[last_stdout_len:]
                socketio.emit('log_output', {
                    'job_id': job_id,
                    'stream': 'stdout',
                    'data': new_output
                }, room=f'job_{job_id}')
                last_stdout_len = len(stdout)
            
            # Stream stderr updates
            stderr = job_data.get('stderr', '') or ''
            if len(stderr) > last_stderr_len:
                new_output = stderr[last_stderr_len:]
                socketio.emit('log_output', {
                    'job_id': job_id,
                    'stream': 'stderr',
                    'data': new_output
                }, room=f'job_{job_id}')
                last_stderr_len = len(stderr)
            
            # Check if job is still processing
            if job_data['state'] not in ['processing', 'pending']:
                # Job completed, send final update
                socketio.emit('job_complete', {
                    'job_id': job_id,
                    'state': job_data['state'],
                    'exit_code': job_data.get('exit_code')
                }, room=f'job_{job_id}')
                break
            
            time.sleep(0.5)  # Poll every 500ms
        
        # Clean up
        if client_id in active_streams:
            del active_streams[client_id]
    
    # Start background thread
    thread = threading.Thread(target=stream_logs)
    thread.daemon = True
    thread.start()


@app.route('/logs/<job_id>')
def logs_page(job_id):
    """Job logs viewer page"""
    return render_template('logs.html', job_id=job_id)


# Add this to the existing app.py file after the other routes
