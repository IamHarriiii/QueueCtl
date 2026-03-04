"""
Metrics tracking system for queuectl
Tracks job execution statistics and performance metrics
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .storage import Storage

logger = logging.getLogger('queuectl.metrics')


class MetricsTracker:
    """Tracks and records job queue metrics"""
    
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
    
    def record_metric(self, metric_name: str, metric_value: float,
                      metadata: Dict = None) -> None:
        """
        Record a metric value
        
        Args:
            metric_name: Name of the metric
            metric_value: Numeric value
            metadata: Optional metadata as dict
        """
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO metrics (metric_name, metric_value, metadata)
                   VALUES (?, ?, ?)''',
                (metric_name, metric_value, json.dumps(metadata) if metadata else None)
            )
    
    def get_job_stats(self, period_hours: int = 24) -> Dict:
        """
        Get job statistics for a time period
        
        Args:
            period_hours: Number of hours to look back
            
        Returns:
            Dictionary with job statistics
        """
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(hours=period_hours)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Jobs processed
            cursor.execute('''
                SELECT COUNT(*) FROM jobs 
                WHERE updated_at >= ? AND state IN ('completed', 'failed', 'dead')
            ''', (cutoff,))
            jobs_processed = cursor.fetchone()[0]
            
            # Success rate
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
                    COUNT(*) as total
                FROM jobs 
                WHERE updated_at >= ? AND state IN ('completed', 'failed', 'dead')
            ''', (cutoff,))
            row = cursor.fetchone()
            completed = row[0] or 0
            total = row[1] or 0
            success_rate = (completed / total * 100) if total > 0 else 0
            
            # Average execution time (from metrics)
            cursor.execute('''
                SELECT AVG(metric_value) FROM metrics
                WHERE metric_name = 'job_execution_time' 
                AND timestamp >= ?
            ''', (cutoff,))
            avg_execution_time = cursor.fetchone()[0] or 0
            
            # Retry rate
            cursor.execute('''
                SELECT AVG(attempts) FROM jobs
                WHERE updated_at >= ? AND state IN ('completed', 'failed', 'dead')
            ''', (cutoff,))
            avg_retries = cursor.fetchone()[0] or 0
            
            return {
                'period_hours': period_hours,
                'jobs_processed': jobs_processed,
                'success_rate': round(success_rate, 2),
                'avg_execution_time': round(avg_execution_time, 2),
                'avg_retries': round(avg_retries, 2),
            }
    
    def get_queue_depth_over_time(self, period_hours: int = 24) -> List[Dict]:
        """
        Get queue depth metrics over time
        
        Args:
            period_hours: Number of hours to look back
            
        Returns:
            List of queue depth measurements
        """
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(hours=period_hours)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT timestamp, metric_value, metadata
                FROM metrics
                WHERE metric_name = 'queue_depth' AND timestamp >= ?
                ORDER BY timestamp
            ''', (cutoff,))
            
            return [
                {
                    'timestamp': row[0],
                    'depth': row[1],
                    'metadata': json.loads(row[2]) if row[2] else {}
                }
                for row in cursor.fetchall()
            ]
    
    def get_worker_utilization(self, period_hours: int = 24) -> Dict:
        """
        Get worker utilization metrics
        
        Args:
            period_hours: Number of hours to look back
            
        Returns:
            Worker utilization statistics
        """
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(hours=period_hours)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT AVG(metric_value), MAX(metric_value)
                FROM metrics
                WHERE metric_name = 'active_workers' AND timestamp >= ?
            ''', (cutoff,))
            
            row = cursor.fetchone()
            avg_workers = row[0] or 0
            max_workers = row[1] or 0
            
            return {
                'avg_active_workers': round(avg_workers, 2),
                'max_active_workers': int(max_workers),
            }
    
    def record_queue_snapshot(self) -> None:
        """Record current queue state as metrics"""
        stats = self.storage.get_job_stats()
        
        # Record queue depth
        queue_depth = stats.get('pending', 0) + stats.get('processing', 0)
        self.record_metric('queue_depth', queue_depth, {
            'pending': stats.get('pending', 0),
            'processing': stats.get('processing', 0)
        })
        
        # Record state counts
        for state, count in stats.items():
            if state != 'total':
                self.record_metric(f'jobs_{state}', count)
    
    def export_metrics(self, period_hours: int = 24, format: str = 'json') -> str:
        """
        Export metrics in specified format
        
        Args:
            period_hours: Number of hours to look back
            format: Export format ('json' or 'csv')
            
        Returns:
            Formatted metrics data
        """
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(hours=period_hours)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT metric_name, metric_value, timestamp, metadata
                FROM metrics
                WHERE timestamp >= ?
                ORDER BY timestamp
            ''', (cutoff,))
            
            rows = cursor.fetchall()
            
            if format == 'json':
                data = [
                    {
                        'metric': row[0],
                        'value': row[1],
                        'timestamp': row[2],
                        'metadata': json.loads(row[3]) if row[3] else {}
                    }
                    for row in rows
                ]
                return json.dumps(data, indent=2)
            
            elif format == 'csv':
                lines = ['metric,value,timestamp,metadata']
                for row in rows:
                    metadata_str = row[3] if row[3] else ''
                    lines.append(f'{row[0]},{row[1]},{row[2]},"{metadata_str}"')
                return '\n'.join(lines)
            
            else:
                raise ValueError(f"Unsupported format: {format}")
